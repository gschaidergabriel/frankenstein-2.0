from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.cognitive_information_seeking_benchmark import (
    run_matched_information_seeking_benchmark,
)
from tests.test_cognitive_information_seeking_benchmark import fixture, pair_for


class WP802NoveltyNotValueCandidateTests(unittest.TestCase):
    """Candidate falsifier: probe/novelty activity is diagnostic, not decision value."""

    @staticmethod
    def _with_signal_score(score: int):
        original = fixture()
        nodes = tuple(
            replace(node, evaluator_score=score)
            if node.node_id == "evaluator-signal"
            else node
            for node in original.nodes
        )
        candidate = replace(original, nodes=nodes)

        # The intervention changes evaluator-only scoring. The public SUT-facing
        # fixture identity stays unchanged, so the policy receives no new signal.
        assert candidate.public_sha256() == original.public_sha256()
        assert candidate.sha256() != original.sha256()
        return candidate

    def test_positive_probe_novelty_does_not_imply_positive_decision_value(self) -> None:
        cases = (
            (-15, -5, 0),   # probe cost exactly cancels the later good commit
            (-20, -10, -5), # probe cost exceeds the later good commit
        )

        for signal_score, expected_intervention_score, expected_score_delta in cases:
            with self.subTest(signal_score=signal_score):
                f = self._with_signal_score(signal_score)
                pair, baseline_policy, intervention_policy = pair_for(f)
                result = run_matched_information_seeking_benchmark(
                    f,
                    pair=pair,
                    baseline_policy=baseline_policy,
                    intervention_policy=intervention_policy,
                )

                self.assertEqual(result.baseline.action_ids, ("commit-a",))
                self.assertEqual(result.intervention.action_ids, ("probe", "commit-b"))
                self.assertEqual(result.baseline.cumulative_score, -5)
                self.assertEqual(result.intervention.cumulative_score, expected_intervention_score)
                self.assertEqual(result.score_delta, expected_score_delta)
                self.assertLessEqual(result.score_delta, 0)

                # These diagnostics still rise even though decision value does not.
                self.assertEqual(result.probe_delta, 1)
                self.assertEqual(result.public_payload_novelty_delta, 1)
                self.assertGreater(result.public_payload_novelty_delta, 0)


if __name__ == "__main__":
    unittest.main()
