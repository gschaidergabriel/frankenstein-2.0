"""Deterministic candidate-pool coverage planning for F2-WP-1208 generation 2.

Measures cross-family pairwise action combinations and ordered action pairs already present
in an immutable HostileChaosMatrix, then chooses an equal-budget subset by deterministic
marginal coverage gain.  This is repository-only derived evidence: it executes no faults and
mints no target/runtime/physical/completion credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from itertools import combinations
from typing import Any, Iterable

from .target_fault_scenarios import ACTION_DOMAIN
from .target_hostile_chaos_matrix import (
    DOMAIN_TO_FAMILY,
    HostileChaosCase,
    HostileChaosMatrix,
    REQUIRED_FAULT_FAMILIES,
)

COVERAGE_PLAN_SCHEMA = "FRANKENSTEIN2_HOSTILE_CHAOS_COVERAGE_PLAN/v1"
COVERAGE_CLASSIFICATION = "DERIVED_CANDIDATE_POOL_COVERAGE_NO_TARGET_RUNTIME_OR_COMPLETION_CREDIT"
MAX_COVERAGE_UNIVERSE = 100_000
Token = tuple[str, str, str, str]


class TargetChaosCoverageError(ValueError):
    """Fail-closed validation error for derived hostile-chaos coverage."""


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TargetChaosCoverageError("value is not canonical JSON-safe data") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _validated_matrix(matrix: HostileChaosMatrix) -> HostileChaosMatrix:
    if type(matrix) is not HostileChaosMatrix:
        raise TargetChaosCoverageError("matrix must be a concrete HostileChaosMatrix")
    return HostileChaosMatrix(
        schema=matrix.schema,
        matrix_id=matrix.matrix_id,
        matrix_name=matrix.matrix_name,
        cases=matrix.cases,
        total_events=matrix.total_events,
        classification=matrix.classification,
        runtime_execution_observed=matrix.runtime_execution_observed,
        physical_host_credit=matrix.physical_host_credit,
        completion_credit=matrix.completion_credit,
    )


def _family_actions(case: HostileChaosCase) -> dict[str, tuple[str, ...]]:
    case = case.validated_copy()
    found: dict[str, set[str]] = {family: set() for family in REQUIRED_FAULT_FAMILIES}
    for event in case.scenario.events:
        family = DOMAIN_TO_FAMILY.get(ACTION_DOMAIN[event.action])
        if family in found:
            found[family].add(event.action)
    result = {family: tuple(sorted(values)) for family, values in found.items()}
    missing = [family for family, values in result.items() if not values]
    if missing:
        raise TargetChaosCoverageError("case is missing required family actions: " + ",".join(missing))
    return result


def _pool_levels(cases: tuple[HostileChaosCase, ...]) -> dict[str, tuple[str, ...]]:
    levels: dict[str, set[str]] = {family: set() for family in REQUIRED_FAULT_FAMILIES}
    for case in cases:
        for family, actions in _family_actions(case).items():
            levels[family].update(actions)
    return {family: tuple(sorted(values)) for family, values in levels.items()}


def _pairwise_universe(levels: dict[str, tuple[str, ...]]) -> frozenset[Token]:
    out: set[Token] = set()
    for left, right in combinations(REQUIRED_FAULT_FAMILIES, 2):
        out.update((left, la, right, ra) for la in levels[left] for ra in levels[right])
    if len(out) > MAX_COVERAGE_UNIVERSE:
        raise TargetChaosCoverageError(f"pairwise universe exceeds {MAX_COVERAGE_UNIVERSE} combinations")
    return frozenset(out)


def _ordered_universe(levels: dict[str, tuple[str, ...]]) -> frozenset[Token]:
    out = {
        (left, la, right, ra)
        for left in REQUIRED_FAULT_FAMILIES
        for right in REQUIRED_FAULT_FAMILIES
        if left != right
        for la in levels[left]
        for ra in levels[right]
    }
    if len(out) > MAX_COVERAGE_UNIVERSE:
        raise TargetChaosCoverageError(f"ordered universe exceeds {MAX_COVERAGE_UNIVERSE} combinations")
    return frozenset(out)


def _case_pairwise(case: HostileChaosCase) -> frozenset[Token]:
    actions = _family_actions(case)
    return frozenset(
        (left, la, right, ra)
        for left, right in combinations(REQUIRED_FAULT_FAMILIES, 2)
        for la in actions[left]
        for ra in actions[right]
    )


def _case_ordered(case: HostileChaosCase) -> frozenset[Token]:
    events: list[tuple[int, str, str]] = []
    for event in case.validated_copy().scenario.events:
        family = DOMAIN_TO_FAMILY.get(ACTION_DOMAIN[event.action])
        if family in REQUIRED_FAULT_FAMILIES:
            events.append((event.sequence, family, event.action))
    events.sort()
    return frozenset(
        (lf, la, rf, ra)
        for i, (_, lf, la) in enumerate(events)
        for _, rf, ra in events[i + 1 :]
        if lf != rf
    )


def _covered(cases: Iterable[HostileChaosCase]) -> tuple[frozenset[Token], frozenset[Token]]:
    pairwise: set[Token] = set()
    ordered: set[Token] = set()
    for case in cases:
        pairwise.update(_case_pairwise(case))
        ordered.update(_case_ordered(case))
    return frozenset(pairwise), frozenset(ordered)


@dataclass(frozen=True, slots=True)
class CoverageCounts:
    case_count: int
    event_count: int
    pairwise_covered: int
    pairwise_universe: int
    ordered_covered: int
    ordered_universe: int

    def __post_init__(self) -> None:
        for field in self.__dataclass_fields__:
            value = getattr(self, field)
            if type(value) is not int or value < 0:
                raise TargetChaosCoverageError(f"{field} must be a non-negative integer")
        if self.pairwise_covered > self.pairwise_universe or self.ordered_covered > self.ordered_universe:
            raise TargetChaosCoverageError("covered count exceeds universe")

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_count": self.case_count,
            "event_count": self.event_count,
            "pairwise_covered": self.pairwise_covered,
            "pairwise_universe": self.pairwise_universe,
            "pairwise_ratio": f"{self.pairwise_covered}/{self.pairwise_universe}",
            "ordered_covered": self.ordered_covered,
            "ordered_universe": self.ordered_universe,
            "ordered_ratio": f"{self.ordered_covered}/{self.ordered_universe}",
        }


def _measure(cases: tuple[HostileChaosCase, ...], pu: frozenset[Token], ou: frozenset[Token]) -> CoverageCounts:
    pairwise, ordered = _covered(cases)
    return CoverageCounts(
        case_count=len(cases),
        event_count=sum(len(case.scenario.events) for case in cases),
        pairwise_covered=len(pairwise & pu),
        pairwise_universe=len(pu),
        ordered_covered=len(ordered & ou),
        ordered_universe=len(ou),
    )


@dataclass(frozen=True, slots=True)
class ChaosCoveragePlan:
    schema: str
    plan_id: str
    source_matrix_id: str
    source_matrix_sha256: str
    case_budget: int
    mandatory_case_ids: tuple[str, ...]
    baseline_case_ids: tuple[str, ...]
    selected_case_ids: tuple[str, ...]
    baseline: CoverageCounts
    selected: CoverageCounts
    pairwise_gain: int
    ordered_gain: int
    classification: str = COVERAGE_CLASSIFICATION
    runtime_execution_observed: bool = False
    target_runtime_credit: int = 0
    physical_host_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False

    def __post_init__(self) -> None:
        if self.schema != COVERAGE_PLAN_SCHEMA or self.classification != COVERAGE_CLASSIFICATION:
            raise TargetChaosCoverageError("coverage plan schema/classification mismatch")
        if not self.plan_id.startswith("hostile-chaos-coverage:"):
            raise TargetChaosCoverageError("plan_id prefix mismatch")
        if self.runtime_execution_observed or any((self.target_runtime_credit, self.physical_host_credit, self.completion_credit)) or self.whole_system_acceptance:
            raise TargetChaosCoverageError("repository coverage plan cannot mint runtime/completion credit")
        if len(self.baseline_case_ids) != self.case_budget or len(self.selected_case_ids) != self.case_budget:
            raise TargetChaosCoverageError("coverage selections must exactly match case budget")
        if len(set(self.selected_case_ids)) != len(self.selected_case_ids):
            raise TargetChaosCoverageError("selected_case_ids contains duplicates")
        if not set(self.mandatory_case_ids).issubset(self.selected_case_ids):
            raise TargetChaosCoverageError("mandatory sentinel missing from selected cases")
        if self.pairwise_gain != self.selected.pairwise_covered - self.baseline.pairwise_covered:
            raise TargetChaosCoverageError("pairwise gain mismatch")
        if self.ordered_gain != self.selected.ordered_covered - self.baseline.ordered_covered:
            raise TargetChaosCoverageError("ordered gain mismatch")
        expected = "hostile-chaos-coverage:" + _digest(self._identity_payload())
        if self.plan_id != expected:
            raise TargetChaosCoverageError("plan_id does not bind exact coverage plan")

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_matrix_id": self.source_matrix_id,
            "source_matrix_sha256": self.source_matrix_sha256,
            "case_budget": self.case_budget,
            "mandatory_case_ids": list(self.mandatory_case_ids),
            "baseline_case_ids": list(self.baseline_case_ids),
            "selected_case_ids": list(self.selected_case_ids),
            "baseline": self.baseline.as_dict(),
            "selected": self.selected.as_dict(),
            "pairwise_gain": self.pairwise_gain,
            "ordered_gain": self.ordered_gain,
            "classification": self.classification,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            **self._identity_payload(),
            "plan_id": self.plan_id,
            "runtime_execution_observed": self.runtime_execution_observed,
            "target_runtime_credit": self.target_runtime_credit,
            "physical_host_credit": self.physical_host_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def compile_chaos_coverage_plan(
    matrix: HostileChaosMatrix,
    *,
    case_budget: int,
    mandatory_case_ids: Iterable[str] = (),
) -> ChaosCoveragePlan:
    """Build a deterministic same-budget coverage plan from an immutable candidate matrix."""
    matrix = _validated_matrix(matrix)
    if type(case_budget) is not int or not 1 <= case_budget <= len(matrix.cases):
        raise TargetChaosCoverageError(f"case_budget must be an integer in [1, {len(matrix.cases)}]")
    if isinstance(mandatory_case_ids, (str, bytes)):
        raise TargetChaosCoverageError("mandatory_case_ids must be an iterable of case ids")
    raw_mandatory = tuple(mandatory_case_ids)
    if any(type(value) is not str or not value for value in raw_mandatory):
        raise TargetChaosCoverageError("mandatory_case_ids must contain non-empty strings")
    if len(raw_mandatory) != len(set(raw_mandatory)):
        raise TargetChaosCoverageError("mandatory_case_ids contains duplicates")
    mandatory = tuple(sorted(raw_mandatory))
    if len(mandatory) > case_budget:
        raise TargetChaosCoverageError("mandatory cases exceed case budget")

    by_id = {case.case_id: case for case in matrix.cases}
    unknown = [value for value in mandatory if value not in by_id]
    if unknown:
        raise TargetChaosCoverageError("unknown mandatory case ids: " + ",".join(unknown))

    levels = _pool_levels(matrix.cases)
    pairwise_universe, ordered_universe = _pairwise_universe(levels), _ordered_universe(levels)
    per_pair = {case.case_id: _case_pairwise(case) for case in matrix.cases}
    per_order = {case.case_id: _case_ordered(case) for case in matrix.cases}

    selected = list(mandatory)
    covered_pair: set[Token] = set().union(*(per_pair[value] for value in selected)) if selected else set()
    covered_order: set[Token] = set().union(*(per_order[value] for value in selected)) if selected else set()
    remaining = set(by_id) - set(selected)
    while len(selected) < case_budget:
        best: tuple[tuple[int, int, int], str] | None = None
        for case_id in sorted(remaining):
            new_pair = len(per_pair[case_id] - covered_pair)
            new_order = len(per_order[case_id] - covered_order)
            scored = ((new_pair + new_order, new_pair, new_order), case_id)
            if best is None or scored[0] > best[0]:
                best = scored
        if best is None:
            raise TargetChaosCoverageError("coverage selection exhausted candidates early")
        case_id = best[1]
        selected.append(case_id)
        covered_pair.update(per_pair[case_id])
        covered_order.update(per_order[case_id])
        remaining.remove(case_id)

    baseline_cases = tuple(matrix.cases[:case_budget])
    selected_cases = tuple(by_id[value] for value in selected)
    baseline = _measure(baseline_cases, pairwise_universe, ordered_universe)
    chosen = _measure(selected_cases, pairwise_universe, ordered_universe)
    identity = {
        "schema": COVERAGE_PLAN_SCHEMA,
        "source_matrix_id": matrix.matrix_id,
        "source_matrix_sha256": matrix.sha256(),
        "case_budget": case_budget,
        "mandatory_case_ids": list(mandatory),
        "baseline_case_ids": [case.case_id for case in baseline_cases],
        "selected_case_ids": selected,
        "baseline": baseline.as_dict(),
        "selected": chosen.as_dict(),
        "pairwise_gain": chosen.pairwise_covered - baseline.pairwise_covered,
        "ordered_gain": chosen.ordered_covered - baseline.ordered_covered,
        "classification": COVERAGE_CLASSIFICATION,
    }
    return ChaosCoveragePlan(
        schema=COVERAGE_PLAN_SCHEMA,
        plan_id="hostile-chaos-coverage:" + _digest(identity),
        source_matrix_id=matrix.matrix_id,
        source_matrix_sha256=matrix.sha256(),
        case_budget=case_budget,
        mandatory_case_ids=mandatory,
        baseline_case_ids=tuple(case.case_id for case in baseline_cases),
        selected_case_ids=tuple(selected),
        baseline=baseline,
        selected=chosen,
        pairwise_gain=chosen.pairwise_covered - baseline.pairwise_covered,
        ordered_gain=chosen.ordered_covered - baseline.ordered_covered,
    )
