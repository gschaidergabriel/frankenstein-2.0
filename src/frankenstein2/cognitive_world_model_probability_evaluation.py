"""Candidate probabilistic evaluator layer for F2-WP-803.

This module is deliberately parallel to the accepted generation-2 hard
CORRECT/INCORRECT/ABSTAIN evaluator. It does not modify that ABI and it does not
turn probability, confidence, Brier score or log loss into world truth, effect
authority, completion authority, runtime credit or whole-system acceptance.

A public policy may attach a bounded probability-of-correctness claim to an exact
non-abstaining ``PredictionCandidate``. The outer evaluator/run harness must retain
both the already-predeclared ``BenchmarkRunAdmission`` digest and the exact probability
claim digest before revealing the next observation. The integrated evaluator verifies
both identities before the accepted generation-2 hard evaluator advances the world.

Classification: CANDIDATE_FALSIFIER / successor-scope input only. Merge/adoption
requires an explicit successor workpackage claim/reconciliation; this file itself does
not grant mutation authority.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass
import hashlib
import json
import math
import re
from typing import Any

from .cognitive_microworld import (
    EpisodeState,
    EvaluatorStep,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
)
from .cognitive_world_model_prediction_benchmark import (
    ABSTAIN,
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

PROBABILITY_CLAIM_SCHEMA = "FRANKENSTEIN2_WORLD_MODEL_PROBABILITY_CORRECT_CLAIM/v1"
PROBABILITY_EVALUATION_SCHEMA = "FRANKENSTEIN2_WORLD_MODEL_PROBABILITY_EVALUATION/v1"
PUBLIC_PROBABILITY_CLASSIFICATION = "PUBLIC_PREDICTION_DERIVED_PROBABILITY_CANDIDATE_NO_WORLD_AUTHORITY"
EVALUATOR_PROBABILITY_CLASSIFICATION = "EVALUATOR_ONLY_PROPER_SCORE_MEASUREMENT_NOT_WORLD_TRUTH"
PROBABILITY_DENOMINATOR = 1_000_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_GENERATION = 1_000_000
_EVALUATION_ORIGIN = object()


class WorldModelProbabilityEvaluationError(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise WorldModelProbabilityEvaluationError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise WorldModelProbabilityEvaluationError(f"{name} is outside the identifier domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise WorldModelProbabilityEvaluationError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_GENERATION:
        raise WorldModelProbabilityEvaluationError(f"{name} must be a bounded non-negative integer")
    return value


def _probability_ppm(value: Any) -> int:
    # Keep log loss finite and fail closed instead of clipping asserted certainty.
    if type(value) is not int or not 1 <= value < PROBABILITY_DENOMINATOR:
        raise WorldModelProbabilityEvaluationError("probability_correct_ppm must be an integer in [1, 999999]")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ProbabilityCorrectClaim:
    """Public, untrusted probability that one exact prediction will be correct."""

    schema: str
    probability_claim_id: str
    prediction_id: str
    prediction_sha256: str
    benchmark_run_id: str
    benchmark_generation: int
    policy_id: str
    policy_generation: int
    probability_correct_ppm: int
    classification: str = PUBLIC_PROBABILITY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != PROBABILITY_CLAIM_SCHEMA or self.classification != PUBLIC_PROBABILITY_CLASSIFICATION:
            raise WorldModelProbabilityEvaluationError("probability claim schema/classification mismatch")
        for name, value in (
            ("probability_claim_id", self.probability_claim_id),
            ("prediction_id", self.prediction_id),
            ("benchmark_run_id", self.benchmark_run_id),
            ("policy_id", self.policy_id),
        ):
            _id(name, value)
        _sha("prediction_sha256", self.prediction_sha256)
        _generation("benchmark_generation", self.benchmark_generation)
        _generation("policy_generation", self.policy_generation)
        _probability_ppm(self.probability_correct_ppm)

    @classmethod
    def for_prediction(
        cls,
        prediction: PredictionCandidate,
        *,
        probability_claim_id: str,
        probability_correct_ppm: int,
    ) -> "ProbabilityCorrectClaim":
        if type(prediction) is not PredictionCandidate:
            raise WorldModelProbabilityEvaluationError("prediction must be exact concrete PredictionCandidate")
        if prediction.prediction_kind == ABSTAIN:
            raise WorldModelProbabilityEvaluationError("ABSTAIN has no probability-of-correctness score")
        return cls(
            PROBABILITY_CLAIM_SCHEMA,
            probability_claim_id,
            prediction.prediction_id,
            prediction.sha256(),
            prediction.benchmark_run_id,
            prediction.benchmark_generation,
            prediction.policy_id,
            prediction.policy_generation,
            _probability_ppm(probability_correct_ppm),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ProbabilityScoreEvaluation:
    """Evaluator-only proper score for one admitted pre-outcome probability claim."""

    schema: str
    probability_claim_id: str
    probability_claim_sha256: str
    prediction_id: str
    prediction_sha256: str
    hard_evaluation_sha256: str
    run_admission_sha256: str
    benchmark_run_id: str
    benchmark_generation: int
    hard_outcome: str
    target_correct: int
    probability_correct_ppm: int
    brier_score: float
    log_loss: float
    classification: str = EVALUATOR_PROBABILITY_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != PROBABILITY_EVALUATION_SCHEMA or self.classification != EVALUATOR_PROBABILITY_CLASSIFICATION:
            raise WorldModelProbabilityEvaluationError("probability evaluation schema/classification mismatch")
        for name, value in (
            ("probability_claim_id", self.probability_claim_id),
            ("prediction_id", self.prediction_id),
            ("benchmark_run_id", self.benchmark_run_id),
        ):
            _id(name, value)
        for name, value in (
            ("probability_claim_sha256", self.probability_claim_sha256),
            ("prediction_sha256", self.prediction_sha256),
            ("hard_evaluation_sha256", self.hard_evaluation_sha256),
            ("run_admission_sha256", self.run_admission_sha256),
        ):
            _sha(name, value)
        _generation("benchmark_generation", self.benchmark_generation)
        if self.hard_outcome not in (CORRECT, INCORRECT):
            raise WorldModelProbabilityEvaluationError("probability score requires CORRECT or INCORRECT hard outcome")
        if type(self.target_correct) is not int or self.target_correct not in (0, 1):
            raise WorldModelProbabilityEvaluationError("target_correct must be exact integer 0 or 1")
        expected_target = 1 if self.hard_outcome == CORRECT else 0
        if self.target_correct != expected_target:
            raise WorldModelProbabilityEvaluationError("target_correct/hard_outcome mismatch")
        _probability_ppm(self.probability_correct_ppm)
        if type(self.brier_score) is not float or not math.isfinite(self.brier_score) or not 0.0 <= self.brier_score <= 1.0:
            raise WorldModelProbabilityEvaluationError("brier_score is outside finite [0,1]")
        if type(self.log_loss) is not float or not math.isfinite(self.log_loss) or self.log_loss < 0.0:
            raise WorldModelProbabilityEvaluationError("log_loss must be finite and non-negative")
        if _origin is not _EVALUATION_ORIGIN:
            raise WorldModelProbabilityEvaluationError("ProbabilityScoreEvaluation must be created by evaluator API")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def proper_binary_scores(probability_correct_ppm: int, target_correct: int) -> tuple[float, float]:
    """Return Brier score and log loss for a binary probability.

    This helper is evaluator math only. It does not establish that the probability was
    causally available before the outcome; provenance is enforced by the bound evaluator
    functions below.
    """
    ppm = _probability_ppm(probability_correct_ppm)
    if type(target_correct) is not int or target_correct not in (0, 1):
        raise WorldModelProbabilityEvaluationError("target_correct must be exact integer 0 or 1")
    p = ppm / PROBABILITY_DENOMINATOR
    brier = (p - target_correct) ** 2
    likelihood = p if target_correct == 1 else 1.0 - p
    return float(brier), float(-math.log(likelihood))


def _assert_preoutcome_binding(
    claim: ProbabilityCorrectClaim,
    prediction: PredictionCandidate,
    run_admission: BenchmarkRunAdmission,
    expected_run_admission_sha256: str,
    expected_probability_claim_sha256: str,
) -> tuple[str, str]:
    """Verify all candidate-side identities before the world outcome is revealed."""
    if type(claim) is not ProbabilityCorrectClaim:
        raise WorldModelProbabilityEvaluationError("claim must be exact concrete ProbabilityCorrectClaim")
    if type(prediction) is not PredictionCandidate:
        raise WorldModelProbabilityEvaluationError("prediction must be exact concrete PredictionCandidate")
    if type(run_admission) is not BenchmarkRunAdmission:
        raise WorldModelProbabilityEvaluationError("run_admission must be exact concrete BenchmarkRunAdmission")

    expected_admission = _sha("expected_run_admission_sha256", expected_run_admission_sha256)
    if run_admission.sha256() != expected_admission:
        raise WorldModelProbabilityEvaluationError("run admission digest does not match predeclared expected digest")
    expected_claim = _sha("expected_probability_claim_sha256", expected_probability_claim_sha256)
    if claim.sha256() != expected_claim:
        raise WorldModelProbabilityEvaluationError("probability claim digest does not match pre-outcome expected digest")
    if prediction.prediction_kind == ABSTAIN:
        raise WorldModelProbabilityEvaluationError("ABSTAIN is not admitted to probability scoring")

    claim_prediction = (
        claim.prediction_id,
        claim.prediction_sha256,
        claim.benchmark_run_id,
        claim.benchmark_generation,
        claim.policy_id,
        claim.policy_generation,
    )
    actual_prediction = (
        prediction.prediction_id,
        prediction.sha256(),
        prediction.benchmark_run_id,
        prediction.benchmark_generation,
        prediction.policy_id,
        prediction.policy_generation,
    )
    if claim_prediction != actual_prediction:
        raise WorldModelProbabilityEvaluationError("probability claim/prediction provenance mismatch")

    if (
        run_admission.run_id != prediction.benchmark_run_id
        or run_admission.benchmark_generation != prediction.benchmark_generation
        or run_admission.system_under_test_ref != prediction.policy_id
    ):
        raise WorldModelProbabilityEvaluationError("prediction/run admission provenance mismatch")
    return expected_admission, expected_claim


def _assert_cross_binding(
    claim: ProbabilityCorrectClaim,
    prediction: PredictionCandidate,
    hard_evaluation: PredictionEvaluation,
    run_admission: BenchmarkRunAdmission,
    expected_run_admission_sha256: str,
    expected_probability_claim_sha256: str,
) -> tuple[str, str]:
    if type(hard_evaluation) is not PredictionEvaluation:
        raise WorldModelProbabilityEvaluationError("hard_evaluation must be exact concrete PredictionEvaluation")
    expected_admission, expected_claim = _assert_preoutcome_binding(
        claim,
        prediction,
        run_admission,
        expected_run_admission_sha256,
        expected_probability_claim_sha256,
    )
    if hard_evaluation.outcome == ABSTAINED:
        raise WorldModelProbabilityEvaluationError("ABSTAIN is not admitted to probability scoring")

    hard_prediction = (
        hard_evaluation.prediction_id,
        hard_evaluation.prediction_sha256,
        hard_evaluation.benchmark_run_id,
        hard_evaluation.benchmark_generation,
    )
    expected_hard_prediction = (
        prediction.prediction_id,
        prediction.sha256(),
        prediction.benchmark_run_id,
        prediction.benchmark_generation,
    )
    if hard_prediction != expected_hard_prediction:
        raise WorldModelProbabilityEvaluationError("hard evaluation/prediction provenance mismatch")

    if run_admission.run_descriptor_sha256 != hard_evaluation.run_descriptor_sha256:
        raise WorldModelProbabilityEvaluationError("hard evaluation/run descriptor admission mismatch")
    expected_fixture = (
        run_admission.fixture_id,
        run_admission.fixture_generation,
        run_admission.fixture_sha256,
    )
    actual_fixture = (
        hard_evaluation.fixture_id,
        hard_evaluation.fixture_generation,
        hard_evaluation.fixture_sha256,
    )
    if actual_fixture != expected_fixture:
        raise WorldModelProbabilityEvaluationError("hard evaluation/fixture admission mismatch")
    return expected_admission, expected_claim


def evaluate_probability_quality(
    claim: ProbabilityCorrectClaim,
    *,
    prediction: PredictionCandidate,
    hard_evaluation: PredictionEvaluation,
    run_admission: BenchmarkRunAdmission,
    expected_run_admission_sha256: str,
    expected_probability_claim_sha256: str,
) -> ProbabilityScoreEvaluation:
    """Proper-score one probability against one admitted hard evaluation.

    This post-step helper requires both externally retained expected digests. It can
    validate a stored evaluation transcript, but the integrated evaluator below is the
    stronger causal path because it checks the probability-claim digest before the world
    step that reveals the outcome.
    """
    expected_admission, expected_claim = _assert_cross_binding(
        claim,
        prediction,
        hard_evaluation,
        run_admission,
        expected_run_admission_sha256,
        expected_probability_claim_sha256,
    )
    target = 1 if hard_evaluation.outcome == CORRECT else 0
    brier, log_loss = proper_binary_scores(claim.probability_correct_ppm, target)
    return ProbabilityScoreEvaluation(
        PROBABILITY_EVALUATION_SCHEMA,
        claim.probability_claim_id,
        expected_claim,
        prediction.prediction_id,
        prediction.sha256(),
        hard_evaluation.sha256(),
        expected_admission,
        prediction.benchmark_run_id,
        prediction.benchmark_generation,
        hard_evaluation.outcome,
        target,
        claim.probability_correct_ppm,
        brier,
        log_loss,
        _origin=_EVALUATION_ORIGIN,
    )


def evaluate_admitted_probabilistic_next_observation_prediction(
    fixture: MicroWorldFixture,
    *,
    state: EpisodeState,
    action_id: str,
    prediction: PredictionCandidate,
    probability_claim: ProbabilityCorrectClaim,
    run_descriptor: RunDescriptor,
    run_admission: BenchmarkRunAdmission,
    expected_run_admission_sha256: str,
    expected_probability_claim_sha256: str,
) -> tuple[
    EpisodeState,
    ObservationView,
    EvaluatorStep,
    PredictionEvaluation,
    ProbabilityScoreEvaluation,
]:
    """Verify probability provenance before stepping, then reuse the accepted G2 path.

    The two ``expected_*`` digests are deliberately supplied independently of the
    candidate objects. A run harness can persist/pin the run admission before candidate
    emission and the probability claim after candidate emission but before the world
    step. Both are verified before ``evaluate_admitted_next_observation_prediction`` can
    reveal the next observation. A post-outcome replacement claim therefore cannot pass
    against the retained pre-outcome claim digest.
    """
    _assert_preoutcome_binding(
        probability_claim,
        prediction,
        run_admission,
        expected_run_admission_sha256,
        expected_probability_claim_sha256,
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
    probability_evaluation = evaluate_probability_quality(
        probability_claim,
        prediction=prediction,
        hard_evaluation=hard_evaluation,
        run_admission=run_admission,
        expected_run_admission_sha256=expected_run_admission_sha256,
        expected_probability_claim_sha256=expected_probability_claim_sha256,
    )
    return next_state, next_observation, evaluator_step, hard_evaluation, probability_evaluation
