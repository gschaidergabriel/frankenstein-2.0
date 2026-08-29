from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from frankenstein2.cognitive_goal_inference_benchmark import (
    ABSTAIN,
    CANDIDATE_GOAL_SCHEMA,
    EVALUATOR_CLASSIFICATION,
    GOAL,
    GOAL_LABEL_SCHEMA,
    CandidateGoal,
    EvaluatorGoalLabel,
    GoalChoice,
    GoalInferenceBenchmarkError,
    always_abstain_policy,
    canonical_first_policy,
    candidate_set_digest,
    run_goal_inference,
    score_goal_inference,
    seal_evaluator_goal_label,
    unique_public_signal_policy,
)
from frankenstein2.cognitive_microworld import (
    BASELINE,
    FIXTURE_SCHEMA,
    ActionSpec,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
    TransitionRule,
    WorldNode,
    begin_episode,
)


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fixture() -> MicroWorldFixture:
    return MicroWorldFixture(
        schema=FIXTURE_SCHEMA,
        fixture_id="heldout.goal-inference.001",
        generation=1,
        holdout_set_id="goal-inference.v1",
        initial_node_id="evaluator-node-start",
        max_steps=2,
        actions=(
            ActionSpec("inspect", "action:inspect", h("inspect")),
            ActionSpec("wait", "action:wait", h("wait")),
        ),
        nodes=(
            WorldNode(
                "evaluator-node-start",
                "obs:needs-blue",
                h("needs-blue"),
                "ground-truth:goal-blue",
                h("gt-goal-blue"),
                False,
                0,
            ),
            WorldNode(
                "evaluator-node-terminal",
                "obs:done",
                h("done"),
                "ground-truth:done",
                h("gt-done"),
                True,
                1,
            ),
        ),
        transitions=(
            TransitionRule(
                "evaluator-node-start",
                "inspect",
                "evaluator-node-terminal",
                "t:start:inspect",
                h("start-inspect"),
            ),
            TransitionRule(
                "evaluator-node-start",
                "wait",
                "evaluator-node-start",
                "t:start:wait",
                h("start-wait"),
            ),
        ),
        evidence_source_family="synthetic-heldout",
        primary_source_ids=("wp804-fixture-design-v1",),
        donor_path_family="none-synthetic",
        method_family="deterministic-goal-inference",
    )


def goals(*, ambiguous: bool = False) -> tuple[CandidateGoal, ...]:
    blue_signals = ("obs:needs-blue",)
    red_signals = ("obs:needs-blue",) if ambiguous else ("obs:needs-red",)
    return (
        CandidateGoal(
            CANDIDATE_GOAL_SCHEMA,
            "goal-blue",
            "goal:blue",
            h("goal-blue"),
            blue_signals,
        ),
        CandidateGoal(
            CANDIDATE_GOAL_SCHEMA,
            "goal-red",
            "goal:red",
            h("goal-red"),
            red_signals,
        ),
    )


def run(f: MicroWorldFixture, *, sut: str = "sut:goal-policy") -> RunDescriptor:
    return RunDescriptor.for_fixture(
        f,
        run_id="run:wp804:001",
        condition=BASELINE,
        episode_family_id="ep-family:wp804",
        system_under_test_ref=sut,
        communication_before_result=False,
        independent_reproduction=False,
    )


