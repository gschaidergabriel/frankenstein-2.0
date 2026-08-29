from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.cognitive_microworld import (
    FIXTURE_SCHEMA,
    ActionSpec,
    MicroWorldFixture,
    ObservationView,
    TransitionRule,
    WorldNode,
    begin_episode,
)
from frankenstein2.cognitive_transfer_recovery_benchmark import (
    CHECKPOINT_RESUME,
    COLD_RESTART,
    POLICY_STATE_SCHEMA,
    PublicPolicyState,
    RecoveryCheckpoint,
    TransferCase,
)
from frankenstein2.cognitive_transfer_recovery_e2 import (
    EvaluatorReferencePlan,
    EvaluatorResourceVector,
    MatchedRecoveryComparisonV2,
    PostChangeStartIdentity,
    RecoveryE2Error,
    RecoveryEfficiencySummaryV2,
    RecoveryPerturbation,
    RecoveryRunMeasurementV2,
    RecoveryScenario,
    RecoveryTraceReceipt,
    RecoveryTraceStep,
    StructuralFamilyVector,
)


def _actions() -> tuple[ActionSpec, ...]:
    return (
        ActionSpec("a_go", "action/go", "a" * 64),
        ActionSpec("b_wait", "action/wait", "b" * 64),
    )


def _fixture(
    name: str,
    *,
    holdout: str,
    evidence_family: str,
    donor_family: str,
    method_family: str,
    generation: int = 1,
) -> MicroWorldFixture:
    nodes = (
        WorldNode(f"{name}-n0", f"public/{name}/start", "1" * 64, f"hidden/{name}/start", "2" * 64, False, 0),
        WorldNode(f"{name}-n1", f"public/{name}/terminal", "3" * 64, f"hidden/{name}/terminal", "4" * 64, True, 10),
    )
    transitions = (
        TransitionRule(f"{name}-n0", "a_go", f"{name}-n1", f"transition/{name}/go", "5" * 64),
        TransitionRule(f"{name}-n0", "b_wait", f"{name}-n0", f"transition/{name}/wait", "6" * 64),
    )
    return MicroWorldFixture(
        FIXTURE_SCHEMA,
        f"fixture/{name}",
        generation,
        holdout,
        f"{name}-n0",
        4,
        _actions(),
        nodes,
        transitions,
        evidence_family,
        (f"source/{name}",),
        donor_family,
        method_family,
    )


def _context(*, structural_overlap: bool = False):
    source = _fixture(
        "source",
        holdout="holdout/source",
        evidence_family="family/evidence/source",
        donor_family="family/donor/source",
        method_family="family/method/source",
    )
    target = _fixture(
        "target",
        holdout="holdout/target",
        evidence_family="family/evidence/source" if structural_overlap else "family/evidence/target",
        donor_family="family/donor/source" if structural_overlap else "family/donor/target",
        method_family="family/method/source" if structural_overlap else "family/method/target",
    )
    case = TransferCase.create(
        source_fixture_id=source.fixture_id,
        source_fixture_generation=source.generation,
        source_holdout_set_id=source.holdout_set_id,
        source_public_fixture_sha256=source.public_sha256(),
        target_fixture_id=target.fixture_id,
        target_fixture_generation=target.generation,
        target_holdout_set_id=target.holdout_set_id,
        target_public_fixture_sha256=target.public_sha256(),
        episode_family_id="episode-family/wp805-g2",
        action_budget=4,
    )
    perturbation = RecoveryPerturbation.seal(
        source_fixture=source,
        target_fixture=target,
        perturbation_kind="LOCAL_RULE_CHANGE",
        change_generation=2,
        changed_component_refs=("component/navigation-rule",),
    )
    state, observation = begin_episode(target, episode_id="episode/postchange", episode_generation=2)
    return source, target, case, perturbation, state, observation


