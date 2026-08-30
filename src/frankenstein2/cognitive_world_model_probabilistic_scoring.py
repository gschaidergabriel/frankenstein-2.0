"""WP803 candidate successor: probabilistic confidence sidecar.

This module does not replace the accepted hard CORRECT/INCORRECT/ABSTAIN evaluator.
It binds a pre-evaluation probability-of-correctness statement to the exact public
PredictionCandidate and computes evaluator-side Brier/log-loss/reliability evidence
after the existing hard evaluation has closed.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass
from decimal import Decimal, localcontext
import hashlib
import json
from typing import Iterable, Any

from .cognitive_world_model_prediction_benchmark import (
    ABSTAINED,
    CORRECT,
    INCORRECT,
    PredictionCandidate,
    PredictionEvaluation,
)

CONFIDENCE_SCHEMA = "FRANKENSTEIN2_WORLD_MODEL_PREDICTION_CONFIDENCE/v1"
PROB_EVALUATION_SCHEMA = "FRANKENSTEIN2_WORLD_MODEL_PROBABILISTIC_EVALUATION/v1"
PUBLIC_CONFIDENCE_CLASSIFICATION = "PUBLIC_PREDICTION_BOUND_CONFIDENCE_NO_WORLD_AUTHORITY"
EVALUATOR_PROB_CLASSIFICATION = "EVALUATOR_ONLY_PROBABILISTIC_MEASUREMENT_NOT_WORLD_TRUTH"
SCORED = "SCORED"
ABSTAIN_NOT_SCORED = "ABSTAIN_NOT_PROBABILISTICALLY_SCORED"
_ORIGIN = object()
_PPM = 1_000_000


class ProbabilisticScoringError(ValueError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000000001")), "f")


@dataclass(frozen=True, slots=True)
class PredictionConfidence:
    schema: str
    prediction_id: str
    prediction_sha256: str
    benchmark_run_id: str
    benchmark_generation: int
    probability_correct_ppm: int
    classification: str = PUBLIC_CONFIDENCE_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != CONFIDENCE_SCHEMA or self.classification != PUBLIC_CONFIDENCE_CLASSIFICATION:
            raise ProbabilisticScoringError("confidence schema/classification mismatch")
        if type(self.probability_correct_ppm) is not int or not 1 <= self.probability_correct_ppm < _PPM:
            raise ProbabilisticScoringError("probability_correct_ppm must be integer in [1, 999999]")

    @classmethod
    def for_prediction(cls, prediction: PredictionCandidate, *, probability_correct_ppm: int) -> "PredictionConfidence":
        if type(prediction) is not PredictionCandidate:
            raise ProbabilisticScoringError("prediction must be exact concrete PredictionCandidate")
        return cls(
            CONFIDENCE_SCHEMA,
            prediction.prediction_id,
            prediction.sha256(),
            prediction.benchmark_run_id,
            prediction.benchmark_generation,
            probability_correct_ppm,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ProbabilisticPredictionEvaluation:
    schema: str
    prediction_id: str
    prediction_sha256: str
    confidence_sha256: str
    hard_evaluation_sha256: str
    benchmark_run_id: str
    benchmark_generation: int
    hard_outcome: str
    hard_score_delta: int
    probability_correct_ppm: int
    target_correct: int | None
    score_status: str
    brier_loss: str | None
    log_loss_nats: str | None
    classification: str = EVALUATOR_PROB_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if _origin is not _ORIGIN:
            raise ProbabilisticScoringError("probabilistic evaluation must be created by evaluator API")
        if self.schema != PROB_EVALUATION_SCHEMA or self.classification != EVALUATOR_PROB_CLASSIFICATION:
            raise ProbabilisticScoringError("probabilistic evaluation schema/classification mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def evaluate_prediction_confidence(
    confidence: PredictionConfidence,
    hard_evaluation: PredictionEvaluation,
) -> ProbabilisticPredictionEvaluation:
    if type(confidence) is not PredictionConfidence:
        raise ProbabilisticScoringError("confidence must be exact concrete PredictionConfidence")
    if type(hard_evaluation) is not PredictionEvaluation:
        raise ProbabilisticScoringError("hard_evaluation must be exact concrete PredictionEvaluation")
    if (
        confidence.prediction_id != hard_evaluation.prediction_id
        or confidence.prediction_sha256 != hard_evaluation.prediction_sha256
        or confidence.benchmark_run_id != hard_evaluation.benchmark_run_id
        or confidence.benchmark_generation != hard_evaluation.benchmark_generation
    ):
        raise ProbabilisticScoringError("confidence/hard-evaluation provenance mismatch")

    target = None
    status = ABSTAIN_NOT_SCORED
    brier = None
    log_loss = None
    if hard_evaluation.outcome in (CORRECT, INCORRECT):
        target = 1 if hard_evaluation.outcome == CORRECT else 0
        status = SCORED
        with localcontext() as ctx:
            ctx.prec = 50
            p = Decimal(confidence.probability_correct_ppm) / Decimal(_PPM)
            y = Decimal(target)
            brier = _decimal_text((p - y) ** 2)
            log_loss = _decimal_text(-(p.ln() if target else (Decimal(1) - p).ln()))
    elif hard_evaluation.outcome != ABSTAINED:
        raise ProbabilisticScoringError("unknown hard evaluation outcome")

    return ProbabilisticPredictionEvaluation(
        PROB_EVALUATION_SCHEMA,
        confidence.prediction_id,
        confidence.prediction_sha256,
        confidence.sha256(),
        hard_evaluation.sha256(),
        confidence.benchmark_run_id,
        confidence.benchmark_generation,
        hard_evaluation.outcome,
        hard_evaluation.benchmark_score_delta,
        confidence.probability_correct_ppm,
        target,
        status,
        brier,
        log_loss,
        _origin=_ORIGIN,
    )


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    lower_ppm: int
    upper_ppm: int
    count: int
    mean_confidence: str
    empirical_accuracy: str
    absolute_calibration_gap: str


def reliability_bins(
    evaluations: Iterable[ProbabilisticPredictionEvaluation],
    *,
    bin_width_ppm: int = 100_000,
) -> tuple[ReliabilityBin, ...]:
    if type(bin_width_ppm) is not int or not 1 <= bin_width_ppm <= _PPM:
        raise ProbabilisticScoringError("bin_width_ppm outside domain")
    buckets: dict[int, list[ProbabilisticPredictionEvaluation]] = {}
    for item in evaluations:
        if type(item) is not ProbabilisticPredictionEvaluation:
            raise ProbabilisticScoringError("reliability input must contain exact probabilistic evaluations")
        if item.score_status != SCORED:
            continue
        lower = ((item.probability_correct_ppm - 1) // bin_width_ppm) * bin_width_ppm
        buckets.setdefault(lower, []).append(item)
    result = []
    with localcontext() as ctx:
        ctx.prec = 50
        for lower in sorted(buckets):
            items = buckets[lower]
            mean_p = sum(Decimal(x.probability_correct_ppm) for x in items) / Decimal(_PPM * len(items))
            acc = sum(Decimal(x.target_correct) for x in items) / Decimal(len(items))
            result.append(ReliabilityBin(
                lower,
                min(_PPM, lower + bin_width_ppm),
                len(items),
                _decimal_text(mean_p),
                _decimal_text(acc),
                _decimal_text(abs(mean_p - acc)),
            ))
    return tuple(result)
