"""Deterministic WAIT/HOLD wake-condition matching for Frankenstein 2.0.

This module is intentionally persistence-agnostic and side-effect free.

It does NOT:
- read clocks, sensors, files, UnifiedDB, or external state;
- schedule work or resume goals;
- infer observations or world facts;
- choose Persistent Pulse actions;
- call providers or tools;
- authorize/execute effects;
- mint completion.

A WakeHoldState only freezes explicit caller-supplied conditions. A WakeProbe only
carries explicit caller-supplied observations plus an exact state identity/generation/
digest fence. evaluate() returns a pure match classification. WAKE_MATCH is a candidate
signal only; it is never scheduler, goal-adoption, effect, or completion authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

WAKE_CONDITION_SCHEMA = "FRANKENSTEIN2_WAKE_CONDITION/v1"
WAKE_OBSERVATION_SCHEMA = "FRANKENSTEIN2_WAKE_OBSERVATION/v1"
WAKE_HOLD_STATE_SCHEMA = "FRANKENSTEIN2_WAKE_HOLD_STATE/v1"
WAKE_PROBE_SCHEMA = "FRANKENSTEIN2_WAKE_PROBE/v1"
WAKE_DECISION_SCHEMA = "FRANKENSTEIN2_WAKE_DECISION/v1"

_ALLOWED_OPERATORS = frozenset({"PRESENT", "EQUALS", "INT_GTE", "INT_LTE"})
_ALLOWED_POLICIES = frozenset({"ANY", "ALL"})
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class WakeHoldError(ValueError):
    """Raised when wake/hold input is ambiguous, invalid, or stale."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise WakeHoldError(f"{name} must be a bounded stable identifier")
    return value


def _text(name: str, value: Any, *, max_len: int = 512) -> str:
    if not isinstance(value, str):
        raise WakeHoldError(f"{name} must be a string")
    value = value.strip()
    if not value or len(value) > max_len:
        raise WakeHoldError(f"{name} must be non-empty and <= {max_len} characters")
    if any(ord(ch) < 32 for ch in value):
        raise WakeHoldError(f"{name} must not contain control characters")
    return value


def _generation(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WakeHoldError("generation must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise WakeHoldError(f"{name} must be a lowercase sha256 hex digest")
    return value


def _refs(name: str, values: Iterable[str], *, required: bool = True) -> tuple[str, ...]:
    try:
        items = tuple(values)
    except TypeError as exc:
        raise WakeHoldError(f"{name} must be an iterable of references") from exc
    normalized = tuple(sorted({_text(name, item, max_len=256) for item in items}))
    if required and not normalized:
        raise WakeHoldError(f"{name} must contain at least one explicit reference")
    return normalized


def _scalar(name: str, value: Any) -> str | int | bool | None:
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str):
            return _text(name, value, max_len=512)
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 2**63 - 1:
            raise WakeHoldError(f"{name} integer exceeds signed 64-bit range")
        return value
    raise WakeHoldError(f"{name} must be null, string, boolean, or integer")


def _strict_tuple(
    name: str,
    values: Iterable[Any],
    expected_type: type,
    id_attr: str,
    *,
    allow_empty: bool,
) -> tuple[Any, ...]:
    try:
        items = tuple(values)
    except TypeError as exc:
        raise WakeHoldError(f"{name} must be iterable") from exc
    if not allow_empty and not items:
        raise WakeHoldError(f"{name} must not be empty")
    mapping: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, expected_type):
            raise WakeHoldError(f"{name} must contain only {expected_type.__name__}")
        item_id = getattr(item, id_attr)
        if item_id in mapping:
            raise WakeHoldError(f"duplicate {name} id: {item_id}")
        mapping[item_id] = item
    return tuple(mapping[key] for key in sorted(mapping))


