"""WP803 candidate successor: probabilistic confidence sidecar.

This module does not replace the accepted hard CORRECT/INCORRECT/ABSTAIN evaluator.
It binds a pre-evaluation probability-of-correctness statement to the exact public
PredictionCandidate and computes evaluator-side Brier/log-loss/reliability evidence
after the existing hard evaluation has closed.

The probabilistic evaluator additionally requires the exact externally pinned
``BenchmarkRunAdmission`` digest retained by the accepted generation-2 provenance path.
Probability quality therefore remains a parallel evaluator measurement and cannot loosen
run/fixture/policy/generation provenance merely because the hard outcome is available.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass
from decimal import Decimal, localcontext
import hashlib
import json
import re
from typing import Iterable, Any

from .cognitive_world_model_prediction_benchmark import (
    ABSTAINED,
    CORRECT,
    INCORRECT,
    PredictionCandidate,
    PredictionEvaluation,
)
from .cognitive_world_model_run_admission import BenchmarkRunAdmission

CONFIDENCE_SCHEMA = "FRANKENSTEIN2_WORLD_MODEL_PREDICTION_CONFIDENCE/v1"
PROB_EVALUATION_SCHEMA = "FRANKENSTEIN2_WORLD_MODEL_PROBABILISTIC_EVALUATION/v1"
PUBLIC_CONFIDENCE_CLASSIFICATION = "PUBLIC_PREDICTION_BOUND_CONFIDENCE_NO_WORLD_AUTHORITY"
EVALUATOR_PROB_CLASSIFICATION = "EVALUATOR_ONLY_PROBABILISTIC_MEASUREMENT_NOT_WORLD_TRUTH"
SCORED = "SCORED"
ABSTAIN_NOT_SCORED = "ABSTAIN_NOT_PROBABILISTICALLY_SCORED"
_ORIGIN = object()
_PPM = 1_000_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProbabilisticScoringError(ValueError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ProbabilisticScoringError(f"{name} must be lowercase 64-hex SHA-256")
    return value


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
    run_admission_sha256: str
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
        _sha("prediction_sha256", self.prediction_sha256)
        _sha("confidence_sha256", self.confidence_sha256)
        _sha("hard_evaluation_sha256", self.hard_evaluation_sha256)
        _sha("run_admission_sha256", self.run_admission_sha256)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _assert_admitted_provenance(
    confidence: PredictionConfidence,
    prediction: PredictionCandidate,
    hard_evaluation: PredictionEvaluation,
    run_admission: BenchmarkRunAdmission,
    expected_run_admission_sha256: str,
) -> str:
    if type(confidence) is not PredictionConfidence:
        raise ProbabilisticScoringError("confidence must be exact concrete PredictionConfidence")
    if type(prediction) is not PredictionCandidate:
        raise ProbabilisticScoringError("prediction must be exact concrete PredictionCandidate")
    if type(hard_evaluation) is not PredictionEvaluation:
        raise ProbabilisticScoringError("hard_evaluation must be exact concrete PredictionEvaluation")
    if type(run_admission) is not BenchmarkRunAdmission:
        raise ProbabilisticScoringError("run_admission must be exact concrete BenchmarkRunAdmission")

    expected_admission = _sha("expected_run_admission_sha256", expected_run_admission_sha256)
    if run_admission.sha256() != expected_admission:
        raise ProbabilisticScoringError("run admission digest does not match predeclared expected digest")

    if (
        confidence.prediction_id != prediction.prediction_id
        or confidence.prediction_sha256 != prediction.sha256()
        or confidence.benchmark_run_id != prediction.benchmark_run_id
        or confidence.benchmark_generation != prediction.benchmark_generation
    ):
        raise ProbabilisticScoringError("confidence/prediction provenance mismatch")

    if (
        hard_evaluation.prediction_id != prediction.prediction_id
        or hard_evaluation.prediction_sha256 != prediction.sha256()
        or hard_evaluation.benchmark_run_id != prediction.benchmark_run_id
        or hard_evaluation.benchmark_generation != prediction.benchmark_generation
    ):
        raise ProbabilisticScoringError("hard-evaluation/prediction provenance mismatch")

    if (
        run_admission.run_id != prediction.benchmark_run_id
        or run_admission.benchmark_generation != prediction.benchmark_generation
        or run_admission.system_under_test_ref != prediction.policy_id
    ):
        raise ProbabilisticScoringError("prediction/run-admission provenance mismatch")
    if run_admission.run_descriptor_sha256 != hard_evaluation.run_descriptor_sha256:
        raise ProbabilisticScoringError("hard-evaluation/run-descriptor admission mismatch")
    if (
        run_admission.fixture_id,
        run_admission.fixture_generation,
        run_admission.fixture_sha256,
    ) != (
        hard_evaluation.fixture_id,
        hard_evaluation.fixture_generation,
        hard_evaluation.fixture_sha256,
    ):
        raise ProbabilisticScoringError("hard-evaluation/fixture admission mismatch")

    return expected_admission


def evaluate_prediction_confidence(
    confidence: PredictionConfidence,
    prediction: PredictionCandidate,
    hard_evaluation: PredictionEvaluation,
    *,
    run_admission: BenchmarkRunAdmission,
    expected_run_admission_sha256: str,
) -> ProbabilisticPredictionEvaluation:
    """Score confidence only inside the retained predeclared run-admission boundary."""
    expected_admission = _assert_admitted_provenance(
        confidence,
        prediction,
        hard_evaluation,
        run_admission,
        expected_run_admission_sha256,
    )

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
        expected_admission,
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
