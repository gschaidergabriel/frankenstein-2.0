"""Persisted-row/load attestation boundary for WP901 restart recovery.

F2-WP-901 generation 4 repository-component scope only.

This successor is deliberately narrower than runtime/recovery acceptance. It proves that the
restart checkpoint used by WP901 passed the exact canonical WP206 SQLite loader, binds the
exact persisted row that was consumed in the same SQLite read snapshot, and closes the direct
predecessor linkage into the authenticated WP900 whole-loop seal before accepted G3/G2
planning is allowed.

It does not create another persistence authority, does not claim same-inode live database
drift closure, and does not grant target-host/runtime, scheduler, truth, effect, completion,
model, GRID10, GWT/J-Space, training, or whole-system credit.
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
    CHECKPOINT_TABLE,
    CanonicalPersistentAgencyStore,
    PersistentAgencyCheckpoint,
)
from .restart_recovery_continuation import PersistedRestartEvidence, RestartContinuationPlan
from .restart_recovery_source_authentication import (
    RestartSourceAuthenticationError,
    plan_restart_continuation_from_sources,
)
from .whole_persistent_loop import LoopOutcomeEvidence, WholePersistentLoopSeal


PERSISTED_ROW_LOAD_ATTESTATION_SCHEMA = (
    "FRANKENSTEIN2_RESTART_PERSISTED_ROW_LOAD_ATTESTATION/v1"
)
PERSISTED_ROW_LOAD_ATTESTATION_CLASSIFICATION = (
    "CANONICAL_WP206_EXACT_TYPE_SQLITE_SNAPSHOT_ROW_LOAD_ATTESTATION_COMPONENT_ONLY"
)
CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF = (
    "workpackages/receipts/F2-WP-100_G1_SOURCE_CI_ACCEPTANCE.json"
)
CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE = "src/state/unifieddb_identity.py"


class RestartPersistedRowLoadAttestationError(RestartSourceAuthenticationError):
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


def _same_real_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
        os.path.realpath(right)
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class PersistedCheckpointLoadReceipt:
    """Typed, immutable evidence over one exact WP206 checkpoint row consumption."""

    checkpoint_id: str
    checkpoint_generation: int
    checkpoint_sha256: str
    previous_checkpoint_id: str
    predecessor_checkpoint_sha256: str
    kernel_state_id: str
    checkpoint_json_sha256: str
    row_evidence_sha256: str
    canonical_db_path: str
    db_device: int
    db_inode: int
    store_authority_receipt_sha256: str
    unifieddb_authority_receipt_ref: str
    unifieddb_authority_canonical_source: str
    evidence_id: str
    evidence_sha256: str

    schema: ClassVar[str] = PERSISTED_ROW_LOAD_ATTESTATION_SCHEMA
    classification: ClassVar[str] = PERSISTED_ROW_LOAD_ATTESTATION_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_generation": self.checkpoint_generation,
            "checkpoint_sha256": self.checkpoint_sha256,
            "previous_checkpoint_id": self.previous_checkpoint_id,
            "predecessor_checkpoint_sha256": self.predecessor_checkpoint_sha256,
            "kernel_state_id": self.kernel_state_id,
            "checkpoint_json_sha256": self.checkpoint_json_sha256,
            "row_evidence_sha256": self.row_evidence_sha256,
            "canonical_db_path": self.canonical_db_path,
            "db_device": self.db_device,
            "db_inode": self.db_inode,
            "store_authority_receipt_sha256": self.store_authority_receipt_sha256,
            "unifieddb_authority_receipt_ref": self.unifieddb_authority_receipt_ref,
            "unifieddb_authority_canonical_source": self.unifieddb_authority_canonical_source,
            "evidence_id": self.evidence_id,
            "evidence_sha256": self.evidence_sha256,
            "persisted_checkpoint_row_load": "OBSERVED_VIA_EXACT_CANONICAL_WP206_STORE",
            "sqlite_snapshot_bound": True,
            "row_evidence_digest_bound": True,
            "unifieddb_component_authority_bound": True,
            "wp900_persisted_seal_load": "NOT_CLAIMED",
            "same_inode_live_database_drift": "NOT_CLAIMED",
            "target_host_execution_observed": False,
            "runtime_credit": 0,
            "truth_authority": "NONE",
            "scheduler_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "persistence_authority": "EXISTING_UNIFIEDDB_ONLY",
        }

    def sha256(self) -> str:
        return _sha256_json(self.as_dict())


def load_checkpoint_with_persisted_row_receipt(
    evidence: PersistedRestartEvidence,
    *,
    store: CanonicalPersistentAgencyStore,
    unifieddb_authority: UnifiedDBAuthorityRef,
) -> tuple[PersistentAgencyCheckpoint, PersistedCheckpointLoadReceipt]:
    """Load one exact WP206 row and mint a deterministic non-authoritative receipt.

    The exact type check plus direct base-class dispatch closes hostile subclass loader
    substitution. The explicit read transaction keeps the typed loader read, exact row
    evidence read, and predecessor replay on one SQLite snapshot. The downstream
    ``UnifiedDBAuthorityRef`` must name the exact already-accepted WP100 UnifiedDB identity
    component; the actual file identity remains independently bound by the WP206 store's
    path/device/inode and bound-file authority receipt.
    """
    if type(evidence) is not PersistedRestartEvidence:
        raise RestartPersistedRowLoadAttestationError(
            "evidence must be concrete PersistedRestartEvidence"
        )
    if type(store) is not CanonicalPersistentAgencyStore:
        raise RestartPersistedRowLoadAttestationError(
            "PERSISTED_ROW_CANONICAL_STORE_EXACT_TYPE_REQUIRED"
        )
    if type(unifieddb_authority) is not UnifiedDBAuthorityRef:
        raise RestartPersistedRowLoadAttestationError(
            "unifieddb_authority must be concrete UnifiedDBAuthorityRef"
        )
    if unifieddb_authority.fingerprint_schema != store.fingerprint.schema:
        raise RestartPersistedRowLoadAttestationError(
            "PERSISTED_ROW_UNIFIEDDB_FINGERPRINT_SCHEMA_MISMATCH"
        )
    if unifieddb_authority.receipt_ref != CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF:
        raise RestartPersistedRowLoadAttestationError(
            "PERSISTED_ROW_UNIFIEDDB_AUTHORITY_RECEIPT_REF_MISMATCH"
        )
    if unifieddb_authority.canonical_source != CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE:
        raise RestartPersistedRowLoadAttestationError(
            "PERSISTED_ROW_UNIFIEDDB_AUTHORITY_CANONICAL_SOURCE_MISMATCH"
        )
    if store.connection.in_transaction:
        raise RestartPersistedRowLoadAttestationError(
            "PERSISTED_ROW_CALLER_TRANSACTION_ALREADY_OPEN"
        )

    connection = store.connection
    try:
        connection.execute("BEGIN")
        checkpoint = CanonicalPersistentAgencyStore.load_checkpoint(
            store, evidence.source_checkpoint_id
        )

        row = connection.execute(
            f"""SELECT checkpoint_id, previous_checkpoint_id, kernel_state_id, generation,
                       checkpoint_sha256, checkpoint_json, canonical_db_path,
                       db_device, db_inode, unifieddb_authority_receipt_sha256
                FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
            (checkpoint.checkpoint_id,),
        ).fetchone()
        if row is None:
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_DISAPPEARED_INSIDE_SNAPSHOT"
            )

        (
            row_checkpoint_id,
            row_previous_checkpoint_id,
            row_kernel_state_id,
            row_generation,
            row_checkpoint_sha256,
            row_checkpoint_json,
            row_db_path,
            row_device,
            row_inode,
            row_authority_receipt,
        ) = row

        checkpoint_sha = checkpoint.sha256()
        if row_checkpoint_id != checkpoint.checkpoint_id:
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_CHECKPOINT_ID_MISMATCH"
            )
        if row_previous_checkpoint_id != checkpoint.previous_checkpoint_id:
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_PREVIOUS_CHECKPOINT_ID_MISMATCH"
            )
        if row_kernel_state_id != checkpoint.kernel_state_id:
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_KERNEL_STATE_ID_MISMATCH"
            )
        if row_generation != checkpoint.generation:
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_CHECKPOINT_GENERATION_MISMATCH"
            )
        if row_checkpoint_sha256 != checkpoint_sha:
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_CHECKPOINT_DIGEST_MISMATCH"
            )
        if row_checkpoint_json != checkpoint.canonical_json():
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_CHECKPOINT_JSON_BYTES_MISMATCH"
            )
        if not _same_real_path(row_db_path, store.canonical_db_path):
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_DB_PATH_MISMATCH"
            )
        if (row_device, row_inode) != (store.db_device, store.db_inode):
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_DB_FILE_IDENTITY_MISMATCH"
            )
        if row_authority_receipt != store.authority_receipt_sha256:
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_STORE_AUTHORITY_RECEIPT_MISMATCH"
            )

        if checkpoint.previous_checkpoint_id is None:
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_RESTART_CHECKPOINT_REQUIRES_PREDECESSOR"
            )
        predecessor = CanonicalPersistentAgencyStore.load_checkpoint(
            store, checkpoint.previous_checkpoint_id
        )
        if predecessor.checkpoint_id != checkpoint.previous_checkpoint_id:
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_PREDECESSOR_ID_MISMATCH"
            )
        if predecessor.kernel_state_id != checkpoint.kernel_state_id:
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_PREDECESSOR_KERNEL_STATE_MISMATCH"
            )
        if predecessor.generation + 1 != checkpoint.generation:
            raise RestartPersistedRowLoadAttestationError(
                "PERSISTED_ROW_PREDECESSOR_GENERATION_MISMATCH"
            )

        row_evidence = {
            "checkpoint_id": row_checkpoint_id,
            "previous_checkpoint_id": row_previous_checkpoint_id,
            "kernel_state_id": row_kernel_state_id,
            "generation": row_generation,
            "checkpoint_sha256": row_checkpoint_sha256,
            "checkpoint_json": row_checkpoint_json,
            "canonical_db_path": os.path.realpath(row_db_path),
            "db_device": row_device,
            "db_inode": row_inode,
            "unifieddb_authority_receipt_sha256": row_authority_receipt,
        }
        receipt = PersistedCheckpointLoadReceipt(
            checkpoint_id=checkpoint.checkpoint_id,
            checkpoint_generation=checkpoint.generation,
            checkpoint_sha256=checkpoint_sha,
            previous_checkpoint_id=predecessor.checkpoint_id,
            predecessor_checkpoint_sha256=predecessor.sha256(),
            kernel_state_id=checkpoint.kernel_state_id,
            checkpoint_json_sha256=hashlib.sha256(
                row_checkpoint_json.encode("utf-8")
            ).hexdigest(),
            row_evidence_sha256=_sha256_json(row_evidence),
            canonical_db_path=store.canonical_db_path,
            db_device=store.db_device,
            db_inode=store.db_inode,
            store_authority_receipt_sha256=store.authority_receipt_sha256,
            unifieddb_authority_receipt_ref=unifieddb_authority.receipt_ref,
            unifieddb_authority_canonical_source=unifieddb_authority.canonical_source,
            evidence_id=evidence.evidence_id,
            evidence_sha256=evidence.sha256(),
        )
        connection.commit()
        return checkpoint, receipt
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise


