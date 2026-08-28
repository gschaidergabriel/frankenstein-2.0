"""Deterministic Persistent Pulse eligibility kernel for Frankenstein 2.0.

F2-WP-200 generation 2 decision-consistency repair.

The kernel consumes one explicit caller-supplied state/observation identity plus opaque
eligibility references for ACT/ASK/OBSERVE/WAIT/HOLD/DELEGATE. It deterministically returns
which action classes are eligible; it never selects an action, infers a world fact, reads or
writes durable state, schedules work, invokes a model/tool/provider, authorizes an effect, or
mints completion.

HOLD is a local fail-closed eligibility gate: when explicitly supplied it suppresses ACT and
DELEGATE eligibility while preserving epistemic/non-effectful ASK/OBSERVE/WAIT/HOLD signals.
No missing signal is invented. PulseDecision also rejects contradictory direct construction:
an action class cannot occur more than once in eligible and ACT/DELEGATE cannot be both
eligible and suppressed by HOLD.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any

PULSE_INPUT_SCHEMA = "FRANKENSTEIN2_PERSISTENT_PULSE_INPUT/v1"
PULSE_DECISION_SCHEMA = "FRANKENSTEIN2_PERSISTENT_PULSE_ELIGIBILITY/v1"
PULSE_ACTION_ORDER = ("ACT", "ASK", "OBSERVE", "WAIT", "HOLD", "DELEGATE")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_IDENTIFIER_LENGTH = 512


class PersistentPulseError(ValueError):
    """Fail-closed Persistent Pulse contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise PersistentPulseError(f"{name} must be a string")
    if not value or value != value.strip():
        raise PersistentPulseError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise PersistentPulseError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PersistentPulseError(f"{name} contains control characters")
    return value