def _scenario():
    source, target, case, perturbation, state, observation = _context()
    scenario = RecoveryScenario.seal(
        case=case,
        source_fixture=source,
        target_fixture=target,
        perturbation=perturbation,
        target_start_state=state,
        target_start_observation=observation,
    )
    start = PostChangeStartIdentity.from_observation(observation)
    reference = EvaluatorReferencePlan.shortest_terminal(
        scenario=scenario,
        target_fixture=target,
        target_start_state=state,
        target_start_observation=observation,
    )
    policy = PublicPolicyState(
        POLICY_STATE_SCHEMA,
        "policy/wp805-g2",
        1,
        source.fixture_id,
        source.holdout_set_id,
        source.public_sha256(),
        "7" * 64,
        ("a_go", "b_wait"),
        4,
    )
    checkpoint = RecoveryCheckpoint.seal(
        case=case,
        policy=policy,
        observation=observation,
        action_history_sha256="8" * 64,
    )
    return source, target, case, scenario, state, observation, start, reference, checkpoint


def _trace(scenario: RecoveryScenario, start: PostChangeStartIdentity, *, reused: bool, repeat: bool = False):
    steps = [
        RecoveryTraceStep(
            "FRANKENSTEIN2_RECOVERY_TRACE_STEP/v2",
            0,
            "a_go",
            "work/plan-terminal",
            "prior/plan-terminal" if reused else None,
            reused,
        )
    ]
    if repeat:
        steps.append(
            RecoveryTraceStep(
                "FRANKENSTEIN2_RECOVERY_TRACE_STEP/v2",
                1,
                "b_wait",
                "work/plan-terminal",
                None,
                False,
            )
        )
    return RecoveryTraceReceipt.seal(scenario=scenario, start_identity=start, steps=tuple(steps))


