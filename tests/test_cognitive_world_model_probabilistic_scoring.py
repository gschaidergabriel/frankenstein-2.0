from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
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
    abstain_for_observation,
    persistence_baseline,
)
from frankenstein2.cognitive_world_model_probabilistic_scoring import (
    ABSTAIN_NOT_SCORED,
    PredictionConfidence,
    ProbabilisticScoringError,
    evaluate_admitted_prediction_confidence,
    evaluate_prediction_confidence,
    reliability_bins,
)
from frankenstein2.cognitive_world_model_run_admission import (
    BenchmarkRunAdmission,
    evaluate_admitted_next_observation_prediction,
)


def _fixture() -> MicroWorldFixture:
    return MicroWorldFixture(
        FIXTURE_SCHEMA,
        "fixture/wp803-prob",
        1,
        "holdout/wp803-prob",
        "n0",
        3,
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
        "synthetic-heldout",
        ("source/wp803-prob",),
        "donor/none",
        "method/probabilistic-scoring",
    )


def _run(fixture: MicroWorldFixture, *, run_id: str, policy_id: str) -> RunDescriptor:
    return RunDescriptor.for_fixture(
        fixture,
        run_id=run_id,
        condition=BASELINE,
        episode_family_id="episode-family/wp803-prob",
        system_under_test_ref=policy_id,
        communication_before_result=False,
        independent_reproduction=True,
    )


def _admission(fixture: MicroWorldFixture, run: RunDescriptor, *, admission_id: str) -> BenchmarkRunAdmission:
    return BenchmarkRunAdmission.predeclare(
        fixture,
        run,
        admission_id=admission_id,
        manifest_ref="manifest/wp803-probabilistic-scoring",
        benchmark_generation=2,
    )


def _persistence_case(action_id: str, run_id: str, probability_correct_ppm: int):
    fixture = _fixture()
    state, observation = begin_episode(fixture, episode_id=f"episode/{run_id}", episode_generation=1)
    policy_id = "PUBLIC_PERSISTENCE_BASELINE"
    run = _run(fixture, run_id=run_id, policy_id=policy_id)
    admission = _admission(fixture, run, admission_id=f"admission/{run_id}")
    prediction = persistence_baseline(
        observation,
        action_id=action_id,
        prediction_id=f"prediction/{run_id}",
        benchmark_run_id=run.run_id,
        benchmark_generation=2,
    )
    confidence = PredictionConfidence.for_prediction(
        prediction,
        probability_correct_ppm=probability_correct_ppm,
    )
    return fixture, state, run, admission, prediction, confidence


