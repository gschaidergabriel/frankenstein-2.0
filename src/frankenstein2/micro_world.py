"""Deterministic held-out interactive micro-world harness.

F2-WP-800 generation 1.

This module provides a tiny pure-state environment for cognitive falsification tests.
Canonical environment truth is kept mechanically separate from agent-visible observations.
The harness performs no model/provider/tool calls, no durable-state writes, no effects and
no completion minting.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

MICRO_WORLD_SCENARIO_SCHEMA = "FRANKENSTEIN2_MICRO_WORLD_SCENARIO/v1"
MICRO_WORLD_RUN_STATE_SCHEMA = "FRANKENSTEIN2_MICRO_WORLD_RUN_STATE/v1"
MICRO_WORLD_OBSERVATION_SCHEMA = "FRANKENSTEIN2_MICRO_WORLD_OBSERVATION/v1"
MICRO_WORLD_PARTITION_SCHEMA = "FRANKENSTEIN2_MICRO_WORLD_PARTITION/v1"

SPLIT_DEVELOPMENT = "DEVELOPMENT"
SPLIT_HELD_OUT = "HELD_OUT"

TRANSITION_APPLIED = "APPLIED"
TRANSITION_BLOCKED = "BLOCKED_PRECONDITION"
TRANSITION_MAX_STEPS = "MAX_STEPS_REACHED"

AUTHORITY_BOUNDARY = (
    "MICRO_WORLD_TEST_HARNESS_NOT_WORLD_TRUTH_EFFECT_COMPLETION_OR_RUNTIME_AUTHORITY"
)

_MAX_ID_LEN = 256
_MAX_KEYS = 128
_MAX_ACTIONS = 64
_MAX_STEPS = 10_000
_STATE_TOKEN = object()
_OBSERVATION_TOKEN = object()

Scalar = str | int | bool | None


class MicroWorldError(ValueError):
    """Fail-closed micro-world contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise MicroWorldError(f"{name} must be a string")
    if not value or value != value.strip():
        raise MicroWorldError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise MicroWorldError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise MicroWorldError(f"{name} contains control characters")
    return value


def _scalar(name: str, value: Any) -> Scalar:
    if value is None or isinstance(value, (str, bool)):
        return value
    if type(value) is int:
        if abs(value) > 10**12:
            raise MicroWorldError(f"{name} integer exceeds canonical bound")
        return value
    raise MicroWorldError(f"{name} must be a canonical scalar (str/int/bool/null)")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _pairs(name: str, values: Mapping[str, Scalar] | Iterable[tuple[str, Scalar]]) -> tuple[tuple[str, Scalar], ...]:
    if isinstance(values, Mapping):
        items = tuple(values.items())
    else:
        items = tuple(values)
    if len(items) > _MAX_KEYS:
        raise MicroWorldError(f"{name} exceeds {_MAX_KEYS} entries")
    normalized: list[tuple[str, Scalar]] = []
    seen: set[str] = set()
    for raw_key, raw_value in items:
        key = _identifier(f"{name}.key", raw_key)
        if key in seen:
            raise MicroWorldError(f"{name} contains duplicate key {key!r}")
        seen.add(key)
        normalized.append((key, _scalar(f"{name}[{key}]", raw_value)))
    return tuple(sorted(normalized, key=lambda item: item[0]))


def _keys(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise MicroWorldError(f"{name} must be an iterable of keys")
    normalized = tuple(_identifier(name, value) for value in values)
    if len(normalized) > _MAX_KEYS:
        raise MicroWorldError(f"{name} exceeds {_MAX_KEYS} keys")
    if len(set(normalized)) != len(normalized):
        raise MicroWorldError(f"{name} contains duplicate keys")
    return tuple(sorted(normalized))


def _state_dict(values: tuple[tuple[str, Scalar], ...]) -> dict[str, Scalar]:
    return {key: value for key, value in values}


def _validate_sha256(name: str, value: Any) -> str:
    value = _identifier(name, value)
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise MicroWorldError(f"{name} must be lowercase 64-hex SHA-256")
    return value


@dataclass(frozen=True, slots=True)
class Condition:
    key: str
    equals: Scalar

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _identifier("condition.key", self.key))
        object.__setattr__(self, "equals", _scalar("condition.equals", self.equals))


