from __future__ import annotations

from dataclasses import replace
import math
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
    INCORRECT,
    abstain_for_observation,
    persistence_baseline,
    prediction_for_observation,
)
from frankenstein2.cognitive_world_model_probability_evaluation import (
    ProbabilityCorrectClaim,
    WorldModelProbabilityEvaluationError,
    evaluate_probability_quality,
    proper_binary_scores,
)
from frankenstein2.cognitive_world_model_run_admission import (
    BenchmarkRunAdmission,
    evaluate_admitted_next_observation_prediction,
)


def _fixture() -> MicroWorldFixture:
    return MicroWorldFixture(
        FIXTURE_SCHEMA,
        "fixture/wp803-probability-candidate",
        1,
        "holdout/wp803-probability-candidate",
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
        ("source/wp803-probability-candidate",),
        "donor/none",
        "method/world-model-probability-candidate",
    )


def _run(fixture: MicroWorldFixture, *, run_id: str, policy_id: str) -> RunDescriptor:
    return RunDescriptor.for_fixture(
        fixture,
        run_id=run_id,
        condition=BASELINE,
        episode_family_id="episode-family/wp803-probability-candidate",
        system_under_test_ref=policy_id,
        communication_before_result=False,
        independent_reproduction=True,
    )


def _admit(fixture: MicroWorldFixture, run: RunDescriptor, *, admission_id: str) -> BenchmarkRunAdmission:
    return BenchmarkRunAdmission.predeclare(
        fixture,
        run,
        admission_id=admission_id,
        manifest_ref="manifest/wp803-probability-candidate",
        benchmark_generation=2,
    )


