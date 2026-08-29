from __future__ import annotations

from dataclasses import fields, replace
import unittest

from frankenstein2.cognitive_microworld import (
    FIXTURE_SCHEMA,
    ActionSpec,
    MicroWorldFixture,
    ObservationView,
    TransitionRule,
    WorldNode,
    begin_episode,
)
from frankenstein2.cognitive_goal_inference_benchmark import (
    ABSTAIN,
    ABSTAINED,
    CORRECT,
    CORRECT_ABSTAIN,
    GOAL,
    INCORRECT,
    PUBLIC_POLICY_SCHEMA,
    CandidateGoalDescriptor,
    GoalEvaluationCase,
    GoalInference,
    GoalInferenceBenchmarkError,
    GoalInferenceEvaluation,
    PublicGoalInferenceInput,
    PublicPolicyState,
    abstain_baseline,
    abstain_goal,
    evaluate_goal_inference,
    infer_goal,
    lexical_first_baseline,
    matched_public_baselines,
    predeclare_goal_evaluation_case,
    public_goal_input,
)


def _fixture(*, hidden_suffix: str = "base") -> MicroWorldFixture:
    return MicroWorldFixture(
        FIXTURE_SCHEMA,
        "fixture/wp804-heldout-1",
        1,
        "holdout/wp804",
        "n0",
        3,
        (
            ActionSpec("a_observe", "action/observe", "a" * 64),
            ActionSpec("b_wait", "action/wait", "b" * 64),
        ),
        (
            WorldNode("n0", "public/red-object", "1" * 64, f"hidden/red-{hidden_suffix}", "c" * 64, False, 0),
            WorldNode("n1", "public/terminal", "2" * 64, f"hidden/end-{hidden_suffix}", "d" * 64, True, 1),
        ),
        (
            TransitionRule("n0", "a_observe", "n1", f"transition/observe-{hidden_suffix}", "e" * 64),
            TransitionRule("n0", "b_wait", "n0", f"transition/wait-{hidden_suffix}", "f" * 64),
        ),
        "synthetic-heldout",
        ("source/wp804",),
        "donor/none",
        "method/goal-inference",
    )


def _goals() -> tuple[CandidateGoalDescriptor, ...]:
    return (
        CandidateGoalDescriptor("goal/inspect-red", "goal-public/inspect-red", "3" * 64),
        CandidateGoalDescriptor("goal/wait", "goal-public/wait", "4" * 64),
    )


def _episode(*, generation: int = 1, hidden_suffix: str = "base"):
    fixture = _fixture(hidden_suffix=hidden_suffix)
    state, observation = begin_episode(fixture, episode_id="episode/wp804", episode_generation=generation)
    public = public_goal_input(
        observation,
        candidate_goals=_goals(),
        benchmark_run_id="run/wp804-1",
        benchmark_generation=1,
    )
    return fixture, state, observation, public


def _policy(policy_id: str = "policy/test") -> PublicPolicyState:
    return PublicPolicyState(
        PUBLIC_POLICY_SCHEMA,
        policy_id,
        1,
        f"public-policy-state/{policy_id}",
        "5" * 64,
    )


