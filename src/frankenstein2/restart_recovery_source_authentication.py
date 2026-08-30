"""Typed source-binding boundary for WP901 restart/recovery planning.

F2-WP-901 generation 3 repository-component scope only.

This module closes the *self-attested string/hash* gap left outside accepted WP901 G2.
It does not claim to load rows from UnifiedDB and it does not turn a caller assertion into
canonical truth.  Instead it requires:

* the existing canonical :class:`CausalIdentity`;
* concrete :class:`PersistentAgencyCheckpoint`, :class:`WholePersistentLoopSeal`, and
  :class:`LoopOutcomeEvidence` objects;
* an explicit :class:`UnifiedDBAuthorityRef` witnessing the separately admitted canonical
  state authority; and
* the same causal-identity provenance reference on the concrete checkpoint, outcome, seal,
  and persisted restart evidence.

Principal ids/digests passed to the accepted G2 planner are derived from those concrete
objects.  The low-level G2 planner therefore remains unchanged and keeps every G2
reason-code/disposition invariant already accepted by repository CI.

Important evidence boundary: a ``UnifiedDBAuthorityRef`` is an authority *reference*, not
proof that a particular row was loaded.  Target/runtime loader-consumption or persisted-row
attestation remains a later integration gate and receives zero credit here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .causal_authority_binding import UnifiedDBAuthorityRef
from .causal_identity import CausalIdentity
from .persistent_agency_kernel import PersistentAgencyCheckpoint
from .restart_recovery_continuation import (
    PersistedRestartEvidence,
    RestartContinuationPlan,
    RestartRecoveryError,
    plan_restart_continuation,
)
from .whole_persistent_loop import LoopOutcomeEvidence, WholePersistentLoopSeal


SOURCE_BINDING_SCHEMA = "FRANKENSTEIN2_RESTART_RECOVERY_SOURCE_BINDING/v1"
SOURCE_BINDING_CLASSIFICATION = (
    "TYPED_SOURCE_OBJECT_AND_AUTHORITY_REFERENCE_BINDING_NOT_PERSISTED_ROW_ATTESTATION"
)


class RestartSourceAuthenticationError(RestartRecoveryError):
    """Fail-closed source-object/authority-binding error."""


def causal_identity_ref(identity: CausalIdentity) -> str:
    """Exact reusable provenance ref for one canonical F2 causal identity."""
    if type(identity) is not CausalIdentity:
        raise RestartSourceAuthenticationError(
            "causal_identity must be concrete CausalIdentity"
        )
    return f"f2:causal-identity:{identity.causal_id}:{identity.sha256()}"


@dataclass(frozen=True, slots=True, kw_only=True)
class RestartSourceBinding:
    """Validated non-authoritative binding used before the accepted G2 planner."""

    causal_identity: CausalIdentity
    unifieddb_authority: UnifiedDBAuthorityRef
    checkpoint_id: str
    checkpoint_generation: int
    checkpoint_sha256: str
    whole_loop_seal_id: str
    whole_loop_seal_sha256: str
    outcome_id: str
    outcome_sha256: str
    evidence_id: str
    evidence_sha256: str

    schema: ClassVar[str] = SOURCE_BINDING_SCHEMA
    classification: ClassVar[str] = SOURCE_BINDING_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "causal_identity": self.causal_identity.as_dict(),
            "causal_identity_sha256": self.causal_identity.sha256(),
            "unifieddb_authority": {
                "receipt_ref": self.unifieddb_authority.receipt_ref,
                "canonical_source": self.unifieddb_authority.canonical_source,
                "fingerprint_schema": self.unifieddb_authority.fingerprint_schema,
            },
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_generation": self.checkpoint_generation,
            "checkpoint_sha256": self.checkpoint_sha256,
            "whole_loop_seal_id": self.whole_loop_seal_id,
            "whole_loop_seal_sha256": self.whole_loop_seal_sha256,
            "outcome_id": self.outcome_id,
            "outcome_sha256": self.outcome_sha256,
            "evidence_id": self.evidence_id,
            "evidence_sha256": self.evidence_sha256,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "persistence_authority": "NONE",
            "persisted_row_attestation": "NOT_OBSERVED",
        }


def bind_restart_sources(
    evidence: PersistedRestartEvidence,
    *,
    causal_identity: CausalIdentity,
    unifieddb_authority: UnifiedDBAuthorityRef,
    source_checkpoint: PersistentAgencyCheckpoint,
    whole_loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
) -> RestartSourceBinding:
    """Validate concrete restart sources without creating state/effect authority."""
    if type(evidence) is not PersistedRestartEvidence:
        raise RestartSourceAuthenticationError(
            "evidence must be concrete PersistedRestartEvidence"
        )
    if type(causal_identity) is not CausalIdentity:
        raise RestartSourceAuthenticationError(
            "causal_identity must be concrete CausalIdentity"
        )
    if type(unifieddb_authority) is not UnifiedDBAuthorityRef:
        raise RestartSourceAuthenticationError(
            "unifieddb_authority must be concrete UnifiedDBAuthorityRef"
        )
    if type(source_checkpoint) is not PersistentAgencyCheckpoint:
        raise RestartSourceAuthenticationError(
            "source_checkpoint must be concrete PersistentAgencyCheckpoint"
        )
    if type(whole_loop_seal) is not WholePersistentLoopSeal:
        raise RestartSourceAuthenticationError(
            "whole_loop_seal must be concrete WholePersistentLoopSeal"
        )
    if type(outcome) is not LoopOutcomeEvidence:
        raise RestartSourceAuthenticationError(
            "outcome must be concrete LoopOutcomeEvidence"
        )

    checkpoint_sha = source_checkpoint.sha256()
    seal_sha = whole_loop_seal.sha256()
    outcome_sha = outcome.sha256()
    causal_ref = causal_identity_ref(causal_identity)

    if causal_identity.generation != source_checkpoint.generation:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_CAUSAL_CHECKPOINT_GENERATION_MISMATCH"
        )
    if source_checkpoint.generation != whole_loop_seal.generation + 1:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_SEAL_CHECKPOINT_GENERATION_MISMATCH"
        )
    if whole_loop_seal.next_checkpoint_id != source_checkpoint.checkpoint_id:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_SEAL_CHECKPOINT_ID_MISMATCH"
        )
    if whole_loop_seal.next_checkpoint_sha256 != checkpoint_sha:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_SEAL_CHECKPOINT_DIGEST_MISMATCH"
        )
    if whole_loop_seal.outcome_id != outcome.outcome_id:
        raise RestartSourceAuthenticationError("SOURCE_AUTH_SEAL_OUTCOME_ID_MISMATCH")
    if whole_loop_seal.outcome_sha256 != outcome_sha:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_SEAL_OUTCOME_DIGEST_MISMATCH"
        )

    if evidence.source_checkpoint_id != source_checkpoint.checkpoint_id:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_EVIDENCE_CHECKPOINT_ID_MISMATCH"
        )
    if evidence.source_checkpoint_generation != source_checkpoint.generation:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_EVIDENCE_CHECKPOINT_GENERATION_MISMATCH"
        )
    if evidence.source_checkpoint_sha256 != checkpoint_sha:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_EVIDENCE_CHECKPOINT_DIGEST_MISMATCH"
        )
    if evidence.whole_loop_seal_id != whole_loop_seal.seal_id:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_EVIDENCE_SEAL_ID_MISMATCH"
        )
    if evidence.whole_loop_seal_sha256 != seal_sha:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_EVIDENCE_SEAL_DIGEST_MISMATCH"
        )
    if evidence.outcome_status != outcome.status:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_EVIDENCE_OUTCOME_STATUS_MISMATCH"
        )
    if evidence.outcome_sha256 != outcome_sha:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_EVIDENCE_OUTCOME_DIGEST_MISMATCH"
        )

    for label, refs in (
        ("checkpoint", source_checkpoint.provenance_refs),
        ("whole_loop_seal", whole_loop_seal.provenance_refs),
        ("outcome", outcome.provenance_refs),
        ("restart_evidence", evidence.provenance_refs),
    ):
        if causal_ref not in refs:
            raise RestartSourceAuthenticationError(
                f"SOURCE_AUTH_CAUSAL_REF_MISSING:{label}"
            )

    return RestartSourceBinding(
        causal_identity=causal_identity,
        unifieddb_authority=unifieddb_authority,
        checkpoint_id=source_checkpoint.checkpoint_id,
        checkpoint_generation=source_checkpoint.generation,
        checkpoint_sha256=checkpoint_sha,
        whole_loop_seal_id=whole_loop_seal.seal_id,
        whole_loop_seal_sha256=seal_sha,
        outcome_id=outcome.outcome_id,
        outcome_sha256=outcome_sha,
        evidence_id=evidence.evidence_id,
        evidence_sha256=evidence.sha256(),
    )


def plan_restart_continuation_from_sources(
    evidence: PersistedRestartEvidence,
    *,
    plan_id: str,
    expected_evidence_sha256: str,
    causal_identity: CausalIdentity,
    unifieddb_authority: UnifiedDBAuthorityRef,
    source_checkpoint: PersistentAgencyCheckpoint,
    whole_loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
) -> RestartContinuationPlan:
    """Canonical G3 component boundary: bind typed sources, then call accepted G2 planner.

    The accepted G2 planner is deliberately invoked only after the source binding succeeds.
    Its expected checkpoint/seal values are derived from concrete source objects here, not
    accepted as a second caller-controlled identity set.
    """
    binding = bind_restart_sources(
        evidence,
        causal_identity=causal_identity,
        unifieddb_authority=unifieddb_authority,
        source_checkpoint=source_checkpoint,
        whole_loop_seal=whole_loop_seal,
        outcome=outcome,
    )
    if expected_evidence_sha256 != binding.evidence_sha256:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_EXPECTED_EVIDENCE_DIGEST_MISMATCH"
        )

    plan = plan_restart_continuation(
        evidence,
        plan_id=plan_id,
        expected_evidence_sha256=binding.evidence_sha256,
        expected_checkpoint_id=binding.checkpoint_id,
        expected_checkpoint_generation=binding.checkpoint_generation,
        expected_checkpoint_sha256=binding.checkpoint_sha256,
        expected_whole_loop_seal_id=binding.whole_loop_seal_id,
        expected_whole_loop_seal_sha256=binding.whole_loop_seal_sha256,
    )

    causal_ref = causal_identity_ref(causal_identity)
    if causal_ref not in plan.provenance_refs:
        raise RestartSourceAuthenticationError(
            "SOURCE_AUTH_PLAN_CAUSAL_REF_MISSING"
        )
    return plan


__all__ = [
    "RestartSourceAuthenticationError",
    "RestartSourceBinding",
    "SOURCE_BINDING_CLASSIFICATION",
    "SOURCE_BINDING_SCHEMA",
    "bind_restart_sources",
    "causal_identity_ref",
    "plan_restart_continuation_from_sources",
]
