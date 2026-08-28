"""Deterministic Familiarity / prediction-error binding for Frankenstein 2.0.

F2-WP-302 generation 2.

G2 hardens the G1 provenance boundary. Familiarity evidence is accepted only through an
explicit WP301 RetrievalNeed plus RetrievalPlan whose exact digests were fenced when the
binding was constructed. Callers can no longer pass standalone RetrievalResult objects as
familiarity evidence.

Authority invariants:

    FAMILIARITY != OBSERVATION
    RETRIEVAL_SCORE != TRUTH
    RETRIEVAL_PLAN != WORLD_FACT
    PREDICTION_MATCH != COMPLETION
    PREDICTION_MISMATCH != EFFECT_AUTHORITY

All inputs remain caller supplied. Digest binding proves identity/equality at this interface;
it does not turn the caller, memory, retrieval plan, or model output into canonical truth.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from .emergent_retrieval import (
    NEED_SCHEMA,
    PLAN_CLASSIFICATION,
    PLAN_SCHEMA,
    RESULT_SCHEMA,
    RetrievalNeed,
    RetrievalPlan,
    RetrievalResult,
)
from .prediction_contract import PredictionResidual

BINDING_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_PREDICTION_BINDING/v2"
SIGNAL_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_PREDICTION_SIGNAL/v2"

STATUS_MATCH = "MATCH"
STATUS_MISMATCH = "MISMATCH"
STATUS_UNKNOWN = "UNKNOWN"

CLASSIFICATION = "FAMILIARITY_PREDICTION_CANDIDATE_SIGNAL_NOT_WORLD_TRUTH_OR_AUTHORITY"

MAX_BASIS_POINTS = 10_000
_MAX_IDENTIFIER_LENGTH = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FamiliarityPredictionBindingError(ValueError):
    """Fail-closed F2-WP-302 contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise FamiliarityPredictionBindingError(f"{name} must be a string")
    if not value or value != value.strip():
        raise FamiliarityPredictionBindingError(
            f"{name} must be non-empty and already trimmed"
        )
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise FamiliarityPredictionBindingError(
            f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters"
        )
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise FamiliarityPredictionBindingError(f"{name} contains control characters")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 1:
        raise FamiliarityPredictionBindingError("generation must be a positive integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FamiliarityPredictionBindingError(
            f"{name} must be lowercase 64-hex SHA-256"
        )
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise FamiliarityPredictionBindingError(f"{name} must be an iterable of references")
    refs = tuple(_identifier(name, value) for value in values)
    if not refs:
        raise FamiliarityPredictionBindingError(f"{name} must contain at least one reference")
    if len(set(refs)) != len(refs):
        raise FamiliarityPredictionBindingError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _residual_error_bp(residual: PredictionResidual) -> int:
    denominator = max(
        residual.compared_leaf_count
        + len(residual.missing_paths)
        + len(residual.unexpected_paths),
        1,
    )
    return min(MAX_BASIS_POINTS, residual.mismatch_count * MAX_BASIS_POINTS // denominator)


def _validate_retrieval_result(result: RetrievalResult, *, selected: bool) -> None:
    if not isinstance(result, RetrievalResult):
        raise FamiliarityPredictionBindingError(
            "retrieval plan must contain RetrievalResult values"
        )
    if result.schema != RESULT_SCHEMA:
        raise FamiliarityPredictionBindingError("retrieval result schema mismatch")
    _identifier("retrieval memory_id", result.memory_id)
    if type(result.memory_generation) is not int or result.memory_generation < 0:
        raise FamiliarityPredictionBindingError(
            "retrieval memory_generation must be a non-negative integer"
        )
    _sha256("memory_state_sha256", result.memory_state_sha256)
    _sha256("candidate_sha256", result.candidate_sha256)
    if result.selected is not selected:
        raise FamiliarityPredictionBindingError(
            "retrieval result selected flag contradicts plan partition"
        )
    if type(result.weighted_score_bp) is not int or not (
        0 <= result.weighted_score_bp <= MAX_BASIS_POINTS
    ):
        raise FamiliarityPredictionBindingError(
            "retrieval weighted_score_bp must be an integer in [0, 10000]"
        )
    if type(result.bottleneck_score_bp) is not int or not (
        0 <= result.bottleneck_score_bp <= MAX_BASIS_POINTS
    ):
        raise FamiliarityPredictionBindingError(
            "retrieval bottleneck_score_bp must be an integer in [0, 10000]"
        )
    if type(result.overlap_count) is not int or result.overlap_count < 0:
        raise FamiliarityPredictionBindingError("retrieval overlap_count must be non-negative integer")
    if result.overlap_count != len(result.overlap_axes):
        raise FamiliarityPredictionBindingError("retrieval overlap_count is internally inconsistent")
    if type(result.rank_score) is not int or result.rank_score < 0:
        raise FamiliarityPredictionBindingError("retrieval rank_score must be non-negative integer")
    if result.rank_score != result.weighted_score_bp * result.overlap_count:
        raise FamiliarityPredictionBindingError("retrieval rank_score is internally inconsistent")


def _validate_retrieval_provenance(
    *,
    need: RetrievalNeed,
    plan: RetrievalPlan,
    expected_need_id: str,
    expected_need_sha256: str,
    expected_plan_sha256: str,
) -> tuple[RetrievalResult, ...]:
    if not isinstance(need, RetrievalNeed):
        raise FamiliarityPredictionBindingError("retrieval_need must be RetrievalNeed")
    if need.schema != NEED_SCHEMA:
        raise FamiliarityPredictionBindingError("retrieval need schema mismatch")
    if need.need_id != expected_need_id:
        raise FamiliarityPredictionBindingError("retrieval need_id mismatch")
    actual_need_sha = need.sha256()
    if actual_need_sha != expected_need_sha256:
        raise FamiliarityPredictionBindingError("retrieval need digest mismatch")

    if not isinstance(plan, RetrievalPlan):
        raise FamiliarityPredictionBindingError("retrieval_plan must be RetrievalPlan")
    if plan.schema != PLAN_SCHEMA or plan.classification != PLAN_CLASSIFICATION:
        raise FamiliarityPredictionBindingError("retrieval plan schema/classification mismatch")
    if plan.need_id != need.need_id or plan.need_sha256 != actual_need_sha:
        raise FamiliarityPredictionBindingError("retrieval plan is not bound to supplied need")
    if type(plan.candidate_count) is not int or plan.candidate_count < 0:
        raise FamiliarityPredictionBindingError("retrieval plan candidate_count must be non-negative integer")
    if plan.candidate_count != len(plan.selected) + len(plan.not_selected):
        raise FamiliarityPredictionBindingError("retrieval plan candidate_count is internally inconsistent")
    if len(plan.selected) > need.limit:
        raise FamiliarityPredictionBindingError("retrieval plan selected count exceeds need limit")

    all_results = tuple(plan.selected) + tuple(plan.not_selected)
    memory_ids: set[str] = set()
    for result in plan.selected:
        _validate_retrieval_result(result, selected=True)
        if result.memory_id in memory_ids:
            raise FamiliarityPredictionBindingError("duplicate retrieval memory_id in plan")
        memory_ids.add(result.memory_id)
    for result in plan.not_selected:
        _validate_retrieval_result(result, selected=False)
        if result.memory_id in memory_ids:
            raise FamiliarityPredictionBindingError("duplicate retrieval memory_id in plan")
        memory_ids.add(result.memory_id)

    expected_selected_order = tuple(
        sorted(
            plan.selected,
            key=lambda result: (
                -result.rank_score,
                -result.overlap_count,
                -result.bottleneck_score_bp,
                result.memory_id,
                result.memory_state_sha256,
            ),
        )
    )
    if tuple(plan.selected) != expected_selected_order:
        raise FamiliarityPredictionBindingError("retrieval plan selected order is non-canonical")
    expected_rejected_order = tuple(
        sorted(
            plan.not_selected,
            key=lambda result: (result.classification, result.memory_id, result.memory_state_sha256),
        )
    )
    if tuple(plan.not_selected) != expected_rejected_order:
        raise FamiliarityPredictionBindingError("retrieval plan rejected order is non-canonical")

    actual_plan_sha = plan.sha256()
    if actual_plan_sha != expected_plan_sha256:
        raise FamiliarityPredictionBindingError("retrieval plan digest mismatch")
    return tuple(plan.selected)


@dataclass(frozen=True, slots=True)
class FamiliarityPredictionSignal:
    schema: str
    prediction_id: str
    generation: int
    status: str
    residual_sha256: str | None
    observation_id: str | None
    observation_fingerprint_sha256: str | None
    prediction_error_bp: int | None
    familiarity_bp: int
    attention_priority_bp: int
    retrieval_need_id: str
    retrieval_need_sha256: str
    retrieval_plan_sha256: str
    retrieval_memory_ids: tuple[str, ...]
    retrieval_result_sha256s: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    classification: str = CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, init=False)
