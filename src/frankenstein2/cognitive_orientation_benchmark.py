"""F2-WP-801 held-out ORIENTATION benchmark on the accepted WP800 micro-world.

Only public ObservationView plus public action history reaches the policy logic. Hidden
MicroWorldFixture nodes, transitions, ground truth and evaluator scores remain inside the
runner. This component characterizes benchmark discrimination only; it does not establish
GRID10/GWT/J-Space or whole-system superiority and grants no runtime/effect authority.
"""
from __future__ import annotations

from dataclasses import InitVar, dataclass
import hashlib
import json
import re
from typing import Any

from .cognitive_microworld import (
    BASELINE,
    INTERVENTION,
    ActionRequest,
    CognitiveMicroWorldError,
    MatchedRunPair,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
    begin_episode,
    step_episode,
)

POLICY_SCHEMA = "FRANKENSTEIN2_ORIENTATION_POLICY/v1"
TRACE_ENTRY_SCHEMA = "FRANKENSTEIN2_ORIENTATION_PUBLIC_TRACE_ENTRY/v1"
RESULT_SCHEMA = "FRANKENSTEIN2_ORIENTATION_RUN_RESULT/v1"
COMPARISON_SCHEMA = "FRANKENSTEIN2_ORIENTATION_COMPARISON/v1"

MEMORYLESS_CANONICAL_FIRST = "MEMORYLESS_CANONICAL_FIRST"
BOUNDED_PUBLIC_EXPLORATION = "BOUNDED_PUBLIC_EXPLORATION"
_ALLOWED_MODES = frozenset({MEMORYLESS_CANONICAL_FIRST, BOUNDED_PUBLIC_EXPLORATION})
_ALLOWED_CONDITIONS = frozenset({BASELINE, INTERVENTION})

POLICY_CLASSIFICATION = "PUBLIC_OBSERVATION_ONLY_BASELINE_POLICY_NOT_COGNITIVE_AUTHORITY"
RESULT_CLASSIFICATION = "EVALUATOR_RESULT_NOT_RUNTIME_OR_COGNITIVE_SUPERIORITY_CREDIT"
COMPARISON_CLASSIFICATION = "DESCRIPTIVE_MATCHED_COMPARISON_NOT_CAUSAL_OR_WHOLE_SYSTEM_CREDIT"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_HISTORY = 100_000
_RUNNER_ORIGIN = object()
_COMPARISON_ORIGIN = object()


class OrientationBenchmarkError(ValueError):
    """Fail-closed WP801 benchmark contract error."""


