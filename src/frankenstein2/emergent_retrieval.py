"""Deterministic multi-axis Emergent Retrieval planning for Frankenstein 2.0.

F2-WP-301 generation 1.

This module does not retrieve payload bytes and does not infer relevance.  It consumes
explicit caller-supplied relevance signals that are already tied to evidence references,
combines them deterministically, and returns payload references plus the exact evidence
used to rank them.

Important authority boundary:

    RETRIEVAL_REFERENCE != OBSERVATION
    RETRIEVAL_SCORE != TRUTH
    MEMORY != CURRENT_WORLD_FACT

The planner is persistence-agnostic: no UnifiedDB access, no clock, no vector/model call,
no provider/tool invocation, no EffectGate/CompletionGate authority, and no mutation of
MemoryLifecycleState.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping

from .memory_lifecycle import (
    MemoryLifecycleState,
    STATUS_ACTIVE,
    STATUS_DEGRADED,
    STATUS_SUPERSEDED,
)

SIGNAL_SCHEMA = "FRANKENSTEIN2_RETRIEVAL_SIGNAL/v1"
NEED_SCHEMA = "FRANKENSTEIN2_RETRIEVAL_NEED/v1"
CANDIDATE_SCHEMA = "FRANKENSTEIN2_RETRIEVAL_CANDIDATE/v1"
RESULT_SCHEMA = "FRANKENSTEIN2_RETRIEVAL_RESULT/v1"
PLAN_SCHEMA = "FRANKENSTEIN2_RETRIEVAL_PLAN/v1"

AXIS_GOAL = "goal"
AXIS_SEMANTIC = "semantic"
AXIS_CAUSAL = "causal"
AXIS_TEMPORAL = "temporal"
AXIS_STATE = "state"
AXIS_PROVENANCE = "provenance"
AXIS_CONFIDENCE = "confidence"

ALLOWED_AXES = (
    AXIS_CAUSAL,
    AXIS_CONFIDENCE,
    AXIS_GOAL,
    AXIS_PROVENANCE,
    AXIS_SEMANTIC,
    AXIS_STATE,
    AXIS_TEMPORAL,
)
_ALLOWED_AXIS_SET = frozenset(ALLOWED_AXES)

CLASSIFICATION_SELECTED = "RETRIEVAL_REFERENCE_CANDIDATE_NOT_TRUTH"
CLASSIFICATION_INSUFFICIENT = "INSUFFICIENT_MULTI_AXIS_OVERLAP_NOT_SELECTED"
CLASSIFICATION_SUPERSEDED = "SUPERSEDED_REDIRECT_ONLY_NOT_SELECTED"
CLASSIFICATION_LIMIT = "VALID_OVERLAP_BELOW_RESULT_LIMIT_NOT_SELECTED"
PLAN_CLASSIFICATION = "DETERMINISTIC_RETRIEVAL_PLAN_NOT_WORLD_FACT_OR_EFFECT_AUTHORITY"

MAX_BASIS_POINTS = 10_000
_MAX_ID_LEN = 512


class EmergentRetrievalError(ValueError):
    """Fail-closed retrieval contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise EmergentRetrievalError(f"{name} must be a string")
    if not value or value != value.strip():
        raise EmergentRetrievalError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise EmergentRetrievalError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise EmergentRetrievalError(f"{name} contains control characters")
    return value


def _basis_points(name: str, value: Any, *, allow_zero: bool = True) -> int:
    if type(value) is not int:
        raise EmergentRetrievalError(f"{name} must be an integer basis-point value")
    lower = 0 if allow_zero else 1
    if value < lower or value > MAX_BASIS_POINTS:
        raise EmergentRetrievalError(
            f"{name} must be between {lower} and {MAX_BASIS_POINTS}"
        )
    return value


