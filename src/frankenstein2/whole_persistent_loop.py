"""Fail-closed whole persistent loop integration seal for Frankenstein 2.0.

F2-WP-900 generation 1 repository-component scope only.

This module does not schedule work, call models/providers/tools, execute effects, infer
world truth, or mint completion. It binds already-typed component evidence into one
direct-successor persistence cycle:

    PersistentAgencyCheckpoint
      -> SituationFrame
      -> CycleContract
      -> GRID10 plan
      -> GWT causal-path seal
      -> deterministic decision proposal
      -> typed effect/outcome evidence
      -> direct-successor PersistentAgencyCheckpoint

Positive admission requires exact identity/digest/generation closure plus explicit
re-entry references persisted in the successor checkpoint. The WP510 GWT seal is
revalidated from its concrete source evidence before it may contribute to a positive
whole-loop seal. UNKNOWN or non-causal GWT paths remain non-positive and cannot be
silently upgraded into causal closure.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar, Iterable

from state.execution_completion import ExecutionStage

from .deferred_execution_verification import DeferredExecutionVerificationTarget
from .direct_delegate_router import RouteCandidate
from .effect_invocation_correlation import EffectCallBinding, EffectCorrelationStage
from .epistemic_action_selection import EpistemicSelectionProposal
from .grid10_interface import Grid10Plan
from .gwt_causal_path import (
    GwtCausalPathError,
    GwtCausalPathSeal,
    ReentryEvidenceBundle,
    validate_gwt_causal_path_seal,
)
from .gwt_uptake import (
    CausalInfluenceResult,
    CausalProbeArm,
    CellUptakeReceipt,
    UptakeSummary,
)
from .gwt_workspace import BroadcastEnvelope, WorkspaceSelection
from .persistent_agency_kernel import (
    PersistentAgencyCheckpoint,
    PersistentAgencyError,
    selected_fingerprint_change,
)
from .situation_frame import CycleContract, SituationFrame, SituationFrameError


WHOLE_LOOP_SEAL_SCHEMA = "FRANKENSTEIN2_WHOLE_PERSISTENT_LOOP_SEAL/v1"
LOOP_OUTCOME_SCHEMA = "FRANKENSTEIN2_WHOLE_LOOP_OUTCOME/v1"
CLASSIFICATION = (
    "DERIVED_CAUSAL_PERSISTENCE_SEAL_NOT_SCHEDULER_EFFECT_TRUTH_OR_COMPLETION_AUTHORITY"
)
OUTCOME_CLASSIFICATION = (
    "TYPED_LOOP_OUTCOME_EVIDENCE_NOT_WORLD_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"
)

NO_EFFECT = "NO_EFFECT"
EFFECT_RESULT_OBSERVED = "EFFECT_RESULT_OBSERVED"
EFFECT_VERIFIED_APPLIED = "EFFECT_VERIFIED_APPLIED"
EFFECT_VERIFIED_NOT_APPLIED = "EFFECT_VERIFIED_NOT_APPLIED"
EFFECT_OUTCOME_UNKNOWN = "EFFECT_OUTCOME_UNKNOWN"
_OUTCOME_STATUSES = frozenset(
    {
        NO_EFFECT,
        EFFECT_RESULT_OBSERVED,
        EFFECT_VERIFIED_APPLIED,
        EFFECT_VERIFIED_NOT_APPLIED,
        EFFECT_OUTCOME_UNKNOWN,
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_REFS = 4096
_POSITIVE_GWT_PATH_STATUS = "CONTRACT_SCOPE_CAUSAL_PATH_SEALED"
_POSITIVE_GWT_CAUSAL_STATUS = "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"


class WholePersistentLoopError(ValueError):
    """Fail-closed F2-WP-900 integration error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str:
        raise WholePersistentLoopError(f"{name} must be exact concrete string")
    if not value or value != value.strip():
        raise WholePersistentLoopError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise WholePersistentLoopError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise WholePersistentLoopError(f"{name} contains control characters")
    return value


