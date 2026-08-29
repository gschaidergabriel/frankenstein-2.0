"""Deterministic HOLD/stop/rumination exit control for Frankenstein 2.0.

F2-WP-509 generation 1.

This component decides only whether a caller-supplied cognitive cycle may continue or must
leave the current rumination loop through an explicit typed transition. It does not infer
world facts, goals, causality or completion; schedule wakeups; call models/providers/tools;
read or write UnifiedDB; mutate GRID/GWT state; authorize effects; or mint runtime credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

RUMINATION_SNAPSHOT_SCHEMA = "FRANKENSTEIN2_RUMINATION_SNAPSHOT/v1"
RUMINATION_POLICY_SCHEMA = "FRANKENSTEIN2_RUMINATION_EXIT_POLICY/v1"
RUMINATION_DECISION_SCHEMA = "FRANKENSTEIN2_RUMINATION_EXIT_DECISION/v1"

SNAPSHOT_CLASSIFICATION = "LOOP_CONTROL_INPUT_NOT_WORLD_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"
POLICY_CLASSIFICATION = "EXPLICIT_LOOP_EXIT_POLICY_NOT_EFFECT_OR_COMPLETION_AUTHORITY"
DECISION_CLASSIFICATION = "LOOP_EXIT_DECISION_NOT_WORLD_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"

EXIT_ACT = "ACT"
EXIT_ASK = "ASK"
EXIT_WAIT = "WAIT"
EXIT_OBSERVE = "OBSERVE"
EXIT_DEFER_HOLD = "DEFER_HOLD"
CONTINUE = "CONTINUE"

_ALLOWED_EXITS = frozenset({EXIT_ACT, EXIT_ASK, EXIT_WAIT, EXIT_OBSERVE, EXIT_DEFER_HOLD})
_EPISTEMIC_STATES = frozenset({"CLEAR", "UNKNOWN", "CONFLICT"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_COUNTER = 2**31 - 1
_MAX_REFS = 4096


class RuminationControlError(ValueError):
    """Fail-closed rumination-control contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise RuminationControlError(f"{name} must be a string")
    if not value or value != value.strip():
        raise RuminationControlError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise RuminationControlError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RuminationControlError(f"{name} contains control characters")
    return value