class ProbabilisticScoringTests(unittest.TestCase):
    def test_same_hard_decision_distinguishes_preoutcome_calibrated_from_overconfident(self) -> None:
        calibrated_case = _persistence_case("a_change", "run/wrong-calibrated", 310_000)
        overconfident_case = _persistence_case("a_change", "run/wrong-overconfident", 990_000)

        def score(case):
            fixture, state, run, admission, prediction, confidence = case
            return evaluate_admitted_prediction_confidence(
                fixture,
                state=state,
                action_id="a_change",
                prediction=prediction,
                confidence=confidence,
                run_descriptor=run,
                run_admission=admission,
                expected_run_admission_sha256=admission.sha256(),
                expected_confidence_sha256=confidence.sha256(),
            )[-1]

        calibrated = score(calibrated_case)
        overconfident = score(overconfident_case)
        self.assertEqual(calibrated.hard_score_delta, overconfident.hard_score_delta)
        self.assertEqual(calibrated.hard_outcome, overconfident.hard_outcome)
        self.assertLess(Decimal(calibrated.brier_loss), Decimal(overconfident.brier_loss))
        self.assertLess(Decimal(calibrated.log_loss_nats), Decimal(overconfident.log_loss_nats))

    def test_confidence_is_bound_to_exact_prediction(self) -> None:
        fixture, state, run, admission, prediction, confidence = _persistence_case(
            "b_stay", "run/correct", 700_000
        )
        forged = replace(confidence, prediction_sha256="0" * 64)
        with self.assertRaisesRegex(ProbabilisticScoringError, "provenance mismatch"):
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

    def test_wrong_expected_run_admission_digest_fails_before_step(self) -> None:
        fixture, state, run, admission, prediction, confidence = _persistence_case(
            "b_stay", "run/wrong-admission-pin", 700_000
        )
        with self.assertRaisesRegex(ProbabilisticScoringError, "predeclared expected digest"):
            evaluate_admitted_prediction_confidence(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=prediction,
                confidence=confidence,
                run_descriptor=run,
                run_admission=admission,
                expected_run_admission_sha256="9" * 64,
                expected_confidence_sha256=confidence.sha256(),
            )
        self.assertEqual(state.step_index, 0)

    def test_wrong_expected_confidence_digest_fails_before_step(self) -> None:
        fixture, state, run, admission, prediction, confidence = _persistence_case(
            "b_stay", "run/wrong-confidence-pin", 700_000
        )
        with self.assertRaisesRegex(ProbabilisticScoringError, "pre-outcome expected digest"):
            evaluate_admitted_prediction_confidence(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=prediction,
                confidence=confidence,
                run_descriptor=run,
                run_admission=admission,
                expected_run_admission_sha256=admission.sha256(),
                expected_confidence_sha256="8" * 64,
            )
        self.assertEqual(state.step_index, 0)

    def test_post_outcome_adaptive_confidence_replacement_fails_retained_digest(self) -> None:
        fixture, state, run, admission, prediction, pre_outcome_confidence = _persistence_case(
            "b_stay", "run/post-outcome-replacement", 600_000
        )
        retained_confidence_sha = pre_outcome_confidence.sha256()
        _, _, _, hard = evaluate_admitted_next_observation_prediction(
            fixture,
            state=state,
            action_id="b_stay",
            prediction=prediction,
            run_descriptor=run,
            run_admission=admission,
            expected_run_admission_sha256=admission.sha256(),
        )
        adaptive_ppm = 999_999 if hard.outcome == CORRECT else 1
        post_outcome_confidence = PredictionConfidence.for_prediction(
            prediction,
            probability_correct_ppm=adaptive_ppm,
        )
        with self.assertRaisesRegex(ProbabilisticScoringError, "pre-outcome expected digest"):
            evaluate_prediction_confidence(
                post_outcome_confidence,
                hard,
                prediction=prediction,
                run_admission=admission,
                expected_run_admission_sha256=admission.sha256(),
                expected_confidence_sha256=retained_confidence_sha,
            )

    def test_abstain_preserves_hard_semantics_and_gets_no_probability_score(self) -> None:
        fixture = _fixture()
        state, observation = begin_episode(fixture, episode_id="episode/abstain", episode_generation=1)
        policy_id = "policy/abstain"
        run = _run(fixture, run_id="run/abstain", policy_id=policy_id)
        admission = _admission(fixture, run, admission_id="admission/run-abstain")
        prediction = abstain_for_observation(
            observation,
            action_id="a_change",
            prediction_id="prediction/abstain",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
            policy_id=policy_id,
            policy_generation=1,
            policy_state_sha256="4" * 64,
        )
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
        self.assertEqual(scored.hard_score_delta, hard.benchmark_score_delta)
        self.assertEqual(scored.hard_score_delta, 0)
        self.assertEqual(scored.score_status, ABSTAIN_NOT_SCORED)
        self.assertIsNone(scored.brier_loss)
        self.assertIsNone(scored.log_loss_nats)

    def test_reliability_bins_are_evaluator_derived_from_admitted_rows(self) -> None:
        good_case = _persistence_case("b_stay", "run/good", 700_000)
        bad_case = _persistence_case("a_change", "run/bad", 300_000)
        rows = []
        for action_id, case in (("b_stay", good_case), ("a_change", bad_case)):
            fixture, state, run, admission, prediction, confidence = case
            rows.append(evaluate_admitted_prediction_confidence(
                fixture,
                state=state,
                action_id=action_id,
                prediction=prediction,
                confidence=confidence,
                run_descriptor=run,
                run_admission=admission,
                expected_run_admission_sha256=admission.sha256(),
                expected_confidence_sha256=confidence.sha256(),
            )[-1])
        bins = reliability_bins(rows, bin_width_ppm=500_000)
        self.assertEqual(len(bins), 2)
        self.assertEqual(sum(x.count for x in bins), 2)
        self.assertTrue(all(x.absolute_calibration_gap is not None for x in bins))

    def test_probability_domain_excludes_nonfinite_log_loss_endpoints(self) -> None:
        _, _, _, _, prediction, _ = _persistence_case("b_stay", "run/domain", 500_000)
        for invalid in (0, 1_000_000, True, -1):
            with self.assertRaises(ProbabilisticScoringError):
                PredictionConfidence.for_prediction(prediction, probability_correct_ppm=invalid)


if __name__ == "__main__":
    unittest.main()
