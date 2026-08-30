"""WP803 candidate successor: probabilistic confidence sidecar.

This module does not replace the accepted hard CORRECT/INCORRECT/ABSTAIN evaluator.
It binds a pre-evaluation probability-of-correctness statement to the exact public
PredictionCandidate and computes evaluator-side Decimal Brier/log-loss/reliability
evidence after the existing hard evaluation has closed.

Two independent evaluator identities are retained before the world step:
- the accepted generation-2 BenchmarkRunAdmission digest; and
- the exact PredictionConfidence digest emitted for that PredictionCandidate.

The integrated path verifies both before delegating to the accepted admitted hard
evaluator. Probability/confidence/reliability remain candidate measurements only: no
world truth, runtime, GRID/GWT/J-Space, effect, completion, training or whole-system
credit is minted here.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass
from decimal import Decimal, localcontext
import hashlib
import json
import re
from typing import Iterable, Any

from .cognitive_microworld import (
    EpisodeState,
    EvaluatorStep,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
)
from .cognitive_world_model_prediction_benchmark import (
    ABSTAINED,
    CORRECT,
    INCORRECT,
    PredictionCandidate,
    PredictionEvaluation,
)
from .cognitive_world_model_run_admission import (
    BenchmarkRunAdmission,
    evaluate_admitted_next_observation_prediction,
)

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
        _sha("prediction_sha256", self.prediction_sha256)
        if type(self.benchmark_generation) is not int or self.benchmark_generation < 0:
            raise ProbabilisticScoringError("benchmark_generation must be a non-negative integer")

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
        for name, value in (
            ("prediction_sha256", self.prediction_sha256),
            ("confidence_sha256", self.confidence_sha256),
            ("hard_evaluation_sha256", self.hard_evaluation_sha256),
            ("run_admission_sha256", self.run_admission_sha256),
        ):
            _sha(name, value)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _assert_preoutcome_binding(
    confidence: PredictionConfidence,
    prediction: PredictionCandidate,
    run_admission: BenchmarkRunAdmission,
    *,
    expected_run_admission_sha256: str,
    expected_confidence_sha256: str,
) -> tuple[str, str]:
    """Fail closed on candidate/admission/confidence drift before outcome revelation."""
    if type(confidence) is not PredictionConfidence:
        raise ProbabilisticScoringError("confidence must be exact concrete PredictionConfidence")
    if type(prediction) is not PredictionCandidate:
        raise ProbabilisticScoringError("prediction must be exact concrete PredictionCandidate")
    if type(run_admission) is not BenchmarkRunAdmission:
        raise ProbabilisticScoringError("run_admission must be exact concrete BenchmarkRunAdmission")

    expected_admission = _sha("expected_run_admission_sha256", expected_run_admission_sha256)
    if run_admission.sha256() != expected_admission:
        raise ProbabilisticScoringError("run admission digest does not match predeclared expected digest")
    expected_confidence = _sha("expected_confidence_sha256", expected_confidence_sha256)
    if confidence.sha256() != expected_confidence:
        raise ProbabilisticScoringError("confidence digest does not match pre-outcome expected digest")

    if (
        confidence.prediction_id != prediction.prediction_id
        or confidence.prediction_sha256 != prediction.sha256()
        or confidence.benchmark_run_id != prediction.benchmark_run_id
        or confidence.benchmark_generation != prediction.benchmark_generation
    ):
        raise ProbabilisticScoringError("confidence/prediction provenance mismatch")
    if (
        run_admission.run_id != prediction.benchmark_run_id
        or run_admission.benchmark_generation != prediction.benchmark_generation
        or run_admission.system_under_test_ref != prediction.policy_id
    ):
        raise ProbabilisticScoringError("prediction/run-admission provenance mismatch")
    return expected_admission, expected_confidence


def evaluate_prediction_confidence(
    confidence: PredictionConfidence,
    hard_evaluation: PredictionEvaluation,
    *,
    prediction: PredictionCandidate,
    run_admission: BenchmarkRunAdmission,
    expected_run_admission_sha256: str,
    expected_confidence_sha256: str,
) -> ProbabilisticPredictionEvaluation:
    """Score a retained pre-outcome confidence against an admitted hard evaluation.

    For causal evaluation in one call, prefer
    ``evaluate_admitted_prediction_confidence`` below; this post-step function remains
    useful for replaying a transcript only when both retained expected digests are
    supplied independently of the observed outcome.
    """
    expected_admission, expected_confidence = _assert_preoutcome_binding(
        confidence,
        prediction,
        run_admission,
        expected_run_admission_sha256=expected_run_admission_sha256,
        expected_confidence_sha256=expected_confidence_sha256,
    )
    if type(hard_evaluation) is not PredictionEvaluation:
        raise ProbabilisticScoringError("hard_evaluation must be exact concrete PredictionEvaluation")
    if (
        prediction.prediction_id != hard_evaluation.prediction_id
        or prediction.sha256() != hard_evaluation.prediction_sha256
        or prediction.benchmark_run_id != hard_evaluation.benchmark_run_id
        or prediction.benchmark_generation != hard_evaluation.benchmark_generation
    ):
        raise ProbabilisticScoringError("prediction/hard-evaluation provenance mismatch")
    if run_admission.run_descriptor_sha256 != hard_evaluation.run_descriptor_sha256:
        raise ProbabilisticScoringError("hard-evaluation/run-descriptor admission mismatch")
    if (
        run_admission.fixture_id != hard_evaluation.fixture_id
        or run_admission.fixture_generation != hard_evaluation.fixture_generation
        or run_admission.fixture_sha256 != hard_evaluation.fixture_sha256
    ):
        raise ProbabilisticScoringError("hard-evaluation/fixture admission mismatch")

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
        expected_confidence,
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


def evaluate_admitted_prediction_confidence(
    fixture: MicroWorldFixture,
    *,
    state: EpisodeState,
    action_id: str,
    prediction: PredictionCandidate,
    confidence: PredictionConfidence,
    run_descriptor: RunDescriptor,
    run_admission: BenchmarkRunAdmission,
    expected_run_admission_sha256: str,
    expected_confidence_sha256: str,
) -> tuple[
    EpisodeState,
    ObservationView,
    EvaluatorStep,
    PredictionEvaluation,
    ProbabilisticPredictionEvaluation,
]:
    """Pin both candidate-side identities before reusing the accepted G2 hard path."""
    _assert_preoutcome_binding(
        confidence,
        prediction,
        run_admission,
        expected_run_admission_sha256=expected_run_admission_sha256,
        expected_confidence_sha256=expected_confidence_sha256,
    )
    next_state, next_observation, evaluator_step, hard_evaluation = (
        evaluate_admitted_next_observation_prediction(
            fixture,
            state=state,
            action_id=action_id,
            prediction=prediction,
            run_descriptor=run_descriptor,
            run_admission=run_admission,
            expected_run_admission_sha256=expected_run_admission_sha256,
        )
    )
    probabilistic = evaluate_prediction_confidence(
        confidence,
        hard_evaluation,
        prediction=prediction,
        run_admission=run_admission,
        expected_run_admission_sha256=expected_run_admission_sha256,
        expected_confidence_sha256=expected_confidence_sha256,
    )
    return next_state, next_observation, evaluator_step, hard_evaluation, probabilistic


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
