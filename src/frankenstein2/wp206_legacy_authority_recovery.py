"""Explicit one-time legacy authority recovery for F2-WP-206.

This module closes only the persisted-representation compatibility gap between accepted
WP206 generation-1 rows, which stored a mutable full UnifiedDB fingerprint receipt, and
the current restart-stable bound-file authority receipt used by CanonicalPersistentAgencyStore.

Recovery is deliberately NOT part of normal checkpoint loading.  A caller must supply the
historical receipt expected from external evidence plus a provenance reference.  Before a
row is rebound, the adapter verifies the exact canonical DB file identity, stored checkpoint
digest and typed checkpoint replay.  A one-per-checkpoint recovery record is persisted in
the same canonical UnifiedDB so a later receipt drift cannot be silently "recovered" again.

This is migration/recovery authority only.  It does not infer truth, schedule work, execute
effects, mint completion, or create a second state database.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from frankenstein2.persistent_agency_kernel import (
    CHECKPOINT_TABLE,
    CanonicalPersistentAgencyStore,
    PersistentAgencyCheckpoint,
    PersistentAgencyError,
)

RECOVERY_SCHEMA = "FRANKENSTEIN2_WP206_LEGACY_AUTHORITY_RECOVERY/v1"
RECOVERY_TABLE = "f2_wp206_legacy_authority_recoveries"
RECOVERED = "RECOVERED"
ALREADY_RECOVERED = "ALREADY_RECOVERED"
_MAX_ID_LEN = 512


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


def _receipt(name: str, value: Any) -> str:
    value = _identifier(name, value)
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PersistentAgencyError(f"{name} must be lowercase 64-hex SHA-256")
    return value


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
class LegacyAuthorityRecoveryReceipt:
    schema: str
    recovery_id: str
    checkpoint_id: str
    checkpoint_sha256: str
    legacy_authority_receipt_sha256: str
    rebound_authority_receipt_sha256: str
    recovery_provenance_ref: str
    status: str
    classification: str = (
        "EXPLICIT_ONE_TIME_PERSISTENCE_MIGRATION_NOT_WORLD_TRUTH_OR_RUNTIME_ACCEPTANCE"
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "recovery_id": self.recovery_id,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "legacy_authority_receipt_sha256": self.legacy_authority_receipt_sha256,
            "rebound_authority_receipt_sha256": self.rebound_authority_receipt_sha256,
            "recovery_provenance_ref": self.recovery_provenance_ref,
            "status": self.status,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _sha256(self.as_dict())


def _validate_checkpoint_bytes(expected_sha: str, raw_json: str) -> None:
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise PersistentAgencyError("CORRUPT_CHECKPOINT_JSON") from exc
    actual_sha = _sha256(raw)
    if actual_sha != expected_sha:
        raise PersistentAgencyError("CHECKPOINT_DIGEST_MISMATCH")
    checkpoint = PersistentAgencyCheckpoint.from_dict(raw)
    if checkpoint.sha256() != expected_sha:
        raise PersistentAgencyError("CHECKPOINT_TYPED_REPLAY_DIGEST_MISMATCH")


def recover_legacy_g1_checkpoint_authority(
    *,
    store: CanonicalPersistentAgencyStore,
    checkpoint_id: str,
    expected_legacy_authority_receipt_sha256: str,
    recovery_provenance_ref: str,
) -> LegacyAuthorityRecoveryReceipt:
    """Explicitly rebind one externally witnessed legacy G1 row to current file authority.

    The caller-supplied legacy receipt is an external recovery input, not a value learned
    from the row during recovery.  A checkpoint can be recovered once.  Exact repeat calls
    are idempotent only while the row still carries the recorded rebound receipt; any later
    receipt drift fails closed and cannot be laundered through another recovery call.
    """
    if not isinstance(store, CanonicalPersistentAgencyStore):
        raise PersistentAgencyError("CANONICAL_PERSISTENT_AGENCY_STORE_REQUIRED")
    checkpoint_id = _identifier("checkpoint_id", checkpoint_id)
    expected_legacy = _receipt(
        "expected_legacy_authority_receipt_sha256",
        expected_legacy_authority_receipt_sha256,
    )
    provenance_ref = _identifier("recovery_provenance_ref", recovery_provenance_ref)
    current_receipt = _receipt(
        "current_authority_receipt_sha256", store.authority_receipt_sha256
    )
    if expected_legacy == current_receipt:
        raise PersistentAgencyError("LEGACY_RECOVERY_NOT_REQUIRED_FOR_CURRENT_RECEIPT")
    if store.connection.in_transaction:
        raise PersistentAgencyError("CALLER_TRANSACTION_ALREADY_OPEN")

    try:
        st = Path(store.canonical_db_path).stat()
    except OSError as exc:
        raise PersistentAgencyError("UNIFIEDDB_FILE_MISSING_DURING_LEGACY_RECOVERY") from exc
    if (st.st_dev, st.st_ino) != (store.db_device, store.db_inode):
        raise PersistentAgencyError("UNIFIEDDB_FILE_IDENTITY_DRIFT")

    connection = store.connection
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            f"""CREATE TABLE IF NOT EXISTS {RECOVERY_TABLE}(
                recovery_id TEXT PRIMARY KEY,
                checkpoint_id TEXT NOT NULL UNIQUE,
                checkpoint_sha256 TEXT NOT NULL,
                canonical_db_path TEXT NOT NULL,
                db_device INTEGER NOT NULL,
                db_inode INTEGER NOT NULL,
                legacy_authority_receipt_sha256 TEXT NOT NULL,
                rebound_authority_receipt_sha256 TEXT NOT NULL,
                recovery_provenance_ref TEXT NOT NULL,
                classification TEXT NOT NULL,
                FOREIGN KEY(checkpoint_id) REFERENCES {CHECKPOINT_TABLE}(checkpoint_id)
            )"""
        )

        row = connection.execute(
            f"""SELECT checkpoint_sha256, checkpoint_json, canonical_db_path,
                       db_device, db_inode, unifieddb_authority_receipt_sha256
                FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
            (checkpoint_id,),
        ).fetchone()
        if row is None:
            raise PersistentAgencyError("CHECKPOINT_NOT_FOUND")
        (
            checkpoint_sha,
            raw_json,
            stored_path,
            stored_device,
            stored_inode,
            stored_receipt,
        ) = row
        checkpoint_sha = _receipt("checkpoint_sha256", checkpoint_sha)
        stored_receipt = _receipt(
            "stored_authority_receipt_sha256", stored_receipt
        )
        if not _same_real_path(stored_path, store.canonical_db_path):
            raise PersistentAgencyError("CHECKPOINT_DB_PATH_AUTHORITY_MISMATCH")
        if (stored_device, stored_inode) != (store.db_device, store.db_inode):
            raise PersistentAgencyError("CHECKPOINT_DB_FILE_IDENTITY_DRIFT")
        _validate_checkpoint_bytes(checkpoint_sha, raw_json)

        existing = connection.execute(
            f"""SELECT recovery_id, checkpoint_sha256,
                       legacy_authority_receipt_sha256,
                       rebound_authority_receipt_sha256,
                       recovery_provenance_ref, classification
                FROM {RECOVERY_TABLE} WHERE checkpoint_id=?""",
            (checkpoint_id,),
        ).fetchone()
        if existing is not None:
            (
                recovery_id,
                recorded_checkpoint_sha,
                recorded_legacy,
                recorded_rebound,
                recorded_provenance,
                classification,
            ) = existing
            if recorded_checkpoint_sha != checkpoint_sha:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_CHECKPOINT_DIGEST_DRIFT"
                )
            if recorded_legacy != expected_legacy:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_EXTERNAL_RECEIPT_CONFLICT"
                )
            if recorded_rebound != current_receipt:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_CURRENT_AUTHORITY_CHANGED"
                )
            if stored_receipt != recorded_rebound:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_POST_MIGRATION_AUTHORITY_DRIFT"
                )
            connection.commit()
            return LegacyAuthorityRecoveryReceipt(
                schema=RECOVERY_SCHEMA,
                recovery_id=recovery_id,
                checkpoint_id=checkpoint_id,
                checkpoint_sha256=checkpoint_sha,
                legacy_authority_receipt_sha256=recorded_legacy,
                rebound_authority_receipt_sha256=recorded_rebound,
                recovery_provenance_ref=recorded_provenance,
                status=ALREADY_RECOVERED,
                classification=classification,
            )

        if stored_receipt != expected_legacy:
            raise PersistentAgencyError("LEGACY_RECOVERY_EXPECTED_RECEIPT_MISMATCH")

        classification = (
            "EXPLICIT_ONE_TIME_PERSISTENCE_MIGRATION_NOT_WORLD_TRUTH_OR_RUNTIME_ACCEPTANCE"
        )
        recovery_id = _sha256(
            {
                "schema": RECOVERY_SCHEMA,
                "checkpoint_id": checkpoint_id,
                "checkpoint_sha256": checkpoint_sha,
                "canonical_db_path": store.canonical_db_path,
                "db_device": store.db_device,
                "db_inode": store.db_inode,
                "legacy_authority_receipt_sha256": expected_legacy,
                "rebound_authority_receipt_sha256": current_receipt,
                "recovery_provenance_ref": provenance_ref,
            }
        )
        connection.execute(
            f"""INSERT INTO {RECOVERY_TABLE}(
                recovery_id, checkpoint_id, checkpoint_sha256,
                canonical_db_path, db_device, db_inode,
                legacy_authority_receipt_sha256,
                rebound_authority_receipt_sha256,
                recovery_provenance_ref, classification
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                recovery_id,
                checkpoint_id,
                checkpoint_sha,
                store.canonical_db_path,
                store.db_device,
                store.db_inode,
                expected_legacy,
                current_receipt,
                provenance_ref,
                classification,
            ),
        )
        updated = connection.execute(
            f"""UPDATE {CHECKPOINT_TABLE}
                SET unifieddb_authority_receipt_sha256=?
                WHERE checkpoint_id=?
                  AND checkpoint_sha256=?
                  AND canonical_db_path=?
                  AND db_device=?
                  AND db_inode=?
                  AND unifieddb_authority_receipt_sha256=?""",
            (
                current_receipt,
                checkpoint_id,
                checkpoint_sha,
                stored_path,
                stored_device,
                stored_inode,
                expected_legacy,
            ),
        )
        if updated.rowcount != 1:
            raise PersistentAgencyError("LEGACY_RECOVERY_COMPARE_AND_SWAP_FAILED")
        connection.commit()
        return LegacyAuthorityRecoveryReceipt(
            schema=RECOVERY_SCHEMA,
            recovery_id=recovery_id,
            checkpoint_id=checkpoint_id,
            checkpoint_sha256=checkpoint_sha,
            legacy_authority_receipt_sha256=expected_legacy,
            rebound_authority_receipt_sha256=current_receipt,
            recovery_provenance_ref=provenance_ref,
            status=RECOVERED,
            classification=classification,
        )
    except Exception:
        connection.rollback()
        raise


__all__ = [
    "ALREADY_RECOVERED",
    "RECOVERED",
    "RECOVERY_SCHEMA",
    "RECOVERY_TABLE",
    "LegacyAuthorityRecoveryReceipt",
    "recover_legacy_g1_checkpoint_authority",
]
