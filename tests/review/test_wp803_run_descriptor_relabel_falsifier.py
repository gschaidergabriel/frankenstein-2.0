from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.cognitive_microworld import (
    FIXTURE_SCHEMA,
    INTERVENTION,
    ActionSpec,
    MicroWorldFixture,
    RunDescriptor,
    TransitionRule,
    WorldNode,
    begin_episode,
)
from frankenstein2.cognitive_world_model_prediction_benchmark import (
    CORRECT,
    evaluate_next_observation_prediction,
    persistence_baseline,
)


class WP803RunDescriptorRelabelFalsifier(unittest.TestCase):
    """REVIEW_ONLY witness for accepted F2-WP-803 generation 1.

    Passing means the current accepted source still allows benchmark run identity to be
    relabeled without presenting the exact WP800 RunDescriptor whose fixture, SUT and
    evidence ancestry the run id is supposed to represent. This is negative evidence,
    not an alternative implementation and not runtime/GRID/GWT/J-Space credit.
    """

    @staticmethod
    def _fixture() -> MicroWorldFixture:
        return MicroWorldFixture(
            FIXTURE_SCHEMA,
            "fixture/wp803-run-relabel-review",
            1,
            "holdout/wp803-run-relabel-review",
            "n0",
            2,
            (
                ActionSpec("a_change", "action/change", "a" * 64),
                ActionSpec("b_stay", "action/stay", "b" * 64),
            ),
            (
                WorldNode("n0", "public/a", "1" * 64, "hidden/a", "c" * 64, False, 0),
                WorldNode("n1", "public/b", "2" * 64, "hidden/b", "d" * 64, True, 1),
            ),
            (
                TransitionRule("n0", "a_change", "n1", "transition/change", "e" * 64),
                TransitionRule("n0", "b_stay", "n0", "transition/stay", "f" * 64),
            ),
            "review-independent-source-family",
            ("review/source/wp803-run-relabel",),
            "review/donor-none",
            "review/run-provenance-falsifier",
        )

    def test_accepted_wp803_allows_run_id_relabel_without_exact_wp800_descriptor(self) -> None:
        fixture = self._fixture()
        state, observation = begin_episode(
            fixture,
            episode_id="episode/wp803-run-relabel-review",
            episode_generation=1,
        )
        canonical_run = RunDescriptor.for_fixture(
            fixture,
            run_id="run/wp803-canonical",
            condition=INTERVENTION,
            episode_family_id="episode-family/wp803-run-relabel-review",
            system_under_test_ref="sut/review-policy-a",
            communication_before_result=False,
            independent_reproduction=True,
        )
        canonical_run.assert_matches_fixture(fixture)

        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/wp803-run-relabel-review",
            benchmark_run_id=canonical_run.run_id,
            benchmark_generation=1,
        )

        relabeled = replace(prediction, benchmark_run_id="run/wp803-forged-unbound")
        self.assertNotEqual(relabeled.benchmark_run_id, canonical_run.run_id)
        self.assertNotEqual(relabeled.sha256(), prediction.sha256())

        _, _, _, evaluation = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="b_stay",
            prediction=relabeled,
        )

        self.assertEqual(evaluation.outcome, CORRECT)
        self.assertEqual(evaluation.benchmark_run_id, "run/wp803-forged-unbound")
        self.assertNotEqual(evaluation.benchmark_run_id, canonical_run.run_id)


if __name__ == "__main__":
    unittest.main()