class CognitiveGoalInferenceBenchmarkTests(unittest.TestCase):
    def test_policy_boundary_contains_only_public_observation_and_candidates(self) -> None:
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep-1", episode_generation=0)
        seen: dict[str, object] = {}

        def spy(observation: ObservationView, candidates: tuple[CandidateGoal, ...]) -> GoalChoice:
            seen["observation"] = observation.as_dict()
            seen["candidates"] = tuple(item.as_dict() for item in candidates)
            return GoalChoice.abstain(public_reason_refs=("policy:no-leak",))

        inference = run_goal_inference(
            policy=spy,
            run=run(f),
            fixture=f,
            observation=obs,
            candidates=goals(),
        )
        public = seen["observation"]
        self.assertIsInstance(public, dict)
        for forbidden in (
            "current_node_id",
            "fixture_sha256",
            "cumulative_score",
            "hidden_ground_truth_ref",
            "evaluator_score",
            "expected_goal_id",
        ):
            self.assertNotIn(forbidden, public)
        self.assertEqual(inference.choice.decision, ABSTAIN)
        self.assertEqual(state.current_node_id, "evaluator-node-start")

    def test_unique_public_signal_selects_goal_and_scores_correct(self) -> None:
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep-2", episode_generation=3)
        candidates = goals()
        inference = run_goal_inference(
            policy=unique_public_signal_policy,
            run=run(f),
            fixture=f,
            observation=obs,
            candidates=candidates,
        )
        label = seal_evaluator_goal_label(
            fixture=f,
            state=state,
            candidates=candidates,
            expected_goal_id="goal-blue",
            label_ref="label:heldout:blue",
            label_sha256=h("label-blue"),
        )
        score = score_goal_inference(
            fixture=f,
            state=state,
            observation=obs,
            candidates=candidates,
            inference=inference,
            label=label,
        )
        self.assertEqual(inference.choice.decision, GOAL)
        self.assertEqual(inference.choice.goal_id, "goal-blue")
        self.assertTrue(score.correct)
        self.assertIn("NO_GOAL_ADOPTION_AUTHORITY", score.classification)

    def test_ambiguous_public_signal_preserves_abstention(self) -> None:
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep-3", episode_generation=0)
        candidates = goals(ambiguous=True)
        inference = run_goal_inference(
            policy=unique_public_signal_policy,
            run=run(f),
            fixture=f,
            observation=obs,
            candidates=candidates,
        )
        label = seal_evaluator_goal_label(
            fixture=f,
            state=state,
            candidates=candidates,
            expected_goal_id=None,
            label_ref="label:heldout:ambiguous",
            label_sha256=h("label-ambiguous"),
        )
        score = score_goal_inference(
            fixture=f,
            state=state,
            observation=obs,
            candidates=candidates,
            inference=inference,
            label=label,
        )
        self.assertEqual(inference.choice.decision, ABSTAIN)
        self.assertIsNone(inference.choice.goal_id)
        self.assertTrue(score.correct)

    def test_public_signal_baseline_can_beat_canonical_first_without_hidden_input(self) -> None:
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep-4", episode_generation=0)
        candidates = (
            CandidateGoal(CANDIDATE_GOAL_SCHEMA, "goal-a-red", "goal:red", h("red"), ("obs:needs-red",)),
            CandidateGoal(CANDIDATE_GOAL_SCHEMA, "goal-z-blue", "goal:blue", h("blue"), ("obs:needs-blue",)),
        )
        baseline = run_goal_inference(
            policy=canonical_first_policy,
            run=run(f, sut="baseline:canonical-first"),
            fixture=f,
            observation=obs,
            candidates=candidates,
        )
        signal = run_goal_inference(
            policy=unique_public_signal_policy,
            run=run(f, sut="baseline:public-signal"),
            fixture=f,
            observation=obs,
            candidates=candidates,
        )
        label = seal_evaluator_goal_label(
            fixture=f,
            state=state,
            candidates=candidates,
            expected_goal_id="goal-z-blue",
            label_ref="label:heldout:z-blue",
            label_sha256=h("label-z-blue"),
        )
        base_score = score_goal_inference(
            fixture=f, state=state, observation=obs, candidates=candidates, inference=baseline, label=label
        )
        signal_score = score_goal_inference(
            fixture=f, state=state, observation=obs, candidates=candidates, inference=signal, label=label
        )
        self.assertFalse(base_score.correct)
        self.assertTrue(signal_score.correct)

    def test_hidden_fixture_mutation_does_not_change_public_policy_output(self) -> None:
        f1 = fixture()
        _, obs1 = begin_episode(f1, episode_id="ep-5", episode_generation=0)
        nodes = list(f1.nodes)
        nodes[0] = replace(nodes[0], hidden_ground_truth_ref="ground-truth:other")
        f2 = replace(f1, nodes=tuple(nodes))
        _, obs2 = begin_episode(f2, episode_id="ep-5", episode_generation=0)
        self.assertEqual(obs1, obs2)
        self.assertEqual(f1.public_sha256(), f2.public_sha256())
        self.assertNotEqual(f1.sha256(), f2.sha256())
        c = goals()
        i1 = run_goal_inference(policy=unique_public_signal_policy, run=run(f1), fixture=f1, observation=obs1, candidates=c)
        i2 = run_goal_inference(policy=unique_public_signal_policy, run=run(f2), fixture=f2, observation=obs2, candidates=c)
        self.assertEqual(i1.choice, i2.choice)
        self.assertNotEqual(i1.run_descriptor_sha256, i2.run_descriptor_sha256)

    def test_candidate_set_requires_exact_concrete_unique_canonical_values(self) -> None:
        c = goals()
        self.assertEqual(len(candidate_set_digest(c)), 64)
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "canonical goal_id order"):
            candidate_set_digest(tuple(reversed(c)))
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "goal_id values must be unique"):
            candidate_set_digest((c[0], replace(c[1], goal_id=c[0].goal_id)))

        class EvilCandidate(CandidateGoal):
            pass

        evil = EvilCandidate(CANDIDATE_GOAL_SCHEMA, c[0].goal_id, c[0].public_goal_ref, c[0].public_goal_sha256, c[0].public_signal_refs)
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "exact concrete CandidateGoal"):
            candidate_set_digest((evil, c[1]))

    def test_observation_subclass_and_unknown_goal_output_are_rejected(self) -> None:
        f = fixture()
        _, obs = begin_episode(f, episode_id="ep-6", episode_generation=0)

        class EvilObservation(ObservationView):
            pass

        evil_obs = EvilObservation(**obs.as_dict())
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "exact concrete ObservationView"):
            run_goal_inference(policy=always_abstain_policy, run=run(f), fixture=f, observation=evil_obs, candidates=goals())

        def unknown_goal(_observation: ObservationView, _candidates: tuple[CandidateGoal, ...]) -> GoalChoice:
            return GoalChoice.goal("goal-not-offered")

        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "outside candidate set"):
            run_goal_inference(policy=unknown_goal, run=run(f), fixture=f, observation=obs, candidates=goals())

    def test_run_fixture_generation_binding_fails_closed(self) -> None:
        f1 = fixture()
        f2 = replace(f1, generation=2)
        _, obs2 = begin_episode(f2, episode_id="ep-7", episode_generation=0)
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "run descriptor does not match"):
            run_goal_inference(
                policy=always_abstain_policy,
                run=run(f1),
                fixture=f2,
                observation=obs2,
                candidates=goals(),
            )

    def test_evaluator_label_cannot_be_forged_by_direct_construction(self) -> None:
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep-8", episode_generation=0)
        c = goals()
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "must be created by seal_evaluator_goal_label"):
            EvaluatorGoalLabel(
                GOAL_LABEL_SCHEMA,
                f.sha256(),
                state.sha256(),
                obs.sha256(),
                candidate_set_digest(c),
                GOAL,
                "goal-blue",
                "label:forged",
                h("forged"),
            )

    def test_score_rejects_label_from_different_state_binding(self) -> None:
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep-9", episode_generation=0)
        other_state, _ = begin_episode(f, episode_id="ep-9-other", episode_generation=0)
        c = goals()
        inference = run_goal_inference(policy=unique_public_signal_policy, run=run(f), fixture=f, observation=obs, candidates=c)
        other_label = seal_evaluator_goal_label(
            fixture=f,
            state=other_state,
            candidates=c,
            expected_goal_id="goal-blue",
            label_ref="label:other-state",
            label_sha256=h("label-other-state"),
        )
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "label evaluator fixture/state binding mismatch"):
            score_goal_inference(
                fixture=f, state=state, observation=obs, candidates=c, inference=inference, label=other_label
            )
        self.assertEqual(other_label.classification, EVALUATOR_CLASSIFICATION)

    def test_abstain_baseline_scores_only_against_explicit_abstain_label(self) -> None:
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep-10", episode_generation=0)
        c = goals()
        inference = run_goal_inference(policy=always_abstain_policy, run=run(f), fixture=f, observation=obs, candidates=c)
        goal_label = seal_evaluator_goal_label(
            fixture=f,
            state=state,
            candidates=c,
            expected_goal_id="goal-blue",
            label_ref="label:goal",
            label_sha256=h("label-goal"),
        )
        score = score_goal_inference(
            fixture=f, state=state, observation=obs, candidates=c, inference=inference, label=goal_label
        )
        self.assertFalse(score.correct)
        self.assertEqual(score.decision, ABSTAIN)
        self.assertEqual(score.expected_decision, GOAL)


if __name__ == "__main__":
    unittest.main()
