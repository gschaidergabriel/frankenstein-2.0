"""Deterministic epistemic-action selection for Frankenstein 2.0 Stage 5.

This module ranks already-bound Hyperposition discriminator candidates against an
exact GRID10 plan and emits a proposal only. A selected proposal is not an executed
action, world fact, effect authorization, completion claim, or policy authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

from .grid10_interface import Grid10InterfaceError, Grid10Plan
from .hyperposition import (
    DiscriminatorCandidate,
    Hyperposition,
    HyperpositionError,
    verify_hyperposition_binding,
)


EPISTEMIC_ACTION_CANDIDATE_SCHEMA = "FRANKENSTEIN2_EPISTEMIC_ACTION_CANDIDATE/v1"
EPISTEMIC_SELECTION_PROPOSAL_SCHEMA = "FRANKENSTEIN2_EPISTEMIC_SELECTION_PROPOSAL/v1"
SELECTION_RULE = (
    "MAX_EXPECTED_INFORMATION_GAIN_THEN_MIN_ESTIMATED_COST_THEN_MIN_WORK_UNITS_"
    "PRESERVE_TIES_THEN_LEXICOGRAPHIC_ID"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EpistemicActionSelectionError(ValueError):
    """Fail-closed validation error for epistemic selection structures."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EpistemicActionSelectionError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise EpistemicActionSelectionError(
            f"{name} must not contain leading or trailing whitespace"
        )
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise EpistemicActionSelectionError(f"{name} must not contain control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EpistemicActionSelectionError(f"{name} must be an integer >= 0")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise EpistemicActionSelectionError(
            f"{name} must be a lowercase sha256 hex digest"
        )
    return value


