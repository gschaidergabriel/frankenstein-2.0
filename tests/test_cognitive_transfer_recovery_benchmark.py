from __future__ import annotations
from dataclasses import replace
import hashlib
import unittest

from frankenstein2.cognitive_microworld import OBSERVATION_SCHEMA, ObservationView
from frankenstein2.cognitive_transfer_recovery_benchmark import (
    CHECKPOINT_RESUME,
    COLD_RESTART,
    POLICY_STATE_SCHEMA,
    PublicPolicyState,
    TransferCase,
    RecoveryCheckpoint,
    EvaluatorExecutionTrace,
    EvaluatorRunMeasurement,
    MatchedRecoveryComparison,
    EfficiencySummary,
    TransferRecoveryBenchmarkError,
    assert_public_only_payload,
)


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def observation(*, step: int = 2, episode_generation: int = 4, ref: str = "obs:public-room") -> ObservationView:
    return ObservationView(
        schema=OBSERVATION_SCHEMA,
        episode_id="ep-target-1",
        episode_generation=episode_generation,
        fixture_id="heldout.target.001",
        fixture_generation=3,
        public_fixture_sha256=h("target-public-fixture"),
        step_index=step,
        observation_ref=ref,
        observation_sha256=h(ref),
        available_action_ids=("left", "right"),
        terminal=False,
    )


def case() -> TransferCase:
    return TransferCase.create(
        source_fixture_id="train.source.001",
        source_fixture_generation=1,
        source_holdout_set_id="source-family-v1",
        source_public_fixture_sha256=h("source-public-fixture"),
        target_fixture_id="heldout.target.001",
        target_fixture_generation=3,
        target_holdout_set_id="target-family-v1",
        target_public_fixture_sha256=h("target-public-fixture"),
        episode_family_id="transfer-family-1",
        action_budget=8,
    )


def policy() -> PublicPolicyState:
    return PublicPolicyState(
        POLICY_STATE_SCHEMA,
        "policy:public-only-v1",
        2,
        "train.source.001",
        "source-family-v1",
        h("source-public-fixture"),
        h("policy-artifact"),
        ("left", "right"),
        8,
    )


def checkpoint(*, obs: ObservationView | None = None) -> RecoveryCheckpoint:
    return RecoveryCheckpoint.seal(
        case=case(),
        policy=policy(),
        observation=obs or observation(),
        action_history_sha256=h("history"),
    )


def trace(
    *,
    mode: str,
    actions: tuple[str, ...],
    score: int,
    terminal: bool,
    replay: tuple[int, ...] = (),
    repeated: tuple[int, ...] = (),
    obs: ObservationView | None = None,
) -> EvaluatorExecutionTrace:
    c = case()
    o = obs or observation()
    cp = checkpoint(obs=o) if mode == CHECKPOINT_RESUME else None
    return EvaluatorExecutionTrace.record(
        mode=mode,
        case=c,
        target_fixture_sha256=h("target-hidden-fixture"),
        start_observation=o,
        checkpoint=cp,
        action_ids=actions,
        replayed_action_indexes=replay,
        repeated_work_action_indexes=repeated,
        final_evaluator_score=score,
        terminal=terminal,
    )