@dataclass(frozen=True, slots=True)
class ActionSpec:
    action_id: str
    preconditions: tuple[Condition, ...]
    updates: tuple[tuple[str, Scalar], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", _identifier("action_id", self.action_id))
        if not isinstance(self.preconditions, tuple) or not all(
            isinstance(item, Condition) for item in self.preconditions
        ):
            raise MicroWorldError("preconditions must be a tuple of Condition values")
        if len({item.key for item in self.preconditions}) != len(self.preconditions):
            raise MicroWorldError("preconditions contain duplicate keys")
        object.__setattr__(self, "updates", _pairs("updates", self.updates))


@dataclass(frozen=True, slots=True)
class MicroWorldScenario:
    schema: str
    scenario_id: str
    generation: int
    split: str
    initial_state: tuple[tuple[str, Scalar], ...]
    visible_keys: tuple[str, ...]
    actions: tuple[ActionSpec, ...]
    terminal_conditions: tuple[Condition, ...]
    max_steps: int
    authority_boundary: str = AUTHORITY_BOUNDARY

    def __post_init__(self) -> None:
        if self.schema != MICRO_WORLD_SCENARIO_SCHEMA:
            raise MicroWorldError("scenario schema mismatch")
        object.__setattr__(self, "scenario_id", _identifier("scenario_id", self.scenario_id))
        if type(self.generation) is not int or self.generation < 1:
            raise MicroWorldError("generation must be a positive integer")
        if self.split not in {SPLIT_DEVELOPMENT, SPLIT_HELD_OUT}:
            raise MicroWorldError("unsupported split")
        initial_state = _pairs("initial_state", self.initial_state)
        if not initial_state:
            raise MicroWorldError("initial_state must not be empty")
        object.__setattr__(self, "initial_state", initial_state)
        visible_keys = _keys("visible_keys", self.visible_keys)
        state_keys = {key for key, _ in initial_state}
        if not set(visible_keys).issubset(state_keys):
            raise MicroWorldError("visible_keys must be present in initial_state")
        object.__setattr__(self, "visible_keys", visible_keys)
        if not isinstance(self.actions, tuple) or not self.actions:
            raise MicroWorldError("actions must be a non-empty tuple")
        if len(self.actions) > _MAX_ACTIONS:
            raise MicroWorldError(f"actions exceeds {_MAX_ACTIONS}")
        if not all(isinstance(item, ActionSpec) for item in self.actions):
            raise MicroWorldError("actions must contain ActionSpec values")
        if len({item.action_id for item in self.actions}) != len(self.actions):
            raise MicroWorldError("actions contain duplicate action_id")
        for action in self.actions:
            referenced = {item.key for item in action.preconditions} | {key for key, _ in action.updates}
            if not referenced.issubset(state_keys):
                raise MicroWorldError("action references unknown state key")
        if not isinstance(self.terminal_conditions, tuple) or not all(
            isinstance(item, Condition) for item in self.terminal_conditions
        ):
            raise MicroWorldError("terminal_conditions must be a tuple of Condition values")
        if len({item.key for item in self.terminal_conditions}) != len(self.terminal_conditions):
            raise MicroWorldError("terminal_conditions contain duplicate keys")
        if not {item.key for item in self.terminal_conditions}.issubset(state_keys):
            raise MicroWorldError("terminal condition references unknown state key")
        if type(self.max_steps) is not int or self.max_steps < 1 or self.max_steps > _MAX_STEPS:
            raise MicroWorldError(f"max_steps must be an integer in [1, {_MAX_STEPS}]")
        if self.authority_boundary != AUTHORITY_BOUNDARY:
            raise MicroWorldError("scenario authority boundary mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, init=False)
class MicroWorldRunState:
    schema: str
    scenario_id: str
    scenario_generation: int
    scenario_sha256: str
    step_index: int
    world_state: tuple[tuple[str, Scalar], ...]
    terminal: bool
    authority_boundary: str

    def __init__(
        self,
        *,
        schema: str,
        scenario_id: str,
        scenario_generation: int,
        scenario_sha256: str,
        step_index: int,
        world_state: tuple[tuple[str, Scalar], ...],
        terminal: bool,
        authority_boundary: str,
        _token: object | None = None,
    ) -> None:
        if _token is not _STATE_TOKEN:
            raise MicroWorldError("MicroWorldRunState must be created by the harness")
        if schema != MICRO_WORLD_RUN_STATE_SCHEMA:
            raise MicroWorldError("run-state schema mismatch")
        scenario_id = _identifier("scenario_id", scenario_id)
        if type(scenario_generation) is not int or scenario_generation < 1:
            raise MicroWorldError("scenario_generation must be positive integer")
        scenario_sha256 = _validate_sha256("scenario_sha256", scenario_sha256)
        if type(step_index) is not int or step_index < 0:
            raise MicroWorldError("step_index must be a non-negative integer")
        world_state = _pairs("world_state", world_state)
        if type(terminal) is not bool:
            raise MicroWorldError("terminal must be boolean")
        if authority_boundary != AUTHORITY_BOUNDARY:
            raise MicroWorldError("run-state authority boundary mismatch")
        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "scenario_id", scenario_id)
        object.__setattr__(self, "scenario_generation", scenario_generation)
        object.__setattr__(self, "scenario_sha256", scenario_sha256)
        object.__setattr__(self, "step_index", step_index)
        object.__setattr__(self, "world_state", world_state)
        object.__setattr__(self, "terminal", terminal)
        object.__setattr__(self, "authority_boundary", authority_boundary)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, init=False)
