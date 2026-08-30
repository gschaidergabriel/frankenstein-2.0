from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import unittest

from frankenstein2.cognitive_microworld import (
    BASELINE, FIXTURE_SCHEMA, ActionSpec, MicroWorldFixture, RunDescriptor,
    TransitionRule, WorldNode, begin_episode,
)
from frankenstein2.cognitive_world_model_prediction_benchmark import (
    abstain_for_observation, persistence_baseline,
)
from frankenstein2.cognitive_world_model_probabilistic_scoring import (
    ABSTAIN_NOT_SCORED,
    PredictionConfidence,
    ProbabilisticScoringError,
    evaluate_admitted_prediction_confidence,
    evaluate_prediction_confidence,
    reliability_bins,
)
from frankenstein2.cognitive_world_model_run_admission import BenchmarkRunAdmission


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


def _prepared_case(action_id: str, run_id: str, *, probability_correct_ppm: int):
    fixture = _fixture()
    state, observation = begin_episode(fixture, episode_id=f"episode/{run_id}", episode_generation=1)
    run = RunDescriptor.for_fixture(
        fixture, run_id=run_id, condition=BASELINE, episode_family_id="episode-family/wp803-prob",
        system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE", communication_before_result=False,
        independent_reproduction=True,
    )
    admission = BenchmarkRunAdmission.predeclare(
        fixture,
        run,
        admission_id=f"admission/{run_id}",
        manifest_ref="manifest/wp803-prob",
        benchmark_generation=3,
    )
    prediction = persistence_baseline(
        observation, action_id=action_id, prediction_id=f"prediction/{run_id}",
        benchmark_run_id=run.run_id, benchmark_generation=3,
    )
    confidence = PredictionConfidence.for_prediction(
        prediction,
        probability_correct_ppm=probability_correct_ppm,
    )
    return fixture, state, run, admission, prediction, confidence


def _integrated(action_id: str, run_id: str, probability_correct_ppm: int):
    fixture, state, run, admission, prediction, confidence = _prepared_case(
        action_id, run_id, probability_correct_ppm=probability_correct_ppm)
    result = evaluate_admitted_prediction_confidence(
        fixture,
        state=state,
        action_id=action_id,
        prediction=prediction,
        confidence=confidence,
        run_descriptor=run,
        run_admission=admission,
        expected_run_admission_sha256=admission.sha256(),
        expected_confidence_sha256=confidence.sha256(),
    )
    return (*result, admission, prediction, confidence)


