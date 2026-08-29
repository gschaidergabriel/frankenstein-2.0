from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.cognitive_microworld import (
    BASELINE,
    FIXTURE_SCHEMA,
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


class WP803G2GenerationAndCoforgeFalsifier(unittest.TestCase):
    """REVIEW_ONLY counterexamples against WP803 generation-2 run provenance closure.

    These tests intentionally assert the *currently accepted behavior*. A green review
    run therefore means the negative control reproduced: G2 rejects a prediction-only
    run-id relabel, but benchmark generation is still candidate-self-attested and a
    run-id/policy relabel can still be paired with a freshly builder-originated descriptor.

    This file grants no runtime, physical GRID10, GWT/J-Space, training, effect,
    completion, or whole-system credit.
    """

    @staticmethod
    def _fixture() -> MicroWorldFixture:
        return MicroWorldFixture(
            FIXTURE_SCHEMA,
            "fixture/wp803-g2-coforge-review",
            1,
            "holdout/wp803-g2-coforge-review",
            "n0",
            2,
            (ActionSpec("stay", "action/stay", "a" * 64),),
            (
                WorldNode("n0", "public/a", "1" * 64, "hidden/a", "c" * 64, False, 0),
            ),
            (TransitionRule("n0", "stay", "n0", "transition/stay", "e" * 64),),
            "review-independent-source-family",
            ("review/source/wp803-g2-coforge",),
            "review/donor-none",
            "review/generation-coforge-falsifier",
        )

    @staticmethod
    def _run(
        fixture: MicroWorldFixture,
        *,
        run_id: str,
        sut_ref: str,
        episode_family_id: str = "family/wp803-g2-coforge",
    ) -> RunDescriptor:
        return RunDescriptor.for_fixture(
            fixture,
            run_id=run_id,
            condition=BASELINE,
            episode_family_id=episode_family_id,
            system_under_test_ref=sut_ref,
            communication_before_result=False,
            independent_reproduction=True,
        )

    def test_benchmark_generation_is_still_candidate_self_attested(self) -> None:
        fixture = self._fixture()
        state, observation = begin_episode(
            fixture,
            episode_id="episode/wp803-g2-generation",
            episode_generation=1,
        )
        run = self._run(
            fixture,
            run_id="run/wp803-g2-generation",
            sut_ref="PUBLIC_PERSISTENCE_BASELINE",
        )
        prediction = persistence_baseline(
            observation,
            action_id="stay",
            prediction_id="prediction/wp803-g2-generation",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )

        forged_generation = replace(prediction, benchmark_generation=999999)
        _, _, _, evaluation = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="stay",
            prediction=forged_generation,
            run_descriptor=run,
        )

        self.assertEqual(evaluation.outcome, CORRECT)
        self.assertEqual(evaluation.benchmark_generation, 999999)
        self.assertEqual(evaluation.benchmark_run_id, run.run_id)
        self.assertEqual(evaluation.run_descriptor_sha256, run.sha256())

    def test_run_and_policy_identity_can_be_coforged_with_fresh_builder_descriptor(self) -> None:
        fixture = self._fixture()
        state, observation = begin_episode(
            fixture,
            episode_id="episode/wp803-g2-coforge",
            episode_generation=1,
        )
        canonical_run = self._run(
            fixture,
            run_id="run/wp803-g2-canonical",
            sut_ref="PUBLIC_PERSISTENCE_BASELINE",
            episode_family_id="family/wp803-g2-canonical",
        )
        prediction = persistence_baseline(
            observation,
            action_id="stay",
            prediction_id="prediction/wp803-g2-coforge",
            benchmark_run_id=canonical_run.run_id,
            benchmark_generation=2,
        )

        # Re-label the untrusted candidate, then mint a fresh builder-originated
        # descriptor that agrees with the new labels. G2 currently has no prior
        # admitted run-manifest/digest against which to distinguish this pair.
        forged_prediction = replace(
            prediction,
            benchmark_run_id="run/wp803-g2-forged",
            policy_id="policy/wp803-g2-forged",
        )
        forged_run = self._run(
            fixture,
            run_id=forged_prediction.benchmark_run_id,
            sut_ref=forged_prediction.policy_id,
            episode_family_id="family/wp803-g2-forged",
        )

        _, _, _, evaluation = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="stay",
            prediction=forged_prediction,
            run_descriptor=forged_run,
        )

        self.assertNotEqual(canonical_run.sha256(), forged_run.sha256())
        self.assertEqual(evaluation.outcome, CORRECT)
        self.assertEqual(evaluation.benchmark_run_id, forged_prediction.benchmark_run_id)
        self.assertEqual(evaluation.run_descriptor_sha256, forged_run.sha256())


if __name__ == "__main__":
    unittest.main()