class MicroWorldObservation:
    schema: str
    episode_id: str
    step_index: int
    visible_state: tuple[tuple[str, Scalar], ...]
    action_ids: tuple[str, ...]
    last_action_id: str | None
    transition_class: str | None
    terminal: bool
    authority_boundary: str

    def __init__(
        self,
        *,
        schema: str,
        episode_id: str,
        step_index: int,
        visible_state: tuple[tuple[str, Scalar], ...],
        action_ids: tuple[str, ...],
        last_action_id: str | None,
        transition_class: str | None,
        terminal: bool,
        authority_boundary: str,
        _token: object | None = None,
    ) -> None:
        if _token is not _OBSERVATION_TOKEN:
            raise MicroWorldError("MicroWorldObservation must be created by the harness")
        if schema != MICRO_WORLD_OBSERVATION_SCHEMA:
            raise MicroWorldError("observation schema mismatch")
        episode_id = _identifier("episode_id", episode_id)
        if type(step_index) is not int or step_index < 0:
            raise MicroWorldError("step_index must be non-negative integer")
        visible_state = _pairs("visible_state", visible_state)
        action_ids = _keys("action_ids", action_ids)
        if last_action_id is not None:
            last_action_id = _identifier("last_action_id", last_action_id)
        if transition_class not in {None, TRANSITION_APPLIED, TRANSITION_BLOCKED, TRANSITION_MAX_STEPS}:
            raise MicroWorldError("unsupported transition_class")
        if type(terminal) is not bool:
            raise MicroWorldError("terminal must be boolean")
        if authority_boundary != AUTHORITY_BOUNDARY:
            raise MicroWorldError("observation authority boundary mismatch")
        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "episode_id", episode_id)
        object.__setattr__(self, "step_index", step_index)
        object.__setattr__(self, "visible_state", visible_state)
        object.__setattr__(self, "action_ids", action_ids)
        object.__setattr__(self, "last_action_id", last_action_id)
        object.__setattr__(self, "transition_class", transition_class)
        object.__setattr__(self, "terminal", terminal)
        object.__setattr__(self, "authority_boundary", authority_boundary)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class MicroWorldPartition:
    schema: str
    development: tuple[tuple[str, str], ...]
    held_out: tuple[tuple[str, str], ...]
    authority_boundary: str = AUTHORITY_BOUNDARY

    def __post_init__(self) -> None:
        if self.schema != MICRO_WORLD_PARTITION_SCHEMA:
            raise MicroWorldError("partition schema mismatch")
        for label, rows in (("development", self.development), ("held_out", self.held_out)):
            if not isinstance(rows, tuple) or not rows:
                raise MicroWorldError(f"{label} partition must be a non-empty tuple")
            ids: set[str] = set()
            digests: set[str] = set()
            for scenario_id, digest in rows:
                scenario_id = _identifier(f"{label}.scenario_id", scenario_id)
                digest = _validate_sha256(f"{label}.scenario_sha256", digest)
                if scenario_id in ids or digest in digests:
                    raise MicroWorldError(f"{label} partition contains duplicate identity or digest")
                ids.add(scenario_id)
                digests.add(digest)
        if self.authority_boundary != AUTHORITY_BOUNDARY:
            raise MicroWorldError("partition authority boundary mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def create_scenario(
    *,
    scenario_id: str,
    generation: int,
    split: str,
    initial_state: Mapping[str, Scalar] | Iterable[tuple[str, Scalar]],
    visible_keys: Iterable[str],
    actions: Sequence[ActionSpec],
    terminal_conditions: Sequence[Condition] = (),
    max_steps: int = 32,
) -> MicroWorldScenario:
    return MicroWorldScenario(
        schema=MICRO_WORLD_SCENARIO_SCHEMA,
        scenario_id=scenario_id,
        generation=generation,
        split=split,
        initial_state=_pairs("initial_state", initial_state),
        visible_keys=_keys("visible_keys", visible_keys),
        actions=tuple(actions),
        terminal_conditions=tuple(terminal_conditions),
        max_steps=max_steps,
    )