class WorldModelProbabilityEvaluationTests(unittest.TestCase):
    def test_probability_score_binds_existing_predeclared_admission(self) -> None:
        fixture = _fixture()
        state, observation = begin_episode(fixture, episode_id="episode/probability-correct", episode_generation=1)
        policy_id = "policy/probability-correct"
        run = _run(fixture, run_id="run/wp803-probability-correct", policy_id=policy_id)
        admission = _admit(fixture, run, admission_id="admission/wp803-probability-correct")
        expected_admission_sha = admission.sha256()

        prediction = prediction_for_observation(
            observation,
            action_id="a_change",
            prediction_id="prediction/probability-correct",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
            policy_id=policy_id,
            policy_generation=1,
            policy_state_sha256="3" * 64,
            predicted_observation_ref="public/b",
            predicted_observation_sha256="2" * 64,
        )
        claim = ProbabilityCorrectClaim.for_prediction(
            prediction,
            probability_claim_id="probability-claim/correct-70pct",
            probability_correct_ppm=700_000,
        )
        _, _, _, hard = evaluate_admitted_next_observation_prediction(
            fixture,
            state=state,
            action_id="a_change",
            prediction=prediction,
            run_descriptor=run,
            run_admission=admission,
            expected_run_admission_sha256=expected_admission_sha,
        )
        score = evaluate_probability_quality(
            claim,
            prediction=prediction,
            hard_evaluation=hard,
            run_admission=admission,
            expected_run_admission_sha256=expected_admission_sha,
        )

        self.assertEqual(hard.outcome, CORRECT)
        self.assertEqual(score.target_correct, 1)
        self.assertEqual(score.run_admission_sha256, expected_admission_sha)
        self.assertAlmostEqual(score.brier_score, 0.09)
        self.assertAlmostEqual(score.log_loss, -math.log(0.7))

    def test_wrong_hard_prediction_penalizes_overconfidence(self) -> None:
        fixture = _fixture()
        state, observation = begin_episode(fixture, episode_id="episode/probability-wrong", episode_generation=1)
        policy_id = "PUBLIC_PERSISTENCE_BASELINE"
        run = _run(fixture, run_id="run/wp803-probability-wrong", policy_id=policy_id)
        admission = _admit(fixture, run, admission_id="admission/wp803-probability-wrong")
        expected_admission_sha = admission.sha256()
        prediction = persistence_baseline(
            observation,
            action_id="a_change",
            prediction_id="prediction/probability-wrong",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        claim = ProbabilityCorrectClaim.for_prediction(
            prediction,
            probability_claim_id="probability-claim/wrong-90pct",
            probability_correct_ppm=900_000,
        )
        _, _, _, hard = evaluate_admitted_next_observation_prediction(
            fixture,
            state=state,
            action_id="a_change",
            prediction=prediction,
            run_descriptor=run,
            run_admission=admission,
            expected_run_admission_sha256=expected_admission_sha,
        )
        score = evaluate_probability_quality(
            claim,
            prediction=prediction,
            hard_evaluation=hard,
            run_admission=admission,
            expected_run_admission_sha256=expected_admission_sha,
        )

        self.assertEqual(hard.outcome, INCORRECT)
        self.assertEqual(score.target_correct, 0)
        self.assertAlmostEqual(score.brier_score, 0.81)
        self.assertAlmostEqual(score.log_loss, -math.log(0.1))

    def test_same_hard_decisions_now_distinguish_probability_quality(self) -> None:
        # Mirrors the admitted research falsifier: the hard decisions/outcomes are fixed.
        # Only confidence changes. Two errors make blanket 0.99 confidence materially worse.
        targets = (1, 1, 0, 1, 1, 1, 0, 1, 1, 1)
        calibrated_ppm = (700_000, 680_000, 690_000, 660_000, 640_000, 710_000, 710_000, 660_000, 640_000, 620_000)
        overconfident_ppm = (990_000,) * len(targets)

        calibrated = [proper_binary_scores(p, t) for p, t in zip(calibrated_ppm, targets)]
        overconfident = [proper_binary_scores(p, t) for p, t in zip(overconfident_ppm, targets)]
        calibrated_brier = sum(v[0] for v in calibrated) / len(calibrated)
        overconfident_brier = sum(v[0] for v in overconfident) / len(overconfident)
        calibrated_log = sum(v[1] for v in calibrated) / len(calibrated)
        overconfident_log = sum(v[1] for v in overconfident) / len(overconfident)

        self.assertEqual(sum(targets), 8)  # same 0.8 hard accuracy in both confidence variants
        self.assertLess(calibrated_brier, overconfident_brier)
        self.assertLess(calibrated_log, overconfident_log)

    def test_fresh_or_wrong_admission_digest_cannot_replace_pinned_identity(self) -> None:
        fixture = _fixture()
        state, observation = begin_episode(fixture, episode_id="episode/probability-admission", episode_generation=1)
        policy_id = "PUBLIC_PERSISTENCE_BASELINE"
        run = _run(fixture, run_id="run/wp803-probability-admission", policy_id=policy_id)
        admission = _admit(fixture, run, admission_id="admission/wp803-probability-admission")
        expected_admission_sha = admission.sha256()
        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/probability-admission",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        claim = ProbabilityCorrectClaim.for_prediction(
            prediction,
            probability_claim_id="probability-claim/admission",
            probability_correct_ppm=600_000,
        )
        _, _, _, hard = evaluate_admitted_next_observation_prediction(
            fixture,
            state=state,
            action_id="b_stay",
            prediction=prediction,
            run_descriptor=run,
            run_admission=admission,
            expected_run_admission_sha256=expected_admission_sha,
        )

        with self.assertRaisesRegex(WorldModelProbabilityEvaluationError, "predeclared expected digest"):
            evaluate_probability_quality(
                claim,
                prediction=prediction,
                hard_evaluation=hard,
                run_admission=admission,
                expected_run_admission_sha256="9" * 64,
            )

    def test_probability_claim_is_bound_to_exact_prediction_digest(self) -> None:
        fixture = _fixture()
        state, observation = begin_episode(fixture, episode_id="episode/probability-binding", episode_generation=1)
        policy_id = "PUBLIC_PERSISTENCE_BASELINE"
        run = _run(fixture, run_id="run/wp803-probability-binding", policy_id=policy_id)
        admission = _admit(fixture, run, admission_id="admission/wp803-probability-binding")
        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/probability-binding",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        claim = ProbabilityCorrectClaim.for_prediction(
            prediction,
            probability_claim_id="probability-claim/binding",
            probability_correct_ppm=600_000,
        )
        _, _, _, hard = evaluate_admitted_next_observation_prediction(
            fixture,
            state=state,
            action_id="b_stay",
            prediction=prediction,
            run_descriptor=run,
            run_admission=admission,
            expected_run_admission_sha256=admission.sha256(),
        )
        forged_claim = replace(claim, prediction_sha256="8" * 64)
        with self.assertRaisesRegex(WorldModelProbabilityEvaluationError, "claim/prediction provenance mismatch"):
            evaluate_probability_quality(
                forged_claim,
                prediction=prediction,
                hard_evaluation=hard,
                run_admission=admission,
                expected_run_admission_sha256=admission.sha256(),
            )

    def test_abstention_cannot_be_given_a_probability_score(self) -> None:
        fixture = _fixture()
        _, observation = begin_episode(fixture, episode_id="episode/probability-abstain", episode_generation=1)
        prediction = abstain_for_observation(
            observation,
            action_id="a_change",
            prediction_id="prediction/probability-abstain",
            benchmark_run_id="run/wp803-probability-abstain",
            benchmark_generation=2,
            policy_id="policy/abstain",
            policy_generation=1,
            policy_state_sha256="4" * 64,
        )
        with self.assertRaisesRegex(WorldModelProbabilityEvaluationError, "ABSTAIN"):
            ProbabilityCorrectClaim.for_prediction(
                prediction,
                probability_claim_id="probability-claim/abstain",
                probability_correct_ppm=500_000,
            )

    def test_exact_certainty_is_rejected_instead_of_hidden_log_loss_clipping(self) -> None:
        with self.assertRaisesRegex(WorldModelProbabilityEvaluationError, "\[1, 999999\]"):
            proper_binary_scores(1_000_000, 1)
        with self.assertRaisesRegex(WorldModelProbabilityEvaluationError, "\[1, 999999\]"):
            proper_binary_scores(0, 0)


if __name__ == "__main__":
    unittest.main()