def _positive_int(name: str, value: Any, *, maximum: int) -> int:
    if type(value) is not int or value < 1 or value > maximum:
        raise EmergentRetrievalError(f"{name} must be an integer in [1, {maximum}]")
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise EmergentRetrievalError(f"{name} must be an iterable of references")
    refs = tuple(_identifier(name, value) for value in values)
    if not refs:
        raise EmergentRetrievalError(f"{name} must contain at least one reference")
    if len(set(refs)) != len(refs):
        raise EmergentRetrievalError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RetrievalSignal:
    """One explicit relevance dimension; the planner never computes this score."""

    schema: str
    axis: str
    score_bp: int
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != SIGNAL_SCHEMA:
            raise EmergentRetrievalError("retrieval signal schema mismatch")
        if self.axis not in _ALLOWED_AXIS_SET:
            raise EmergentRetrievalError(f"unsupported retrieval axis: {self.axis!r}")
        object.__setattr__(self, "score_bp", _basis_points("score_bp", self.score_bp))
        object.__setattr__(self, "evidence_refs", _refs("signal evidence_ref", self.evidence_refs))

    @classmethod
    def create(
        cls,
        *,
        axis: str,
        score_bp: int,
        evidence_refs: Iterable[str],
    ) -> "RetrievalSignal":
        return cls(
            schema=SIGNAL_SCHEMA,
            axis=axis,
            score_bp=score_bp,
            evidence_refs=tuple(evidence_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True, init=False)
class RetrievalNeed:
    """Explicit ranking policy for one bounded retrieval request."""

    schema: str
    need_id: str
    axis_weights_bp: tuple[tuple[str, int], ...]
    min_overlap_axes: int
    limit: int
    evidence_refs: tuple[str, ...]

    def __init__(
        self,
        *,
        schema: str,
        need_id: str,
        axis_weights_bp: Mapping[str, int] | Iterable[tuple[str, int]],
        min_overlap_axes: int,
        limit: int,
        evidence_refs: Iterable[str],
    ) -> None:
        if schema != NEED_SCHEMA:
            raise EmergentRetrievalError("retrieval need schema mismatch")
        need_id = _identifier("need_id", need_id)
        raw_items = tuple(axis_weights_bp.items()) if isinstance(axis_weights_bp, Mapping) else tuple(axis_weights_bp)
        if not raw_items:
            raise EmergentRetrievalError("axis_weights_bp must not be empty")
        axes: set[str] = set()
        normalized: list[tuple[str, int]] = []
        for axis, weight in raw_items:
            if axis not in _ALLOWED_AXIS_SET:
                raise EmergentRetrievalError(f"unsupported retrieval axis: {axis!r}")
            if axis in axes:
                raise EmergentRetrievalError(f"duplicate retrieval axis: {axis!r}")
            axes.add(axis)
            normalized.append((axis, _basis_points(f"weight[{axis}]", weight, allow_zero=False)))
        normalized.sort(key=lambda pair: pair[0])
        min_overlap_axes = _positive_int(
            "min_overlap_axes", min_overlap_axes, maximum=len(normalized)
        )
        # Emergent Retrieval is intentionally not a single-axis semantic nearest-neighbour path.
        if min_overlap_axes < 2:
            raise EmergentRetrievalError("min_overlap_axes must be at least 2")
        limit = _positive_int("limit", limit, maximum=10_000)
        refs = _refs("need evidence_ref", evidence_refs)

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "need_id", need_id)
        object.__setattr__(self, "axis_weights_bp", tuple(normalized))
        object.__setattr__(self, "min_overlap_axes", min_overlap_axes)
        object.__setattr__(self, "limit", limit)
        object.__setattr__(self, "evidence_refs", refs)

    @classmethod
    def create(
        cls,
        *,
        need_id: str,
        axis_weights_bp: Mapping[str, int] | Iterable[tuple[str, int]],
        min_overlap_axes: int = 2,
        limit: int = 8,
        evidence_refs: Iterable[str],
    ) -> "RetrievalNeed":
        return cls(
            schema=NEED_SCHEMA,
            need_id=need_id,
            axis_weights_bp=axis_weights_bp,
            min_overlap_axes=min_overlap_axes,
            limit=limit,
            evidence_refs=evidence_refs,
        )

    @property
    def axes(self) -> tuple[str, ...]:
        return tuple(axis for axis, _ in self.axis_weights_bp)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, init=False)
