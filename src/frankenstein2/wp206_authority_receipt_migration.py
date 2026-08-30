"""Explicit compatibility migration for historical F2-WP-206 authority receipts.

REVIEW_ONLY donor for Triggerword-4 WP206 migration re-entry.

Accepted WP206 generation-1 checkpoints stored the mutable full
``UnifiedDBFingerprint.receipt_sha256()`` in
``unifieddb_authority_receipt_sha256``. Current source instead stores a stable
bound-file authority receipt over canonical path + device + inode. The current
reader must not silently reinterpret an arbitrary mismatching 64-hex value as a
legitimate legacy receipt, because doing so would turn receipt tampering into a
migration path.

This module therefore provides a deliberate, permit-bound migration. The permit
must carry the exact legacy receipt and checkpoint digest from evidence outside
of the row being migrated. Migration verifies checkpoint bytes and file identity,
then atomically rewrites only the authority receipt and appends a migration audit
record. Ordinary checkpoint reads remain fail-closed before migration and after
post-migration tampering.

No provider/model/tool/effect/completion authority exists here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from frankenstein2.persistent_agency_kernel import (
    CHECKPOINT_TABLE,
    CanonicalPersistentAgencyStore,
    PersistentAgencyError,
)

MIGRATION_SCHEMA = "FRANKENSTEIN2_WP206_AUTHORITY_RECEIPT_MIGRATION/v1"
MIGRATION_RECEIPT_SCHEMA = (
    "FRANKENSTEIN2_WP206_AUTHORITY_RECEIPT_MIGRATION_RECEIPT/v1"
)
MIGRATION_AUDIT_TABLE = "f2_wp206_authority_receipt_migrations"
_MAX_ID_LEN = 512


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


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise PersistentAgencyError(f"{name} must be a string")
    if not value or value != value.strip():
        raise PersistentAgencyError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise PersistentAgencyError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PersistentAgencyError(f"{name} contains control characters")
    return value


def _sha256_hex(name: str, value: Any) -> str:
    value = _identifier(name, value)
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PersistentAgencyError(f"{name} must be lowercase sha256 hex")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise PersistentAgencyError("provenance_refs must be an iterable of strings")
    refs = tuple(_identifier("provenance_ref", value) for value in values)
    if not refs:
        raise PersistentAgencyError("provenance_refs must be non-empty")
    if len(set(refs)) != len(refs):
        raise PersistentAgencyError("provenance_refs contain duplicates")
    return tuple(sorted(refs))


def _same_real_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
        os.path.realpath(right)
    )


@dataclass(frozen=True)
class LegacyAuthorityReceiptMigrationPermit:
    """External evidence needed to migrate one accepted legacy checkpoint row."""

    schema: str
    migration_id: str
    checkpoint_id: str
    checkpoint_sha256: str
    legacy_authority_receipt_sha256: str
    canonical_db_path: str
    db_device: int
    db_inode: int
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != MIGRATION_SCHEMA:
            raise PersistentAgencyError("WP206_MIGRATION_SCHEMA_MISMATCH")
        _identifier("migration_id", self.migration_id)
        _identifier("checkpoint_id", self.checkpoint_id)
        _sha256_hex("checkpoint_sha256", self.checkpoint_sha256)
        _sha256_hex(
            "legacy_authority_receipt_sha256",
            self.legacy_authority_receipt_sha256,
        )
        _identifier("canonical_db_path", self.canonical_db_path)
        if type(self.db_device) is not int or self.db_device < 0:
            raise PersistentAgencyError("db_device must be a non-negative integer")
        if type(self.db_inode) is not int or self.db_inode < 0:
            raise PersistentAgencyError("db_inode must be a non-negative integer")
        _refs(self.provenance_refs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "migration_id": self.migration_id,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "legacy_authority_receipt_sha256": self.legacy_authority_receipt_sha256,
            "canonical_db_path": os.path.realpath(self.canonical_db_path),
            "db_device": self.db_device,
            "db_inode": self.db_inode,
            "provenance_refs": list(_refs(self.provenance_refs)),
        }

    def sha256(self) -> str:
        return _sha256(self.as_dict())


@dataclass(frozen=True)
class AuthorityReceiptMigrationReceipt:
    schema: str
    migration_id: str
    checkpoint_id: str
    checkpoint_sha256: str
    old_authority_receipt_sha256: str
    new_authority_receipt_sha256: str
    permit_sha256: str
    canonical_db_path: str
    db_device: int
    db_inode: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "migration_id": self.migration_id,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "old_authority_receipt_sha256": self.old_authority_receipt_sha256,
            "new_authority_receipt_sha256": self.new_authority_receipt_sha256,
            "permit_sha256": self.permit_sha256,
            "canonical_db_path": self.canonical_db_path,
            "db_device": self.db_device,
            "db_inode": self.db_inode,
        }

    def sha256(self) -> str:
        return _sha256(self.as_dict())


def migrate_legacy_checkpoint_authority_receipt(
    store: CanonicalPersistentAgencyStore,
    permit: LegacyAuthorityReceiptMigrationPermit,
) -> AuthorityReceiptMigrationReceipt:
    """Migrate exactly one externally-authorized legacy WP206 checkpoint row.

    The legacy receipt is never inferred from the mutable row itself. A caller must
    provide the exact expected legacy receipt and checkpoint digest in ``permit``.
    """
    if not isinstance(store, CanonicalPersistentAgencyStore):
        raise PersistentAgencyError("CANONICAL_PERSISTENT_AGENCY_STORE_REQUIRED")
    if not isinstance(permit, LegacyAuthorityReceiptMigrationPermit):
        raise PersistentAgencyError("WP206_MIGRATION_PERMIT_REQUIRED")
    if store.connection.in_transaction:
        raise PersistentAgencyError("CALLER_TRANSACTION_ALREADY_OPEN")

    permit_path = os.path.realpath(permit.canonical_db_path)
    if not _same_real_path(permit_path, store.canonical_db_path):
        raise PersistentAgencyError("WP206_MIGRATION_DB_PATH_MISMATCH")
    if (permit.db_device, permit.db_inode) != (store.db_device, store.db_inode):
        raise PersistentAgencyError("WP206_MIGRATION_DB_FILE_IDENTITY_MISMATCH")

    try:
        st = Path(store.canonical_db_path).stat()
    except OSError as exc:
        raise PersistentAgencyError("UNIFIEDDB_FILE_MISSING_DURING_MIGRATION") from exc
    if (st.st_dev, st.st_ino) != (store.db_device, store.db_inode):
        raise PersistentAgencyError("UNIFIEDDB_FILE_IDENTITY_DRIFT_DURING_MIGRATION")

    if permit.legacy_authority_receipt_sha256 == store.authority_receipt_sha256:
        raise PersistentAgencyError("WP206_LEGACY_RECEIPT_ALREADY_CURRENT")

    try:
        store.connection.execute("BEGIN IMMEDIATE")
        try:
            row = store.connection.execute(
                f"""SELECT checkpoint_sha256, checkpoint_json, canonical_db_path,
                           db_device, db_inode, unifieddb_authority_receipt_sha256
                    FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
                (permit.checkpoint_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise PersistentAgencyError("WP206_CHECKPOINT_TABLE_REQUIRED") from exc
        if row is None:
            raise PersistentAgencyError("CHECKPOINT_NOT_FOUND")

        (
            stored_checkpoint_sha,
            raw_json,
            stored_path,
            stored_device,
            stored_inode,
            stored_authority_receipt,
        ) = row

        if stored_checkpoint_sha != permit.checkpoint_sha256:
            raise PersistentAgencyError("WP206_MIGRATION_CHECKPOINT_DIGEST_MISMATCH")
        if not _same_real_path(stored_path, permit_path):
            raise PersistentAgencyError("WP206_MIGRATION_STORED_DB_PATH_MISMATCH")
        if (stored_device, stored_inode) != (permit.db_device, permit.db_inode):
            raise PersistentAgencyError("WP206_MIGRATION_STORED_FILE_IDENTITY_MISMATCH")
        if stored_authority_receipt != permit.legacy_authority_receipt_sha256:
            raise PersistentAgencyError("WP206_MIGRATION_LEGACY_RECEIPT_MISMATCH")

        try:
            raw = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise PersistentAgencyError("CORRUPT_CHECKPOINT_JSON") from exc
        if _sha256(raw) != permit.checkpoint_sha256:
            raise PersistentAgencyError("WP206_MIGRATION_CHECKPOINT_BYTES_MISMATCH")

        permit_sha = permit.sha256()
        store.connection.execute(
            f"""CREATE TABLE IF NOT EXISTS {MIGRATION_AUDIT_TABLE}(
                migration_id TEXT PRIMARY KEY,
                schema TEXT NOT NULL,
                checkpoint_id TEXT NOT NULL,
                checkpoint_sha256 TEXT NOT NULL,
                old_authority_receipt_sha256 TEXT NOT NULL,
                new_authority_receipt_sha256 TEXT NOT NULL,
                permit_sha256 TEXT NOT NULL,
                canonical_db_path TEXT NOT NULL,
                db_device INTEGER NOT NULL,
                db_inode INTEGER NOT NULL,
                receipt_sha256 TEXT NOT NULL,
                UNIQUE(checkpoint_id, old_authority_receipt_sha256,
                       new_authority_receipt_sha256)
            )"""
        )

        receipt = AuthorityReceiptMigrationReceipt(
            schema=MIGRATION_RECEIPT_SCHEMA,
            migration_id=permit.migration_id,
            checkpoint_id=permit.checkpoint_id,
            checkpoint_sha256=permit.checkpoint_sha256,
            old_authority_receipt_sha256=permit.legacy_authority_receipt_sha256,
            new_authority_receipt_sha256=store.authority_receipt_sha256,
            permit_sha256=permit_sha,
            canonical_db_path=store.canonical_db_path,
            db_device=store.db_device,
            db_inode=store.db_inode,
        )

        cursor = store.connection.execute(
            f"""UPDATE {CHECKPOINT_TABLE}
                SET unifieddb_authority_receipt_sha256=?
                WHERE checkpoint_id=?
                  AND checkpoint_sha256=?
                  AND unifieddb_authority_receipt_sha256=?""",
            (
                store.authority_receipt_sha256,
                permit.checkpoint_id,
                permit.checkpoint_sha256,
                permit.legacy_authority_receipt_sha256,
            ),
        )
        if cursor.rowcount != 1:
            raise PersistentAgencyError("WP206_MIGRATION_COMPARE_AND_SWAP_FAILED")

        store.connection.execute(
            f"""INSERT INTO {MIGRATION_AUDIT_TABLE}(
                migration_id, schema, checkpoint_id, checkpoint_sha256,
                old_authority_receipt_sha256, new_authority_receipt_sha256,
                permit_sha256, canonical_db_path, db_device, db_inode,
                receipt_sha256
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                receipt.migration_id,
                receipt.schema,
                receipt.checkpoint_id,
                receipt.checkpoint_sha256,
                receipt.old_authority_receipt_sha256,
                receipt.new_authority_receipt_sha256,
                receipt.permit_sha256,
                receipt.canonical_db_path,
                receipt.db_device,
                receipt.db_inode,
                receipt.sha256(),
            ),
        )
        store.connection.commit()
        return receipt
    except Exception:
        store.connection.rollback()
        raise


__all__ = [
    "MIGRATION_AUDIT_TABLE",
    "MIGRATION_RECEIPT_SCHEMA",
    "MIGRATION_SCHEMA",
    "AuthorityReceiptMigrationReceipt",
    "LegacyAuthorityReceiptMigrationPermit",
    "migrate_legacy_checkpoint_authority_receipt",
]
