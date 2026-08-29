from __future__ import annotations

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
    persistence_baseline,
    evaluate_next_observation_prediction,
)


def fixture() -> MicroWorldFixture:
    return MicroWorldFixture(
        FIXTURE_SCHEMA,
        "fixture/wp803-run-binding-falsifier",
        1,
        "holdout/wp803-run-binding-falsifier",
        "n0",
        1,
        (ActionSpec("go", "action/go", "a" * 64),),
        (
            WorldNode("n0", "public/a", "1" * 64, "hidden/a", "b" * 64, False, 0),
            WorldNode("n1", "public/b", "2" * 64, "hidden/b", "c" * 64, True, 1),
        ),
        (TransitionRule("n0", "go", "n1", "transition/go", "d" * 64),),
        "synthetic-heldout",
        ("source/wp803-run-binding-falsifier",),
        "donor/wp800",
        "method/run-identity-falsifier",
    )


class WP803RunIdentityFalsifier(unittest.TestCase):
    def test_evaluator_must_not_mint_score_under_self_attested_run_identity(self) -> None:
        world = fixture()
        state, observation = begin_episode(world, episode_id="episode/run-binding", episode_generation=1)
        canonical_run = RunDescriptor.for_fixture(
            world,
            run_id="run/canonical",
            condition=BASELINE,
            episode_family_id="family/run-binding",
            system_under_test_ref="sut/wp803",
            communication_before_result=False,
            independent_reproduction=False,
        )

        prediction = persistence_baseline(
            observation,
            action_id="go",
            prediction_id="prediction/forged-run",
            benchmark_run_id="run/FORGED-BY-CANDIDATE",
            benchmark_generation=999999,
        )

        _, _, _, evaluation = evaluate_next_observation_prediction(
            world,
            state=state,
            action_id="go",
            prediction=prediction,
        )

        # Acceptance contract requires prediction + episode + fixture + generation + RUN
        # identities to be bound. A candidate-supplied run identity that is never checked
        # against the canonical WP800 RunDescriptor must not survive into evaluator evidence.
        self.assertEqual(
            evaluation.benchmark_run_id,
            canonical_run.run_id,
            "FALSIFIER_CONFIRMED: evaluator accepted candidate-self-attested run_id and minted evaluator evidence under it",
        )
        self.assertEqual(
            evaluation.benchmark_generation,
            1,
            "FALSIFIER_CONFIRMED: evaluator accepted candidate-self-attested benchmark_generation",
        )


if __name__ == "__main__":
    unittest.main()
