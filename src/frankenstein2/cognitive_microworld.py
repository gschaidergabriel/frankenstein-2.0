"""F2-WP-800 deterministic held-out cognitive micro-world harness.

The harness separates evaluator-only world state from the public observation/action
surface presented to a system under test (SUT). It is evaluation infrastructure only:
it does not execute GRID10, models, providers, tools, effects, UnifiedDB writes or
real-world actions, and it does not mint runtime/GWT/J-Space/training credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
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


class CognitiveMicroWorldError(ValueError):
    """Fail-closed validation or transition error for the WP800 harness."""


def _identifier(name: str, value: Any) -> str:
    if type(value) is not str:
        raise CognitiveMicroWorldError(f"{name} must be a string")
    if not value or value != value.strip():
        raise CognitiveMicroWorldError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise CognitiveMicroWorldError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CognitiveMicroWorldError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise CognitiveMicroWorldError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _nonnegative_int(name: str, value: Any, *, maximum: int | None = None) -> int:
    if type(value) is not int or value < 0:
        raise CognitiveMicroWorldError(f"{name} must be a non-negative integer")
    if maximum is not None and value > maximum:
        raise CognitiveMicroWorldError(f"{name} exceeds {maximum}")
    return value


def _positive_int(name: str, value: Any, *, maximum: int | None = None) -> int:
    if type(value) is not int or value < 1:
        raise CognitiveMicroWorldError(f"{name} must be a positive integer")
    if maximum is not None and value > maximum:
        raise CognitiveMicroWorldError(f"{name} exceeds {maximum}")
    return value


def _score(name: str, value: Any) -> int:
    if type(value) is not int or not -_MAX_SCORE_ABS <= value <= _MAX_SCORE_ABS:
        raise CognitiveMicroWorldError(
            f"{name} must be an integer in [-{_MAX_SCORE_ABS}, {_MAX_SCORE_ABS}]"
        )
    return value


def _boolean(name: str, value: Any) -> bool:
    if type(value) is not bool:
        raise CognitiveMicroWorldError(f"{name} must be a boolean")
    return value


def _refs(name: str, value: Any, *, require_nonempty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise CognitiveMicroWorldError(f"{name} must be an immutable tuple")
    if len(value) > _MAX_REFS:
        raise CognitiveMicroWorldError(f"{name} exceeds {_MAX_REFS} references")
    cleaned = tuple(_identifier(f"{name} item", item) for item in value)
    if len(set(cleaned)) != len(cleaned):
        raise CognitiveMicroWorldError(f"{name} must not contain duplicates")
    if cleaned != tuple(sorted(cleaned)):
        raise CognitiveMicroWorldError(f"{name} must be in canonical lexical order")
    if require_nonempty and not cleaned:
        raise CognitiveMicroWorldError(f"{name} must contain at least one reference")
    return cleaned


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
class ActionSpec:
    """Public action token. It contains no transition or evaluator-state semantics."""

    action_id: str
    payload_ref: str
    payload_sha256: str

    def __post_init__(self) -> None:
        _identifier("action_id", self.action_id)
        _identifier("payload_ref", self.payload_ref)
        _sha256("payload_sha256", self.payload_sha256)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WorldNode:
    """Evaluator-only node. Hidden fields never appear in ObservationView."""

    node_id: str
    public_payload_ref: str
    public_payload_sha256: str
    hidden_ground_truth_ref: str
    hidden_ground_truth_sha256: str
    terminal: bool
    evaluator_score: int

    def __post_init__(self) -> None:
        _identifier("node_id", self.node_id)
        _identifier("public_payload_ref", self.public_payload_ref)
        _sha256("public_payload_sha256", self.public_payload_sha256)
        _identifier("hidden_ground_truth_ref", self.hidden_ground_truth_ref)
        _sha256("hidden_ground_truth_sha256", self.hidden_ground_truth_sha256)
        _boolean("terminal", self.terminal)
        _score("evaluator_score", self.evaluator_score)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TransitionRule:
    """Evaluator-only deterministic transition keyed by (node_id, action_id)."""

    from_node_id: str
    action_id: str
    to_node_id: str
    transition_ref: str
    transition_sha256: str

    def __post_init__(self) -> None:
        _identifier("from_node_id", self.from_node_id)
        _identifier("action_id", self.action_id)
        _identifier("to_node_id", self.to_node_id)
        _identifier("transition_ref", self.transition_ref)
        _sha256("transition_sha256", self.transition_sha256)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MicroWorldFixture:
    """Complete held-out evaluator fixture.

    ``sha256`` binds hidden state and transitions for scorer/replay integrity.
    ``public_sha256`` binds only the SUT-visible interface, avoiding a digest side-channel
    from hidden evaluator state into the tested component.
    """

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
        _identifier("fixture_id", self.fixture_id)
        _nonnegative_int("generation", self.generation)
        _identifier("holdout_set_id", self.holdout_set_id)
        _identifier("initial_node_id", self.initial_node_id)
        _positive_int("max_steps", self.max_steps, maximum=_MAX_STEPS)
        _identifier("evidence_source_family", self.evidence_source_family)
        _identifier("donor_path_family", self.donor_path_family)
        _identifier("method_family", self.method_family)
        _refs("primary_source_ids", self.primary_source_ids, require_nonempty=True)

        if type(self.actions) is not tuple or not self.actions:
            raise CognitiveMicroWorldError("actions must be a non-empty immutable tuple")
        if type(self.nodes) is not tuple or not self.nodes:
            raise CognitiveMicroWorldError("nodes must be a non-empty immutable tuple")
        if type(self.transitions) is not tuple:
            raise CognitiveMicroWorldError("transitions must be an immutable tuple")
        if any(type(item) is not ActionSpec for item in self.actions):
            raise CognitiveMicroWorldError("actions must contain exact concrete ActionSpec values")
        if any(type(item) is not WorldNode for item in self.nodes):
            raise CognitiveMicroWorldError("nodes must contain exact concrete WorldNode values")
        if any(type(item) is not TransitionRule for item in self.transitions):
            raise CognitiveMicroWorldError(
                "transitions must contain exact concrete TransitionRule values"
            )

        action_ids = tuple(action.action_id for action in self.actions)
        node_ids = tuple(node.node_id for node in self.nodes)
        action_id_set = set(action_ids)
        node_id_set = set(node_ids)
        if len(action_id_set) != len(action_ids):
            raise CognitiveMicroWorldError("action_id values must be unique")
        if len(node_id_set) != len(node_ids):
            raise CognitiveMicroWorldError("node_id values must be unique")
        if self.actions != tuple(sorted(self.actions, key=lambda item: item.action_id)):
            raise CognitiveMicroWorldError("actions must be in canonical action_id order")
        if self.nodes != tuple(sorted(self.nodes, key=lambda item: item.node_id)):
            raise CognitiveMicroWorldError("nodes must be in canonical node_id order")
        if self.initial_node_id not in node_id_set:
            raise CognitiveMicroWorldError("initial_node_id is not present in nodes")

        seen_edges: set[tuple[str, str]] = set()
        for rule in self.transitions:
            if rule.from_node_id not in node_id_set or rule.to_node_id not in node_id_set:
                raise CognitiveMicroWorldError("transition references unknown node")
            if rule.action_id not in action_id_set:
                raise CognitiveMicroWorldError("transition references unknown action")
            key = (rule.from_node_id, rule.action_id)
            if key in seen_edges:
                raise CognitiveMicroWorldError(
                    "at most one deterministic transition is allowed per node/action pair"
                )
            seen_edges.add(key)
        ordered = tuple(
            sorted(self.transitions, key=lambda item: (item.from_node_id, item.action_id))
        )
        if self.transitions != ordered:
            raise CognitiveMicroWorldError(
                "transitions must be in canonical (from_node_id, action_id) order"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "fixture_id": self.fixture_id,
            "generation": self.generation,
            "holdout_set_id": self.holdout_set_id,
            "initial_node_id": self.initial_node_id,
            "max_steps": self.max_steps,
            "actions": [action.as_dict() for action in self.actions],
            "nodes": [node.as_dict() for node in self.nodes],
            "transitions": [rule.as_dict() for rule in self.transitions],
            "evidence_source_family": self.evidence_source_family,
            "primary_source_ids": list(self.primary_source_ids),
            "donor_path_family": self.donor_path_family,
            "method_family": self.method_family,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def public_interface_dict(self) -> dict[str, Any]:
        return {
            "schema": FIXTURE_SCHEMA,
            "fixture_id": self.fixture_id,
            "generation": self.generation,
            "holdout_set_id": self.holdout_set_id,
            "max_steps": self.max_steps,
            "actions": [action.as_dict() for action in self.actions],
        }

    def public_sha256(self) -> str:
        return _digest(self.public_interface_dict())

    def node(self, node_id: str) -> WorldNode:
        _identifier("node_id", node_id)
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise CognitiveMicroWorldError("unknown evaluator node")

    def transition(self, node_id: str, action_id: str) -> TransitionRule:
        _identifier("node_id", node_id)
        _identifier("action_id", action_id)
        for rule in self.transitions:
            if rule.from_node_id == node_id and rule.action_id == action_id:
                return rule
        raise CognitiveMicroWorldError("action has no deterministic transition at current state")


@dataclass(frozen=True, slots=True)
class ObservationView:
    """The only world-state object intended for the SUT."""

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
        if self.schema != OBSERVATION_SCHEMA:
            raise CognitiveMicroWorldError("observation schema mismatch")
        if self.classification != PUBLIC_CLASSIFICATION:
            raise CognitiveMicroWorldError("observation classification mismatch")
        _identifier("episode_id", self.episode_id)
        _nonnegative_int("episode_generation", self.episode_generation)
        _identifier("fixture_id", self.fixture_id)
        _nonnegative_int("fixture_generation", self.fixture_generation)
        _sha256("public_fixture_sha256", self.public_fixture_sha256)
        _nonnegative_int("step_index", self.step_index, maximum=_MAX_STEPS)
        _identifier("observation_ref", self.observation_ref)
        _sha256("observation_sha256", self.observation_sha256)
        _refs("available_action_ids", self.available_action_ids, require_nonempty=True)
        _boolean("terminal", self.terminal)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class EpisodeState:
    """Evaluator-only episode state; never a SUT input."""

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

    def __post_init__(self) -> None:
        if self.schema != EPISODE_STATE_SCHEMA:
            raise CognitiveMicroWorldError("episode-state schema mismatch")
        if self.classification != EVALUATOR_CLASSIFICATION:
            raise CognitiveMicroWorldError("episode-state classification mismatch")
        _identifier("episode_id", self.episode_id)
        _nonnegative_int("episode_generation", self.episode_generation)
        _identifier("fixture_id", self.fixture_id)
        _nonnegative_int("fixture_generation", self.fixture_generation)
        _sha256("fixture_sha256", self.fixture_sha256)
        _identifier("current_node_id", self.current_node_id)
        _nonnegative_int("step_index", self.step_index, maximum=_MAX_STEPS)
        _score("cumulative_score", self.cumulative_score)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ActionRequest:
    """SUT-produced action token bound to one exact public observation."""

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
        _identifier("episode_id", self.episode_id)
        _nonnegative_int("episode_generation", self.episode_generation)
        _identifier("fixture_id", self.fixture_id)
        _nonnegative_int("fixture_generation", self.fixture_generation)
        _sha256("public_fixture_sha256", self.public_fixture_sha256)
        _nonnegative_int("step_index", self.step_index, maximum=_MAX_STEPS)
        _sha256("observation_sha256", self.observation_sha256)
        _identifier("action_id", self.action_id)

    @classmethod
    def for_observation(cls, observation: ObservationView, *, action_id: str) -> "ActionRequest":
        if type(observation) is not ObservationView:
            raise CognitiveMicroWorldError("observation must be exact concrete ObservationView")
        return cls(
            schema=ACTION_REQUEST_SCHEMA,
            episode_id=observation.episode_id,
            episode_generation=observation.episode_generation,
            fixture_id=observation.fixture_id,
            fixture_generation=observation.fixture_generation,
            public_fixture_sha256=observation.public_fixture_sha256,
            step_index=observation.step_index,
            observation_sha256=observation.sha256(),
            action_id=action_id,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class EvaluatorStep:
    """Evaluator-only transition evidence. It must never be fed to the SUT."""

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

    def __post_init__(self) -> None:
        if self.schema != EVALUATOR_STEP_SCHEMA:
            raise CognitiveMicroWorldError("evaluator-step schema mismatch")
        if self.classification != EVALUATOR_CLASSIFICATION:
            raise CognitiveMicroWorldError("evaluator-step classification mismatch")
        _sha256("fixture_sha256", self.fixture_sha256)
        _sha256("prior_state_sha256", self.prior_state_sha256)
        _sha256("action_request_sha256", self.action_request_sha256)
        _identifier("transition_ref", self.transition_ref)
        _sha256("transition_sha256", self.transition_sha256)
        _identifier("from_node_id", self.from_node_id)
        _identifier("to_node_id", self.to_node_id)
        _sha256("next_state_sha256", self.next_state_sha256)
        _score("score_delta", self.score_delta)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _assert_fixture_state(fixture: MicroWorldFixture, state: EpisodeState) -> None:
    if type(fixture) is not MicroWorldFixture:
        raise CognitiveMicroWorldError("fixture must be exact concrete MicroWorldFixture")
    if type(state) is not EpisodeState:
        raise CognitiveMicroWorldError("state must be exact concrete EpisodeState")
    if state.fixture_id != fixture.fixture_id:
        raise CognitiveMicroWorldError("state fixture_id mismatch")
    if state.fixture_generation != fixture.generation:
        raise CognitiveMicroWorldError("state fixture generation mismatch")
    if state.fixture_sha256 != fixture.sha256():
        raise CognitiveMicroWorldError("state fixture digest mismatch")
    fixture.node(state.current_node_id)
    if state.step_index > fixture.max_steps:
        raise CognitiveMicroWorldError("state step index exceeds fixture ceiling")


def observation_for_state(fixture: MicroWorldFixture, state: EpisodeState) -> ObservationView:
    """Project evaluator state into the deliberately smaller public SUT view."""

    _assert_fixture_state(fixture, state)
    node = fixture.node(state.current_node_id)
    return ObservationView(
        schema=OBSERVATION_SCHEMA,
        episode_id=state.episode_id,
        episode_generation=state.episode_generation,
        fixture_id=fixture.fixture_id,
        fixture_generation=fixture.generation,
        public_fixture_sha256=fixture.public_sha256(),
        step_index=state.step_index,
        observation_ref=node.public_payload_ref,
        observation_sha256=node.public_payload_sha256,
        available_action_ids=tuple(action.action_id for action in fixture.actions),
        terminal=node.terminal,
    )


def begin_episode(
    fixture: MicroWorldFixture,
    *,
    episode_id: str,
    episode_generation: int,
) -> tuple[EpisodeState, ObservationView]:
    if type(fixture) is not MicroWorldFixture:
        raise CognitiveMicroWorldError("fixture must be exact concrete MicroWorldFixture")
    _identifier("episode_id", episode_id)
    _nonnegative_int("episode_generation", episode_generation)
    initial = fixture.node(fixture.initial_node_id)
    state = EpisodeState(
        schema=EPISODE_STATE_SCHEMA,
        episode_id=episode_id,
        episode_generation=episode_generation,
        fixture_id=fixture.fixture_id,
        fixture_generation=fixture.generation,
        fixture_sha256=fixture.sha256(),
        current_node_id=initial.node_id,
        step_index=0,
        cumulative_score=initial.evaluator_score,
    )
    return state, observation_for_state(fixture, state)


def step_episode(
    fixture: MicroWorldFixture,
    *,
    state: EpisodeState,
    request: ActionRequest,
) -> tuple[EpisodeState, ObservationView, EvaluatorStep]:
    """Apply exactly one deterministic evaluator transition.

    The caller must expose only the returned ObservationView to the SUT. EpisodeState and
    EvaluatorStep are explicitly evaluator-only and include hidden node/scoring identity.
    """

    _assert_fixture_state(fixture, state)
    if type(request) is not ActionRequest:
        raise CognitiveMicroWorldError("request must be exact concrete ActionRequest")
    current_observation = observation_for_state(fixture, state)
    if request.episode_id != state.episode_id:
        raise CognitiveMicroWorldError("action episode_id mismatch")
    if request.episode_generation != state.episode_generation:
        raise CognitiveMicroWorldError("action episode generation mismatch")
    if request.fixture_id != fixture.fixture_id:
        raise CognitiveMicroWorldError("action fixture_id mismatch")
    if request.fixture_generation != fixture.generation:
        raise CognitiveMicroWorldError("action fixture generation mismatch")
    if request.public_fixture_sha256 != fixture.public_sha256():
        raise CognitiveMicroWorldError("action public fixture digest mismatch")
    if request.step_index != state.step_index:
        raise CognitiveMicroWorldError("stale or future action step index")
    if request.observation_sha256 != current_observation.sha256():
        raise CognitiveMicroWorldError("action observation digest mismatch")
    if request.action_id not in set(current_observation.available_action_ids):
        raise CognitiveMicroWorldError("unknown action_id")
    current_node = fixture.node(state.current_node_id)
    if current_node.terminal:
        raise CognitiveMicroWorldError("terminal episode cannot be stepped")
    if state.step_index >= fixture.max_steps:
        raise CognitiveMicroWorldError("episode step ceiling reached")

    rule = fixture.transition(current_node.node_id, request.action_id)
    next_node = fixture.node(rule.to_node_id)
    next_score = state.cumulative_score + next_node.evaluator_score
    _score("next cumulative_score", next_score)
    next_state = EpisodeState(
        schema=EPISODE_STATE_SCHEMA,
        episode_id=state.episode_id,
        episode_generation=state.episode_generation,
        fixture_id=fixture.fixture_id,
        fixture_generation=fixture.generation,
        fixture_sha256=fixture.sha256(),
        current_node_id=next_node.node_id,
        step_index=state.step_index + 1,
        cumulative_score=next_score,
    )
    evidence = EvaluatorStep(
        schema=EVALUATOR_STEP_SCHEMA,
        fixture_sha256=fixture.sha256(),
        prior_state_sha256=state.sha256(),
        action_request_sha256=request.sha256(),
        transition_ref=rule.transition_ref,
        transition_sha256=rule.transition_sha256,
        from_node_id=current_node.node_id,
        to_node_id=next_node.node_id,
        next_state_sha256=next_state.sha256(),
        score_delta=next_node.evaluator_score,
    )
    return next_state, observation_for_state(fixture, next_state), evidence


@dataclass(frozen=True, slots=True)
class RunDescriptor:
    """Evaluator-side run/provenance identity for matched baseline/ablation evidence."""

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

    def __post_init__(self) -> None:
        if self.schema != RUN_DESCRIPTOR_SCHEMA:
            raise CognitiveMicroWorldError("run descriptor schema mismatch")
        if self.classification != RUN_CLASSIFICATION:
            raise CognitiveMicroWorldError("run descriptor classification mismatch")
        _identifier("run_id", self.run_id)
        if self.condition not in _ALLOWED_CONDITIONS:
            raise CognitiveMicroWorldError("condition must be BASELINE or INTERVENTION")
        _identifier("fixture_id", self.fixture_id)
        _nonnegative_int("fixture_generation", self.fixture_generation)
        _sha256("fixture_sha256", self.fixture_sha256)
        _identifier("episode_family_id", self.episode_family_id)
        _identifier("system_under_test_ref", self.system_under_test_ref)
        _identifier("evidence_source_family", self.evidence_source_family)
        _refs("primary_source_ids", self.primary_source_ids, require_nonempty=True)
        _identifier("donor_path_family", self.donor_path_family)
        _identifier("method_family", self.method_family)
        _boolean("communication_before_result", self.communication_before_result)
        _boolean("independent_reproduction", self.independent_reproduction)

    @classmethod
    def for_fixture(
        cls,
        fixture: MicroWorldFixture,
        *,
        run_id: str,
        condition: str,
        episode_family_id: str,
        system_under_test_ref: str,
        communication_before_result: bool,
        independent_reproduction: bool,
    ) -> "RunDescriptor":
        if type(fixture) is not MicroWorldFixture:
            raise CognitiveMicroWorldError("fixture must be exact concrete MicroWorldFixture")
        return cls(
            schema=RUN_DESCRIPTOR_SCHEMA,
            run_id=run_id,
            condition=condition,
            fixture_id=fixture.fixture_id,
            fixture_generation=fixture.generation,
            fixture_sha256=fixture.sha256(),
            episode_family_id=episode_family_id,
            system_under_test_ref=system_under_test_ref,
            evidence_source_family=fixture.evidence_source_family,
            primary_source_ids=fixture.primary_source_ids,
            donor_path_family=fixture.donor_path_family,
            method_family=fixture.method_family,
            communication_before_result=communication_before_result,
            independent_reproduction=independent_reproduction,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class MatchedRunPair:
    """Exact matched-pair identity; it does not itself establish causal superiority."""

    schema: str
    pair_id: str
    baseline: RunDescriptor
    intervention: RunDescriptor
    classification: str = RUN_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != MATCHED_PAIR_SCHEMA:
            raise CognitiveMicroWorldError("matched-pair schema mismatch")
        if self.classification != RUN_CLASSIFICATION:
            raise CognitiveMicroWorldError("matched-pair classification mismatch")
        _identifier("pair_id", self.pair_id)
        if type(self.baseline) is not RunDescriptor or type(self.intervention) is not RunDescriptor:
            raise CognitiveMicroWorldError("matched pair requires exact concrete RunDescriptor values")
        if self.baseline.condition != BASELINE or self.intervention.condition != INTERVENTION:
            raise CognitiveMicroWorldError("matched pair must contain BASELINE then INTERVENTION")
        if self.baseline.run_id == self.intervention.run_id:
            raise CognitiveMicroWorldError("matched runs must have distinct run_id values")
        exact_match_fields = (
            "fixture_id",
            "fixture_generation",
            "fixture_sha256",
            "episode_family_id",
            "evidence_source_family",
            "primary_source_ids",
            "donor_path_family",
            "method_family",
        )
        for field in exact_match_fields:
            if getattr(self.baseline, field) != getattr(self.intervention, field):
                raise CognitiveMicroWorldError(f"matched pair differs on {field}")
        expected = "pair:" + _digest(
            {
                "baseline_sha256": self.baseline.sha256(),
                "intervention_sha256": self.intervention.sha256(),
            }
        )
        if self.pair_id != expected:
            raise CognitiveMicroWorldError("pair_id does not bind exact matched run descriptors")

    @classmethod
    def create(
        cls,
        *,
        baseline: RunDescriptor,
        intervention: RunDescriptor,
    ) -> "MatchedRunPair":
        if type(baseline) is not RunDescriptor or type(intervention) is not RunDescriptor:
            raise CognitiveMicroWorldError("matched pair requires exact concrete RunDescriptor values")
        pair_id = "pair:" + _digest(
            {
                "baseline_sha256": baseline.sha256(),
                "intervention_sha256": intervention.sha256(),
            }
        )
        return cls(
            schema=MATCHED_PAIR_SCHEMA,
            pair_id=pair_id,
            baseline=baseline,
            intervention=intervention,
        )

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
