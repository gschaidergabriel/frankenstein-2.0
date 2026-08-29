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
from frankenstein2.cognitive_world_model_prediction_benchmark import persistence_baseline
from frankenstein2.cognitive_world_model_run_admission import (
    BenchmarkRunAdmission,
    BenchmarkRunAdmissionError,
    evaluate_admitted_next_observation_prediction,
)


def _fixture() -> MicroWorldFixture:
    return MicroWorldFixture(
        FIXTURE_SCHEMA,
        "fixture/wp803-admission-1",
        1,
        "holdout/wp803-admission",
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
        ("source/wp803-admission",),
        "donor/none",
        "method/world-model-prediction-admission",
    )


def _run(fixture: MicroWorldFixture, *, run_id: str, system_under_test_ref: str) -> RunDescriptor:
    return RunDescriptor.for_fixture(
        fixture,
        run_id=run_id,
        condition=BASELINE,
        episode_family_id="episode-family/wp803-admission",
        system_under_test_ref=system_under_test_ref,
        communication_before_result=False,
        independent_reproduction=True,
    )


def _admission(
    fixture: MicroWorldFixture,
    run: RunDescriptor,
    *,
    admission_id: str = "admission/wp803-canonical",
    benchmark_generation: int = 2,
) -> BenchmarkRunAdmission:
    return BenchmarkRunAdmission.predeclare(
        fixture,
        run,
        admission_id=admission_id,
        manifest_ref="run-manifest/wp803-canonical",
        benchmark_generation=benchmark_generation,
    )


class WorldModelRunAdmissionTests(unittest.TestCase):
    def test_predeclared_admission_allows_exact_intended_run(self) -> None:
        fixture = _fixture()
        state, observation = begin_episode(fixture, episode_id="episode/wp803-admission", episode_generation=1)
        run = _run(fixture, run_id="run/wp803-canonical", system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE")
        admission = _admission(fixture, run)
        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/wp803-canonical",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        next_state, _, _, evaluation = evaluate_admitted_next_observation_prediction(
            fixture,
            state=state,
            action_id="b_stay",
            prediction=prediction,
            run_descriptor=run,
            run_admission=admission,
            expected_run_admission_sha256=admission.sha256(),
        )
        self.assertEqual(next_state.step_index, 1)
        self.assertEqual(evaluation.benchmark_generation, 2)
        self.assertEqual(evaluation.run_descriptor_sha256, run.sha256())

    def test_generation_self_attestation_fails_against_predeclared_admission_before_step(self) -> None:
        fixture = _fixture()
        state, observation = begin_episode(fixture, episode_id="episode/wp803-generation", episode_generation=1)
        run = _run(fixture, run_id="run/wp803-generation", system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE")
        admission = _admission(fixture, run)
        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/wp803-generation",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        forged = replace(prediction, benchmark_generation=999999)
        with self.assertRaisesRegex(BenchmarkRunAdmissionError, "benchmark generation/admission mismatch"):
            evaluate_admitted_next_observation_prediction(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=forged,
                run_descriptor=run,
                run_admission=admission,
                expected_run_admission_sha256=admission.sha256(),
            )
        self.assertEqual(state.step_index, 0)

    def test_run_and_sut_coforge_fails_against_original_predeclared_admission(self) -> None:
        fixture = _fixture()
        state, observation = begin_episode(fixture, episode_id="episode/wp803-coforge", episode_generation=1)
        run = _run(fixture, run_id="run/wp803-canonical", system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE")
        admission = _admission(fixture, run)
        prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/wp803-coforge",
            benchmark_run_id=run.run_id,
            benchmark_generation=2,
        )
        forged_prediction = replace(
            prediction,
            benchmark_run_id="run/wp803-forged",
            policy_id="policy/wp803-forged",
        )
        forged_run = _run(
            fixture,
            run_id="run/wp803-forged",
            system_under_test_ref="policy/wp803-forged",
        )
        with self.assertRaisesRegex(BenchmarkRunAdmissionError, "run descriptor digest/admission mismatch"):
            evaluate_admitted_next_observation_prediction(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=forged_prediction,
                run_descriptor=forged_run,
                run_admission=admission,
                expected_run_admission_sha256=admission.sha256(),
            )
        self.assertEqual(state.step_index, 0)

    def test_fresh_posthoc_compatible_admission_cannot_replace_pinned_expected_digest(self) -> None:
        fixture = _fixture()
        state, observation = begin_episode(fixture, episode_id="episode/wp803-posthoc", episode_generation=1)
        canonical_run = _run(
            fixture,
            run_id="run/wp803-canonical",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
        )
        canonical_admission = _admission(fixture, canonical_run)
        canonical_prediction = persistence_baseline(
            observation,
            action_id="b_stay",
            prediction_id="prediction/wp803-posthoc",
            benchmark_run_id=canonical_run.run_id,
            benchmark_generation=2,
        )
        forged_prediction = replace(
            canonical_prediction,
            benchmark_run_id="run/wp803-posthoc-forged",
            policy_id="policy/wp803-posthoc-forged",
        )
        forged_run = _run(
            fixture,
            run_id="run/wp803-posthoc-forged",
            system_under_test_ref="policy/wp803-posthoc-forged",
        )
        forged_admission = BenchmarkRunAdmission.predeclare(
            fixture,
            forged_run,
            admission_id="admission/wp803-posthoc-forged",
            manifest_ref="run-manifest/wp803-posthoc-forged",
            benchmark_generation=2,
        )
        self.assertNotEqual(forged_admission.sha256(), canonical_admission.sha256())
        with self.assertRaisesRegex(BenchmarkRunAdmissionError, "predeclared expected digest"):
            evaluate_admitted_next_observation_prediction(
                fixture,
                state=state,
                action_id="b_stay",
                prediction=forged_prediction,
                run_descriptor=forged_run,
                run_admission=forged_admission,
                expected_run_admission_sha256=canonical_admission.sha256(),
            )
        self.assertEqual(state.step_index, 0)

    def test_admission_cannot_be_reconstructed_by_plain_dataclass_replace(self) -> None:
        fixture = _fixture()
        run = _run(fixture, run_id="run/wp803-origin", system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE")
        admission = _admission(fixture, run)
        with self.assertRaisesRegex(BenchmarkRunAdmissionError, "must be created by predeclare"):
            replace(admission)


if __name__ == "__main__":
    unittest.main()