def _is_terminal(scenario: MicroWorldScenario, world_state: tuple[tuple[str, Scalar], ...]) -> bool:
    if not scenario.terminal_conditions:
        return False
    state = _state_dict(world_state)
    return all(state[condition.key] == condition.equals for condition in scenario.terminal_conditions)


def _observation(
    scenario: MicroWorldScenario,
    run_state: MicroWorldRunState,
    *,
    episode_id: str,
    last_action_id: str | None,
    transition_class: str | None,
) -> MicroWorldObservation:
    state = _state_dict(run_state.world_state)
    visible = tuple((key, state[key]) for key in scenario.visible_keys)
    return MicroWorldObservation(
        schema=MICRO_WORLD_OBSERVATION_SCHEMA,
        episode_id=episode_id,
        step_index=run_state.step_index,
        visible_state=visible,
        action_ids=tuple(action.action_id for action in scenario.actions),
        last_action_id=last_action_id,
        transition_class=transition_class,
        terminal=run_state.terminal,
        authority_boundary=AUTHORITY_BOUNDARY,
        _token=_OBSERVATION_TOKEN,
    )


def reset_micro_world(
    scenario: MicroWorldScenario,
    *,
    episode_id: str,
) -> tuple[MicroWorldRunState, MicroWorldObservation]:
    if not isinstance(scenario, MicroWorldScenario):
        raise MicroWorldError("scenario must be a MicroWorldScenario")
    episode_id = _identifier("episode_id", episode_id)
    terminal = _is_terminal(scenario, scenario.initial_state)
    run_state = MicroWorldRunState(
        schema=MICRO_WORLD_RUN_STATE_SCHEMA,
        scenario_id=scenario.scenario_id,
        scenario_generation=scenario.generation,
        scenario_sha256=scenario.sha256(),
        step_index=0,
        world_state=scenario.initial_state,
        terminal=terminal,
        authority_boundary=AUTHORITY_BOUNDARY,
        _token=_STATE_TOKEN,
    )
    return run_state, _observation(
        scenario,
        run_state,
        episode_id=episode_id,
        last_action_id=None,
        transition_class=None,
    )


def _revalidate_run_state(scenario: MicroWorldScenario, run_state: MicroWorldRunState) -> None:
    if type(run_state) is not MicroWorldRunState:
        raise MicroWorldError("run_state must be exact MicroWorldRunState")
    if run_state.scenario_id != scenario.scenario_id:
        raise MicroWorldError("run_state scenario_id mismatch")
    if run_state.scenario_generation != scenario.generation:
        raise MicroWorldError("run_state scenario_generation mismatch")
    if run_state.scenario_sha256 != scenario.sha256():
        raise MicroWorldError("run_state scenario digest mismatch")
    expected_keys = {key for key, _ in scenario.initial_state}
    actual_keys = {key for key, _ in run_state.world_state}
    if actual_keys != expected_keys:
        raise MicroWorldError("run_state world-state keyset mismatch")
    if run_state.step_index > scenario.max_steps:
        raise MicroWorldError("run_state step_index exceeds scenario max_steps")
    if run_state.terminal != _is_terminal(scenario, run_state.world_state):
        raise MicroWorldError("run_state terminal flag does not match canonical conditions")