class ProbabilisticScoringTests(unittest.TestCase):
    def test_same_hard_evaluation_distinguishes_calibrated_from_overconfident(self) -> None:
        _, _, _, hard_cal, calibrated, _, prediction_cal, _ = _integrated(
            "a_change", "run/wrong", 310_000)
        _, _, _, hard_over, overconfident, _, prediction_over, _ = _integrated(
            "a_change", "run/wrong", 990_000)

        self.assertEqual(prediction_cal.sha256(), prediction_over.sha256())
        self.assertEqual(hard_cal.sha256(), hard_over.sha256())
        self.assertEqual(calibrated.hard_score_delta, overconfident.hard_score_delta)
        self.assertEqual(calibrated.hard_outcome, overconfident.hard_outcome)
        self.assertLess(Decimal(calibrated.brier_loss), Decimal(overconfident.brier_loss))
        self.assertLess(Decimal(calibrated.log_loss_nats), Decimal(overconfident.log_loss_nats))

    def test_confidence_digest_is_pinned_before_outcome(self) -> None:
        fixture, state, run, admission, prediction, confidence = _prepared_case(
            "b_stay", "run/confidence-pin", probability_correct_ppm=700_000)
        expected_confidence = confidence.sha256()
        altered_after_pin = replace(confidence, probability_correct_ppm=990_000)

        with self.assertRaisesRegex(ProbabilisticScoringError, "pre-outcome expected digest"):
            evaluate_admitted_prediction_confidence(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=prediction,
                confidence=altered_after_pin,
                run_descriptor=run,
                run_admission=admission,
                expected_run_admission_sha256=admission.sha256(),
                expected_confidence_sha256=expected_confidence,
            )
        self.assertEqual(state.step_index, 0)

    def test_confidence_is_bound_to_exact_prediction(self) -> None:
        fixture, state, run, admission, prediction, confidence = _prepared_case(
            "b_stay", "run/prediction-bind", probability_correct_ppm=700_000)
        forged = replace(confidence, prediction_sha256="0"*64)
        with self.assertRaisesRegex(ProbabilisticScoringError, "confidence/prediction provenance mismatch"):
            evaluate_admitted_prediction_confidence(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=prediction,
                confidence=forged,
                run_descriptor=run,
                run_admission=admission,
                expected_run_admission_sha256=admission.sha256(),
                expected_confidence_sha256=forged.sha256(),
            )
        self.assertEqual(state.step_index, 0)

    def test_wrong_expected_admission_digest_fails_closed_before_world_step(self) -> None:
        fixture, state, run, admission, prediction, confidence = _prepared_case(
            "b_stay", "run/admission-pin", probability_correct_ppm=700_000)
        with self.assertRaisesRegex(ProbabilisticScoringError, "predeclared expected digest"):
            evaluate_admitted_prediction_confidence(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=prediction,
                confidence=confidence,
                run_descriptor=run,
                run_admission=admission,
                expected_run_admission_sha256="9"*64,
                expected_confidence_sha256=confidence.sha256(),
            )
        self.assertEqual(state.step_index, 0)

    def test_post_step_replay_requires_both_retained_digests(self) -> None:
        _, _, _, hard, scored, admission, prediction, confidence = _integrated(
            "b_stay", "run/replay", 700_000)
        replayed = evaluate_prediction_confidence(
            confidence,
            hard,
            prediction=prediction,
            run_admission=admission,
            expected_run_admission_sha256=admission.sha256(),
            expected_confidence_sha256=confidence.sha256(),
        )
        self.assertEqual(replayed.sha256(), scored.sha256())
        with self.assertRaisesRegex(ProbabilisticScoringError, "pre-outcome expected digest"):
            evaluate_prediction_confidence(
                confidence,
                hard,
                prediction=prediction,
                run_admission=admission,
                expected_run_admission_sha256=admission.sha256(),
                expected_confidence_sha256="8"*64,
            )

    def test_abstain_preserves_hard_semantics_and_gets_no_probability_score(self) -> None:
        fixture = _fixture()
        state, observation = begin_episode(fixture, episode_id="episode/abstain", episode_generation=1)
        run = RunDescriptor.for_fixture(
            fixture, run_id="run/abstain", condition=BASELINE, episode_family_id="episode-family/wp803-prob",
            system_under_test_ref="policy/abstain", communication_before_result=False, independent_reproduction=True)
        admission = BenchmarkRunAdmission.predeclare(
            fixture,
            run,
            admission_id="admission/run-abstain",
            manifest_ref="manifest/wp803-prob",
            benchmark_generation=3,
        )
        prediction = abstain_for_observation(
            observation, action_id="a_change", prediction_id="prediction/abstain",
            benchmark_run_id=run.run_id, benchmark_generation=3, policy_id="policy/abstain",
            policy_generation=1, policy_state_sha256="4"*64)
        confidence = PredictionConfidence.for_prediction(prediction, probability_correct_ppm=500_000)
        _, _, _, hard, scored = evaluate_admitted_prediction_confidence(
            fixture,
            state=state,
            action_id="a_change",
            prediction=prediction,
            confidence=confidence,
            run_descriptor=run,
            run_admission=admission,
            expected_run_admission_sha256=admission.sha256(),
            expected_confidence_sha256=confidence.sha256(),
        )
        self.assertEqual(scored.hard_score_delta, 0)
        self.assertEqual(scored.score_status, ABSTAIN_NOT_SCORED)
        self.assertIsNone(scored.brier_loss)
        self.assertIsNone(scored.log_loss_nats)
        self.assertEqual(scored.run_admission_sha256, admission.sha256())
        self.assertEqual(scored.confidence_sha256, confidence.sha256())

    def test_reliability_bins_are_evaluator_derived(self) -> None:
        *_, good, _, _, _ = _integrated("b_stay", "run/good", 700_000)
        *_, bad, _, _, _ = _integrated("a_change", "run/bad", 300_000)
        bins = reliability_bins((good, bad), bin_width_ppm=500_000)
        self.assertEqual(len(bins), 2)
        self.assertEqual(sum(x.count for x in bins), 2)
        self.assertTrue(all(x.absolute_calibration_gap is not None for x in bins))

    def test_probability_domain_excludes_nonfinite_log_loss_endpoints(self) -> None:
        _, _, _, _, prediction, _ = _prepared_case(
            "b_stay", "run/domain", probability_correct_ppm=700_000)
        for invalid in (0, 1_000_000, True, -1):
            with self.assertRaises(ProbabilisticScoringError):
                PredictionConfidence.for_prediction(prediction, probability_correct_ppm=invalid)


if __name__ == "__main__":
    unittest.main()
