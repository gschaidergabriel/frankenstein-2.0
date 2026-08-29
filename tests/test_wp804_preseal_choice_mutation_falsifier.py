from __future__ import annotations

import unittest

from frankenstein2.cognitive_goal_inference_benchmark import (
    GOAL,
    GoalInferenceBenchmarkError,
    always_abstain_policy,
    run_goal_inference,
    seal_evaluator_goal_label,
    score_goal_inference,
)
from frankenstein2.cognitive_microworld import begin_episode
from tests.test_cognitive_goal_inference_benchmark import fixture, goals, run, h


class WP804PreSealChoiceMutationFalsifier(unittest.TestCase):
    def test_runner_choice_mutation_before_label_seal_must_fail_closed(self) -> None:
        """Preregistered Trigger-6 discriminator against pre-seal result mutation."""
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

        object.__setattr__(inference.choice, "decision", GOAL)
        object.__setattr__(inference.choice, "goal_id", "goal-blue")

        with self.assertRaises(GoalInferenceBenchmarkError):
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
            score_goal_inference(
                run=r,
                fixture=f,
                state=state,
                observation=obs,
                candidates=candidates,
                inference=inference,
                label=label,
            )


if __name__ == "__main__":
    unittest.main()
