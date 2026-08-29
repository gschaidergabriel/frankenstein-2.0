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
    WorldModelPredictionBenchmarkError,
    evaluate_next_observation_prediction,
    persistence_baseline,
)


def _fixture() -> MicroWorldFixture:
    return MicroWorldFixture(
        FIXTURE_SCHEMA,
        "fixture/wp803-run-provenance-falsifier",
        1,
        "holdout/wp803-run-provenance",
        "n0",
        1,
        (ActionSpec("advance", "action/advance", "a" * 64),),
        (
            WorldNode("n0", "public/a", "1" * 64, "hidden/a", "c" * 64, False, 0),
            WorldNode("n1", "public/b", "2" * 64, "hidden/b", "d" * 64, True, 1),
        ),
        (TransitionRule("n0", "advance", "n1", "transition/advance", "e" * 64),),
        "synthetic-heldout",
        ("source/wp803-run-provenance-falsifier",),
        "donor/none",
        "method/run-provenance-falsifier",
    )


class WP803RunProvenanceFalsifier(unittest.TestCase):
    def test_self_declared_run_id_cannot_substitute_for_canonical_wp800_run_identity(self) -> None:
        fixture = _fixture()
        state, observation = begin_episode(
            fixture,
            episode_id="episode/wp803-run-provenance",
            episode_generation=1,
        )
        canonical_run = RunDescriptor.for_fixture(
            fixture,
            run_id="run/canonical",
            condition=BASELINE,
            episode_family_id="family/wp803-run-provenance",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            communication_before_result=False,
            independent_reproduction=False,
        )
        prediction = persistence_baseline(
            observation,
            action_id="advance",
            prediction_id="prediction/forged-run-id",
            benchmark_run_id="run/self-declared-not-canonical",
            benchmark_generation=1,
        )

        self.assertNotEqual(prediction.benchmark_run_id, canonical_run.run_id)
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "run"):
            evaluate_next_observation_prediction(
                fixture,
                state=state,
                action_id="advance",
                prediction=prediction,
            )


if __name__ == "__main__":
    unittest.main()
