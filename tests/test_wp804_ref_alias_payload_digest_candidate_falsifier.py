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


class WP804RefAliasPayloadDigestCandidateFalsifierTests(unittest.TestCase):
    def test_same_public_ref_different_payload_digest_remains_self_consistently_goal_identifiable(self) -> None:
        """Positive reproducer for the recorded ref-alias/payload-digest candidate falsifier.

        Two otherwise-valid fixture generations expose the same public observation reference
        but different public payload digests. The unchanged CandidateGoal set binds only the
        reference. If both policy and evaluator still identify goal-blue, the benchmark has
        not independently bound candidate-goal signal identity to the public payload digest.
        """
        f1 = fixture()
        changed_nodes = tuple(
            replace(node, public_payload_sha256=h("needs-blue-v2"))
            if node.node_id == "evaluator-node-start"
            else node
            for node in f1.nodes
        )
        f2 = replace(f1, generation=f1.generation + 1, nodes=changed_nodes)

        s1, o1 = begin_episode(f1, episode_id="ep-ref-alias-v1", episode_generation=0)
        s2, o2 = begin_episode(f2, episode_id="ep-ref-alias-v2", episode_generation=0)
        self.assertEqual(o1.observation_ref, o2.observation_ref)
        self.assertNotEqual(o1.observation_sha256, o2.observation_sha256)

        candidates = goals()
        r1 = run(f1, sut="sut:wp804-ref-alias", run_id="run:wp804:ref-alias:v1")
        r2 = run(f2, sut="sut:wp804-ref-alias", run_id="run:wp804:ref-alias:v2")

        i1 = run_goal_inference(
            policy=unique_public_signal_policy,
            run=r1,
            fixture=f1,
            observation=o1,
            candidates=candidates,
        )
        i2 = run_goal_inference(
            policy=unique_public_signal_policy,
            run=r2,
            fixture=f2,
            observation=o2,
            candidates=candidates,
        )
        self.assertEqual((i1.choice.decision, i1.choice.goal_id), (GOAL, "goal-blue"))
        self.assertEqual((i2.choice.decision, i2.choice.goal_id), (GOAL, "goal-blue"))

        l1 = seal_evaluator_goal_label(
            run=r1,
            fixture=f1,
            state=s1,
            observation=o1,
            candidates=candidates,
            inference=i1,
            expected_goal_id="goal-blue",
            label_ref="label:ref-alias:v1",
            label_sha256=h("label-ref-alias-v1"),
        )
        l2 = seal_evaluator_goal_label(
            run=r2,
            fixture=f2,
            state=s2,
            observation=o2,
            candidates=candidates,
            inference=i2,
            expected_goal_id="goal-blue",
            label_ref="label:ref-alias:v2",
            label_sha256=h("label-ref-alias-v2"),
        )
        score1 = score_goal_inference(
            run=r1,
            fixture=f1,
            state=s1,
            observation=o1,
            candidates=candidates,
            inference=i1,
            label=l1,
        )
        score2 = score_goal_inference(
            run=r2,
            fixture=f2,
            state=s2,
            observation=o2,
            candidates=candidates,
            inference=i2,
            label=l2,
        )
        self.assertTrue(score1.correct)
        self.assertTrue(score2.correct)
        self.assertEqual(l1.expected_goal_id, l2.expected_goal_id)


if __name__ == "__main__":
    unittest.main()