def _sha256_text(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise WholePersistentLoopError(
            f"{name} must be exact concrete lowercase 64-hex SHA-256"
        )
    return value


def _refs(name: str, values: Iterable[str], *, require_nonempty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise WholePersistentLoopError(f"{name} must be an iterable of reference strings")
    refs = tuple(_text(f"{name} item", item) for item in values)
    if require_nonempty and not refs:
        raise WholePersistentLoopError(f"{name} must not be empty")
    if len(refs) > _MAX_REFS:
        raise WholePersistentLoopError(f"{name} exceeds {_MAX_REFS} items")
    if len(set(refs)) != len(refs):
        raise WholePersistentLoopError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


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
        raise WholePersistentLoopError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def checkpoint_ref(checkpoint: PersistentAgencyCheckpoint) -> str:
    if type(checkpoint) is not PersistentAgencyCheckpoint:
        raise WholePersistentLoopError(
            "checkpoint_ref requires concrete PersistentAgencyCheckpoint"
        )
    return f"wp900:checkpoint:{checkpoint.checkpoint_id}:{checkpoint.sha256()}"


def frame_ref(frame: SituationFrame) -> str:
    if type(frame) is not SituationFrame:
        raise WholePersistentLoopError("frame_ref requires concrete SituationFrame")
    return f"wp900:frame:{frame.frame_id}:{frame.sha256()}"


def contract_ref(contract: CycleContract) -> str:
    if type(contract) is not CycleContract:
        raise WholePersistentLoopError("contract_ref requires concrete CycleContract")
    return f"wp900:contract:{contract.contract_id}:{contract.sha256()}"


def plan_ref(plan: Grid10Plan) -> str:
    if type(plan) is not Grid10Plan:
        raise WholePersistentLoopError("plan_ref requires concrete Grid10Plan")
    return f"wp900:grid10:{plan.plan_id}:{plan.sha256()}"


def gwt_ref(gwt_seal: GwtCausalPathSeal) -> str:
    if type(gwt_seal) is not GwtCausalPathSeal:
        raise WholePersistentLoopError("gwt_ref requires concrete GwtCausalPathSeal")
    return f"wp900:gwt:{gwt_seal.seal_id}:{gwt_seal.sha256()}"


@dataclass(frozen=True, slots=True, kw_only=True)
class GwtCausalValidationEvidence:
    """Concrete WP510 source objects required to revalidate one GWT causal seal.

    The object is deliberately persistence-agnostic and contains no authority bit. The
    public WP510 validator reconstructs the seal from these exact source objects; merely
    carrying a GwtCausalPathSeal digest or factory marker is insufficient at the WP900
    consumer boundary.
    """

    selection: WorkspaceSelection
    broadcast: BroadcastEnvelope
    receipts: tuple[CellUptakeReceipt, ...]
    uptake_summary: UptakeSummary
    intervention: CausalProbeArm
    control: CausalProbeArm
    causal_result: CausalInfluenceResult
    reentry_bundles: tuple[ReentryEvidenceBundle, ...]

    def validate(self, *, seal: GwtCausalPathSeal, plan: Grid10Plan) -> None:
        try:
            validate_gwt_causal_path_seal(
                seal,
                plan=plan,
                selection=self.selection,
                broadcast=self.broadcast,
                receipts=self.receipts,
                uptake_summary=self.uptake_summary,
                intervention=self.intervention,
                control=self.control,
                causal_result=self.causal_result,
                reentry_bundles=self.reentry_bundles,
            )
        except (GwtCausalPathError, TypeError, ValueError) as exc:
            raise WholePersistentLoopError(
                f"GWT causal-path source lineage rejected: {exc}"
            ) from exc


def _assert_effect_target_match(
    effect_call: EffectCallBinding,
    target: DeferredExecutionVerificationTarget,
) -> None:
    if type(target) is not DeferredExecutionVerificationTarget:
        raise WholePersistentLoopError(
            "verification_target must be concrete DeferredExecutionVerificationTarget"
        )
    binding = target.returned.binding
    expected = {
        "return_id": target.returned.return_id,
        "binding_id": binding.binding_id(),
        "invocation_id": binding.invocation_id,
        "tool_use_id": binding.tool_use_id,
        "delegation_id": binding.delegation_id,
        "child_identity_sha256": binding.child.sha256(),
        "result_id": binding.result_id,
        "result_sha256": binding.result_sha256,
    }
    actual = {
        "return_id": effect_call.return_id,
        "binding_id": effect_call.binding_id,
        "invocation_id": effect_call.invocation_id,
        "tool_use_id": effect_call.tool_use_id,
        "delegation_id": effect_call.delegation_id,
        "child_identity_sha256": effect_call.child_identity_sha256,
        "result_id": effect_call.result_id,
        "result_sha256": effect_call.result_sha256,
    }
    for name, expected_value in expected.items():
        if actual[name] != expected_value:
            raise WholePersistentLoopError(
                f"effect verification target {name} mismatch"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class LoopOutcomeEvidence:
    """Typed effect/outcome evidence admitted for persistence re-entry.

    UNKNOWN deliberately remains UNKNOWN. A result observation is not automatically a
    verified world outcome. Final APPLIED / NOT_APPLIED status is accepted only from an
    already-correlated WP-105 verification target.
    """

    outcome_id: str
    status: str
    effect_call: EffectCallBinding | None = None
    verification_target: DeferredExecutionVerificationTarget | None = None
    unknown_reason_ref: str | None = None
    provenance_refs: tuple[str, ...] = ()

    schema: ClassVar[str] = LOOP_OUTCOME_SCHEMA
    classification: ClassVar[str] = OUTCOME_CLASSIFICATION

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome_id", _text("outcome_id", self.outcome_id))
        if type(self.status) is not str or self.status not in _OUTCOME_STATUSES:
            raise WholePersistentLoopError("unsupported loop outcome status")
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs, require_nonempty=True),
        )

        if self.status == NO_EFFECT:
            if (
                self.effect_call is not None
                or self.verification_target is not None
                or self.unknown_reason_ref is not None
            ):
                raise WholePersistentLoopError(
                    "NO_EFFECT cannot carry effect/verification/unknown evidence"
                )
            return

        if type(self.effect_call) is not EffectCallBinding:
            raise WholePersistentLoopError(
                "effect outcome requires concrete EffectCallBinding"
            )

        if self.status == EFFECT_OUTCOME_UNKNOWN:
            if self.effect_call.stage is not EffectCorrelationStage.PREPARED:
                raise WholePersistentLoopError(
                    "UNKNOWN outcome requires result-free PREPARED effect binding"
                )
            if self.verification_target is not None:
                raise WholePersistentLoopError(
                    "UNKNOWN outcome cannot carry verification target"
                )
            object.__setattr__(
                self,
                "unknown_reason_ref",
                _text("unknown_reason_ref", self.unknown_reason_ref),
            )
            return

        if self.effect_call.stage is not EffectCorrelationStage.RESULT_OBSERVED:
            raise WholePersistentLoopError(
                "observed/verified outcome requires RESULT_OBSERVED effect binding"
            )
        if self.effect_call.result_id is None or self.effect_call.result_sha256 is None:
            raise WholePersistentLoopError("observed effect result identity is incomplete")
        if self.unknown_reason_ref is not None:
            raise WholePersistentLoopError(
                "observed/verified outcome cannot also be UNKNOWN"
            )

        if self.status == EFFECT_RESULT_OBSERVED:
            if self.verification_target is not None:
                _assert_effect_target_match(self.effect_call, self.verification_target)
            return

        if type(self.verification_target) is not DeferredExecutionVerificationTarget:
            raise WholePersistentLoopError(
                "verified outcome requires DeferredExecutionVerificationTarget"
            )
        _assert_effect_target_match(self.effect_call, self.verification_target)
        expected_stage = (
            ExecutionStage.VERIFIED_APPLIED
            if self.status == EFFECT_VERIFIED_APPLIED
            else ExecutionStage.VERIFIED_NOT_APPLIED
        )
        if self.verification_target.lineage.stage is not expected_stage:
            raise WholePersistentLoopError(
                "verified outcome status does not match WP-105 lineage stage"
            )

    def as_dict(self) -> dict[str, Any]:
        effect: dict[str, Any] | None = None
        if self.effect_call is not None:
            effect = {
                "effect_id": self.effect_call.effect_id,
                "return_id": self.effect_call.return_id,
                "binding_id": self.effect_call.binding_id,
                "invocation_id": self.effect_call.invocation_id,
                "tool_use_id": self.effect_call.tool_use_id,
                "delegation_id": self.effect_call.delegation_id,
                "child_identity_sha256": self.effect_call.child_identity_sha256,
                "stage": self.effect_call.stage.value,
                "request_sha256": self.effect_call.request_sha256,
                "result_id": self.effect_call.result_id,
                "result_sha256": self.effect_call.result_sha256,
            }
        verification: dict[str, Any] | None = None
        if self.verification_target is not None:
            verification = {
                "return_id": self.verification_target.returned.return_id,
                "causal_id": self.verification_target.lineage.causal_id,
                "generation": self.verification_target.lineage.generation,
                "stage": self.verification_target.lineage.stage.value,
            }
        return {
            "schema": self.schema,
            "classification": self.classification,
            "outcome_id": self.outcome_id,
            "status": self.status,
            "effect": effect,
            "verification": verification,
            "unknown_reason_ref": self.unknown_reason_ref,
            "provenance_refs": list(self.provenance_refs),
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def outcome_ref(outcome: LoopOutcomeEvidence) -> str:
    if type(outcome) is not LoopOutcomeEvidence:
        raise WholePersistentLoopError(
            "outcome_ref requires concrete LoopOutcomeEvidence"
        )
    return f"wp900:outcome:{outcome.outcome_id}:{outcome.sha256()}"


def _decision_identity(
    decision: RouteCandidate | EpistemicSelectionProposal,
    *,
    contract: CycleContract,
    plan: Grid10Plan,
) -> tuple[str, str, str]:
    if type(decision) is RouteCandidate:
        if decision.cycle_contract_id != contract.contract_id:
            raise WholePersistentLoopError("route decision cycle contract id mismatch")
        if decision.cycle_generation != contract.cycle_generation:
            raise WholePersistentLoopError(
                "route decision cycle contract generation mismatch"
            )
        if decision.cycle_contract_sha256 != contract.sha256():
            raise WholePersistentLoopError(
                "route decision cycle contract digest mismatch"
            )
        return "ROUTE", decision.candidate_id, decision.sha256()

    if type(decision) is EpistemicSelectionProposal:
        if decision.grid_plan_id != plan.plan_id:
            raise WholePersistentLoopError("epistemic decision GRID10 plan id mismatch")
        if decision.grid_plan_generation != plan.generation:
            raise WholePersistentLoopError(
                "epistemic decision GRID10 plan generation mismatch"
            )
        if decision.grid_plan_sha256 != plan.sha256():
            raise WholePersistentLoopError(
                "epistemic decision GRID10 plan digest mismatch"
            )
        if decision.policy_id != plan.policy_id:
            raise WholePersistentLoopError("epistemic decision policy id mismatch")
        if decision.policy_generation != plan.policy_generation:
            raise WholePersistentLoopError(
                "epistemic decision policy generation mismatch"
            )
        if decision.policy_sha256 != plan.policy_sha256:
            raise WholePersistentLoopError(
                "epistemic decision policy digest mismatch"
            )
        return "EPISTEMIC", decision.proposal_id, decision.sha256()

    raise WholePersistentLoopError(
        "decision must be concrete RouteCandidate or EpistemicSelectionProposal"
    )


def decision_ref(
    decision: RouteCandidate | EpistemicSelectionProposal,
    *,
    contract: CycleContract,
    plan: Grid10Plan,
) -> str:
    kind, decision_id, sha256 = _decision_identity(
        decision,
        contract=contract,
        plan=plan,
    )
    return f"wp900:decision:{kind}:{decision_id}:{sha256}"


def required_reentry_refs(
    *,
    current_checkpoint: PersistentAgencyCheckpoint,
    frame: SituationFrame,
    contract: CycleContract,
    plan: Grid10Plan,
    gwt_seal: GwtCausalPathSeal,
    decision: RouteCandidate | EpistemicSelectionProposal,
    outcome: LoopOutcomeEvidence,
) -> tuple[str, ...]:
    """Return exact lineage refs that a successor checkpoint must persist."""
    refs = (
        checkpoint_ref(current_checkpoint),
        frame_ref(frame),
        contract_ref(contract),
        plan_ref(plan),
        gwt_ref(gwt_seal),
        decision_ref(decision, contract=contract, plan=plan),
        outcome_ref(outcome),
    )
    return tuple(sorted(refs))


@dataclass(frozen=True, slots=True, kw_only=True)
class WholePersistentLoopSeal:
    seal_id: str
    generation: int
    current_checkpoint_id: str
    current_checkpoint_sha256: str
    frame_id: str
    frame_sha256: str
    contract_id: str
    contract_sha256: str
    grid_plan_id: str
    grid_plan_sha256: str
    gwt_seal_id: str
    gwt_seal_sha256: str
    decision_kind: str
    decision_id: str
    decision_sha256: str
    outcome_id: str
    outcome_sha256: str
    next_checkpoint_id: str
    next_checkpoint_sha256: str
    reentry_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = WHOLE_LOOP_SEAL_SCHEMA
    classification: ClassVar[str] = CLASSIFICATION

    def __post_init__(self) -> None:
        for name in (
            "seal_id",
            "current_checkpoint_id",
            "frame_id",
            "contract_id",
            "grid_plan_id",
            "gwt_seal_id",
            "decision_kind",
            "decision_id",
            "outcome_id",
            "next_checkpoint_id",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if type(self.generation) is not int or self.generation < 0:
            raise WholePersistentLoopError(
                "generation must be a non-negative integer"
            )
        for name in (
            "current_checkpoint_sha256",
            "frame_sha256",
            "contract_sha256",
            "grid_plan_sha256",
            "gwt_seal_sha256",
            "decision_sha256",
            "outcome_sha256",
            "next_checkpoint_sha256",
        ):
            object.__setattr__(
                self, name, _sha256_text(name, getattr(self, name))
            )
        if self.decision_kind not in {"ROUTE", "EPISTEMIC"}:
            raise WholePersistentLoopError("unsupported decision_kind")
        object.__setattr__(
            self,
            "reentry_refs",
            _refs("reentry_refs", self.reentry_refs, require_nonempty=True),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs, require_nonempty=True),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "seal_id": self.seal_id,
            "generation": self.generation,
            "current_checkpoint_id": self.current_checkpoint_id,
            "current_checkpoint_sha256": self.current_checkpoint_sha256,
            "frame_id": self.frame_id,
            "frame_sha256": self.frame_sha256,
            "contract_id": self.contract_id,
            "contract_sha256": self.contract_sha256,
            "grid_plan_id": self.grid_plan_id,
            "grid_plan_sha256": self.grid_plan_sha256,
            "gwt_seal_id": self.gwt_seal_id,
            "gwt_seal_sha256": self.gwt_seal_sha256,
            "decision_kind": self.decision_kind,
            "decision_id": self.decision_id,
            "decision_sha256": self.decision_sha256,
            "outcome_id": self.outcome_id,
            "outcome_sha256": self.outcome_sha256,
            "next_checkpoint_id": self.next_checkpoint_id,
            "next_checkpoint_sha256": self.next_checkpoint_sha256,
            "reentry_refs": list(self.reentry_refs),
            "provenance_refs": list(self.provenance_refs),
            "truth_authority": "NONE",
            "scheduler_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "runtime_credit": 0,
            "physical_grid10_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "training_credit": 0,
            "whole_system_acceptance": False,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def seal_whole_persistent_loop(
    *,
    seal_id: str,
    generation: int,
    current_checkpoint: PersistentAgencyCheckpoint,
    frame: SituationFrame,
    contract: CycleContract,
    plan: Grid10Plan,
    gwt_seal: GwtCausalPathSeal,
    gwt_evidence: GwtCausalValidationEvidence,
    decision: RouteCandidate | EpistemicSelectionProposal,
    outcome: LoopOutcomeEvidence,
    next_checkpoint: PersistentAgencyCheckpoint,
    provenance_refs: Iterable[str],
) -> WholePersistentLoopSeal:
    """Revalidate one direct-successor persistence cycle without executing anything."""
    if type(generation) is not int or generation < 0:
        raise WholePersistentLoopError(
            "generation must be a non-negative integer"
        )
    if type(current_checkpoint) is not PersistentAgencyCheckpoint:
        raise WholePersistentLoopError(
            "current_checkpoint must be concrete PersistentAgencyCheckpoint"
        )
    if type(frame) is not SituationFrame:
        raise WholePersistentLoopError("frame must be concrete SituationFrame")
    if type(contract) is not CycleContract:
        raise WholePersistentLoopError("contract must be concrete CycleContract")
    if type(plan) is not Grid10Plan:
        raise WholePersistentLoopError("plan must be concrete Grid10Plan")
    if type(gwt_seal) is not GwtCausalPathSeal:
        raise WholePersistentLoopError("gwt_seal must be concrete GwtCausalPathSeal")
    if type(gwt_evidence) is not GwtCausalValidationEvidence:
        raise WholePersistentLoopError(
            "gwt_evidence must be concrete GwtCausalValidationEvidence"
        )
    if type(outcome) is not LoopOutcomeEvidence:
        raise WholePersistentLoopError("outcome must be concrete LoopOutcomeEvidence")
    if type(next_checkpoint) is not PersistentAgencyCheckpoint:
        raise WholePersistentLoopError(
            "next_checkpoint must be concrete PersistentAgencyCheckpoint"
        )

    if frame.agency_state_ref != current_checkpoint.agency_state.state_id:
        raise WholePersistentLoopError("frame AgencyState id mismatch")
    if frame.agency_state_generation != current_checkpoint.agency_state.generation:
        raise WholePersistentLoopError("frame AgencyState generation mismatch")
    if frame.agency_state_sha256 != current_checkpoint.agency_state.sha256():
        raise WholePersistentLoopError("frame AgencyState digest mismatch")
    if checkpoint_ref(current_checkpoint) not in frame.provenance_refs:
        raise WholePersistentLoopError(
            "frame lacks exact current-checkpoint provenance binding"
        )

    try:
        contract.assert_matches(frame)
    except SituationFrameError as exc:
        raise WholePersistentLoopError(
            f"cycle contract/frame binding rejected: {exc}"
        ) from exc
    if contract.cycle_generation != generation:
        raise WholePersistentLoopError("cycle contract generation mismatch")

    try:
        plan.assert_frame_binding(
            frame_id=frame.frame_id,
            generation=frame.generation,
            sha256=frame.sha256(),
        )
    except Exception as exc:
        raise WholePersistentLoopError(
            f"GRID10 plan/frame binding rejected: {exc}"
        ) from exc
    if plan.cycle_id != contract.cycle_id:
        raise WholePersistentLoopError("GRID10 plan/cycle contract cycle_id mismatch")

    if gwt_seal.cycle_id != plan.cycle_id:
        raise WholePersistentLoopError("GWT seal cycle_id mismatch")
    if gwt_seal.plan_id != plan.plan_id:
        raise WholePersistentLoopError("GWT seal GRID10 plan id mismatch")
    if gwt_seal.plan_sha256 != plan.sha256():
        raise WholePersistentLoopError("GWT seal GRID10 plan digest mismatch")

    gwt_evidence.validate(seal=gwt_seal, plan=plan)
    if (
        gwt_seal.path_status != _POSITIVE_GWT_PATH_STATUS
        or gwt_seal.causal_status != _POSITIVE_GWT_CAUSAL_STATUS
    ):
        raise WholePersistentLoopError(
            "GWT causal path is not positive contract-scope causal closure; UNKNOWN/no-causal remains non-positive"
        )

    decision_kind, decision_id, decision_sha256 = _decision_identity(
        decision,
        contract=contract,
        plan=plan,
    )

    try:
        selected_fingerprint_change(current_checkpoint, next_checkpoint)
    except PersistentAgencyError as exc:
        raise WholePersistentLoopError(
            f"successor checkpoint lineage rejected: {exc}"
        ) from exc

    required_refs = required_reentry_refs(
        current_checkpoint=current_checkpoint,
        frame=frame,
        contract=contract,
        plan=plan,
        gwt_seal=gwt_seal,
        decision=decision,
        outcome=outcome,
    )
    missing = sorted(set(required_refs) - set(next_checkpoint.provenance_refs))
    if missing:
        raise WholePersistentLoopError(
            "successor checkpoint lacks exact loop re-entry refs: "
            + ", ".join(missing)
        )

    return WholePersistentLoopSeal(
        seal_id=seal_id,
        generation=generation,
        current_checkpoint_id=current_checkpoint.checkpoint_id,
        current_checkpoint_sha256=current_checkpoint.sha256(),
        frame_id=frame.frame_id,
        frame_sha256=frame.sha256(),
        contract_id=contract.contract_id,
        contract_sha256=contract.sha256(),
        grid_plan_id=plan.plan_id,
        grid_plan_sha256=plan.sha256(),
        gwt_seal_id=gwt_seal.seal_id,
        gwt_seal_sha256=gwt_seal.sha256(),
        decision_kind=decision_kind,
        decision_id=decision_id,
        decision_sha256=decision_sha256,
        outcome_id=outcome.outcome_id,
        outcome_sha256=outcome.sha256(),
        next_checkpoint_id=next_checkpoint.checkpoint_id,
        next_checkpoint_sha256=next_checkpoint.sha256(),
        reentry_refs=required_refs,
        provenance_refs=tuple(provenance_refs),
    )


__all__ = [
    "CLASSIFICATION",
    "EFFECT_OUTCOME_UNKNOWN",
    "EFFECT_RESULT_OBSERVED",
    "EFFECT_VERIFIED_APPLIED",
    "EFFECT_VERIFIED_NOT_APPLIED",
    "GwtCausalValidationEvidence",
    "LOOP_OUTCOME_SCHEMA",
    "LoopOutcomeEvidence",
    "NO_EFFECT",
    "OUTCOME_CLASSIFICATION",
    "WHOLE_LOOP_SEAL_SCHEMA",
    "WholePersistentLoopError",
    "WholePersistentLoopSeal",
    "checkpoint_ref",
    "contract_ref",
    "decision_ref",
    "frame_ref",
    "gwt_ref",
    "outcome_ref",
    "plan_ref",
    "required_reentry_refs",
    "seal_whole_persistent_loop",
]
