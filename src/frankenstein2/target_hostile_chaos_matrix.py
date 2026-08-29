"""Deterministic hostile target-twin chaos-matrix planning primitives.

F2-WP-1208 generation 1.

This module composes accepted source-level fault-scenario primitives into bounded hostile
chaos cases. It does not mutate a host/twin, does not observe sustained runtime behavior,
and cannot mint target, physical-host, CompletionGate, EffectGate, GRID/GWT/J-Space,
training, or whole-system credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable

from .target_fault_scenarios import (
    ACTION_DOMAIN,
    DEVICE,
    FILESYSTEM_PACKAGE,
    GENERATION_INVALIDATING_ACTIONS,
    NETWORK_BRIDGE,
    PERMISSION,
    PROCESS_LIFECYCLE,
    SESSION_SERVICE,
    FaultScenario,
    FaultSpec,
    compile_fault_scenario,
)

CHAOS_CASE_SCHEMA = "FRANKENSTEIN2_HOSTILE_CHAOS_CASE/v1"
CHAOS_MATRIX_SCHEMA = "FRANKENSTEIN2_HOSTILE_CHAOS_MATRIX/v1"
CHAOS_CLASSIFICATION = "SIMULATED_HOSTILE_CHAOS_MATRIX_NO_TARGET_OR_COMPLETION_CREDIT"
COMPLETION_EXPECTATION = "FAIL_CLOSED_UNKNOWN_UNTIL_INDEPENDENT_MANDATORY_EVIDENCE"
AUTHORITY_REBIND_POLICY = "GENERATION_CHANGE_REQUIRES_EXPLICIT_REOBSERVATION_AND_REBIND"
PROTECTED_STATE_EXPECTATION = "COGNITION_AND_CANONICAL_STATE_MUST_REMAIN_INTACT_OR_CASE_FAILS"

FAMILY_MULTIMEDIA_SESSION = "MULTIMEDIA_SESSION"
FAMILY_PERMISSION = "PERMISSION"
FAMILY_LIFECYCLE = "LIFECYCLE"
FAMILY_NETWORK = "NETWORK"
FAMILY_RESOURCE_PRESSURE = "RESOURCE_PRESSURE"

REQUIRED_FAULT_FAMILIES = (
    FAMILY_MULTIMEDIA_SESSION,
    FAMILY_PERMISSION,
    FAMILY_LIFECYCLE,
    FAMILY_NETWORK,
    FAMILY_RESOURCE_PRESSURE,
)
DEGRADATION_ORDER = ("PERCEPTION", "VOICE", "COGNITION", "CANONICAL_STATE")

DOMAIN_TO_FAMILY = {
    DEVICE: FAMILY_MULTIMEDIA_SESSION,
    SESSION_SERVICE: FAMILY_MULTIMEDIA_SESSION,
    PERMISSION: FAMILY_PERMISSION,
    PROCESS_LIFECYCLE: FAMILY_LIFECYCLE,
    NETWORK_BRIDGE: FAMILY_NETWORK,
    FILESYSTEM_PACKAGE: FAMILY_RESOURCE_PRESSURE,
}

MAX_CASES = 64
MAX_EVENTS_PER_CASE = 512
MAX_TOTAL_EVENTS = 8192
MAX_SIMULTANEOUS_EVENTS = 64
_PROTECTED_TARGET_PREFIXES = ("canonical_state:", "unifieddb:", "cognition:")


class TargetHostileChaosMatrixError(ValueError):
    """Fail-closed validation error for hostile chaos planning."""


def _exact_string(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise TargetHostileChaosMatrixError(f"{name} must be a non-empty trimmed string")
    if len(value) > 512:
        raise TargetHostileChaosMatrixError(f"{name} exceeds 512 characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TargetHostileChaosMatrixError(f"{name} contains control characters")
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TargetHostileChaosMatrixError("value is not canonical JSON-safe data") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _family_for_domain(domain: str) -> str | None:
    return DOMAIN_TO_FAMILY.get(domain)


def _family_counts(scenario: FaultScenario) -> tuple[tuple[str, int], ...]:
    counts = {family: 0 for family in REQUIRED_FAULT_FAMILIES}
    for event in scenario.events:
        family = _family_for_domain(ACTION_DOMAIN[event.action])
        if family is not None:
            counts[family] += 1
    return tuple((family, counts[family]) for family in REQUIRED_FAULT_FAMILIES)


def _concurrent_offsets(scenario: FaultScenario) -> tuple[int, ...]:
    by_offset: dict[int, set[str]] = {}
    raw_counts: dict[int, int] = {}
    for event in scenario.events:
        family = _family_for_domain(ACTION_DOMAIN[event.action])
        if family is None:
            continue
        by_offset.setdefault(event.offset_ms, set()).add(family)
        raw_counts[event.offset_ms] = raw_counts.get(event.offset_ms, 0) + 1
    for offset, count in raw_counts.items():
        if count > MAX_SIMULTANEOUS_EVENTS:
            raise TargetHostileChaosMatrixError(
                f"offset {offset} exceeds {MAX_SIMULTANEOUS_EVENTS} simultaneous events"
            )
    return tuple(sorted(offset for offset, families in by_offset.items() if len(families) >= 2))


def _authority_fence_event_ids(scenario: FaultScenario) -> tuple[str, ...]:
    return tuple(
        event.event_id
        for event in scenario.events
        if event.action in GENERATION_INVALIDATING_ACTIONS
        and event.generation_after > event.generation_before
    )


def _validate_protected_targets(scenario: FaultScenario) -> None:
    for event in scenario.events:
        lowered = event.target.lower()
        if lowered.startswith(_PROTECTED_TARGET_PREFIXES):
            raise TargetHostileChaosMatrixError(
                f"hostile chaos input may not directly target protected cognition/state authority: {event.target}"
            )


def _case_identity_payload(
    *,
    case_name: str,
    scenario: FaultScenario,
    family_counts: tuple[tuple[str, int], ...],
    concurrent_offsets_ms: tuple[int, ...],
    authority_fence_event_ids: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "case_name": case_name,
        "scenario": scenario.as_dict(),
        "family_counts": {key: value for key, value in family_counts},
        "concurrent_offsets_ms": list(concurrent_offsets_ms),
        "authority_fence_event_ids": list(authority_fence_event_ids),
        "degradation_order": list(DEGRADATION_ORDER),
        "completion_expectation": COMPLETION_EXPECTATION,
        "authority_rebind_policy": AUTHORITY_REBIND_POLICY,
        "protected_state_expectation": PROTECTED_STATE_EXPECTATION,
    }


@dataclass(frozen=True, slots=True)
class HostileChaosCase:
    schema: str
    case_id: str
    case_name: str
    scenario: FaultScenario
    family_counts: tuple[tuple[str, int], ...]
    concurrent_offsets_ms: tuple[int, ...]
    authority_fence_event_ids: tuple[str, ...]
    degradation_order: tuple[str, ...] = DEGRADATION_ORDER
    completion_expectation: str = COMPLETION_EXPECTATION
    authority_rebind_policy: str = AUTHORITY_REBIND_POLICY
    protected_state_expectation: str = PROTECTED_STATE_EXPECTATION
    classification: str = CHAOS_CLASSIFICATION
    runtime_execution_observed: bool = False
    physical_host_credit: int = 0
    completion_credit: int = 0

    def __post_init__(self) -> None:
        if self.schema != CHAOS_CASE_SCHEMA:
            raise TargetHostileChaosMatrixError("chaos case schema mismatch")
        _exact_string("case_id", self.case_id)
        _exact_string("case_name", self.case_name)
        if type(self.scenario) is not FaultScenario:
            raise TargetHostileChaosMatrixError("scenario must be a concrete FaultScenario")
        scenario = self.scenario.validated_copy()
        object.__setattr__(self, "scenario", scenario)
        if len(scenario.events) > MAX_EVENTS_PER_CASE:
            raise TargetHostileChaosMatrixError(
                f"case exceeds {MAX_EVENTS_PER_CASE} events"
            )
        _validate_protected_targets(scenario)

        expected_counts = _family_counts(scenario)
        if self.family_counts != expected_counts:
            raise TargetHostileChaosMatrixError("family_counts do not bind exact scenario")
        missing = [family for family, count in expected_counts if count == 0]
        if missing:
            raise TargetHostileChaosMatrixError(
                "hostile chaos case missing required fault families: " + ",".join(missing)
            )

        expected_offsets = _concurrent_offsets(scenario)
        if self.concurrent_offsets_ms != expected_offsets:
            raise TargetHostileChaosMatrixError("concurrent_offsets_ms do not bind exact scenario")
        if not expected_offsets:
            raise TargetHostileChaosMatrixError(
                "hostile chaos case requires cross-family concurrency at one or more offsets"
            )

        expected_fences = _authority_fence_event_ids(scenario)
        if self.authority_fence_event_ids != expected_fences:
            raise TargetHostileChaosMatrixError("authority_fence_event_ids do not bind generation changes")
        if not expected_fences:
            raise TargetHostileChaosMatrixError(
                "hostile chaos case requires at least one generation-invalidating fault"
            )

        if self.degradation_order != DEGRADATION_ORDER:
            raise TargetHostileChaosMatrixError("degradation order must preserve cognition/state after perception/voice")
        if self.completion_expectation != COMPLETION_EXPECTATION:
            raise TargetHostileChaosMatrixError("completion expectation must remain fail-closed")
        if self.authority_rebind_policy != AUTHORITY_REBIND_POLICY:
            raise TargetHostileChaosMatrixError("authority rebind policy mismatch")
        if self.protected_state_expectation != PROTECTED_STATE_EXPECTATION:
            raise TargetHostileChaosMatrixError("protected state expectation mismatch")
        if self.classification != CHAOS_CLASSIFICATION:
            raise TargetHostileChaosMatrixError("chaos classification mismatch")
        if type(self.runtime_execution_observed) is not bool or self.runtime_execution_observed:
            raise TargetHostileChaosMatrixError("source-level chaos plan cannot claim runtime execution")
        if type(self.physical_host_credit) is not int or self.physical_host_credit != 0:
            raise TargetHostileChaosMatrixError("source-level chaos plan cannot claim physical host credit")
        if type(self.completion_credit) is not int or self.completion_credit != 0:
            raise TargetHostileChaosMatrixError("source-level chaos plan cannot claim completion credit")

        expected_id = "hostile-chaos-case:" + _digest(
            _case_identity_payload(
                case_name=self.case_name,
                scenario=self.scenario,
                family_counts=self.family_counts,
                concurrent_offsets_ms=self.concurrent_offsets_ms,
                authority_fence_event_ids=self.authority_fence_event_ids,
            )
        )
        if self.case_id != expected_id:
            raise TargetHostileChaosMatrixError("case_id does not bind exact hostile chaos case")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "case_id": self.case_id,
            **_case_identity_payload(
                case_name=self.case_name,
                scenario=self.scenario,
                family_counts=self.family_counts,
                concurrent_offsets_ms=self.concurrent_offsets_ms,
                authority_fence_event_ids=self.authority_fence_event_ids,
            ),
            "classification": self.classification,
            "runtime_execution_observed": self.runtime_execution_observed,
            "physical_host_credit": self.physical_host_credit,
            "completion_credit": self.completion_credit,
        }

    def validated_copy(self) -> "HostileChaosCase":
        return HostileChaosCase(
            schema=self.schema,
            case_id=self.case_id,
            case_name=self.case_name,
            scenario=self.scenario,
            family_counts=self.family_counts,
            concurrent_offsets_ms=self.concurrent_offsets_ms,
            authority_fence_event_ids=self.authority_fence_event_ids,
            degradation_order=self.degradation_order,
            completion_expectation=self.completion_expectation,
            authority_rebind_policy=self.authority_rebind_policy,
            protected_state_expectation=self.protected_state_expectation,
            classification=self.classification,
            runtime_execution_observed=self.runtime_execution_observed,
            physical_host_credit=self.physical_host_credit,
            completion_credit=self.completion_credit,
        )


def compile_hostile_chaos_case(
    *,
    case_name: str,
    seed: int,
    target_profile_digest: str,
    start_generation: int,
    specs: Iterable[FaultSpec],
) -> HostileChaosCase:
    case_name = _exact_string("case_name", case_name)
    if isinstance(specs, (str, bytes)):
        raise TargetHostileChaosMatrixError("specs must be an iterable of FaultSpec objects")
    spec_tuple = tuple(specs)
    if not spec_tuple:
        raise TargetHostileChaosMatrixError("hostile chaos case requires at least one fault")
    if len(spec_tuple) > MAX_EVENTS_PER_CASE:
        raise TargetHostileChaosMatrixError(
            f"case exceeds {MAX_EVENTS_PER_CASE} events"
        )
    scenario = compile_fault_scenario(
        scenario_name=f"hostile-chaos:{case_name}",
        seed=seed,
        target_profile_digest=target_profile_digest,
        start_generation=start_generation,
        specs=spec_tuple,
    )
    family_counts = _family_counts(scenario)
    concurrent_offsets_ms = _concurrent_offsets(scenario)
    authority_fence_event_ids = _authority_fence_event_ids(scenario)
    identity = _case_identity_payload(
        case_name=case_name,
        scenario=scenario,
        family_counts=family_counts,
        concurrent_offsets_ms=concurrent_offsets_ms,
        authority_fence_event_ids=authority_fence_event_ids,
    )
    return HostileChaosCase(
        schema=CHAOS_CASE_SCHEMA,
        case_id="hostile-chaos-case:" + _digest(identity),
        case_name=case_name,
        scenario=scenario,
        family_counts=family_counts,
        concurrent_offsets_ms=concurrent_offsets_ms,
        authority_fence_event_ids=authority_fence_event_ids,
    )


def _matrix_identity_payload(*, matrix_name: str, cases: tuple[HostileChaosCase, ...]) -> dict[str, Any]:
    return {
        "matrix_name": matrix_name,
        "cases": [case.as_dict() for case in cases],
        "limits": {
            "max_cases": MAX_CASES,
            "max_events_per_case": MAX_EVENTS_PER_CASE,
            "max_total_events": MAX_TOTAL_EVENTS,
            "max_simultaneous_events": MAX_SIMULTANEOUS_EVENTS,
        },
    }


@dataclass(frozen=True, slots=True)
class HostileChaosMatrix:
    schema: str
    matrix_id: str
    matrix_name: str
    cases: tuple[HostileChaosCase, ...]
    total_events: int
    classification: str = CHAOS_CLASSIFICATION
    runtime_execution_observed: bool = False
    physical_host_credit: int = 0
    completion_credit: int = 0

    def __post_init__(self) -> None:
        if self.schema != CHAOS_MATRIX_SCHEMA:
            raise TargetHostileChaosMatrixError("chaos matrix schema mismatch")
        _exact_string("matrix_id", self.matrix_id)
        _exact_string("matrix_name", self.matrix_name)
        if type(self.cases) is not tuple or not self.cases:
            raise TargetHostileChaosMatrixError("cases must be a non-empty tuple")
        if len(self.cases) > MAX_CASES:
            raise TargetHostileChaosMatrixError(f"matrix exceeds {MAX_CASES} cases")
        validated: list[HostileChaosCase] = []
        for raw_case in self.cases:
            if type(raw_case) is not HostileChaosCase:
                raise TargetHostileChaosMatrixError("cases must contain concrete HostileChaosCase objects")
            validated.append(raw_case.validated_copy())
        object.__setattr__(self, "cases", tuple(validated))
        names = [case.case_name for case in self.cases]
        if len(names) != len(set(names)):
            raise TargetHostileChaosMatrixError("case names must be unique within a matrix")
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise TargetHostileChaosMatrixError("case ids must be unique within a matrix")
        expected_total = sum(len(case.scenario.events) for case in self.cases)
        if type(self.total_events) is not int or self.total_events != expected_total:
            raise TargetHostileChaosMatrixError("total_events does not bind exact matrix cases")
        if expected_total > MAX_TOTAL_EVENTS:
            raise TargetHostileChaosMatrixError(f"matrix exceeds {MAX_TOTAL_EVENTS} total events")
        if self.classification != CHAOS_CLASSIFICATION:
            raise TargetHostileChaosMatrixError("chaos classification mismatch")
        if type(self.runtime_execution_observed) is not bool or self.runtime_execution_observed:
            raise TargetHostileChaosMatrixError("repository-level matrix cannot claim runtime execution")
        if type(self.physical_host_credit) is not int or self.physical_host_credit != 0:
            raise TargetHostileChaosMatrixError("repository-level matrix cannot claim physical host credit")
        if type(self.completion_credit) is not int or self.completion_credit != 0:
            raise TargetHostileChaosMatrixError("repository-level matrix cannot claim completion credit")
        expected_id = "hostile-chaos-matrix:" + _digest(
            _matrix_identity_payload(matrix_name=self.matrix_name, cases=self.cases)
        )
        if self.matrix_id != expected_id:
            raise TargetHostileChaosMatrixError("matrix_id does not bind exact hostile chaos matrix")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "matrix_id": self.matrix_id,
            **_matrix_identity_payload(matrix_name=self.matrix_name, cases=self.cases),
            "total_events": self.total_events,
            "classification": self.classification,
            "runtime_execution_observed": self.runtime_execution_observed,
            "physical_host_credit": self.physical_host_credit,
            "completion_credit": self.completion_credit,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def compile_hostile_chaos_matrix(
    *,
    matrix_name: str,
    cases: Iterable[HostileChaosCase],
) -> HostileChaosMatrix:
    matrix_name = _exact_string("matrix_name", matrix_name)
    if isinstance(cases, (str, bytes)):
        raise TargetHostileChaosMatrixError("cases must be an iterable of HostileChaosCase objects")
    case_tuple = tuple(cases)
    if not case_tuple:
        raise TargetHostileChaosMatrixError("matrix requires at least one case")
    if len(case_tuple) > MAX_CASES:
        raise TargetHostileChaosMatrixError(f"matrix exceeds {MAX_CASES} cases")
    validated = tuple(
        case.validated_copy() if type(case) is HostileChaosCase else case
        for case in case_tuple
    )
    if any(type(case) is not HostileChaosCase for case in validated):
        raise TargetHostileChaosMatrixError("cases must contain concrete HostileChaosCase objects")
    total_events = sum(len(case.scenario.events) for case in validated)
    if total_events > MAX_TOTAL_EVENTS:
        raise TargetHostileChaosMatrixError(f"matrix exceeds {MAX_TOTAL_EVENTS} total events")
    identity = _matrix_identity_payload(matrix_name=matrix_name, cases=validated)
    return HostileChaosMatrix(
        schema=CHAOS_MATRIX_SCHEMA,
        matrix_id="hostile-chaos-matrix:" + _digest(identity),
        matrix_name=matrix_name,
        cases=validated,
        total_events=total_events,
    )
