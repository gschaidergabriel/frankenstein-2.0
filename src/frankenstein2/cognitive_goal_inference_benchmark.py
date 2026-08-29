"""F2-WP-804 deterministic held-out goal-inference benchmark.

Policy input is restricted to exact public ObservationView values and immutable public
CandidateGoal values. Evaluator labels require a sealed policy inference and are constrained
by identifiability from the same declared public evidence. Agreement is benchmark evidence
only; it never grants goal-adoption, effect, completion, runtime, GRID/GWT/J-Space, training
or world-truth authority.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass
import hashlib
import json
import re
from typing import Any, Callable

from frankenstein2.cognitive_microworld import (
    CognitiveMicroWorldError,
    EpisodeState,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
    observation_for_state,
)

CANDIDATE_GOAL_SCHEMA = "FRANKENSTEIN2_COGNITIVE_GOAL_CANDIDATE/v1"
GOAL_CHOICE_SCHEMA = "FRANKENSTEIN2_COGNITIVE_GOAL_CHOICE/v1"
GOAL_INFERENCE_SCHEMA = "FRANKENSTEIN2_COGNITIVE_GOAL_INFERENCE/v1"
GOAL_LABEL_SCHEMA = "FRANKENSTEIN2_COGNITIVE_GOAL_EVALUATOR_LABEL/v1"
GOAL_SCORE_SCHEMA = "FRANKENSTEIN2_COGNITIVE_GOAL_INFERENCE_SCORE/v1"
PUBLIC_CANDIDATE_CLASSIFICATION = "PUBLIC_GOAL_CANDIDATE_NO_ADOPTION_AUTHORITY"
POLICY_OUTPUT_CLASSIFICATION = "POLICY_OUTPUT_BENCHMARK_ONLY_NO_GOAL_AUTHORITY"
EVALUATOR_CLASSIFICATION = "EVALUATOR_ONLY_NOT_POLICY_INPUT_OR_GOAL_AUTHORITY"
SCORE_CLASSIFICATION = "BENCHMARK_MEASUREMENT_ONLY_NO_GOAL_ADOPTION_AUTHORITY"
GOAL = "GOAL"
ABSTAIN = "ABSTAIN"
IDENTIFIABLE = "IDENTIFIABLE_FROM_DECLARED_PUBLIC_SIGNAL"
NON_IDENTIFIABLE = "NON_IDENTIFIABLE_FROM_DECLARED_PUBLIC_SIGNAL"
_ALLOWED_DECISIONS = frozenset((GOAL, ABSTAIN))
_ALLOWED_IDENTIFIABILITY = frozenset((IDENTIFIABLE, NON_IDENTIFIABLE))
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LABEL_ORIGIN = object()
_SCORE_ORIGIN = object()


class GoalInferenceBenchmarkError(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise GoalInferenceBenchmarkError(f"{name} must be a non-empty trimmed string")
    if len(value) > 512 or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise GoalInferenceBenchmarkError(f"{name} is outside the identifier domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise GoalInferenceBenchmarkError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Any) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GoalInferenceBenchmarkError(f"{name} must be an immutable tuple")
    if len(values) > 4096:
        raise GoalInferenceBenchmarkError(f"{name} exceeds reference ceiling")
    out = tuple(_id(f"{name} item", value) for value in values)
    if len(out) != len(set(out)):
        raise GoalInferenceBenchmarkError(f"{name} contains duplicate references")
    if out != tuple(sorted(out)):
        raise GoalInferenceBenchmarkError(f"{name} must be in canonical lexical order")
    return out


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class _Digestible:
    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class CandidateGoal(_Digestible):
    schema: str
    goal_id: str
    public_goal_ref: str
    public_goal_sha256: str
    public_signal_refs: tuple[str, ...]
    classification: str = PUBLIC_CANDIDATE_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != CANDIDATE_GOAL_SCHEMA or self.classification != PUBLIC_CANDIDATE_CLASSIFICATION:
            raise GoalInferenceBenchmarkError("candidate-goal schema/classification mismatch")
        _id("goal_id", self.goal_id)
        _id("public_goal_ref", self.public_goal_ref)
        _sha("public_goal_sha256", self.public_goal_sha256)
        _refs("public_signal_refs", self.public_signal_refs)


def candidate_set_digest(candidates: tuple[CandidateGoal, ...]) -> str:
    if type(candidates) is not tuple or not candidates:
        raise GoalInferenceBenchmarkError("candidates must be a non-empty immutable tuple")
    if any(type(item) is not CandidateGoal for item in candidates):
        raise GoalInferenceBenchmarkError("candidates must contain exact concrete CandidateGoal values")
    if candidates != tuple(sorted(candidates, key=lambda item: item.goal_id)):
        raise GoalInferenceBenchmarkError("candidates must be in canonical goal_id order")
    ids = tuple(item.goal_id for item in candidates)
    if len(ids) != len(set(ids)):
        raise GoalInferenceBenchmarkError("goal_id values must be unique")
    return _digest([item.as_dict() for item in candidates])


def public_signal_matches(observation: ObservationView, candidates: tuple[CandidateGoal, ...]) -> tuple[str, ...]:
    if type(observation) is not ObservationView:
        raise GoalInferenceBenchmarkError("observation must be exact concrete ObservationView")
    candidate_set_digest(candidates)
    return tuple(item.goal_id for item in candidates if observation.observation_ref in item.public_signal_refs)


def public_identifiability_digest(observation: ObservationView, candidates: tuple[CandidateGoal, ...]) -> str:
    matches = public_signal_matches(observation, candidates)
    return _digest(
        {
            "observation_sha256": observation.sha256(),
            "candidate_set_sha256": candidate_set_digest(candidates),
            "matching_goal_ids": list(matches),
            "identifiability": IDENTIFIABLE if len(matches) == 1 else NON_IDENTIFIABLE,
        }
    )


@dataclass(frozen=True, slots=True)
class GoalChoice(_Digestible):
    schema: str
    decision: str
    goal_id: str | None
    public_reason_refs: tuple[str, ...]
    classification: str = POLICY_OUTPUT_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != GOAL_CHOICE_SCHEMA or self.classification != POLICY_OUTPUT_CLASSIFICATION:
            raise GoalInferenceBenchmarkError("goal-choice schema/classification mismatch")
        if self.decision not in _ALLOWED_DECISIONS:
            raise GoalInferenceBenchmarkError("decision must be GOAL or ABSTAIN")
        _refs("public_reason_refs", self.public_reason_refs)
        if self.decision == GOAL:
            _id("goal_id", self.goal_id)
        elif self.goal_id is not None:
            raise GoalInferenceBenchmarkError("ABSTAIN must not carry goal_id")

    @classmethod
    def goal(cls, goal_id: str, *, public_reason_refs: tuple[str, ...] = ()) -> "GoalChoice":
        return cls(GOAL_CHOICE_SCHEMA, GOAL, goal_id, public_reason_refs)

    @classmethod
    def abstain(cls, *, public_reason_refs: tuple[str, ...] = ()) -> "GoalChoice":
        return cls(GOAL_CHOICE_SCHEMA, ABSTAIN, None, public_reason_refs)


@dataclass(frozen=True, slots=True)
class GoalInference(_Digestible):
    schema: str
    run_descriptor_sha256: str
    fixture_id: str
    fixture_generation: int
    public_fixture_sha256: str
    episode_id: str
    episode_generation: int
    observation_sha256: str
    candidate_set_sha256: str
    choice: GoalChoice
    classification: str = POLICY_OUTPUT_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != GOAL_INFERENCE_SCHEMA or self.classification != POLICY_OUTPUT_CLASSIFICATION:
            raise GoalInferenceBenchmarkError("goal-inference schema/classification mismatch")
        _sha("run_descriptor_sha256", self.run_descriptor_sha256)
        _id("fixture_id", self.fixture_id)
        if type(self.fixture_generation) is not int or self.fixture_generation < 0:
            raise GoalInferenceBenchmarkError("fixture_generation must be a non-negative integer")
        _sha("public_fixture_sha256", self.public_fixture_sha256)
        _id("episode_id", self.episode_id)
        if type(self.episode_generation) is not int or self.episode_generation < 0:
            raise GoalInferenceBenchmarkError("episode_generation must be a non-negative integer")
        _sha("observation_sha256", self.observation_sha256)
        _sha("candidate_set_sha256", self.candidate_set_sha256)
        if type(self.choice) is not GoalChoice:
            raise GoalInferenceBenchmarkError("choice must be exact concrete GoalChoice")


Policy = Callable[[ObservationView, tuple[CandidateGoal, ...]], GoalChoice]


def run_goal_inference(*, policy: Policy, run: RunDescriptor, fixture: MicroWorldFixture,
                       observation: ObservationView, candidates: tuple[CandidateGoal, ...]) -> GoalInference:
    if not callable(policy):
        raise GoalInferenceBenchmarkError("policy must be callable")
    if type(run) is not RunDescriptor:
        raise GoalInferenceBenchmarkError("run must be exact concrete RunDescriptor")
    if type(fixture) is not MicroWorldFixture:
        raise GoalInferenceBenchmarkError("fixture must be exact concrete MicroWorldFixture")
    if type(observation) is not ObservationView:
        raise GoalInferenceBenchmarkError("observation must be exact concrete ObservationView")
    try:
        run.assert_matches_fixture(fixture)
    except CognitiveMicroWorldError as exc:
        raise GoalInferenceBenchmarkError(str(exc)) from exc
    if (observation.fixture_id, observation.fixture_generation) != (fixture.fixture_id, fixture.generation):
        raise GoalInferenceBenchmarkError("observation fixture identity/generation mismatch")
    if observation.public_fixture_sha256 != fixture.public_sha256():
        raise GoalInferenceBenchmarkError("observation public fixture digest mismatch")
    candidate_digest = candidate_set_digest(candidates)
    choice = policy(observation, candidates)
    if type(choice) is not GoalChoice:
        raise GoalInferenceBenchmarkError("policy must return exact concrete GoalChoice")
    if choice.goal_id is not None and choice.goal_id not in {item.goal_id for item in candidates}:
        raise GoalInferenceBenchmarkError("policy selected goal outside candidate set")
    return GoalInference(
        GOAL_INFERENCE_SCHEMA,
        run.sha256(),
        observation.fixture_id,
        observation.fixture_generation,
        observation.public_fixture_sha256,
        observation.episode_id,
        observation.episode_generation,
        observation.sha256(),
        candidate_digest,
        choice,
    )


def canonical_first_policy(observation: ObservationView, candidates: tuple[CandidateGoal, ...]) -> GoalChoice:
    if type(observation) is not ObservationView:
        raise GoalInferenceBenchmarkError("observation must be exact concrete ObservationView")
    candidate_set_digest(candidates)
    return GoalChoice.goal(candidates[0].goal_id, public_reason_refs=("baseline:canonical-first",))


def always_abstain_policy(observation: ObservationView, candidates: tuple[CandidateGoal, ...]) -> GoalChoice:
    if type(observation) is not ObservationView:
        raise GoalInferenceBenchmarkError("observation must be exact concrete ObservationView")
    candidate_set_digest(candidates)
    return GoalChoice.abstain(public_reason_refs=("baseline:always-abstain",))


def unique_public_signal_policy(observation: ObservationView, candidates: tuple[CandidateGoal, ...]) -> GoalChoice:
    matches = public_signal_matches(observation, candidates)
    if len(matches) == 1:
        return GoalChoice.goal(matches[0], public_reason_refs=(observation.observation_ref,))
    return GoalChoice.abstain(public_reason_refs=(observation.observation_ref,))


def _assert_inference_binding(*, run: RunDescriptor, fixture: MicroWorldFixture, state: EpisodeState,
                              observation: ObservationView, candidates: tuple[CandidateGoal, ...],
                              inference: GoalInference) -> None:
    if type(run) is not RunDescriptor or type(inference) is not GoalInference:
        raise GoalInferenceBenchmarkError("run/inference must be exact concrete benchmark values")
    try:
        run.assert_matches_fixture(fixture)
    except CognitiveMicroWorldError as exc:
        raise GoalInferenceBenchmarkError(str(exc)) from exc
    candidate_digest = candidate_set_digest(candidates)
    if inference.run_descriptor_sha256 != run.sha256():
        raise GoalInferenceBenchmarkError("inference run descriptor binding mismatch")
    if (inference.fixture_id, inference.fixture_generation, inference.public_fixture_sha256) != (
        fixture.fixture_id,
        fixture.generation,
        fixture.public_sha256(),
    ):
        raise GoalInferenceBenchmarkError("inference fixture identity/generation mismatch")
    if (inference.episode_id, inference.episode_generation) != (state.episode_id, state.episode_generation):
        raise GoalInferenceBenchmarkError("inference episode identity/generation mismatch")
    if (inference.observation_sha256, inference.candidate_set_sha256) != (observation.sha256(), candidate_digest):
        raise GoalInferenceBenchmarkError("inference observation/candidate binding mismatch")


@dataclass(frozen=True, slots=True)
class EvaluatorGoalLabel(_Digestible):
    schema: str
    run_descriptor_sha256: str
    fixture_sha256: str
    state_sha256: str
    observation_sha256: str
    candidate_set_sha256: str
    public_identifiability_sha256: str
    identifiability: str
    expected_decision: str
    expected_goal_id: str | None
    label_ref: str
    label_sha256: str
    sealed_inference_sha256: str
    classification: str = EVALUATOR_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != GOAL_LABEL_SCHEMA or self.classification != EVALUATOR_CLASSIFICATION:
            raise GoalInferenceBenchmarkError("evaluator label schema/classification mismatch")
        for name in (
            "run_descriptor_sha256",
            "fixture_sha256",
            "state_sha256",
            "observation_sha256",
            "candidate_set_sha256",
            "public_identifiability_sha256",
            "label_sha256",
            "sealed_inference_sha256",
        ):
            _sha(name, getattr(self, name))
        if self.identifiability not in _ALLOWED_IDENTIFIABILITY:
            raise GoalInferenceBenchmarkError("identifiability domain mismatch")
        if self.expected_decision not in _ALLOWED_DECISIONS:
            raise GoalInferenceBenchmarkError("expected_decision must be GOAL or ABSTAIN")
        if self.expected_decision == GOAL:
            _id("expected_goal_id", self.expected_goal_id)
            if self.identifiability != IDENTIFIABLE:
                raise GoalInferenceBenchmarkError("exact GOAL label requires public identifiability")
        elif self.expected_goal_id is not None:
            raise GoalInferenceBenchmarkError("ABSTAIN label must not carry expected_goal_id")
        _id("label_ref", self.label_ref)
        if _origin is not _LABEL_ORIGIN:
            raise GoalInferenceBenchmarkError("EvaluatorGoalLabel must be created by seal_evaluator_goal_label")


def seal_evaluator_goal_label(*, run: RunDescriptor, fixture: MicroWorldFixture, state: EpisodeState,
                              observation: ObservationView, candidates: tuple[CandidateGoal, ...],
                              inference: GoalInference, expected_goal_id: str | None,
                              label_ref: str, label_sha256: str) -> EvaluatorGoalLabel:
    if type(fixture) is not MicroWorldFixture or type(state) is not EpisodeState:
        raise GoalInferenceBenchmarkError("fixture/state must be exact concrete evaluator values")
    if type(observation) is not ObservationView:
        raise GoalInferenceBenchmarkError("observation must be exact concrete ObservationView")
    try:
        expected_observation = observation_for_state(fixture, state)
    except CognitiveMicroWorldError as exc:
        raise GoalInferenceBenchmarkError(str(exc)) from exc
    if observation != expected_observation:
        raise GoalInferenceBenchmarkError("observation is stale or not evaluator-derived from state")
    _assert_inference_binding(
        run=run,
        fixture=fixture,
        state=state,
        observation=observation,
        candidates=candidates,
        inference=inference,
    )
    matches = public_signal_matches(observation, candidates)
    identifiability = IDENTIFIABLE if len(matches) == 1 else NON_IDENTIFIABLE
    if identifiability == IDENTIFIABLE:
        if expected_goal_id != matches[0]:
            raise GoalInferenceBenchmarkError("exact evaluator goal label contradicts uniquely identifying public evidence")
    elif expected_goal_id is not None:
        raise GoalInferenceBenchmarkError("ambiguous public evidence cannot mint exact evaluator goal label")
    return EvaluatorGoalLabel(
        GOAL_LABEL_SCHEMA,
        run.sha256(),
        fixture.sha256(),
        state.sha256(),
        observation.sha256(),
        candidate_set_digest(candidates),
        public_identifiability_digest(observation, candidates),
        identifiability,
        GOAL if expected_goal_id is not None else ABSTAIN,
        expected_goal_id,
        label_ref,
        label_sha256,
        inference.sha256(),
        _origin=_LABEL_ORIGIN,
    )


@dataclass(frozen=True, slots=True)
class GoalInferenceScore(_Digestible):
    schema: str
    inference_sha256: str
    label_sha256: str
    identifiability: str
    decision: str
    inferred_goal_id: str | None
    expected_decision: str
    expected_goal_id: str | None
    correct: bool
    classification: str = SCORE_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != GOAL_SCORE_SCHEMA or self.classification != SCORE_CLASSIFICATION:
            raise GoalInferenceBenchmarkError("score schema/classification mismatch")
        _sha("inference_sha256", self.inference_sha256)
        _sha("label_sha256", self.label_sha256)
        if self.identifiability not in _ALLOWED_IDENTIFIABILITY:
            raise GoalInferenceBenchmarkError("score identifiability domain mismatch")
        if self.decision not in _ALLOWED_DECISIONS or self.expected_decision not in _ALLOWED_DECISIONS:
            raise GoalInferenceBenchmarkError("score decision domain mismatch")
        if type(self.correct) is not bool:
            raise GoalInferenceBenchmarkError("correct must be boolean")
        if _origin is not _SCORE_ORIGIN:
            raise GoalInferenceBenchmarkError("GoalInferenceScore must be created by score_goal_inference")


def score_goal_inference(*, run: RunDescriptor, fixture: MicroWorldFixture, state: EpisodeState,
                         observation: ObservationView, candidates: tuple[CandidateGoal, ...],
                         inference: GoalInference, label: EvaluatorGoalLabel) -> GoalInferenceScore:
    if type(fixture) is not MicroWorldFixture or type(state) is not EpisodeState:
        raise GoalInferenceBenchmarkError("fixture/state must be exact concrete evaluator values")
    if type(observation) is not ObservationView:
        raise GoalInferenceBenchmarkError("observation must be exact concrete ObservationView")
    if type(inference) is not GoalInference or type(label) is not EvaluatorGoalLabel:
        raise GoalInferenceBenchmarkError("inference/label must be exact concrete benchmark values")
    expected_observation = observation_for_state(fixture, state)
    if observation != expected_observation:
        raise GoalInferenceBenchmarkError("observation is stale or not evaluator-derived from state")
    _assert_inference_binding(
        run=run,
        fixture=fixture,
        state=state,
        observation=observation,
        candidates=candidates,
        inference=inference,
    )
    candidate_digest = candidate_set_digest(candidates)
    ident_digest = public_identifiability_digest(observation, candidates)
    matches = public_signal_matches(observation, candidates)
    expected_identifiability = IDENTIFIABLE if len(matches) == 1 else NON_IDENTIFIABLE
    if label.run_descriptor_sha256 != run.sha256():
        raise GoalInferenceBenchmarkError("label run descriptor binding mismatch")
    if (label.fixture_sha256, label.state_sha256) != (fixture.sha256(), state.sha256()):
        raise GoalInferenceBenchmarkError("label evaluator fixture/state binding mismatch")
    if (label.observation_sha256, label.candidate_set_sha256) != (observation.sha256(), candidate_digest):
        raise GoalInferenceBenchmarkError("label observation/candidate binding mismatch")
    if (label.public_identifiability_sha256, label.identifiability) != (ident_digest, expected_identifiability):
        raise GoalInferenceBenchmarkError("label public-identifiability binding mismatch")
    if label.sealed_inference_sha256 != inference.sha256():
        raise GoalInferenceBenchmarkError("label is not bound to sealed inference")
    if expected_identifiability == IDENTIFIABLE:
        if label.expected_decision != GOAL or label.expected_goal_id != matches[0]:
            raise GoalInferenceBenchmarkError("identifiable label does not match unique public evidence")
    elif label.expected_decision != ABSTAIN or label.expected_goal_id is not None:
        raise GoalInferenceBenchmarkError("non-identifiable label must remain ABSTAIN")
    correct = inference.choice.decision == label.expected_decision and inference.choice.goal_id == label.expected_goal_id
    return GoalInferenceScore(
        GOAL_SCORE_SCHEMA,
        inference.sha256(),
        label.sha256(),
        label.identifiability,
        inference.choice.decision,
        inference.choice.goal_id,
        label.expected_decision,
        label.expected_goal_id,
        correct,
        _origin=_SCORE_ORIGIN,
    )
