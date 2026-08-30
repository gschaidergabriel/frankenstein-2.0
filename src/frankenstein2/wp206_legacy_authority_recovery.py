"""Explicit one-time legacy authority recovery for F2-WP-206.

This module closes only the persisted-representation compatibility gap between accepted
WP206 generation-1 rows, which stored a mutable full UnifiedDB fingerprint receipt, and
the current restart-stable bound-file authority receipt used by CanonicalPersistentAgencyStore.

Recovery is deliberately NOT part of normal checkpoint loading. A caller must supply the
historical receipt plus a concrete typed evidence subject. The adapter derives the evidence
content digest internally, validates it against the checkpoint/recovery inputs, and persists
the binding in the same canonical recovery row. Pre-G5 recovery rows are migrated only at
the schema level and remain explicitly evidence-subject-unbound; caller-supplied bytes are
never retroactively promoted into proof of their historical authorization.

This is migration/recovery authority only. It does not infer truth, schedule work, execute
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

LEGACY_RECOVERY_SCHEMA_V1 = "FRANKENSTEIN2_WP206_LEGACY_AUTHORITY_RECOVERY/v1"
RECOVERY_SCHEMA = "FRANKENSTEIN2_WP206_LEGACY_AUTHORITY_RECOVERY/v2"
EVIDENCE_SUBJECT_SCHEMA = "FRANKENSTEIN2_WP206_LEGACY_RECOVERY_EVIDENCE_SUBJECT/v1"
RECOVERY_TABLE = "f2_wp206_legacy_authority_recoveries"
RECOVERED = "RECOVERED"
ALREADY_RECOVERED = "ALREADY_RECOVERED"
LEGACY_EVIDENCE_SUBJECT_UNBOUND = "LEGACY_EVIDENCE_SUBJECT_UNBOUND"
EVIDENCE_SUBJECT_BOUND_G5 = "EVIDENCE_SUBJECT_BOUND_G5"
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
class LegacyRecoveryEvidenceSubject:
    """Concrete content-bearing evidence supplied to the exceptional recovery ingress."""

    source_ref: str
    checkpoint_id: str
    checkpoint_sha256: str
    legacy_authority_receipt_sha256: str
    evidence: Any
    schema: str = EVIDENCE_SUBJECT_SCHEMA

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_ref": self.source_ref,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "legacy_authority_receipt_sha256": self.legacy_authority_receipt_sha256,
            "evidence": self.evidence,
        }


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
    recovery_evidence_subject_schema: str | None = None
    recovery_evidence_source_ref: str | None = None
    recovery_evidence_sha256: str | None = None
    recovery_evidence_subject_state: str = EVIDENCE_SUBJECT_BOUND_G5
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
            "recovery_evidence_subject_schema": self.recovery_evidence_subject_schema,
            "recovery_evidence_source_ref": self.recovery_evidence_source_ref,
            "recovery_evidence_sha256": self.recovery_evidence_sha256,
            "recovery_evidence_subject_state": self.recovery_evidence_subject_state,
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


def _ensure_g5_recovery_schema(connection: Any) -> None:
    """Create or forward-migrate only the canonical recovery table.

    New columns are intentionally nullable so a pre-G5 row can remain historically honest:
    schema migration is permitted, synthetic retroactive evidence binding is not.
    """
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
            recovery_evidence_subject_schema TEXT,
            recovery_evidence_source_ref TEXT,
            recovery_evidence_sha256 TEXT,
            recovery_evidence_subject_state TEXT,
            FOREIGN KEY(checkpoint_id) REFERENCES {CHECKPOINT_TABLE}(checkpoint_id)
        )"""
    )
    columns = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({RECOVERY_TABLE})").fetchall()
    }
    required = (
        ("recovery_evidence_subject_schema", "TEXT"),
        ("recovery_evidence_source_ref", "TEXT"),
        ("recovery_evidence_sha256", "TEXT"),
        ("recovery_evidence_subject_state", "TEXT"),
    )
    for name, sql_type in required:
        if name not in columns:
            connection.execute(
                f"ALTER TABLE {RECOVERY_TABLE} ADD COLUMN {name} {sql_type}"
            )


