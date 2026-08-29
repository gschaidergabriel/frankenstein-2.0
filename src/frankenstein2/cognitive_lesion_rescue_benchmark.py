"""F2-WP-806 deterministic cognitive lesion/rescue benchmark.

The tested policy boundary receives only exact public ``ObservationView`` values plus
explicit immutable public capability/condition configuration. The evaluator may use the
full WP800 fixture to advance and score an episode, but evaluator-only nodes,
transitions, scores and hidden-ground-truth fields never enter policy input.

Generation 2 hardens experiment identity and interpretation. Matched rescue must act in
the exact declared lesion universe, score/operator semantics are first-class sealed
identity, and positive language is derived only from measured deltas using conservative
bounded labels.

This is repository evaluation infrastructure only. A lesion/rescue delta is a benchmark
measurement; it grants no runtime, physical GRID10, GWT/J-Space, training, effect,
completion, causal-localization or whole-system authority.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass, field
import hashlib
import json
import re
from typing import Any

from .cognitive_microworld import (
    BASELINE,
    INTERVENTION,
    ActionRequest,
    CognitiveMicroWorldError,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
    begin_episode,
    step_episode,
)

CAPABILITY_SCHEMA = "FRANKENSTEIN2_COGNITIVE_PUBLIC_CAPABILITY/v1"
CONDITION_SCHEMA = "FRANKENSTEIN2_COGNITIVE_LESION_CONDITION/v1"
RESULT_SCHEMA = "FRANKENSTEIN2_COGNITIVE_LESION_RUN_RESULT/v1"
COMPARISON_SCHEMA = "FRANKENSTEIN2_COGNITIVE_LESION_RESCUE_COMPARISON/v2"

NORMAL = "NORMAL"
LESION = "LESION"
RESCUE = "RESCUE"
_ALLOWED_KINDS = frozenset((NORMAL, LESION, RESCUE))

TESTED_INTERVENTION_DEPENDENCE = "TESTED_INTERVENTION_DEPENDENCE"
TARGET_SPECIFIC_RESTORATION_AT_SCOPE = "TARGET_SPECIFIC_RESTORATION_AT_SCOPE"
REDUNDANCY_OR_INTERACTION_UNKNOWN = "REDUNDANCY_OR_INTERACTION_UNKNOWN"
NO_RESTORATION_AT_SCOPE = "NO_RESTORATION_AT_SCOPE"
_ALLOWED_INTERPRETATIONS = frozenset(
    (
        TESTED_INTERVENTION_DEPENDENCE,
        TARGET_SPECIFIC_RESTORATION_AT_SCOPE,
        REDUNDANCY_OR_INTERACTION_UNKNOWN,
        NO_RESTORATION_AT_SCOPE,
    )
)

DEFAULT_SCORE_METRIC_ID = "evaluator-final-score-delta"
DEFAULT_SCORE_METRIC_VERSION = "1"
DEFAULT_LESION_OPERATOR_ID = "public-capability-disable/v1"
DEFAULT_RESCUE_OPERATOR_ID = "public-capability-restore-subset/v1"

PUBLIC_POLICY_CLASSIFICATION = "PUBLIC_POLICY_CONFIG_NO_EVALUATOR_GROUND_TRUTH"
EVALUATOR_RESULT_CLASSIFICATION = "EVALUATOR_MEASUREMENT_NOT_RUNTIME_OR_CAUSAL_CREDIT"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_CAPABILITIES = 4096
_MAX_STEPS = 1_000_000
_CONDITION_ORIGIN = object()
_RESULT_ORIGIN = object()
_COMPARISON_ORIGIN = object()


class CognitiveLesionRescueError(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise CognitiveLesionRescueError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise CognitiveLesionRescueError(f"{name} is outside the identifier domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise CognitiveLesionRescueError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _nint(name: str, value: Any, *, maximum: int = _MAX_STEPS) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise CognitiveLesionRescueError(
            f"{name} must be a non-negative integer in [0, {maximum}]"
        )
    return value


def _refs(name: str, values: Any) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise CognitiveLesionRescueError(f"{name} must be an immutable tuple")
    if len(values) > _MAX_CAPABILITIES:
        raise CognitiveLesionRescueError(f"{name} exceeds capability ceiling")
    out = tuple(_id(f"{name} item", value) for value in values)
    if len(out) != len(set(out)):
        raise CognitiveLesionRescueError(f"{name} contains duplicate references")
    if out != tuple(sorted(out)):
        raise CognitiveLesionRescueError(f"{name} must be in canonical lexical order")
    return out


def _json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class PublicCapability:
    schema: str
    capability_id: str
    action_id: str
    rank: int
    classification: str = PUBLIC_POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if (
            self.schema != CAPABILITY_SCHEMA
            or self.classification != PUBLIC_POLICY_CLASSIFICATION
        ):
            raise CognitiveLesionRescueError(
                "public capability schema/classification mismatch"
            )
        _id("capability_id", self.capability_id)
        _id("action_id", self.action_id)
        _nint("rank", self.rank, maximum=1_000_000)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CognitiveCondition:
    schema: str
    condition_id: str
    condition_kind: str
    fixture_id: str
    fixture_generation: int
    public_fixture_sha256: str
    disabled_capability_ids: tuple[str, ...]
    rescued_capability_ids: tuple[str, ...]
    classification: str = PUBLIC_POLICY_CLASSIFICATION
    _builder_verified: bool = field(init=False, repr=False, compare=False)
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if (
            self.schema != CONDITION_SCHEMA
            or self.classification != PUBLIC_POLICY_CLASSIFICATION
        ):
            raise CognitiveLesionRescueError("condition schema/classification mismatch")
        _id("condition_id", self.condition_id)
        if self.condition_kind not in _ALLOWED_KINDS:
            raise CognitiveLesionRescueError(
                "condition_kind must be NORMAL, LESION or RESCUE"
            )
        _id("fixture_id", self.fixture_id)
        _nint("fixture_generation", self.fixture_generation)
        _sha("public_fixture_sha256", self.public_fixture_sha256)
        disabled = _refs("disabled_capability_ids", self.disabled_capability_ids)
        rescued = _refs("rescued_capability_ids", self.rescued_capability_ids)
        if not set(rescued).issubset(disabled):
            raise CognitiveLesionRescueError(
                "rescued capabilities must be a subset of explicitly lesioned capabilities"
            )
        if self.condition_kind == NORMAL and (disabled or rescued):
            raise CognitiveLesionRescueError(
                "NORMAL cannot disable or rescue capabilities"
            )
        if self.condition_kind == LESION and (not disabled or rescued):
            raise CognitiveLesionRescueError(
                "LESION requires disabled capabilities and no rescue"
            )
        if self.condition_kind == RESCUE and (not disabled or not rescued):
            raise CognitiveLesionRescueError(
                "RESCUE requires an explicit lesion and explicit rescued subset"
            )
        expected = "condition:" + _digest(self._identity_payload())
        if self.condition_id != expected:
            raise CognitiveLesionRescueError(
                "condition_id does not seal exact public condition identity"
            )
        object.__setattr__(self, "_builder_verified", _origin is _CONDITION_ORIGIN)

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "condition_kind": self.condition_kind,
            "fixture_id": self.fixture_id,
            "fixture_generation": self.fixture_generation,
            "public_fixture_sha256": self.public_fixture_sha256,
            "disabled_capability_ids": list(self.disabled_capability_ids),
            "rescued_capability_ids": list(self.rescued_capability_ids),
            "classification": self.classification,
        }

    @classmethod
    def for_observation(
        cls,
        observation: ObservationView,
        *,
        condition_kind: str,
        disabled_capability_ids: tuple[str, ...] = (),
        rescued_capability_ids: tuple[str, ...] = (),
    ) -> "CognitiveCondition":
        if type(observation) is not ObservationView:
            raise CognitiveLesionRescueError(
                "observation must be exact concrete ObservationView"
            )
        payload = {
            "schema": CONDITION_SCHEMA,
            "condition_kind": condition_kind,
            "fixture_id": observation.fixture_id,
            "fixture_generation": observation.fixture_generation,
            "public_fixture_sha256": observation.public_fixture_sha256,
            "disabled_capability_ids": list(disabled_capability_ids),
            "rescued_capability_ids": list(rescued_capability_ids),
            "classification": PUBLIC_POLICY_CLASSIFICATION,
        }
        return cls(
            CONDITION_SCHEMA,
            "condition:" + _digest(payload),
            condition_kind,
            observation.fixture_id,
            observation.fixture_generation,
            observation.public_fixture_sha256,
            disabled_capability_ids,
            rescued_capability_ids,
            _origin=_CONDITION_ORIGIN,
        )

    def assert_matches_observation(self, observation: ObservationView) -> None:
        if type(observation) is not ObservationView:
            raise CognitiveLesionRescueError(
                "observation must be exact concrete ObservationView"
            )
        if not self._builder_verified:
            raise CognitiveLesionRescueError(
                "condition must originate from CognitiveCondition.for_observation"
            )
        if (
            self.fixture_id,
            self.fixture_generation,
            self.public_fixture_sha256,
        ) != (
            observation.fixture_id,
            observation.fixture_generation,
            observation.public_fixture_sha256,
        ):
            raise CognitiveLesionRescueError(
                "condition does not match exact public fixture identity"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "condition_id": self.condition_id,
            **self._identity_payload(),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ConditionRunResult:
    schema: str
    condition_id: str
    condition_kind: str
    run_id: str
    run_sha256: str
    episode_id: str
    episode_generation: int
    fixture_id: str
    fixture_generation: int
    fixture_sha256: str
    public_fixture_sha256: str
    capability_set_sha256: str
    observation_sha256s: tuple[str, ...]
    action_request_sha256s: tuple[str, ...]
    evaluator_step_sha256s: tuple[str, ...]
    final_score: int
    step_count: int
    terminal: bool
    abstained: bool
    classification: str = EVALUATOR_RESULT_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if (
            self.schema != RESULT_SCHEMA
            or self.classification != EVALUATOR_RESULT_CLASSIFICATION
        ):
            raise CognitiveLesionRescueError("result schema/classification mismatch")
        _id("condition_id", self.condition_id)
        if self.condition_kind not in _ALLOWED_KINDS:
            raise CognitiveLesionRescueError("invalid result condition_kind")
        _id("run_id", self.run_id)
        _sha("run_sha256", self.run_sha256)
        _id("episode_id", self.episode_id)
        _nint("episode_generation", self.episode_generation)
        _id("fixture_id", self.fixture_id)
        _nint("fixture_generation", self.fixture_generation)
        _sha("fixture_sha256", self.fixture_sha256)
        _sha("public_fixture_sha256", self.public_fixture_sha256)
        _sha("capability_set_sha256", self.capability_set_sha256)
        for group_name, group in (
            ("observation_sha256s", self.observation_sha256s),
            ("action_request_sha256s", self.action_request_sha256s),
            ("evaluator_step_sha256s", self.evaluator_step_sha256s),
        ):
            if type(group) is not tuple:
                raise CognitiveLesionRescueError(
                    f"{group_name} must be immutable tuple"
                )
            for value in group:
                _sha(f"{group_name} item", value)
        if type(self.final_score) is not int:
            raise CognitiveLesionRescueError(
                "final_score must be an integer evaluator measurement"
            )
        _nint("step_count", self.step_count)
        if type(self.terminal) is not bool or type(self.abstained) is not bool:
            raise CognitiveLesionRescueError("terminal/abstained must be booleans")
        if (
            len(self.action_request_sha256s) != self.step_count
            or len(self.evaluator_step_sha256s) != self.step_count
        ):
            raise CognitiveLesionRescueError(
                "step_count does not bind request/evaluator evidence lengths"
            )
        if len(self.observation_sha256s) != self.step_count + 1:
            raise CognitiveLesionRescueError(
                "observation evidence must include initial plus every resulting observation"
            )
        if _origin is not _RESULT_ORIGIN:
            raise CognitiveLesionRescueError(
                "ConditionRunResult must be created by run_condition"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "condition_id": self.condition_id,
            "condition_kind": self.condition_kind,
            "run_id": self.run_id,
            "run_sha256": self.run_sha256,
            "episode_id": self.episode_id,
            "episode_generation": self.episode_generation,
            "fixture_id": self.fixture_id,
            "fixture_generation": self.fixture_generation,
            "fixture_sha256": self.fixture_sha256,
            "public_fixture_sha256": self.public_fixture_sha256,
            "capability_set_sha256": self.capability_set_sha256,
            "observation_sha256s": list(self.observation_sha256s),
            "action_request_sha256s": list(self.action_request_sha256s),
            "evaluator_step_sha256s": list(self.evaluator_step_sha256s),
            "final_score": self.final_score,
            "step_count": self.step_count,
            "terminal": self.terminal,
            "abstained": self.abstained,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _validate_capabilities(
    observation: ObservationView,
    capabilities: tuple[PublicCapability, ...],
) -> tuple[PublicCapability, ...]:
    if type(observation) is not ObservationView:
        raise CognitiveLesionRescueError(
            "observation must be exact concrete ObservationView"
        )
    if type(capabilities) is not tuple or not capabilities:
        raise CognitiveLesionRescueError(
            "capabilities must be a non-empty immutable tuple"
        )
    if len(capabilities) > _MAX_CAPABILITIES or any(
        type(item) is not PublicCapability for item in capabilities
    ):
        raise CognitiveLesionRescueError(
            "capabilities must contain exact concrete PublicCapability values"
        )
    if capabilities != tuple(
        sorted(capabilities, key=lambda x: (x.rank, x.capability_id, x.action_id))
    ):
        raise CognitiveLesionRescueError(
            "capabilities must be in canonical rank/capability/action order"
        )
    capability_ids = tuple(item.capability_id for item in capabilities)
    action_ids = tuple(item.action_id for item in capabilities)
    if len(capability_ids) != len(set(capability_ids)):
        raise CognitiveLesionRescueError("capability_id values must be unique")
    if len(action_ids) != len(set(action_ids)):
        raise CognitiveLesionRescueError(
            "public benchmark capability actions must be unique"
        )
    available = set(observation.available_action_ids)
    if any(action_id not in available for action_id in action_ids):
        raise CognitiveLesionRescueError(
            "capability references action unavailable in public ObservationView"
        )
    return capabilities


def _capability_digest(capabilities: tuple[PublicCapability, ...]) -> str:
    return _digest([item.as_dict() for item in capabilities])


def choose_action_public(
    observation: ObservationView,
    *,
    capabilities: tuple[PublicCapability, ...],
    condition: CognitiveCondition,
) -> str | None:
    """Return an action using public inputs only, or ``None`` for explicit abstention."""
    if type(observation) is not ObservationView:
        raise CognitiveLesionRescueError(
            "observation must be exact concrete ObservationView"
        )
    if type(condition) is not CognitiveCondition:
        raise CognitiveLesionRescueError(
            "condition must be exact concrete CognitiveCondition"
        )
    condition.assert_matches_observation(observation)
    caps = _validate_capabilities(observation, capabilities)
    known = {item.capability_id for item in caps}
    disabled = set(condition.disabled_capability_ids)
    rescued = set(condition.rescued_capability_ids)
    if not disabled.issubset(known):
        raise CognitiveLesionRescueError(
            "condition disables unknown public capability"
        )
    if not rescued.issubset(known):
        raise CognitiveLesionRescueError(
            "condition rescues unknown public capability"
        )
    for item in caps:
        enabled = item.capability_id not in disabled or item.capability_id in rescued
        if enabled:
            return item.action_id
    return None


def run_condition(
    fixture: MicroWorldFixture,
    *,
    run: RunDescriptor,
    condition: CognitiveCondition,
    capabilities: tuple[PublicCapability, ...],
    episode_id: str,
    episode_generation: int,
) -> ConditionRunResult:
    if type(fixture) is not MicroWorldFixture:
        raise CognitiveLesionRescueError(
            "fixture must be exact concrete MicroWorldFixture"
        )
    if type(run) is not RunDescriptor:
        raise CognitiveLesionRescueError(
            "run must be exact concrete RunDescriptor"
        )
    if type(condition) is not CognitiveCondition:
        raise CognitiveLesionRescueError(
            "condition must be exact concrete CognitiveCondition"
        )
    _id("episode_id", episode_id)
    _nint("episode_generation", episode_generation)
    try:
        run.assert_matches_fixture(fixture)
    except CognitiveMicroWorldError as exc:
        raise CognitiveLesionRescueError(str(exc)) from exc
    if condition.condition_kind == NORMAL and run.condition != BASELINE:
        raise CognitiveLesionRescueError(
            "NORMAL requires a BASELINE run descriptor"
        )
    if condition.condition_kind in (LESION, RESCUE) and run.condition != INTERVENTION:
        raise CognitiveLesionRescueError(
            "LESION/RESCUE require INTERVENTION run descriptors"
        )

    state, observation = begin_episode(
        fixture,
        episode_id=episode_id,
        episode_generation=episode_generation,
    )
    condition.assert_matches_observation(observation)
    caps = _validate_capabilities(observation, capabilities)
    observations = [observation.sha256()]
    requests: list[str] = []
    evaluator_steps: list[str] = []
    abstained = False

    while not observation.terminal and state.step_index < fixture.max_steps:
        action_id = choose_action_public(
            observation,
            capabilities=caps,
            condition=condition,
        )
        if action_id is None:
            abstained = True
            break
        request = ActionRequest.for_observation(observation, action_id=action_id)
        try:
            state, observation, evaluator_step = step_episode(
                fixture,
                state=state,
                request=request,
            )
        except CognitiveMicroWorldError as exc:
            raise CognitiveLesionRescueError(str(exc)) from exc
        requests.append(request.sha256())
        evaluator_steps.append(evaluator_step.sha256())
        observations.append(observation.sha256())

    return ConditionRunResult(
        RESULT_SCHEMA,
        condition.condition_id,
        condition.condition_kind,
        run.run_id,
        run.sha256(),
        episode_id,
        episode_generation,
        fixture.fixture_id,
        fixture.generation,
        fixture.sha256(),
        fixture.public_sha256(),
        _capability_digest(caps),
        tuple(observations),
        tuple(requests),
        tuple(evaluator_steps),
        state.cumulative_score,
        len(requests),
        observation.terminal,
        abstained,
        _origin=_RESULT_ORIGIN,
    )


def _interpret_measured_deltas(
    *,
    lesion_delta: int,
    rescue_delta: int,
    restoration_gap: int,
) -> str:
    """Return a deliberately bounded interpretation from measured score deltas only."""
    if (
        type(lesion_delta) is not int
        or type(rescue_delta) is not int
        or type(restoration_gap) is not int
    ):
        raise CognitiveLesionRescueError("measured deltas must be exact integers")
    if lesion_delta == 0:
        return REDUNDANCY_OR_INTERACTION_UNKNOWN
    if restoration_gap == 0 and rescue_delta == -lesion_delta:
        return TARGET_SPECIFIC_RESTORATION_AT_SCOPE
    if abs(restoration_gap) < abs(lesion_delta):
        return TESTED_INTERVENTION_DEPENDENCE
    return NO_RESTORATION_AT_SCOPE


@dataclass(frozen=True, slots=True)
class LesionRescueComparison:
    schema: str
    comparison_id: str
    normal: ConditionRunResult
    lesion: ConditionRunResult
    rescue: ConditionRunResult
    score_metric_id: str
    score_metric_version: str
    lesion_operator_id: str
    rescue_operator_id: str
    lesion_delta: int
    rescue_delta: int
    restoration_gap: int
    interpretation: str
    classification: str = EVALUATOR_RESULT_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if (
            self.schema != COMPARISON_SCHEMA
            or self.classification != EVALUATOR_RESULT_CLASSIFICATION
        ):
            raise CognitiveLesionRescueError("comparison schema/classification mismatch")
        _id("comparison_id", self.comparison_id)
        for name in (
            "score_metric_id",
            "score_metric_version",
            "lesion_operator_id",
            "rescue_operator_id",
        ):
            _id(name, getattr(self, name))
        if self.interpretation not in _ALLOWED_INTERPRETATIONS:
            raise CognitiveLesionRescueError(
                "unknown bounded comparison interpretation"
            )
        if (
            type(self.normal) is not ConditionRunResult
            or type(self.lesion) is not ConditionRunResult
            or type(self.rescue) is not ConditionRunResult
        ):
            raise CognitiveLesionRescueError(
                "comparison requires exact concrete run results"
            )
        if (
            self.normal.condition_kind,
            self.lesion.condition_kind,
            self.rescue.condition_kind,
        ) != (NORMAL, LESION, RESCUE):
            raise CognitiveLesionRescueError(
                "comparison result order must be NORMAL, LESION, RESCUE"
            )
        identity = lambda r: (
            r.fixture_id,
            r.fixture_generation,
            r.fixture_sha256,
            r.public_fixture_sha256,
            r.capability_set_sha256,
        )
        if (
            identity(self.normal) != identity(self.lesion)
            or identity(self.normal) != identity(self.rescue)
        ):
            raise CognitiveLesionRescueError(
                "comparison results are not matched on exact fixture/capability identity"
            )
        if self.lesion_delta != self.lesion.final_score - self.normal.final_score:
            raise CognitiveLesionRescueError("lesion_delta mismatch")
        if self.rescue_delta != self.rescue.final_score - self.lesion.final_score:
            raise CognitiveLesionRescueError("rescue_delta mismatch")
        if self.restoration_gap != self.rescue.final_score - self.normal.final_score:
            raise CognitiveLesionRescueError("restoration_gap mismatch")
        expected_interpretation = _interpret_measured_deltas(
            lesion_delta=self.lesion_delta,
            rescue_delta=self.rescue_delta,
            restoration_gap=self.restoration_gap,
        )
        if self.interpretation != expected_interpretation:
            raise CognitiveLesionRescueError(
                "interpretation does not match measured-delta semantics"
            )
        expected = "comparison:" + _digest(self._identity_payload())
        if self.comparison_id != expected:
            raise CognitiveLesionRescueError(
                "comparison_id does not bind exact run and experiment semantics"
            )
        if _origin is not _COMPARISON_ORIGIN:
            raise CognitiveLesionRescueError(
                "comparison must be created by run_matched_lesion_rescue"
            )

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "normal": self.normal.sha256(),
            "lesion": self.lesion.sha256(),
            "rescue": self.rescue.sha256(),
            "score_metric_id": self.score_metric_id,
            "score_metric_version": self.score_metric_version,
            "lesion_operator_id": self.lesion_operator_id,
            "rescue_operator_id": self.rescue_operator_id,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "comparison_id": self.comparison_id,
            "normal": self.normal.as_dict(),
            "lesion": self.lesion.as_dict(),
            "rescue": self.rescue.as_dict(),
            "score_metric_id": self.score_metric_id,
            "score_metric_version": self.score_metric_version,
            "lesion_operator_id": self.lesion_operator_id,
            "rescue_operator_id": self.rescue_operator_id,
            "lesion_delta": self.lesion_delta,
            "rescue_delta": self.rescue_delta,
            "restoration_gap": self.restoration_gap,
            "interpretation": self.interpretation,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _assert_matched_runs(
    normal: RunDescriptor,
    lesion: RunDescriptor,
    rescue: RunDescriptor,
    fixture: MicroWorldFixture,
) -> None:
    if any(type(run) is not RunDescriptor for run in (normal, lesion, rescue)):
        raise CognitiveLesionRescueError(
            "matched runs require exact concrete RunDescriptor values"
        )
    try:
        for run in (normal, lesion, rescue):
            run.assert_matches_fixture(fixture)
    except CognitiveMicroWorldError as exc:
        raise CognitiveLesionRescueError(str(exc)) from exc
    if (
        normal.condition != BASELINE
        or lesion.condition != INTERVENTION
        or rescue.condition != INTERVENTION
    ):
        raise CognitiveLesionRescueError(
            "matched run conditions must be BASELINE, INTERVENTION, INTERVENTION"
        )
    if len({normal.run_id, lesion.run_id, rescue.run_id}) != 3:
        raise CognitiveLesionRescueError(
            "matched runs require three distinct run_id values"
        )
    for field_name in (
        "fixture_id",
        "fixture_generation",
        "fixture_sha256",
        "episode_family_id",
        "evidence_source_family",
        "primary_source_ids",
        "donor_path_family",
        "method_family",
        "communication_before_result",
        "independent_reproduction",
    ):
        if (
            getattr(normal, field_name) != getattr(lesion, field_name)
            or getattr(normal, field_name) != getattr(rescue, field_name)
        ):
            raise CognitiveLesionRescueError(f"matched runs differ on {field_name}")


def run_matched_lesion_rescue(
    fixture: MicroWorldFixture,
    *,
    normal_run: RunDescriptor,
    lesion_run: RunDescriptor,
    rescue_run: RunDescriptor,
    normal_condition: CognitiveCondition,
    lesion_condition: CognitiveCondition,
    rescue_condition: CognitiveCondition,
    capabilities: tuple[PublicCapability, ...],
    episode_generation: int,
    score_metric_id: str = DEFAULT_SCORE_METRIC_ID,
    score_metric_version: str = DEFAULT_SCORE_METRIC_VERSION,
    lesion_operator_id: str = DEFAULT_LESION_OPERATOR_ID,
    rescue_operator_id: str = DEFAULT_RESCUE_OPERATOR_ID,
) -> LesionRescueComparison:
    if type(fixture) is not MicroWorldFixture:
        raise CognitiveLesionRescueError(
            "fixture must be exact concrete MicroWorldFixture"
        )
    _assert_matched_runs(normal_run, lesion_run, rescue_run, fixture)
    if any(
        type(c) is not CognitiveCondition
        for c in (normal_condition, lesion_condition, rescue_condition)
    ):
        raise CognitiveLesionRescueError(
            "matched conditions require exact concrete CognitiveCondition values"
        )
    if (
        normal_condition.condition_kind,
        lesion_condition.condition_kind,
        rescue_condition.condition_kind,
    ) != (NORMAL, LESION, RESCUE):
        raise CognitiveLesionRescueError(
            "matched conditions must be NORMAL, LESION, RESCUE"
        )
    if (
        rescue_condition.disabled_capability_ids
        != lesion_condition.disabled_capability_ids
    ):
        raise CognitiveLesionRescueError(
            "matched rescue must use the same disabled capability universe as lesion"
        )
    for name, value in (
        ("score_metric_id", score_metric_id),
        ("score_metric_version", score_metric_version),
        ("lesion_operator_id", lesion_operator_id),
        ("rescue_operator_id", rescue_operator_id),
    ):
        _id(name, value)

    normal_id = f"{normal_run.episode_family_id}:normal"
    lesion_id = f"{normal_run.episode_family_id}:lesion"
    rescue_id = f"{normal_run.episode_family_id}:rescue"
    normal_result = run_condition(
        fixture,
        run=normal_run,
        condition=normal_condition,
        capabilities=capabilities,
        episode_id=normal_id,
        episode_generation=episode_generation,
    )
    lesion_result = run_condition(
        fixture,
        run=lesion_run,
        condition=lesion_condition,
        capabilities=capabilities,
        episode_id=lesion_id,
        episode_generation=episode_generation,
    )
    rescue_result = run_condition(
        fixture,
        run=rescue_run,
        condition=rescue_condition,
        capabilities=capabilities,
        episode_id=rescue_id,
        episode_generation=episode_generation,
    )
    lesion_delta = lesion_result.final_score - normal_result.final_score
    rescue_delta = rescue_result.final_score - lesion_result.final_score
    restoration_gap = rescue_result.final_score - normal_result.final_score
    interpretation = _interpret_measured_deltas(
        lesion_delta=lesion_delta,
        rescue_delta=rescue_delta,
        restoration_gap=restoration_gap,
    )
    identity_payload = {
        "normal": normal_result.sha256(),
        "lesion": lesion_result.sha256(),
        "rescue": rescue_result.sha256(),
        "score_metric_id": score_metric_id,
        "score_metric_version": score_metric_version,
        "lesion_operator_id": lesion_operator_id,
        "rescue_operator_id": rescue_operator_id,
    }
    comparison_id = "comparison:" + _digest(identity_payload)
    return LesionRescueComparison(
        COMPARISON_SCHEMA,
        comparison_id,
        normal_result,
        lesion_result,
        rescue_result,
        score_metric_id,
        score_metric_version,
        lesion_operator_id,
        rescue_operator_id,
        lesion_delta,
        rescue_delta,
        restoration_gap,
        interpretation,
        _origin=_COMPARISON_ORIGIN,
    )
