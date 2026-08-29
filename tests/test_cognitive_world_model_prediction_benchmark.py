from __future__ import annotations

from dataclasses import fields, replace
import unittest

from frankenstein2.cognitive_microworld import (
    FIXTURE_SCHEMA,
    ActionSpec,
    CognitiveMicroWorldError,
    MicroWorldFixture,
    TransitionRule,
    WorldNode,
    begin_episode,
)
from frankenstein2.cognitive_world_model_prediction_benchmark import (
    ABSTAIN,
    ABSTAINED,
    CORRECT,
    INCORRECT,
    NEXT_OBSERVATION,
    PredictionCandidate,
    PredictionEvaluation,
    WorldModelPredictionBenchmarkError,
    abstain_for_observation,
    evaluate_next_observation_prediction,
    persistence_baseline,
    prediction_for_observation,
)


def _fixture() -> MicroWorldFixture:
    return MicroWorldFixture(
        FIXTURE_SCHEMA,
        "fixture/wp803-heldout-1",
        1,
        "holdout/wp803",
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
        ("source/wp803",),
        "donor/none",
        "method/world-model-prediction",
    )


def _episode():
    fixture = _fixture()
    state, observation = begin_episode(fixture, episode_id="episode/wp803", episode_generation=1)
    return fixture, state, observation


