"""F2-WP-800 deterministic held-out cognitive micro-world harness.

Evaluator-only state is mechanically separated from the public SUT view. This module is
repository evaluation infrastructure only; it grants no runtime, GRID/GWT/J-Space, effect,
completion, training or world-truth authority.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass, field
import hashlib
import json
import re
from typing import Any

FIXTURE_SCHEMA = "FRANKENSTEIN2_COGNITIVE_MICROWORLD_FIXTURE/v1"
OBSERVATION_SCHEMA = "FRANKENSTEIN2_COGNITIVE_MICROWORLD_OBSERVATION/v1"
ACTION_REQUEST_SCHEMA = "FRANKENSTEIN2_COGNITIVE_MICROWORLD_ACTION_REQUEST/v1"
EPISODE_STATE_SCHEMA = "FRANKENSTEIN2_COGNITIVE_MICROWORLD_EPISODE_STATE/v1"
EVALUATOR_STEP_SCHEMA = "FRANKENSTEIN2_COGNITIVE_MICROWORLD_EVALUATOR_STEP/v1"
RUN_DESCRIPTOR_SCHEMA = "FRANKENSTEIN2_COGNITIVE_MICROWORLD_RUN_DESCRIPTOR/v1"
MATCHED_PAIR_SCHEMA = "FRANKENSTEIN2_COGNITIVE_MICROWORLD_MATCHED_PAIR/v1"
PUBLIC_CLASSIFICATION = "PUBLIC_SUT_VIEW_NO_EVALUATOR_GROUND_TRUTH"
EVALUATOR_CLASSIFICATION = "EVALUATOR_ONLY_NOT_SUT_INPUT_OR_WORLD_AUTHORITY"
RUN_CLASSIFICATION = "EVALUATION_PROVENANCE_NOT_RUNTIME_OR_CAUSAL_CREDIT"
BASELINE = "BASELINE"
INTERVENTION = "INTERVENTION"
_ALLOWED_CONDITIONS = frozenset((BASELINE, INTERVENTION))
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_REFS = 4096
_MAX_STEPS = 1_000_000
_MAX_SCORE_ABS = 1_000_000_000
_EVALUATOR_ORIGIN = object()
_RUN_ORIGIN = object()
_PAIR_ORIGIN = object()


class CognitiveMicroWorldError(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise CognitiveMicroWorldError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise CognitiveMicroWorldError(f"{name} is outside the identifier domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise CognitiveMicroWorldError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _nint(name: str, value: Any, *, minimum: int = 0, maximum: int = _MAX_STEPS) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        kind = "positive" if minimum == 1 else "non-negative"
        raise CognitiveMicroWorldError(f"{name} must be a {kind} integer in [{minimum}, {maximum}]")
    return value


def _score(name: str, value: Any) -> int:
    if type(value) is not int or not -_MAX_SCORE_ABS <= value <= _MAX_SCORE_ABS:
        raise CognitiveMicroWorldError(f"{name} exceeds bounded evaluator score domain")
    return value


def _bool(name: str, value: Any) -> bool:
    if type(value) is not bool:
        raise CognitiveMicroWorldError(f"{name} must be a boolean")
    return value


def _refs(name: str, values: Any, *, nonempty: bool = False) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise CognitiveMicroWorldError(f"{name} must be an immutable tuple")
    if len(values) > _MAX_REFS:
        raise CognitiveMicroWorldError(f"{name} exceeds reference ceiling")
    out = tuple(_id(f"{name} item", value) for value in values)
    if nonempty and not out:
        raise CognitiveMicroWorldError(f"{name} must not be empty")
    if len(out) != len(set(out)):
        raise CognitiveMicroWorldError(f"{name} contains duplicate references")
    if out != tuple(sorted(out)):
        raise CognitiveMicroWorldError(f"{name} must be in canonical lexical order")
    return out


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ActionSpec:
    action_id: str
    payload_ref: str
    payload_sha256: str

    def __post_init__(self) -> None:
        _id("action_id", self.action_id)
        _id("payload_ref", self.payload_ref)
        _sha("payload_sha256", self.payload_sha256)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WorldNode:
    node_id: str
    public_payload_ref: str
    public_payload_sha256: str
    hidden_ground_truth_ref: str
    hidden_ground_truth_sha256: str
    terminal: bool
    evaluator_score: int

    def __post_init__(self) -> None:
        _id("node_id", self.node_id)
        _id("public_payload_ref", self.public_payload_ref)
        _sha("public_payload_sha256", self.public_payload_sha256)
        _id("hidden_ground_truth_ref", self.hidden_ground_truth_ref)
        _sha("hidden_ground_truth_sha256", self.hidden_ground_truth_sha256)
        _bool("terminal", self.terminal)
        _score("evaluator_score", self.evaluator_score)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TransitionRule:
    from_node_id: str
    action_id: str
    to_node_id: str
    transition_ref: str
    transition_sha256: str

    def __post_init__(self) -> None:
        _id("from_node_id", self.from_node_id)
        _id("action_id", self.action_id)
        _id("to_node_id", self.to_node_id)
        _id("transition_ref", self.transition_ref)
        _sha("transition_sha256", self.transition_sha256)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MicroWorldFixture:
    schema: str
    fixture_id: str
    generation: int
    holdout_set_id: str
    initial_node_id: str
    max_steps: int
    actions: tuple[ActionSpec, ...]
    nodes: tuple[WorldNode, ...]
    transitions: tuple[TransitionRule, ...]
    evidence_source_family: str
    primary_source_ids: tuple[str, ...]
    donor_path_family: str
    method_family: str

    def __post_init__(self) -> None:
        if self.schema != FIXTURE_SCHEMA:
            raise CognitiveMicroWorldError("fixture schema mismatch")
        _id("fixture_id", self.fixture_id)
        _nint("generation", self.generation)
        _id("holdout_set_id", self.holdout_set_id)
        _id("initial_node_id", self.initial_node_id)
        _nint("max_steps", self.max_steps, minimum=1)
        _id("evidence_source_family", self.evidence_source_family)
        _refs("primary_source_ids", self.primary_source_ids, nonempty=True)
        _id("donor_path_family", self.donor_path_family)
        _id("method_family", self.method_family)
        if type(self.actions) is not tuple or not self.actions or any(type(x) is not ActionSpec for x in self.actions):
            raise CognitiveMicroWorldError("actions must contain exact concrete ActionSpec values")
        if type(self.nodes) is not tuple or not self.nodes or any(type(x) is not WorldNode for x in self.nodes):
            raise CognitiveMicroWorldError("nodes must contain exact concrete WorldNode values")
        if type(self.transitions) is not tuple or any(type(x) is not TransitionRule for x in self.transitions):
            raise CognitiveMicroWorldError("transitions must contain exact concrete TransitionRule values")
        if self.actions != tuple(sorted(self.actions, key=lambda x: x.action_id)):
            raise CognitiveMicroWorldError("actions must be in canonical action_id order")
        if self.nodes != tuple(sorted(self.nodes, key=lambda x: x.node_id)):
            raise CognitiveMicroWorldError("nodes must be in canonical node_id order")
        action_ids = tuple(x.action_id for x in self.actions)
        node_ids = tuple(x.node_id for x in self.nodes)
        action_set, node_set = set(action_ids), set(node_ids)
        if len(action_set) != len(action_ids):
            raise CognitiveMicroWorldError("action_id values must be unique")
        if len(node_set) != len(node_ids):
            raise CognitiveMicroWorldError("node_id values must be unique")
        if self.initial_node_id not in node_set:
            raise CognitiveMicroWorldError("initial_node_id is not present in nodes")
        if self.transitions != tuple(sorted(self.transitions, key=lambda x: (x.from_node_id, x.action_id))):
            raise CognitiveMicroWorldError("transitions must be in canonical (from_node_id, action_id) order")
        seen: set[tuple[str, str]] = set()
        for rule in self.transitions:
            if rule.from_node_id not in node_set or rule.to_node_id not in node_set:
                raise CognitiveMicroWorldError("transition references unknown node")
            if rule.action_id not in action_set:
                raise CognitiveMicroWorldError("transition references unknown action")
            key = (rule.from_node_id, rule.action_id)
            if key in seen:
                raise CognitiveMicroWorldError("at most one deterministic transition is allowed per node/action pair")
            seen.add(key)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "fixture_id": self.fixture_id,
            "generation": self.generation,
            "holdout_set_id": self.holdout_set_id,
            "initial_node_id": self.initial_node_id,
            "max_steps": self.max_steps,
            "actions": [x.as_dict() for x in self.actions],
            "nodes": [x.as_dict() for x in self.nodes],
            "transitions": [x.as_dict() for x in self.transitions],
            "evidence_source_family": self.evidence_source_family,
            "primary_source_ids": list(self.primary_source_ids),
            "donor_path_family": self.donor_path_family,
            "method_family": self.method_family,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def public_interface_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "fixture_id": self.fixture_id,
            "generation": self.generation,
            "holdout_set_id": self.holdout_set_id,
            "max_steps": self.max_steps,
            "actions": [x.as_dict() for x in self.actions],
        }

    def public_sha256(self) -> str:
        return _digest(self.public_interface_dict())

    def node(self, node_id: str) -> WorldNode:
        _id("node_id", node_id)
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise CognitiveMicroWorldError("unknown evaluator node")

    def transition(self, node_id: str, action_id: str) -> TransitionRule:
        _id("node_id", node_id)
        _id("action_id", action_id)
        for rule in self.transitions:
            if rule.from_node_id == node_id and rule.action_id == action_id:
                return rule
        raise CognitiveMicroWorldError("action has no deterministic transition at current state")


@dataclass(frozen=True, slots=True)
class ObservationView:
    schema: str
    episode_id: str
    episode_generation: int
    fixture_id: str
    fixture_generation: int
    public_fixture_sha256: str
    step_index: int
    observation_ref: str
    observation_sha256: str
    available_action_ids: tuple[str, ...]
    terminal: bool
    classification: str = PUBLIC_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != OBSERVATION_SCHEMA or self.classification != PUBLIC_CLASSIFICATION:
            raise CognitiveMicroWorldError("observation schema/classification mismatch")
        _id("episode_id", self.episode_id)
        _nint("episode_generation", self.episode_generation)
        _id("fixture_id", self.fixture_id)
        _nint("fixture_generation", self.fixture_generation)
        _sha("public_fixture_sha256", self.public_fixture_sha256)
        _nint("step_index", self.step_index)
        _id("observation_ref", self.observation_ref)
        _sha("observation_sha256", self.observation_sha256)
        _refs("available_action_ids", self.available_action_ids, nonempty=True)
        _bool("terminal", self.terminal)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class EpisodeState:
    schema: str
    episode_id: str
    episode_generation: int
    fixture_id: str
    fixture_generation: int
    fixture_sha256: str
    current_node_id: str
    step_index: int
    cumulative_score: int
    classification: str = EVALUATOR_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != EPISODE_STATE_SCHEMA or self.classification != EVALUATOR_CLASSIFICATION:
            raise CognitiveMicroWorldError("episode-state schema/classification mismatch")
        _id("episode_id", self.episode_id)
        _nint("episode_generation", self.episode_generation)
        _id("fixture_id", self.fixture_id)
        _nint("fixture_generation", self.fixture_generation)
        _sha("fixture_sha256", self.fixture_sha256)
        _id("current_node_id", self.current_node_id)
        _nint("step_index", self.step_index)
        _score("cumulative_score", self.cumulative_score)
        if _origin is not _EVALUATOR_ORIGIN:
            raise CognitiveMicroWorldError("EpisodeState must be created by the evaluator transition API")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ActionRequest:
    schema: str
    episode_id: str
    episode_generation: int
    fixture_id: str
    fixture_generation: int
    public_fixture_sha256: str
    step_index: int
    observation_sha256: str
    action_id: str

    def __post_init__(self) -> None:
        if self.schema != ACTION_REQUEST_SCHEMA:
            raise CognitiveMicroWorldError("action-request schema mismatch")
        _id("episode_id", self.episode_id)
        _nint("episode_generation", self.episode_generation)
        _id("fixture_id", self.fixture_id)
        _nint("fixture_generation", self.fixture_generation)
        _sha("public_fixture_sha256", self.public_fixture_sha256)
        _nint("step_index", self.step_index)
        _sha("observation_sha256", self.observation_sha256)
        _id("action_id", self.action_id)

    @classmethod
    def for_observation(cls, observation: ObservationView, *, action_id: str) -> "ActionRequest":
        if type(observation) is not ObservationView:
            raise CognitiveMicroWorldError("observation must be exact concrete ObservationView")
        return cls(
            ACTION_REQUEST_SCHEMA,
            observation.episode_id,
            observation.episode_generation,
            observation.fixture_id,
            observation.fixture_generation,
            observation.public_fixture_sha256,
            observation.step_index,
            observation.sha256(),
            action_id,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class EvaluatorStep:
    schema: str
    fixture_sha256: str
    prior_state_sha256: str
    action_request_sha256: str
    transition_ref: str
    transition_sha256: str
    from_node_id: str
    to_node_id: str
    next_state_sha256: str
    score_delta: int
    classification: str = EVALUATOR_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != EVALUATOR_STEP_SCHEMA or self.classification != EVALUATOR_CLASSIFICATION:
            raise CognitiveMicroWorldError("evaluator-step schema/classification mismatch")
        for name, value in (("fixture_sha256", self.fixture_sha256), ("prior_state_sha256", self.prior_state_sha256), ("action_request_sha256", self.action_request_sha256), ("transition_sha256", self.transition_sha256), ("next_state_sha256", self.next_state_sha256)):
            _sha(name, value)
        _id("transition_ref", self.transition_ref)
        _id("from_node_id", self.from_node_id)
        _id("to_node_id", self.to_node_id)
        _score("score_delta", self.score_delta)
        if _origin is not _EVALUATOR_ORIGIN:
            raise CognitiveMicroWorldError("EvaluatorStep must be created by step_episode")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _assert_fixture_state(fixture: MicroWorldFixture, state: EpisodeState) -> None:
    if type(fixture) is not MicroWorldFixture or type(state) is not EpisodeState:
        raise CognitiveMicroWorldError("fixture/state must be exact concrete harness values")
    if (state.fixture_id, state.fixture_generation, state.fixture_sha256) != (fixture.fixture_id, fixture.generation, fixture.sha256()):
        raise CognitiveMicroWorldError("state fixture digest mismatch")
    fixture.node(state.current_node_id)
    if state.step_index > fixture.max_steps:
        raise CognitiveMicroWorldError("state step index exceeds fixture ceiling")


def observation_for_state(fixture: MicroWorldFixture, state: EpisodeState) -> ObservationView:
    _assert_fixture_state(fixture, state)
    node = fixture.node(state.current_node_id)
    return ObservationView(
        OBSERVATION_SCHEMA,
        state.episode_id,
        state.episode_generation,
        fixture.fixture_id,
        fixture.generation,
        fixture.public_sha256(),
        state.step_index,
        node.public_payload_ref,
        node.public_payload_sha256,
        tuple(x.action_id for x in fixture.actions),
        node.terminal,
    )


def begin_episode(fixture: MicroWorldFixture, *, episode_id: str, episode_generation: int) -> tuple[EpisodeState, ObservationView]:
    if type(fixture) is not MicroWorldFixture:
        raise CognitiveMicroWorldError("fixture must be exact concrete MicroWorldFixture")
    _id("episode_id", episode_id)
    _nint("episode_generation", episode_generation)
    node = fixture.node(fixture.initial_node_id)
    state = EpisodeState(
        EPISODE_STATE_SCHEMA,
        episode_id,
        episode_generation,
        fixture.fixture_id,
        fixture.generation,
        fixture.sha256(),
        node.node_id,
        0,
        node.evaluator_score,
        _origin=_EVALUATOR_ORIGIN,
    )
    return state, observation_for_state(fixture, state)


def step_episode(fixture: MicroWorldFixture, *, state: EpisodeState, request: ActionRequest) -> tuple[EpisodeState, ObservationView, EvaluatorStep]:
    _assert_fixture_state(fixture, state)
    if type(request) is not ActionRequest:
        raise CognitiveMicroWorldError("request must be exact concrete ActionRequest")
    obs = observation_for_state(fixture, state)
    if request.episode_id != state.episode_id:
        raise CognitiveMicroWorldError("action episode_id mismatch")
    if request.episode_generation != state.episode_generation:
        raise CognitiveMicroWorldError("action episode generation mismatch")
    if request.fixture_id != fixture.fixture_id or request.fixture_generation != fixture.generation:
        raise CognitiveMicroWorldError("action fixture identity/generation mismatch")
    if request.public_fixture_sha256 != fixture.public_sha256():
        raise CognitiveMicroWorldError("action public fixture digest mismatch")
    if request.step_index != state.step_index:
        raise CognitiveMicroWorldError("stale or future action step index")
    if request.observation_sha256 != obs.sha256():
        raise CognitiveMicroWorldError("action observation digest mismatch")
    if request.action_id not in set(obs.available_action_ids):
        raise CognitiveMicroWorldError("unknown action_id")
    node = fixture.node(state.current_node_id)
    if node.terminal:
        raise CognitiveMicroWorldError("terminal episode cannot be stepped")
    if state.step_index >= fixture.max_steps:
        raise CognitiveMicroWorldError("episode step ceiling reached")
    rule = fixture.transition(node.node_id, request.action_id)
    next_node = fixture.node(rule.to_node_id)
    total = state.cumulative_score + next_node.evaluator_score
    _score("next cumulative_score", total)
    next_state = EpisodeState(
        EPISODE_STATE_SCHEMA,
        state.episode_id,
        state.episode_generation,
        fixture.fixture_id,
        fixture.generation,
        fixture.sha256(),
        next_node.node_id,
        state.step_index + 1,
        total,
        _origin=_EVALUATOR_ORIGIN,
    )
    evidence = EvaluatorStep(
        EVALUATOR_STEP_SCHEMA,
        fixture.sha256(),
        state.sha256(),
        request.sha256(),
        rule.transition_ref,
        rule.transition_sha256,
        node.node_id,
        next_node.node_id,
        next_state.sha256(),
        next_node.evaluator_score,
        _origin=_EVALUATOR_ORIGIN,
    )
    return next_state, observation_for_state(fixture, next_state), evidence


@dataclass(frozen=True, slots=True)
class RunDescriptor:
    schema: str
    run_id: str
    condition: str
    fixture_id: str
    fixture_generation: int
    fixture_sha256: str
    episode_family_id: str
    system_under_test_ref: str
    evidence_source_family: str
    primary_source_ids: tuple[str, ...]
    donor_path_family: str
    method_family: str
    communication_before_result: bool
    independent_reproduction: bool
    classification: str = RUN_CLASSIFICATION
    _builder_verified: bool = field(init=False, repr=False, compare=False)
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != RUN_DESCRIPTOR_SCHEMA or self.classification != RUN_CLASSIFICATION:
            raise CognitiveMicroWorldError("run descriptor schema/classification mismatch")
        _id("run_id", self.run_id)
        if self.condition not in _ALLOWED_CONDITIONS:
            raise CognitiveMicroWorldError("condition must be BASELINE or INTERVENTION")
        _id("fixture_id", self.fixture_id)
        _nint("fixture_generation", self.fixture_generation)
        _sha("fixture_sha256", self.fixture_sha256)
        _id("episode_family_id", self.episode_family_id)
        _id("system_under_test_ref", self.system_under_test_ref)
        _id("evidence_source_family", self.evidence_source_family)
        _refs("primary_source_ids", self.primary_source_ids, nonempty=True)
        _id("donor_path_family", self.donor_path_family)
        _id("method_family", self.method_family)
        _bool("communication_before_result", self.communication_before_result)
        _bool("independent_reproduction", self.independent_reproduction)
        object.__setattr__(self, "_builder_verified", _origin is _RUN_ORIGIN)

    @classmethod
    def for_fixture(cls, fixture: MicroWorldFixture, *, run_id: str, condition: str, episode_family_id: str, system_under_test_ref: str, communication_before_result: bool, independent_reproduction: bool) -> "RunDescriptor":
        if type(fixture) is not MicroWorldFixture:
            raise CognitiveMicroWorldError("fixture must be exact concrete MicroWorldFixture")
        return cls(
            RUN_DESCRIPTOR_SCHEMA,
            run_id,
            condition,
            fixture.fixture_id,
            fixture.generation,
            fixture.sha256(),
            episode_family_id,
            system_under_test_ref,
            fixture.evidence_source_family,
            fixture.primary_source_ids,
            fixture.donor_path_family,
            fixture.method_family,
            communication_before_result,
            independent_reproduction,
            _origin=_RUN_ORIGIN,
        )

    def assert_matches_fixture(self, fixture: MicroWorldFixture) -> None:
        expected = RunDescriptor.for_fixture(
            fixture,
            run_id=self.run_id,
            condition=self.condition,
            episode_family_id=self.episode_family_id,
            system_under_test_ref=self.system_under_test_ref,
            communication_before_result=self.communication_before_result,
            independent_reproduction=self.independent_reproduction,
        )
        if self != expected:
            raise CognitiveMicroWorldError("run descriptor does not match exact fixture/provenance binding")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "condition": self.condition,
            "fixture_id": self.fixture_id,
            "fixture_generation": self.fixture_generation,
            "fixture_sha256": self.fixture_sha256,
            "episode_family_id": self.episode_family_id,
            "system_under_test_ref": self.system_under_test_ref,
            "evidence_source_family": self.evidence_source_family,
            "primary_source_ids": list(self.primary_source_ids),
            "donor_path_family": self.donor_path_family,
            "method_family": self.method_family,
            "communication_before_result": self.communication_before_result,
            "independent_reproduction": self.independent_reproduction,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class MatchedRunPair:
    schema: str
    pair_id: str
    baseline: RunDescriptor
    intervention: RunDescriptor
    classification: str = RUN_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != MATCHED_PAIR_SCHEMA or self.classification != RUN_CLASSIFICATION:
            raise CognitiveMicroWorldError("matched-pair schema/classification mismatch")
        _id("pair_id", self.pair_id)
        if type(self.baseline) is not RunDescriptor or type(self.intervention) is not RunDescriptor:
            raise CognitiveMicroWorldError("matched pair requires exact concrete RunDescriptor values")
        if self.baseline.condition != BASELINE or self.intervention.condition != INTERVENTION:
            raise CognitiveMicroWorldError("matched pair must contain BASELINE then INTERVENTION")
        if self.baseline.run_id == self.intervention.run_id:
            raise CognitiveMicroWorldError("matched runs must have distinct run_id values")
        for field_name in ("fixture_id", "fixture_generation", "fixture_sha256", "episode_family_id", "evidence_source_family", "primary_source_ids", "donor_path_family", "method_family"):
            if getattr(self.baseline, field_name) != getattr(self.intervention, field_name):
                raise CognitiveMicroWorldError(f"matched pair differs on {field_name}")
        expected = "pair:" + _digest({"baseline_sha256": self.baseline.sha256(), "intervention_sha256": self.intervention.sha256()})
        if self.pair_id != expected:
            raise CognitiveMicroWorldError("pair_id does not bind exact matched run descriptors")
        if not self.baseline._builder_verified or not self.intervention._builder_verified:
            raise CognitiveMicroWorldError("matched runs must originate from RunDescriptor.for_fixture")
        if _origin is not _PAIR_ORIGIN:
            raise CognitiveMicroWorldError("MatchedRunPair must be created by MatchedRunPair.create")

    @classmethod
    def create(cls, *, baseline: RunDescriptor, intervention: RunDescriptor, fixture: MicroWorldFixture | None = None) -> "MatchedRunPair":
        if type(baseline) is not RunDescriptor or type(intervention) is not RunDescriptor:
            raise CognitiveMicroWorldError("matched pair requires exact concrete RunDescriptor values")
        if fixture is not None:
            if type(fixture) is not MicroWorldFixture:
                raise CognitiveMicroWorldError("fixture must be exact concrete MicroWorldFixture")
            baseline.assert_matches_fixture(fixture)
            intervention.assert_matches_fixture(fixture)
        pair_id = "pair:" + _digest({"baseline_sha256": baseline.sha256(), "intervention_sha256": intervention.sha256()})
        return cls(MATCHED_PAIR_SCHEMA, pair_id, baseline, intervention, _origin=_PAIR_ORIGIN)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "pair_id": self.pair_id,
            "baseline": self.baseline.as_dict(),
            "intervention": self.intervention.as_dict(),
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())
