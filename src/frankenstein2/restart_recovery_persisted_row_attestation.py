"""Persisted-row/load attestation boundary for WP901 restart planning.

F2-WP-901 generation 4 repository-component scope only.

Accepted WP901 G3 authenticates concrete typed checkpoint/seal/outcome objects, but it
explicitly does not prove that the checkpoint object came from a persisted UnifiedDB row.
This adapter closes only that repository-component gap by wrapping the already-accepted
WP206 :class:`CanonicalPersistentAgencyStore.load_checkpoint` path in one SQLite read
snapshot, binding the exact loaded checkpoint to the store's canonical file identity and
bound-file authority receipt, and only then calling the accepted G3 planner.

This module does not create a second persistence authority and does not grant target-host,
truth, scheduler, effect, completion, model, GRID10, GWT/J-Space, training, or whole-system
credit. A successful repository test still is not target-host execution/readback evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from typing import Any, ClassVar

from .causal_authority_binding import UnifiedDBAuthorityRef
from .causal_identity import CausalIdentity
from .persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    PersistentAgencyCheckpoint,
    PersistentAgencyError,
)
from .restart_recovery_continuation import PersistedRestartEvidence, RestartContinuationPlan
from .restart_recovery_source_authentication import (
    RestartSourceAuthenticationError,
    plan_restart_continuation_from_sources,
)
from .whole_persistent_loop import LoopOutcomeEvidence, WholePersistentLoopSeal


PERSISTED_ROW_ATTESTATION_SCHEMA = (
    "FRANKENSTEIN2_RESTART_PERSISTED_ROW_LOAD_ATTESTATION/v1"
)
PERSISTED_ROW_ATTESTATION_CLASSIFICATION = (
    "SQLITE_SNAPSHOT_ROW_CONSUMPTION_ATTESTATION_NOT_CANONICAL_TRUTH_OR_TARGET_RUNTIME"
)
_STORE_AUTHORITY_REF_PREFIX = "f2:wp206-bound-file-authority-sha256:"


class RestartPersistedRowAttestationError(RestartSourceAuthenticationError):
    """Fail-closed persisted-row/load-attestation error."""


def _sha256_json(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def store_authority_receipt_ref(store: CanonicalPersistentAgencyStore) -> str:
    """Deterministic reference to the exact WP206 bound-file authority receipt."""
    if type(store) is not CanonicalPersistentAgencyStore:
        raise RestartPersistedRowAttestationError(
            "store must be concrete CanonicalPersistentAgencyStore"
        )
    return _STORE_AUTHORITY_REF_PREFIX + store.authority_receipt_sha256


@dataclass(frozen=True, slots=True, kw_only=True)
class PersistedRowLoadAttestation:
    """Non-authoritative evidence that one exact checkpoint row was consumed."""

    checkpoint_id: str
    checkpoint_generation: int
    checkpoint_sha256: str
    checkpoint_json_sha256: str
    row_identity_sha256: str
    canonical_db_path: str
    db_device: int
    db_inode: int
    unifieddb_authority_receipt_sha256: str
    unifieddb_authority_ref: str

    schema: ClassVar[str] = PERSISTED_ROW_ATTESTATION_SCHEMA
    classification: ClassVar[str] = PERSISTED_ROW_ATTESTATION_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_generation": self.checkpoint_generation,
            "checkpoint_sha256": self.checkpoint_sha256,
            "checkpoint_json_sha256": self.checkpoint_json_sha256,
            "row_identity_sha256": self.row_identity_sha256,
            "canonical_db_path": self.canonical_db_path,
            "db_device": self.db_device,
            "db_inode": self.db_inode,
            "unifieddb_authority_receipt_sha256": (
                self.unifieddb_authority_receipt_sha256
            ),
            "unifieddb_authority_ref": self.unifieddb_authority_ref,
            "persisted_row_consumed": True,
            "sqlite_snapshot_bound": True,
            "truth_authority": "NONE",
            "persistence_authority": "NONE",
            "scheduler_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "target_host_execution_observed": False,
        }

    def sha256(self) -> str:
        return _sha256_json(self.as_dict())


def _verify_unifieddb_authority_ref(
    store: CanonicalPersistentAgencyStore,
    authority: UnifiedDBAuthorityRef,
) -> None:
    if type(authority) is not UnifiedDBAuthorityRef:
        raise RestartPersistedRowAttestationError(
            "unifieddb_authority must be concrete UnifiedDBAuthorityRef"
        )
    expected_ref = store_authority_receipt_ref(store)
    if authority.receipt_ref != expected_ref:
        raise RestartPersistedRowAttestationError(
            "PERSISTED_ROW_UNIFIEDDB_AUTHORITY_REF_MISMATCH"
        )
    if authority.fingerprint_schema != store.fingerprint.schema:
        raise RestartPersistedRowAttestationError(
            "PERSISTED_ROW_UNIFIEDDB_FINGERPRINT_SCHEMA_MISMATCH"
        )


def load_checkpoint_with_attestation(
    store: CanonicalPersistentAgencyStore,
    checkpoint_id: str,
    *,
    unifieddb_authority: UnifiedDBAuthorityRef,
) -> tuple[PersistentAgencyCheckpoint, PersistedRowLoadAttestation]:
    """Consume one checkpoint through WP206 and bind the exact SQLite snapshot row.

    The explicit read transaction is important: ``load_checkpoint`` and the metadata
    read used to construct the attestation observe the same SQLite snapshot. The accepted
    WP206 loader remains the component that validates DB path/device/inode, authority
    receipt, JSON digest, and typed replay digest.
    """
    if type(store) is not CanonicalPersistentAgencyStore:
        raise RestartPersistedRowAttestationError(
            "store must be concrete CanonicalPersistentAgencyStore"
        )
    if store.connection.in_transaction:
        raise RestartPersistedRowAttestationError(
            "PERSISTED_ROW_CALLER_TRANSACTION_ALREADY_OPEN"
        )
    _verify_unifieddb_authority_ref(store, unifieddb_authority)

    try:
        store.connection.execute("BEGIN")
        checkpoint = store.load_checkpoint(checkpoint_id)
        row = store.connection.execute(
            """SELECT checkpoint_id, kernel_state_id, generation,
                      checkpoint_sha256, checkpoint_json, canonical_db_path,
                      db_device, db_inode, unifieddb_authority_receipt_sha256
               FROM f2_persistent_agency_checkpoints WHERE checkpoint_id=?""",
            (checkpoint.checkpoint_id,),
        ).fetchone()
        if row is None:
            raise RestartPersistedRowAttestationError(
                "PERSISTED_ROW_DISAPPEARED_INSIDE_SNAPSHOT"
            )
        (
            row_checkpoint_id,
            row_kernel_state_id,
            row_generation,
            row_checkpoint_sha256,
            row_checkpoint_json,
            row_db_path,
            row_device,
            row_inode,
            row_authority_receipt,
        ) = row

        if row_checkpoint_id != checkpoint.checkpoint_id:
            raise RestartPersistedRowAttestationError(
                "PERSISTED_ROW_CHECKPOINT_ID_MISMATCH"
            )
        if row_generation != checkpoint.generation:
            raise RestartPersistedRowAttestationError(
                "PERSISTED_ROW_CHECKPOINT_GENERATION_MISMATCH"
            )
        if row_checkpoint_sha256 != checkpoint.sha256():
            raise RestartPersistedRowAttestationError(
                "PERSISTED_ROW_CHECKPOINT_DIGEST_MISMATCH"
            )
        if os.path.normcase(os.path.realpath(row_db_path)) != os.path.normcase(
            store.canonical_db_path
        ):
            raise RestartPersistedRowAttestationError(
                "PERSISTED_ROW_DB_PATH_MISMATCH"
            )
        if (row_device, row_inode) != (store.db_device, store.db_inode):
            raise RestartPersistedRowAttestationError(
                "PERSISTED_ROW_DB_FILE_IDENTITY_MISMATCH"
            )
        if row_authority_receipt != store.authority_receipt_sha256:
            raise RestartPersistedRowAttestationError(
                "PERSISTED_ROW_DB_AUTHORITY_RECEIPT_MISMATCH"
            )

        row_identity = {
            "checkpoint_id": row_checkpoint_id,
            "kernel_state_id": row_kernel_state_id,
            "generation": row_generation,
            "checkpoint_sha256": row_checkpoint_sha256,
            "checkpoint_json_sha256": hashlib.sha256(
                row_checkpoint_json.encode("utf-8")
            ).hexdigest(),
            "canonical_db_path": os.path.realpath(row_db_path),
            "db_device": row_device,
            "db_inode": row_inode,
            "unifieddb_authority_receipt_sha256": row_authority_receipt,
        }
        attestation = PersistedRowLoadAttestation(
            checkpoint_id=checkpoint.checkpoint_id,
            checkpoint_generation=checkpoint.generation,
            checkpoint_sha256=checkpoint.sha256(),
            checkpoint_json_sha256=row_identity["checkpoint_json_sha256"],
            row_identity_sha256=_sha256_json(row_identity),
            canonical_db_path=store.canonical_db_path,
            db_device=store.db_device,
            db_inode=store.db_inode,
            unifieddb_authority_receipt_sha256=store.authority_receipt_sha256,
            unifieddb_authority_ref=unifieddb_authority.receipt_ref,
        )
        store.connection.commit()
        return checkpoint, attestation
    except Exception:
        if store.connection.in_transaction:
            store.connection.rollback()
        raise


def plan_restart_continuation_from_persisted_row(
    store: CanonicalPersistentAgencyStore,
    checkpoint_id: str,
    evidence: PersistedRestartEvidence,
    *,
    plan_id: str,
    expected_evidence_sha256: str,
    causal_identity: CausalIdentity,
    unifieddb_authority: UnifiedDBAuthorityRef,
    whole_loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
) -> tuple[RestartContinuationPlan, PersistedRowLoadAttestation]:
    """Canonical G4 component boundary: persisted row -> accepted G3 -> G2 plan."""
    checkpoint, attestation = load_checkpoint_with_attestation(
        store,
        checkpoint_id,
        unifieddb_authority=unifieddb_authority,
    )
    plan = plan_restart_continuation_from_sources(
        evidence,
        plan_id=plan_id,
        expected_evidence_sha256=expected_evidence_sha256,
        causal_identity=causal_identity,
        unifieddb_authority=unifieddb_authority,
        source_checkpoint=checkpoint,
        whole_loop_seal=whole_loop_seal,
        outcome=outcome,
    )
    return plan, attestation


__all__ = [
    "PERSISTED_ROW_ATTESTATION_CLASSIFICATION",
    "PERSISTED_ROW_ATTESTATION_SCHEMA",
    "PersistedRowLoadAttestation",
    "RestartPersistedRowAttestationError",
    "load_checkpoint_with_attestation",
    "plan_restart_continuation_from_persisted_row",
    "store_authority_receipt_ref",
]