def _refs(name: str, value: Any, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise EpistemicActionSelectionError(f"{name} must be an immutable tuple")
    if not allow_empty and not value:
        raise EpistemicActionSelectionError(f"{name} must not be empty")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(set(refs)) != len(refs):
        raise EpistemicActionSelectionError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _work_units(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EpistemicActionSelectionError("work_units_requested must be an integer >= 0")
    return value


def _micros(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
        raise EpistemicActionSelectionError(f"{name} must be an integer in [0, 1000000]")
    return value


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
        raise EpistemicActionSelectionError(
            "value must be canonical-JSON encodable"
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class EpistemicActionCandidate:
    candidate_id: str
    action_ref: str
    cell_id: str
    work_units_requested: int
    discriminator: DiscriminatorCandidate
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = EPISTEMIC_ACTION_CANDIDATE_SCHEMA
    classification: ClassVar[str] = (
        "EPISTEMIC_ACTION_CANDIDATE_NOT_ACTION_EFFECT_OR_TRUTH_AUTHORITY"
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text("candidate_id", self.candidate_id))
        object.__setattr__(self, "action_ref", _text("action_ref", self.action_ref))
        object.__setattr__(self, "cell_id", _text("cell_id", self.cell_id))
        _work_units(self.work_units_requested)
        if type(self.discriminator) is not DiscriminatorCandidate:
            raise EpistemicActionSelectionError(
                "discriminator must be a concrete DiscriminatorCandidate"
            )
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )

    @property
    def expected_information_gain_micros(self) -> int:
        return self.discriminator.expected_information_gain_micros

    @property
    def estimated_cost_micros(self) -> int:
        return self.discriminator.estimated_cost_micros

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "candidate_id": self.candidate_id,
            "action_ref": self.action_ref,
            "cell_id": self.cell_id,
            "work_units_requested": self.work_units_requested,
            "discriminator_id": self.discriminator.discriminator_id,
            "discriminator_sha256": self.discriminator.sha256(),
            "expected_information_gain_micros": self.expected_information_gain_micros,
            "estimated_cost_micros": self.estimated_cost_micros,
            "provenance_refs": list(self.provenance_refs),
            "execution_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateAssessment:
    candidate_id: str
    eligible: bool
    reason: str
    expected_information_gain_micros: int
    estimated_cost_micros: int
    work_units_requested: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text("candidate_id", self.candidate_id))
        if not isinstance(self.eligible, bool):
            raise EpistemicActionSelectionError("eligible must be bool")
        object.__setattr__(self, "reason", _text("reason", self.reason))
        _micros(
            "expected_information_gain_micros",
            self.expected_information_gain_micros,
        )
        _micros("estimated_cost_micros", self.estimated_cost_micros)
        _work_units(self.work_units_requested)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "eligible": self.eligible,
            "reason": self.reason,
            "expected_information_gain_micros": self.expected_information_gain_micros,
            "estimated_cost_micros": self.estimated_cost_micros,
            "work_units_requested": self.work_units_requested,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class EpistemicSelectionProposal:
    proposal_id: str
    hyperposition_id: str
    hyperposition_generation: int
    hyperposition_sha256: str
    grid_plan_id: str
    grid_plan_generation: int
    grid_plan_sha256: str
    policy_id: str
    policy_generation: int
    policy_sha256: str
    selected_candidate_id: str | None
    selected_action_ref: str | None
    tied_candidate_ids: tuple[str, ...]
    assessments: tuple[CandidateAssessment, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = EPISTEMIC_SELECTION_PROPOSAL_SCHEMA
    classification: ClassVar[str] = (
        "EPISTEMIC_SELECTION_PROPOSAL_NOT_ACTION_EFFECT_COMPLETION_OR_TRUTH_AUTHORITY"
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _text("proposal_id", self.proposal_id))
        object.__setattr__(
            self, "hyperposition_id", _text("hyperposition_id", self.hyperposition_id)
        )
        _generation("hyperposition_generation", self.hyperposition_generation)
        _sha256("hyperposition_sha256", self.hyperposition_sha256)
        object.__setattr__(self, "grid_plan_id", _text("grid_plan_id", self.grid_plan_id))
        _generation("grid_plan_generation", self.grid_plan_generation)
        _sha256("grid_plan_sha256", self.grid_plan_sha256)
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _generation("policy_generation", self.policy_generation)
        _sha256("policy_sha256", self.policy_sha256)

        if (self.selected_candidate_id is None) != (self.selected_action_ref is None):
            raise EpistemicActionSelectionError(
                "selected_candidate_id and selected_action_ref must both be set or both be None"
            )
        if self.selected_candidate_id is not None:
            object.__setattr__(
                self,
                "selected_candidate_id",
                _text("selected_candidate_id", self.selected_candidate_id),
            )
            object.__setattr__(
                self,
                "selected_action_ref",
                _text("selected_action_ref", self.selected_action_ref),
            )

        object.__setattr__(
            self,
            "tied_candidate_ids",
            _refs("tied_candidate_ids", self.tied_candidate_ids, allow_empty=True),
        )
        if not isinstance(self.assessments, tuple):
            raise EpistemicActionSelectionError("assessments must be an immutable tuple")
        if not all(type(item) is CandidateAssessment for item in self.assessments):
            raise EpistemicActionSelectionError(
                "assessments must contain concrete CandidateAssessment values"
            )
        assessment_ids = [item.candidate_id for item in self.assessments]
        if len(set(assessment_ids)) != len(assessment_ids):
            raise EpistemicActionSelectionError("duplicate candidate assessment identity")
        object.__setattr__(
            self,
            "assessments",
            tuple(sorted(self.assessments, key=lambda item: item.candidate_id)),
        )
        by_id = {item.candidate_id: item for item in self.assessments}
        if self.selected_candidate_id is None:
            if self.tied_candidate_ids:
                raise EpistemicActionSelectionError(
                    "tied_candidate_ids must be empty when no candidate is selected"
                )
        else:
            selected = by_id.get(self.selected_candidate_id)
            if selected is None or not selected.eligible:
                raise EpistemicActionSelectionError("selected candidate must be eligible")
            if self.selected_candidate_id not in self.tied_candidate_ids:
                raise EpistemicActionSelectionError(
                    "selected candidate must be present in tied_candidate_ids"
                )
            for candidate_id in self.tied_candidate_ids:
                assessment = by_id.get(candidate_id)
                if assessment is None or not assessment.eligible:
                    raise EpistemicActionSelectionError(
                        "all tied candidates must be eligible assessments"
                    )
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )

    @property
    def status(self) -> str:
        return (
            "SELECTED_PROPOSAL"
            if self.selected_candidate_id is not None
            else "NO_ELIGIBLE_CANDIDATE"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "status": self.status,
            "selection_rule": SELECTION_RULE,
            "proposal_id": self.proposal_id,
            "hyperposition_id": self.hyperposition_id,
            "hyperposition_generation": self.hyperposition_generation,
            "hyperposition_sha256": self.hyperposition_sha256,
            "grid_plan_id": self.grid_plan_id,
            "grid_plan_generation": self.grid_plan_generation,
            "grid_plan_sha256": self.grid_plan_sha256,
            "policy_id": self.policy_id,
            "policy_generation": self.policy_generation,
            "policy_sha256": self.policy_sha256,
            "selected_candidate_id": self.selected_candidate_id,
            "selected_action_ref": self.selected_action_ref,
            "tied_candidate_ids": list(self.tied_candidate_ids),
            "assessments": [item.as_dict() for item in self.assessments],
            "execution_authority": "NONE",
            "effect_authority": "NONE",
            "truth_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _verify_plan_binding(
    plan: Grid10Plan,
    *,
    expected_plan_generation: int,
    expected_plan_sha256: str,
) -> None:
    if type(plan) is not Grid10Plan:
        raise EpistemicActionSelectionError("plan must be a concrete Grid10Plan")
    _generation("expected_plan_generation", expected_plan_generation)
    _sha256("expected_plan_sha256", expected_plan_sha256)
    if plan.generation != expected_plan_generation:
        raise EpistemicActionSelectionError("GRID10 plan generation mismatch")
    if plan.sha256() != expected_plan_sha256:
        raise EpistemicActionSelectionError("GRID10 plan digest mismatch")


def _verify_discriminator_binding(
    state: Hyperposition,
    discriminator: DiscriminatorCandidate,
) -> None:
    if discriminator.hyperposition_id != state.hyperposition_id:
        raise EpistemicActionSelectionError("discriminator Hyperposition id mismatch")
    if discriminator.hyperposition_generation != state.generation:
        raise EpistemicActionSelectionError(
            "discriminator Hyperposition generation mismatch"
        )
    if discriminator.hyperposition_sha256 != state.sha256():
        raise EpistemicActionSelectionError("discriminator Hyperposition digest mismatch")
    known = {item.alternative_id for item in state.alternatives}
    unknown = sorted(set(discriminator.target_alternative_ids) - known)
    if unknown:
        raise EpistemicActionSelectionError(
            "discriminator targets unknown Hyperposition alternatives: "
            + ", ".join(unknown)
        )


def select_epistemic_action(
    *,
    proposal_id: str,
    state: Hyperposition,
    expected_hyperposition_generation: int,
    expected_hyperposition_sha256: str,
    plan: Grid10Plan,
    expected_plan_generation: int,
    expected_plan_sha256: str,
    candidates: tuple[EpistemicActionCandidate, ...],
    provenance_refs: tuple[str, ...],
) -> EpistemicSelectionProposal:
    """Rank exact-bound discriminator candidates without executing any action."""

    try:
        verify_hyperposition_binding(
            state,
            expected_generation=expected_hyperposition_generation,
            expected_state_sha256=expected_hyperposition_sha256,
        )
    except HyperpositionError as exc:
        raise EpistemicActionSelectionError(str(exc)) from exc
    _verify_plan_binding(
        plan,
        expected_plan_generation=expected_plan_generation,
        expected_plan_sha256=expected_plan_sha256,
    )

    if not isinstance(candidates, tuple):
        raise EpistemicActionSelectionError("candidates must be an immutable tuple")
    if not all(type(item) is EpistemicActionCandidate for item in candidates):
        raise EpistemicActionSelectionError(
            "candidates must contain concrete EpistemicActionCandidate values"
        )
    ids = [item.candidate_id for item in candidates]
    if len(set(ids)) != len(ids):
        raise EpistemicActionSelectionError("duplicate epistemic action candidate identity")

    assessments: list[CandidateAssessment] = []
    eligible: list[EpistemicActionCandidate] = []
    for candidate in candidates:
        _verify_discriminator_binding(state, candidate.discriminator)
        try:
            budget = plan.budget_for(candidate.cell_id)
        except Grid10InterfaceError as exc:
            raise EpistemicActionSelectionError(str(exc)) from exc
        if plan.max_total_work_units == 0:
            reason = "PLAN_TOTAL_WORK_BUDGET_UNAVAILABLE"
            is_eligible = False
        elif budget.max_work_units == 0:
            reason = "CELL_WORK_BUDGET_UNAVAILABLE"
            is_eligible = False
        elif candidate.work_units_requested > budget.max_work_units:
            reason = "CELL_WORK_BUDGET_EXCEEDED"
            is_eligible = False
        elif candidate.work_units_requested > plan.max_total_work_units:
            reason = "PLAN_TOTAL_WORK_BUDGET_EXCEEDED"
            is_eligible = False
        else:
            reason = "ELIGIBLE"
            is_eligible = True
            eligible.append(candidate)
        assessments.append(
            CandidateAssessment(
                candidate_id=candidate.candidate_id,
                eligible=is_eligible,
                reason=reason,
                expected_information_gain_micros=(
                    candidate.expected_information_gain_micros
                ),
                estimated_cost_micros=candidate.estimated_cost_micros,
                work_units_requested=candidate.work_units_requested,
            )
        )

    selected_candidate_id: str | None = None
    selected_action_ref: str | None = None
    tied_candidate_ids: tuple[str, ...] = ()
    if eligible:
        def primary_key(item: EpistemicActionCandidate) -> tuple[int, int, int]:
            return (
                item.expected_information_gain_micros,
                -item.estimated_cost_micros,
                -item.work_units_requested,
            )

        best_key = max(primary_key(item) for item in eligible)
        tied = sorted(
            (item for item in eligible if primary_key(item) == best_key),
            key=lambda item: item.candidate_id,
        )
        tied_candidate_ids = tuple(item.candidate_id for item in tied)
        selected_candidate_id = tied[0].candidate_id
        selected_action_ref = tied[0].action_ref

    return EpistemicSelectionProposal(
        proposal_id=proposal_id,
        hyperposition_id=state.hyperposition_id,
        hyperposition_generation=state.generation,
        hyperposition_sha256=state.sha256(),
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        policy_id=plan.policy_id,
        policy_generation=plan.policy_generation,
        policy_sha256=plan.policy_sha256,
        selected_candidate_id=selected_candidate_id,
        selected_action_ref=selected_action_ref,
        tied_candidate_ids=tied_candidate_ids,
        assessments=tuple(assessments),
        provenance_refs=provenance_refs,
    )


__all__ = [
    "EPISTEMIC_ACTION_CANDIDATE_SCHEMA",
    "EPISTEMIC_SELECTION_PROPOSAL_SCHEMA",
    "SELECTION_RULE",
    "CandidateAssessment",
    "EpistemicActionCandidate",
    "EpistemicActionSelectionError",
    "EpistemicSelectionProposal",
    "select_epistemic_action",
]
