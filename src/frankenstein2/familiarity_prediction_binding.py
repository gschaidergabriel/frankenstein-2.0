"""Deterministic Familiarity / prediction-error binding for Frankenstein 2.0.

F2-WP-302 provenance-repair candidate.

This component binds an optional explicit PredictionResidual to already-ranked Emergent
Retrieval results. It never reads memory payloads, computes semantic familiarity, predicts
missing facts, or turns memory into observation.

Authority invariants:

    FAMILIARITY != OBSERVATION
    RETRIEVAL_SCORE != TRUTH
    PREDICTION_MATCH != COMPLETION
    PREDICTION_MISMATCH != EFFECT_AUTHORITY

A present residual decides MATCH versus MISMATCH mechanically. Familiarity can only
contribute a bounded attention hint and can never suppress a contradictory observation.
When no residual is available the result is UNKNOWN even if retrieved memories are strong.
Positive familiarity from RetrievalResult values is admitted only when the exact canonical
result digests are supplied by the upstream WP-301 boundary and the result structure remains
internally coherent.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from .emergent_retrieval import (
    ALLOWED_AXES,
    CLASSIFICATION_SELECTED,
    RESULT_SCHEMA,
    RetrievalResult,
)
from .memory_lifecycle import STATUS_ACTIVE, STATUS_DEGRADED
from .prediction_contract import PredictionResidual

BINDING_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_PREDICTION_BINDING/v1"
SIGNAL_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_PREDICTION_SIGNAL/v1"

STATUS_MATCH = "MATCH"
STATUS_MISMATCH = "MISMATCH"
STATUS_UNKNOWN = "UNKNOWN"

CLASSIFICATION = "FAMILIARITY_PREDICTION_CANDIDATE_SIGNAL_NOT_WORLD_TRUTH_OR_AUTHORITY"

MAX_BASIS_POINTS = 10_000
_MAX_IDENTIFIER_LENGTH = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_AXIS_SET = frozenset(ALLOWED_AXES)
_ALLOWED_RETRIEVAL_LIFECYCLE = frozenset({STATUS_ACTIVE, STATUS_DEGRADED})


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


def _basis_points(name: str, value: Any) -> int:
    if type(value) is not int or not (0 <= value <= MAX_BASIS_POINTS):
        raise FamiliarityPredictionBindingError(
            f"{name} must be an integer in [0, {MAX_BASIS_POINTS}]"
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


def _digest_refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise FamiliarityPredictionBindingError(f"{name} must be an iterable of digests")
    digests = tuple(_sha256(name, value) for value in values)
    if len(set(digests)) != len(digests):
        raise FamiliarityPredictionBindingError(f"{name} contains duplicate digests")
    return tuple(sorted(digests))


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


def _normalize_axis_scores(
    values: Iterable[tuple[str, int]],
) -> tuple[tuple[str, int], ...]:
    if isinstance(values, (str, bytes)):
        raise FamiliarityPredictionBindingError(
            "retrieval signal_scores_bp must be axis/score pairs"
        )
    rows: list[tuple[str, int]] = []
    seen: set[str] = set()
    for row in values:
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            raise FamiliarityPredictionBindingError(
                "retrieval signal_scores_bp must contain axis/score pairs"
            )
        axis, score = row
        if axis not in _ALLOWED_AXIS_SET:
            raise FamiliarityPredictionBindingError(
                f"retrieval result contains unsupported signal axis: {axis!r}"
            )
        if axis in seen:
            raise FamiliarityPredictionBindingError(
                f"retrieval result contains duplicate signal axis: {axis!r}"
            )
        seen.add(axis)
        rows.append((axis, _basis_points(f"retrieval signal score[{axis}]", score)))
    if not rows:
        raise FamiliarityPredictionBindingError(
            "selected retrieval result must contain signal scores"
        )
    rows.sort(key=lambda item: item[0])
    return tuple(rows)


def _normalize_axis_evidence(
    values: Iterable[tuple[str, Iterable[str]]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if isinstance(values, (str, bytes)):
        raise FamiliarityPredictionBindingError(
            "retrieval signal_evidence_refs must be axis/reference pairs"
        )
    rows: list[tuple[str, tuple[str, ...]]] = []
    seen: set[str] = set()
    for row in values:
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            raise FamiliarityPredictionBindingError(
                "retrieval signal_evidence_refs must contain axis/reference pairs"
            )
        axis, refs = row
        if axis not in _ALLOWED_AXIS_SET:
            raise FamiliarityPredictionBindingError(
                f"retrieval result contains unsupported evidence axis: {axis!r}"
            )
        if axis in seen:
            raise FamiliarityPredictionBindingError(
                f"retrieval result contains duplicate evidence axis: {axis!r}"
            )
        seen.add(axis)
        rows.append((axis, _refs(f"retrieval signal evidence[{axis}]", refs)))
    if not rows:
        raise FamiliarityPredictionBindingError(
            "selected retrieval result must contain signal evidence"
        )
    rows.sort(key=lambda item: item[0])
    return tuple(rows)


def _validate_retrieval_result(result: RetrievalResult) -> str:
    if not isinstance(result, RetrievalResult):
        raise FamiliarityPredictionBindingError(
            "retrieval_results must contain RetrievalResult values"
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
    if result.lifecycle_status not in _ALLOWED_RETRIEVAL_LIFECYCLE:
        raise FamiliarityPredictionBindingError(
            "selected retrieval result must reference ACTIVE or DEGRADED memory"
        )
    if not result.selected:
        raise FamiliarityPredictionBindingError(
            "only selected retrieval results may be used as familiarity evidence"
        )
    if result.classification != CLASSIFICATION_SELECTED:
        raise FamiliarityPredictionBindingError(
            "selected retrieval result classification mismatch"
        )
    _identifier("retrieval payload_ref", result.payload_ref)
    _sha256("retrieval payload_sha256", result.payload_sha256)
    _refs("retrieval provenance_ref", result.provenance_refs)

    if not isinstance(result.overlap_axes, tuple):
        raise FamiliarityPredictionBindingError("retrieval overlap_axes must be a tuple")
    overlap_axes = tuple(result.overlap_axes)
    if not overlap_axes:
        raise FamiliarityPredictionBindingError(
            "selected retrieval result must have positive overlap"
        )
    if tuple(sorted(overlap_axes)) != overlap_axes or len(set(overlap_axes)) != len(overlap_axes):
        raise FamiliarityPredictionBindingError(
            "retrieval overlap_axes must be sorted and unique"
        )
    if any(axis not in _ALLOWED_AXIS_SET for axis in overlap_axes):
        raise FamiliarityPredictionBindingError(
            "retrieval overlap_axes contains unsupported axis"
        )
    if type(result.overlap_count) is not int or result.overlap_count != len(overlap_axes):
        raise FamiliarityPredictionBindingError(
            "retrieval overlap_count does not match overlap_axes"
        )
    # Every WP-301 RetrievalNeed enforces min_overlap_axes >= 2.
    if result.overlap_count < 2:
        raise FamiliarityPredictionBindingError(
            "selected retrieval result cannot have fewer than two overlap axes"
        )

    weighted_score = _basis_points("retrieval weighted_score_bp", result.weighted_score_bp)
    bottleneck_score = _basis_points(
        "retrieval bottleneck_score_bp", result.bottleneck_score_bp
    )
    if type(result.rank_score) is not int or result.rank_score < 0:
        raise FamiliarityPredictionBindingError(
            "retrieval rank_score must be a non-negative integer"
        )
    if result.rank_score != weighted_score * result.overlap_count:
        raise FamiliarityPredictionBindingError(
            "retrieval rank_score is inconsistent with weighted score and overlap count"
        )

    signal_scores = _normalize_axis_scores(result.signal_scores_bp)
    signal_evidence = _normalize_axis_evidence(result.signal_evidence_refs)
    score_axes = tuple(axis for axis, _ in signal_scores)
    evidence_axes = tuple(axis for axis, _ in signal_evidence)
    if score_axes != evidence_axes:
        raise FamiliarityPredictionBindingError(
            "retrieval signal score/evidence axes mismatch"
        )
    positive_axes = tuple(axis for axis, score in signal_scores if score > 0)
    if positive_axes != overlap_axes:
        raise FamiliarityPredictionBindingError(
            "retrieval overlap_axes is inconsistent with positive signal scores"
        )
    if bottleneck_score != min(score for _, score in signal_scores):
        raise FamiliarityPredictionBindingError(
            "retrieval bottleneck_score_bp is inconsistent with signal scores"
        )

    return _digest(result.as_dict())


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
    expected_residual_sha256: str | None
    expected_retrieval_result_sha256s: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __init__(
        self,
        *,
        schema: str,
        prediction_id: str,
        generation: int,
        expected_residual_sha256: str | None,
        expected_retrieval_result_sha256s: Iterable[str] = (),
        evidence_refs: Iterable[str],
    ) -> None:
        if schema != BINDING_SCHEMA:
            raise FamiliarityPredictionBindingError("binding schema mismatch")
        prediction_id = _identifier("prediction_id", prediction_id)
        generation = _generation(generation)
        if expected_residual_sha256 is not None:
            expected_residual_sha256 = _sha256(
                "expected_residual_sha256", expected_residual_sha256
            )
        expected_result_digests = _digest_refs(
            "expected_retrieval_result_sha256", expected_retrieval_result_sha256s
        )
        refs = _refs("binding evidence_ref", evidence_refs)

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "prediction_id", prediction_id)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(self, "expected_residual_sha256", expected_residual_sha256)
        object.__setattr__(
            self,
            "expected_retrieval_result_sha256s",
            expected_result_digests,
        )
        object.__setattr__(self, "evidence_refs", refs)

    @classmethod
    def create(
        cls,
        *,
        prediction_id: str,
        generation: int,
        expected_residual_sha256: str | None,
        expected_retrieval_result_sha256s: Iterable[str] = (),
        evidence_refs: Iterable[str],
    ) -> "FamiliarityPredictionBinding":
        return cls(
            schema=BINDING_SCHEMA,
            prediction_id=prediction_id,
            generation=generation,
            expected_residual_sha256=expected_residual_sha256,
            expected_retrieval_result_sha256s=expected_retrieval_result_sha256s,
            evidence_refs=evidence_refs,
        )

    def evaluate(
        self,
        *,
        residual: PredictionResidual | None,
        retrieval_results: Iterable[RetrievalResult] = (),
    ) -> FamiliarityPredictionSignal:
        raw_results = tuple(retrieval_results)
        seen_memory_ids: set[str] = set()
        result_rows: list[tuple[str, int, str]] = []
        for result in raw_results:
            result_sha256 = _validate_retrieval_result(result)
            if result.memory_id in seen_memory_ids:
                raise FamiliarityPredictionBindingError(
                    f"duplicate retrieval memory_id: {result.memory_id!r}"
                )
            seen_memory_ids.add(result.memory_id)
            result_rows.append(
                (
                    result.memory_id,
                    result.weighted_score_bp,
                    result_sha256,
                )
            )

        actual_result_digests = tuple(sorted(row[2] for row in result_rows))
        if raw_results and not self.expected_retrieval_result_sha256s:
            raise FamiliarityPredictionBindingError(
                "retrieval results require expected_retrieval_result_sha256s fence"
            )
        if self.expected_retrieval_result_sha256s and not raw_results:
            raise FamiliarityPredictionBindingError(
                "expected retrieval result digests were supplied but retrieval results are unavailable"
            )
        if actual_result_digests != self.expected_retrieval_result_sha256s:
            raise FamiliarityPredictionBindingError(
                "retrieval result digest fence mismatch"
            )

        result_rows.sort(key=lambda row: row[0])
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
            # A contradictory current observation is never down-weighted by familiarity.
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
