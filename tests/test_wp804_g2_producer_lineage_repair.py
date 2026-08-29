from __future__ import annotations

import unittest

from frankenstein2.cognitive_goal_inference_benchmark import (
    GOAL,
    GoalInferenceBenchmarkError,
    always_abstain_policy,
    run_goal_inference,
    score_goal_inference,
    seal_evaluator_goal_label,
)
from frankenstein2.cognitive_microworld import begin_episode
from tests.test_cognitive_goal_inference_benchmark import fixture, goals, run, h


class WP804G2ProducerLineageRepairTests(unittest.TestCase):
    def test_runner_binds_exact_producer_choice_digest(self) -> None:
        f = fixture()
        _, obs = begin_episode(f, episode_id="ep-g2-producer-digest", episode_generation=0)
        inference = run_goal_inference(
            policy=always_abstain_policy,
            run=run(f, sut="sut:g2-digest", run_id="run:wp804:g2-digest"),
            fixture=f,
            observation=obs,
            candidates=goals(),
        )
        self.assertEqual(inference.producer_choice_sha256, inference.choice.sha256())

    def test_preregistered_preseal_abstain_to_goal_mutation_fails_closed(self) -> None:
        """Regression for the exact post-generation-1 positive reproducer.

        Generation 1 allowed a runner-produced ABSTAIN choice to be mutated to GOAL before
        evaluator-label sealing. Generation 2 must reject that current content because it no
        longer matches the choice digest bound by run_goal_inference.
        """
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep-g2-preseal-mutation", episode_generation=0)
        candidates = goals()
        r = run(f, sut="sut:g2-preseal-repair", run_id="run:wp804:g2-preseal-repair")
        inference = run_goal_inference(
            policy=always_abstain_policy,
            run=r,
            fixture=f,
            observation=obs,
            candidates=candidates,
        )
        producer_choice_sha = inference.producer_choice_sha256

        object.__setattr__(inference.choice, "decision", GOAL)
        object.__setattr__(inference.choice, "goal_id", "goal-blue")
        self.assertNotEqual(producer_choice_sha, inference.choice.sha256())

        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "inference choice producer binding mismatch"):
            seal_evaluator_goal_label(
                run=r,
                fixture=f,
                state=state,
                observation=obs,
                candidates=candidates,
                inference=inference,
                expected_goal_id="goal-blue",
                label_ref="label:g2-preseal-mutation",
                label_sha256=h("label-g2-preseal-mutation"),
            )

    def test_postseal_choice_mutation_is_rejected_before_scoring(self) -> None:
        """The scorer must revalidate the runner-produced choice, not trust the seal alone."""
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep-g2-postseal-mutation", episode_generation=0)
        candidates = goals()
        r = run(f, sut="sut:g2-postseal-repair", run_id="run:wp804:g2-postseal-repair")
        inference = run_goal_inference(
            policy=always_abstain_policy,
            run=r,
            fixture=f,
            observation=obs,
            candidates=candidates,
        )
        label = seal_evaluator_goal_label(
            run=r,
            fixture=f,
            state=state,
            observation=obs,
            candidates=candidates,
            inference=inference,
            expected_goal_id=None,
            label_ref="label:g2-postseal-mutation",
            label_sha256=h("label-g2-postseal-mutation"),
        )

        object.__setattr__(inference.choice, "decision", GOAL)
        object.__setattr__(inference.choice, "goal_id", "goal-blue")

        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "inference choice producer binding mismatch"):
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
