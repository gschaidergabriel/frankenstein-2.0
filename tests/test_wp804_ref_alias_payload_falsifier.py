from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.cognitive_goal_inference_benchmark import (
    GOAL,
    run_goal_inference,
    score_goal_inference,
    seal_evaluator_goal_label,
    unique_public_signal_policy,
)
from frankenstein2.cognitive_microworld import begin_episode
from tests.test_cognitive_goal_inference_benchmark import fixture, goals, h, run


class WP804RefAliasPayloadFalsifierTests(unittest.TestCase):
    def test_same_public_ref_different_payload_sha_remains_self_consistent(self) -> None:
        """Positive reproducer for the preregistered ref-alias candidate falsifier.

        Two valid fixture generations expose the same public payload reference with different
        public payload SHA-256 values. One ref-only CandidateGoal set is nevertheless accepted
        by both policy and evaluator, demonstrating that exact public-payload identity is not
        currently part of candidate-goal signal matching.
        """
        fixture_a = fixture()
        start_a, terminal_a = fixture_a.nodes
        fixture_b = replace(
            fixture_a,
            fixture_id="heldout.goal-inference.alias.002",
            generation=2,
            nodes=(
                replace(start_a, public_payload_sha256=h("needs-blue-aliased-payload")),
                terminal_a,
            ),
            primary_source_ids=("wp804-ref-alias-falsifier-v1",),
        )

        state_a, obs_a = begin_episode(fixture_a, episode_id="ep-ref-alias-a", episode_generation=0)
        state_b, obs_b = begin_episode(fixture_b, episode_id="ep-ref-alias-b", episode_generation=0)
        self.assertEqual(obs_a.observation_ref, obs_b.observation_ref)
        self.assertNotEqual(obs_a.observation_sha256, obs_b.observation_sha256)

        candidates = goals()
        run_a = run(fixture_a, sut="sut:ref-alias-a", run_id="run:wp804:ref-alias-a")
        run_b = run(fixture_b, sut="sut:ref-alias-b", run_id="run:wp804:ref-alias-b")
        inference_a = run_goal_inference(
            policy=unique_public_signal_policy,
            run=run_a,
            fixture=fixture_a,
            observation=obs_a,
            candidates=candidates,
        )
        inference_b = run_goal_inference(
            policy=unique_public_signal_policy,
            run=run_b,
            fixture=fixture_b,
            observation=obs_b,
            candidates=candidates,
        )

        self.assertEqual((inference_a.choice.decision, inference_a.choice.goal_id), (GOAL, "goal-blue"))
        self.assertEqual((inference_b.choice.decision, inference_b.choice.goal_id), (GOAL, "goal-blue"))

        label_a = seal_evaluator_goal_label(
            run=run_a,
            fixture=fixture_a,
            state=state_a,
            observation=obs_a,
            candidates=candidates,
            inference=inference_a,
            expected_goal_id="goal-blue",
            label_ref="label:ref-alias-a",
            label_sha256=h("label-ref-alias-a"),
        )
        label_b = seal_evaluator_goal_label(
            run=run_b,
            fixture=fixture_b,
            state=state_b,
            observation=obs_b,
            candidates=candidates,
            inference=inference_b,
            expected_goal_id="goal-blue",
            label_ref="label:ref-alias-b",
            label_sha256=h("label-ref-alias-b"),
        )

        score_a = score_goal_inference(
            run=run_a,
            fixture=fixture_a,
            state=state_a,
            observation=obs_a,
            candidates=candidates,
            inference=inference_a,
            label=label_a,
        )
        score_b = score_goal_inference(
            run=run_b,
            fixture=fixture_b,
            state=state_b,
            observation=obs_b,
            candidates=candidates,
            inference=inference_b,
            label=label_b,
        )
        self.assertTrue(score_a.correct)
        self.assertTrue(score_b.correct)


if __name__ == "__main__":
    unittest.main()