def _identifier(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise OrientationBenchmarkError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN:
        raise OrientationBenchmarkError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise OrientationBenchmarkError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise OrientationBenchmarkError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _nonnegative_int(name: str, value: Any, *, maximum: int = _MAX_HISTORY) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise OrientationBenchmarkError(f"{name} must be an integer in [0, {maximum}]")
    return value


def _positive_int(name: str, value: Any, *, maximum: int = _MAX_HISTORY) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise OrientationBenchmarkError(f"{name} must be an integer in [1, {maximum}]")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OrientationPolicy:
    """Explicit built-in public-only policy configuration."""

    schema: str
    policy_id: str
    mode: str
    max_public_history_entries: int
    classification: str = POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != POLICY_SCHEMA:
            raise OrientationBenchmarkError("policy schema mismatch")
        if self.classification != POLICY_CLASSIFICATION:
            raise OrientationBenchmarkError("policy classification mismatch")
        _identifier("policy_id", self.policy_id)
        if self.mode not in _ALLOWED_MODES:
            raise OrientationBenchmarkError(f"mode must be one of {sorted(_ALLOWED_MODES)}")
        _positive_int("max_public_history_entries", self.max_public_history_entries)

    @classmethod
    def memoryless(cls, *, policy_id: str = "baseline.memoryless-canonical-first.v1") -> "OrientationPolicy":
        return cls(POLICY_SCHEMA, policy_id, MEMORYLESS_CANONICAL_FIRST, 1)

    @classmethod
    def bounded_exploration(
        cls,
        *,
        policy_id: str = "baseline.bounded-public-exploration.v1",
        max_public_history_entries: int = 1024,
    ) -> "OrientationPolicy":
        return cls(
            POLICY_SCHEMA,
            policy_id,
            BOUNDED_PUBLIC_EXPLORATION,
            max_public_history_entries,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "mode": self.mode,
            "max_public_history_entries": self.max_public_history_entries,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class PublicTraceEntry:
    """Policy-visible history only; no evaluator node, transition, score or ground truth."""

    schema: str
    step_index: int
    observation_view_sha256: str
    observation_ref: str
    observation_payload_sha256: str
    action_id: str

    def __post_init__(self) -> None:
        if self.schema != TRACE_ENTRY_SCHEMA:
            raise OrientationBenchmarkError("trace-entry schema mismatch")
        _nonnegative_int("step_index", self.step_index)
        _sha256("observation_view_sha256", self.observation_view_sha256)
        _identifier("observation_ref", self.observation_ref)
        _sha256("observation_payload_sha256", self.observation_payload_sha256)
        _identifier("action_id", self.action_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "step_index": self.step_index,
            "observation_view_sha256": self.observation_view_sha256,
            "observation_ref": self.observation_ref,
            "observation_payload_sha256": self.observation_payload_sha256,
            "action_id": self.action_id,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _select_public_action(
    *,
    policy: OrientationPolicy,
    observation: ObservationView,
    public_history: tuple[PublicTraceEntry, ...],
) -> str:
    """Choose from public fields only. The hidden fixture is intentionally not an argument."""

    if type(policy) is not OrientationPolicy:
        raise OrientationBenchmarkError("policy must be exact concrete OrientationPolicy")
    if type(observation) is not ObservationView:
        raise OrientationBenchmarkError("observation must be exact concrete ObservationView")
    if type(public_history) is not tuple or any(type(item) is not PublicTraceEntry for item in public_history):
        raise OrientationBenchmarkError("public_history must contain exact PublicTraceEntry values")
    if len(public_history) > policy.max_public_history_entries:
        raise OrientationBenchmarkError("public history exceeds policy budget")

    available = tuple(sorted(observation.available_action_ids))
    if not available:
        raise OrientationBenchmarkError("observation has no available public actions")

    if policy.mode == MEMORYLESS_CANONICAL_FIRST:
        return available[0]

    if policy.mode == BOUNDED_PUBLIC_EXPLORATION:
        tried_here = {
            entry.action_id
            for entry in public_history
            if entry.observation_ref == observation.observation_ref
            and entry.observation_payload_sha256 == observation.observation_sha256
        }
        for action_id in available:
            if action_id not in tried_here:
                return action_id
        return available[0]

    raise OrientationBenchmarkError("unreachable unsupported policy mode")


@dataclass(frozen=True, slots=True)
class OrientationRunResult:
    schema: str
    result_id: str
    run_descriptor: RunDescriptor
    policy_id: str
    policy_sha256: str
    episode_id: str
    episode_generation: int
    public_trace: tuple[PublicTraceEntry, ...]
    terminal_reached: bool
    step_budget_exhausted: bool
    steps_used: int
    evaluator_score: int
    final_observation_view_sha256: str
    classification: str = RESULT_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != RESULT_SCHEMA:
            raise OrientationBenchmarkError("result schema mismatch")
        if self.classification != RESULT_CLASSIFICATION:
            raise OrientationBenchmarkError("result classification mismatch")
        _identifier("result_id", self.result_id)
        if type(self.run_descriptor) is not RunDescriptor:
            raise OrientationBenchmarkError("run_descriptor must be exact concrete RunDescriptor")
        _identifier("policy_id", self.policy_id)
        _sha256("policy_sha256", self.policy_sha256)
        _identifier("episode_id", self.episode_id)
        _nonnegative_int("episode_generation", self.episode_generation)
        if type(self.public_trace) is not tuple or any(type(item) is not PublicTraceEntry for item in self.public_trace):
            raise OrientationBenchmarkError("public_trace must contain exact PublicTraceEntry values")
        _nonnegative_int("steps_used", self.steps_used)
        if self.steps_used != len(self.public_trace):
            raise OrientationBenchmarkError("steps_used must equal public trace length")
        if type(self.terminal_reached) is not bool or type(self.step_budget_exhausted) is not bool:
            raise OrientationBenchmarkError("terminal/budget flags must be booleans")
        if self.terminal_reached and self.step_budget_exhausted:
            raise OrientationBenchmarkError("terminal_reached and step_budget_exhausted are mutually exclusive")
        if type(self.evaluator_score) is not int:
            raise OrientationBenchmarkError("evaluator_score must be an integer")
        _sha256("final_observation_view_sha256", self.final_observation_view_sha256)
        if _origin is not _RUNNER_ORIGIN:
            raise OrientationBenchmarkError("OrientationRunResult must be created by run_orientation_policy")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "result_id": self.result_id,
            "run_descriptor": self.run_descriptor.as_dict(),
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "episode_id": self.episode_id,
            "episode_generation": self.episode_generation,
            "public_trace": [entry.as_dict() for entry in self.public_trace],
            "terminal_reached": self.terminal_reached,
            "step_budget_exhausted": self.step_budget_exhausted,
            "steps_used": self.steps_used,
            "evaluator_score": self.evaluator_score,
            "final_observation_view_sha256": self.final_observation_view_sha256,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def run_orientation_policy(
    fixture: MicroWorldFixture,
    *,
    policy: OrientationPolicy,
    run_id: str,
    condition: str,
    episode_family_id: str,
    episode_id: str,
    episode_generation: int,
    system_under_test_ref: str,
    communication_before_result: bool = False,
    independent_reproduction: bool = False,
) -> OrientationRunResult:
    """Run one built-in public-only policy while keeping hidden fixture state evaluator-side."""

    if type(fixture) is not MicroWorldFixture:
        raise OrientationBenchmarkError("fixture must be exact concrete MicroWorldFixture")
    if type(policy) is not OrientationPolicy:
        raise OrientationBenchmarkError("policy must be exact concrete OrientationPolicy")
    if condition not in _ALLOWED_CONDITIONS:
        raise OrientationBenchmarkError("condition must be BASELINE or INTERVENTION")
    _identifier("episode_id", episode_id)
    _nonnegative_int("episode_generation", episode_generation)

    descriptor = RunDescriptor.for_fixture(
        fixture,
        run_id=run_id,
        condition=condition,
        episode_family_id=episode_family_id,
        system_under_test_ref=system_under_test_ref,
        communication_before_result=communication_before_result,
        independent_reproduction=independent_reproduction,
    )
    state, observation = begin_episode(
        fixture,
        episode_id=episode_id,
        episode_generation=episode_generation,
    )
    history: list[PublicTraceEntry] = []

    while not observation.terminal and state.step_index < fixture.max_steps:
        bounded_history = tuple(history[-policy.max_public_history_entries :])
        action_id = _select_public_action(
            policy=policy,
            observation=observation,
            public_history=bounded_history,
        )
        history.append(
            PublicTraceEntry(
                schema=TRACE_ENTRY_SCHEMA,
                step_index=state.step_index,
                observation_view_sha256=observation.sha256(),
                observation_ref=observation.observation_ref,
                observation_payload_sha256=observation.observation_sha256,
                action_id=action_id,
            )
        )
        request = ActionRequest.for_observation(observation, action_id=action_id)
        try:
            state, observation, _ = step_episode(fixture, state=state, request=request)
        except CognitiveMicroWorldError as exc:
            raise OrientationBenchmarkError("public policy selected an unroutable action") from exc

    terminal_reached = observation.terminal
    exhausted = not terminal_reached and state.step_index >= fixture.max_steps
    payload = {
        "run_descriptor_sha256": descriptor.sha256(),
        "policy_sha256": policy.sha256(),
        "episode_id": episode_id,
        "episode_generation": episode_generation,
        "public_trace_sha256": _digest([entry.as_dict() for entry in history]),
        "terminal_reached": terminal_reached,
        "step_budget_exhausted": exhausted,
        "steps_used": len(history),
        "evaluator_score": state.cumulative_score,
        "final_observation_view_sha256": observation.sha256(),
    }
    return OrientationRunResult(
        schema=RESULT_SCHEMA,
        result_id="orientation-result:" + _digest(payload),
        run_descriptor=descriptor,
        policy_id=policy.policy_id,
        policy_sha256=policy.sha256(),
        episode_id=episode_id,
        episode_generation=episode_generation,
        public_trace=tuple(history),
        terminal_reached=terminal_reached,
        step_budget_exhausted=exhausted,
        steps_used=len(history),
        evaluator_score=state.cumulative_score,
        final_observation_view_sha256=observation.sha256(),
        _origin=_RUNNER_ORIGIN,
    )


@dataclass(frozen=True, slots=True)
class OrientationComparison:
    schema: str
    comparison_id: str
    matched_pair: MatchedRunPair
    baseline_result_sha256: str
    intervention_result_sha256: str
    evaluator_score_delta: int
    steps_used_delta: int
    terminal_delta: str
    classification: str = COMPARISON_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != COMPARISON_SCHEMA:
            raise OrientationBenchmarkError("comparison schema mismatch")
        if self.classification != COMPARISON_CLASSIFICATION:
            raise OrientationBenchmarkError("comparison classification mismatch")
        _identifier("comparison_id", self.comparison_id)
        if type(self.matched_pair) is not MatchedRunPair:
            raise OrientationBenchmarkError("matched_pair must be exact concrete MatchedRunPair")
        _sha256("baseline_result_sha256", self.baseline_result_sha256)
        _sha256("intervention_result_sha256", self.intervention_result_sha256)
        if type(self.evaluator_score_delta) is not int or type(self.steps_used_delta) is not int:
            raise OrientationBenchmarkError("comparison deltas must be integers")
        if self.terminal_delta not in {"SAME", "BASELINE_ONLY", "INTERVENTION_ONLY"}:
            raise OrientationBenchmarkError("unsupported terminal_delta")
        if _origin is not _COMPARISON_ORIGIN:
            raise OrientationBenchmarkError("OrientationComparison must be created by compare_orientation_runs")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "comparison_id": self.comparison_id,
            "matched_pair": self.matched_pair.as_dict(),
            "baseline_result_sha256": self.baseline_result_sha256,
            "intervention_result_sha256": self.intervention_result_sha256,
            "evaluator_score_delta": self.evaluator_score_delta,
            "steps_used_delta": self.steps_used_delta,
            "terminal_delta": self.terminal_delta,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def compare_orientation_runs(
    fixture: MicroWorldFixture,
    *,
    baseline: OrientationRunResult,
    intervention: OrientationRunResult,
) -> OrientationComparison:
    """Produce descriptive matched comparison; no causal or system-superiority promotion."""

    if type(fixture) is not MicroWorldFixture:
        raise OrientationBenchmarkError("fixture must be exact concrete MicroWorldFixture")
    if type(baseline) is not OrientationRunResult or type(intervention) is not OrientationRunResult:
        raise OrientationBenchmarkError("comparison requires exact concrete OrientationRunResult values")
    if baseline.run_descriptor.condition != BASELINE:
        raise OrientationBenchmarkError("baseline result must have BASELINE condition")
    if intervention.run_descriptor.condition != INTERVENTION:
        raise OrientationBenchmarkError("intervention result must have INTERVENTION condition")
    if (baseline.episode_id, baseline.episode_generation) != (
        intervention.episode_id,
        intervention.episode_generation,
    ):
        raise OrientationBenchmarkError("matched orientation runs must use the same episode identity/generation")

    pair = MatchedRunPair.create(
        fixture=fixture,
        baseline=baseline.run_descriptor,
        intervention=intervention.run_descriptor,
    )
    if baseline.terminal_reached == intervention.terminal_reached:
        terminal_delta = "SAME"
    elif baseline.terminal_reached:
        terminal_delta = "BASELINE_ONLY"
    else:
        terminal_delta = "INTERVENTION_ONLY"

    payload = {
        "matched_pair_sha256": pair.sha256(),
        "baseline_result_sha256": baseline.sha256(),
        "intervention_result_sha256": intervention.sha256(),
    }
    return OrientationComparison(
        schema=COMPARISON_SCHEMA,
        comparison_id="orientation-comparison:" + _digest(payload),
        matched_pair=pair,
        baseline_result_sha256=baseline.sha256(),
        intervention_result_sha256=intervention.sha256(),
        evaluator_score_delta=intervention.evaluator_score - baseline.evaluator_score,
        steps_used_delta=intervention.steps_used - baseline.steps_used,
        terminal_delta=terminal_delta,
        _origin=_COMPARISON_ORIGIN,
    )


__all__ = [
    "BOUNDED_PUBLIC_EXPLORATION",
    "COMPARISON_CLASSIFICATION",
    "COMPARISON_SCHEMA",
    "MEMORYLESS_CANONICAL_FIRST",
    "OrientationBenchmarkError",
    "OrientationComparison",
    "OrientationPolicy",
    "OrientationRunResult",
    "POLICY_CLASSIFICATION",
    "POLICY_SCHEMA",
    "PublicTraceEntry",
    "RESULT_CLASSIFICATION",
    "RESULT_SCHEMA",
    "TRACE_ENTRY_SCHEMA",
    "compare_orientation_runs",
    "run_orientation_policy",
]
