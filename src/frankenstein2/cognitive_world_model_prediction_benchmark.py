"""F2-WP-803 held-out world-model prediction benchmark.

The policy boundary accepts only an exact WP800 ``ObservationView`` plus explicit
immutable public policy configuration/state. Hidden fixture nodes, transitions,
scores and ground-truth refs are evaluator-only. Benchmark scores are measurements,
not world truth, causal credit, completion authority or runtime evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
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
    RunDescriptor,
)

POLICY_CONFIG_SCHEMA = "FRANKENSTEIN2_WORLD_MODEL_POLICY_CONFIG/v1"
PUBLIC_MEMORY_SCHEMA = "FRANKENSTEIN2_WORLD_MODEL_PUBLIC_MEMORY/v1"
RAW_PREDICTION_SCHEMA = "FRANKENSTEIN2_WORLD_MODEL_RAW_PREDICTION/v1"
BOUND_PREDICTION_SCHEMA = "FRANKENSTEIN2_WORLD_MODEL_BOUND_PREDICTION/v1"
PREDICTION_SCORE_SCHEMA = "FRANKENSTEIN2_WORLD_MODEL_PREDICTION_SCORE/v1"

PUBLIC_MEMORY = "PUBLIC_MEMORY"
PERSISTENCE = "PERSISTENCE"
ABSTAIN = "ABSTAIN"
_ALLOWED_POLICIES = frozenset((PUBLIC_MEMORY, PERSISTENCE, ABSTAIN))

PREDICTED = "PREDICTED"
UNKNOWN = "UNKNOWN"
CORRECT = "CORRECT"
INCORRECT = "INCORRECT"
ABSTAINED = "ABSTAINED"

PUBLIC_POLICY_CLASSIFICATION = "PUBLIC_OBSERVATION_ONLY_NO_EVALUATOR_GROUND_TRUTH"
EVALUATION_CLASSIFICATION = "EVALUATOR_MEASUREMENT_ONLY_NO_WORLD_OR_RUNTIME_AUTHORITY"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512


class WorldModelPredictionError(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise WorldModelPredictionError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise WorldModelPredictionError(f"{name} is outside the identifier domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise WorldModelPredictionError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _nint(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise WorldModelPredictionError(f"{name} must be a non-negative integer")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    schema: str
    policy_id: str
    generation: int
    policy_kind: str
    classification: str = PUBLIC_POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != POLICY_CONFIG_SCHEMA or self.classification != PUBLIC_POLICY_CLASSIFICATION:
            raise WorldModelPredictionError("policy config schema/classification mismatch")
        _id("policy_id", self.policy_id)
        _nint("generation", self.generation)
        if self.policy_kind not in _ALLOWED_POLICIES:
            raise WorldModelPredictionError("unknown policy_kind")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class PublicTransitionMemoryEntry:
    fixture_id: str
    fixture_generation: int
    public_fixture_sha256: str
    observation_ref: str
    observation_sha256: str
    action_id: str
    next_observation_ref: str
    next_observation_sha256: str

    def __post_init__(self) -> None:
        _id("fixture_id", self.fixture_id)
        _nint("fixture_generation", self.fixture_generation)
        _sha("public_fixture_sha256", self.public_fixture_sha256)
        _id("observation_ref", self.observation_ref)
        _sha("observation_sha256", self.observation_sha256)
        _id("action_id", self.action_id)
        _id("next_observation_ref", self.next_observation_ref)
        _sha("next_observation_sha256", self.next_observation_sha256)

    def key(self) -> tuple[str, int, str, str, str, str]:
        return (
            self.fixture_id,
            self.fixture_generation,
            self.public_fixture_sha256,
            self.observation_ref,
            self.observation_sha256,
            self.action_id,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PublicTransitionMemory:
    schema: str
    generation: int
    entries: tuple[PublicTransitionMemoryEntry, ...]
    classification: str = PUBLIC_POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != PUBLIC_MEMORY_SCHEMA or self.classification != PUBLIC_POLICY_CLASSIFICATION:
            raise WorldModelPredictionError("public memory schema/classification mismatch")
        _nint("generation", self.generation)
        if type(self.entries) is not tuple or any(type(x) is not PublicTransitionMemoryEntry for x in self.entries):
            raise WorldModelPredictionError("entries must be an immutable tuple of exact public-memory entries")
        keys = tuple(x.key() for x in self.entries)
        if keys != tuple(sorted(keys)):
            raise WorldModelPredictionError("public memory entries must be in canonical key order")
        if len(keys) != len(set(keys)):
            raise WorldModelPredictionError("public memory contains duplicate transition keys")

    @classmethod
    def empty(cls) -> "PublicTransitionMemory":
        return cls(PUBLIC_MEMORY_SCHEMA, 0, ())

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "generation": self.generation,
            "entries": [x.as_dict() for x in self.entries],
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RawPrediction:
    schema: str
    policy_id: str
    policy_generation: int
    policy_config_sha256: str
    public_memory_sha256: str
    episode_id: str
    episode_generation: int
    fixture_id: str
    fixture_generation: int
    public_fixture_sha256: str
    step_index: int
    observation_sha256: str
    action_id: str
    status: str
    predicted_observation_ref: str | None
    predicted_observation_sha256: str | None
    classification: str = PUBLIC_POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != RAW_PREDICTION_SCHEMA or self.classification != PUBLIC_POLICY_CLASSIFICATION:
            raise WorldModelPredictionError("raw prediction schema/classification mismatch")
        _id("policy_id", self.policy_id)
        _nint("policy_generation", self.policy_generation)
        _sha("policy_config_sha256", self.policy_config_sha256)
        _sha("public_memory_sha256", self.public_memory_sha256)
        _id("episode_id", self.episode_id)
        _nint("episode_generation", self.episode_generation)
        _id("fixture_id", self.fixture_id)
        _nint("fixture_generation", self.fixture_generation)
        _sha("public_fixture_sha256", self.public_fixture_sha256)
        _nint("step_index", self.step_index)
        _sha("observation_sha256", self.observation_sha256)
        _id("action_id", self.action_id)
        if self.status not in (PREDICTED, UNKNOWN):
            raise WorldModelPredictionError("prediction status must be PREDICTED or UNKNOWN")
        if self.status == UNKNOWN:
            if self.predicted_observation_ref is not None or self.predicted_observation_sha256 is not None:
                raise WorldModelPredictionError("UNKNOWN prediction must not fabricate an observation")
        else:
            _id("predicted_observation_ref", self.predicted_observation_ref)
            _sha("predicted_observation_sha256", self.predicted_observation_sha256)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class BoundPrediction:
    schema: str
    run_id: str
    run_descriptor_sha256: str
    raw_prediction: RawPrediction
    classification: str = EVALUATION_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != BOUND_PREDICTION_SCHEMA or self.classification != EVALUATION_CLASSIFICATION:
            raise WorldModelPredictionError("bound prediction schema/classification mismatch")
        _id("run_id", self.run_id)
        _sha("run_descriptor_sha256", self.run_descriptor_sha256)
        if type(self.raw_prediction) is not RawPrediction:
            raise WorldModelPredictionError("raw_prediction must be exact RawPrediction")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "run_descriptor_sha256": self.run_descriptor_sha256,
            "raw_prediction": self.raw_prediction.as_dict(),
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class PredictionScore:
    schema: str
    run_id: str
    run_descriptor_sha256: str
    prediction_sha256: str
    evaluator_step_sha256: str
    next_observation_sha256: str
    result: str
    points: int
    classification: str = EVALUATION_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != PREDICTION_SCORE_SCHEMA or self.classification != EVALUATION_CLASSIFICATION:
            raise WorldModelPredictionError("prediction score schema/classification mismatch")
        _id("run_id", self.run_id)
        for name, value in (
            ("run_descriptor_sha256", self.run_descriptor_sha256),
            ("prediction_sha256", self.prediction_sha256),
            ("evaluator_step_sha256", self.evaluator_step_sha256),
            ("next_observation_sha256", self.next_observation_sha256),
        ):
            _sha(name, value)
        if self.result not in (CORRECT, INCORRECT, ABSTAINED):
            raise WorldModelPredictionError("unknown score result")
        expected = {CORRECT: 1, INCORRECT: 0, ABSTAINED: 0}[self.result]
        if self.points != expected:
            raise WorldModelPredictionError("points do not match score result")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _assert_public_inputs(observation: ObservationView, config: PolicyConfig, memory: PublicTransitionMemory, action_id: str) -> None:
    if type(observation) is not ObservationView:
        raise WorldModelPredictionError("policy input must be exact concrete ObservationView")
    if type(config) is not PolicyConfig:
        raise WorldModelPredictionError("config must be exact concrete PolicyConfig")
    if type(memory) is not PublicTransitionMemory:
        raise WorldModelPredictionError("memory must be exact concrete PublicTransitionMemory")
    _id("action_id", action_id)
    if observation.terminal:
        raise WorldModelPredictionError("terminal observation cannot request a next-observation prediction")
    if action_id not in observation.available_action_ids:
        raise WorldModelPredictionError("action_id is not publically available in this observation")


def predict_next_public_observation(
    observation: ObservationView,
    *,
    action_id: str,
    config: PolicyConfig,
    memory: PublicTransitionMemory,
) -> RawPrediction:
    """Policy/SUT boundary: no evaluator-only object is accepted here."""
    _assert_public_inputs(observation, config, memory, action_id)
    predicted_ref: str | None = None
    predicted_sha: str | None = None

    if config.policy_kind == PERSISTENCE:
        predicted_ref = observation.observation_ref
        predicted_sha = observation.observation_sha256
    elif config.policy_kind == PUBLIC_MEMORY:
        key = (
            observation.fixture_id,
            observation.fixture_generation,
            observation.public_fixture_sha256,
            observation.observation_ref,
            observation.observation_sha256,
            action_id,
        )
        matches = tuple(x for x in memory.entries if x.key() == key)
        if len(matches) > 1:
            raise WorldModelPredictionError("ambiguous public transition memory")
        if matches:
            predicted_ref = matches[0].next_observation_ref
            predicted_sha = matches[0].next_observation_sha256
    elif config.policy_kind != ABSTAIN:
        raise WorldModelPredictionError("unsupported policy kind")

    status = PREDICTED if predicted_ref is not None else UNKNOWN
    return RawPrediction(
        RAW_PREDICTION_SCHEMA,
        config.policy_id,
        config.generation,
        config.sha256(),
        memory.sha256(),
        observation.episode_id,
        observation.episode_generation,
        observation.fixture_id,
        observation.fixture_generation,
        observation.public_fixture_sha256,
        observation.step_index,
        observation.sha256(),
        action_id,
        status,
        predicted_ref,
        predicted_sha,
    )


def bind_prediction_to_run(
    prediction: RawPrediction,
    *,
    run: RunDescriptor,
    fixture: MicroWorldFixture,
) -> BoundPrediction:
    """Evaluator-side provenance seal; this function is outside the policy boundary."""
    if type(prediction) is not RawPrediction or type(run) is not RunDescriptor or type(fixture) is not MicroWorldFixture:
        raise WorldModelPredictionError("prediction/run/fixture must be exact concrete values")
    try:
        run.assert_matches_fixture(fixture)
    except CognitiveMicroWorldError as exc:
        raise WorldModelPredictionError(str(exc)) from exc
    if (prediction.fixture_id, prediction.fixture_generation, prediction.public_fixture_sha256) != (
        fixture.fixture_id,
        fixture.generation,
        fixture.public_sha256(),
    ):
        raise WorldModelPredictionError("prediction fixture/public digest does not match bound run fixture")
    return BoundPrediction(BOUND_PREDICTION_SCHEMA, run.run_id, run.sha256(), prediction)


def _assert_evaluator_transition(
    *,
    prior_observation: ObservationView,
    request: ActionRequest,
    next_state: EpisodeState,
    next_observation: ObservationView,
    evaluator_step: EvaluatorStep,
) -> None:
    if any((
        type(prior_observation) is not ObservationView,
        type(request) is not ActionRequest,
        type(next_state) is not EpisodeState,
        type(next_observation) is not ObservationView,
        type(evaluator_step) is not EvaluatorStep,
    )):
        raise WorldModelPredictionError("evaluation requires exact WP800 transition values")
    if request.observation_sha256 != prior_observation.sha256():
        raise WorldModelPredictionError("request is not bound to prior public observation")
    if evaluator_step.action_request_sha256 != request.sha256():
        raise WorldModelPredictionError("evaluator step is not bound to action request")
    if evaluator_step.next_state_sha256 != next_state.sha256():
        raise WorldModelPredictionError("evaluator step is not bound to next state")
    if next_observation.step_index != prior_observation.step_index + 1:
        raise WorldModelPredictionError("next observation does not advance exactly one step")
    identity_prior = (prior_observation.episode_id, prior_observation.episode_generation, prior_observation.fixture_id, prior_observation.fixture_generation, prior_observation.public_fixture_sha256)
    identity_next = (next_observation.episode_id, next_observation.episode_generation, next_observation.fixture_id, next_observation.fixture_generation, next_observation.public_fixture_sha256)
    if identity_prior != identity_next:
        raise WorldModelPredictionError("episode/fixture/generation changed across evaluator transition")


def learn_public_transition(
    memory: PublicTransitionMemory,
    *,
    prior_observation: ObservationView,
    request: ActionRequest,
    next_state: EpisodeState,
    next_observation: ObservationView,
    evaluator_step: EvaluatorStep,
) -> PublicTransitionMemory:
    """Learn only public values after an attested canonical WP800 evaluator advance."""
    if type(memory) is not PublicTransitionMemory:
        raise WorldModelPredictionError("memory must be exact PublicTransitionMemory")
    _assert_evaluator_transition(
        prior_observation=prior_observation,
        request=request,
        next_state=next_state,
        next_observation=next_observation,
        evaluator_step=evaluator_step,
    )
    entry = PublicTransitionMemoryEntry(
        prior_observation.fixture_id,
        prior_observation.fixture_generation,
        prior_observation.public_fixture_sha256,
        prior_observation.observation_ref,
        prior_observation.observation_sha256,
        request.action_id,
        next_observation.observation_ref,
        next_observation.observation_sha256,
    )
    existing = {x.key(): x for x in memory.entries}
    old = existing.get(entry.key())
    if old is not None and old != entry:
        raise WorldModelPredictionError("public transition memory conflict; preserve UNKNOWN rather than overwrite")
    existing[entry.key()] = entry
    return PublicTransitionMemory(
        PUBLIC_MEMORY_SCHEMA,
        memory.generation + 1,
        tuple(sorted(existing.values(), key=lambda x: x.key())),
    )


def evaluate_prediction_after_step(
    bound: BoundPrediction,
    *,
    run: RunDescriptor,
    fixture: MicroWorldFixture,
    prior_observation: ObservationView,
    request: ActionRequest,
    next_state: EpisodeState,
    next_observation: ObservationView,
    evaluator_step: EvaluatorStep,
) -> PredictionScore:
    """Score only after WP800 ``step_episode`` has produced the next public view."""
    if type(bound) is not BoundPrediction or type(run) is not RunDescriptor or type(fixture) is not MicroWorldFixture:
        raise WorldModelPredictionError("bound/run/fixture must be exact concrete values")
    try:
        run.assert_matches_fixture(fixture)
    except CognitiveMicroWorldError as exc:
        raise WorldModelPredictionError(str(exc)) from exc
    if (bound.run_id, bound.run_descriptor_sha256) != (run.run_id, run.sha256()):
        raise WorldModelPredictionError("bound prediction run identity mismatch")
    prediction = bound.raw_prediction
    if (
        prediction.episode_id,
        prediction.episode_generation,
        prediction.fixture_id,
        prediction.fixture_generation,
        prediction.public_fixture_sha256,
        prediction.step_index,
        prediction.observation_sha256,
        prediction.action_id,
    ) != (
        prior_observation.episode_id,
        prior_observation.episode_generation,
        prior_observation.fixture_id,
        prior_observation.fixture_generation,
        prior_observation.public_fixture_sha256,
        prior_observation.step_index,
        prior_observation.sha256(),
        request.action_id,
    ):
        raise WorldModelPredictionError("prediction is not bound to this prior public observation/action")
    _assert_evaluator_transition(
        prior_observation=prior_observation,
        request=request,
        next_state=next_state,
        next_observation=next_observation,
        evaluator_step=evaluator_step,
    )
    if prediction.status == UNKNOWN:
        result = ABSTAINED
    elif (prediction.predicted_observation_ref, prediction.predicted_observation_sha256) == (
        next_observation.observation_ref,
        next_observation.observation_sha256,
    ):
        result = CORRECT
    else:
        result = INCORRECT
    return PredictionScore(
        PREDICTION_SCORE_SCHEMA,
        run.run_id,
        run.sha256(),
        bound.sha256(),
        evaluator_step.sha256(),
        next_observation.sha256(),
        result,
        1 if result == CORRECT else 0,
    )
