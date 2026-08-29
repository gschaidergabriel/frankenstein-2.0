"""F2-WP-804 deterministic held-out goal-inference benchmark.

The system-under-test receives only an exact public ``ObservationView``, immutable public
candidate-goal descriptors, and immutable public policy-state metadata. Evaluator-only
MicroWorldFixture nodes/transitions/scores/ground-truth and predeclared goal labels remain
behind a separate sealed evaluation-case boundary.

A benchmark label match is synthetic repository evaluation evidence only. It never adopts a
GoalContract, mutates UnifiedDB, authorizes an effect, proves runtime/GRID/GWT/J-Space
behavior, grants training credit, or establishes whole-system acceptance.
"""
from __future__ import annotations

from dataclasses import InitVar, asdict, dataclass
import hashlib
import json
import re
from typing import Any

from .cognitive_microworld import (
    EpisodeState,
    MicroWorldFixture,
    ObservationView,
    observation_for_state,
)

PUBLIC_INPUT_SCHEMA = "FRANKENSTEIN2_HELDOUT_GOAL_INFERENCE_PUBLIC_INPUT/v1"
PUBLIC_POLICY_SCHEMA = "FRANKENSTEIN2_HELDOUT_GOAL_INFERENCE_POLICY_STATE/v1"
INFERENCE_SCHEMA = "FRANKENSTEIN2_HELDOUT_GOAL_INFERENCE/v1"
EVALUATION_CASE_SCHEMA = "FRANKENSTEIN2_HELDOUT_GOAL_INFERENCE_CASE/v1"
EVALUATION_SCHEMA = "FRANKENSTEIN2_HELDOUT_GOAL_INFERENCE_EVALUATION/v1"

PUBLIC_CLASSIFICATION = "PUBLIC_OBSERVATION_AND_CANDIDATE_DESCRIPTOR_INPUT_NO_GOAL_AUTHORITY"
PUBLIC_POLICY_CLASSIFICATION = "PUBLIC_IMMUTABLE_POLICY_STATE_NO_GOAL_AUTHORITY"
INFERENCE_CLASSIFICATION = "PUBLIC_POLICY_OUTPUT_BENCHMARK_CANDIDATE_NO_GOAL_AUTHORITY"
EVALUATOR_CLASSIFICATION = "EVALUATOR_ONLY_PREDECLARED_LABEL_NOT_SUT_INPUT_OR_GOAL_AUTHORITY"
EVALUATION_CLASSIFICATION = "EVALUATOR_ONLY_BENCHMARK_MEASUREMENT_NOT_GOAL_AUTHORITY"

GOAL = "GOAL"
ABSTAIN = "ABSTAIN"
LABEL_GOAL = "LABEL_GOAL"
LABEL_UNRESOLVED = "LABEL_UNRESOLVED"
CORRECT = "CORRECT"
INCORRECT = "INCORRECT"
CORRECT_ABSTAIN = "CORRECT_ABSTAIN"
ABSTAINED = "ABSTAINED"

_ALLOWED_INFERENCE_KINDS = frozenset((GOAL, ABSTAIN))
_ALLOWED_LABEL_KINDS = frozenset((LABEL_GOAL, LABEL_UNRESOLVED))
_ALLOWED_OUTCOMES = frozenset((CORRECT, INCORRECT, CORRECT_ABSTAIN, ABSTAINED))
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_GENERATION = 1_000_000
_MAX_REFS = 4096
_CASE_ORIGIN = object()
_EVALUATION_ORIGIN = object()


class GoalInferenceBenchmarkError(ValueError):
    pass