class RetrievalCandidate:
    """One memory reference plus explicitly supplied independent relevance signals."""

    schema: str
    memory: MemoryLifecycleState
    signals: tuple[RetrievalSignal, ...]
    candidate_evidence_refs: tuple[str, ...]

    def __init__(
        self,
        *,
        schema: str,
        memory: MemoryLifecycleState,
        signals: Iterable[RetrievalSignal],
        candidate_evidence_refs: Iterable[str],
    ) -> None:
        if schema != CANDIDATE_SCHEMA:
            raise EmergentRetrievalError("retrieval candidate schema mismatch")
        if not isinstance(memory, MemoryLifecycleState):
            raise EmergentRetrievalError("memory must be a MemoryLifecycleState")
        raw_signals = tuple(signals)
        if not raw_signals:
            raise EmergentRetrievalError("candidate requires at least one retrieval signal")
        if any(not isinstance(signal, RetrievalSignal) for signal in raw_signals):
            raise EmergentRetrievalError("signals must contain RetrievalSignal values")
        axes = [signal.axis for signal in raw_signals]
        if len(set(axes)) != len(axes):
            raise EmergentRetrievalError("candidate contains duplicate signal axes")
        ordered = tuple(sorted(raw_signals, key=lambda signal: signal.axis))
        refs = _refs("candidate evidence_ref", candidate_evidence_refs)

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "memory", memory)
        object.__setattr__(self, "signals", ordered)
        object.__setattr__(self, "candidate_evidence_refs", refs)

    @classmethod
    def create(
        cls,
        *,
        memory: MemoryLifecycleState,
        signals: Iterable[RetrievalSignal],
        candidate_evidence_refs: Iterable[str],
    ) -> "RetrievalCandidate":
        return cls(
            schema=CANDIDATE_SCHEMA,
            memory=memory,
            signals=signals,
            candidate_evidence_refs=candidate_evidence_refs,
        )

    def signal_map(self) -> dict[str, RetrievalSignal]:
        return {signal.axis: signal for signal in self.signals}

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "memory_state": self.memory.as_dict(),
            "memory_state_sha256": self.memory.sha256(),
            "signals": [signal.as_dict() for signal in self.signals],
            "candidate_evidence_refs": list(self.candidate_evidence_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    schema: str
    memory_id: str
    memory_generation: int
    memory_state_sha256: str
    lifecycle_status: str
    selected: bool
    classification: str
    payload_ref: str | None
    payload_sha256: str | None
    provenance_refs: tuple[str, ...]
    successor_ref: str | None
    overlap_axes: tuple[str, ...]
    overlap_count: int
    weighted_score_bp: int
    bottleneck_score_bp: int
    rank_score: int
    signal_scores_bp: tuple[tuple[str, int], ...]
    signal_evidence_refs: tuple[tuple[str, tuple[str, ...]], ...]
    candidate_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    schema: str
    need_id: str
    need_sha256: str
    selected: tuple[RetrievalResult, ...]
    not_selected: tuple[RetrievalResult, ...]
    candidate_count: int
    classification: str = PLAN_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _evaluate_candidate(need: RetrievalNeed, candidate: RetrievalCandidate) -> RetrievalResult:
    memory = candidate.memory
    state_sha = memory.sha256()
    signal_map = candidate.signal_map()

    missing_axes = tuple(axis for axis in need.axes if axis not in signal_map)
    if missing_axes:
        raise EmergentRetrievalError(
            f"candidate {memory.memory_id!r} missing required signal axes: {missing_axes!r}"
        )

    weights = dict(need.axis_weights_bp)
    score_pairs = tuple((axis, signal_map[axis].score_bp) for axis in need.axes)
    evidence_pairs = tuple((axis, signal_map[axis].evidence_refs) for axis in need.axes)
    overlap_axes = tuple(axis for axis, score in score_pairs if score > 0)
    overlap_count = len(overlap_axes)
    weight_total = sum(weights[axis] for axis in need.axes)
    weighted_numerator = sum(score * weights[axis] for axis, score in score_pairs)
    weighted_score = weighted_numerator // weight_total
    bottleneck_score = min((score for _, score in score_pairs), default=0)
    rank_score = weighted_score * overlap_count

    if memory.status == STATUS_SUPERSEDED:
        return RetrievalResult(
            schema=RESULT_SCHEMA,
            memory_id=memory.memory_id,
            memory_generation=memory.generation,
            memory_state_sha256=state_sha,
            lifecycle_status=memory.status,
            selected=False,
            classification=CLASSIFICATION_SUPERSEDED,
            payload_ref=None,
            payload_sha256=None,
            provenance_refs=memory.provenance_refs,
            successor_ref=memory.successor_ref,
            overlap_axes=overlap_axes,
            overlap_count=overlap_count,
            weighted_score_bp=weighted_score,
            bottleneck_score_bp=bottleneck_score,
            rank_score=rank_score,
            signal_scores_bp=score_pairs,
            signal_evidence_refs=evidence_pairs,
            candidate_sha256=candidate.sha256(),
        )

    if memory.status not in {STATUS_ACTIVE, STATUS_DEGRADED}:
        raise EmergentRetrievalError(f"unsupported memory lifecycle status: {memory.status!r}")

    if overlap_count < need.min_overlap_axes:
        classification = CLASSIFICATION_INSUFFICIENT
        selected = False
    else:
        classification = CLASSIFICATION_SELECTED
        selected = True

    return RetrievalResult(
        schema=RESULT_SCHEMA,
        memory_id=memory.memory_id,
        memory_generation=memory.generation,
        memory_state_sha256=state_sha,
        lifecycle_status=memory.status,
        selected=selected,
        classification=classification,
        payload_ref=memory.payload_ref if selected else None,
        payload_sha256=memory.payload_sha256 if selected else None,
        provenance_refs=memory.provenance_refs,
        successor_ref=memory.successor_ref,
        overlap_axes=overlap_axes,
        overlap_count=overlap_count,
        weighted_score_bp=weighted_score,
        bottleneck_score_bp=bottleneck_score,
        rank_score=rank_score,
        signal_scores_bp=score_pairs,
        signal_evidence_refs=evidence_pairs,
        candidate_sha256=candidate.sha256(),
    )


def build_retrieval_plan(
    need: RetrievalNeed,
    candidates: Iterable[RetrievalCandidate],
) -> RetrievalPlan:
    """Build one deterministic bounded plan from explicit relevance evidence only."""
    if not isinstance(need, RetrievalNeed):
        raise EmergentRetrievalError("need must be a RetrievalNeed")
    candidate_tuple = tuple(candidates)
    if any(not isinstance(candidate, RetrievalCandidate) for candidate in candidate_tuple):
        raise EmergentRetrievalError("candidates must contain RetrievalCandidate values")

    memory_ids = [candidate.memory.memory_id for candidate in candidate_tuple]
    if len(set(memory_ids)) != len(memory_ids):
        raise EmergentRetrievalError("duplicate memory_id candidates are forbidden")

    evaluated = [_evaluate_candidate(need, candidate) for candidate in candidate_tuple]
    eligible = [result for result in evaluated if result.selected]
    rejected = [result for result in evaluated if not result.selected]

    eligible.sort(
        key=lambda result: (
            -result.rank_score,
            -result.overlap_count,
            -result.bottleneck_score_bp,
            result.memory_id,
            result.memory_state_sha256,
        )
    )
    selected = eligible[: need.limit]
    overflow = eligible[need.limit :]
    overflow_rewritten = [
        RetrievalResult(
            **{
                **result.as_dict(),
                "selected": False,
                "classification": CLASSIFICATION_LIMIT,
                "payload_ref": None,
                "payload_sha256": None,
            }
        )
        for result in overflow
    ]
    rejected.extend(overflow_rewritten)
    rejected.sort(key=lambda result: (result.classification, result.memory_id, result.memory_state_sha256))

    return RetrievalPlan(
        schema=PLAN_SCHEMA,
        need_id=need.need_id,
        need_sha256=need.sha256(),
        selected=tuple(selected),
        not_selected=tuple(rejected),
        candidate_count=len(candidate_tuple),
    )


__all__ = [
    "ALLOWED_AXES",
    "AXIS_CAUSAL",
    "AXIS_CONFIDENCE",
    "AXIS_GOAL",
    "AXIS_PROVENANCE",
    "AXIS_SEMANTIC",
    "AXIS_STATE",
    "AXIS_TEMPORAL",
    "CANDIDATE_SCHEMA",
    "CLASSIFICATION_INSUFFICIENT",
    "CLASSIFICATION_LIMIT",
    "CLASSIFICATION_SELECTED",
    "CLASSIFICATION_SUPERSEDED",
    "EmergentRetrievalError",
    "NEED_SCHEMA",
    "PLAN_SCHEMA",
    "RESULT_SCHEMA",
    "RetrievalCandidate",
    "RetrievalNeed",
    "RetrievalPlan",
    "RetrievalResult",
    "RetrievalSignal",
    "SIGNAL_SCHEMA",
    "build_retrieval_plan",
]