class GoalInferenceBenchmarkTests(unittest.TestCase):
    def test_public_goal_inference_can_match_predeclared_label(self) -> None:
        fixture, state, _, public = _episode()
        case = predeclare_goal_evaluation_case(
            fixture,
            state=state,
            public_input=public,
            case_id="case/wp804-correct",
            expected_goal_id="goal/inspect-red",
            evaluator_evidence_refs=("evaluator/label/red-means-inspect",),
        )
        inference = infer_goal(
            public,
            policy_state=_policy(),
            inference_id="inference/wp804-correct",
            inferred_goal_id="goal/inspect-red",
        )
        evaluation = evaluate_goal_inference(case, public_input=public, inference=inference)
        self.assertEqual(inference.inference_kind, GOAL)
        self.assertEqual(evaluation.outcome, CORRECT)
        self.assertEqual(evaluation.benchmark_score_delta, 1)
        self.assertEqual(evaluation.fixture_sha256, fixture.sha256())

    def test_wrong_public_goal_is_scored_incorrect_not_adopted(self) -> None:
        fixture, state, _, public = _episode()
        case = predeclare_goal_evaluation_case(
            fixture,
            state=state,
            public_input=public,
            case_id="case/wp804-wrong",
            expected_goal_id="goal/wait",
            evaluator_evidence_refs=("evaluator/label/wait",),
        )
        inference = infer_goal(
            public,
            policy_state=_policy(),
            inference_id="inference/wp804-wrong",
            inferred_goal_id="goal/inspect-red",
        )
        evaluation = evaluate_goal_inference(case, public_input=public, inference=inference)
        self.assertEqual(evaluation.outcome, INCORRECT)
        self.assertEqual(evaluation.benchmark_score_delta, -1)
        self.assertNotIn("adopt", repr(evaluation).lower())

    def test_abstain_is_correct_when_evaluator_predeclares_no_unique_goal(self) -> None:
        fixture, state, _, public = _episode()
        case = predeclare_goal_evaluation_case(
            fixture,
            state=state,
            public_input=public,
            case_id="case/wp804-unresolved",
            expected_goal_id=None,
            evaluator_evidence_refs=("evaluator/label/ambiguous-public-evidence",),
        )
        inference = abstain_goal(
            public,
            policy_state=_policy("policy/uncertainty"),
            inference_id="inference/wp804-abstain-correct",
        )
        evaluation = evaluate_goal_inference(case, public_input=public, inference=inference)
        self.assertEqual(inference.inference_kind, ABSTAIN)
        self.assertEqual(evaluation.outcome, CORRECT_ABSTAIN)
        self.assertEqual(evaluation.benchmark_score_delta, 1)

    def test_abstain_remains_valid_without_false_positive_when_goal_label_exists(self) -> None:
        fixture, state, _, public = _episode()
        case = predeclare_goal_evaluation_case(
            fixture,
            state=state,
            public_input=public,
            case_id="case/wp804-abstain-labelled",
            expected_goal_id="goal/wait",
            evaluator_evidence_refs=("evaluator/label/wait",),
        )
        inference = abstain_baseline(public, inference_id="inference/wp804-abstain-labelled")
        evaluation = evaluate_goal_inference(case, public_input=public, inference=inference)
        self.assertEqual(evaluation.outcome, ABSTAINED)
        self.assertEqual(evaluation.benchmark_score_delta, 0)

    def test_lexical_and_abstain_baselines_are_matched_to_exact_public_input(self) -> None:
        _, _, _, public = _episode()
        lexical, abstain = matched_public_baselines(
            public,
            lexical_inference_id="inference/wp804-lexical",
            abstain_inference_id="inference/wp804-abstain",
        )
        self.assertEqual(lexical.public_input_sha256, public.sha256())
        self.assertEqual(abstain.public_input_sha256, public.sha256())
        self.assertEqual(lexical.inferred_goal_id, "goal/inspect-red")
        self.assertEqual(abstain.inference_kind, ABSTAIN)

    def test_lexical_baseline_is_deterministic_for_replayed_public_input(self) -> None:
        _, _, _, public_a = _episode()
        _, _, _, public_b = _episode()
        a = lexical_first_baseline(public_a, inference_id="inference/wp804-replay")
        b = lexical_first_baseline(public_b, inference_id="inference/wp804-replay")
        self.assertEqual(public_a.sha256(), public_b.sha256())
        self.assertEqual(a.sha256(), b.sha256())

    def test_hidden_fixture_mutation_cannot_change_public_policy_input_or_baseline(self) -> None:
        fixture_a, _, observation_a, public_a = _episode(hidden_suffix="a")
        fixture_b, _, observation_b, public_b = _episode(hidden_suffix="b")
        self.assertNotEqual(fixture_a.sha256(), fixture_b.sha256())
        self.assertEqual(fixture_a.public_sha256(), fixture_b.public_sha256())
        self.assertEqual(observation_a, observation_b)
        self.assertEqual(public_a.sha256(), public_b.sha256())
        baseline_a = lexical_first_baseline(public_a, inference_id="inference/wp804-hidden-isolation")
        baseline_b = lexical_first_baseline(public_b, inference_id="inference/wp804-hidden-isolation")
        self.assertEqual(baseline_a.sha256(), baseline_b.sha256())

    def test_public_surfaces_contain_no_evaluator_hidden_fields(self) -> None:
        forbidden = {
            "current_node_id",
            "to_node_id",
            "transition_ref",
            "transition_sha256",
            "hidden_ground_truth_ref",
            "hidden_ground_truth_sha256",
            "evaluator_score",
            "fixture_sha256",
            "expected_goal_id",
            "evaluator_evidence_refs",
        }
        public_fields = {field.name for field in fields(PublicGoalInferenceInput)}
        inference_fields = {field.name for field in fields(GoalInference)}
        candidate_fields = {field.name for field in fields(CandidateGoalDescriptor)}
        self.assertTrue(public_fields.isdisjoint(forbidden))
        self.assertTrue(inference_fields.isdisjoint(forbidden))
        self.assertTrue(candidate_fields.isdisjoint(forbidden))

    def test_evaluator_case_is_factory_only_and_not_reconstructable_as_public_data(self) -> None:
        fixture, state, _, public = _episode()
        case = predeclare_goal_evaluation_case(
            fixture,
            state=state,
            public_input=public,
            case_id="case/wp804-factory",
            expected_goal_id="goal/wait",
            evaluator_evidence_refs=("evaluator/label/wait",),
        )
        self.assertNotIn("expected_goal_id", public.as_dict())
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "predeclared by evaluator API"):
            GoalEvaluationCase(**case.as_dict())

    def test_evaluation_is_factory_only_evaluator_measurement(self) -> None:
        fixture, state, _, public = _episode()
        case = predeclare_goal_evaluation_case(
            fixture,
            state=state,
            public_input=public,
            case_id="case/wp804-eval-factory",
            expected_goal_id="goal/inspect-red",
            evaluator_evidence_refs=("evaluator/label/red",),
        )
        inference = lexical_first_baseline(public, inference_id="inference/wp804-eval-factory")
        evaluation = evaluate_goal_inference(case, public_input=public, inference=inference)
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "created by evaluator API"):
            GoalInferenceEvaluation(**evaluation.as_dict())

    def test_inference_rejects_goal_outside_exact_public_candidate_set(self) -> None:
        _, _, _, public = _episode()
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "not an admitted public candidate"):
            infer_goal(
                public,
                policy_state=_policy(),
                inference_id="inference/wp804-hidden-goal",
                inferred_goal_id="goal/evaluator-only-secret",
            )

    def test_generation_and_observation_provenance_mismatch_fails_closed(self) -> None:
        fixture, state, _, public = _episode(generation=1)
        case = predeclare_goal_evaluation_case(
            fixture,
            state=state,
            public_input=public,
            case_id="case/wp804-generation",
            expected_goal_id="goal/inspect-red",
            evaluator_evidence_refs=("evaluator/label/red",),
        )
        _, _, _, public_generation_2 = _episode(generation=2)
        stale = lexical_first_baseline(public_generation_2, inference_id="inference/wp804-generation")
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "provenance mismatch"):
            evaluate_goal_inference(case, public_input=public, inference=stale)

    def test_public_input_digest_mismatch_fails_closed_before_label_scoring(self) -> None:
        fixture, state, _, public = _episode()
        case = predeclare_goal_evaluation_case(
            fixture,
            state=state,
            public_input=public,
            case_id="case/wp804-input-mismatch",
            expected_goal_id="goal/wait",
            evaluator_evidence_refs=("evaluator/label/wait",),
        )
        altered_goals = (
            CandidateGoalDescriptor("goal/inspect-red", "goal-public/inspect-red-v2", "6" * 64),
            CandidateGoalDescriptor("goal/wait", "goal-public/wait", "4" * 64),
        )
        altered_public = public_goal_input(
            _episode()[2],
            candidate_goals=altered_goals,
            benchmark_run_id="run/wp804-1",
            benchmark_generation=1,
        )
        inference = lexical_first_baseline(altered_public, inference_id="inference/wp804-input-mismatch")
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "evaluation-case/public-input provenance mismatch"):
            evaluate_goal_inference(case, public_input=altered_public, inference=inference)

    def test_exact_concrete_observation_and_descriptor_subtypes_are_rejected(self) -> None:
        class EvilObservation(ObservationView):
            pass

        class EvilGoal(CandidateGoalDescriptor):
            pass

        _, _, observation, _ = _episode()
        evil_observation = EvilObservation(**observation.as_dict())
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "exact concrete ObservationView"):
            public_goal_input(
                evil_observation,
                candidate_goals=_goals(),
                benchmark_run_id="run/wp804-evil-observation",
                benchmark_generation=1,
            )
        evil_goal = EvilGoal("goal/evil", "goal-public/evil", "7" * 64)
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "exact concrete CandidateGoalDescriptor"):
            public_goal_input(
                observation,
                candidate_goals=(evil_goal,),
                benchmark_run_id="run/wp804-evil-goal",
                benchmark_generation=1,
            )

    def test_exact_concrete_policy_state_is_required(self) -> None:
        class EvilPolicy(PublicPolicyState):
            pass

        _, _, _, public = _episode()
        evil = EvilPolicy(
            PUBLIC_POLICY_SCHEMA,
            "policy/evil",
            1,
            "public-policy-state/evil",
            "8" * 64,
        )
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "exact concrete PublicPolicyState"):
            infer_goal(
                public,
                policy_state=evil,
                inference_id="inference/wp804-evil-policy",
                inferred_goal_id="goal/wait",
            )

    def test_manual_provenance_tamper_is_rejected_even_when_goal_label_matches(self) -> None:
        fixture, state, _, public = _episode()
        case = predeclare_goal_evaluation_case(
            fixture,
            state=state,
            public_input=public,
            case_id="case/wp804-tamper",
            expected_goal_id="goal/inspect-red",
            evaluator_evidence_refs=("evaluator/label/red",),
        )
        inference = lexical_first_baseline(public, inference_id="inference/wp804-tamper")
        tampered = replace(inference, observation_sha256="9" * 64)
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "provenance mismatch"):
            evaluate_goal_inference(case, public_input=public, inference=tampered)


if __name__ == "__main__":
    unittest.main()
