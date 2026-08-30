"""Explicit one-time compatibility migration for F2-WP-206 authority receipts.

The accepted WP206 G1 table already persisted ``unifieddb_authority_receipt_sha256`` but
G1 used the mutable full UnifiedDB fingerprint receipt and did not compare that field on
load. The current reader uses a restart-stable bound-file receipt derived from canonical
path + device + inode and rejects historical G1 rows.

This module closes only that representation transition. It does not weaken the current
reader and it does not auto-discover/auto-bless arbitrary mismatches. A caller must supply
an exact manifest binding every legacy checkpoint id to its already-observed checkpoint
digest and legacy receipt. The migration additionally requires that the manifest covers
*all* currently non-stable rows in the WP206 table. After a successful migration an
append-only migration record makes the operation idempotent but non-healing: later receipt
tamper is rejected rather than rewritten again.

No checkpoint payload bytes, goal/agency state, world facts, scheduler/effect/completion
state, provider/model output or external effects are created or promoted here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from frankenstein2.persistent_agency_kernel import (
    CHECKPOINT_TABLE,
    CanonicalPersistentAgencyStore,
    PersistentAgencyCheckpoint,
    PersistentAgencyError,
)

MIGRATION_SCHEMA = "FRANKENSTEIN2_WP206_AUTHORITY_RECEIPT_MIGRATION/v1"
MIGRATION_TABLE = "f2_persistent_agency_authority_migrations"
MIGRATION_CLASSIFICATION = (
    "EXPLICIT_G1_RECEIPT_COMPATIBILITY_NOT_CHECKPOINT_OR_WORLD_AUTHORITY"
)
RESULT_SCHEMA = "FRANKENSTEIN2_WP206_AUTHORITY_RECEIPT_MIGRATION_RESULT/v1"
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


def _digest(name: str, value: Any) -> str:
    value = _identifier(name, value)
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PersistentAgencyError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _same_real_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
        os.path.realpath(right)
    )


@dataclass(frozen=True, slots=True)
class LegacyAuthorityReceiptBinding:
    checkpoint_id: str
    checkpoint_sha256: str
    legacy_authority_receipt_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "checkpoint_id", _identifier("checkpoint_id", self.checkpoint_id)
        )
        object.__setattr__(
            self,
            "checkpoint_sha256",
            _digest("checkpoint_sha256", self.checkpoint_sha256),
        )
        object.__setattr__(
            self,
            "legacy_authority_receipt_sha256",
            _digest(
                "legacy_authority_receipt_sha256",
                self.legacy_authority_receipt_sha256,
            ),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "legacy_authority_receipt_sha256": self.legacy_authority_receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class LegacyAuthorityMigrationManifest:
    schema: str
    migration_id: str
    bindings: tuple[LegacyAuthorityReceiptBinding, ...]
    provenance_refs: tuple[str, ...]
    classification: str = MIGRATION_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != MIGRATION_SCHEMA:
            raise PersistentAgencyError("WP206 migration manifest schema mismatch")
        object.__setattr__(
            self, "migration_id", _identifier("migration_id", self.migration_id)
        )
        if not isinstance(self.bindings, tuple) or not self.bindings:
            raise PersistentAgencyError("WP206 migration bindings must be a non-empty tuple")
        if any(not isinstance(item, LegacyAuthorityReceiptBinding) for item in self.bindings):
            raise PersistentAgencyError("WP206 migration bindings contain invalid values")
        checkpoint_ids = [item.checkpoint_id for item in self.bindings]
        if len(set(checkpoint_ids)) != len(checkpoint_ids):
            raise PersistentAgencyError("WP206 migration bindings contain duplicate checkpoint ids")
        refs = tuple(_identifier("provenance_ref", item) for item in self.provenance_refs)
        if not refs:
            raise PersistentAgencyError("WP206 migration provenance_refs must be non-empty")
        if len(set(refs)) != len(refs):
            raise PersistentAgencyError("WP206 migration provenance_refs contain duplicates")
        object.__setattr__(self, "provenance_refs", tuple(sorted(refs)))
        object.__setattr__(
            self,
            "bindings",
            tuple(sorted(self.bindings, key=lambda item: item.checkpoint_id)),
        )
        if self.classification != MIGRATION_CLASSIFICATION:
            raise PersistentAgencyError("WP206 migration classification mismatch")

    @classmethod
    def create(
        cls,
        *,
        migration_id: str,
        bindings: Iterable[LegacyAuthorityReceiptBinding],
        provenance_refs: Iterable[str],
    ) -> "LegacyAuthorityMigrationManifest":
        return cls(
            schema=MIGRATION_SCHEMA,
            migration_id=migration_id,
            bindings=tuple(bindings),
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "migration_id": self.migration_id,
            "bindings": [item.as_dict() for item in self.bindings],
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _sha256(self.as_dict())


@dataclass(frozen=True, slots=True)
class LegacyAuthorityMigrationResult:
    schema: str
    migration_id: str
    manifest_sha256: str
    stable_authority_receipt_sha256: str
    migrated_checkpoint_ids: tuple[str, ...]
    status: str
    classification: str = (
        "MIGRATION_RECEIPT_ONLY_NO_RUNTIME_EFFECT_COMPLETION_OR_WORLD_TRUTH_CREDIT"
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "migration_id": self.migration_id,
            "manifest_sha256": self.manifest_sha256,
            "stable_authority_receipt_sha256": self.stable_authority_receipt_sha256,
            "migrated_checkpoint_ids": list(self.migrated_checkpoint_ids),
            "status": self.status,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _sha256(self.as_dict())


def _assert_store_identity(store: CanonicalPersistentAgencyStore) -> None:
    if not isinstance(store, CanonicalPersistentAgencyStore):
        raise PersistentAgencyError("WP206 migration requires CanonicalPersistentAgencyStore")
    if store.connection.in_transaction:
        raise PersistentAgencyError("CALLER_TRANSACTION_ALREADY_OPEN")
    try:
        stat = Path(store.canonical_db_path).stat()
    except OSError as exc:
        raise PersistentAgencyError("UNIFIEDDB_FILE_MISSING_DURING_MIGRATION") from exc
    if (stat.st_dev, stat.st_ino) != (store.db_device, store.db_inode):
        raise PersistentAgencyError("UNIFIEDDB_FILE_IDENTITY_DRIFT")


def _checkpoint_table_columns(store: CanonicalPersistentAgencyStore) -> set[str]:
    rows = store.connection.execute(f"PRAGMA table_info({CHECKPOINT_TABLE})").fetchall()
    if not rows:
        raise PersistentAgencyError("WP206 checkpoint table is not initialized")
    columns = {str(row[1]) for row in rows if len(row) >= 2}
    required = {
        "checkpoint_id",
        "checkpoint_sha256",
        "checkpoint_json",
        "canonical_db_path",
        "db_device",
        "db_inode",
        "unifieddb_authority_receipt_sha256",
    }
    if not required.issubset(columns):
        raise PersistentAgencyError("WP206 checkpoint table schema is incompatible")
    return columns


def _validate_checkpoint_row(
    store: CanonicalPersistentAgencyStore,
    binding: LegacyAuthorityReceiptBinding,
    row: tuple[Any, ...],
    *,
    require_legacy_receipt: bool,
) -> None:
    (
        checkpoint_sha256,
        checkpoint_json,
        stored_path,
        stored_device,
        stored_inode,
        stored_receipt,
    ) = row
    if checkpoint_sha256 != binding.checkpoint_sha256:
        raise PersistentAgencyError("LEGACY_CHECKPOINT_DIGEST_MANIFEST_MISMATCH")
    if require_legacy_receipt and stored_receipt != binding.legacy_authority_receipt_sha256:
        raise PersistentAgencyError("LEGACY_AUTHORITY_RECEIPT_MANIFEST_MISMATCH")
    if not _same_real_path(stored_path, store.canonical_db_path):
        raise PersistentAgencyError("LEGACY_CHECKPOINT_DB_PATH_AUTHORITY_MISMATCH")
    if (stored_device, stored_inode) != (store.db_device, store.db_inode):
        raise PersistentAgencyError("LEGACY_CHECKPOINT_DB_FILE_IDENTITY_DRIFT")
    try:
        raw = json.loads(checkpoint_json)
    except json.JSONDecodeError as exc:
        raise PersistentAgencyError("CORRUPT_CHECKPOINT_JSON") from exc
    if _sha256(raw) != checkpoint_sha256:
        raise PersistentAgencyError("CHECKPOINT_DIGEST_MISMATCH")
    checkpoint = PersistentAgencyCheckpoint.from_dict(raw)
    if checkpoint.sha256() != checkpoint_sha256:
        raise PersistentAgencyError("CHECKPOINT_TYPED_REPLAY_DIGEST_MISMATCH")


def migrate_g1_authority_receipts(
    store: CanonicalPersistentAgencyStore,
    manifest: LegacyAuthorityMigrationManifest,
) -> LegacyAuthorityMigrationResult:
    """Migrate exactly manifested G1-style receipt rows to the current stable receipt.

    This is deliberately explicit and one-time. It cannot be used as a generic repair
    function after migration because a recorded migration requires every bound row to remain
    on the stable receipt; later mismatches raise ``MIGRATED_ROW_AUTHORITY_RECEIPT_TAMPER``.
    """
    _assert_store_identity(store)
    if not isinstance(manifest, LegacyAuthorityMigrationManifest):
        raise PersistentAgencyError("WP206 migration manifest required")
    _checkpoint_table_columns(store)

    stable_receipt = _digest(
        "stable_authority_receipt_sha256", store.authority_receipt_sha256
    )
    manifest_sha = manifest.sha256()
    target_ids = tuple(item.checkpoint_id for item in manifest.bindings)
    binding_by_id = {item.checkpoint_id: item for item in manifest.bindings}

    try:
        store.connection.execute("BEGIN IMMEDIATE")
        store.connection.execute(
            f"""CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE}(
                migration_id TEXT PRIMARY KEY,
                migration_schema TEXT NOT NULL,
                manifest_sha256 TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                stable_authority_receipt_sha256 TEXT NOT NULL,
                item_count INTEGER NOT NULL CHECK(item_count > 0),
                classification TEXT NOT NULL
            )"""
        )

        prior = store.connection.execute(
            f"""SELECT migration_schema, manifest_sha256, manifest_json,
                       stable_authority_receipt_sha256, item_count, classification
                FROM {MIGRATION_TABLE} WHERE migration_id=?""",
            (manifest.migration_id,),
        ).fetchone()

        if prior is not None:
            expected_prior = (
                MIGRATION_SCHEMA,
                manifest_sha,
                _canonical_json(manifest.as_dict()),
                stable_receipt,
                len(target_ids),
                MIGRATION_CLASSIFICATION,
            )
            if tuple(prior) != expected_prior:
                raise PersistentAgencyError("MIGRATION_ID_ALREADY_BOUND_TO_DIFFERENT_MANIFEST")
            for checkpoint_id in target_ids:
                row = store.connection.execute(
                    f"""SELECT checkpoint_sha256, checkpoint_json, canonical_db_path,
                               db_device, db_inode, unifieddb_authority_receipt_sha256
                        FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
                    (checkpoint_id,),
                ).fetchone()
                if row is None:
                    raise PersistentAgencyError("MIGRATED_CHECKPOINT_NOT_FOUND")
                _validate_checkpoint_row(
                    store,
                    binding_by_id[checkpoint_id],
                    row,
                    require_legacy_receipt=False,
                )
                if row[5] != stable_receipt:
                    raise PersistentAgencyError("MIGRATED_ROW_AUTHORITY_RECEIPT_TAMPER")
            store.connection.commit()
            return LegacyAuthorityMigrationResult(
                schema=RESULT_SCHEMA,
                migration_id=manifest.migration_id,
                manifest_sha256=manifest_sha,
                stable_authority_receipt_sha256=stable_receipt,
                migrated_checkpoint_ids=target_ids,
                status="ALREADY_MIGRATED_VERIFIED",
            )

        mismatched_rows = store.connection.execute(
            f"""SELECT checkpoint_id
                FROM {CHECKPOINT_TABLE}
                WHERE unifieddb_authority_receipt_sha256<>?
                ORDER BY checkpoint_id""",
            (stable_receipt,),
        ).fetchall()
        mismatched_ids = tuple(str(row[0]) for row in mismatched_rows)
        if mismatched_ids != tuple(sorted(target_ids)):
            raise PersistentAgencyError("LEGACY_MANIFEST_DOES_NOT_COVER_ALL_NONSTABLE_ROWS")

        for binding in manifest.bindings:
            if binding.legacy_authority_receipt_sha256 == stable_receipt:
                raise PersistentAgencyError("LEGACY_MANIFEST_CONTAINS_ALREADY_STABLE_RECEIPT")
            row = store.connection.execute(
                f"""SELECT checkpoint_sha256, checkpoint_json, canonical_db_path,
                           db_device, db_inode, unifieddb_authority_receipt_sha256
                    FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
                (binding.checkpoint_id,),
            ).fetchone()
            if row is None:
                raise PersistentAgencyError("LEGACY_CHECKPOINT_NOT_FOUND")
            _validate_checkpoint_row(
                store,
                binding,
                row,
                require_legacy_receipt=True,
            )

        for binding in manifest.bindings:
            cursor = store.connection.execute(
                f"""UPDATE {CHECKPOINT_TABLE}
                    SET unifieddb_authority_receipt_sha256=?
                    WHERE checkpoint_id=?
                      AND checkpoint_sha256=?
                      AND unifieddb_authority_receipt_sha256=?""",
                (
                    stable_receipt,
                    binding.checkpoint_id,
                    binding.checkpoint_sha256,
                    binding.legacy_authority_receipt_sha256,
                ),
            )
            if cursor.rowcount != 1:
                raise PersistentAgencyError("LEGACY_CHECKPOINT_CHANGED_DURING_MIGRATION")

        store.connection.execute(
            f"""INSERT INTO {MIGRATION_TABLE}(
                migration_id, migration_schema, manifest_sha256, manifest_json,
                stable_authority_receipt_sha256, item_count, classification
            ) VALUES(?,?,?,?,?,?,?)""",
            (
                manifest.migration_id,
                MIGRATION_SCHEMA,
                manifest_sha,
                _canonical_json(manifest.as_dict()),
                stable_receipt,
                len(target_ids),
                MIGRATION_CLASSIFICATION,
            ),
        )
        store.connection.commit()
    except Exception:
        store.connection.rollback()
        raise

    # Post-commit typed readback uses the current canonical reader. Failure here is a hard
    # implementation defect, not permission to silently weaken the reader.
    for checkpoint_id in target_ids:
        store.load_checkpoint(checkpoint_id)

    return LegacyAuthorityMigrationResult(
        schema=RESULT_SCHEMA,
        migration_id=manifest.migration_id,
        manifest_sha256=manifest_sha,
        stable_authority_receipt_sha256=stable_receipt,
        migrated_checkpoint_ids=target_ids,
        status="MIGRATED",
    )


__all__ = [
    "LegacyAuthorityMigrationManifest",
    "LegacyAuthorityMigrationResult",
    "LegacyAuthorityReceiptBinding",
    "MIGRATION_CLASSIFICATION",
    "MIGRATION_SCHEMA",
    "MIGRATION_TABLE",
    "RESULT_SCHEMA",
    "migrate_g1_authority_receipts",
]
