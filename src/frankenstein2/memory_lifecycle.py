"""Deterministic non-destructive memory lifecycle primitive for Frankenstein 2.0.

F2-WP-300 generation 1.

This module evolves only explicit caller-supplied memory identity and payload references.
It does not read a clock, infer decay, rank retrieval, interpret payload semantics, read or
write UnifiedDB, invoke a model/provider/tool, authorize effects, or mint completion.

The payload reference, payload digest and source provenance are immutable across lifecycle
transitions. Degradation changes lifecycle state only; it never deletes or rewrites memory
content. Every transition is fenced by exact memory id, generation and prior-state digest.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

MEMORY_STATE_SCHEMA = "FRANKENSTEIN2_MEMORY_LIFECYCLE_STATE/v1"
MEMORY_TRANSITION_SCHEMA = "FRANKENSTEIN2_MEMORY_LIFECYCLE_TRANSITION/v1"
MEMORY_RECEIPT_SCHEMA = "FRANKENSTEIN2_MEMORY_LIFECYCLE_RECEIPT/v1"

STATUS_ACTIVE = "ACTIVE"
STATUS_DEGRADED = "DEGRADED"
STATUS_SUPERSEDED = "SUPERSEDED"

TRANSITION_DEGRADE = "DEGRADE"
TRANSITION_RESTORE = "RESTORE"
TRANSITION_SUPERSEDE = "SUPERSEDE"

_STATE_CLASSIFICATION = "PRESERVED_MEMORY_PAYLOAD_LIFECYCLE_NOT_TRUTH_OR_RETRIEVAL_AUTHORITY"
_RECEIPT_CLASSIFICATION = "LIFECYCLE_TRANSITION_RECEIPT_NOT_PERSISTENCE_OR_EFFECT_AUTHORITY"
_ALLOWED_STATUSES = frozenset({STATUS_ACTIVE, STATUS_DEGRADED, STATUS_SUPERSEDED})
_ALLOWED_TRANSITIONS = frozenset({TRANSITION_DEGRADE, TRANSITION_RESTORE, TRANSITION_SUPERSEDE})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_STATE_TOKEN = object()


class MemoryLifecycleError(ValueError):
    """Fail-closed memory lifecycle contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise MemoryLifecycleError(f"{name} must be a string")
    if not value or value != value.strip():
        raise MemoryLifecycleError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise MemoryLifecycleError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise MemoryLifecycleError(f"{name} contains control characters")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise MemoryLifecycleError("generation must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise MemoryLifecycleError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise MemoryLifecycleError(f"{name} must be an iterable of reference strings")
    raw = tuple(_identifier(name, value) for value in values)
    if not raw:
        raise MemoryLifecycleError(f"{name} must contain at least one explicit reference")
    if len(set(raw)) != len(raw):
        raise MemoryLifecycleError(f"{name} contains duplicate references")
    return tuple(sorted(raw))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, init=False)