class WorldModelPredictionBenchmarkTests(unittest.TestCase):
    def test_public_persistence_baseline_is_wrong_when_public_observation_changes(self) -> None:
        fixture, state, observation = _episode()
        prediction = persistence_baseline(
            observation,
            prediction_id="prediction/persist-change",
            benchmark_run_id="run/wp803-1",
            benchmark_generation=1,
        )
        next_state, next_observation, evaluator_step, evaluation = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="a_change",
            prediction=prediction,
        )
        self.assertEqual(prediction.prediction_kind, NEXT_OBSERVATION)
        self.assertEqual(next_observation.observation_ref, "public/b")
        self.assertEqual(evaluation.outcome, INCORRECT)
        self.assertEqual(evaluation.benchmark_score_delta, -1)
        self.assertEqual(evaluation.fixture_sha256, fixture.sha256())
        self.assertEqual(evaluation.prior_state_sha256, state.sha256())
        self.assertEqual(evaluation.evaluator_step_sha256, evaluator_step.sha256())
        self.assertEqual(next_state.step_index, 1)

    def test_public_persistence_baseline_is_correct_when_public_observation_persists(self) -> None:
        fixture, state, observation = _episode()
        prediction = persistence_baseline(
            observation,
            prediction_id="prediction/persist-stay",
            benchmark_run_id="run/wp803-2",
            benchmark_generation=1,
        )
        _, next_observation, _, evaluation = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="b_stay",
            prediction=prediction,
        )
        self.assertEqual(next_observation.observation_ref, observation.observation_ref)
        self.assertEqual(evaluation.outcome, CORRECT)
        self.assertEqual(evaluation.benchmark_score_delta, 1)

    def test_explicit_public_prediction_can_match_next_public_observation(self) -> None:
        fixture, state, observation = _episode()
        prediction = prediction_for_observation(
            observation,
            prediction_id="prediction/explicit-b",
            benchmark_run_id="run/wp803-3",
            benchmark_generation=1,
            policy_id="policy/test-explicit",
            policy_generation=1,
            policy_state_sha256="3" * 64,
            predicted_observation_ref="public/b",
            predicted_observation_sha256="2" * 64,
        )
        _, _, _, evaluation = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="a_change",
            prediction=prediction,
        )
        self.assertEqual(evaluation.outcome, CORRECT)
        self.assertEqual(evaluation.benchmark_score_delta, 1)

    def test_unknown_public_evidence_can_abstain_without_forced_guess(self) -> None:
        fixture, state, observation = _episode()
        prediction = abstain_for_observation(
            observation,
            prediction_id="prediction/abstain",
            benchmark_run_id="run/wp803-4",
            benchmark_generation=1,
            policy_id="policy/abstain",
            policy_generation=1,
            policy_state_sha256="4" * 64,
        )
        self.assertEqual(prediction.prediction_kind, ABSTAIN)
        _, _, _, evaluation = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="a_change",
            prediction=prediction,
        )
        self.assertEqual(evaluation.outcome, ABSTAINED)
        self.assertEqual(evaluation.benchmark_score_delta, 0)

    def test_prediction_provenance_generation_mismatch_fails_closed_before_scoring(self) -> None:
        fixture, state, observation = _episode()
        prediction = persistence_baseline(
            observation,
            prediction_id="prediction/stale-generation",
            benchmark_run_id="run/wp803-5",
            benchmark_generation=1,
        )
        stale = replace(prediction, fixture_generation=prediction.fixture_generation + 1)
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "provenance mismatch"):
            evaluate_next_observation_prediction(fixture, state=state, action_id="a_change", prediction=stale)

    def test_prediction_observation_digest_mismatch_fails_closed_before_scoring(self) -> None:
        fixture, state, observation = _episode()
        prediction = persistence_baseline(
            observation,
            prediction_id="prediction/stale-observation",
            benchmark_run_id="run/wp803-6",
            benchmark_generation=1,
        )
        stale = replace(prediction, observation_sha256="9" * 64)
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "provenance mismatch"):
            evaluate_next_observation_prediction(fixture, state=state, action_id="a_change", prediction=stale)

    def test_abstain_cannot_smuggle_a_predicted_public_value(self) -> None:
        _, _, observation = _episode()
        prediction = abstain_for_observation(
            observation,
            prediction_id="prediction/no-smuggle",
            benchmark_run_id="run/wp803-7",
            benchmark_generation=1,
            policy_id="policy/abstain",
            policy_generation=1,
            policy_state_sha256="5" * 64,
        )
        data = prediction.as_dict()
        data["predicted_observation_ref"] = "public/b"
        data["predicted_observation_sha256"] = "2" * 64
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "ABSTAIN"):
            PredictionCandidate(**data)

    def test_candidate_surface_contains_no_evaluator_hidden_state_fields(self) -> None:
        names = {field.name for field in fields(PredictionCandidate)}
        forbidden = {
            "current_node_id",
            "to_node_id",
            "transition_ref",
            "transition_sha256",
            "hidden_ground_truth_ref",
            "hidden_ground_truth_sha256",
            "evaluator_score",
            "fixture_sha256",
        }
        self.assertTrue(names.isdisjoint(forbidden))

    def test_evaluation_is_factory_only_evaluator_evidence(self) -> None:
        fixture, state, observation = _episode()
        prediction = persistence_baseline(
            observation,
            prediction_id="prediction/factory-result",
            benchmark_run_id="run/wp803-8",
            benchmark_generation=1,
        )
        _, _, _, evaluation = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="a_change",
            prediction=prediction,
        )
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "evaluator API"):
            PredictionEvaluation(**evaluation.as_dict())

    def test_canonical_wp800_replay_boundary_still_rejects_unknown_action(self) -> None:
        fixture, state, observation = _episode()
        prediction = persistence_baseline(
            observation,
            prediction_id="prediction/invalid-action",
            benchmark_run_id="run/wp803-9",
            benchmark_generation=1,
        )
        with self.assertRaises(CognitiveMicroWorldError):
            evaluate_next_observation_prediction(
                fixture,
                state=state,
                action_id="z_unknown",
                prediction=prediction,
            )

    def test_replay_is_deterministic_for_same_fixture_episode_action_and_prediction(self) -> None:
        fixture, state_a, observation_a = _episode()
        state_b, observation_b = begin_episode(fixture, episode_id="episode/wp803", episode_generation=1)
        prediction_a = persistence_baseline(
            observation_a,
            prediction_id="prediction/replay",
            benchmark_run_id="run/wp803-10",
            benchmark_generation=1,
        )
        prediction_b = persistence_baseline(
            observation_b,
            prediction_id="prediction/replay",
            benchmark_run_id="run/wp803-10",
            benchmark_generation=1,
        )
        _, _, _, evaluation_a = evaluate_next_observation_prediction(
            fixture,
            state=state_a,
            action_id="a_change",
            prediction=prediction_a,
        )
        _, _, _, evaluation_b = evaluate_next_observation_prediction(
            fixture,
            state=state_b,
            action_id="a_change",
            prediction=prediction_b,
        )
        self.assertEqual(prediction_a.sha256(), prediction_b.sha256())
        self.assertEqual(evaluation_a.sha256(), evaluation_b.sha256())


if __name__ == "__main__":
    unittest.main()