class FamiliarityPredictionBinding:
    schema: str
    prediction_id: str
    generation: int
    retrieval_need_id: str
    expected_retrieval_need_sha256: str
    expected_retrieval_plan_sha256: str
    expected_residual_sha256: str | None
    evidence_refs: tuple[str, ...]

    def __init__(
        self,
        *,
        schema: str,
        prediction_id: str,
        generation: int,
        retrieval_need_id: str,
        expected_retrieval_need_sha256: str,
        expected_retrieval_plan_sha256: str,
        expected_residual_sha256: str | None,
        evidence_refs: Iterable[str],
    ) -> None:
        if schema != BINDING_SCHEMA:
            raise FamiliarityPredictionBindingError("binding schema mismatch")
        prediction_id = _identifier("prediction_id", prediction_id)
        generation = _generation(generation)
        retrieval_need_id = _identifier("retrieval_need_id", retrieval_need_id)
        expected_retrieval_need_sha256 = _sha256(
            "expected_retrieval_need_sha256", expected_retrieval_need_sha256
        )
        expected_retrieval_plan_sha256 = _sha256(
            "expected_retrieval_plan_sha256", expected_retrieval_plan_sha256
        )
        if expected_residual_sha256 is not None:
            expected_residual_sha256 = _sha256(
                "expected_residual_sha256", expected_residual_sha256
            )
        refs = _refs("binding evidence_ref", evidence_refs)

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "prediction_id", prediction_id)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(self, "retrieval_need_id", retrieval_need_id)
        object.__setattr__(self, "expected_retrieval_need_sha256", expected_retrieval_need_sha256)
        object.__setattr__(self, "expected_retrieval_plan_sha256", expected_retrieval_plan_sha256)
        object.__setattr__(self, "expected_residual_sha256", expected_residual_sha256)
        object.__setattr__(self, "evidence_refs", refs)

    @classmethod
    def create(
        cls,
        *,
        prediction_id: str,
        generation: int,
        retrieval_need: RetrievalNeed,
        retrieval_plan: RetrievalPlan,
        expected_residual_sha256: str | None,
        evidence_refs: Iterable[str],
    ) -> "FamiliarityPredictionBinding":
        if not isinstance(retrieval_need, RetrievalNeed):
            raise FamiliarityPredictionBindingError("retrieval_need must be RetrievalNeed")
        if not isinstance(retrieval_plan, RetrievalPlan):
            raise FamiliarityPredictionBindingError("retrieval_plan must be RetrievalPlan")
        # Creation itself captures an exact identity fence; evaluate() revalidates all structure.
        return cls(
            schema=BINDING_SCHEMA,
            prediction_id=prediction_id,
            generation=generation,
            retrieval_need_id=retrieval_need.need_id,
            expected_retrieval_need_sha256=retrieval_need.sha256(),
            expected_retrieval_plan_sha256=retrieval_plan.sha256(),
            expected_residual_sha256=expected_residual_sha256,
            evidence_refs=evidence_refs,
        )

    def evaluate(
        self,
        *,
        residual: PredictionResidual | None,
        retrieval_need: RetrievalNeed,
        retrieval_plan: RetrievalPlan,
    ) -> FamiliarityPredictionSignal:
        selected_results = _validate_retrieval_provenance(
            need=retrieval_need,
            plan=retrieval_plan,
            expected_need_id=self.retrieval_need_id,
            expected_need_sha256=self.expected_retrieval_need_sha256,
            expected_plan_sha256=self.expected_retrieval_plan_sha256,
        )

        result_rows = sorted(
            (
                result.memory_id,
                result.weighted_score_bp,
                _digest(result.as_dict()),
            )
            for result in selected_results
        )
        familiarity_bp = max((row[1] for row in result_rows), default=0)

        if residual is None:
            if self.expected_residual_sha256 is not None:
                raise FamiliarityPredictionBindingError(
                    "expected residual digest was supplied but residual is unavailable"
                )
            status = STATUS_UNKNOWN
            residual_sha256 = None
            observation_id = None
            observation_fingerprint_sha256 = None
            prediction_error_bp = None
            attention_priority_bp = familiarity_bp
        else:
            if not isinstance(residual, PredictionResidual):
                raise FamiliarityPredictionBindingError(
                    "residual must be PredictionResidual or None"
                )
            if residual.prediction_id != self.prediction_id:
                raise FamiliarityPredictionBindingError("prediction_id mismatch")
            if residual.generation != self.generation:
                raise FamiliarityPredictionBindingError("prediction generation mismatch")
            residual_sha256 = residual.sha256()
            if self.expected_residual_sha256 is None:
                raise FamiliarityPredictionBindingError(
                    "present residual requires expected_residual_sha256 fence"
                )
            if residual_sha256 != self.expected_residual_sha256:
                raise FamiliarityPredictionBindingError("residual digest mismatch")
            _identifier("observation_id", residual.observation_id)
            _sha256(
                "observation_fingerprint_sha256",
                residual.observation_fingerprint_sha256,
            )
            prediction_error_bp = _residual_error_bp(residual)
            status = STATUS_MATCH if residual.exact_match else STATUS_MISMATCH
            attention_priority_bp = max(familiarity_bp, prediction_error_bp)
            observation_id = residual.observation_id
            observation_fingerprint_sha256 = residual.observation_fingerprint_sha256

        return FamiliarityPredictionSignal(
            schema=SIGNAL_SCHEMA,
            prediction_id=self.prediction_id,
            generation=self.generation,
            status=status,
            residual_sha256=residual_sha256,
            observation_id=observation_id,
            observation_fingerprint_sha256=observation_fingerprint_sha256,
            prediction_error_bp=prediction_error_bp,
            familiarity_bp=familiarity_bp,
            attention_priority_bp=attention_priority_bp,
            retrieval_need_id=retrieval_need.need_id,
            retrieval_need_sha256=retrieval_need.sha256(),
            retrieval_plan_sha256=retrieval_plan.sha256(),
            retrieval_memory_ids=tuple(row[0] for row in result_rows),
            retrieval_result_sha256s=tuple(row[2] for row in result_rows),
            evidence_refs=self.evidence_refs,
        )


__all__ = [
    "BINDING_SCHEMA",
    "SIGNAL_SCHEMA",
    "STATUS_MATCH",
    "STATUS_MISMATCH",
    "STATUS_UNKNOWN",
    "CLASSIFICATION",
    "FamiliarityPredictionBinding",
    "FamiliarityPredictionBindingError",
    "FamiliarityPredictionSignal",
]
