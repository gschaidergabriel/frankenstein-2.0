"""Deterministic Familiarity / prediction-error binding for Frankenstein 2.0.

F2-WP-302 generation 1.

The component consumes an already-produced :class:`PredictionResidual` plus familiarity
that is *derived from an exact F2-WP-301 RetrievalNeed/RetrievalPlan pair*.  It never
accepts a free caller-supplied familiarity score and never accepts a bare RetrievalResult.
That boundary prevents an internally inconsistent, directly constructed RetrievalResult
from being promoted into familiarity/attention evidence without the WP-301 plan identity
that selected it.

Authority boundary::

    FAMILIARITY != OBSERVATION
    RETRIEVAL_REFERENCE != WORLD_FACT
    RETRIEVAL_PLAN != CANONICAL_TRUTH
    PREDICTION_RESIDUAL != COMPLETION

A contradictory residual always remains a contradiction regardless of familiarity.  The
binding emits only a deterministic candidate attention signal for downstream
Hyperposition/GWT handling.  It has no persistence, model/provider/tool, effect,
completion, VPS, physical-GRID10, or whole-system authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from .emergent_retrieval import (
    CLASSIFICATION_SELECTED,
    PLAN_CLASSIFICATION,
    PLAN_SCHEMA,
    RESULT_SCHEMA,
    RetrievalNeed,
    RetrievalPlan,
    RetrievalResult,
)
from .memory_lifecycle import STATUS_ACTIVE, STATUS_DEGRADED
from .prediction_contract import PredictionResidual

FAMILIARITY_EVIDENCE_SCHEMA = "FRANKENSTEIN2_RETRIEVAL_BOUND_FAMILIARITY_EVIDENCE/v2"
FAMILIARITY_PREDICTION_SIGNAL_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_PREDICTION_SIGNAL/v2"

RELATION_MATCH = "MATCH"
RELATION_MISMATCH = "MISMATCH"
RELATION_UNKNOWN = "UNKNOWN"

SIGNAL_CLASSIFICATION = (
    "EPISTEMIC_ATTENTION_CANDIDATE_NOT_OBSERVATION_TRUTH_EFFECT_OR_COMPLETION"
)
FAMILIARITY_CLASSIFICATION = (
    "RETRIEVAL_PLAN_BOUND_FAMILIARITY_NOT_OBSERVATION_OR_WORLD_TRUTH"
)

MAX_BASIS_POINTS = 10_000
_MAX_IDENTIFIER_LENGTH = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FAMILIARITY_TOKEN = object()


class FamiliarityPredictionError(ValueError):
    """Fail-closed Familiarity/prediction binding error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise FamiliarityPredictionError(f"{name} must be a string")
    if not value or value != value.strip():
        raise FamiliarityPredictionError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise FamiliarityPredictionError(
            f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters"
        )
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise FamiliarityPredictionError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FamiliarityPredictionError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 1:
        raise FamiliarityPredictionError("generation must be a positive integer")
    return value


def _basis_points(name: str, value: Any) -> int:
    if type(value) is not int:
        raise FamiliarityPredictionError(f"{name} must be an integer basis-point value")
    if value < 0 or value > MAX_BASIS_POINTS:
        raise FamiliarityPredictionError(
            f"{name} must be between 0 and {MAX_BASIS_POINTS}"
        )
    return value


