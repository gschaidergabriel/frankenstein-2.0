"""Deterministic GRID10 SituationFrame and cycle contract for Frankenstein 2.0.

F2-WP-500 generation 1.

This module is deliberately persistence-agnostic and authority-free. It canonicalizes only
explicit caller-supplied typed references into an immutable SituationFrame, then binds a
bounded next-cycle contract to that exact frame identity/generation/digest. It does not
retrieve hidden state, infer facts/goals/causality/completion, allocate effects, call models
or tools, read/write UnifiedDB, or mint GRID/GWT runtime credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

SITUATION_FRAME_SCHEMA = "FRANKENSTEIN2_GRID10_SITUATION_FRAME/v1"
CYCLE_CONTRACT_SCHEMA = "FRANKENSTEIN2_GRID10_CYCLE_CONTRACT/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_REF_COUNT = 4096
_MAX_GRID_CELLS = 10
_EPISTEMIC_KINDS = frozenset(
    {"OBSERVATION", "MEMORY", "HYPOTHESIS", "SIMULATION", "CONFLICT", "UNKNOWN"}
)
_EXIT_ORDER = ("ACT", "ASK", "WAIT", "OBSERVE", "DEFER", "HOLD")
_ALLOWED_EXITS = frozenset(_EXIT_ORDER)


class SituationFrameError(ValueError):
    """Fail-closed SituationFrame/cycle-contract validation error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise SituationFrameError(f"{name} must be a string")
    if not value or value != value.strip():
        raise SituationFrameError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise SituationFrameError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise SituationFrameError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise SituationFrameError(f"{name} must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise SituationFrameError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str], *, require_nonempty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise SituationFrameError(f"{name} must be an iterable of reference strings")
    cleaned = tuple(sorted({_identifier(name, value) for value in values}))
    if len(cleaned) > _MAX_REF_COUNT:
        raise SituationFrameError(f"{name} exceeds {_MAX_REF_COUNT} unique references")
    if require_nonempty and not cleaned:
        raise SituationFrameError(f"{name} must contain at least one explicit reference")
    return cleaned


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EpistemicRef:
    """One explicitly typed cognitive reference; the type is not inferred here."""

    kind: str
    ref: str

    def __post_init__(self) -> None:
        if self.kind not in _EPISTEMIC_KINDS:
            raise SituationFrameError(
                f"epistemic kind must be one of {sorted(_EPISTEMIC_KINDS)}"
            )
        object.__setattr__(self, "ref", _identifier("epistemic ref", self.ref))

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "ref": self.ref}


def _epistemic_refs(values: Iterable[EpistemicRef]) -> tuple[EpistemicRef, ...]:
    if isinstance(values, (str, bytes)):
        raise SituationFrameError("epistemic_refs must be an iterable of EpistemicRef")
    by_ref: dict[str, EpistemicRef] = {}
    for item in values:
        if type(item) is not EpistemicRef:
            raise SituationFrameError("epistemic_refs items must be concrete EpistemicRef")
        prior = by_ref.get(item.ref)
        if prior is not None and prior.kind != item.kind:
            raise SituationFrameError(
                f"epistemic ref {item.ref!r} has conflicting explicit kinds "
                f"{prior.kind} and {item.kind}"
            )
        by_ref[item.ref] = item
    if len(by_ref) > _MAX_REF_COUNT:
        raise SituationFrameError(
            f"epistemic_refs exceeds {_MAX_REF_COUNT} unique references"
        )
    return tuple(sorted(by_ref.values(), key=lambda item: (item.kind, item.ref)))


