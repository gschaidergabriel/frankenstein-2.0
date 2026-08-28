"""Deterministic epistemic-action selection for Frankenstein 2.0 Stage 5.

F2-WP-504 generation 1.

This module ranks already-typed Hyperposition discriminator candidates against an
explicit deterministic selection policy and an exact GRID10 plan binding.  It emits
only a proposal.  It does not execute a discriminator, mutate Hyperposition/GRID,
read or write UnifiedDB, call models/providers/tools, infer world facts, authorize
an effect, verify completion, or mint runtime/GWT/GRID10/training credit.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, ClassVar, Iterable

from .grid10_interface import Grid10Plan
from .hyperposition import DiscriminatorCandidate, Hyperposition, verify_hyperposition_binding


SELECTION_POLICY_SCHEMA = "FRANKENSTEIN2_EPISTEMIC_SELECTION_POLICY/v1"
SELECTION_PROPOSAL_SCHEMA = "FRANKENSTEIN2_EPISTEMIC_SELECTION_PROPOSAL/v1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_MICROS = 1_000_000
_MAX_CANDIDATES = 4096


class EpistemicActionSelectionError(ValueError):
    """Fail-closed validation error for epistemic selection."""


class RankingRule(str, Enum):
    """Declared deterministic ranking rules; no hidden learned ranking is allowed."""

    MAX_EIG_THEN_MIN_COST = "MAX_EIG_THEN_MIN_COST"
    MAX_EIG_PER_COST_THEN_MAX_EIG_THEN_MIN_COST = (
        "MAX_EIG_PER_COST_THEN_MAX_EIG_THEN_MIN_COST"
    )


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EpistemicActionSelectionError(f"{name} must be a non-empty trimmed string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise EpistemicActionSelectionError(f"{name} must not contain control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise EpistemicActionSelectionError(f"{name} must be a non-negative integer")
    return value


def _micros(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_MICROS:
        raise EpistemicActionSelectionError(
            f"{name} must be an integer in [0, {_MAX_MICROS}]"
        )
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise EpistemicActionSelectionError(f"{name} must be lowercase 64-hex SHA-256")
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
        raise EpistemicActionSelectionError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sorted_unique_texts(name: str, values: Iterable[str], *, allow_empty: bool) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise EpistemicActionSelectionError(f"{name} must be an iterable of strings")
    cleaned = tuple(_text(f"{name} item", item) for item in values)
    if not allow_empty and not cleaned:
        raise EpistemicActionSelectionError(f"{name} must not be empty")
    if len(set(cleaned)) != len(cleaned):
        raise EpistemicActionSelectionError(f"{name} must not contain duplicates")
    return tuple(sorted(cleaned))


@dataclass(frozen=True, slots=True, kw_only=True)
class SelectionPolicy:
    """Explicit bounded policy for ranking typed discriminator candidates."""

    policy_id: str
    generation: int
    ranking_rule: RankingRule
    min_expected_information_gain_micros: int
    max_estimated_cost_micros: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = SELECTION_POLICY_SCHEMA
    classification: ClassVar[str] = "DETERMINISTIC_SELECTION_POLICY_NOT_EFFECT_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _generation("generation", self.generation)
        if not isinstance(self.ranking_rule, RankingRule):
            raise EpistemicActionSelectionError("ranking_rule must be a RankingRule")
        _micros(
            "min_expected_information_gain_micros",
            self.min_expected_information_gain_micros,
        )
        _micros("max_estimated_cost_micros", self.max_estimated_cost_micros)
        object.__setattr__(
            self,
            "provenance_refs",
            _sorted_unique_texts("provenance_refs", self.provenance_refs, allow_empty=False),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "ranking_rule": self.ranking_rule.value,
            "min_expected_information_gain_micros": self.min_expected_information_gain_micros,
            "max_estimated_cost_micros": self.max_estimated_cost_micros,
            "provenance_refs": list(self.provenance_refs),
            "effect_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class EpistemicSelectionProposal:
    """Read-only proposal bound to exact Hyperposition, GRID10 plan, and policy identities."""

    proposal_id: str
    generation: int
    hyperposition_id: str
    hyperposition_generation: int
    hyperposition_sha256: str
    grid_plan_id: str
    grid_plan_generation: int
    grid_plan_sha256: str
    policy_id: str
    policy_generation: int
    policy_sha256: str
    ranking_rule: RankingRule
    selected_discriminator_id: str
    tied_discriminator_ids: tuple[str, ...]
    eligible_discriminator_ids: tuple[str, ...]
    preserved_alternative_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = SELECTION_PROPOSAL_SCHEMA
    classification: ClassVar[str] = (
        "EPISTEMIC_SELECTION_PROPOSAL_NOT_ACTION_EFFECT_COMPLETION_OR_TRUTH_AUTHORITY"
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _text("proposal_id", self.proposal_id))
        _generation("generation", self.generation)
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
        if not isinstance(self.ranking_rule, RankingRule):
            raise EpistemicActionSelectionError("ranking_rule must be a RankingRule")
        object.__setattr__(
            self,
            "selected_discriminator_id",
            _text("selected_discriminator_id", self.selected_discriminator_id),
        )
        object.__setattr__(
            self,
            "tied_discriminator_ids",
            _sorted_unique_texts(
                "tied_discriminator_ids", self.tied_discriminator_ids, allow_empty=False
            ),
        )
        object.__setattr__(
            self,
            "eligible_discriminator_ids",
            _sorted_unique_texts(
                "eligible_discriminator_ids", self.eligible_discriminator_ids, allow_empty=False
            ),
        )
        object.__setattr__(
            self,
            "preserved_alternative_ids",
            _sorted_unique_texts(
                "preserved_alternative_ids", self.preserved_alternative_ids, allow_empty=False
            ),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _sorted_unique_texts("provenance_refs", self.provenance_refs, allow_empty=False),
        )
        if self.selected_discriminator_id not in self.tied_discriminator_ids:
            raise EpistemicActionSelectionError(
                "selected_discriminator_id must be one of tied_discriminator_ids"
            )
        if not set(self.tied_discriminator_ids).issubset(self.eligible_discriminator_ids):
            raise EpistemicActionSelectionError(
                "tied_discriminator_ids must be a subset of eligible_discriminator_ids"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "proposal_id": self.proposal_id,
            "generation": self.generation,
            "hyperposition_id": self.hyperposition_id,
            "hyperposition_generation": self.hyperposition_generation,
            "hyperposition_sha256": self.hyperposition_sha256,
            "grid_plan_id": self.grid_plan_id,
            "grid_plan_generation": self.grid_plan_generation,
            "grid_plan_sha256": self.grid_plan_sha256,
            "policy_id": self.policy_id,
            "policy_generation": self.policy_generation,
            "policy_sha256": self.policy_sha256,
            "ranking_rule": self.ranking_rule.value,
            "selected_discriminator_id": self.selected_discriminator_id,
            "tied_discriminator_ids": list(self.tied_discriminator_ids),
            "eligible_discriminator_ids": list(self.eligible_discriminator_ids),
            "preserved_alternative_ids": list(self.preserved_alternative_ids),
            "selection_authority": "PROPOSAL_ONLY",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "truth_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _verify_grid_plan_binding(
    plan: Grid10Plan,
    *,
    expected_plan_id: str,
    expected_generation: int,
    expected_plan_sha256: str,
) -> None:
    if type(plan) is not Grid10Plan:
        raise EpistemicActionSelectionError("grid_plan must be concrete Grid10Plan")
    expected_plan_id = _text("expected_plan_id", expected_plan_id)
    expected_generation = _generation("expected_generation", expected_generation)
    expected_plan_sha256 = _sha256("expected_plan_sha256", expected_plan_sha256)
    if plan.plan_id != expected_plan_id:
        raise EpistemicActionSelectionError("GRID10 plan identity mismatch")
    if plan.generation != expected_generation:
        raise EpistemicActionSelectionError("GRID10 plan generation mismatch")
    if plan.sha256() != expected_plan_sha256:
        raise EpistemicActionSelectionError("GRID10 plan digest mismatch")
    if plan.max_total_work_units <= 0 or not any(
        cell.max_work_units > 0 for cell in plan.cells
    ):
        raise EpistemicActionSelectionError("GRID10 work budget unavailable")


def _validate_candidates(
    state: Hyperposition,
    candidates: Iterable[DiscriminatorCandidate],
) -> tuple[DiscriminatorCandidate, ...]:
    if isinstance(candidates, (str, bytes)):
        raise EpistemicActionSelectionError("candidates must be an iterable")
    values = tuple(candidates)
    if not values:
        raise EpistemicActionSelectionError("at least one discriminator candidate is required")
    if len(values) > _MAX_CANDIDATES:
        raise EpistemicActionSelectionError(f"candidate count exceeds {_MAX_CANDIDATES}")
    if any(type(item) is not DiscriminatorCandidate for item in values):
        raise EpistemicActionSelectionError(
            "candidates must contain concrete DiscriminatorCandidate values"
        )

    ids = [item.discriminator_id for item in values]
    if len(set(ids)) != len(ids):
        raise EpistemicActionSelectionError("duplicate discriminator_id")

    known_alternatives = {item.alternative_id for item in state.alternatives}
    for item in values:
        if item.hyperposition_id != state.hyperposition_id:
            raise EpistemicActionSelectionError("candidate Hyperposition identity mismatch")
        if item.hyperposition_generation != state.generation:
            raise EpistemicActionSelectionError("candidate Hyperposition generation mismatch")
        if item.hyperposition_sha256 != state.sha256():
            raise EpistemicActionSelectionError("candidate Hyperposition digest mismatch")
        unknown = set(item.target_alternative_ids) - known_alternatives
        if unknown:
            raise EpistemicActionSelectionError(
                "candidate targets unknown alternatives: " + ", ".join(sorted(unknown))
            )
        _micros(
            "candidate expected_information_gain_micros",
            item.expected_information_gain_micros,
        )
        _micros("candidate estimated_cost_micros", item.estimated_cost_micros)
    return tuple(sorted(values, key=lambda item: item.discriminator_id))


def _ratio_compare(left: DiscriminatorCandidate, right: DiscriminatorCandidate) -> int:
    """Compare EIG/cost exactly without floats; zero cost with EIG>0 is best."""

    left_cost = left.estimated_cost_micros
    right_cost = right.estimated_cost_micros
    if left_cost == 0 or right_cost == 0:
        if left_cost == right_cost == 0:
            if left.expected_information_gain_micros != right.expected_information_gain_micros:
                return 1 if left.expected_information_gain_micros > right.expected_information_gain_micros else -1
            return 0
        if left_cost == 0:
            return 1 if left.expected_information_gain_micros > 0 else -1
        return -1 if right.expected_information_gain_micros > 0 else 1
    lhs = left.expected_information_gain_micros * right_cost
    rhs = right.expected_information_gain_micros * left_cost
    if lhs == rhs:
        return 0
    return 1 if lhs > rhs else -1


def _primary_tie(left: DiscriminatorCandidate, right: DiscriminatorCandidate, rule: RankingRule) -> bool:
    if rule is RankingRule.MAX_EIG_THEN_MIN_COST:
        return (
            left.expected_information_gain_micros == right.expected_information_gain_micros
            and left.estimated_cost_micros == right.estimated_cost_micros
        )
    return (
        _ratio_compare(left, right) == 0
        and left.expected_information_gain_micros == right.expected_information_gain_micros
        and left.estimated_cost_micros == right.estimated_cost_micros
    )


def _is_better(left: DiscriminatorCandidate, right: DiscriminatorCandidate, rule: RankingRule) -> bool:
    if rule is RankingRule.MAX_EIG_THEN_MIN_COST:
        if left.expected_information_gain_micros != right.expected_information_gain_micros:
            return left.expected_information_gain_micros > right.expected_information_gain_micros
        if left.estimated_cost_micros != right.estimated_cost_micros:
            return left.estimated_cost_micros < right.estimated_cost_micros
        return left.discriminator_id < right.discriminator_id

    ratio_cmp = _ratio_compare(left, right)
    if ratio_cmp:
        return ratio_cmp > 0
    if left.expected_information_gain_micros != right.expected_information_gain_micros:
        return left.expected_information_gain_micros > right.expected_information_gain_micros
    if left.estimated_cost_micros != right.estimated_cost_micros:
        return left.estimated_cost_micros < right.estimated_cost_micros
    return left.discriminator_id < right.discriminator_id


def select_epistemic_action(
    *,
    proposal_id: str,
    generation: int,
    state: Hyperposition,
    expected_hyperposition_generation: int,
    expected_hyperposition_sha256: str,
    grid_plan: Grid10Plan,
    expected_grid_plan_id: str,
    expected_grid_plan_generation: int,
    expected_grid_plan_sha256: str,
    policy: SelectionPolicy,
    expected_policy_generation: int,
    expected_policy_sha256: str,
    candidates: Iterable[DiscriminatorCandidate],
    provenance_refs: Iterable[str],
) -> EpistemicSelectionProposal:
    """Return one deterministic proposal while preserving ties and all alternatives."""

    if type(state) is not Hyperposition:
        raise EpistemicActionSelectionError("state must be concrete Hyperposition")
    verify_hyperposition_binding(
        state,
        expected_generation=expected_hyperposition_generation,
        expected_state_sha256=expected_hyperposition_sha256,
    )
    _verify_grid_plan_binding(
        grid_plan,
        expected_plan_id=expected_grid_plan_id,
        expected_generation=expected_grid_plan_generation,
        expected_plan_sha256=expected_grid_plan_sha256,
    )
    if type(policy) is not SelectionPolicy:
        raise EpistemicActionSelectionError("policy must be concrete SelectionPolicy")
    expected_policy_generation = _generation(
        "expected_policy_generation", expected_policy_generation
    )
    expected_policy_sha256 = _sha256("expected_policy_sha256", expected_policy_sha256)
    if policy.generation != expected_policy_generation:
        raise EpistemicActionSelectionError("selection policy generation mismatch")
    if policy.sha256() != expected_policy_sha256:
        raise EpistemicActionSelectionError("selection policy digest mismatch")

    values = _validate_candidates(state, candidates)
    eligible = tuple(
        item
        for item in values
        if item.expected_information_gain_micros
        >= policy.min_expected_information_gain_micros
        and item.estimated_cost_micros <= policy.max_estimated_cost_micros
    )
    if not eligible:
        raise EpistemicActionSelectionError(
            "no discriminator candidate is eligible under the explicit selection policy"
        )

    best = eligible[0]
    for item in eligible[1:]:
        if _is_better(item, best, policy.ranking_rule):
            best = item

    ties = tuple(
        item.discriminator_id
        for item in eligible
        if _primary_tie(item, best, policy.ranking_rule)
    )
    selected_id = min(ties)

    provenance = _sorted_unique_texts(
        "provenance_refs", provenance_refs, allow_empty=False
    )
    return EpistemicSelectionProposal(
        proposal_id=proposal_id,
        generation=generation,
        hyperposition_id=state.hyperposition_id,
        hyperposition_generation=state.generation,
        hyperposition_sha256=state.sha256(),
        grid_plan_id=grid_plan.plan_id,
        grid_plan_generation=grid_plan.generation,
        grid_plan_sha256=grid_plan.sha256(),
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=policy.sha256(),
        ranking_rule=policy.ranking_rule,
        selected_discriminator_id=selected_id,
        tied_discriminator_ids=ties,
        eligible_discriminator_ids=tuple(item.discriminator_id for item in eligible),
        preserved_alternative_ids=tuple(item.alternative_id for item in state.alternatives),
        provenance_refs=provenance,
    )


__all__ = [
    "SELECTION_POLICY_SCHEMA",
    "SELECTION_PROPOSAL_SCHEMA",
    "EpistemicActionSelectionError",
    "EpistemicSelectionProposal",
    "RankingRule",
    "SelectionPolicy",
    "select_epistemic_action",
]
