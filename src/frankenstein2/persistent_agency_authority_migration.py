"""Explicit WP206 G1 -> current UnifiedDB authority-receipt migration.

F2-WP-206 generation 3.

The accepted G1 writer persisted ``UnifiedDBFingerprint.receipt_sha256()`` while the
current reader expects ``FRANKENSTEIN2_UNIFIEDDB_BOUND_FILE_AUTHORITY/v1``.  Both are
unversioned 64-hex values in the historical checkpoint column, so this module MUST NOT
classify or migrate a legacy row from shape alone.

Migration is deliberately explicit and fail-closed:

* the caller supplies the exact expected legacy receipt from an external admitted
  migration/recovery record;
* the caller supplies the exact expected checkpoint digest;
* canonical path/device/inode and typed checkpoint bytes are verified before mutation;
* the checkpoint row is updated with a compare-and-swap predicate over all bound fields;
* a versioned append-only migration receipt is stored in the same canonical UnifiedDB;
* the unchanged current WP206 reader must successfully replay the migrated row before
  the transaction commits.

This module does not address same-inode live SQLite data/schema drift.  It creates no
second truth store and grants no scheduler, effect, completion, model, provider or
whole-system authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import sqlite3
from typing import Any, Iterable, Mapping

from frankenstein2.persistent_agency_kernel import (
    CHECKPOINT_TABLE,
    CanonicalPersistentAgencyStore,
    PersistentAgencyCheckpoint,
    PersistentAgencyError,
)

MIGRATION_SCHEMA = "FRANKENSTEIN2_WP206_AUTHORITY_RECEIPT_MIGRATION/v1"
LEGACY_RECEIPT_SCHEMA = "FRANKENSTEIN2_UNIFIEDDB_FULL_FINGERPRINT_RECEIPT_LEGACY/v1"
CURRENT_RECEIPT_SCHEMA = "FRANKENSTEIN2_UNIFIEDDB_BOUND_FILE_AUTHORITY/v1"
MIGRATION_TABLE = "f2_persistent_agency_authority_migrations"
_CLASSIFICATION = (
    "EXPLICIT_VERSIONED_COMPATIBILITY_MIGRATION_NOT_WORLD_EFFECT_OR_COMPLETION_AUTHORITY"
)
_MAX_ID_LEN = 512


class AuthorityMigrationError(PersistentAgencyError):
    """Fail-closed WP206 authority-receipt migration error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise AuthorityMigrationError(f"{name} must be a string")
    if not value or value != value.strip():
        raise AuthorityMigrationError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise AuthorityMigrationError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise AuthorityMigrationError(f"{name} contains control characters")
    return value


def _sha256_hex(name: str, value: Any) -> str:
    value = _identifier(name, value)
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise AuthorityMigrationError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise AuthorityMigrationError("evidence_refs must be an iterable of strings")
    refs = tuple(_identifier("evidence_ref", value) for value in values)
    if not refs:
        raise AuthorityMigrationError("evidence_refs must be non-empty")
    if len(set(refs)) != len(refs):
        raise AuthorityMigrationError("evidence_refs contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _same_real_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
        os.path.realpath(right)
    )


@dataclass(frozen=True, slots=True)
class AuthorityReceiptMigrationReceipt:
    schema: str
    migration_id: str
    checkpoint_id: str
    checkpoint_sha256: str
    from_schema: str
    from_receipt_sha256: str
    to_schema: str
    to_receipt_sha256: str
    canonical_db_path: str
    db_device: int
    db_inode: int
    evidence_refs: tuple[str, ...]
    classification: str = _CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != MIGRATION_SCHEMA:
            raise AuthorityMigrationError("MIGRATION_SCHEMA_MISMATCH")
        _identifier("migration_id", self.migration_id)
        _identifier("checkpoint_id", self.checkpoint_id)
        _sha256_hex("checkpoint_sha256", self.checkpoint_sha256)
        if self.from_schema != LEGACY_RECEIPT_SCHEMA:
            raise AuthorityMigrationError("LEGACY_RECEIPT_SCHEMA_MISMATCH")
        _sha256_hex("from_receipt_sha256", self.from_receipt_sha256)
        if self.to_schema != CURRENT_RECEIPT_SCHEMA:
            raise AuthorityMigrationError("CURRENT_RECEIPT_SCHEMA_MISMATCH")
        _sha256_hex("to_receipt_sha256", self.to_receipt_sha256)
        _identifier("canonical_db_path", self.canonical_db_path)
        if type(self.db_device) is not int or self.db_device < 0:
            raise AuthorityMigrationError("db_device must be a non-negative integer")
        if type(self.db_inode) is not int or self.db_inode < 0:
            raise AuthorityMigrationError("db_inode must be a non-negative integer")
        object.__setattr__(self, "evidence_refs", _refs(self.evidence_refs))
        if self.classification != _CLASSIFICATION:
            raise AuthorityMigrationError("MIGRATION_CLASSIFICATION_MISMATCH")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "migration_id": self.migration_id,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "from_schema": self.from_schema,
            "from_receipt_sha256": self.from_receipt_sha256,
            "to_schema": self.to_schema,
            "to_receipt_sha256": self.to_receipt_sha256,
            "canonical_db_path": self.canonical_db_path,
            "db_device": self.db_device,
            "db_inode": self.db_inode,
            "evidence_refs": list(self.evidence_refs),
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256(self.as_dict())

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AuthorityReceiptMigrationReceipt":
        if not isinstance(raw, dict):
            raise AuthorityMigrationError("migration receipt must be a JSON object")
        expected = {
            "schema",
            "migration_id",
            "checkpoint_id",
            "checkpoint_sha256",
            "from_schema",
            "from_receipt_sha256",
            "to_schema",
            "to_receipt_sha256",
            "canonical_db_path",
            "db_device",
            "db_inode",
            "evidence_refs",
            "classification",
        }
        if set(raw) != expected:
            raise AuthorityMigrationError("migration receipt field mismatch")
        return cls(
            schema=raw["schema"],
            migration_id=raw["migration_id"],
            checkpoint_id=raw["checkpoint_id"],
            checkpoint_sha256=raw["checkpoint_sha256"],
            from_schema=raw["from_schema"],
            from_receipt_sha256=raw["from_receipt_sha256"],
            to_schema=raw["to_schema"],
            to_receipt_sha256=raw["to_receipt_sha256"],
            canonical_db_path=raw["canonical_db_path"],
            db_device=raw["db_device"],
            db_inode=raw["db_inode"],
            evidence_refs=tuple(raw["evidence_refs"]),
            classification=raw["classification"],
        )