def _bind_evidence_subject(
    *,
    subject: LegacyRecoveryEvidenceSubject | None,
    provenance_ref: str,
    checkpoint_id: str,
    checkpoint_sha256: str,
    expected_legacy: str,
) -> tuple[str, str, str]:
    if not isinstance(subject, LegacyRecoveryEvidenceSubject):
        raise PersistentAgencyError("RECOVERY_EVIDENCE_SUBJECT_REQUIRED")
    if subject.schema != EVIDENCE_SUBJECT_SCHEMA:
        raise PersistentAgencyError("RECOVERY_EVIDENCE_SUBJECT_SCHEMA_UNSUPPORTED")
    source_ref = _identifier("recovery_evidence_source_ref", subject.source_ref)
    subject_checkpoint_id = _identifier(
        "recovery_evidence_checkpoint_id", subject.checkpoint_id
    )
    subject_checkpoint_sha = _receipt(
        "recovery_evidence_checkpoint_sha256", subject.checkpoint_sha256
    )
    subject_legacy = _receipt(
        "recovery_evidence_legacy_authority_receipt_sha256",
        subject.legacy_authority_receipt_sha256,
    )
    if source_ref != provenance_ref:
        raise PersistentAgencyError("RECOVERY_EVIDENCE_SOURCE_PROVENANCE_MISMATCH")
    if subject_checkpoint_id != checkpoint_id:
        raise PersistentAgencyError("RECOVERY_EVIDENCE_CHECKPOINT_ID_MISMATCH")
    if subject_checkpoint_sha != checkpoint_sha256:
        raise PersistentAgencyError("RECOVERY_EVIDENCE_CHECKPOINT_DIGEST_MISMATCH")
    if subject_legacy != expected_legacy:
        raise PersistentAgencyError("RECOVERY_EVIDENCE_LEGACY_RECEIPT_MISMATCH")
    try:
        evidence_sha = _sha256(subject.as_dict())
    except (TypeError, ValueError, OverflowError) as exc:
        raise PersistentAgencyError(
            "RECOVERY_EVIDENCE_SUBJECT_NOT_CANONICAL_JSON"
        ) from exc
    return subject.schema, source_ref, evidence_sha