def _id(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise GoalInferenceBenchmarkError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise GoalInferenceBenchmarkError(f"{name} is outside the identifier domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise GoalInferenceBenchmarkError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_GENERATION:
        raise GoalInferenceBenchmarkError(f"{name} must be a bounded non-negative integer")
    return value


def _refs(name: str, values: Any, *, nonempty: bool = False) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GoalInferenceBenchmarkError(f"{name} must be an immutable tuple")
    if len(values) > _MAX_REFS:
        raise GoalInferenceBenchmarkError(f"{name} exceeds reference ceiling")
    out = tuple(_id(f"{name} item", value) for value in values)
    if nonempty and not out:
        raise GoalInferenceBenchmarkError(f"{name} must not be empty")
    if len(out) != len(set(out)):
        raise GoalInferenceBenchmarkError(f"{name} contains duplicate references")
    if out != tuple(sorted(out)):
        raise GoalInferenceBenchmarkError(f"{name} must be in canonical lexical order")
    return out


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class CandidateGoalDescriptor:
    """Explicit public candidate descriptor; no evaluator or adoption fields exist here."""

    goal_id: str
    public_descriptor_ref: str
    public_descriptor_sha256: str

    def __post_init__(self) -> None:
        _id("goal_id", self.goal_id)
        _id("public_descriptor_ref", self.public_descriptor_ref)
        _sha("public_descriptor_sha256", self.public_descriptor_sha256)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class PublicPolicyState:
    schema: str
    policy_id: str
    policy_generation: int
    public_state_ref: str
    public_state_sha256: str
    classification: str = PUBLIC_POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != PUBLIC_POLICY_SCHEMA or self.classification != PUBLIC_POLICY_CLASSIFICATION:
            raise GoalInferenceBenchmarkError("policy-state schema/classification mismatch")
        _id("policy_id", self.policy_id)
        _generation("policy_generation", self.policy_generation)
        _id("public_state_ref", self.public_state_ref)
        _sha("public_state_sha256", self.public_state_sha256)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class PublicGoalInferenceInput:
    schema: str
    benchmark_run_id: str
    benchmark_generation: int
    episode_id: str
    episode_generation: int
    fixture_id: str
    fixture_generation: int
    public_fixture_sha256: str
    step_index: int
    observation_ref: str
    observation_payload_sha256: str
    observation_sha256: str
    available_action_ids: tuple[str, ...]
    terminal: bool
    candidate_goals: tuple[CandidateGoalDescriptor, ...]
    classification: str = PUBLIC_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != PUBLIC_INPUT_SCHEMA or self.classification != PUBLIC_CLASSIFICATION:
            raise GoalInferenceBenchmarkError("public-input schema/classification mismatch")
        for name, value in (
            ("benchmark_run_id", self.benchmark_run_id),
            ("episode_id", self.episode_id),
            ("fixture_id", self.fixture_id),
            ("observation_ref", self.observation_ref),
        ):
            _id(name, value)
        _generation("benchmark_generation", self.benchmark_generation)
        _generation("episode_generation", self.episode_generation)
        _generation("fixture_generation", self.fixture_generation)
        if type(self.step_index) is not int or self.step_index < 0:
            raise GoalInferenceBenchmarkError("step_index must be a non-negative integer")
        for name, value in (
            ("public_fixture_sha256", self.public_fixture_sha256),
            ("observation_payload_sha256", self.observation_payload_sha256),
            ("observation_sha256", self.observation_sha256),
        ):
            _sha(name, value)
        _refs("available_action_ids", self.available_action_ids, nonempty=True)
        if type(self.terminal) is not bool:
            raise GoalInferenceBenchmarkError("terminal must be a boolean")
        if type(self.candidate_goals) is not tuple or not self.candidate_goals:
            raise GoalInferenceBenchmarkError("candidate_goals must be a non-empty immutable tuple")
        if any(type(goal) is not CandidateGoalDescriptor for goal in self.candidate_goals):
            raise GoalInferenceBenchmarkError("candidate_goals require exact concrete CandidateGoalDescriptor values")
        if self.candidate_goals != tuple(sorted(self.candidate_goals, key=lambda goal: goal.goal_id)):
            raise GoalInferenceBenchmarkError("candidate_goals must be in canonical goal_id order")
        goal_ids = tuple(goal.goal_id for goal in self.candidate_goals)
        if len(goal_ids) != len(set(goal_ids)):
            raise GoalInferenceBenchmarkError("candidate goal_id values must be unique")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "benchmark_run_id": self.benchmark_run_id,
            "benchmark_generation": self.benchmark_generation,
            "episode_id": self.episode_id,
            "episode_generation": self.episode_generation,
            "fixture_id": self.fixture_id,
            "fixture_generation": self.fixture_generation,
            "public_fixture_sha256": self.public_fixture_sha256,
            "step_index": self.step_index,
            "observation_ref": self.observation_ref,
            "observation_payload_sha256": self.observation_payload_sha256,
            "observation_sha256": self.observation_sha256,
            "available_action_ids": list(self.available_action_ids),
            "terminal": self.terminal,
            "candidate_goals": [goal.as_dict() for goal in self.candidate_goals],
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def candidate_goal_ids(self) -> tuple[str, ...]:
        return tuple(goal.goal_id for goal in self.candidate_goals)


@dataclass(frozen=True, slots=True)
class GoalInference:
    schema: str
    inference_id: str
    benchmark_run_id: str
    benchmark_generation: int
    policy_id: str
    policy_generation: int
    policy_state_sha256: str
    public_input_sha256: str
    episode_id: str
    episode_generation: int
    fixture_id: str
    fixture_generation: int
    observation_sha256: str
    inference_kind: str
    inferred_goal_id: str | None
    classification: str = INFERENCE_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != INFERENCE_SCHEMA or self.classification != INFERENCE_CLASSIFICATION:
            raise GoalInferenceBenchmarkError("inference schema/classification mismatch")
        for name, value in (
            ("inference_id", self.inference_id),
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
        _sha("policy_state_sha256", self.policy_state_sha256)
        _sha("public_input_sha256", self.public_input_sha256)
        _sha("observation_sha256", self.observation_sha256)
        if self.inference_kind not in _ALLOWED_INFERENCE_KINDS:
            raise GoalInferenceBenchmarkError("inference_kind is not admitted")
        if self.inference_kind == ABSTAIN:
            if self.inferred_goal_id is not None:
                raise GoalInferenceBenchmarkError("ABSTAIN must not carry inferred_goal_id")
        else:
            _id("inferred_goal_id", self.inferred_goal_id)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class GoalEvaluationCase:
    schema: str
    case_id: str
    benchmark_run_id: str
    benchmark_generation: int
    public_input_sha256: str
    fixture_id: str
    fixture_generation: int
    fixture_sha256: str
    episode_id: str
    episode_generation: int
    observation_sha256: str
    label_kind: str
    expected_goal_id: str | None
    evaluator_evidence_refs: tuple[str, ...]
    classification: str = EVALUATOR_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != EVALUATION_CASE_SCHEMA or self.classification != EVALUATOR_CLASSIFICATION:
            raise GoalInferenceBenchmarkError("evaluation-case schema/classification mismatch")
        for name, value in (
            ("case_id", self.case_id),
            ("benchmark_run_id", self.benchmark_run_id),
            ("fixture_id", self.fixture_id),
            ("episode_id", self.episode_id),
        ):
            _id(name, value)
        _generation("benchmark_generation", self.benchmark_generation)
        _generation("fixture_generation", self.fixture_generation)
        _generation("episode_generation", self.episode_generation)
        _sha("public_input_sha256", self.public_input_sha256)
        _sha("fixture_sha256", self.fixture_sha256)
        _sha("observation_sha256", self.observation_sha256)
        if self.label_kind not in _ALLOWED_LABEL_KINDS:
            raise GoalInferenceBenchmarkError("label_kind is not admitted")
        if self.label_kind == LABEL_UNRESOLVED:
            if self.expected_goal_id is not None:
                raise GoalInferenceBenchmarkError("unresolved label must not carry expected_goal_id")
        else:
            _id("expected_goal_id", self.expected_goal_id)
        _refs("evaluator_evidence_refs", self.evaluator_evidence_refs, nonempty=True)
        if _origin is not _CASE_ORIGIN:
            raise GoalInferenceBenchmarkError("GoalEvaluationCase must be predeclared by evaluator API")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class GoalInferenceEvaluation:
    schema: str
    case_id: str
    case_sha256: str
    benchmark_run_id: str
    benchmark_generation: int
    inference_id: str
    inference_sha256: str
    public_input_sha256: str
    fixture_id: str
    fixture_generation: int
    fixture_sha256: str
    episode_id: str
    episode_generation: int
    observation_sha256: str
    outcome: str
    benchmark_score_delta: int
    classification: str = EVALUATION_CLASSIFICATION
    _origin: InitVar[object | None] = None

    def __post_init__(self, _origin: object | None) -> None:
        if self.schema != EVALUATION_SCHEMA or self.classification != EVALUATION_CLASSIFICATION:
            raise GoalInferenceBenchmarkError("evaluation schema/classification mismatch")
        for name, value in (
            ("case_id", self.case_id),
            ("benchmark_run_id", self.benchmark_run_id),
            ("inference_id", self.inference_id),
            ("fixture_id", self.fixture_id),
            ("episode_id", self.episode_id),
        ):
            _id(name, value)
        _generation("benchmark_generation", self.benchmark_generation)
        _generation("fixture_generation", self.fixture_generation)
        _generation("episode_generation", self.episode_generation)
        for name, value in (
            ("case_sha256", self.case_sha256),
            ("inference_sha256", self.inference_sha256),
            ("public_input_sha256", self.public_input_sha256),
            ("fixture_sha256", self.fixture_sha256),
            ("observation_sha256", self.observation_sha256),
        ):
            _sha(name, value)
        if self.outcome not in _ALLOWED_OUTCOMES:
            raise GoalInferenceBenchmarkError("evaluation outcome is not admitted")
        expected_score = {
            CORRECT: 1,
            INCORRECT: -1,
            CORRECT_ABSTAIN: 1,
            ABSTAINED: 0,
        }[self.outcome]
        if type(self.benchmark_score_delta) is not int or self.benchmark_score_delta != expected_score:
            raise GoalInferenceBenchmarkError("benchmark score/outcome mismatch")
        if _origin is not _EVALUATION_ORIGIN:
            raise GoalInferenceBenchmarkError("GoalInferenceEvaluation must be created by evaluator API")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def public_goal_input(
    observation: ObservationView,
    *,
    candidate_goals: tuple[CandidateGoalDescriptor, ...],
    benchmark_run_id: str,
    benchmark_generation: int,
) -> PublicGoalInferenceInput:
    """Compile the only observation/candidate surface admitted to tested policies."""
    if type(observation) is not ObservationView:
        raise GoalInferenceBenchmarkError("observation must be exact concrete ObservationView")
    if type(candidate_goals) is not tuple or any(type(goal) is not CandidateGoalDescriptor for goal in candidate_goals):
        raise GoalInferenceBenchmarkError("candidate_goals require exact concrete CandidateGoalDescriptor values")
    return PublicGoalInferenceInput(
        PUBLIC_INPUT_SCHEMA,
        benchmark_run_id,
        benchmark_generation,
        observation.episode_id,
        observation.episode_generation,
        observation.fixture_id,
        observation.fixture_generation,
        observation.public_fixture_sha256,
        observation.step_index,
        observation.observation_ref,
        observation.observation_sha256,
        observation.sha256(),
        observation.available_action_ids,
        observation.terminal,
        candidate_goals,
    )


def _assert_exact_public_inputs(public_input: PublicGoalInferenceInput, policy_state: PublicPolicyState) -> None:
    if type(public_input) is not PublicGoalInferenceInput:
        raise GoalInferenceBenchmarkError("public_input must be exact concrete PublicGoalInferenceInput")
    if type(policy_state) is not PublicPolicyState:
        raise GoalInferenceBenchmarkError("policy_state must be exact concrete PublicPolicyState")


def infer_goal(
    public_input: PublicGoalInferenceInput,
    *,
    policy_state: PublicPolicyState,
    inference_id: str,
    inferred_goal_id: str,
) -> GoalInference:
    """Seal a public-only goal candidate; this does not adopt or authorize the goal."""
    _assert_exact_public_inputs(public_input, policy_state)
    _id("inferred_goal_id", inferred_goal_id)
    if inferred_goal_id not in set(public_input.candidate_goal_ids()):
        raise GoalInferenceBenchmarkError("inferred_goal_id is not an admitted public candidate")
    return GoalInference(
        INFERENCE_SCHEMA,
        inference_id,
        public_input.benchmark_run_id,
        public_input.benchmark_generation,
        policy_state.policy_id,
        policy_state.policy_generation,
        policy_state.sha256(),
        public_input.sha256(),
        public_input.episode_id,
        public_input.episode_generation,
        public_input.fixture_id,
        public_input.fixture_generation,
        public_input.observation_sha256,
        GOAL,
        inferred_goal_id,
    )


def abstain_goal(
    public_input: PublicGoalInferenceInput,
    *,
    policy_state: PublicPolicyState,
    inference_id: str,
) -> GoalInference:
    """Seal UNKNOWN/ABSTAIN when the public evidence cannot discriminate candidates."""
    _assert_exact_public_inputs(public_input, policy_state)
    return GoalInference(
        INFERENCE_SCHEMA,
        inference_id,
        public_input.benchmark_run_id,
        public_input.benchmark_generation,
        policy_state.policy_id,
        policy_state.policy_generation,
        policy_state.sha256(),
        public_input.sha256(),
        public_input.episode_id,
        public_input.episode_generation,
        public_input.fixture_id,
        public_input.fixture_generation,
        public_input.observation_sha256,
        ABSTAIN,
        None,
    )


def lexical_first_baseline(
    public_input: PublicGoalInferenceInput,
    *,
    inference_id: str,
    policy_generation: int = 1,
) -> GoalInference:
    """Deterministic public-information baseline: lexical first candidate, no hidden state."""
    if type(public_input) is not PublicGoalInferenceInput:
        raise GoalInferenceBenchmarkError("public_input must be exact concrete PublicGoalInferenceInput")
    policy = PublicPolicyState(
        PUBLIC_POLICY_SCHEMA,
        "PUBLIC_LEXICAL_FIRST_BASELINE",
        policy_generation,
        "policy/lexical-first/no-hidden-state",
        "1" * 64,
    )
    return infer_goal(
        public_input,
        policy_state=policy,
        inference_id=inference_id,
        inferred_goal_id=public_input.candidate_goal_ids()[0],
    )


def abstain_baseline(
    public_input: PublicGoalInferenceInput,
    *,
    inference_id: str,
    policy_generation: int = 1,
) -> GoalInference:
    """Deterministic public-information baseline that always preserves uncertainty."""
    if type(public_input) is not PublicGoalInferenceInput:
        raise GoalInferenceBenchmarkError("public_input must be exact concrete PublicGoalInferenceInput")
    policy = PublicPolicyState(
        PUBLIC_POLICY_SCHEMA,
        "PUBLIC_ALWAYS_ABSTAIN_BASELINE",
        policy_generation,
        "policy/always-abstain/no-hidden-state",
        "2" * 64,
    )
    return abstain_goal(public_input, policy_state=policy, inference_id=inference_id)


def matched_public_baselines(
    public_input: PublicGoalInferenceInput,
    *,
    lexical_inference_id: str,
    abstain_inference_id: str,
) -> tuple[GoalInference, GoalInference]:
    """Return two deterministic baselines bound to the exact same public input digest."""
    lexical = lexical_first_baseline(public_input, inference_id=lexical_inference_id)
    abstain = abstain_baseline(public_input, inference_id=abstain_inference_id)
    if lexical.public_input_sha256 != abstain.public_input_sha256:
        raise GoalInferenceBenchmarkError("matched baselines do not share exact public input")
    return lexical, abstain


def predeclare_goal_evaluation_case(
    fixture: MicroWorldFixture,
    *,
    state: EpisodeState,
    public_input: PublicGoalInferenceInput,
    case_id: str,
    expected_goal_id: str | None,
    evaluator_evidence_refs: tuple[str, ...],
) -> GoalEvaluationCase:
    """Seal evaluator-only labels before policy output; hidden fixture state stays private."""
    if type(fixture) is not MicroWorldFixture or type(state) is not EpisodeState:
        raise GoalInferenceBenchmarkError("fixture/state must be exact concrete WP800 values")
    if type(public_input) is not PublicGoalInferenceInput:
        raise GoalInferenceBenchmarkError("public_input must be exact concrete PublicGoalInferenceInput")
    current = observation_for_state(fixture, state)
    expected_public = public_goal_input(
        current,
        candidate_goals=public_input.candidate_goals,
        benchmark_run_id=public_input.benchmark_run_id,
        benchmark_generation=public_input.benchmark_generation,
    )
    if expected_public.sha256() != public_input.sha256():
        raise GoalInferenceBenchmarkError("public input does not match exact WP800 fixture/state observation")
    if expected_goal_id is None:
        label_kind = LABEL_UNRESOLVED
    else:
        _id("expected_goal_id", expected_goal_id)
        if expected_goal_id not in set(public_input.candidate_goal_ids()):
            raise GoalInferenceBenchmarkError("expected_goal_id is not an admitted public candidate")
        label_kind = LABEL_GOAL
    return GoalEvaluationCase(
        EVALUATION_CASE_SCHEMA,
        case_id,
        public_input.benchmark_run_id,
        public_input.benchmark_generation,
        public_input.sha256(),
        fixture.fixture_id,
        fixture.generation,
        fixture.sha256(),
        state.episode_id,
        state.episode_generation,
        current.sha256(),
        label_kind,
        expected_goal_id,
        evaluator_evidence_refs,
        _origin=_CASE_ORIGIN,
    )


def evaluate_goal_inference(
    evaluation_case: GoalEvaluationCase,
    *,
    public_input: PublicGoalInferenceInput,
    inference: GoalInference,
) -> GoalInferenceEvaluation:
    """Score a sealed inference against a separately predeclared evaluator-only label."""
    if type(evaluation_case) is not GoalEvaluationCase:
        raise GoalInferenceBenchmarkError("evaluation_case must be exact concrete GoalEvaluationCase")
    if type(public_input) is not PublicGoalInferenceInput:
        raise GoalInferenceBenchmarkError("public_input must be exact concrete PublicGoalInferenceInput")
    if type(inference) is not GoalInference:
        raise GoalInferenceBenchmarkError("inference must be exact concrete GoalInference")
    if public_input.sha256() != evaluation_case.public_input_sha256:
        raise GoalInferenceBenchmarkError("evaluation-case/public-input provenance mismatch")
    expected_inference = (
        public_input.benchmark_run_id,
        public_input.benchmark_generation,
        public_input.sha256(),
        public_input.episode_id,
        public_input.episode_generation,
        public_input.fixture_id,
        public_input.fixture_generation,
        public_input.observation_sha256,
    )
    actual_inference = (
        inference.benchmark_run_id,
        inference.benchmark_generation,
        inference.public_input_sha256,
        inference.episode_id,
        inference.episode_generation,
        inference.fixture_id,
        inference.fixture_generation,
        inference.observation_sha256,
    )
    if actual_inference != expected_inference:
        raise GoalInferenceBenchmarkError("inference/public-input provenance mismatch")
    if inference.inference_kind == GOAL and inference.inferred_goal_id not in set(public_input.candidate_goal_ids()):
        raise GoalInferenceBenchmarkError("inference selected goal outside exact public candidate set")

    if evaluation_case.label_kind == LABEL_UNRESOLVED:
        if inference.inference_kind == ABSTAIN:
            outcome = CORRECT_ABSTAIN
        else:
            outcome = INCORRECT
    elif inference.inference_kind == ABSTAIN:
        outcome = ABSTAINED
    elif inference.inferred_goal_id == evaluation_case.expected_goal_id:
        outcome = CORRECT
    else:
        outcome = INCORRECT

    score = {CORRECT: 1, INCORRECT: -1, CORRECT_ABSTAIN: 1, ABSTAINED: 0}[outcome]
    return GoalInferenceEvaluation(
        EVALUATION_SCHEMA,
        evaluation_case.case_id,
        evaluation_case.sha256(),
        evaluation_case.benchmark_run_id,
        evaluation_case.benchmark_generation,
        inference.inference_id,
        inference.sha256(),
        public_input.sha256(),
        evaluation_case.fixture_id,
        evaluation_case.fixture_generation,
        evaluation_case.fixture_sha256,
        evaluation_case.episode_id,
        evaluation_case.episode_generation,
        evaluation_case.observation_sha256,
        outcome,
        score,
        _origin=_EVALUATION_ORIGIN,
    )