def _ensure_migration_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE}(
            migration_id TEXT PRIMARY KEY,
            checkpoint_id TEXT NOT NULL UNIQUE,
            receipt_sha256 TEXT NOT NULL,
            receipt_json TEXT NOT NULL,
            from_schema TEXT NOT NULL,
            from_receipt_sha256 TEXT NOT NULL,
            to_schema TEXT NOT NULL,
            to_receipt_sha256 TEXT NOT NULL,
            checkpoint_sha256 TEXT NOT NULL,
            FOREIGN KEY(checkpoint_id) REFERENCES {CHECKPOINT_TABLE}(checkpoint_id)
        )"""
    )


def _decode_and_verify_checkpoint(raw_json: str, expected_sha256: str) -> None:
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise AuthorityMigrationError("CORRUPT_CHECKPOINT_JSON") from exc
    if _sha256(raw) != expected_sha256:
        raise AuthorityMigrationError("CHECKPOINT_DIGEST_MISMATCH")
    checkpoint = PersistentAgencyCheckpoint.from_dict(raw)
    if checkpoint.sha256() != expected_sha256:
        raise AuthorityMigrationError("CHECKPOINT_TYPED_REPLAY_DIGEST_MISMATCH")


def migrate_legacy_authority_receipt(
    store: CanonicalPersistentAgencyStore,
    *,
    migration_id: str,
    checkpoint_id: str,
    expected_checkpoint_sha256: str,
    expected_legacy_receipt_sha256: str,
    evidence_refs: Iterable[str],
) -> AuthorityReceiptMigrationReceipt:
    """CAS-migrate one explicitly proven legacy G1 authority receipt.

    ``expected_legacy_receipt_sha256`` must come from an external admitted migration or
    recovery record.  Reading the current row and feeding its value back is not proof and
    is intentionally not performed here.
    """
    if not isinstance(store, CanonicalPersistentAgencyStore):
        raise AuthorityMigrationError("CANONICAL_PERSISTENT_AGENCY_STORE_REQUIRED")
    migration_id = _identifier("migration_id", migration_id)
    checkpoint_id = _identifier("checkpoint_id", checkpoint_id)
    expected_checkpoint_sha256 = _sha256_hex(
        "expected_checkpoint_sha256", expected_checkpoint_sha256
    )
    expected_legacy_receipt_sha256 = _sha256_hex(
        "expected_legacy_receipt_sha256", expected_legacy_receipt_sha256
    )
    evidence_refs = _refs(evidence_refs)
    if expected_legacy_receipt_sha256 == store.authority_receipt_sha256:
        raise AuthorityMigrationError("LEGACY_RECEIPT_ALREADY_CURRENT_SEMANTICS")

    store._assert_current_file_identity()
    connection = store.connection
    if connection.in_transaction:
        raise AuthorityMigrationError("CALLER_TRANSACTION_ALREADY_OPEN")

    try:
        connection.execute("BEGIN IMMEDIATE")
        _ensure_migration_table(connection)

        existing_row = connection.execute(
            f"""SELECT receipt_sha256, receipt_json
                FROM {MIGRATION_TABLE} WHERE checkpoint_id=?""",
            (checkpoint_id,),
        ).fetchone()
        if existing_row is not None:
            try:
                existing_raw = json.loads(existing_row[1])
            except json.JSONDecodeError as exc:
                raise AuthorityMigrationError("CORRUPT_MIGRATION_RECEIPT_JSON") from exc
            existing = AuthorityReceiptMigrationReceipt.from_dict(existing_raw)
            if existing.sha256() != existing_row[0]:
                raise AuthorityMigrationError("MIGRATION_RECEIPT_DIGEST_MISMATCH")
            if existing.migration_id != migration_id:
                raise AuthorityMigrationError("CHECKPOINT_ALREADY_MIGRATED_BY_OTHER_ID")
            if (
                existing.checkpoint_sha256 != expected_checkpoint_sha256
                or existing.from_receipt_sha256 != expected_legacy_receipt_sha256
                or existing.evidence_refs != evidence_refs
            ):
                raise AuthorityMigrationError("MIGRATION_REPLAY_ARGUMENT_MISMATCH")
            replayed = store.load_checkpoint(checkpoint_id)
            if replayed.sha256() != expected_checkpoint_sha256:
                raise AuthorityMigrationError("MIGRATED_CHECKPOINT_REPLAY_DIGEST_MISMATCH")
            connection.commit()
            return existing

        row = connection.execute(
            f"""SELECT checkpoint_sha256, checkpoint_json, canonical_db_path,
                       db_device, db_inode, unifieddb_authority_receipt_sha256
                FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
            (checkpoint_id,),
        ).fetchone()
        if row is None:
            raise AuthorityMigrationError("CHECKPOINT_NOT_FOUND")
        (
            stored_checkpoint_sha256,
            raw_json,
            stored_path,
            stored_device,
            stored_inode,
            stored_authority_receipt_sha256,
        ) = row

        if stored_checkpoint_sha256 != expected_checkpoint_sha256:
            raise AuthorityMigrationError("EXPECTED_CHECKPOINT_DIGEST_MISMATCH")
        if not _same_real_path(stored_path, store.canonical_db_path):
            raise AuthorityMigrationError("CHECKPOINT_DB_PATH_AUTHORITY_MISMATCH")
        if (stored_device, stored_inode) != (store.db_device, store.db_inode):
            raise AuthorityMigrationError("CHECKPOINT_DB_FILE_IDENTITY_DRIFT")
        if stored_authority_receipt_sha256 != expected_legacy_receipt_sha256:
            raise AuthorityMigrationError("EXPECTED_LEGACY_RECEIPT_MISMATCH")

        _decode_and_verify_checkpoint(raw_json, expected_checkpoint_sha256)

        receipt = AuthorityReceiptMigrationReceipt(
            schema=MIGRATION_SCHEMA,
            migration_id=migration_id,
            checkpoint_id=checkpoint_id,
            checkpoint_sha256=expected_checkpoint_sha256,
            from_schema=LEGACY_RECEIPT_SCHEMA,
            from_receipt_sha256=expected_legacy_receipt_sha256,
            to_schema=CURRENT_RECEIPT_SCHEMA,
            to_receipt_sha256=store.authority_receipt_sha256,
            canonical_db_path=store.canonical_db_path,
            db_device=store.db_device,
            db_inode=store.db_inode,
            evidence_refs=evidence_refs,
        )

        cursor = connection.execute(
            f"""UPDATE {CHECKPOINT_TABLE}
                SET unifieddb_authority_receipt_sha256=?
                WHERE checkpoint_id=?
                  AND checkpoint_sha256=?
                  AND canonical_db_path=?
                  AND db_device=?
                  AND db_inode=?
                  AND unifieddb_authority_receipt_sha256=?""",
            (
                receipt.to_receipt_sha256,
                checkpoint_id,
                expected_checkpoint_sha256,
                stored_path,
                stored_device,
                stored_inode,
                expected_legacy_receipt_sha256,
            ),
        )
        if cursor.rowcount != 1:
            raise AuthorityMigrationError("MIGRATION_COMPARE_AND_SWAP_FAILED")

        replayed = store.load_checkpoint(checkpoint_id)
        if replayed.sha256() != expected_checkpoint_sha256:
            raise AuthorityMigrationError("MIGRATED_CHECKPOINT_REPLAY_DIGEST_MISMATCH")

        connection.execute(
            f"""INSERT INTO {MIGRATION_TABLE}(
                    migration_id, checkpoint_id, receipt_sha256, receipt_json,
                    from_schema, from_receipt_sha256, to_schema,
                    to_receipt_sha256, checkpoint_sha256
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                receipt.migration_id,
                receipt.checkpoint_id,
                receipt.sha256(),
                receipt.canonical_json(),
                receipt.from_schema,
                receipt.from_receipt_sha256,
                receipt.to_schema,
                receipt.to_receipt_sha256,
                receipt.checkpoint_sha256,
            ),
        )
        connection.commit()
        return receipt
    except Exception:
        connection.rollback()
        raise


__all__ = [
    "AuthorityMigrationError",
    "AuthorityReceiptMigrationReceipt",
    "CURRENT_RECEIPT_SCHEMA",
    "LEGACY_RECEIPT_SCHEMA",
    "MIGRATION_SCHEMA",
    "MIGRATION_TABLE",
    "migrate_legacy_authority_receipt",
]