@dataclass(frozen=True, slots=True)
class WakeCondition:
    schema: str
    condition_id: str
    key: str
    operator: str
    expected_value: str | int | bool | None
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != WAKE_CONDITION_SCHEMA:
            raise WakeHoldError("wake condition schema mismatch")
        object.__setattr__(self, "condition_id", _identifier("condition_id", self.condition_id))
        object.__setattr__(self, "key", _identifier("key", self.key))
        if self.operator not in _ALLOWED_OPERATORS:
            raise WakeHoldError(f"unsupported wake operator: {self.operator}")
        expected = _scalar("expected_value", self.expected_value)
        if self.operator == "PRESENT":
            if expected is not None:
                raise WakeHoldError("PRESENT condition must use expected_value=null")
        elif self.operator in {"INT_GTE", "INT_LTE"}:
            if isinstance(expected, bool) or not isinstance(expected, int):
                raise WakeHoldError(f"{self.operator} requires an integer expected_value")
        object.__setattr__(self, "expected_value", expected)
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs, required=True),
        )

    @classmethod
    def create(
        cls,
        *,
        condition_id: str,
        key: str,
        operator: str,
        expected_value: str | int | bool | None = None,
        provenance_refs: Iterable[str],
    ) -> "WakeCondition":
        return cls(
            schema=WAKE_CONDITION_SCHEMA,
            condition_id=condition_id,
            key=key,
            operator=operator,
            expected_value=expected_value,
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WakeObservation:
    schema: str
    observation_id: str
    key: str
    value: str | int | bool | None
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != WAKE_OBSERVATION_SCHEMA:
            raise WakeHoldError("wake observation schema mismatch")
        object.__setattr__(self, "observation_id", _identifier("observation_id", self.observation_id))
        object.__setattr__(self, "key", _identifier("key", self.key))
        object.__setattr__(self, "value", _scalar("value", self.value))
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs, required=True),
        )

    @classmethod
    def create(
        cls,
        *,
        observation_id: str,
        key: str,
        value: str | int | bool | None,
        provenance_refs: Iterable[str],
    ) -> "WakeObservation":
        return cls(
            schema=WAKE_OBSERVATION_SCHEMA,
            observation_id=observation_id,
            key=key,
            value=value,
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WakeProbe:
    schema: str
    probe_id: str
    expected_state_id: str
    expected_generation: int
    expected_state_sha256: str
    observations: tuple[WakeObservation, ...]
    probe_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != WAKE_PROBE_SCHEMA:
            raise WakeHoldError("wake probe schema mismatch")
        object.__setattr__(self, "probe_id", _identifier("probe_id", self.probe_id))
        object.__setattr__(self, "expected_state_id", _identifier("expected_state_id", self.expected_state_id))
        object.__setattr__(self, "expected_generation", _generation(self.expected_generation))
        object.__setattr__(
            self,
            "expected_state_sha256",
            _sha256("expected_state_sha256", self.expected_state_sha256),
        )
        observations = _strict_tuple(
            "observations",
            self.observations,
            WakeObservation,
            "observation_id",
            allow_empty=True,
        )
        seen_keys: set[str] = set()
        for item in observations:
            if item.key in seen_keys:
                raise WakeHoldError(
                    f"ambiguous probe: multiple observations for key {item.key}"
                )
            seen_keys.add(item.key)
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "probe_refs", _refs("probe_refs", self.probe_refs, required=True))

    @classmethod
    def create(
        cls,
        *,
        probe_id: str,
        expected_state_id: str,
        expected_generation: int,
        expected_state_sha256: str,
        observations: Iterable[WakeObservation] = (),
        probe_refs: Iterable[str],
    ) -> "WakeProbe":
        return cls(
            schema=WAKE_PROBE_SCHEMA,
            probe_id=probe_id,
            expected_state_id=expected_state_id,
            expected_generation=expected_generation,
            expected_state_sha256=expected_state_sha256,
            observations=tuple(observations),
            probe_refs=tuple(probe_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "probe_id": self.probe_id,
            "expected_state_id": self.expected_state_id,
            "expected_generation": self.expected_generation,
            "expected_state_sha256": self.expected_state_sha256,
            "observations": [item.as_dict() for item in self.observations],
            "probe_refs": list(self.probe_refs),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class WakeDecision:
    schema: str
    probe_id: str
    state_id: str
    generation: int
    state_sha256: str
    probe_sha256: str
    decision: str
    match_policy: str
    matched_condition_ids: tuple[str, ...]
    unmatched_condition_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    classification: str = "PURE_WAKE_MATCH_NOT_WORLD_FACT_NOT_RESUME_AUTHORITY"

    def __post_init__(self) -> None:
        if self.schema != WAKE_DECISION_SCHEMA:
            raise WakeHoldError("wake decision schema mismatch")
        _identifier("probe_id", self.probe_id)
        _identifier("state_id", self.state_id)
        _generation(self.generation)
        _sha256("state_sha256", self.state_sha256)
        _sha256("probe_sha256", self.probe_sha256)
        if self.decision not in {"WAKE_MATCH", "HOLD_REMAINS"}:
            raise WakeHoldError("wake decision must be WAKE_MATCH or HOLD_REMAINS")
        if self.match_policy not in _ALLOWED_POLICIES:
            raise WakeHoldError("wake decision match_policy mismatch")
        object.__setattr__(
            self,
            "matched_condition_ids",
            tuple(sorted(_identifier("matched_condition_id", x) for x in self.matched_condition_ids)),
        )
        object.__setattr__(
            self,
            "unmatched_condition_ids",
            tuple(sorted(_identifier("unmatched_condition_id", x) for x in self.unmatched_condition_ids)),
        )
        object.__setattr__(
            self,
            "observation_ids",
            tuple(sorted(_identifier("observation_id", x) for x in self.observation_ids)),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class WakeHoldState:
    schema: str
    state_id: str
    generation: int
    hold_id: str
    match_policy: str
    conditions: tuple[WakeCondition, ...]
    checkpoint_refs: tuple[str, ...]
    classification: str = "EXPLICIT_HOLD_CHECKPOINT_NOT_SCHEDULER_STATE"

    def __post_init__(self) -> None:
        if self.schema != WAKE_HOLD_STATE_SCHEMA:
            raise WakeHoldError("wake hold state schema mismatch")
        object.__setattr__(self, "state_id", _identifier("state_id", self.state_id))
        object.__setattr__(self, "generation", _generation(self.generation))
        object.__setattr__(self, "hold_id", _identifier("hold_id", self.hold_id))
        if self.match_policy not in _ALLOWED_POLICIES:
            raise WakeHoldError("match_policy must be ANY or ALL")
        object.__setattr__(
            self,
            "conditions",
            _strict_tuple(
                "conditions",
                self.conditions,
                WakeCondition,
                "condition_id",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "checkpoint_refs",
            _refs("checkpoint_refs", self.checkpoint_refs, required=True),
        )

    @classmethod
    def create(
        cls,
        *,
        state_id: str,
        generation: int,
        hold_id: str,
        match_policy: str,
        conditions: Iterable[WakeCondition],
        checkpoint_refs: Iterable[str],
    ) -> "WakeHoldState":
        return cls(
            schema=WAKE_HOLD_STATE_SCHEMA,
            state_id=state_id,
            generation=generation,
            hold_id=hold_id,
            match_policy=match_policy,
            conditions=tuple(conditions),
            checkpoint_refs=tuple(checkpoint_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "state_id": self.state_id,
            "generation": self.generation,
            "hold_id": self.hold_id,
            "match_policy": self.match_policy,
            "conditions": [item.as_dict() for item in self.conditions],
            "checkpoint_refs": list(self.checkpoint_refs),
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def evaluate(self, probe: WakeProbe) -> WakeDecision:
        if not isinstance(probe, WakeProbe):
            raise WakeHoldError("probe must be a WakeProbe")
        if probe.expected_state_id != self.state_id:
            raise WakeHoldError("wake probe state_id mismatch")
        if probe.expected_generation != self.generation:
            raise WakeHoldError("stale wake-hold generation")
        state_sha = self.sha256()
        if probe.expected_state_sha256 != state_sha:
            raise WakeHoldError("stale or mismatched wake-hold digest")

        observed = {item.key: item for item in probe.observations}
        matched: list[str] = []
        unmatched: list[str] = []
        for condition in self.conditions:
            observation = observed.get(condition.key)
            if _condition_matches(condition, observation):
                matched.append(condition.condition_id)
            else:
                unmatched.append(condition.condition_id)

        is_match = bool(matched) if self.match_policy == "ANY" else not unmatched
        return WakeDecision(
            schema=WAKE_DECISION_SCHEMA,
            probe_id=probe.probe_id,
            state_id=self.state_id,
            generation=self.generation,
            state_sha256=state_sha,
            probe_sha256=probe.sha256(),
            decision="WAKE_MATCH" if is_match else "HOLD_REMAINS",
            match_policy=self.match_policy,
            matched_condition_ids=tuple(matched),
            unmatched_condition_ids=tuple(unmatched),
            observation_ids=tuple(item.observation_id for item in probe.observations),
        )


def _condition_matches(
    condition: WakeCondition,
    observation: WakeObservation | None,
) -> bool:
    if observation is None:
        return False
    if condition.operator == "PRESENT":
        return True
    if condition.operator == "EQUALS":
        return type(observation.value) is type(condition.expected_value) and (
            observation.value == condition.expected_value
        )
    if condition.operator == "INT_GTE":
        return (
            isinstance(observation.value, int)
            and not isinstance(observation.value, bool)
            and observation.value >= condition.expected_value
        )
    if condition.operator == "INT_LTE":
        return (
            isinstance(observation.value, int)
            and not isinstance(observation.value, bool)
            and observation.value <= condition.expected_value
        )
    raise AssertionError("unreachable validated wake operator")


__all__ = [
    "WAKE_CONDITION_SCHEMA",
    "WAKE_DECISION_SCHEMA",
    "WAKE_HOLD_STATE_SCHEMA",
    "WAKE_OBSERVATION_SCHEMA",
    "WAKE_PROBE_SCHEMA",
    "WakeCondition",
    "WakeDecision",
    "WakeHoldError",
    "WakeHoldState",
    "WakeObservation",
    "WakeProbe",
]
