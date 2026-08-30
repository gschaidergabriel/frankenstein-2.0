from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import unittest

from frankenstein2.cognitive_microworld import (
    BASELINE, FIXTURE_SCHEMA, ActionSpec, MicroWorldFixture, RunDescriptor,
    TransitionRule, WorldNode, begin_episode,
)
from frankenstein2.cognitive_world_model_prediction_benchmark import (
    abstain_for_observation, evaluate_next_observation_prediction, persistence_baseline,
)
from frankenstein2.cognitive_world_model_probabilistic_scoring import (
    ABSTAIN_NOT_SCORED, PredictionConfidence, ProbabilisticScoringError,
    evaluate_prediction_confidence, reliability_bins,
)


def _fixture() -> MicroWorldFixture:
    return MicroWorldFixture(
        FIXTURE_SCHEMA, "fixture/wp803-prob", 1, "holdout/wp803-prob", "n0", 3,
        (ActionSpec("a_change", "action/change", "a"*64), ActionSpec("b_stay", "action/stay", "b"*64)),
        (WorldNode("n0", "public/a", "1"*64, "hidden/a", "c"*64, False, 0),
         WorldNode("n1", "public/b", "2"*64, "hidden/b", "d"*64, True, 1)),
        (TransitionRule("n0", "a_change", "n1", "transition/change", "e"*64),
         TransitionRule("n0", "b_stay", "n0", "transition/stay", "f"*64)),
        "synthetic-heldout", ("source/wp803-prob",), "donor/none", "method/probabilistic-scoring",
    )


def _hard(action_id: str, run_id: str):
    fixture = _fixture()
    state, observation = begin_episode(fixture, episode_id=f"episode/{run_id}", episode_generation=1)
    run = RunDescriptor.for_fixture(
        fixture, run_id=run_id, condition=BASELINE, episode_family_id="episode-family/wp803-prob",
        system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE", communication_before_result=False,
        independent_reproduction=True,
    )
    prediction = persistence_baseline(
        observation, action_id=action_id, prediction_id=f"prediction/{run_id}",
        benchmark_run_id=run.run_id, benchmark_generation=3,
    )
    _, _, _, evaluation = evaluate_next_observation_prediction(
        fixture, state=state, action_id=action_id, prediction=prediction, run_descriptor=run,
    )
    return prediction, evaluation


class ProbabilisticScoringTests(unittest.TestCase):
    def test_same_hard_evaluation_distinguishes_calibrated_from_overconfident(self) -> None:
        prediction, hard = _hard("a_change", "run/wrong")
        calibrated = evaluate_prediction_confidence(
            PredictionConfidence.for_prediction(prediction, probability_correct_ppm=310_000), hard)
        overconfident = evaluate_prediction_confidence(
            PredictionConfidence.for_prediction(prediction, probability_correct_ppm=990_000), hard)
        self.assertEqual(calibrated.hard_score_delta, overconfident.hard_score_delta)
        self.assertEqual(calibrated.hard_outcome, overconfident.hard_outcome)
        self.assertLess(Decimal(calibrated.brier_loss), Decimal(overconfident.brier_loss))
        self.assertLess(Decimal(calibrated.log_loss_nats), Decimal(overconfident.log_loss_nats))

    def test_confidence_is_bound_to_exact_prediction(self) -> None:
        prediction, hard = _hard("b_stay", "run/correct")
        confidence = PredictionConfidence.for_prediction(prediction, probability_correct_ppm=700_000)
        forged = replace(confidence, prediction_sha256="0"*64)
        with self.assertRaisesRegex(ProbabilisticScoringError, "provenance mismatch"):
            evaluate_prediction_confidence(forged, hard)

    def test_abstain_preserves_hard_semantics_and_gets_no_probability_score(self) -> None:
        fixture = _fixture()
        state, observation = begin_episode(fixture, episode_id="episode/abstain", episode_generation=1)
        run = RunDescriptor.for_fixture(
            fixture, run_id="run/abstain", condition=BASELINE, episode_family_id="episode-family/wp803-prob",
            system_under_test_ref="policy/abstain", communication_before_result=False, independent_reproduction=True)
        prediction = abstain_for_observation(
            observation, action_id="a_change", prediction_id="prediction/abstain",
            benchmark_run_id=run.run_id, benchmark_generation=3, policy_id="policy/abstain",
            policy_generation=1, policy_state_sha256="4"*64)
        _, _, _, hard = evaluate_next_observation_prediction(
            fixture, state=state, action_id="a_change", prediction=prediction, run_descriptor=run)
        scored = evaluate_prediction_confidence(
            PredictionConfidence.for_prediction(prediction, probability_correct_ppm=500_000), hard)
        self.assertEqual(scored.hard_score_delta, 0)
        self.assertEqual(scored.score_status, ABSTAIN_NOT_SCORED)
        self.assertIsNone(scored.brier_loss)
        self.assertIsNone(scored.log_loss_nats)

    def test_reliability_bins_are_evaluator_derived(self) -> None:
        p_good, e_good = _hard("b_stay", "run/good")
        p_bad, e_bad = _hard("a_change", "run/bad")
        rows = (
            evaluate_prediction_confidence(PredictionConfidence.for_prediction(p_good, probability_correct_ppm=700_000), e_good),
            evaluate_prediction_confidence(PredictionConfidence.for_prediction(p_bad, probability_correct_ppm=300_000), e_bad),
        )
        bins = reliability_bins(rows, bin_width_ppm=500_000)
        self.assertEqual(len(bins), 2)
        self.assertEqual(sum(x.count for x in bins), 2)
        self.assertTrue(all(x.absolute_calibration_gap is not None for x in bins))

    def test_probability_domain_excludes_nonfinite_log_loss_endpoints(self) -> None:
        prediction, _ = _hard("b_stay", "run/domain")
        for invalid in (0, 1_000_000, True, -1):
            with self.assertRaises(ProbabilisticScoringError):
                PredictionConfidence.for_prediction(prediction, probability_correct_ppm=invalid)


if __name__ == "__main__":
    unittest.main()
