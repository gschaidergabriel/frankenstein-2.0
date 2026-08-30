"""Typed source-binding candidate for F2-WP-901 restart/recovery.

REVIEW_ONLY candidate. This module does not claim canonical WP901 mutation authority.

The accepted WP901 generation-2 planner intentionally remains unchanged. This adapter
addresses two executed review falsifiers without inflating evidence scope:

* caller-mirrored checkpoint / whole-loop identities must not authenticate themselves;
* a restart plan must not silently bridge a checkpoint and whole-loop seal from different
  direct-successor lineages.

The adapter therefore requires concrete typed WP206/WP900 source objects, binds the WP900
outcome object as well, checks the direct-successor relationship, derives a deterministic
lineage digest from those source objects, and only then delegates disposition calculation to
the accepted generation-2 planner. The emitted object is still a candidate control projection:
it has no scheduler, persistence, truth, effect, completion, runtime or whole-system authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, ClassVar

from .persistent_agency_kernel import PersistentAgencyCheckpoint
from .restart_recovery_continuation import (
    PersistedRestartEvidence,
    RestartContinuationPlan,
    RestartRecoveryError,
    plan_restart_continuation,
)
from .whole_persistent_loop import LoopOutcomeEvidence, WholePersistentLoopSeal


SOURCE_BINDING_SCHEMA = "FRANKENSTEIN2_RESTART_RECOVERY_SOURCE_BINDING/v1"
SOURCE_BOUND_PLAN_SCHEMA = "FRANKENSTEIN2_RESTART_RECOVERY_SOURCE_BOUND_PLAN/v1"
SOURCE_BINDING_CLASSIFICATION = (
    "TYPED_SOURCE_BOUND_RECOVERY_INPUT_NOT_PERSISTENCE_TRUTH_EFFECT_COMPLETION_OR_RUNTIME_AUTHORITY"
)
SOURCE_BOUND_PLAN_CLASSIFICATION = (
    "DETERMINISTIC_SOURCE_BOUND_RESTART_CANDIDATE_NOT_SCHEDULER_PERSISTENCE_TRUTH_EFFECT_COMPLETION_OR_RUNTIME_AUTHORITY"
)


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RestartRecoveryError("source binding must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class RestartSourceBinding:
    """Validated typed source chain consumed by source-bound restart planning.

    Construction is public only so the object can cross process/test boundaries. Its
    __post_init__ reruns every binding invariant; callers cannot opt out by supplying a
    precomputed `validated=True` bit.
    """

    evidence: PersistedRestartEvidence
    checkpoint: PersistentAgencyCheckpoint
    whole_loop_seal: WholePersistentLoopSeal
    outcome: LoopOutcomeEvidence

    schema: ClassVar[str] = SOURCE_BINDING_SCHEMA
    classification: ClassVar[str] = SOURCE_BINDING_CLASSIFICATION

    def __post_init__(self) -> None:
        if type(self.evidence) is not PersistedRestartEvidence:
            raise RestartRecoveryError(
                "RECOVERY_SOURCE_EVIDENCE_MUST_BE_CONCRETE_PERSISTED_RESTART_EVIDENCE"
            )
        if type(self.checkpoint) is not PersistentAgencyCheckpoint:
            raise RestartRecoveryError(
                "RECOVERY_SOURCE_CHECKPOINT_MUST_BE_CONCRETE_WP206_CHECKPOINT"
            )
        if type(self.whole_loop_seal) is not WholePersistentLoopSeal:
            raise RestartRecoveryError(
                "RECOVERY_SOURCE_SEAL_MUST_BE_CONCRETE_WP900_WHOLE_LOOP_SEAL"
            )
        if type(self.outcome) is not LoopOutcomeEvidence:
            raise RestartRecoveryError(
                "RECOVERY_SOURCE_OUTCOME_MUST_BE_CONCRETE_WP900_OUTCOME"
            )

        checkpoint_sha = self.checkpoint.sha256()
        seal_sha = self.whole_loop_seal.sha256()
        outcome_sha = self.outcome.sha256()

        if self.evidence.source_checkpoint_id != self.checkpoint.checkpoint_id:
            raise RestartRecoveryError("RECOVERY_SOURCE_CHECKPOINT_ID_MISMATCH")
        if self.evidence.source_checkpoint_generation != self.checkpoint.generation:
            raise RestartRecoveryError("RECOVERY_SOURCE_CHECKPOINT_GENERATION_MISMATCH")
        if self.evidence.source_checkpoint_sha256 != checkpoint_sha:
            raise RestartRecoveryError("RECOVERY_SOURCE_CHECKPOINT_DIGEST_MISMATCH")

        if self.evidence.whole_loop_seal_id != self.whole_loop_seal.seal_id:
            raise RestartRecoveryError("RECOVERY_SOURCE_WHOLE_LOOP_SEAL_ID_MISMATCH")
        if self.evidence.whole_loop_seal_sha256 != seal_sha:
            raise RestartRecoveryError("RECOVERY_SOURCE_WHOLE_LOOP_SEAL_DIGEST_MISMATCH")

        if self.whole_loop_seal.next_checkpoint_id != self.checkpoint.checkpoint_id:
            raise RestartRecoveryError("RECOVERY_SOURCE_SEAL_NEXT_CHECKPOINT_ID_MISMATCH")
        if self.whole_loop_seal.next_checkpoint_sha256 != checkpoint_sha:
            raise RestartRecoveryError("RECOVERY_SOURCE_SEAL_NEXT_CHECKPOINT_DIGEST_MISMATCH")
        if self.checkpoint.previous_checkpoint_id != self.whole_loop_seal.current_checkpoint_id:
            raise RestartRecoveryError("RECOVERY_SOURCE_CAUSAL_LINEAGE_MISMATCH")
        if self.checkpoint.generation != self.whole_loop_seal.generation + 1:
            raise RestartRecoveryError("RECOVERY_SOURCE_DIRECT_SUCCESSOR_GENERATION_MISMATCH")

        if self.whole_loop_seal.outcome_id != self.outcome.outcome_id:
            raise RestartRecoveryError("RECOVERY_SOURCE_OUTCOME_ID_MISMATCH")
        if self.whole_loop_seal.outcome_sha256 != outcome_sha:
            raise RestartRecoveryError("RECOVERY_SOURCE_SEAL_OUTCOME_DIGEST_MISMATCH")
        if self.evidence.outcome_sha256 != outcome_sha:
            raise RestartRecoveryError("RECOVERY_SOURCE_EVIDENCE_OUTCOME_DIGEST_MISMATCH")
        if self.evidence.outcome_status != self.outcome.status:
            raise RestartRecoveryError("RECOVERY_SOURCE_OUTCOME_STATUS_MISMATCH")

    @property
    def checkpoint_sha256(self) -> str:
        return self.checkpoint.sha256()

    @property
    def whole_loop_seal_sha256(self) -> str:
        return self.whole_loop_seal.sha256()

    @property
    def outcome_sha256(self) -> str:
        return self.outcome.sha256()

    @property
    def causal_lineage_sha256(self) -> str:
        """Replay-stable lineage witness derived from concrete source object identities."""
        return _digest(
            {
                "schema": "FRANKENSTEIN2_RESTART_CAUSAL_LINEAGE/v1",
                "whole_loop_generation": self.whole_loop_seal.generation,
                "previous_checkpoint_id": self.whole_loop_seal.current_checkpoint_id,
                "previous_checkpoint_sha256": self.whole_loop_seal.current_checkpoint_sha256,
                "whole_loop_seal_id": self.whole_loop_seal.seal_id,
                "whole_loop_seal_sha256": self.whole_loop_seal_sha256,
                "outcome_id": self.outcome.outcome_id,
                "outcome_sha256": self.outcome_sha256,
                "source_checkpoint_id": self.checkpoint.checkpoint_id,
                "source_checkpoint_generation": self.checkpoint.generation,
                "source_checkpoint_sha256": self.checkpoint_sha256,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "evidence_id": self.evidence.evidence_id,
            "evidence_sha256": self.evidence.sha256(),
            "source_checkpoint_id": self.checkpoint.checkpoint_id,
            "source_checkpoint_generation": self.checkpoint.generation,
            "source_checkpoint_sha256": self.checkpoint_sha256,
            "whole_loop_seal_id": self.whole_loop_seal.seal_id,
            "whole_loop_seal_sha256": self.whole_loop_seal_sha256,
            "outcome_id": self.outcome.outcome_id,
            "outcome_status": self.outcome.status,
            "outcome_sha256": self.outcome_sha256,
            "causal_lineage_sha256": self.causal_lineage_sha256,
            "scheduler_authority": "NONE",
            "persistence_authority": "NONE",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "runtime_credit": 0,
            "whole_system_acceptance": False,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceBoundRestartContinuationPlan:
    source_binding_sha256: str
    causal_lineage_sha256: str
    base_plan: RestartContinuationPlan

    schema: ClassVar[str] = SOURCE_BOUND_PLAN_SCHEMA
    classification: ClassVar[str] = SOURCE_BOUND_PLAN_CLASSIFICATION

    def __post_init__(self) -> None:
        if type(self.source_binding_sha256) is not str or len(self.source_binding_sha256) != 64:
            raise RestartRecoveryError("source_binding_sha256 must be lowercase SHA-256")
        if any(ch not in "0123456789abcdef" for ch in self.source_binding_sha256):
            raise RestartRecoveryError("source_binding_sha256 must be lowercase SHA-256")
        if type(self.causal_lineage_sha256) is not str or len(self.causal_lineage_sha256) != 64:
            raise RestartRecoveryError("causal_lineage_sha256 must be lowercase SHA-256")
        if any(ch not in "0123456789abcdef" for ch in self.causal_lineage_sha256):
            raise RestartRecoveryError("causal_lineage_sha256 must be lowercase SHA-256")
        if type(self.base_plan) is not RestartContinuationPlan:
            raise RestartRecoveryError("base_plan must be concrete RestartContinuationPlan")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "source_binding_sha256": self.source_binding_sha256,
            "causal_lineage_sha256": self.causal_lineage_sha256,
            "base_plan": self.base_plan.as_dict(),
            "scheduler_authority": "NONE",
            "persistence_authority": "NONE",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "runtime_credit": 0,
            "whole_system_acceptance": False,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_restart_sources(
    *,
    evidence: PersistedRestartEvidence,
    checkpoint: PersistentAgencyCheckpoint,
    whole_loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
) -> RestartSourceBinding:
    """Validate concrete source objects before any restart disposition is produced."""
    return RestartSourceBinding(
        evidence=evidence,
        checkpoint=checkpoint,
        whole_loop_seal=whole_loop_seal,
        outcome=outcome,
    )


def plan_source_bound_restart_continuation(
    binding: RestartSourceBinding,
    *,
    plan_id: str,
) -> SourceBoundRestartContinuationPlan:
    """Plan from typed bound sources; callers cannot mirror raw expected identities."""
    if type(binding) is not RestartSourceBinding:
        raise RestartRecoveryError("binding must be concrete RestartSourceBinding")

    # Reconstructing the binding reruns all source checks at the planning boundary so a
    # stale/mutated surrogate cannot bypass validation merely by retaining old digests.
    checked = RestartSourceBinding(
        evidence=binding.evidence,
        checkpoint=binding.checkpoint,
        whole_loop_seal=binding.whole_loop_seal,
        outcome=binding.outcome,
    )

    base = plan_restart_continuation(
        checked.evidence,
        plan_id=plan_id,
        expected_evidence_sha256=checked.evidence.sha256(),
        expected_checkpoint_id=checked.checkpoint.checkpoint_id,
        expected_checkpoint_generation=checked.checkpoint.generation,
        expected_checkpoint_sha256=checked.checkpoint_sha256,
        expected_whole_loop_seal_id=checked.whole_loop_seal.seal_id,
        expected_whole_loop_seal_sha256=checked.whole_loop_seal_sha256,
    )
    return SourceBoundRestartContinuationPlan(
        source_binding_sha256=checked.sha256(),
        causal_lineage_sha256=checked.causal_lineage_sha256,
        base_plan=base,
    )


__all__ = [
    "RestartSourceBinding",
    "SOURCE_BINDING_SCHEMA",
    "SOURCE_BOUND_PLAN_SCHEMA",
    "SourceBoundRestartContinuationPlan",
    "bind_restart_sources",
    "plan_source_bound_restart_continuation",
]
