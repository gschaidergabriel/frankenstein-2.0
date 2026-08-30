"""Deterministic rebuildable memory-salience projection for Frankenstein 2.0.

F2-WP-300 generation 2 repository-component scope only.

The canonical memory payload and lifecycle remain owned by ``MemoryLifecycleState``.  This
module derives only two WP301-compatible retrieval signals from explicit caller evidence:
TEMPORAL and STATE.  It never reads a wall clock, persistence, payload bytes, retrieval
counts, model/provider/tool output, or effect state.

A projection is rebuildable evidence, not memory or truth authority.  VERIFIED_USE is an
explicit anchor kind whose evidence reference must be supplied by an upstream typed boundary;
this module binds that reference but never authenticates or mints it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from .emergent_retrieval import (
    AXIS_STATE,
    AXIS_TEMPORAL,
    MAX_BASIS_POINTS,
    RetrievalSignal,
)
from .memory_lifecycle import (
    MemoryLifecycleState,
    STATUS_ACTIVE,
    STATUS_DEGRADED,
    STATUS_SUPERSEDED,
)

POLICY_SCHEMA = "FRANKENSTEIN2_MEMORY_SALIENCE_POLICY/v1"
EVIDENCE_SCHEMA = "FRANKENSTEIN2_MEMORY_SALIENCE_EVIDENCE/v1"
PROJECTION_SCHEMA = "FRANKENSTEIN2_MEMORY_SALIENCE_PROJECTION/v1"

ANCHOR_CREATION = "CREATION_EVIDENCE"
ANCHOR_VERIFIED_USE = "VERIFIED_USE_EVIDENCE"
_ALLOWED_ANCHORS = frozenset({ANCHOR_CREATION, ANCHOR_VERIFIED_USE})

PROJECTION_CLASSIFICATION = (
    "DETERMINISTIC_REBUILDABLE_RETRIEVAL_SIGNAL_PROJECTION_NOT_MEMORY_TRUTH_OR_EFFECT_AUTHORITY"
)
MAX_TICK = (1 << 63) - 1
_MAX_ID_LEN = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MemorySalienceProjectionError(ValueError):
    """Fail-closed salience projection contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise MemorySalienceProjectionError(f"{name} must be a string")
    if not value or value != value.strip():
        raise MemorySalienceProjectionError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise MemorySalienceProjectionError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise MemorySalienceProjectionError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise MemorySalienceProjectionError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _basis_points(name: str, value: Any) -> int:
    if type(value) is not int or value < 0 or value > MAX_BASIS_POINTS:
        raise MemorySalienceProjectionError(
            f"{name} must be an integer in [0, {MAX_BASIS_POINTS}]"
        )
    return value


