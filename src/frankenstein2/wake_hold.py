"""Deterministic WAIT/HOLD/Wake contract for Frankenstein 2.0.

F2-WP-205 generation 1.

This component only evaluates explicitly caller-supplied observations against explicitly
caller-supplied wake conditions. It has no clock, sensor, persistence, scheduler, goal,
provider/tool, effect, or completion authority. Evaluation is fail-closed under exact
state-id/generation/state-digest fences.

Epistemic law:
- missing evidence is UNKNOWN, not evidence of NO_MATCH;
- contradictory same-key EQUALS observations are UNKNOWN, not existential MATCH;
- WAKE_CONDITION_MATCH is only a non-authoritative candidate signal.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

HOLD_CHECKPOINT_SCHEMA = "FRANKENSTEIN2_HOLD_CHECKPOINT/v1"
WAKE_EVALUATION_SCHEMA = "FRANKENSTEIN2_WAKE_EVALUATION/v1"
WAKE_ANY = "ANY"
WAKE_ALL = "ALL"
OP_EQUALS = "EQUALS"
OP_PRESENT = "PRESENT"

WAKE_MATCH = "WAKE_CONDITION_MATCH"
HOLD_NO_MATCH = "HOLD_CONDITION_NOT_MATCHED"
WAKE_UNKNOWN = "ABSTAIN_NOT_OBSERVED_OR_AMBIGUOUS"

_ALLOWED_POLICIES = frozenset({WAKE_ANY, WAKE_ALL})
_ALLOWED_OPERATORS = frozenset({OP_EQUALS, OP_PRESENT})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_VALUE_LEN = 4096


class WakeHoldError(ValueError):
    """Fail-closed WAIT/HOLD/Wake contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise WakeHoldError(f"{name} must be a string")
    if not value or value != value.strip():
        raise WakeHoldError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise WakeHoldError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise WakeHoldError(f"{name} contains control characters")
    return value