@dataclass(frozen=True, slots=True)
class SituationFrame:
    """Immutable explicit snapshot presented to one bounded cognitive cycle."""

    schema: str
    frame_id: str
    cycle_id: str
    generation: int
    situation_epoch: int
    agency_state_ref: str
    agency_state_generation: int
    agency_state_sha256: str
    epistemic_refs: tuple[EpistemicRef, ...]
    goal_refs: tuple[str, ...]
    prediction_refs: tuple[str, ...]
    context_refs: tuple[str, ...]
    unresolved_alternative_refs: tuple[str, ...]
    completion_deficit_refs: tuple[str, ...]
    authority_scope_refs: tuple[str, ...]
    do_not_repeat_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    classification: str = "EXPLICIT_COGNITIVE_FRAME_NOT_WORLD_TRUTH_OR_EFFECT_AUTHORITY"

    def __post_init__(self) -> None:
        if self.schema != SITUATION_FRAME_SCHEMA:
            raise SituationFrameError("situation frame schema mismatch")
        object.__setattr__(self, "frame_id", _identifier("frame_id", self.frame_id))
        object.__setattr__(self, "cycle_id", _identifier("cycle_id", self.cycle_id))
        object.__setattr__(self, "generation", _generation("generation", self.generation))
        object.__setattr__(
            self, "situation_epoch", _generation("situation_epoch", self.situation_epoch)
        )
        object.__setattr__(
            self, "agency_state_ref", _identifier("agency_state_ref", self.agency_state_ref)
        )
        object.__setattr__(
            self,
            "agency_state_generation",
            _generation("agency_state_generation", self.agency_state_generation),
        )
        object.__setattr__(
            self,
            "agency_state_sha256",
            _sha256("agency_state_sha256", self.agency_state_sha256),
        )
        object.__setattr__(self, "epistemic_refs", _epistemic_refs(self.epistemic_refs))
        for field_name, require_nonempty in (
            ("goal_refs", False),
            ("prediction_refs", False),
            ("context_refs", False),
            ("unresolved_alternative_refs", False),
            ("completion_deficit_refs", False),
            ("authority_scope_refs", True),
            ("do_not_repeat_refs", False),
            ("provenance_refs", True),
        ):
            object.__setattr__(
                self,
                field_name,
                _refs(field_name, getattr(self, field_name), require_nonempty=require_nonempty),
            )

    @classmethod
    def create(
        cls,
        *,
        frame_id: str,
        cycle_id: str,
        generation: int,
        situation_epoch: int,
        agency_state_ref: str,
        agency_state_generation: int,
        agency_state_sha256: str,
        epistemic_refs: Iterable[EpistemicRef] = (),
        goal_refs: Iterable[str] = (),
        prediction_refs: Iterable[str] = (),
        context_refs: Iterable[str] = (),
        unresolved_alternative_refs: Iterable[str] = (),
        completion_deficit_refs: Iterable[str] = (),
        authority_scope_refs: Iterable[str],
        do_not_repeat_refs: Iterable[str] = (),
        provenance_refs: Iterable[str],
    ) -> "SituationFrame":
        return cls(
            schema=SITUATION_FRAME_SCHEMA,
            frame_id=frame_id,
            cycle_id=cycle_id,
            generation=generation,
            situation_epoch=situation_epoch,
            agency_state_ref=agency_state_ref,
            agency_state_generation=agency_state_generation,
            agency_state_sha256=agency_state_sha256,
            epistemic_refs=tuple(epistemic_refs),
            goal_refs=tuple(goal_refs),
            prediction_refs=tuple(prediction_refs),
            context_refs=tuple(context_refs),
            unresolved_alternative_refs=tuple(unresolved_alternative_refs),
            completion_deficit_refs=tuple(completion_deficit_refs),
            authority_scope_refs=tuple(authority_scope_refs),
            do_not_repeat_refs=tuple(do_not_repeat_refs),
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "frame_id": self.frame_id,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "situation_epoch": self.situation_epoch,
            "agency_state_ref": self.agency_state_ref,
            "agency_state_generation": self.agency_state_generation,
            "agency_state_sha256": self.agency_state_sha256,
            "epistemic_refs": [item.as_dict() for item in self.epistemic_refs],
            "goal_refs": list(self.goal_refs),
            "prediction_refs": list(self.prediction_refs),
            "context_refs": list(self.context_refs),
            "unresolved_alternative_refs": list(self.unresolved_alternative_refs),
            "completion_deficit_refs": list(self.completion_deficit_refs),
            "authority_scope_refs": list(self.authority_scope_refs),
            "do_not_repeat_refs": list(self.do_not_repeat_refs),
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CycleContract:
    """Bounded next-cycle permission envelope tied to one exact SituationFrame."""

    schema: str
    contract_id: str
    cycle_id: str
    cycle_generation: int
    expected_frame_id: str
    expected_frame_generation: int
    expected_frame_sha256: str
    max_grid_cells: int
    allowed_exits: tuple[str, ...]
    continuation_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    classification: str = "CYCLE_PERMISSION_ENVELOPE_NOT_EFFECT_OR_COMPLETION_AUTHORITY"

    def __post_init__(self) -> None:
        if self.schema != CYCLE_CONTRACT_SCHEMA:
            raise SituationFrameError("cycle contract schema mismatch")
        object.__setattr__(self, "contract_id", _identifier("contract_id", self.contract_id))
        object.__setattr__(self, "cycle_id", _identifier("cycle_id", self.cycle_id))
        object.__setattr__(
            self, "cycle_generation", _generation("cycle_generation", self.cycle_generation)
        )
        object.__setattr__(
            self, "expected_frame_id", _identifier("expected_frame_id", self.expected_frame_id)
        )
        object.__setattr__(
            self,
            "expected_frame_generation",
            _generation("expected_frame_generation", self.expected_frame_generation),
        )
        object.__setattr__(
            self,
            "expected_frame_sha256",
            _sha256("expected_frame_sha256", self.expected_frame_sha256),
        )
        if type(self.max_grid_cells) is not int or not 1 <= self.max_grid_cells <= _MAX_GRID_CELLS:
            raise SituationFrameError(
                f"max_grid_cells must be an integer in [1, {_MAX_GRID_CELLS}]"
            )
        exits = tuple(self.allowed_exits)
        if not exits:
            raise SituationFrameError("allowed_exits must contain at least one exit")
        if any(exit_name not in _ALLOWED_EXITS for exit_name in exits):
            raise SituationFrameError(f"allowed_exits must be a subset of {list(_EXIT_ORDER)}")
        object.__setattr__(
            self,
            "allowed_exits",
            tuple(exit_name for exit_name in _EXIT_ORDER if exit_name in set(exits)),
        )
        object.__setattr__(
            self,
            "continuation_refs",
            _refs("continuation_refs", self.continuation_refs, require_nonempty=True),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs, require_nonempty=True),
        )

    @classmethod
    def for_frame(
        cls,
        frame: SituationFrame,
        *,
        contract_id: str,
        cycle_generation: int,
        max_grid_cells: int,
        allowed_exits: Iterable[str],
        continuation_refs: Iterable[str],
        provenance_refs: Iterable[str],
    ) -> "CycleContract":
        if type(frame) is not SituationFrame:
            raise SituationFrameError("frame must be concrete SituationFrame")
        return cls(
            schema=CYCLE_CONTRACT_SCHEMA,
            contract_id=contract_id,
            cycle_id=frame.cycle_id,
            cycle_generation=cycle_generation,
            expected_frame_id=frame.frame_id,
            expected_frame_generation=frame.generation,
            expected_frame_sha256=frame.sha256(),
            max_grid_cells=max_grid_cells,
            allowed_exits=tuple(allowed_exits),
            continuation_refs=tuple(continuation_refs),
            provenance_refs=tuple(provenance_refs),
        )

    def assert_matches(self, frame: SituationFrame) -> None:
        if type(frame) is not SituationFrame:
            raise SituationFrameError("frame must be concrete SituationFrame")
        if self.cycle_id != frame.cycle_id:
            raise SituationFrameError("cycle_id mismatch")
        if self.expected_frame_id != frame.frame_id:
            raise SituationFrameError("frame_id mismatch")
        if self.expected_frame_generation != frame.generation:
            raise SituationFrameError("frame generation mismatch")
        if self.expected_frame_sha256 != frame.sha256():
            raise SituationFrameError("frame digest mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())