class TransferRecoveryBenchmarkTests(unittest.TestCase):
    def test_transfer_case_is_deterministic_and_source_target_are_distinct(self):
        c1, c2 = case(), case()
        self.assertEqual(c1, c2)
        self.assertEqual(c1.sha256(), c2.sha256())
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "distinct source and target fixture_id"):
            TransferCase.create(
                source_fixture_id="same",
                source_fixture_generation=1,
                source_holdout_set_id="a",
                source_public_fixture_sha256=h("a"),
                target_fixture_id="same",
                target_fixture_generation=1,
                target_holdout_set_id="b",
                target_public_fixture_sha256=h("b"),
                episode_family_id="e",
                action_budget=2,
            )

    def test_transfer_case_rejects_same_public_digest_or_same_holdout_set(self):
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "distinct source and target public fixture digests"):
            TransferCase.create(
                source_fixture_id="a",
                source_fixture_generation=1,
                source_holdout_set_id="s1",
                source_public_fixture_sha256=h("x"),
                target_fixture_id="b",
                target_fixture_generation=1,
                target_holdout_set_id="s2",
                target_public_fixture_sha256=h("x"),
                episode_family_id="e",
                action_budget=2,
            )
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "distinct source and target holdout sets"):
            TransferCase.create(
                source_fixture_id="a",
                source_fixture_generation=1,
                source_holdout_set_id="same",
                source_public_fixture_sha256=h("x"),
                target_fixture_id="b",
                target_fixture_generation=1,
                target_holdout_set_id="same",
                target_public_fixture_sha256=h("y"),
                episode_family_id="e",
                action_budget=2,
            )

    def test_policy_and_target_observation_bind_exact_public_identity(self):
        c, p, o = case(), policy(), observation()
        c.assert_policy_source(p)
        c.assert_target_observation(o)
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "exact source public fixture"):
            c.assert_policy_source(replace(p, source_public_fixture_sha256=h("wrong")))
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "exact target public fixture"):
            c.assert_target_observation(replace(o, fixture_generation=4))

    def test_public_payload_guard_rejects_hidden_evaluator_keys_and_subclasses(self):
        assert_public_only_payload({"observation": observation(), "policy": {"name": "ok"}})
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "evaluator-only key hidden_ground_truth_ref"):
            assert_public_only_payload({"nested": [{"hidden_ground_truth_ref": "secret"}]})

        class EvilObservation(ObservationView):
            pass

        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "exact concrete ObservationView"):
            assert_public_only_payload(EvilObservation(**observation().as_dict()))

    def test_checkpoint_is_public_deterministic_budget_bound_and_stale_safe(self):
        c, p, o = case(), policy(), observation(step=2)
        cp = RecoveryCheckpoint.seal(case=c, policy=p, observation=o, action_history_sha256=h("history"))
        self.assertEqual(cp, RecoveryCheckpoint.seal(case=c, policy=p, observation=o, action_history_sha256=h("history")))
        self.assertEqual((cp.actions_consumed, cp.remaining_action_budget), (2, 6))
        self.assertNotIn("fixture_sha256", cp.as_dict())
        cp.assert_resume(case=c, policy=p, observation=o)
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "does not match sealed checkpoint"):
            cp.assert_resume(case=c, policy=p, observation=replace(o, step_index=3))

    def test_trace_derives_run_identity_from_exact_measurement_content(self):
        first = trace(
            mode=COLD_RESTART,
            actions=("left", "right"),
            replay=(0,),
            repeated=(1,),
            score=9,
            terminal=True,
        )
        same = trace(
            mode=COLD_RESTART,
            actions=("left", "right"),
            replay=(0,),
            repeated=(1,),
            score=9,
            terminal=True,
        )
        contradictory = trace(mode=COLD_RESTART, actions=("left",), score=999, terminal=False)
        self.assertEqual(first.trace_id, same.trace_id)
        self.assertEqual(first.run_id, same.run_id)
        self.assertNotEqual(first.trace_id, contradictory.trace_id)
        self.assertNotEqual(first.run_id, contradictory.run_id)

    def test_raw_caller_supplied_measurement_falsifier_is_closed(self):
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "raw caller-supplied metrics are forbidden"):
            EvaluatorRunMeasurement.measure_run(
                run_id="same-declared-run",
                mode=COLD_RESTART,
                case=case(),
                target_fixture_sha256=h("target-hidden-fixture"),
                checkpoint=None,
                actions_executed=7,
                replayed_steps=2,
                repeated_work_steps=3,
                final_evaluator_score=9,
                terminal=True,
            )

    def test_measurement_is_derived_from_trace_and_has_zero_credit(self):
        t = trace(
            mode=CHECKPOINT_RESUME,
            actions=("left", "right", "left"),
            replay=(0,),
            repeated=(2,),
            score=10,
            terminal=True,
        )
        m = EvaluatorRunMeasurement.measure_run(trace=t)
        self.assertEqual(m.evaluator_trace_sha256, t.sha256())
        self.assertEqual(m.run_id, t.run_id)
        self.assertEqual((m.actions_executed, m.replayed_steps, m.repeated_work_steps), (3, 1, 1))
        self.assertEqual(m.final_evaluator_score, 10)
        self.assertTrue(m.terminal)
        self.assertEqual(m.runtime_credit, 0)
        self.assertFalse(m.whole_system_acceptance)

    def test_trace_rejects_mode_checkpoint_mismatch_and_bad_index_provenance(self):
        c, o, cp = case(), observation(), checkpoint()
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "checkpoint-resume trace requires checkpoint_sha256"):
            EvaluatorExecutionTrace.record(
                mode=CHECKPOINT_RESUME,
                case=c,
                target_fixture_sha256=h("t"),
                start_observation=o,
                checkpoint=None,
                action_ids=("left",),
                replayed_action_indexes=(),
                repeated_work_action_indexes=(),
                final_evaluator_score=0,
                terminal=False,
            )
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "cold-restart trace must not claim checkpoint consumption"):
            EvaluatorExecutionTrace.record(
                mode=COLD_RESTART,
                case=c,
                target_fixture_sha256=h("t"),
                start_observation=o,
                checkpoint=cp,
                action_ids=("left",),
                replayed_action_indexes=(),
                repeated_work_action_indexes=(),
                final_evaluator_score=0,
                terminal=False,
            )
        with self.assertRaises(TransferRecoveryBenchmarkError):
            EvaluatorExecutionTrace.record(
                mode=COLD_RESTART,
                case=c,
                target_fixture_sha256=h("t"),
                start_observation=o,
                checkpoint=None,
                action_ids=("left",),
                replayed_action_indexes=(1,),
                repeated_work_action_indexes=(),
                final_evaluator_score=0,
                terminal=False,
            )

    def test_matched_comparison_binds_same_postchange_public_start(self):
        start = observation()
        cold = EvaluatorRunMeasurement.from_trace(
            trace(mode=COLD_RESTART, actions=("left", "right"), score=4, terminal=True, obs=start)
        )
        resume = EvaluatorRunMeasurement.from_trace(
            trace(mode=CHECKPOINT_RESUME, actions=("left",), score=5, terminal=True, obs=start)
        )
        pair = MatchedRecoveryComparison.create(cold_restart=cold, checkpoint_resume=resume)
        self.assertEqual(pair.cold_restart.start_observation_sha256, pair.checkpoint_resume.start_observation_sha256)
        other_start = replace(start, observation_ref="obs:other", observation_sha256=h("obs:other"))
        other_resume = EvaluatorRunMeasurement.from_trace(
            trace(mode=CHECKPOINT_RESUME, actions=("left",), score=5, terminal=True, obs=other_start)
        )
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "differs on start_observation_sha256"):
            MatchedRecoveryComparison.create(cold_restart=cold, checkpoint_resume=other_resume)

    def test_matched_comparison_rejects_different_target(self):
        cold = EvaluatorRunMeasurement.from_trace(
            trace(mode=COLD_RESTART, actions=("left",), score=4, terminal=True)
        )
        c, o, cp = case(), observation(), checkpoint()
        other_trace = EvaluatorExecutionTrace.record(
            mode=CHECKPOINT_RESUME,
            case=c,
            target_fixture_sha256=h("other"),
            start_observation=o,
            checkpoint=cp,
            action_ids=("left",),
            replayed_action_indexes=(),
            repeated_work_action_indexes=(),
            final_evaluator_score=5,
            terminal=True,
        )
        bad = EvaluatorRunMeasurement.from_trace(other_trace)
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "differs on target_fixture_sha256"):
            MatchedRecoveryComparison.create(cold_restart=cold, checkpoint_resume=bad)

    def test_efficiency_summary_reports_trace_derived_deltas_not_authority(self):
        cold = EvaluatorRunMeasurement.from_trace(
            trace(
                mode=COLD_RESTART,
                actions=("left", "right", "left"),
                replay=(0,),
                repeated=(1, 2),
                score=9,
                terminal=False,
            )
        )
        resume = EvaluatorRunMeasurement.from_trace(
            trace(mode=CHECKPOINT_RESUME, actions=("left",), score=10, terminal=True)
        )
        summary = EfficiencySummary.from_comparison(
            MatchedRecoveryComparison.create(cold_restart=cold, checkpoint_resume=resume)
        )
        self.assertEqual(summary.evaluator_score_delta, 1)
        self.assertEqual(summary.action_count_delta, -2)
        self.assertEqual(summary.replayed_step_delta, -1)
        self.assertEqual(summary.repeated_work_delta, -2)
        self.assertEqual(summary.terminal_delta, 1)
        self.assertEqual(summary.runtime_credit, 0)
        self.assertFalse(summary.whole_system_acceptance)


if __name__ == "__main__":
    unittest.main()