def _refs(name: str, values: Iterable[str], *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise FamiliarityPredictionError(f"{name} must be an iterable of references")
    refs = tuple(_identifier(name, value) for value in values)
    if not allow_empty and not refs:
        raise FamiliarityPredictionError(f"{name} must contain at least one reference")
    if len(set(refs)) != len(refs):
        raise FamiliarityPredictionError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_selected_result(result: RetrievalResult, need: RetrievalNeed) -> str:
    """Validate the WP-301 invariants that WP-302 consumes from a selected result."""
    if not isinstance(result, RetrievalResult):
        raise FamiliarityPredictionError("retrieval plan selected entries must be RetrievalResult")
    if result.schema != RESULT_SCHEMA:
        raise FamiliarityPredictionError("retrieval result schema mismatch")
    _identifier("retrieval memory_id", result.memory_id)
    if type(result.memory_generation) is not int or result.memory_generation < 0:
        raise FamiliarityPredictionError(
            "retrieval memory_generation must be a non-negative integer"
        )
    _sha256("memory_state_sha256", result.memory_state_sha256)
    _sha256("candidate_sha256", result.candidate_sha256)
    if result.lifecycle_status not in {STATUS_ACTIVE, STATUS_DEGRADED}:
        raise FamiliarityPredictionError(
            "selected retrieval result must reference ACTIVE or DEGRADED memory"
        )
    if result.selected is not True or result.classification != CLASSIFICATION_SELECTED:
        raise FamiliarityPredictionError(
            "retrieval plan selected entry violates WP301 selection classification"
        )
    _identifier("payload_ref", result.payload_ref)
    _sha256("payload_sha256", result.payload_sha256)
    if result.successor_ref is not None:
        raise FamiliarityPredictionError(
            "selected retrieval result must not carry successor redirect metadata"
        )
    provenance_refs = _refs("retrieval provenance_ref", result.provenance_refs)
    if provenance_refs != tuple(sorted(result.provenance_refs)):
        raise FamiliarityPredictionError("retrieval provenance refs are not canonical")

    overlap_axes = tuple(result.overlap_axes)
    if len(set(overlap_axes)) != len(overlap_axes):
        raise FamiliarityPredictionError("retrieval overlap_axes contain duplicates")
    if result.overlap_count != len(overlap_axes):
        raise FamiliarityPredictionError("retrieval overlap_count does not match overlap_axes")
    if result.overlap_count < need.min_overlap_axes:
        raise FamiliarityPredictionError(
            "selected retrieval result does not satisfy retrieval need overlap threshold"
        )
    if any(axis not in need.axes for axis in overlap_axes):
        raise FamiliarityPredictionError("retrieval overlap axis is outside the bound need")

    score_pairs = tuple(result.signal_scores_bp)
    if len({axis for axis, _ in score_pairs}) != len(score_pairs):
        raise FamiliarityPredictionError("retrieval signal_scores contain duplicate axes")
    score_map = dict(score_pairs)
    if tuple(sorted(score_map)) != tuple(sorted(need.axes)):
        raise FamiliarityPredictionError(
            "retrieval signal score axes do not match the bound need"
        )
    for axis, score in score_pairs:
        _identifier("retrieval signal axis", axis)
        _basis_points(f"retrieval signal score[{axis}]", score)
    computed_overlap = tuple(axis for axis in need.axes if score_map[axis] > 0)
    if tuple(sorted(overlap_axes)) != tuple(sorted(computed_overlap)):
        raise FamiliarityPredictionError(
            "retrieval overlap axes are inconsistent with signal scores"
        )

    evidence_pairs = tuple(result.signal_evidence_refs)
    if len({axis for axis, _ in evidence_pairs}) != len(evidence_pairs):
        raise FamiliarityPredictionError("retrieval signal evidence contains duplicate axes")
    evidence_map = dict(evidence_pairs)
    if tuple(sorted(evidence_map)) != tuple(sorted(need.axes)):
        raise FamiliarityPredictionError(
            "retrieval signal evidence axes do not match the bound need"
        )
    for axis in need.axes:
        _refs(f"retrieval signal evidence[{axis}]", evidence_map[axis])

    weights = dict(need.axis_weights_bp)
    weighted_numerator = sum(score_map[axis] * weights[axis] for axis in need.axes)
    weight_total = sum(weights.values())
    expected_weighted = weighted_numerator // weight_total
    expected_bottleneck = min(score_map.values())
    expected_rank = expected_weighted * result.overlap_count
    if result.weighted_score_bp != expected_weighted:
        raise FamiliarityPredictionError("retrieval weighted_score_bp is inconsistent")
    if result.bottleneck_score_bp != expected_bottleneck:
        raise FamiliarityPredictionError("retrieval bottleneck_score_bp is inconsistent")
    if result.rank_score != expected_rank:
        raise FamiliarityPredictionError("retrieval rank_score is inconsistent")

    return _digest(result.as_dict())


@dataclass(frozen=True, slots=True, init=False)
class FamiliarityEvidence:
    """Familiarity derived only from one exact, caller-fenced WP-301 plan."""

    schema: str
    retrieval_need_id: str
    retrieval_need_sha256: str
    retrieval_plan_sha256: str
    familiarity_score_bp: int
    retrieval_memory_ids: tuple[str, ...]
    retrieval_result_sha256s: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    classification: str

    def __init__(
        self,
        *,
        schema: str,
        retrieval_need_id: str,
        retrieval_need_sha256: str,
        retrieval_plan_sha256: str,
        familiarity_score_bp: int,
        retrieval_memory_ids: Iterable[str],
        retrieval_result_sha256s: Iterable[str],
        evidence_refs: Iterable[str],
        classification: str,
        _token: object | None = None,
    ) -> None:
        if _token is not _FAMILIARITY_TOKEN:
            raise FamiliarityPredictionError(
                "FamiliarityEvidence must be derived through from_retrieval_plan"
            )
        if schema != FAMILIARITY_EVIDENCE_SCHEMA:
            raise FamiliarityPredictionError("familiarity evidence schema mismatch")
        if classification != FAMILIARITY_CLASSIFICATION:
            raise FamiliarityPredictionError("familiarity evidence classification mismatch")
        need_id = _identifier("retrieval_need_id", retrieval_need_id)
        need_sha = _sha256("retrieval_need_sha256", retrieval_need_sha256)
        plan_sha = _sha256("retrieval_plan_sha256", retrieval_plan_sha256)
        score = _basis_points("familiarity_score_bp", familiarity_score_bp)
        memory_ids = tuple(_identifier("retrieval_memory_id", value) for value in retrieval_memory_ids)
        result_shas = tuple(_sha256("retrieval_result_sha256", value) for value in retrieval_result_sha256s)
        if len(memory_ids) != len(result_shas):
            raise FamiliarityPredictionError(
                "retrieval memory/result identity cardinality mismatch"
            )
        if len(set(memory_ids)) != len(memory_ids):
            raise FamiliarityPredictionError("duplicate retrieval memory identity")
        refs = _refs("familiarity evidence_ref", evidence_refs)

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "retrieval_need_id", need_id)
        object.__setattr__(self, "retrieval_need_sha256", need_sha)
        object.__setattr__(self, "retrieval_plan_sha256", plan_sha)
        object.__setattr__(self, "familiarity_score_bp", score)
        object.__setattr__(self, "retrieval_memory_ids", memory_ids)
        object.__setattr__(self, "retrieval_result_sha256s", result_shas)
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "classification", classification)

    @classmethod
    def from_retrieval_plan(
        cls,
        *,
        need: RetrievalNeed,
        plan: RetrievalPlan,
        expected_plan_sha256: str,
    ) -> "FamiliarityEvidence":
        if not isinstance(need, RetrievalNeed):
            raise FamiliarityPredictionError("need must be RetrievalNeed")
        if not isinstance(plan, RetrievalPlan):
            raise FamiliarityPredictionError("plan must be RetrievalPlan")
        if plan.schema != PLAN_SCHEMA or plan.classification != PLAN_CLASSIFICATION:
            raise FamiliarityPredictionError("retrieval plan schema/classification mismatch")

        expected_plan_sha256 = _sha256("expected_plan_sha256", expected_plan_sha256)
        actual_plan_sha256 = plan.sha256()
        if actual_plan_sha256 != expected_plan_sha256:
            raise FamiliarityPredictionError("retrieval plan digest fence mismatch")
        need_sha256 = need.sha256()
        if plan.need_id != need.need_id:
            raise FamiliarityPredictionError("retrieval plan need_id fence mismatch")
        if plan.need_sha256 != need_sha256:
            raise FamiliarityPredictionError("retrieval plan need digest fence mismatch")
        if type(plan.candidate_count) is not int or plan.candidate_count < 0:
            raise FamiliarityPredictionError("retrieval plan candidate_count is invalid")
        if plan.candidate_count != len(plan.selected) + len(plan.not_selected):
            raise FamiliarityPredictionError(
                "retrieval plan candidate_count does not cover selected/not_selected entries"
            )
        if len(plan.selected) > need.limit:
            raise FamiliarityPredictionError("retrieval plan selected set exceeds need limit")

        memory_ids: list[str] = []
        result_shas: list[str] = []
        all_refs: list[str] = list(need.evidence_refs)
        familiarity_score_bp = 0
        for result in plan.selected:
            result_sha = _validate_selected_result(result, need)
            if result.memory_id in memory_ids:
                raise FamiliarityPredictionError("duplicate selected retrieval memory identity")
            memory_ids.append(result.memory_id)
            result_shas.append(result_sha)
            familiarity_score_bp = max(familiarity_score_bp, result.weighted_score_bp)
            all_refs.extend(result.provenance_refs)
            for _, refs in result.signal_evidence_refs:
                all_refs.extend(refs)

        # Evidence refs are a set-like provenance envelope, not a ranking input.
        canonical_refs = tuple(sorted(set(_refs("retrieval evidence_ref", all_refs))))
        return cls(
            schema=FAMILIARITY_EVIDENCE_SCHEMA,
            retrieval_need_id=need.need_id,
            retrieval_need_sha256=need_sha256,
            retrieval_plan_sha256=actual_plan_sha256,
            familiarity_score_bp=familiarity_score_bp,
            retrieval_memory_ids=tuple(memory_ids),
            retrieval_result_sha256s=tuple(result_shas),
            evidence_refs=canonical_refs,
            classification=FAMILIARITY_CLASSIFICATION,
            _token=_FAMILIARITY_TOKEN,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class FamiliarityPredictionSignal:
    schema: str
    prediction_id: str
    target_id: str
    observation_id: str
    generation: int
    residual_sha256: str
    residual_exact_match: bool
    residual_mismatch_count: int
    familiarity_score_bp: int
    familiarity_evidence_sha256: str
    retrieval_need_id: str
    retrieval_need_sha256: str
    retrieval_plan_sha256: str
    retrieval_memory_ids: tuple[str, ...]
    retrieval_result_sha256s: tuple[str, ...]
    relation: str
    attention_priority_bp: int
    familiarity_evidence_refs: tuple[str, ...]
    contradiction_evidence_refs: tuple[str, ...]
    classification: str = SIGNAL_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_familiarity_to_prediction_residual(
    *,
    residual: PredictionResidual,
    expected_prediction_id: str,
    expected_generation: int,
    expected_residual_sha256: str,
    familiarity: FamiliarityEvidence,
    contradiction_evidence_refs: Iterable[str] = (),
) -> FamiliarityPredictionSignal:
    """Bind an exact residual to retrieval-plan-bound familiarity evidence."""
    if not isinstance(residual, PredictionResidual):
        raise FamiliarityPredictionError("residual must be a PredictionResidual")
    if not isinstance(familiarity, FamiliarityEvidence):
        raise FamiliarityPredictionError("familiarity must be FamiliarityEvidence")

    expected_prediction_id = _identifier("expected_prediction_id", expected_prediction_id)
    expected_generation = _generation(expected_generation)
    expected_residual_sha256 = _sha256(
        "expected_residual_sha256", expected_residual_sha256
    )

    actual_residual_sha256 = residual.sha256()
    if residual.prediction_id != expected_prediction_id:
        raise FamiliarityPredictionError("prediction_id fence mismatch")
    if residual.generation != expected_generation:
        raise FamiliarityPredictionError("generation fence mismatch")
    if actual_residual_sha256 != expected_residual_sha256:
        raise FamiliarityPredictionError("residual digest fence mismatch")

    contradiction_refs = _refs(
        "contradiction evidence_ref",
        contradiction_evidence_refs,
        allow_empty=True,
    )

    if residual.exact_match:
        if residual.mismatch_count != 0:
            raise FamiliarityPredictionError(
                "residual invariant violated: exact_match with nonzero mismatch_count"
            )
        relation = (
            RELATION_MATCH
            if familiarity.familiarity_score_bp > 0
            else RELATION_UNKNOWN
        )
        attention_priority_bp = familiarity.familiarity_score_bp
    else:
        if residual.mismatch_count < 1:
            raise FamiliarityPredictionError(
                "residual invariant violated: mismatch without mismatch_count"
            )
        if not contradiction_refs:
            raise FamiliarityPredictionError(
                "mismatching residual requires explicit contradiction evidence"
            )
        relation = RELATION_MISMATCH
        # A current contradiction may never be down-ranked by familiar memory.
        attention_priority_bp = MAX_BASIS_POINTS

    return FamiliarityPredictionSignal(
        schema=FAMILIARITY_PREDICTION_SIGNAL_SCHEMA,
        prediction_id=residual.prediction_id,
        target_id=residual.target_id,
        observation_id=residual.observation_id,
        generation=residual.generation,
        residual_sha256=actual_residual_sha256,
        residual_exact_match=residual.exact_match,
        residual_mismatch_count=residual.mismatch_count,
        familiarity_score_bp=familiarity.familiarity_score_bp,
        familiarity_evidence_sha256=familiarity.sha256(),
        retrieval_need_id=familiarity.retrieval_need_id,
        retrieval_need_sha256=familiarity.retrieval_need_sha256,
        retrieval_plan_sha256=familiarity.retrieval_plan_sha256,
        retrieval_memory_ids=familiarity.retrieval_memory_ids,
        retrieval_result_sha256s=familiarity.retrieval_result_sha256s,
        relation=relation,
        attention_priority_bp=attention_priority_bp,
        familiarity_evidence_refs=familiarity.evidence_refs,
        contradiction_evidence_refs=contradiction_refs,
    )


__all__ = [
    "FAMILIARITY_EVIDENCE_SCHEMA",
    "FAMILIARITY_PREDICTION_SIGNAL_SCHEMA",
    "RELATION_MATCH",
    "RELATION_MISMATCH",
    "RELATION_UNKNOWN",
    "SIGNAL_CLASSIFICATION",
    "FAMILIARITY_CLASSIFICATION",
    "MAX_BASIS_POINTS",
    "FamiliarityEvidence",
    "FamiliarityPredictionError",
    "FamiliarityPredictionSignal",
    "bind_familiarity_to_prediction_residual",
]