def _tick(name: str, value: Any) -> int:
    if type(value) is not int or value < 0 or value > MAX_TICK:
        raise MemorySalienceProjectionError(
            f"{name} must be an integer in [0, {MAX_TICK}]"
        )
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise MemorySalienceProjectionError(f"{name} must be an iterable of references")
    refs = tuple(_identifier(name, value) for value in values)
    if not refs:
        raise MemorySalienceProjectionError(f"{name} must contain at least one reference")
    if len(set(refs)) != len(refs):
        raise MemorySalienceProjectionError(f"{name} contains duplicate references")
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
        raise MemorySalienceProjectionError("value is not canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MemorySaliencePolicy:
    """Explicit caller policy; no product-wide default is implied by this component."""

    schema: str
    policy_id: str
    min_temporal_bp: int
    decay_bp_per_tick: int
    degraded_state_bp: int

    def __post_init__(self) -> None:
        if self.schema != POLICY_SCHEMA:
            raise MemorySalienceProjectionError("memory salience policy schema mismatch")
        object.__setattr__(self, "policy_id", _identifier("policy_id", self.policy_id))
        object.__setattr__(
            self,
            "min_temporal_bp",
            _basis_points("min_temporal_bp", self.min_temporal_bp),
        )
        object.__setattr__(
            self,
            "decay_bp_per_tick",
            _basis_points("decay_bp_per_tick", self.decay_bp_per_tick),
        )
        object.__setattr__(
            self,
            "degraded_state_bp",
            _basis_points("degraded_state_bp", self.degraded_state_bp),
        )

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        min_temporal_bp: int,
        decay_bp_per_tick: int,
        degraded_state_bp: int,
    ) -> "MemorySaliencePolicy":
        return cls(
            schema=POLICY_SCHEMA,
            policy_id=policy_id,
            min_temporal_bp=min_temporal_bp,
            decay_bp_per_tick=decay_bp_per_tick,
            degraded_state_bp=degraded_state_bp,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class MemorySalienceEvidence:
    """Explicit time/use evidence plus exact lifecycle fences."""

    schema: str
    expected_memory_id: str
    expected_generation: int
    expected_state_sha256: str
    reference_tick: int
    anchor_tick: int
    anchor_kind: str
    anchor_evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != EVIDENCE_SCHEMA:
            raise MemorySalienceProjectionError("memory salience evidence schema mismatch")
        object.__setattr__(
            self,
            "expected_memory_id",
            _identifier("expected_memory_id", self.expected_memory_id),
        )
        if type(self.expected_generation) is not int or self.expected_generation < 0:
            raise MemorySalienceProjectionError(
                "expected_generation must be a non-negative integer"
            )
        object.__setattr__(
            self,
            "expected_state_sha256",
            _sha256("expected_state_sha256", self.expected_state_sha256),
        )
        object.__setattr__(self, "reference_tick", _tick("reference_tick", self.reference_tick))
        object.__setattr__(self, "anchor_tick", _tick("anchor_tick", self.anchor_tick))
        if self.anchor_tick > self.reference_tick:
            raise MemorySalienceProjectionError("reference_tick must be >= anchor_tick")
        if self.anchor_kind not in _ALLOWED_ANCHORS:
            raise MemorySalienceProjectionError(
                f"unsupported anchor_kind: {self.anchor_kind!r}"
            )
        object.__setattr__(
            self,
            "anchor_evidence_refs",
            _refs("anchor evidence_ref", self.anchor_evidence_refs),
        )

    @classmethod
    def create(
        cls,
        *,
        memory: MemoryLifecycleState,
        reference_tick: int,
        anchor_tick: int,
        anchor_kind: str,
        anchor_evidence_refs: Iterable[str],
    ) -> "MemorySalienceEvidence":
        if not isinstance(memory, MemoryLifecycleState):
            raise MemorySalienceProjectionError("memory must be a MemoryLifecycleState")
        return cls(
            schema=EVIDENCE_SCHEMA,
            expected_memory_id=memory.memory_id,
            expected_generation=memory.generation,
            expected_state_sha256=memory.sha256(),
            reference_tick=reference_tick,
            anchor_tick=anchor_tick,
            anchor_kind=anchor_kind,
            anchor_evidence_refs=tuple(anchor_evidence_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class MemorySalienceProjection:
    """Immutable rebuildable projection carrying only derived WP301 signal evidence."""

    schema: str
    memory_id: str
    memory_generation: int
    memory_state_sha256: str
    lifecycle_status: str
    payload_ref: str
    payload_sha256: str
    provenance_refs: tuple[str, ...]
    policy_id: str
    policy_sha256: str
    evidence_sha256: str
    reference_tick: int
    anchor_tick: int
    anchor_kind: str
    anchor_evidence_refs: tuple[str, ...]
    temporal_signal: RetrievalSignal
    state_signal: RetrievalSignal
    classification: str = PROJECTION_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != PROJECTION_SCHEMA:
            raise MemorySalienceProjectionError("memory salience projection schema mismatch")
        if self.classification != PROJECTION_CLASSIFICATION:
            raise MemorySalienceProjectionError("memory salience projection classification mismatch")
        if self.temporal_signal.axis != AXIS_TEMPORAL:
            raise MemorySalienceProjectionError("temporal signal axis mismatch")
        if self.state_signal.axis != AXIS_STATE:
            raise MemorySalienceProjectionError("state signal axis mismatch")

    @property
    def signals(self) -> tuple[RetrievalSignal, RetrievalSignal]:
        return (self.temporal_signal, self.state_signal)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "memory_id": self.memory_id,
            "memory_generation": self.memory_generation,
            "memory_state_sha256": self.memory_state_sha256,
            "lifecycle_status": self.lifecycle_status,
            "payload_ref": self.payload_ref,
            "payload_sha256": self.payload_sha256,
            "provenance_refs": list(self.provenance_refs),
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "evidence_sha256": self.evidence_sha256,
            "reference_tick": self.reference_tick,
            "anchor_tick": self.anchor_tick,
            "anchor_kind": self.anchor_kind,
            "anchor_evidence_refs": list(self.anchor_evidence_refs),
            "temporal_signal": self.temporal_signal.as_dict(),
            "state_signal": self.state_signal.as_dict(),
            "classification": self.classification,
            "persistence_authority": "NONE",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "runtime_credit": 0,
            "whole_system_acceptance": False,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def build_memory_salience_projection(
    memory: MemoryLifecycleState,
    *,
    policy: MemorySaliencePolicy,
    evidence: MemorySalienceEvidence,
) -> MemorySalienceProjection:
    """Derive exact TEMPORAL/STATE signals from explicit policy and evidence only."""
    if not isinstance(memory, MemoryLifecycleState):
        raise MemorySalienceProjectionError("memory must be a MemoryLifecycleState")
    if not isinstance(policy, MemorySaliencePolicy):
        raise MemorySalienceProjectionError("policy must be a MemorySaliencePolicy")
    if not isinstance(evidence, MemorySalienceEvidence):
        raise MemorySalienceProjectionError("evidence must be MemorySalienceEvidence")

    state_sha = memory.sha256()
    if evidence.expected_memory_id != memory.memory_id:
        raise MemorySalienceProjectionError("memory_id fence mismatch")
    if evidence.expected_generation != memory.generation:
        raise MemorySalienceProjectionError("memory generation fence mismatch")
    if evidence.expected_state_sha256 != state_sha:
        raise MemorySalienceProjectionError("memory state digest fence mismatch")

    age_ticks = evidence.reference_tick - evidence.anchor_tick
    temporal_score = max(
        policy.min_temporal_bp,
        MAX_BASIS_POINTS - policy.decay_bp_per_tick * age_ticks,
    )
    if memory.status == STATUS_ACTIVE:
        state_score = MAX_BASIS_POINTS
    elif memory.status == STATUS_DEGRADED:
        state_score = policy.degraded_state_bp
    elif memory.status == STATUS_SUPERSEDED:
        # WP301 remains the redirect-only authority for SUPERSEDED memories.  Zero here is
        # merely a derived signal; it never makes the lifecycle state selectable.
        state_score = 0
    else:  # defensive in case lifecycle grows a new state without this contract changing.
        raise MemorySalienceProjectionError(
            f"unsupported memory lifecycle status: {memory.status!r}"
        )

    policy_sha = policy.sha256()
    evidence_sha = evidence.sha256()
    signal_evidence_refs = tuple(
        sorted(
            set(evidence.anchor_evidence_refs)
            | {
                f"memory-state-sha256:{state_sha}",
                f"memory-salience-policy-sha256:{policy_sha}",
                f"memory-salience-evidence-sha256:{evidence_sha}",
            }
        )
    )
    temporal = RetrievalSignal.create(
        axis=AXIS_TEMPORAL,
        score_bp=temporal_score,
        evidence_refs=signal_evidence_refs,
    )
    state = RetrievalSignal.create(
        axis=AXIS_STATE,
        score_bp=state_score,
        evidence_refs=signal_evidence_refs,
    )
    return MemorySalienceProjection(
        schema=PROJECTION_SCHEMA,
        memory_id=memory.memory_id,
        memory_generation=memory.generation,
        memory_state_sha256=state_sha,
        lifecycle_status=memory.status,
        payload_ref=memory.payload_ref,
        payload_sha256=memory.payload_sha256,
        provenance_refs=memory.provenance_refs,
        policy_id=policy.policy_id,
        policy_sha256=policy_sha,
        evidence_sha256=evidence_sha,
        reference_tick=evidence.reference_tick,
        anchor_tick=evidence.anchor_tick,
        anchor_kind=evidence.anchor_kind,
        anchor_evidence_refs=evidence.anchor_evidence_refs,
        temporal_signal=temporal,
        state_signal=state,
    )


__all__ = [
    "ANCHOR_CREATION",
    "ANCHOR_VERIFIED_USE",
    "EVIDENCE_SCHEMA",
    "MAX_TICK",
    "POLICY_SCHEMA",
    "PROJECTION_CLASSIFICATION",
    "PROJECTION_SCHEMA",
    "MemorySalienceEvidence",
    "MemorySaliencePolicy",
    "MemorySalienceProjection",
    "MemorySalienceProjectionError",
    "build_memory_salience_projection",
]
