"""F2-WP-803 held-out next-observation prediction benchmark.

This module is repository evaluation infrastructure only. A prediction candidate is
formed from an exact public ``ObservationView``. Hidden ``MicroWorldFixture`` nodes,
transition rules, evaluator scores, and ground-truth references are used only after the
candidate exists, on the evaluator side, through the canonical F2-WP-800 step boundary.

A benchmark score is a measurement on a synthetic held-out fixture. It is not world
truth, causal credit, cognition superiority, transfer evidence, runtime acceptance,
effect authority, completion authority, or whole-system acceptance.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass
import hashlib
import json
import re
from typing import Any

from .cognitive_microworld import (
    ActionRequest,
    CognitiveMicroWorldError,
    EpisodeState,
    EvaluatorStep,
    MicroWorldFixture,
    ObservationView,
    observation_for_state,
    step_episode,
)

PREDICTION_SCHEMA = "FRANKENSTEIN2_HELDOUT_WORLD_MODEL_PREDICTION/v1"
EVALUATION_SCHEMA = "FRANKENSTEIN2_HELDOUT_WORLD_MODEL_PREDICTION_EVALUATION/v1"
PUBLIC_PREDICTION_CLASSIFICATION = "PUBLIC_OBSERVATION_DERIVED_CANDIDATE_NO_WORLD_AUTHORITY"
EVALUATOR_CLASSIFICATION = "EVALUATOR_ONLY_BENCHMARK_MEASUREMENT_NOT_WORLD_TRUTH"
NEXT_OBSERVATION = "NEXT_OBSERVATION"
ABSTAIN = "ABSTAIN"
CORRECT = "CORRECT"
INCORRECT = "INCORRECT"
ABSTAINED = "ABSTAINED"
_ALLOWED_KINDS = frozenset((NEXT_OBSERVATION, ABSTAIN))
_ALLOWED_OUTCOMES = frozenset((CORRECT, INCORRECT, ABSTAINED))
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_GENERATION = 1_000_000
_EVALUATION_ORIGIN = object()


class WorldModelPredictionBenchmarkError(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise WorldModelPredictionBenchmarkError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise WorldModelPredictionBenchmarkError(f"{name} is outside the identifier domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise WorldModelPredictionBenchmarkError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_GENERATION:
        raise WorldModelPredictionBenchmarkError(f"{name} must be a bounded non-negative integer")
    return value


def _step(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise WorldModelPredictionBenchmarkError(f"{name} must be a non-negative integer")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class PredictionCandidate:
    schema: str
    prediction_id: str
    benchmark_run_id: str
    benchmark_generation: int
    policy_id: str
    policy_generation: int
    policy_state_sha256: str
    episode_id: str
    episode_generation: int
    fixture_id: str
    fixture_generation: int
    public_fixture_sha256: str
    step_index: int
    observation_sha256: str
    prediction_kind: str
    predicted_observation_ref: str | None
    predicted_observation_sha256: str | None
    classification: str = PUBLIC_PREDICTION_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != PREDICTION_SCHEMA or self.classification != PUBLIC_PREDICTION_CLASSIFICATION:
            raise WorldModelPredictionBenchmarkError("prediction schema/classification mismatch")
        for name, value in (
            ("prediction_id", self.prediction_id),
            ("benchmark_run_id", self.benchmark_run_id),
            ("policy_id", self.policy_id),
            ("episode_id", self.episode_id),
            ("fixture_id", self.fixture_id),
        ):
            _id(name, value)
        _generation("benchmark_generation", self.benchmark_generation)
        _generation("policy_generation", self.policy_generation)
        _generation("episode_generation", self.episode_generation)
        _generation("fixture_generation", self.fixture_generation)
        _step("step_index", self.step_index)
        for name, value in (
            ("policy_state_sha256", self.policy_state_sha256),
            ("public_fixture_sha256", self.public_fixture_sha256),
            ("observation_sha256", self.observation_sha256),
        ):
            _sha(name, value)
        if self.prediction_kind not in _ALLOWED_KINDS:
            raise WorldModelPredictionBenchmarkError("prediction_kind is not admitted")
        if self.prediction_kind == ABSTAIN:
            if self.predicted_observation_ref is not None or self.predicted_observation_sha256 is not None:
                raise WorldModelPredictionBenchmarkError("ABSTAIN must not carry a predicted observation")
        else:
            _id("predicted_observation_ref", self.predicted_observation_ref)
            _sha("predicted_observation_sha256", self.predicted_observation_sha256)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class PredictionEvaluation:
    schema: str
    benchmark_run_id: str
    benchmark_generation: int
    prediction_id: str
    prediction_sha256: str
    fixture_id: str
    fixture_generation: int
    fixture_sha256: str
    episode_id: str
    episode_generation: int
    prior_state_sha256: str
    action_request_sha256: str
    evaluator_step_sha256: str
    next_observation_sha256: str
    outcome: str
    benchmark_score_delta: int
    classification: str = EVALUATOR_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != EVALUATION_SCHEMA or self.classification != EVALUATOR_CLASSIFICATION:
            raise WorldModelPredictionBenchmarkError("evaluation schema/classification mismatch")
        for name, value in (
            ("benchmark_run_id", self.benchmark_run_id),
            ("prediction_id", self.prediction_id),
            ("fixture_id", self.fixture_id),
            ("episode_id", self.episode_id),
        ):
            _id(name, value)
        _generation("benchmark_generation", self.benchmark_generation)
        _generation("fixture_generation", self.fixture_generation)
        _generation("episode_generation", self.episode_generation)
        for name, value in (
            ("prediction_sha256", self.prediction_sha256),
            ("fixture_sha256", self.fixture_sha256),
            ("prior_state_sha256", self.prior_state_sha256),
            ("action_request_sha256", self.action_request_sha256),
            ("evaluator_step_sha256", self.evaluator_step_sha256),
            ("next_observation_sha256", self.next_observation_sha256),
        ):
            _sha(name, value)
        if self.outcome not in _ALLOWED_OUTCOMES:
            raise WorldModelPredictionBenchmarkError("evaluation outcome is not admitted")
        expected_score = {CORRECT: 1, INCORRECT: -1, ABSTAINED: 0}[self.outcome]
        if type(self.benchmark_score_delta) is not int or self.benchmark_score_delta != expected_score:
            raise WorldModelPredictionBenchmarkError("benchmark score/outcome mismatch")
        if _origin is not _EVALUATION_ORIGIN:
            raise WorldModelPredictionBenchmarkError("PredictionEvaluation must be created by evaluator API")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def prediction_for_observation(
    observation: ObservationView,
    *,
    prediction_id: str,
    benchmark_run_id: str,
    benchmark_generation: int,
    policy_id: str,
    policy_generation: int,
    policy_state_sha256: str,
    predicted_observation_ref: str,
    predicted_observation_sha256: str,
) -> PredictionCandidate:
    """Create an untrusted next-observation candidate from an exact public view only."""
    if type(observation) is not ObservationView:
        raise WorldModelPredictionBenchmarkError("observation must be exact concrete ObservationView")
    return PredictionCandidate(
        PREDICTION_SCHEMA,
        prediction_id,
        benchmark_run_id,
        benchmark_generation,
        policy_id,
        policy_generation,
        policy_state_sha256,
        observation.episode_id,
        observation.episode_generation,
        observation.fixture_id,
        observation.fixture_generation,
        observation.public_fixture_sha256,
        observation.step_index,
        observation.sha256(),
        NEXT_OBSERVATION,
        predicted_observation_ref,
        predicted_observation_sha256,
    )


def abstain_for_observation(
    observation: ObservationView,
    *,
    prediction_id: str,
    benchmark_run_id: str,
    benchmark_generation: int,
    policy_id: str,
    policy_generation: int,
    policy_state_sha256: str,
) -> PredictionCandidate:
    """Represent insufficient public evidence without forcing a prediction."""
    if type(observation) is not ObservationView:
        raise WorldModelPredictionBenchmarkError("observation must be exact concrete ObservationView")
    return PredictionCandidate(
        PREDICTION_SCHEMA,
        prediction_id,
        benchmark_run_id,
        benchmark_generation,
        policy_id,
        policy_generation,
        policy_state_sha256,
        observation.episode_id,
        observation.episode_generation,
        observation.fixture_id,
        observation.fixture_generation,
        observation.public_fixture_sha256,
        observation.step_index,
        observation.sha256(),
        ABSTAIN,
        None,
        None,
    )


def persistence_baseline(
    observation: ObservationView,
    *,
    prediction_id: str,
    benchmark_run_id: str,
    benchmark_generation: int,
    policy_id: str = "PUBLIC_PERSISTENCE_BASELINE",
    policy_generation: int = 1,
    policy_state_sha256: str = "0" * 64,
) -> PredictionCandidate:
    """Public-only baseline: predict that the current public observation persists."""
    if type(observation) is not ObservationView:
        raise WorldModelPredictionBenchmarkError("observation must be exact concrete ObservationView")
    return prediction_for_observation(
        observation,
        prediction_id=prediction_id,
        benchmark_run_id=benchmark_run_id,
        benchmark_generation=benchmark_generation,
        policy_id=policy_id,
        policy_generation=policy_generation,
        policy_state_sha256=policy_state_sha256,
        predicted_observation_ref=observation.observation_ref,
        predicted_observation_sha256=observation.observation_sha256,
    )


def _assert_prediction_matches_public_view(prediction: PredictionCandidate, observation: ObservationView) -> None:
    if type(prediction) is not PredictionCandidate:
        raise WorldModelPredictionBenchmarkError("prediction must be exact concrete PredictionCandidate")
    expected = (
        observation.episode_id,
        observation.episode_generation,
        observation.fixture_id,
        observation.fixture_generation,
        observation.public_fixture_sha256,
        observation.step_index,
        observation.sha256(),
    )
    actual = (
        prediction.episode_id,
        prediction.episode_generation,
        prediction.fixture_id,
        prediction.fixture_generation,
        prediction.public_fixture_sha256,
        prediction.step_index,
        prediction.observation_sha256,
    )
    if actual != expected:
        raise WorldModelPredictionBenchmarkError("prediction/public-observation provenance mismatch")


def evaluate_next_observation_prediction(
    fixture: MicroWorldFixture,
    *,
    state: EpisodeState,
    action_id: str,
    prediction: PredictionCandidate,
) -> tuple[EpisodeState, ObservationView, EvaluatorStep, PredictionEvaluation]:
    """Advance with WP800, then score a pre-existing candidate on evaluator side.

    The prediction is validated against the exact current public observation before the
    evaluator sees the transition outcome. This function never feeds fixture nodes,
    transitions, evaluator scores, or hidden-ground-truth references into a policy.
    """
    if type(fixture) is not MicroWorldFixture or type(state) is not EpisodeState:
        raise WorldModelPredictionBenchmarkError("fixture/state must be exact concrete WP800 values")
    observation = observation_for_state(fixture, state)
    _assert_prediction_matches_public_view(prediction, observation)
    request = ActionRequest.for_observation(observation, action_id=action_id)
    prior_state_sha256 = state.sha256()
    next_state, next_observation, evaluator_step = step_episode(fixture, state=state, request=request)
    if prediction.prediction_kind == ABSTAIN:
        outcome = ABSTAINED
    elif (
        prediction.predicted_observation_ref == next_observation.observation_ref
        and prediction.predicted_observation_sha256 == next_observation.observation_sha256
    ):
        outcome = CORRECT
    else:
        outcome = INCORRECT
    score = {CORRECT: 1, INCORRECT: -1, ABSTAINED: 0}[outcome]
    evaluation = PredictionEvaluation(
        EVALUATION_SCHEMA,
        prediction.benchmark_run_id,
        prediction.benchmark_generation,
        prediction.prediction_id,
        prediction.sha256(),
        fixture.fixture_id,
        fixture.generation,
        fixture.sha256(),
        state.episode_id,
        state.episode_generation,
        prior_state_sha256,
        request.sha256(),
        evaluator_step.sha256(),
        next_observation.sha256(),
        outcome,
        score,
        _origin=_EVALUATION_ORIGIN,
    )
    return next_state, next_observation, evaluator_step, evaluation