def step_micro_world(
    scenario: MicroWorldScenario,
    run_state: MicroWorldRunState,
    *,
    episode_id: str,
    action_id: str,
) -> tuple[MicroWorldRunState, MicroWorldObservation]:
    if not isinstance(scenario, MicroWorldScenario):
        raise MicroWorldError("scenario must be a MicroWorldScenario")
    _revalidate_run_state(scenario, run_state)
    episode_id = _identifier("episode_id", episode_id)
    action_id = _identifier("action_id", action_id)
    if run_state.terminal:
        raise MicroWorldError("cannot step a terminal micro-world")

    actions = {action.action_id: action for action in scenario.actions}
    if action_id not in actions:
        raise MicroWorldError("unknown action_id")

    if run_state.step_index >= scenario.max_steps:
        next_state = MicroWorldRunState(
            schema=MICRO_WORLD_RUN_STATE_SCHEMA,
            scenario_id=scenario.scenario_id,
            scenario_generation=scenario.generation,
            scenario_sha256=scenario.sha256(),
            step_index=run_state.step_index,
            world_state=run_state.world_state,
            terminal=run_state.terminal,
            authority_boundary=AUTHORITY_BOUNDARY,
            _token=_STATE_TOKEN,
        )
        return next_state, _observation(
            scenario,
            next_state,
            episode_id=episode_id,
            last_action_id=action_id,
            transition_class=TRANSITION_MAX_STEPS,
        )

    action = actions[action_id]
    state = _state_dict(run_state.world_state)
    allowed = all(state[condition.key] == condition.equals for condition in action.preconditions)
    if allowed:
        for key, value in action.updates:
            state[key] = value
        transition_class = TRANSITION_APPLIED
    else:
        transition_class = TRANSITION_BLOCKED

    world_state = _pairs("world_state", state)
    next_state = MicroWorldRunState(
        schema=MICRO_WORLD_RUN_STATE_SCHEMA,
        scenario_id=scenario.scenario_id,
        scenario_generation=scenario.generation,
        scenario_sha256=scenario.sha256(),
        step_index=run_state.step_index + 1,
        world_state=world_state,
        terminal=_is_terminal(scenario, world_state),
        authority_boundary=AUTHORITY_BOUNDARY,
        _token=_STATE_TOKEN,
    )
    return next_state, _observation(
        scenario,
        next_state,
        episode_id=episode_id,
        last_action_id=action_id,
        transition_class=transition_class,
    )


def replay_micro_world(
    scenario: MicroWorldScenario,
    *,
    episode_id: str,
    actions: Sequence[str],
) -> tuple[MicroWorldRunState, tuple[MicroWorldObservation, ...]]:
    run_state, initial = reset_micro_world(scenario, episode_id=episode_id)
    observations = [initial]
    for action_id in actions:
        run_state, observation = step_micro_world(
            scenario,
            run_state,
            episode_id=episode_id,
            action_id=action_id,
        )
        observations.append(observation)
        if run_state.terminal:
            break
    return run_state, tuple(observations)


def create_partition(
    *,
    development: Sequence[MicroWorldScenario],
    held_out: Sequence[MicroWorldScenario],
) -> MicroWorldPartition:
    development = tuple(development)
    held_out = tuple(held_out)
    if not development or not held_out:
        raise MicroWorldError("development and held_out scenario sets must both be non-empty")
    if not all(isinstance(item, MicroWorldScenario) for item in development + held_out):
        raise MicroWorldError("partition inputs must be MicroWorldScenario values")
    if any(item.split != SPLIT_DEVELOPMENT for item in development):
        raise MicroWorldError("development partition contains non-development scenario")
    if any(item.split != SPLIT_HELD_OUT for item in held_out):
        raise MicroWorldError("held_out partition contains non-held-out scenario")

    dev_rows = tuple(sorted((item.scenario_id, item.sha256()) for item in development))
    held_rows = tuple(sorted((item.scenario_id, item.sha256()) for item in held_out))
    dev_ids = {item[0] for item in dev_rows}
    held_ids = {item[0] for item in held_rows}
    dev_digests = {item[1] for item in dev_rows}
    held_digests = {item[1] for item in held_rows}
    if dev_ids & held_ids:
        raise MicroWorldError("development and held_out scenario_id sets must be disjoint")
    if dev_digests & held_digests:
        raise MicroWorldError("development and held_out content digests must be disjoint")

    return MicroWorldPartition(
        schema=MICRO_WORLD_PARTITION_SCHEMA,
        development=dev_rows,
        held_out=held_rows,
    )


__all__ = [
    "AUTHORITY_BOUNDARY",
    "ActionSpec",
    "Condition",
    "MICRO_WORLD_OBSERVATION_SCHEMA",
    "MICRO_WORLD_PARTITION_SCHEMA",
    "MICRO_WORLD_RUN_STATE_SCHEMA",
    "MICRO_WORLD_SCENARIO_SCHEMA",
    "MicroWorldError",
    "MicroWorldObservation",
    "MicroWorldPartition",
    "MicroWorldRunState",
    "MicroWorldScenario",
    "SPLIT_DEVELOPMENT",
    "SPLIT_HELD_OUT",
    "TRANSITION_APPLIED",
    "TRANSITION_BLOCKED",
    "TRANSITION_MAX_STEPS",
    "create_partition",
    "create_scenario",
    "replay_micro_world",
    "reset_micro_world",
    "step_micro_world",
]
