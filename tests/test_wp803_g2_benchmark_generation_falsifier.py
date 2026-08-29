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


class WP803G2BenchmarkGenerationFalsifier(unittest.TestCase):
    def test_evaluator_must_not_copy_untrusted_benchmark_generation_into_evidence(self) -> None:
        fixture = MicroWorldFixture(
            FIXTURE_SCHEMA,
            "fixture/wp803-g2-generation",
            1,
            "holdout/wp803-g2-generation",
            "n0",
            1,
            (ActionSpec("go", "action/go", "a" * 64),),
            (
                WorldNode("n0", "public/a", "1" * 64, "hidden/a", "b" * 64, False, 0),
                WorldNode("n1", "public/b", "2" * 64, "hidden/b", "c" * 64, True, 1),
            ),
            (TransitionRule("n0", "go", "n1", "transition/go", "d" * 64),),
            "synthetic-heldout",
            ("source/wp803-g2-generation",),
            "donor/wp800",
            "method/benchmark-generation-falsifier",
        )
        state, observation = begin_episode(fixture, episode_id="episode/wp803-g2-generation", episode_generation=1)
        run = RunDescriptor.for_fixture(
            fixture,
            run_id="run/wp803-g2-generation",
            condition=BASELINE,
            episode_family_id="family/wp803-g2-generation",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            communication_before_result=False,
            independent_reproduction=False,
        )
        prediction = persistence_baseline(
            observation,
            action_id="go",
            prediction_id="prediction/wp803-g2-generation",
            benchmark_run_id=run.run_id,
            benchmark_generation=999999,
        )
        _, _, _, evaluation = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="go",
            prediction=prediction,
            run_descriptor=run,
        )
        self.assertEqual(
            evaluation.benchmark_generation,
            2,
            "FALSIFIER_CONFIRMED: evaluator copied candidate-self-attested benchmark_generation into evaluator evidence",
        )


if __name__ == "__main__":
    unittest.main()
