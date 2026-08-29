"""Deterministic held-out interactive micro-world harness for F2-WP-800 G1."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

MICRO_WORLD_SCENARIO_SCHEMA = "FRANKENSTEIN2_MICRO_WORLD_SCENARIO/v1"
MICRO_WORLD_RUN_STATE_SCHEMA = "FRANKENSTEIN2_MICRO_WORLD_RUN_STATE/v1"
MICRO_WORLD_OBSERVATION_SCHEMA = "FRANKENSTEIN2_MICRO_WORLD_OBSERVATION/v1"
MICRO_WORLD_PARTITION_SCHEMA = "FRANKENSTEIN2_MICRO_WORLD_PARTITION/v1"
SPLIT_DEVELOPMENT = "DEVELOPMENT"
SPLIT_HELD_OUT = "HELD_OUT"
TRANSITION_APPLIED = "APPLIED"
TRANSITION_BLOCKED = "BLOCKED_PRECONDITION"
AUTHORITY_BOUNDARY = "MICRO_WORLD_TEST_HARNESS_NOT_WORLD_TRUTH_EFFECT_COMPLETION_OR_RUNTIME_AUTHORITY"
_MAX_ID_LEN = 256
_MAX_KEYS = 128
_MAX_ACTIONS = 64
_MAX_STEPS = 10_000
_STATE_TOKEN = object()
_OBSERVATION_TOKEN = object()
Scalar = str | int | bool | None


class MicroWorldError(ValueError):
    pass


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise MicroWorldError(f"{name} must be a string")
    if not value or value != value.strip():
        raise MicroWorldError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise MicroWorldError(f"{name} is outside the canonical identifier domain")
    return value


def _scalar(name: str, value: Any) -> Scalar:
    if value is None or isinstance(value, (str, bool)):
        return value
    if type(value) is int and abs(value) <= 10**12:
        return value
    raise MicroWorldError(f"{name} must be bounded str/int/bool/null")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256(name: str, value: Any) -> str:
    value = _identifier(name, value)
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise MicroWorldError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _pairs(name: str, values: Mapping[str, Scalar] | Iterable[tuple[str, Scalar]]) -> tuple[tuple[str, Scalar], ...]:
    items = tuple(values.items()) if isinstance(values, Mapping) else tuple(values)
    if len(items) > _MAX_KEYS:
        raise MicroWorldError(f"{name} exceeds {_MAX_KEYS} entries")
    out: list[tuple[str, Scalar]] = []
    seen: set[str] = set()
    for raw_key, raw_value in items:
        key = _identifier(f"{name}.key", raw_key)
        if key in seen:
            raise MicroWorldError(f"{name} contains duplicate key {key!r}")
        seen.add(key)
        out.append((key, _scalar(f"{name}[{key}]", raw_value)))
    return tuple(sorted(out))


def _keys(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise MicroWorldError(f"{name} must be an iterable of identifiers")
    out = tuple(_identifier(name, value) for value in values)
    if len(out) > _MAX_KEYS or len(set(out)) != len(out):
        raise MicroWorldError(f"{name} has too many or duplicate entries")
    return tuple(sorted(out))


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
        if type(self.preconditions) is not tuple or not all(type(x) is Condition for x in self.preconditions):
            raise MicroWorldError("preconditions must be exact Condition values")
        if len({x.key for x in self.preconditions}) != len(self.preconditions):
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
        initial = _pairs("initial_state", self.initial_state)
        if not initial:
            raise MicroWorldError("initial_state must not be empty")
        object.__setattr__(self, "initial_state", initial)
        state_keys = {k for k, _ in initial}
        visible = _keys("visible_keys", self.visible_keys)
        if not set(visible).issubset(state_keys):
            raise MicroWorldError("visible_keys must exist in initial_state")
        object.__setattr__(self, "visible_keys", visible)
        if type(self.actions) is not tuple or not self.actions or len(self.actions) > _MAX_ACTIONS or not all(type(x) is ActionSpec for x in self.actions):
            raise MicroWorldError("actions must be a bounded non-empty tuple of exact ActionSpec values")
        if len({x.action_id for x in self.actions}) != len(self.actions):
            raise MicroWorldError("actions contain duplicate action_id")
        for action in self.actions:
            refs = {x.key for x in action.preconditions} | {k for k, _ in action.updates}
            if not refs.issubset(state_keys):
                raise MicroWorldError("action references unknown state key")
        if type(self.terminal_conditions) is not tuple or not all(type(x) is Condition for x in self.terminal_conditions):
            raise MicroWorldError("terminal_conditions must be exact Condition values")
        terminal_keys = {x.key for x in self.terminal_conditions}
        if len(terminal_keys) != len(self.terminal_conditions) or not terminal_keys.issubset(state_keys):
            raise MicroWorldError("terminal condition duplicates or references unknown state key")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= _MAX_STEPS:
            raise MicroWorldError(f"max_steps must be an integer in [1, {_MAX_STEPS}]")
        if self.authority_boundary != AUTHORITY_BOUNDARY:
            raise MicroWorldError("scenario authority boundary mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def content_sha256(self) -> str:
        return _digest({
            "initial_state": self.initial_state,
            "visible_keys": self.visible_keys,
            "actions": tuple(asdict(x) for x in self.actions),
            "terminal_conditions": tuple(asdict(x) for x in self.terminal_conditions),
            "max_steps": self.max_steps,
            "authority_boundary": self.authority_boundary,
        })


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

    def __init__(self, *, schema: str, scenario_id: str, scenario_generation: int, scenario_sha256: str, step_index: int, world_state: tuple[tuple[str, Scalar], ...], terminal: bool, authority_boundary: str, _token: object | None = None) -> None:
        if _token is not _STATE_TOKEN:
            raise MicroWorldError("MicroWorldRunState must be created by the harness")
        if schema != MICRO_WORLD_RUN_STATE_SCHEMA:
            raise MicroWorldError("run-state schema mismatch")
        scenario_id = _identifier("scenario_id", scenario_id)
        if type(scenario_generation) is not int or scenario_generation < 1:
            raise MicroWorldError("scenario_generation must be a positive integer")
        scenario_sha256 = _sha256("scenario_sha256", scenario_sha256)
        if type(step_index) is not int or step_index < 0:
            raise MicroWorldError("step_index must be a non-negative integer")
        world_state = _pairs("world_state", world_state)
        if type(terminal) is not bool or authority_boundary != AUTHORITY_BOUNDARY:
            raise MicroWorldError("run-state terminal/authority mismatch")
        for name, value in (("schema", schema), ("scenario_id", scenario_id), ("scenario_generation", scenario_generation), ("scenario_sha256", scenario_sha256), ("step_index", step_index), ("world_state", world_state), ("terminal", terminal), ("authority_boundary", authority_boundary)):
            object.__setattr__(self, name, value)

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

    def __init__(self, *, schema: str, episode_id: str, step_index: int, visible_state: tuple[tuple[str, Scalar], ...], action_ids: tuple[str, ...], last_action_id: str | None, transition_class: str | None, terminal: bool, authority_boundary: str, _token: object | None = None) -> None:
        if _token is not _OBSERVATION_TOKEN:
            raise MicroWorldError("MicroWorldObservation must be created by the harness")
        if schema != MICRO_WORLD_OBSERVATION_SCHEMA:
            raise MicroWorldError("observation schema mismatch")
        episode_id = _identifier("episode_id", episode_id)
        if type(step_index) is not int or step_index < 0:
            raise MicroWorldError("step_index must be non-negative")
        visible_state = _pairs("visible_state", visible_state)
        action_ids = _keys("action_ids", action_ids)
        if last_action_id is not None:
            last_action_id = _identifier("last_action_id", last_action_id)
        if transition_class not in {None, TRANSITION_APPLIED, TRANSITION_BLOCKED}:
            raise MicroWorldError("unsupported transition_class")
        if type(terminal) is not bool or authority_boundary != AUTHORITY_BOUNDARY:
            raise MicroWorldError("observation terminal/authority mismatch")
        for name, value in (("schema", schema), ("episode_id", episode_id), ("step_index", step_index), ("visible_state", visible_state), ("action_ids", action_ids), ("last_action_id", last_action_id), ("transition_class", transition_class), ("terminal", terminal), ("authority_boundary", authority_boundary)):
            object.__setattr__(self, name, value)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class MicroWorldPartition:
    schema: str
    development: tuple[tuple[str, str, str], ...]
    held_out: tuple[tuple[str, str, str], ...]
    authority_boundary: str = AUTHORITY_BOUNDARY

    def __post_init__(self) -> None:
        if self.schema != MICRO_WORLD_PARTITION_SCHEMA or self.authority_boundary != AUTHORITY_BOUNDARY:
            raise MicroWorldError("partition schema/authority mismatch")
        for label, rows in (("development", self.development), ("held_out", self.held_out)):
            if type(rows) is not tuple or not rows:
                raise MicroWorldError(f"{label} partition must be non-empty")
            ids, exacts, contents = set(), set(), set()
            for sid, exact, content in rows:
                sid = _identifier(f"{label}.scenario_id", sid)
                exact = _sha256(f"{label}.scenario_sha256", exact)
                content = _sha256(f"{label}.content_sha256", content)
                if sid in ids or exact in exacts or content in contents:
                    raise MicroWorldError(f"{label} partition contains duplicate scenario identity/content")
                ids.add(sid)
                exacts.add(exact)
                contents.add(content)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def create_scenario(*, scenario_id: str, generation: int, split: str, initial_state: Mapping[str, Scalar] | Iterable[tuple[str, Scalar]], visible_keys: Iterable[str], actions: Sequence[ActionSpec], terminal_conditions: Sequence[Condition] = (), max_steps: int = 32) -> MicroWorldScenario:
    return MicroWorldScenario(MICRO_WORLD_SCENARIO_SCHEMA, scenario_id, generation, split, _pairs("initial_state", initial_state), _keys("visible_keys", visible_keys), tuple(actions), tuple(terminal_conditions), max_steps)


def _goal_terminal(scenario: MicroWorldScenario, state_pairs: tuple[tuple[str, Scalar], ...]) -> bool:
    if not scenario.terminal_conditions:
        return False
    state = dict(state_pairs)
    return all(state[c.key] == c.equals for c in scenario.terminal_conditions)


def _expected_terminal(scenario: MicroWorldScenario, state_pairs: tuple[tuple[str, Scalar], ...], step_index: int) -> bool:
    return _goal_terminal(scenario, state_pairs) or step_index >= scenario.max_steps


def _observation(scenario: MicroWorldScenario, run_state: MicroWorldRunState, *, episode_id: str, last_action_id: str | None, transition_class: str | None) -> MicroWorldObservation:
    state = dict(run_state.world_state)
    return MicroWorldObservation(schema=MICRO_WORLD_OBSERVATION_SCHEMA, episode_id=episode_id, step_index=run_state.step_index, visible_state=tuple((k, state[k]) for k in scenario.visible_keys), action_ids=tuple(a.action_id for a in scenario.actions), last_action_id=last_action_id, transition_class=transition_class, terminal=run_state.terminal, authority_boundary=AUTHORITY_BOUNDARY, _token=_OBSERVATION_TOKEN)


def reset_micro_world(scenario: MicroWorldScenario, *, episode_id: str) -> tuple[MicroWorldRunState, MicroWorldObservation]:
    if type(scenario) is not MicroWorldScenario:
        raise MicroWorldError("scenario must be exact MicroWorldScenario")
    episode_id = _identifier("episode_id", episode_id)
    state = MicroWorldRunState(schema=MICRO_WORLD_RUN_STATE_SCHEMA, scenario_id=scenario.scenario_id, scenario_generation=scenario.generation, scenario_sha256=scenario.sha256(), step_index=0, world_state=scenario.initial_state, terminal=_expected_terminal(scenario, scenario.initial_state, 0), authority_boundary=AUTHORITY_BOUNDARY, _token=_STATE_TOKEN)
    return state, _observation(scenario, state, episode_id=episode_id, last_action_id=None, transition_class=None)


def _revalidate_run_state(scenario: MicroWorldScenario, run_state: MicroWorldRunState) -> None:
    if type(run_state) is not MicroWorldRunState:
        raise MicroWorldError("run_state must be exact MicroWorldRunState")
    if run_state.scenario_id != scenario.scenario_id:
        raise MicroWorldError("run_state scenario_id mismatch")
    if run_state.scenario_generation != scenario.generation:
        raise MicroWorldError("run_state scenario_generation mismatch")
    if run_state.scenario_sha256 != scenario.sha256():
        raise MicroWorldError("run_state scenario digest mismatch")
    if {k for k, _ in run_state.world_state} != {k for k, _ in scenario.initial_state}:
        raise MicroWorldError("run_state world-state keyset mismatch")
    if run_state.step_index > scenario.max_steps:
        raise MicroWorldError("run_state step_index exceeds max_steps")
    if run_state.terminal is not _expected_terminal(scenario, run_state.world_state, run_state.step_index):
        raise MicroWorldError("run_state terminal flag mismatch")


def step_micro_world(scenario: MicroWorldScenario, run_state: MicroWorldRunState, *, episode_id: str, action_id: str) -> tuple[MicroWorldRunState, MicroWorldObservation]:
    if type(scenario) is not MicroWorldScenario:
        raise MicroWorldError("scenario must be exact MicroWorldScenario")
    _revalidate_run_state(scenario, run_state)
    episode_id = _identifier("episode_id", episode_id)
    action_id = _identifier("action_id", action_id)
    if run_state.terminal:
        raise MicroWorldError("cannot step a terminal micro-world")
    actions = {a.action_id: a for a in scenario.actions}
    if action_id not in actions:
        raise MicroWorldError("unknown action_id")
    action = actions[action_id]
    state = dict(run_state.world_state)
    allowed = all(state[c.key] == c.equals for c in action.preconditions)
    if allowed:
        for key, value in action.updates:
            state[key] = value
    next_index = run_state.step_index + 1
    world_state = _pairs("world_state", state)
    nxt = MicroWorldRunState(schema=MICRO_WORLD_RUN_STATE_SCHEMA, scenario_id=scenario.scenario_id, scenario_generation=scenario.generation, scenario_sha256=scenario.sha256(), step_index=next_index, world_state=world_state, terminal=_expected_terminal(scenario, world_state, next_index), authority_boundary=AUTHORITY_BOUNDARY, _token=_STATE_TOKEN)
    transition = TRANSITION_APPLIED if allowed else TRANSITION_BLOCKED
    return nxt, _observation(scenario, nxt, episode_id=episode_id, last_action_id=action_id, transition_class=transition)


def replay_micro_world(scenario: MicroWorldScenario, *, episode_id: str, actions: Sequence[str]) -> tuple[MicroWorldRunState, tuple[MicroWorldObservation, ...]]:
    state, obs0 = reset_micro_world(scenario, episode_id=episode_id)
    observations = [obs0]
    for action_id in actions:
        if state.terminal:
            break
        state, obs = step_micro_world(scenario, state, episode_id=episode_id, action_id=action_id)
        observations.append(obs)
    return state, tuple(observations)


def create_partition(*, development: Sequence[MicroWorldScenario], held_out: Sequence[MicroWorldScenario]) -> MicroWorldPartition:
    development = tuple(development)
    held_out = tuple(held_out)
    if not development or not held_out:
        raise MicroWorldError("development and held_out sets must both be non-empty")
    if not all(type(x) is MicroWorldScenario for x in development + held_out):
        raise MicroWorldError("partition inputs must be exact MicroWorldScenario values")
    if any(x.split != SPLIT_DEVELOPMENT for x in development):
        raise MicroWorldError("development partition contains non-development scenario")
    if any(x.split != SPLIT_HELD_OUT for x in held_out):
        raise MicroWorldError("held_out partition contains non-held-out scenario")
    dev = tuple(sorted((x.scenario_id, x.sha256(), x.content_sha256()) for x in development))
    held = tuple(sorted((x.scenario_id, x.sha256(), x.content_sha256()) for x in held_out))
    if {r[0] for r in dev} & {r[0] for r in held}:
        raise MicroWorldError("development and held_out scenario_id sets must be disjoint")
    if {r[2] for r in dev} & {r[2] for r in held}:
        raise MicroWorldError("development and held_out semantic content must be disjoint")
    return MicroWorldPartition(MICRO_WORLD_PARTITION_SCHEMA, dev, held)


__all__ = ["AUTHORITY_BOUNDARY", "ActionSpec", "Condition", "MICRO_WORLD_OBSERVATION_SCHEMA", "MICRO_WORLD_PARTITION_SCHEMA", "MICRO_WORLD_RUN_STATE_SCHEMA", "MICRO_WORLD_SCENARIO_SCHEMA", "MicroWorldError", "MicroWorldObservation", "MicroWorldPartition", "MicroWorldRunState", "MicroWorldScenario", "SPLIT_DEVELOPMENT", "SPLIT_HELD_OUT", "TRANSITION_APPLIED", "TRANSITION_BLOCKED", "create_partition", "create_scenario", "replay_micro_world", "reset_micro_world", "step_micro_world"]
