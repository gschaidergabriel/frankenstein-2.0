"""Persisted WP206 checkpoint-row attestation for WP901 restart planning.

F2-WP-901 generation 4 repository-component scope only.

Accepted WP901 G3 deliberately stopped at typed source-object authentication: a concrete
``PersistentAgencyCheckpoint`` was required, but G3 did not prove that object was actually
loaded from the canonical WP206 row.  This successor closes only that explicit gap.

The canonical G4 ingress accepts a ``CanonicalPersistentAgencyStore`` and a
``PersistedRestartEvidence``.  It loads the restart checkpoint by the evidence checkpoint id
through ``store.load_checkpoint()``.  That existing WP206 load boundary already validates the
canonical database path, device/inode identity, bound-file authority receipt, stored digest,
JSON decoding and typed checkpoint replay.  G4 then compares the loaded id/generation/digest
to the restart evidence and passes the *loaded object* into the accepted G3 source-binding
planner.

This module does not attest that a WP900 seal was itself loaded from persistent storage and it
does not grant target-host/runtime, scheduler, truth, effect or completion authority.  It
creates no second database and performs no provider/model/tool calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .causal_authority_binding import UnifiedDBAuthorityRef
from .causal_identity import CausalIdentity
from .persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    PersistentAgencyCheckpoint,
    PersistentAgencyError,
)
from .restart_recovery_continuation import (
    PersistedRestartEvidence,
    RestartContinuationPlan,
    RestartRecoveryError,
)
from .restart_recovery_source_authentication import (
    RestartSourceAuthenticationError,
    plan_restart_continuation_from_sources,
)
from .whole_persistent_loop import LoopOutcomeEvidence, WholePersistentLoopSeal


PERSISTED_ROW_ATTESTATION_SCHEMA = (
    "FRANKENSTEIN2_RESTART_RECOVERY_PERSISTED_CHECKPOINT_ROW_ATTESTATION/v1"
)
PERSISTED_ROW_ATTESTATION_CLASSIFICATION = (
    "CANONICAL_WP206_STORE_LOADED_CHECKPOINT_ROW_ATTESTATION_REPOSITORY_COMPONENT_ONLY"
)


class RestartPersistedRowAttestationError(RestartSourceAuthenticationError):
    """Fail-closed persisted checkpoint-row attestation error."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PersistedCheckpointRowAttestation:
    """Evidence that one exact checkpoint passed the canonical WP206 store load boundary."""

    checkpoint_id: str
    checkpoint_generation: int
    checkpoint_sha256: str
    evidence_id: str
    evidence_sha256: str
    canonical_db_path: str
    db_device: int
    db_inode: int
    bound_file_authority_receipt_sha256: str

    schema: ClassVar[str] = PERSISTED_ROW_ATTESTATION_SCHEMA
    classification: ClassVar[str] = PERSISTED_ROW_ATTESTATION_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_generation": self.checkpoint_generation,
            "checkpoint_sha256": self.checkpoint_sha256,
            "evidence_id": self.evidence_id,
            "evidence_sha256": self.evidence_sha256,
            "canonical_db_path": self.canonical_db_path,
            "db_device": self.db_device,
            "db_inode": self.db_inode,
            "bound_file_authority_receipt_sha256": (
                self.bound_file_authority_receipt_sha256
            ),
            "persisted_checkpoint_row_attestation": "OBSERVED_VIA_CANONICAL_STORE_LOAD",
            "wp900_persisted_seal_attestation": "NOT_OBSERVED",
            "target_host_runtime_credit": 0,
            "truth_authority": "NONE",
            "scheduler_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "persistence_authority": "EXISTING_UNIFIEDDB_ONLY",
        }


def attest_persisted_restart_checkpoint(
    evidence: PersistedRestartEvidence,
    *,
    store: CanonicalPersistentAgencyStore,
) -> tuple[PersistentAgencyCheckpoint, PersistedCheckpointRowAttestation]:
    """Load and exactly bind the restart checkpoint from the canonical WP206 store.

    No caller-supplied checkpoint object is accepted.  Any persisted row/path/file/authority
    drift detected by ``CanonicalPersistentAgencyStore.load_checkpoint`` remains fail closed.
    """
    if type(evidence) is not PersistedRestartEvidence:
        raise RestartPersistedRowAttestationError(
            "evidence must be concrete PersistedRestartEvidence"
        )
    if not isinstance(store, CanonicalPersistentAgencyStore):
        raise RestartPersistedRowAttestationError(
            "store must be CanonicalPersistentAgencyStore"
        )

    try:
        checkpoint = store.load_checkpoint(evidence.source_checkpoint_id)
    except PersistentAgencyError as exc:
        raise RestartPersistedRowAttestationError(
            f"PERSISTED_RESTART_CHECKPOINT_LOAD_REJECTED:{exc}"
        ) from exc

    checkpoint_sha = checkpoint.sha256()
    if checkpoint.checkpoint_id != evidence.source_checkpoint_id:
        raise RestartPersistedRowAttestationError(
            "PERSISTED_RESTART_CHECKPOINT_ID_MISMATCH"
        )
    if checkpoint.generation != evidence.source_checkpoint_generation:
        raise RestartPersistedRowAttestationError(
            "PERSISTED_RESTART_CHECKPOINT_GENERATION_MISMATCH"
        )
    if checkpoint_sha != evidence.source_checkpoint_sha256:
        raise RestartPersistedRowAttestationError(
            "PERSISTED_RESTART_CHECKPOINT_DIGEST_MISMATCH"
        )

    attestation = PersistedCheckpointRowAttestation(
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_generation=checkpoint.generation,
        checkpoint_sha256=checkpoint_sha,
        evidence_id=evidence.evidence_id,
        evidence_sha256=evidence.sha256(),
        canonical_db_path=store.canonical_db_path,
        db_device=store.db_device,
        db_inode=store.db_inode,
        bound_file_authority_receipt_sha256=store.authority_receipt_sha256,
    )
    return checkpoint, attestation


def plan_restart_continuation_from_persisted_row(
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
    """Canonical G4 ingress: load WP206 row, then preserve the accepted G3/G2 gates."""
    checkpoint, attestation = attest_persisted_restart_checkpoint(
        evidence,
        store=store,
    )
    if expected_evidence_sha256 != attestation.evidence_sha256:
        raise RestartPersistedRowAttestationError(
            "PERSISTED_ROW_EXPECTED_EVIDENCE_DIGEST_MISMATCH"
        )

    try:
        return plan_restart_continuation_from_sources(
            evidence,
            plan_id=plan_id,
            expected_evidence_sha256=attestation.evidence_sha256,
            causal_identity=causal_identity,
            unifieddb_authority=unifieddb_authority,
            source_checkpoint=checkpoint,
            whole_loop_seal=whole_loop_seal,
            outcome=outcome,
        )
    except (RestartSourceAuthenticationError, RestartRecoveryError) as exc:
        raise RestartPersistedRowAttestationError(
            f"PERSISTED_ROW_DOWNSTREAM_SOURCE_BINDING_REJECTED:{exc}"
        ) from exc


__all__ = [
    "PERSISTED_ROW_ATTESTATION_CLASSIFICATION",
    "PERSISTED_ROW_ATTESTATION_SCHEMA",
    "PersistedCheckpointRowAttestation",
    "RestartPersistedRowAttestationError",
    "attest_persisted_restart_checkpoint",
    "plan_restart_continuation_from_persisted_row",
]