def recover_legacy_g1_checkpoint_authority(
    *,
    store: CanonicalPersistentAgencyStore,
    checkpoint_id: str,
    expected_legacy_authority_receipt_sha256: str,
    recovery_provenance_ref: str,
    recovery_evidence_subject: LegacyRecoveryEvidenceSubject | None = None,
) -> LegacyAuthorityRecoveryReceipt:
    """Explicitly rebind one externally witnessed legacy G1 row to current file authority.

    G5 requires a concrete typed evidence subject. Its digest is derived internally and
    bound into new recovery identity. A row already recovered under G4 cannot be made
    historically content-authenticated after the fact; it is surfaced as
    LEGACY_EVIDENCE_SUBJECT_UNBOUND with its original recovery_id preserved.
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
        _ensure_g5_recovery_schema(connection)

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

        subject_schema, subject_source_ref, subject_sha = _bind_evidence_subject(
            subject=recovery_evidence_subject,
            provenance_ref=provenance_ref,
            checkpoint_id=checkpoint_id,
            checkpoint_sha256=checkpoint_sha,
            expected_legacy=expected_legacy,
        )

        existing = connection.execute(
            f"""SELECT recovery_id, checkpoint_sha256,
                       legacy_authority_receipt_sha256,
                       rebound_authority_receipt_sha256,
                       recovery_provenance_ref, classification,
                       recovery_evidence_subject_schema,
                       recovery_evidence_source_ref,
                       recovery_evidence_sha256,
                       recovery_evidence_subject_state
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
                recorded_subject_schema,
                recorded_subject_source_ref,
                recorded_subject_sha,
                recorded_subject_state,
            ) = existing
            if recorded_checkpoint_sha != checkpoint_sha:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_CHECKPOINT_DIGEST_DRIFT"
                )
            if recorded_legacy != expected_legacy:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_EXTERNAL_RECEIPT_CONFLICT"
                )
            if recorded_provenance != provenance_ref:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_PROVENANCE_CONFLICT"
                )
            if recorded_rebound != current_receipt:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_CURRENT_AUTHORITY_CHANGED"
                )
            if stored_receipt != recorded_rebound:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_POST_MIGRATION_AUTHORITY_DRIFT"
                )

            subject_values = (
                recorded_subject_schema,
                recorded_subject_source_ref,
                recorded_subject_sha,
            )
            if all(value is None for value in subject_values):
                if recorded_subject_state not in (
                    None,
                    LEGACY_EVIDENCE_SUBJECT_UNBOUND,
                ):
                    raise PersistentAgencyError(
                        "LEGACY_RECOVERY_EVIDENCE_SUBJECT_STATE_INVALID"
                    )
                connection.execute(
                    f"""UPDATE {RECOVERY_TABLE}
                        SET recovery_evidence_subject_state=?
                        WHERE checkpoint_id=?
                          AND recovery_evidence_subject_schema IS NULL
                          AND recovery_evidence_source_ref IS NULL
                          AND recovery_evidence_sha256 IS NULL""",
                    (LEGACY_EVIDENCE_SUBJECT_UNBOUND, checkpoint_id),
                )
                connection.commit()
                return LegacyAuthorityRecoveryReceipt(
                    schema=LEGACY_RECOVERY_SCHEMA_V1,
                    recovery_id=recovery_id,
                    checkpoint_id=checkpoint_id,
                    checkpoint_sha256=checkpoint_sha,
                    legacy_authority_receipt_sha256=recorded_legacy,
                    rebound_authority_receipt_sha256=recorded_rebound,
                    recovery_provenance_ref=recorded_provenance,
                    recovery_evidence_subject_schema=None,
                    recovery_evidence_source_ref=None,
                    recovery_evidence_sha256=None,
                    recovery_evidence_subject_state=LEGACY_EVIDENCE_SUBJECT_UNBOUND,
                    status=LEGACY_EVIDENCE_SUBJECT_UNBOUND,
                    classification=classification,
                )
            if any(value is None for value in subject_values):
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_EVIDENCE_SUBJECT_PARTIAL_BINDING"
                )
            if recorded_subject_state != EVIDENCE_SUBJECT_BOUND_G5:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_EVIDENCE_SUBJECT_STATE_INVALID"
                )
            if recorded_subject_schema != subject_schema:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_EVIDENCE_SUBJECT_SCHEMA_CONFLICT"
                )
            if recorded_subject_source_ref != subject_source_ref:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_EVIDENCE_SOURCE_CONFLICT"
                )
            if recorded_subject_sha != subject_sha:
                raise PersistentAgencyError(
                    "LEGACY_RECOVERY_EVIDENCE_SUBJECT_CONFLICT"
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
                recovery_evidence_subject_schema=recorded_subject_schema,
                recovery_evidence_source_ref=recorded_subject_source_ref,
                recovery_evidence_sha256=recorded_subject_sha,
                recovery_evidence_subject_state=recorded_subject_state,
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
                "recovery_evidence_subject_schema": subject_schema,
                "recovery_evidence_source_ref": subject_source_ref,
                "recovery_evidence_sha256": subject_sha,
            }
        )
        connection.execute(
            f"""INSERT INTO {RECOVERY_TABLE}(
                recovery_id, checkpoint_id, checkpoint_sha256,
                canonical_db_path, db_device, db_inode,
                legacy_authority_receipt_sha256,
                rebound_authority_receipt_sha256,
                recovery_provenance_ref, classification,
                recovery_evidence_subject_schema,
                recovery_evidence_source_ref,
                recovery_evidence_sha256,
                recovery_evidence_subject_state
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                subject_schema,
                subject_source_ref,
                subject_sha,
                EVIDENCE_SUBJECT_BOUND_G5,
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
            recovery_evidence_subject_schema=subject_schema,
            recovery_evidence_source_ref=subject_source_ref,
            recovery_evidence_sha256=subject_sha,
            recovery_evidence_subject_state=EVIDENCE_SUBJECT_BOUND_G5,
            status=RECOVERED,
            classification=classification,
        )
    except Exception:
        connection.rollback()
        raise


__all__ = [
    "ALREADY_RECOVERED",
    "EVIDENCE_SUBJECT_BOUND_G5",
    "EVIDENCE_SUBJECT_SCHEMA",
    "LEGACY_EVIDENCE_SUBJECT_UNBOUND",
    "LEGACY_RECOVERY_SCHEMA_V1",
    "RECOVERED",
    "RECOVERY_SCHEMA",
    "RECOVERY_TABLE",
    "LegacyAuthorityRecoveryReceipt",
    "LegacyRecoveryEvidenceSubject",
    "recover_legacy_g1_checkpoint_authority",
]