class RecoveryE2Tests(unittest.TestCase):
    def test_structural_family_relabeling_is_rejected_even_with_distinct_holdout_ids(self):
        source, target, case, perturbation, state, observation = _context(structural_overlap=True)
        self.assertNotEqual(source.holdout_set_id, target.holdout_set_id)
        with self.assertRaisesRegex(RecoveryE2Error, "structural holdout overlap"):
            RecoveryScenario.seal(
                case=case,
                source_fixture=source,
                target_fixture=target,
                perturbation=perturbation,
                target_start_state=state,
                target_start_observation=observation,
            )

    def test_structural_family_vector_exposes_exact_wp800_split_metadata(self):
        source, target, *_ = _context()
        a = StructuralFamilyVector.from_fixture(source)
        b = StructuralFamilyVector.from_fixture(target)
        self.assertEqual(a.evidence_source_family, source.evidence_source_family)
        self.assertEqual(a.overlaps(b), ())
        self.assertNotEqual(a.sha256(), b.sha256())

    def test_perturbation_binds_exact_evaluator_source_target_and_causal_footprint(self):
        source, target, _, perturbation, *_ = _context()
        self.assertEqual(perturbation.source_fixture_sha256, source.sha256())
        self.assertEqual(perturbation.target_fixture_sha256, target.sha256())
        self.assertEqual(perturbation.changed_component_refs, ("component/navigation-rule",))
        self.assertEqual(len(perturbation.causal_footprint_sha256), 64)
        with self.assertRaisesRegex(RecoveryE2Error, "sealed by evaluator API"):
            RecoveryPerturbation(**perturbation.as_dict())

    def test_scenario_requires_public_start_to_match_exact_hidden_evaluator_state(self):
        source, target, case, perturbation, state, observation = _context()
        _, other_observation = begin_episode(target, episode_id="episode/other", episode_generation=2)
        with self.assertRaisesRegex(RecoveryE2Error, "does not match evaluator target state"):
            RecoveryScenario.seal(
                case=case,
                source_fixture=source,
                target_fixture=target,
                perturbation=perturbation,
                target_start_state=state,
                target_start_observation=other_observation,
            )
        self.assertNotEqual(observation.episode_id, other_observation.episode_id)

    def test_reference_plan_is_deterministic_shortest_terminal_oracle(self):
        _, _, _, scenario, _, _, start, reference, _ = _scenario()
        self.assertEqual(reference.action_ids, ("a_go",))
        self.assertEqual(reference.action_count, 1)
        self.assertEqual(reference.terminal_evaluator_score, 10)
        self.assertEqual(reference.start_identity_sha256, start.sha256())
        replay = _scenario()[7]
        self.assertEqual(reference.sha256(), replay.sha256())

    def test_trace_metrics_are_derived_from_bound_steps_not_free_counters(self):
        _, _, _, scenario, _, _, start, _, _ = _scenario()
        trace = _trace(scenario, start, reused=True, repeat=True)
        self.assertEqual(trace.actions_executed, 2)
        self.assertEqual(trace.replayed_steps, 1)
        self.assertEqual(trace.valid_reuse_steps, 1)
        self.assertEqual(trace.invalid_reuse_steps, 0)
        self.assertEqual(trace.repeated_work_steps, 1)
        with self.assertRaises(RecoveryE2Error):
            replace(trace, replayed_steps=0)

    def test_trace_records_invalid_reuse_separately(self):
        _, _, _, scenario, _, _, start, _, _ = _scenario()
        step = RecoveryTraceStep(
            "FRANKENSTEIN2_RECOVERY_TRACE_STEP/v2",
            0,
            "a_go",
            "work/plan-terminal",
            "prior/stale-plan",
            False,
        )
        trace = RecoveryTraceReceipt.seal(scenario=scenario, start_identity=start, steps=(step,))
        self.assertEqual(trace.replayed_steps, 1)
        self.assertEqual(trace.valid_reuse_steps, 0)
        self.assertEqual(trace.invalid_reuse_steps, 1)

    def test_checkpoint_resume_requires_exact_same_postchange_public_start(self):
        _, target, _, scenario, _, _, start, reference, checkpoint = _scenario()
        trace = _trace(scenario, start, reused=True)
        _, other_observation = begin_episode(target, episode_id="episode/different-start", episode_generation=2)
        other_start = PostChangeStartIdentity.from_observation(other_observation)
        self.assertNotEqual(start.sha256(), other_start.sha256())
        with self.assertRaisesRegex(RecoveryE2Error, "run start identity does not match scenario"):
            RecoveryRunMeasurementV2.measure(
                run_id="run/bad-start",
                mode=CHECKPOINT_RESUME,
                scenario=scenario,
                start_identity=other_start,
                reference_plan=reference,
                trace=trace,
                checkpoint=checkpoint,
                final_evaluator_score=10,
                terminal=True,
            )

    def test_cold_and_resume_compare_only_at_same_start_oracle_and_scenario(self):
        _, _, _, scenario, _, _, start, reference, checkpoint = _scenario()
        cold_trace = _trace(scenario, start, reused=False, repeat=True)
        resume_trace = _trace(scenario, start, reused=True)
        cold = RecoveryRunMeasurementV2.measure(
            run_id="run/cold",
            mode=COLD_RESTART,
            scenario=scenario,
            start_identity=start,
            reference_plan=reference,
            trace=cold_trace,
            checkpoint=None,
            final_evaluator_score=10,
            terminal=True,
        )
        resume = RecoveryRunMeasurementV2.measure(
            run_id="run/resume",
            mode=CHECKPOINT_RESUME,
            scenario=scenario,
            start_identity=start,
            reference_plan=reference,
            trace=resume_trace,
            checkpoint=checkpoint,
            final_evaluator_score=10,
            terminal=True,
        )
        comparison = MatchedRecoveryComparisonV2.create(cold_restart=cold, checkpoint_resume=resume)
        summary = RecoveryEfficiencySummaryV2.from_comparison(comparison)
        self.assertEqual(summary.action_delta, -1)
        self.assertEqual(summary.action_regret_delta, -1)
        self.assertEqual(summary.score_regret_delta, 0)
        self.assertEqual(summary.valid_reuse_delta, 1)
        self.assertEqual(summary.repeated_work_delta, -1)
        self.assertEqual(summary.runtime_credit, 0)
        self.assertFalse(summary.whole_system_acceptance)

    def test_reference_regret_distinguishes_cheaper_wrong_result_from_optimal_terminal(self):
        _, _, _, scenario, _, _, start, reference, _ = _scenario()
        trace = RecoveryTraceReceipt.seal(scenario=scenario, start_identity=start, steps=())
        cold = RecoveryRunMeasurementV2.measure(
            run_id="run/cheap-wrong",
            mode=COLD_RESTART,
            scenario=scenario,
            start_identity=start,
            reference_plan=reference,
            trace=trace,
            checkpoint=None,
            final_evaluator_score=0,
            terminal=False,
        )
        self.assertEqual(cold.actions_executed, 0)
        self.assertEqual(cold.action_regret, -1)
        self.assertEqual(cold.score_regret, 10)
        self.assertFalse(cold.terminal)

    def test_optional_resource_vector_is_bound_and_compared_without_runtime_credit(self):
        _, _, _, scenario, _, _, start, reference, checkpoint = _scenario()
        cold_resource = EvaluatorResourceVector(
            "FRANKENSTEIN2_EVALUATOR_RESOURCE_VECTOR/v2",
            model_calls=2,
            input_tokens=100,
            output_tokens=20,
            latency_us=1000,
            cpu_time_us=800,
            peak_rss_bytes=5000,
            io_bytes=200,
        )
        resume_resource = EvaluatorResourceVector(
            "FRANKENSTEIN2_EVALUATOR_RESOURCE_VECTOR/v2",
            model_calls=1,
            input_tokens=60,
            output_tokens=10,
            latency_us=700,
            cpu_time_us=500,
            peak_rss_bytes=4500,
            io_bytes=100,
        )
        cold = RecoveryRunMeasurementV2.measure(
            run_id="run/resource-cold",
            mode=COLD_RESTART,
            scenario=scenario,
            start_identity=start,
            reference_plan=reference,
            trace=_trace(scenario, start, reused=False, repeat=True),
            checkpoint=None,
            final_evaluator_score=10,
            terminal=True,
            resource_vector=cold_resource,
        )
        resume = RecoveryRunMeasurementV2.measure(
            run_id="run/resource-resume",
            mode=CHECKPOINT_RESUME,
            scenario=scenario,
            start_identity=start,
            reference_plan=reference,
            trace=_trace(scenario, start, reused=True),
            checkpoint=checkpoint,
            final_evaluator_score=10,
            terminal=True,
            resource_vector=resume_resource,
        )
        summary = RecoveryEfficiencySummaryV2.from_comparison(
            MatchedRecoveryComparisonV2.create(cold_restart=cold, checkpoint_resume=resume)
        )
        self.assertEqual(summary.resource_delta["model_calls"], -1)
        self.assertEqual(summary.resource_delta["input_tokens"], -40)
        self.assertEqual(summary.resource_delta["latency_us"], -300)
        self.assertEqual(resume.runtime_credit, 0)

    def test_exact_concrete_observation_is_required_for_public_start_identity(self):
        class EvilObservation(ObservationView):
            pass

        _, _, _, _, _, observation = _context()
        evil = EvilObservation(**observation.as_dict())
        with self.assertRaisesRegex(RecoveryE2Error, "exact concrete ObservationView"):
            PostChangeStartIdentity.from_observation(evil)

    def test_manual_run_construction_cannot_self_attest(self):
        _, _, _, scenario, _, _, start, reference, _ = _scenario()
        trace = _trace(scenario, start, reused=False)
        cold = RecoveryRunMeasurementV2.measure(
            run_id="run/factory",
            mode=COLD_RESTART,
            scenario=scenario,
            start_identity=start,
            reference_plan=reference,
            trace=trace,
            checkpoint=None,
            final_evaluator_score=10,
            terminal=True,
        )
        with self.assertRaisesRegex(RecoveryE2Error, "created by evaluator API"):
            RecoveryRunMeasurementV2(**cold.as_dict())


if __name__ == "__main__":
    unittest.main()