def _value(name: str, value: Any) -> str:
    value = _identifier(name, value)
    if len(value) > _MAX_VALUE_LEN:
        raise WakeHoldError(f"{name} exceeds {_MAX_VALUE_LEN} characters")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise WakeHoldError("generation must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise WakeHoldError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise WakeHoldError(f"{name} must be an iterable of reference strings")
    cleaned = tuple(sorted({_identifier(name, value) for value in values}))
    if not cleaned:
        raise WakeHoldError(f"{name} must contain at least one explicit reference")
    return cleaned


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class WakeCondition:
    condition_id: str
    observation_key: str
    operator: str
    provenance_refs: tuple[str, ...]
    expected_value: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "condition_id", _identifier("condition_id", self.condition_id))
        object.__setattr__(self, "observation_key", _identifier("observation_key", self.observation_key))
        if self.operator not in _ALLOWED_OPERATORS:
            raise WakeHoldError(f"unsupported wake operator: {self.operator!r}")
        if self.operator == OP_EQUALS:
            if self.expected_value is None:
                raise WakeHoldError("EQUALS wake condition requires expected_value")
            object.__setattr__(self, "expected_value", _value("expected_value", self.expected_value))
        elif self.expected_value is not None:
            raise WakeHoldError("PRESENT wake condition must not carry expected_value")
        object.__setattr__(self, "provenance_refs", _refs("condition provenance_ref", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WakeObservation:
    observation_id: str
    observation_key: str
    value: str
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _identifier("observation_id", self.observation_id))
        object.__setattr__(self, "observation_key", _identifier("observation_key", self.observation_key))
        object.__setattr__(self, "value", _value("observation value", self.value))
        object.__setattr__(self, "provenance_refs", _refs("observation provenance_ref", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unique_conditions(values: Iterable[WakeCondition]) -> tuple[WakeCondition, ...]:
    by_id: dict[str, WakeCondition] = {}
    for value in values:
        if not isinstance(value, WakeCondition):
            raise WakeHoldError("wake_conditions must contain WakeCondition values")
        if value.condition_id in by_id:
            raise WakeHoldError(f"duplicate condition_id: {value.condition_id}")
        by_id[value.condition_id] = value
    if not by_id:
        raise WakeHoldError("hold checkpoint requires at least one wake condition")
    return tuple(by_id[key] for key in sorted(by_id))


def _unique_observations(values: Iterable[WakeObservation]) -> tuple[WakeObservation, ...]:
    by_id: dict[str, WakeObservation] = {}
    for value in values:
        if not isinstance(value, WakeObservation):
            raise WakeHoldError("observations must contain WakeObservation values")
        if value.observation_id in by_id:
            raise WakeHoldError(f"duplicate observation_id: {value.observation_id}")
        by_id[value.observation_id] = value
    return tuple(by_id[key] for key in sorted(by_id))


@dataclass(frozen=True, slots=True)
class HoldCheckpoint:
    schema: str
    hold_id: str
    state_id: str
    generation: int
    state_sha256: str
    wake_policy: str
    wake_conditions: tuple[WakeCondition, ...]
    provenance_refs: tuple[str, ...]
    classification: str = "EXPLICIT_HOLD_CHECKPOINT_NOT_SCHEDULER_AUTHORITY"

    def __post_init__(self) -> None:
        if self.schema != HOLD_CHECKPOINT_SCHEMA:
            raise WakeHoldError("hold checkpoint schema mismatch")
        object.__setattr__(self, "hold_id", _identifier("hold_id", self.hold_id))
        object.__setattr__(self, "state_id", _identifier("state_id", self.state_id))
        object.__setattr__(self, "generation", _generation(self.generation))
        object.__setattr__(self, "state_sha256", _sha256("state_sha256", self.state_sha256))
        if self.wake_policy not in _ALLOWED_POLICIES:
            raise WakeHoldError(f"unsupported wake_policy: {self.wake_policy!r}")
        object.__setattr__(self, "wake_conditions", _unique_conditions(self.wake_conditions))
        object.__setattr__(self, "provenance_refs", _refs("checkpoint provenance_ref", self.provenance_refs))

    @classmethod
    def create(cls, *, hold_id: str, state_id: str, generation: int, state_sha256: str,
               wake_policy: str, wake_conditions: Iterable[WakeCondition],
               provenance_refs: Iterable[str]) -> "HoldCheckpoint":
        return cls(
            schema=HOLD_CHECKPOINT_SCHEMA,
            hold_id=hold_id,
            state_id=state_id,
            generation=generation,
            state_sha256=state_sha256,
            wake_policy=wake_policy,
            wake_conditions=tuple(wake_conditions),
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "hold_id": self.hold_id,
            "state_id": self.state_id,
            "generation": self.generation,
            "state_sha256": self.state_sha256,
            "wake_policy": self.wake_policy,
            "wake_conditions": [condition.as_dict() for condition in self.wake_conditions],
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class WakeEvaluation:
    schema: str
    evaluation_id: str
    hold_id: str
    checkpoint_sha256: str
    observed_state_id: str
    observed_generation: int
    observed_state_sha256: str
    observation_ids: tuple[str, ...]
    matched_condition_ids: tuple[str, ...]
    unmatched_condition_ids: tuple[str, ...]
    unknown_condition_ids: tuple[str, ...]
    classification: str
    wake: bool | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _evaluate_condition(
    condition: WakeCondition,
    candidates: tuple[WakeObservation, ...],
) -> str:
    """Return MATCH, NO_MATCH, or UNKNOWN without reading external state."""
    if not candidates:
        return "UNKNOWN"
    if condition.operator == OP_PRESENT:
        return "MATCH"

    observed_values = {item.value for item in candidates}
    if len(observed_values) != 1:
        return "UNKNOWN"
    only_value = next(iter(observed_values))
    return "MATCH" if only_value == condition.expected_value else "NO_MATCH"


def evaluate_wake(
    checkpoint: HoldCheckpoint,
    *,
    evaluation_id: str,
    observed_state_id: str,
    observed_generation: int,
    observed_state_sha256: str,
    observations: Iterable[WakeObservation],
) -> WakeEvaluation:
    """Pure 3-valued evaluation; raises on any stale/mismatched state fence."""
    if not isinstance(checkpoint, HoldCheckpoint):
        raise WakeHoldError("checkpoint must be a HoldCheckpoint")
    evaluation_id = _identifier("evaluation_id", evaluation_id)
    observed_state_id = _identifier("observed_state_id", observed_state_id)
    observed_generation = _generation(observed_generation)
    observed_state_sha256 = _sha256("observed_state_sha256", observed_state_sha256)

    if observed_state_id != checkpoint.state_id:
        raise WakeHoldError("state_id fence mismatch")
    if observed_generation != checkpoint.generation:
        raise WakeHoldError("generation fence mismatch")
    if observed_state_sha256 != checkpoint.state_sha256:
        raise WakeHoldError("state_sha256 fence mismatch")

    explicit = _unique_observations(observations)
    by_key: dict[str, tuple[WakeObservation, ...]] = {}
    for observation in explicit:
        by_key.setdefault(observation.observation_key, ())
        by_key[observation.observation_key] = by_key[observation.observation_key] + (observation,)

    matched: list[str] = []
    unmatched: list[str] = []
    unknown: list[str] = []
    for condition in checkpoint.wake_conditions:
        result = _evaluate_condition(
            condition,
            by_key.get(condition.observation_key, ()),
        )
        if result == "MATCH":
            matched.append(condition.condition_id)
        elif result == "NO_MATCH":
            unmatched.append(condition.condition_id)
        else:
            unknown.append(condition.condition_id)

    if checkpoint.wake_policy == WAKE_ANY:
        if matched:
            wake: bool | None = True
            classification = WAKE_MATCH
        elif unknown:
            wake = None
            classification = WAKE_UNKNOWN
        else:
            wake = False
            classification = HOLD_NO_MATCH
    else:
        if unmatched:
            wake = False
            classification = HOLD_NO_MATCH
        elif unknown:
            wake = None
            classification = WAKE_UNKNOWN
        else:
            wake = True
            classification = WAKE_MATCH

    return WakeEvaluation(
        schema=WAKE_EVALUATION_SCHEMA,
        evaluation_id=evaluation_id,
        hold_id=checkpoint.hold_id,
        checkpoint_sha256=checkpoint.sha256(),
        observed_state_id=observed_state_id,
        observed_generation=observed_generation,
        observed_state_sha256=observed_state_sha256,
        observation_ids=tuple(item.observation_id for item in explicit),
        matched_condition_ids=tuple(matched),
        unmatched_condition_ids=tuple(unmatched),
        unknown_condition_ids=tuple(unknown),
        classification=classification,
        wake=wake,
    )
