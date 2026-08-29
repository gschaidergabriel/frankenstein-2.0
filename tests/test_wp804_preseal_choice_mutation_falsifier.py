from __future__ import annotations

import unittest

from frankenstein2.cognitive_goal_inference_benchmark import (
    GOAL,
    always_abstain_policy,
    run_goal_inference,
    seal_evaluator_goal_label,
    score_goal_inference,
)
from frankenstein2.cognitive_microworld import begin_episode
from tests.test_cognitive_goal_inference_benchmark import fixture, goals, run, h


class WP804PreSealChoiceMutationReproducer(unittest.TestCase):
    def test_preseal_mutation_is_currently_reproduced(self) -> None:
        """Positive reproducer for the preregistered Trigger-6 counterexample.

        This test passes only when a runner-produced ABSTAIN can be mutated before label
        sealing, then sealed and scored as the uniquely identifiable GOAL. It is review
        evidence of the counterexample, not desired product behavior.
        """
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep-preseal-mutation", episode_generation=0)
        candidates = goals()
        r = run(f, sut="sut:preseal-mutation-review", run_id="run:wp804:preseal-mutation")

        inference = run_goal_inference(
            policy=always_abstain_policy,
            run=r,
            fixture=f,
            observation=obs,
            candidates=candidates,
        )
        self.assertEqual(inference.choice.decision, "ABSTAIN")
        self.assertIsNone(inference.choice.goal_id)
        original_inference_sha = inference.sha256()

        object.__setattr__(inference.choice, "decision", GOAL)
        object.__setattr__(inference.choice, "goal_id", "goal-blue")
        mutated_inference_sha = inference.sha256()
        self.assertNotEqual(original_inference_sha, mutated_inference_sha)

        label = seal_evaluator_goal_label(
            run=r,
            fixture=f,
            state=state,
            observation=obs,
            candidates=candidates,
            inference=inference,
            expected_goal_id="goal-blue",
            label_ref="label:preseal-mutation",
            label_sha256=h("label-preseal-mutation"),
        )
        self.assertEqual(label.sealed_inference_sha256, mutated_inference_sha)

        score = score_goal_inference(
            run=r,
            fixture=f,
            state=state,
            observation=obs,
            candidates=candidates,
            inference=inference,
            label=label,
        )
        self.assertTrue(score.correct)
        self.assertEqual(score.inferred_goal_id, "goal-blue")
        self.assertEqual(score.expected_goal_id, "goal-blue")


if __name__ == "__main__":
    unittest.main()
