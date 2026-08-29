from __future__ import annotations

from dataclasses import fields, replace
import unittest

from frankenstein2.cognitive_microworld import (
    BASELINE,
    FIXTURE_SCHEMA,
    INTERVENTION,
    ActionSpec,
    CognitiveMicroWorldError,
    MicroWorldFixture,
    ObservationView,
    RunDescriptor,
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


def _run(
    fixture: MicroWorldFixture,
    *,
    run_id: str,
    system_under_test_ref: str,
    condition: str = INTERVENTION,
) -> RunDescriptor:
    return RunDescriptor.for_fixture(
        fixture,
        run_id=run_id,
        condition=condition,
        episode_family_id="episode-family/wp803",
        system_under_test_ref=system_under_test_ref,
        communication_before_result=False,
        independent_reproduction=True,
    )


class WorldModelPredictionBenchmarkTests(unittest.TestCase):
    def test_public_persistence_baseline_is_wrong_when_public_observation_changes(self) -> None:
        fixture, state, observation = _episode()
        run = _run(
            fixture,
            run_id="run/wp803-1",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        prediction = persistence_baseline(
            observation,
            action_id="a_change",
            prediction_id="prediction/persist-change",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        next_state, next_observation, evaluator_step, evaluation = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="a_change",
            prediction=prediction,
            run_descriptor=run,
        )
        self.assertEqual(prediction.prediction_kind, NEXT_OBSERVATION)
        self.assertEqual(prediction.action_id, "a_change")
        self.assertEqual(next_observation.observation_ref, "public/b")
        self.assertEqual(evaluation.outcome, INCORRECT)
        self.assertEqual(evaluation.benchmark_score_delta, -1)
        self.assertEqual(evaluation.fixture_sha256, fixture.sha256())
        self.assertEqual(evaluation.run_descriptor_sha256, run.sha256())
        self.assertEqual(evaluation.prior_state_sha256, state.sha256())
        self.assertEqual(evaluation.evaluator_step_sha256, evaluator_step.sha256())
        self.assertEqual(next_state.step_index, 1)

    def test_public_persistence_baseline_is_correct_when_public_observation_persists(self) -> None:
        fixture, state, observation = _episode()
        run = _run(
            fixture,
            run_id="run/wp803-2",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/persist-stay",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        _, next_observation, _, evaluation = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="b_stay",
            prediction=prediction,
            run_descriptor=run,
        )
        self.assertEqual(next_observation.observation_ref, observation.observation_ref)
        self.assertEqual(evaluation.outcome, CORRECT)
        self.assertEqual(evaluation.benchmark_score_delta, 1)

    def test_explicit_public_prediction_can_match_next_public_observation(self) -> None:
        fixture, state, observation = _episode()
        run = _run(fixture, run_id="run/wp803-3", system_under_test_ref="policy/test-explicit")
        prediction = prediction_for_observation(
            observation,
            action_id="a_change",
            prediction_id="prediction/explicit-b",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
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
            run_descriptor=run,
        )
        self.assertEqual(evaluation.outcome, CORRECT)
        self.assertEqual(evaluation.run_descriptor_sha256, run.sha256())

    def test_unknown_public_evidence_can_abstain_without_forced_guess(self) -> None:
        fixture, state, observation = _episode()
        run = _run(fixture, run_id="run/wp803-4", system_under_test_ref="policy/abstain")
        prediction = abstain_for_observation(
            observation,
            action_id="a_change",
            prediction_id="prediction/abstain",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
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
            run_descriptor=run,
        )
        self.assertEqual(evaluation.outcome, ABSTAINED)
        self.assertEqual(evaluation.benchmark_score_delta, 0)

    def test_generation1_run_id_relabel_falsifier_now_fails_closed_before_step(self) -> None:
        fixture, state, observation = _episode()
        run = _run(
            fixture,
            run_id="run/wp803-canonical",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/run-relabel",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        relabeled = replace(prediction, benchmark_run_id="run/wp803-forged-unbound")
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "prediction/run descriptor mismatch"):
            evaluate_next_observation_prediction(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=relabeled,
                run_descriptor=run,
            )
        self.assertEqual(state.step_index, 0)

    def test_run_descriptor_must_match_exact_fixture_before_step(self) -> None:
        fixture, state, observation = _episode()
        altered_fixture = replace(fixture, evidence_source_family="different-source-family")
        wrong_run = _run(
            altered_fixture,
            run_id="run/wp803-fixture-mismatch",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/fixture-mismatch",
            benchmark_run_id=wrong_run.run_id,
            benchmark_generation=2,
        )
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "run descriptor/fixture provenance mismatch"):
            evaluate_next_observation_prediction(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=prediction,
                run_descriptor=wrong_run,
            )
        self.assertEqual(state.step_index, 0)

    def test_run_descriptor_system_under_test_must_match_policy_before_step(self) -> None:
        fixture, state, observation = _episode()
        run = _run(
            fixture,
            run_id="run/wp803-sut-mismatch",
            system_under_test_ref="policy/other",
        )
        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/sut-mismatch",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
            policy_id="policy/expected",
        )
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "policy/run system-under-test mismatch"):
            evaluate_next_observation_prediction(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=prediction,
                run_descriptor=run,
            )
        self.assertEqual(state.step_index, 0)

    def test_run_descriptor_must_be_builder_originated(self) -> None:
        fixture, state, observation = _episode()
        canonical = _run(
            fixture,
            run_id="run/wp803-builder-origin",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        reconstructed = replace(canonical)
        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/builder-origin",
            benchmark_run_id=canonical.run_id,
            benchmark_generation=2,
        )
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "RunDescriptor.for_fixture"):
            evaluate_next_observation_prediction(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=prediction,
                run_descriptor=reconstructed,
            )
        self.assertEqual(state.step_index, 0)

    def test_prediction_is_bound_to_action_before_evaluator_step(self) -> None:
        fixture, state, observation = _episode()
        run = _run(
            fixture,
            run_id="run/wp803-action-bound",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/action-bound",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "action target mismatch"):
            evaluate_next_observation_prediction(
                fixture,
                state=state,
                action_id="a_change",
                prediction=prediction,
                run_descriptor=run,
            )
        self.assertEqual(state.step_index, 0)

    def test_prediction_constructor_rejects_nonpublic_action_target(self) -> None:
        _, _, observation = _episode()
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "not public-available"):
            persistence_baseline(
                observation,
                action_id="z_hidden_or_unknown",
                prediction_id="prediction/unknown-action",
                benchmark_run_id="run/wp803-unknown-action",
                benchmark_generation=2,
            )

    def test_terminal_observation_cannot_be_used_as_prediction_target(self) -> None:
        fixture, state, observation = _episode()
        run = _run(
            fixture,
            run_id="run/wp803-terminal-a",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        first = persistence_baseline(
            observation,
            action_id="a_change",
            prediction_id="prediction/to-terminal",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        next_state, next_observation, _, _ = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="a_change",
            prediction=first,
            run_descriptor=run,
        )
        self.assertTrue(next_observation.terminal)
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "terminal observation"):
            persistence_baseline(
                next_observation,
                action_id="a_change",
                prediction_id="prediction/after-terminal",
                benchmark_run_id="run/wp803-terminal-b",
                benchmark_generation=2,
            )
        self.assertEqual(next_state.step_index, 1)

    def test_prediction_provenance_generation_mismatch_fails_closed_before_scoring(self) -> None:
        fixture, state, observation = _episode()
        run = _run(
            fixture,
            run_id="run/wp803-5",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        prediction = persistence_baseline(
            observation,
            action_id="a_change",
            prediction_id="prediction/stale-generation",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        stale = replace(prediction, fixture_generation=prediction.fixture_generation + 1)
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "provenance mismatch"):
            evaluate_next_observation_prediction(
                fixture,
                state=state,
                action_id="a_change",
                prediction=stale,
                run_descriptor=run,
            )

    def test_prediction_observation_digest_mismatch_fails_closed_before_scoring(self) -> None:
        fixture, state, observation = _episode()
        run = _run(
            fixture,
            run_id="run/wp803-6",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        prediction = persistence_baseline(
            observation,
            action_id="a_change",
            prediction_id="prediction/stale-observation",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        stale = replace(prediction, observation_sha256="9" * 64)
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "provenance mismatch"):
            evaluate_next_observation_prediction(
                fixture,
                state=state,
                action_id="a_change",
                prediction=stale,
                run_descriptor=run,
            )

    def test_abstain_cannot_smuggle_a_predicted_public_value(self) -> None:
        _, _, observation = _episode()
        prediction = abstain_for_observation(
            observation,
            action_id="a_change",
            prediction_id="prediction/no-smuggle",
            benchmark_run_id="run/wp803-7",
            benchmark_generation=2,
            policy_id="policy/abstain",
            policy_generation=1,
            policy_state_sha256="5" * 64,
        )
        data = prediction.as_dict()
        data["predicted_observation_ref"] = "public/b"
        data["predicted_observation_sha256"] = "2" * 64
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "ABSTAIN"):
            PredictionCandidate(**data)

    def test_candidate_surface_contains_no_evaluator_run_or_hidden_state_fields(self) -> None:
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
            "run_descriptor_sha256",
            "evidence_source_family",
            "primary_source_ids",
            "donor_path_family",
            "method_family",
        }
        self.assertTrue(names.isdisjoint(forbidden))
        self.assertIn("action_id", names)
        self.assertIn("benchmark_run_id", names)

    def test_hidden_fixture_change_cannot_change_public_persistence_prediction(self) -> None:
        fixture, _, observation = _episode()
        altered = replace(
            fixture,
            transitions=(
                TransitionRule("n0", "a_change", "n0", "transition/change-hidden-alt", "7" * 64),
                TransitionRule("n0", "b_stay", "n1", "transition/stay-hidden-alt", "8" * 64),
            ),
        )
        _, altered_observation = begin_episode(altered, episode_id="episode/wp803", episode_generation=1)
        self.assertEqual(fixture.public_sha256(), altered.public_sha256())
        self.assertEqual(observation, altered_observation)
        p1 = persistence_baseline(
            observation,
            action_id="a_change",
            prediction_id="prediction/no-hidden-leak",
            benchmark_run_id="run/wp803-no-hidden-leak",
            benchmark_generation=2,
        )
        p2 = persistence_baseline(
            altered_observation,
            action_id="a_change",
            prediction_id="prediction/no-hidden-leak",
            benchmark_run_id="run/wp803-no-hidden-leak",
            benchmark_generation=2,
        )
        self.assertEqual(p1.sha256(), p2.sha256())

    def test_exact_concrete_public_observation_type_is_required(self) -> None:
        class EvilObservation(ObservationView):
            pass

        _, _, observation = _episode()
        evil = EvilObservation(**observation.as_dict())
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "exact concrete ObservationView"):
            persistence_baseline(
                evil,
                action_id="a_change",
                prediction_id="prediction/evil-observation",
                benchmark_run_id="run/wp803-evil-observation",
                benchmark_generation=2,
            )

    def test_evaluation_is_factory_only_evaluator_evidence(self) -> None:
        fixture, state, observation = _episode()
        run = _run(
            fixture,
            run_id="run/wp803-8",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        prediction = persistence_baseline(
            observation,
            action_id="a_change",
            prediction_id="prediction/factory-result",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        _, _, _, evaluation = evaluate_next_observation_prediction(
            fixture,
            state=state,
            action_id="a_change",
            prediction=prediction,
            run_descriptor=run,
        )
        with self.assertRaisesRegex(WorldModelPredictionBenchmarkError, "evaluator API"):
            PredictionEvaluation(**evaluation.as_dict())

    def test_canonical_wp800_replay_boundary_still_rejects_unroutable_public_action(self) -> None:
        fixture = replace(
            _fixture(),
            transitions=(
                TransitionRule("n0", "a_change", "n1", "transition/change", "e" * 64),
            ),
        )
        state, observation = begin_episode(fixture, episode_id="episode/wp803-unroutable", episode_generation=1)
        run = _run(
            fixture,
            run_id="run/wp803-9",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/unroutable-action",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        with self.assertRaises(CognitiveMicroWorldError):
            evaluate_next_observation_prediction(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=prediction,
                run_descriptor=run,
            )

    def test_replay_is_deterministic_for_same_fixture_episode_action_prediction_and_run(self) -> None:
        fixture, state_a, observation_a = _episode()
        state_b, observation_b = begin_episode(fixture, episode_id="episode/wp803", episode_generation=1)
        run_a = _run(
            fixture,
            run_id="run/wp803-10",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        run_b = _run(
            fixture,
            run_id="run/wp803-10",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            condition=BASELINE,
        )
        prediction_a = persistence_baseline(
            observation_a,
            action_id="a_change",
            prediction_id="prediction/replay",
            benchmark_run_id=run_a.run_id,
            benchmark_generation=2,
        )
        prediction_b = persistence_baseline(
            observation_b,
            action_id="a_change",
            prediction_id="prediction/replay",
            benchmark_run_id=run_b.run_id,
            benchmark_generation=2,
        )
        _, _, _, evaluation_a = evaluate_next_observation_prediction(
            fixture,
            state=state_a,
            action_id="a_change",
            prediction=prediction_a,
            run_descriptor=run_a,
        )
        _, _, _, evaluation_b = evaluate_next_observation_prediction(
            fixture,
            state=state_b,
            action_id="a_change",
            prediction=prediction_b,
            run_descriptor=run_b,
        )
        self.assertEqual(run_a.sha256(), run_b.sha256())
        self.assertEqual(prediction_a.sha256(), prediction_b.sha256())
        self.assertEqual(evaluation_a.sha256(), evaluation_b.sha256())


if __name__ == "__main__":
    unittest.main()