def plan_restart_continuation_from_persisted_row_load(
    evidence: PersistedRestartEvidence,
    *,
    plan_id: str,
    expected_evidence_sha256: str,
    causal_identity: CausalIdentity,
    unifieddb_authority: UnifiedDBAuthorityRef,
    store: CanonicalPersistentAgencyStore,
    whole_loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
) -> RestartContinuationPlan:
    """Canonical G4 ingress: exact persisted row load, then accepted G3/G2 planning."""
    checkpoint, receipt = load_checkpoint_with_persisted_row_receipt(
        evidence,
        store=store,
        unifieddb_authority=unifieddb_authority,
    )
    if expected_evidence_sha256 != receipt.evidence_sha256:
        raise RestartPersistedRowLoadAttestationError(
            "PERSISTED_ROW_EXPECTED_EVIDENCE_DIGEST_MISMATCH"
        )

    if checkpoint.previous_checkpoint_id != whole_loop_seal.current_checkpoint_id:
        raise RestartPersistedRowLoadAttestationError(
            "PERSISTED_ROW_SEAL_PREDECESSOR_ID_MISMATCH"
        )
    if receipt.predecessor_checkpoint_sha256 != whole_loop_seal.current_checkpoint_sha256:
        raise RestartPersistedRowLoadAttestationError(
            "PERSISTED_ROW_SEAL_PREDECESSOR_DIGEST_MISMATCH"
        )

    try:
        return plan_restart_continuation_from_sources(
            evidence,
            plan_id=plan_id,
            expected_evidence_sha256=receipt.evidence_sha256,
            causal_identity=causal_identity,
            unifieddb_authority=unifieddb_authority,
            source_checkpoint=checkpoint,
            whole_loop_seal=whole_loop_seal,
            outcome=outcome,
        )
    except RestartSourceAuthenticationError as exc:
        raise RestartPersistedRowLoadAttestationError(
            f"PERSISTED_ROW_DOWNSTREAM_SOURCE_BINDING_REJECTED:{exc}"
        ) from exc


__all__ = [
    "CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF",
    "CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE",
    "PERSISTED_ROW_LOAD_ATTESTATION_CLASSIFICATION",
    "PERSISTED_ROW_LOAD_ATTESTATION_SCHEMA",
    "PersistedCheckpointLoadReceipt",
    "RestartPersistedRowLoadAttestationError",
    "load_checkpoint_with_persisted_row_receipt",
    "plan_restart_continuation_from_persisted_row_load",
]