def _counter(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_COUNTER:
        raise RuminationControlError(f"{name} must be an integer in [0, {_MAX_COUNTER}]")
    return value


def _generation(name: str, value: Any) -> int:
    return _counter(name, value)


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise RuminationControlError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str], *, require_nonempty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise RuminationControlError(f"{name} must be an iterable of reference strings")
    refs = tuple(_identifier(name, value) for value in values)
    if require_nonempty and not refs:
        raise RuminationControlError(f"{name} must contain at least one reference")
    if len(refs) > _MAX_REFS:
        raise RuminationControlError(f"{name} exceeds {_MAX_REFS} references")
    if len(refs) != len(set(refs)):
        raise RuminationControlError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RuminationControlError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RuminationSnapshot:
    """Explicit bounded state of one cognitive-loop iteration."""

    schema: str
    cycle_id: str
    cycle_generation: int
    cycle_sha256: str
    iteration_count: int
    unchanged_state_count: int
    remaining_work_units: int
    epistemic_state: str
    explicit_hold: bool
    wake_hold_ref: str | None
    wake_hold_sha256: str | None
    provenance_refs: tuple[str, ...]
    classification: str = SNAPSHOT_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != RUMINATION_SNAPSHOT_SCHEMA:
            raise RuminationControlError("rumination snapshot schema mismatch")
        if self.classification != SNAPSHOT_CLASSIFICATION:
            raise RuminationControlError("rumination snapshot classification mismatch")
        object.__setattr__(self, "cycle_id", _identifier("cycle_id", self.cycle_id))
        object.__setattr__(self, "cycle_generation", _generation("cycle_generation", self.cycle_generation))
        object.__setattr__(self, "cycle_sha256", _sha256("cycle_sha256", self.cycle_sha256))
        object.__setattr__(self, "iteration_count", _counter("iteration_count", self.iteration_count))
        object.__setattr__(self, "unchanged_state_count", _counter("unchanged_state_count", self.unchanged_state_count))
        object.__setattr__(self, "remaining_work_units", _counter("remaining_work_units", self.remaining_work_units))
        if self.unchanged_state_count > self.iteration_count:
            raise RuminationControlError("unchanged_state_count cannot exceed iteration_count")
        if self.epistemic_state not in _EPISTEMIC_STATES:
            raise RuminationControlError(
                f"epistemic_state must be one of {sorted(_EPISTEMIC_STATES)}"
            )
        if type(self.explicit_hold) is not bool:
            raise RuminationControlError("explicit_hold must be a boolean")
        if (self.wake_hold_ref is None) != (self.wake_hold_sha256 is None):
            raise RuminationControlError("wake/HOLD binding must be fully present or fully absent")
        if self.wake_hold_ref is not None:
            object.__setattr__(self, "wake_hold_ref", _identifier("wake_hold_ref", self.wake_hold_ref))
            object.__setattr__(self, "wake_hold_sha256", _sha256("wake_hold_sha256", self.wake_hold_sha256))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    @classmethod
    def create(
        cls,
        *,
        cycle_id: str,
        cycle_generation: int,
        cycle_sha256: str,
        iteration_count: int,
        unchanged_state_count: int,
        remaining_work_units: int,
        epistemic_state: str,
        explicit_hold: bool,
        provenance_refs: Iterable[str],
        wake_hold_ref: str | None = None,
        wake_hold_sha256: str | None = None,
    ) -> "RuminationSnapshot":
        return cls(
            schema=RUMINATION_SNAPSHOT_SCHEMA,
            cycle_id=cycle_id,
            cycle_generation=cycle_generation,
            cycle_sha256=cycle_sha256,
            iteration_count=iteration_count,
            unchanged_state_count=unchanged_state_count,
            remaining_work_units=remaining_work_units,
            epistemic_state=epistemic_state,
            explicit_hold=explicit_hold,
            wake_hold_ref=wake_hold_ref,
            wake_hold_sha256=wake_hold_sha256,
            provenance_refs=tuple(provenance_refs),
        )

    def assert_cycle_binding(self, *, cycle_id: str, generation: int, sha256: str) -> None:
        if self.cycle_id != cycle_id:
            raise RuminationControlError("cycle_id binding mismatch")
        if self.cycle_generation != generation:
            raise RuminationControlError("cycle generation binding mismatch")
        if self.cycle_sha256 != sha256:
            raise RuminationControlError("cycle digest binding mismatch")

    def assert_wake_hold_binding(self, *, ref: str | None, sha256: str | None) -> None:
        if self.wake_hold_ref != ref:
            raise RuminationControlError("wake/HOLD reference binding mismatch")
        if self.wake_hold_sha256 != sha256:
            raise RuminationControlError("wake/HOLD digest binding mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RuminationExitPolicy:
    """Explicit resource/termination policy; never an effect or completion authority."""

    schema: str
    policy_id: str
    generation: int
    max_iterations: int
    max_unchanged_iterations: int
    allowed_exits: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    classification: str = POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != RUMINATION_POLICY_SCHEMA:
            raise RuminationControlError("rumination policy schema mismatch")
        if self.classification != POLICY_CLASSIFICATION:
            raise RuminationControlError("rumination policy classification mismatch")
        object.__setattr__(self, "policy_id", _identifier("policy_id", self.policy_id))
        object.__setattr__(self, "generation", _generation("generation", self.generation))
        _counter("max_iterations", self.max_iterations)
        _counter("max_unchanged_iterations", self.max_unchanged_iterations)
        if self.max_iterations < 1:
            raise RuminationControlError("max_iterations must be at least 1")
        if self.max_unchanged_iterations < 1:
            raise RuminationControlError("max_unchanged_iterations must be at least 1")
        exits = tuple(_identifier("allowed_exit", value) for value in self.allowed_exits)
        if not exits:
            raise RuminationControlError("allowed_exits must contain at least one transition")
        if any(value not in _ALLOWED_EXITS for value in exits):
            raise RuminationControlError(f"allowed_exits must be a subset of {sorted(_ALLOWED_EXITS)}")
        if len(exits) != len(set(exits)):
            raise RuminationControlError("allowed_exits contains duplicates")
        object.__setattr__(self, "allowed_exits", tuple(sorted(exits)))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        generation: int,
        max_iterations: int,
        max_unchanged_iterations: int,
        allowed_exits: Iterable[str],
        provenance_refs: Iterable[str],
    ) -> "RuminationExitPolicy":
        return cls(
            schema=RUMINATION_POLICY_SCHEMA,
            policy_id=policy_id,
            generation=generation,
            max_iterations=max_iterations,
            max_unchanged_iterations=max_unchanged_iterations,
            allowed_exits=tuple(allowed_exits),
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RuminationExitDecision:
    schema: str
    decision_id: str
    snapshot_sha256: str
    policy_id: str
    policy_generation: int
    policy_sha256: str
    transition: str
    reasons: tuple[str, ...]
    can_continue: bool
    unresolved_preserved: bool
    provenance_refs: tuple[str, ...]
    classification: str = DECISION_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != RUMINATION_DECISION_SCHEMA:
            raise RuminationControlError("rumination decision schema mismatch")
        if self.classification != DECISION_CLASSIFICATION:
            raise RuminationControlError("rumination decision classification mismatch")
        object.__setattr__(self, "decision_id", _identifier("decision_id", self.decision_id))
        object.__setattr__(self, "snapshot_sha256", _sha256("snapshot_sha256", self.snapshot_sha256))
        object.__setattr__(self, "policy_id", _identifier("policy_id", self.policy_id))
        object.__setattr__(self, "policy_generation", _generation("policy_generation", self.policy_generation))
        object.__setattr__(self, "policy_sha256", _sha256("policy_sha256", self.policy_sha256))
        if self.transition != CONTINUE and self.transition not in _ALLOWED_EXITS:
            raise RuminationControlError("unsupported transition")
        if type(self.can_continue) is not bool or self.can_continue != (self.transition == CONTINUE):
            raise RuminationControlError("can_continue must exactly match CONTINUE transition")
        if type(self.unresolved_preserved) is not bool:
            raise RuminationControlError("unresolved_preserved must be a boolean")
        reasons = tuple(_identifier("reason", value) for value in self.reasons)
        if not reasons:
            raise RuminationControlError("reasons must contain at least one reason")
        if len(reasons) != len(set(reasons)):
            raise RuminationControlError("reasons contains duplicates")
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "completion_claimed": False,
            "effect_authority": "NONE",
            "wake_scheduled": False,
            "runtime_credit": 0,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _require_allowed(policy: RuminationExitPolicy, transition: str) -> str:
    if transition not in policy.allowed_exits:
        raise RuminationControlError(
            f"required fail-closed transition {transition} is not allowed by policy"
        )
    return transition


def evaluate_rumination_exit(
    *,
    decision_id: str,
    snapshot: RuminationSnapshot,
    policy: RuminationExitPolicy,
    expected_cycle_id: str,
    expected_cycle_generation: int,
    expected_cycle_sha256: str,
    expected_wake_hold_ref: str | None = None,
    expected_wake_hold_sha256: str | None = None,
    provenance_refs: Iterable[str],
) -> RuminationExitDecision:
    """Return CONTINUE or one mandatory typed exit without claiming completion/effects."""
    if type(snapshot) is not RuminationSnapshot:
        raise RuminationControlError("snapshot must be concrete RuminationSnapshot")
    if type(policy) is not RuminationExitPolicy:
        raise RuminationControlError("policy must be concrete RuminationExitPolicy")

    snapshot.assert_cycle_binding(
        cycle_id=_identifier("expected_cycle_id", expected_cycle_id),
        generation=_generation("expected_cycle_generation", expected_cycle_generation),
        sha256=_sha256("expected_cycle_sha256", expected_cycle_sha256),
    )
    if expected_wake_hold_ref is not None or expected_wake_hold_sha256 is not None:
        if expected_wake_hold_ref is None or expected_wake_hold_sha256 is None:
            raise RuminationControlError("expected wake/HOLD binding must be fully present or absent")
        snapshot.assert_wake_hold_binding(
            ref=_identifier("expected_wake_hold_ref", expected_wake_hold_ref),
            sha256=_sha256("expected_wake_hold_sha256", expected_wake_hold_sha256),
        )

    unresolved = snapshot.epistemic_state in {"UNKNOWN", "CONFLICT"}
    reasons: list[str] = []

    if snapshot.explicit_hold:
        transition = _require_allowed(policy, EXIT_DEFER_HOLD)
        reasons.append("EXPLICIT_HOLD")
    elif snapshot.remaining_work_units == 0:
        transition = _require_allowed(policy, EXIT_WAIT)
        reasons.append("WORK_BUDGET_EXHAUSTED")
    elif snapshot.iteration_count >= policy.max_iterations:
        if unresolved:
            transition = _require_allowed(policy, EXIT_ASK)
            reasons.extend(("ITERATION_LIMIT_REACHED", f"EPISTEMIC_{snapshot.epistemic_state}_PRESERVED"))
        else:
            transition = _require_allowed(policy, EXIT_DEFER_HOLD)
            reasons.append("ITERATION_LIMIT_REACHED")
    elif snapshot.unchanged_state_count >= policy.max_unchanged_iterations:
        transition = _require_allowed(policy, EXIT_OBSERVE)
        reasons.append("UNCHANGED_STATE_LIMIT_REACHED")
        if unresolved:
            reasons.append(f"EPISTEMIC_{snapshot.epistemic_state}_PRESERVED")
    else:
        transition = CONTINUE
        reasons.append("BOUNDED_CONTINUATION_AVAILABLE")
        if unresolved:
            reasons.append(f"EPISTEMIC_{snapshot.epistemic_state}_PRESERVED")

    return RuminationExitDecision(
        schema=RUMINATION_DECISION_SCHEMA,
        decision_id=decision_id,
        snapshot_sha256=snapshot.sha256(),
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=policy.sha256(),
        transition=transition,
        reasons=tuple(reasons),
        can_continue=transition == CONTINUE,
        unresolved_preserved=unresolved,
        provenance_refs=tuple(provenance_refs),
    )


__all__ = [
    "CONTINUE",
    "DECISION_CLASSIFICATION",
    "EXIT_ACT",
    "EXIT_ASK",
    "EXIT_DEFER_HOLD",
    "EXIT_OBSERVE",
    "EXIT_WAIT",
    "POLICY_CLASSIFICATION",
    "RUMINATION_DECISION_SCHEMA",
    "RUMINATION_POLICY_SCHEMA",
    "RUMINATION_SNAPSHOT_SCHEMA",
    "RuminationControlError",
    "RuminationExitDecision",
    "RuminationExitPolicy",
    "RuminationSnapshot",
    "SNAPSHOT_CLASSIFICATION",
    "evaluate_rumination_exit",
]