class MemoryLifecycleState:
    schema: str
    memory_id: str
    generation: int
    payload_ref: str
    payload_sha256: str
    provenance_refs: tuple[str, ...]
    status: str
    successor_ref: str | None
    parent_state_sha256: str | None
    classification: str

    def __init__(
        self,
        *,
        schema: str,
        memory_id: str,
        generation: int,
        payload_ref: str,
        payload_sha256: str,
        provenance_refs: Iterable[str],
        status: str,
        successor_ref: str | None,
        parent_state_sha256: str | None,
        classification: str,
        _token: object | None = None,
    ) -> None:
        if _token is not _STATE_TOKEN:
            raise MemoryLifecycleError(
                "MemoryLifecycleState must be created through create_memory or apply_memory_transition"
            )
        if schema != MEMORY_STATE_SCHEMA:
            raise MemoryLifecycleError("memory state schema mismatch")
        memory_id = _identifier("memory_id", memory_id)
        generation = _generation(generation)
        payload_ref = _identifier("payload_ref", payload_ref)
        payload_sha256 = _sha256("payload_sha256", payload_sha256)
        provenance_refs = _refs("provenance_ref", provenance_refs)
        if status not in _ALLOWED_STATUSES:
            raise MemoryLifecycleError(f"unsupported memory status: {status!r}")
        if successor_ref is not None:
            successor_ref = _identifier("successor_ref", successor_ref)
        if status == STATUS_SUPERSEDED:
            if successor_ref is None:
                raise MemoryLifecycleError("SUPERSEDED state requires successor_ref")
            if successor_ref == memory_id:
                raise MemoryLifecycleError("successor_ref must not self-reference memory_id")
        elif successor_ref is not None:
            raise MemoryLifecycleError("non-SUPERSEDED state must not carry successor_ref")
        if parent_state_sha256 is not None:
            parent_state_sha256 = _sha256("parent_state_sha256", parent_state_sha256)
        if generation == 0 and parent_state_sha256 is not None:
            raise MemoryLifecycleError("generation 0 must not carry parent_state_sha256")
        if generation > 0 and parent_state_sha256 is None:
            raise MemoryLifecycleError("nonzero generation requires parent_state_sha256")
        if classification != _STATE_CLASSIFICATION:
            raise MemoryLifecycleError("memory state classification mismatch")

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "memory_id", memory_id)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(self, "payload_ref", payload_ref)
        object.__setattr__(self, "payload_sha256", payload_sha256)
        object.__setattr__(self, "provenance_refs", provenance_refs)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "successor_ref", successor_ref)
        object.__setattr__(self, "parent_state_sha256", parent_state_sha256)
        object.__setattr__(self, "classification", classification)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class MemoryTransition:
    schema: str
    transition_id: str
    memory_id: str
    expected_generation: int
    expected_state_sha256: str
    kind: str
    evidence_refs: tuple[str, ...]
    successor_ref: str | None = None

    def __post_init__(self) -> None:
        if self.schema != MEMORY_TRANSITION_SCHEMA:
            raise MemoryLifecycleError("memory transition schema mismatch")
        object.__setattr__(self, "transition_id", _identifier("transition_id", self.transition_id))
        object.__setattr__(self, "memory_id", _identifier("memory_id", self.memory_id))
        object.__setattr__(self, "expected_generation", _generation(self.expected_generation))
        object.__setattr__(
            self,
            "expected_state_sha256",
            _sha256("expected_state_sha256", self.expected_state_sha256),
        )
        if self.kind not in _ALLOWED_TRANSITIONS:
            raise MemoryLifecycleError(f"unsupported memory transition: {self.kind!r}")
        object.__setattr__(self, "evidence_refs", _refs("transition evidence_ref", self.evidence_refs))
        if self.kind == TRANSITION_SUPERSEDE:
            if self.successor_ref is None:
                raise MemoryLifecycleError("SUPERSEDE transition requires successor_ref")
            successor = _identifier("successor_ref", self.successor_ref)
            if successor == self.memory_id:
                raise MemoryLifecycleError("successor_ref must not self-reference memory_id")
            object.__setattr__(self, "successor_ref", successor)
        elif self.successor_ref is not None:
            raise MemoryLifecycleError("only SUPERSEDE transition may carry successor_ref")

    @classmethod
    def create(
        cls,
        *,
        transition_id: str,
        memory_id: str,
        expected_generation: int,
        expected_state_sha256: str,
        kind: str,
        evidence_refs: Iterable[str],
        successor_ref: str | None = None,
    ) -> "MemoryTransition":
        return cls(
            schema=MEMORY_TRANSITION_SCHEMA,
            transition_id=transition_id,
            memory_id=memory_id,
            expected_generation=expected_generation,
            expected_state_sha256=expected_state_sha256,
            kind=kind,
            evidence_refs=tuple(evidence_refs),
            successor_ref=successor_ref,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class MemoryTransitionReceipt:
    schema: str
    transition_id: str
    memory_id: str
    from_generation: int
    to_generation: int
    from_state_sha256: str
    to_state_sha256: str
    transition_sha256: str
    kind: str
    evidence_refs: tuple[str, ...]
    classification: str = _RECEIPT_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != MEMORY_RECEIPT_SCHEMA:
            raise MemoryLifecycleError("memory receipt schema mismatch")
        _identifier("transition_id", self.transition_id)
        _identifier("memory_id", self.memory_id)
        _generation(self.from_generation)
        _generation(self.to_generation)
        if self.to_generation != self.from_generation + 1:
            raise MemoryLifecycleError("receipt generation must advance exactly once")
        _sha256("from_state_sha256", self.from_state_sha256)
        _sha256("to_state_sha256", self.to_state_sha256)
        _sha256("transition_sha256", self.transition_sha256)
        if self.kind not in _ALLOWED_TRANSITIONS:
            raise MemoryLifecycleError("receipt transition kind mismatch")
        object.__setattr__(self, "evidence_refs", _refs("receipt evidence_ref", self.evidence_refs))
        if self.classification != _RECEIPT_CLASSIFICATION:
            raise MemoryLifecycleError("memory receipt classification mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def create_memory(
    *,
    memory_id: str,
    payload_ref: str,
    payload_sha256: str,
    provenance_refs: Iterable[str],
) -> MemoryLifecycleState:
    """Create generation-zero preserved memory state from explicit caller data only."""
    return MemoryLifecycleState(
        schema=MEMORY_STATE_SCHEMA,
        memory_id=memory_id,
        generation=0,
        payload_ref=payload_ref,
        payload_sha256=payload_sha256,
        provenance_refs=tuple(provenance_refs),
        status=STATUS_ACTIVE,
        successor_ref=None,
        parent_state_sha256=None,
        classification=_STATE_CLASSIFICATION,
        _token=_STATE_TOKEN,
    )


def apply_memory_transition(
    state: MemoryLifecycleState,
    transition: MemoryTransition,
) -> tuple[MemoryLifecycleState, MemoryTransitionReceipt]:
    """Apply one explicit lifecycle transition under exact prior-state fences."""
    if not isinstance(state, MemoryLifecycleState):
        raise MemoryLifecycleError("state must be a MemoryLifecycleState")
    if not isinstance(transition, MemoryTransition):
        raise MemoryLifecycleError("transition must be a MemoryTransition")
    if transition.memory_id != state.memory_id:
        raise MemoryLifecycleError("memory_id fence mismatch")
    if transition.expected_generation != state.generation:
        raise MemoryLifecycleError("generation fence mismatch")
    prior_sha = state.sha256()
    if transition.expected_state_sha256 != prior_sha:
        raise MemoryLifecycleError("state digest fence mismatch")
    if state.status == STATUS_SUPERSEDED:
        raise MemoryLifecycleError("SUPERSEDED memory lifecycle is terminal")

    if transition.kind == TRANSITION_DEGRADE:
        if state.status != STATUS_ACTIVE:
            raise MemoryLifecycleError("DEGRADE requires ACTIVE state")
        next_status = STATUS_DEGRADED
        successor_ref = None
    elif transition.kind == TRANSITION_RESTORE:
        if state.status != STATUS_DEGRADED:
            raise MemoryLifecycleError("RESTORE requires DEGRADED state")
        next_status = STATUS_ACTIVE
        successor_ref = None
    else:
        if state.status not in {STATUS_ACTIVE, STATUS_DEGRADED}:
            raise MemoryLifecycleError("SUPERSEDE requires ACTIVE or DEGRADED state")
        next_status = STATUS_SUPERSEDED
        successor_ref = transition.successor_ref

    next_state = MemoryLifecycleState(
        schema=MEMORY_STATE_SCHEMA,
        memory_id=state.memory_id,
        generation=state.generation + 1,
        payload_ref=state.payload_ref,
        payload_sha256=state.payload_sha256,
        provenance_refs=state.provenance_refs,
        status=next_status,
        successor_ref=successor_ref,
        parent_state_sha256=prior_sha,
        classification=_STATE_CLASSIFICATION,
        _token=_STATE_TOKEN,
    )
    receipt = MemoryTransitionReceipt(
        schema=MEMORY_RECEIPT_SCHEMA,
        transition_id=transition.transition_id,
        memory_id=state.memory_id,
        from_generation=state.generation,
        to_generation=next_state.generation,
        from_state_sha256=prior_sha,
        to_state_sha256=next_state.sha256(),
        transition_sha256=transition.sha256(),
        kind=transition.kind,
        evidence_refs=transition.evidence_refs,
    )
    return next_state, receipt


__all__ = [
    "MEMORY_RECEIPT_SCHEMA",
    "MEMORY_STATE_SCHEMA",
    "MEMORY_TRANSITION_SCHEMA",
    "STATUS_ACTIVE",
    "STATUS_DEGRADED",
    "STATUS_SUPERSEDED",
    "TRANSITION_DEGRADE",
    "TRANSITION_RESTORE",
    "TRANSITION_SUPERSEDE",
    "MemoryLifecycleError",
    "MemoryLifecycleState",
    "MemoryTransition",
    "MemoryTransitionReceipt",
    "apply_memory_transition",
    "create_memory",
]