def _optional_ref(name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _identifier(name, value)


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PersistentPulseError("generation must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise PersistentPulseError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class PulseInput:
    """One explicit caller-supplied eligibility snapshot.

    Each non-None action reference is opaque evidence/candidate identity owned by the caller.
    Presence means only "consider this action class eligible". It is not evidence that an
    action is correct, authorized, executable or complete.
    """

    schema: str
    pulse_id: str
    observation_id: str
    state_id: str
    generation: int
    state_digest_sha256: str
    act_candidate_ref: str | None = None
    ask_candidate_ref: str | None = None
    observe_candidate_ref: str | None = None
    wait_condition_ref: str | None = None
    hold_reason_ref: str | None = None
    delegate_candidate_ref: str | None = None
    classification: str = "EXPLICIT_ELIGIBILITY_INPUT_NOT_WORLD_FACT"

    def __post_init__(self) -> None:
        if self.schema != PULSE_INPUT_SCHEMA:
            raise PersistentPulseError("pulse input schema mismatch")
        object.__setattr__(self, "pulse_id", _identifier("pulse_id", self.pulse_id))
        object.__setattr__(
            self, "observation_id", _identifier("observation_id", self.observation_id)
        )
        object.__setattr__(self, "state_id", _identifier("state_id", self.state_id))
        object.__setattr__(self, "generation", _generation(self.generation))
        object.__setattr__(
            self,
            "state_digest_sha256",
            _sha256("state_digest_sha256", self.state_digest_sha256),
        )
        for field_name in (
            "act_candidate_ref",
            "ask_candidate_ref",
            "observe_candidate_ref",
            "wait_condition_ref",
            "hold_reason_ref",
            "delegate_candidate_ref",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_ref(field_name, getattr(self, field_name)),
            )
        if self.classification != "EXPLICIT_ELIGIBILITY_INPUT_NOT_WORLD_FACT":
            raise PersistentPulseError("pulse input classification mismatch")

    @classmethod
    def create(
        cls,
        *,
        pulse_id: str,
        observation_id: str,
        state_id: str,
        generation: int,
        state_digest_sha256: str,
        act_candidate_ref: str | None = None,
        ask_candidate_ref: str | None = None,
        observe_candidate_ref: str | None = None,
        wait_condition_ref: str | None = None,
        hold_reason_ref: str | None = None,
        delegate_candidate_ref: str | None = None,
    ) -> "PulseInput":
        return cls(
            schema=PULSE_INPUT_SCHEMA,
            pulse_id=pulse_id,
            observation_id=observation_id,
            state_id=state_id,
            generation=generation,
            state_digest_sha256=state_digest_sha256,
            act_candidate_ref=act_candidate_ref,
            ask_candidate_ref=ask_candidate_ref,
            observe_candidate_ref=observe_candidate_ref,
            wait_condition_ref=wait_condition_ref,
            hold_reason_ref=hold_reason_ref,
            delegate_candidate_ref=delegate_candidate_ref,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PulseEligibility:
    action: str
    basis_ref: str

    def __post_init__(self) -> None:
        if self.action not in PULSE_ACTION_ORDER:
            raise PersistentPulseError(f"unsupported pulse action: {self.action}")
        object.__setattr__(self, "basis_ref", _identifier("basis_ref", self.basis_ref))


@dataclass(frozen=True, slots=True)
class PulseDecision:
    schema: str
    pulse_id: str
    observation_id: str
    state_id: str
    generation: int
    state_digest_sha256: str
    input_sha256: str
    eligible: tuple[PulseEligibility, ...]
    suppressed_by_hold: tuple[str, ...]
    classification: str = "ELIGIBILITY_ONLY_NO_ACTION_SELECTION_OR_EFFECT_AUTHORITY"

    def __post_init__(self) -> None:
        if self.schema != PULSE_DECISION_SCHEMA:
            raise PersistentPulseError("pulse decision schema mismatch")
        _identifier("pulse_id", self.pulse_id)
        _identifier("observation_id", self.observation_id)
        _identifier("state_id", self.state_id)
        _generation(self.generation)
        _sha256("state_digest_sha256", self.state_digest_sha256)
        _sha256("input_sha256", self.input_sha256)
        if self.classification != "ELIGIBILITY_ONLY_NO_ACTION_SELECTION_OR_EFFECT_AUTHORITY":
            raise PersistentPulseError("pulse decision classification mismatch")

        eligible_actions = tuple(item.action for item in self.eligible)
        if eligible_actions != tuple(sorted(eligible_actions, key=PULSE_ACTION_ORDER.index)):
            raise PersistentPulseError("eligible actions are not canonically ordered")
        if len(set(eligible_actions)) != len(eligible_actions):
            raise PersistentPulseError("eligible actions contain duplicate action classes")

        if any(action not in {"ACT", "DELEGATE"} for action in self.suppressed_by_hold):
            raise PersistentPulseError("hold suppression may only contain ACT/DELEGATE")
        if tuple(sorted(set(self.suppressed_by_hold), key=PULSE_ACTION_ORDER.index)) != self.suppressed_by_hold:
            raise PersistentPulseError("hold suppression is not canonical")
        overlap = set(eligible_actions) & set(self.suppressed_by_hold)
        if overlap:
            raise PersistentPulseError(
                "eligible actions and hold suppression must be disjoint"
            )

    @property
    def eligible_actions(self) -> tuple[str, ...]:
        return tuple(item.action for item in self.eligible)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "pulse_id": self.pulse_id,
            "observation_id": self.observation_id,
            "state_id": self.state_id,
            "generation": self.generation,
            "state_digest_sha256": self.state_digest_sha256,
            "input_sha256": self.input_sha256,
            "eligible": [asdict(item) for item in self.eligible],
            "suppressed_by_hold": list(self.suppressed_by_hold),
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def classify_pulse_eligibility(pulse_input: PulseInput) -> PulseDecision:
    """Classify explicit eligibility without selecting or executing an action."""
    if not isinstance(pulse_input, PulseInput):
        raise PersistentPulseError("pulse_input must be a PulseInput")

    refs = {
        "ACT": pulse_input.act_candidate_ref,
        "ASK": pulse_input.ask_candidate_ref,
        "OBSERVE": pulse_input.observe_candidate_ref,
        "WAIT": pulse_input.wait_condition_ref,
        "HOLD": pulse_input.hold_reason_ref,
        "DELEGATE": pulse_input.delegate_candidate_ref,
    }
    suppressed: list[str] = []
    if pulse_input.hold_reason_ref is not None:
        for action in ("ACT", "DELEGATE"):
            if refs[action] is not None:
                suppressed.append(action)
                refs[action] = None

    eligible = tuple(
        PulseEligibility(action=action, basis_ref=refs[action])
        for action in PULSE_ACTION_ORDER
        if refs[action] is not None
    )
    return PulseDecision(
        schema=PULSE_DECISION_SCHEMA,
        pulse_id=pulse_input.pulse_id,
        observation_id=pulse_input.observation_id,
        state_id=pulse_input.state_id,
        generation=pulse_input.generation,
        state_digest_sha256=pulse_input.state_digest_sha256,
        input_sha256=pulse_input.sha256(),
        eligible=eligible,
        suppressed_by_hold=tuple(suppressed),
    )


__all__ = [
    "PULSE_ACTION_ORDER",
    "PULSE_DECISION_SCHEMA",
    "PULSE_INPUT_SCHEMA",
    "PersistentPulseError",
    "PulseDecision",
    "PulseEligibility",
    "PulseInput",
    "classify_pulse_eligibility",
]
