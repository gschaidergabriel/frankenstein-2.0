from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from frankenstein2.cognitive_goal_inference_benchmark import (
    ABSTAIN,
    CANDIDATE_GOAL_SCHEMA,
    GOAL,
    CandidateGoal,
    GoalInferenceBenchmarkError,
    run_goal_inference,
    score_goal_inference,
    seal_evaluator_goal_label,
    unique_public_signal_policy,
)
from frankenstein2.cognitive_microworld import begin_episode
from tests.test_cognitive_goal_inference_benchmark import fixture, goals, h, run


class WP804G3PublicSignalDigestBindingTests(unittest.TestCase):
    def test_same_ref_changed_payload_digest_no_longer_preserves_stale_goal_match(self) -> None:
        f1 = fixture()
        changed_nodes = tuple(
            replace(node, public_payload_sha256=h("needs-blue-v2"))
            if node.node_id == "evaluator-node-start"
            else node
            for node in f1.nodes
        )
        f2 = replace(f1, generation=f1.generation + 1, nodes=changed_nodes)

        _, o1 = begin_episode(f1, episode_id="ep-g3-ref-alias-v1", episode_generation=0)
        s2, o2 = begin_episode(f2, episode_id="ep-g3-ref-alias-v2", episode_generation=0)
        self.assertEqual(o1.observation_ref, o2.observation_ref)
        self.assertNotEqual(o1.observation_sha256, o2.observation_sha256)

        candidates = goals()
        r1 = run(f1, sut="sut:g3-ref-digest", run_id="run:wp804:g3-ref-digest:v1")
        r2 = run(f2, sut="sut:g3-ref-digest", run_id="run:wp804:g3-ref-digest:v2")
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
        self.assertEqual((i2.choice.decision, i2.choice.goal_id), (ABSTAIN, None))

        with self.assertRaisesRegex(
            GoalInferenceBenchmarkError,
            "ambiguous public evidence cannot mint exact evaluator goal label",
        ):
            seal_evaluator_goal_label(
                run=r2,
                fixture=f2,
                state=s2,
                observation=o2,
                candidates=candidates,
                inference=i2,
                expected_goal_id="goal-blue",
                label_ref="label:g3-stale-blue-forbidden",
                label_sha256=h("label-g3-stale-blue-forbidden"),
            )

        abstain_label = seal_evaluator_goal_label(
            run=r2,
            fixture=f2,
            state=s2,
            observation=o2,
            candidates=candidates,
            inference=i2,
            expected_goal_id=None,
            label_ref="label:g3-stale-blue-abstain",
            label_sha256=h("label-g3-stale-blue-abstain"),
        )
        score = score_goal_inference(
            run=r2,
            fixture=f2,
            state=s2,
            observation=o2,
            candidates=candidates,
            inference=i2,
            label=abstain_label,
        )
        self.assertTrue(score.correct)
        self.assertEqual(score.expected_decision, ABSTAIN)

    def test_candidate_signal_refs_and_digests_must_form_exact_pairs(self) -> None:
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "binding length mismatch"):
            CandidateGoal(
                CANDIDATE_GOAL_SCHEMA,
                "goal-x",
                "goal:x",
                h("goal-x"),
                ("obs:x",),
                (),
            )
        with self.assertRaisesRegex(GoalInferenceBenchmarkError, "lowercase 64-hex SHA-256"):
            CandidateGoal(
                CANDIDATE_GOAL_SCHEMA,
                "goal-x",
                "goal:x",
                h("goal-x"),
                ("obs:x",),
                ("not-a-digest",),
            )

    def test_evaluator_reconstructs_signal_binding_without_policy_matching_helper(self) -> None:
        f = fixture()
        state, obs = begin_episode(f, episode_id="ep-g3-independent-evaluator", episode_generation=0)
        candidates = goals()
        r = run(f, sut="sut:g3-independent-evaluator", run_id="run:wp804:g3-independent-evaluator")
        inference = run_goal_inference(
            policy=unique_public_signal_policy,
            run=r,
            fixture=f,
            observation=obs,
            candidates=candidates,
        )
        self.assertEqual((inference.choice.decision, inference.choice.goal_id), (GOAL, "goal-blue"))

        with patch(
            "frankenstein2.cognitive_goal_inference_benchmark.public_signal_matches",
            side_effect=AssertionError("evaluator called policy match helper"),
        ), patch(
            "frankenstein2.cognitive_goal_inference_benchmark.public_identifiability_digest",
            side_effect=AssertionError("evaluator called policy identifiability helper"),
        ):
            label = seal_evaluator_goal_label(
                run=r,
                fixture=f,
                state=state,
                observation=obs,
                candidates=candidates,
                inference=inference,
                expected_goal_id="goal-blue",
                label_ref="label:g3-independent-evaluator",
                label_sha256=h("label-g3-independent-evaluator"),
            )
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
        self.assertEqual(label.expected_goal_id, "goal-blue")


if __name__ == "__main__":
    unittest.main()
