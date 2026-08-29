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
    EvaluatorRunMeasurement,
    MatchedRecoveryComparison,
    EfficiencySummary,
    TransferRecoveryBenchmarkError,
    assert_public_only_payload,
)


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def observation(*, step: int = 2, episode_generation: int = 4) -> ObservationView:
    return ObservationView(
        schema=OBSERVATION_SCHEMA,
        episode_id="ep-target-1",
        episode_generation=episode_generation,
        fixture_id="heldout.target.001",
        fixture_generation=3,
        public_fixture_sha256=h("target-public-fixture"),
        step_index=step,
        observation_ref="obs:public-room",
        observation_sha256=h("public-room"),
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


class TransferRecoveryBenchmarkTests(unittest.TestCase):
    def test_transfer_case_is_deterministic_and_source_target_are_distinct(self):
        c1, c2 = case(), case()
        self.assertEqual(c1.case_id, c2.case_id)
        self.assertEqual(c1.sha256(), c2.sha256())
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "distinct source and target fixture_id"):
            TransferCase.create(
                source_fixture_id="same", source_fixture_generation=1, source_holdout_set_id="a", source_public_fixture_sha256=h("a"),
                target_fixture_id="same", target_fixture_generation=1, target_holdout_set_id="b", target_public_fixture_sha256=h("b"),
                episode_family_id="e", action_budget=2,
            )

    def test_transfer_case_rejects_same_public_digest_or_same_holdout_set(self):
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "distinct source and target public fixture digests"):
            TransferCase.create(
                source_fixture_id="a", source_fixture_generation=1, source_holdout_set_id="s1", source_public_fixture_sha256=h("x"),
                target_fixture_id="b", target_fixture_generation=1, target_holdout_set_id="s2", target_public_fixture_sha256=h("x"),
                episode_family_id="e", action_budget=2,
            )
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "distinct source and target holdout sets"):
            TransferCase.create(
                source_fixture_id="a", source_fixture_generation=1, source_holdout_set_id="same", source_public_fixture_sha256=h("x"),
                target_fixture_id="b", target_fixture_generation=1, target_holdout_set_id="same", target_public_fixture_sha256=h("y"),
                episode_family_id="e", action_budget=2,
            )

    def test_policy_must_bind_exact_source_and_budget(self):
        c = case(); p = policy(); c.assert_policy_source(p)
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "exact source public fixture"):
            c.assert_policy_source(replace(p, source_public_fixture_sha256=h("wrong")))
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "below transfer-case action budget"):
            c.assert_policy_source(replace(p, max_action_budget=7))

    def test_target_observation_binding_rejects_wrong_generation_or_digest(self):
        c = case(); o = observation(); c.assert_target_observation(o)
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "exact target public fixture"):
            c.assert_target_observation(replace(o, fixture_generation=4))
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "exact target public fixture"):
            c.assert_target_observation(replace(o, public_fixture_sha256=h("wrong")))

    def test_public_payload_guard_rejects_hidden_evaluator_keys_recursively(self):
        assert_public_only_payload({"observation": observation(), "policy": {"name": "ok"}})
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "evaluator-only key hidden_ground_truth_ref"):
            assert_public_only_payload({"nested": [{"hidden_ground_truth_ref": "secret"}]})
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "evaluator-only key fixture_sha256"):
            assert_public_only_payload({"fixture_sha256": h("full-hidden-fixture")})

    def test_public_payload_guard_rejects_observation_subclass(self):
        class EvilObservation(ObservationView):
            pass
        o = observation()
        evil = EvilObservation(**o.as_dict())
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "exact concrete ObservationView"):
            assert_public_only_payload(evil)

    def test_checkpoint_seal_is_deterministic_public_only_and_budget_bound(self):
        c, p, o = case(), policy(), observation(step=2)
        cp1 = RecoveryCheckpoint.seal(case=c, policy=p, observation=o, action_history_sha256=h("history"))
        cp2 = RecoveryCheckpoint.seal(case=c, policy=p, observation=o, action_history_sha256=h("history"))
        self.assertEqual(cp1, cp2)
        self.assertEqual(cp1.actions_consumed, 2)
        self.assertEqual(cp1.remaining_action_budget, 6)
        self.assertNotIn("current_node_id", cp1.as_dict())
        self.assertNotIn("fixture_sha256", cp1.as_dict())
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "exceeds transfer-case action budget"):
            RecoveryCheckpoint.seal(case=c, policy=p, observation=observation(step=9), action_history_sha256=h("history"))

    def test_checkpoint_resume_rejects_stale_or_future_observation(self):
        c, p, o = case(), policy(), observation(step=2)
        cp = RecoveryCheckpoint.seal(case=c, policy=p, observation=o, action_history_sha256=h("history"))
        cp.assert_resume(case=c, policy=p, observation=o)
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "does not match sealed checkpoint"):
            cp.assert_resume(case=c, policy=p, observation=replace(o, step_index=3))
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "does not match sealed checkpoint"):
            cp.assert_resume(case=c, policy=p, observation=replace(o, episode_generation=5))

    def test_measurement_requires_mode_checkpoint_consistency_and_zero_credit(self):
        c, p, o = case(), policy(), observation()
        cp = RecoveryCheckpoint.seal(case=c, policy=p, observation=o, action_history_sha256=h("history"))
        cold = EvaluatorRunMeasurement.measure_run(
            run_id="cold", mode=COLD_RESTART, case=c, target_fixture_sha256=h("target-hidden-fixture"), checkpoint=None,
            actions_executed=7, replayed_steps=2, repeated_work_steps=3, final_evaluator_score=9, terminal=True,
        )
        resume = EvaluatorRunMeasurement.measure_run(
            run_id="resume", mode=CHECKPOINT_RESUME, case=c, target_fixture_sha256=h("target-hidden-fixture"), checkpoint=cp,
            actions_executed=5, replayed_steps=0, repeated_work_steps=1, final_evaluator_score=10, terminal=True,
        )
        self.assertEqual(cold.runtime_credit, 0); self.assertFalse(resume.whole_system_acceptance)
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "requires checkpoint_sha256"):
            EvaluatorRunMeasurement.measure_run(
                run_id="bad", mode=CHECKPOINT_RESUME, case=c, target_fixture_sha256=h("target-hidden-fixture"), checkpoint=None,
                actions_executed=1, replayed_steps=0, repeated_work_steps=0, final_evaluator_score=0, terminal=False,
            )

    def test_measurement_rejects_budget_and_replay_overclaims(self):
        c = case()
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "exceeds matched action budget"):
            EvaluatorRunMeasurement.measure_run(
                run_id="bad", mode=COLD_RESTART, case=c, target_fixture_sha256=h("target-hidden-fixture"), checkpoint=None,
                actions_executed=9, replayed_steps=0, repeated_work_steps=0, final_evaluator_score=0, terminal=False,
            )
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "count exceeds executed actions"):
            EvaluatorRunMeasurement.measure_run(
                run_id="bad2", mode=COLD_RESTART, case=c, target_fixture_sha256=h("target-hidden-fixture"), checkpoint=None,
                actions_executed=2, replayed_steps=3, repeated_work_steps=0, final_evaluator_score=0, terminal=False,
            )

    def test_matched_comparison_rejects_different_target_or_budget(self):
        c, p, o = case(), policy(), observation()
        cp = RecoveryCheckpoint.seal(case=c, policy=p, observation=o, action_history_sha256=h("history"))
        cold = EvaluatorRunMeasurement.measure_run(run_id="cold", mode=COLD_RESTART, case=c, target_fixture_sha256=h("t"), checkpoint=None, actions_executed=6, replayed_steps=2, repeated_work_steps=2, final_evaluator_score=4, terminal=True)
        resume = EvaluatorRunMeasurement.measure_run(run_id="resume", mode=CHECKPOINT_RESUME, case=c, target_fixture_sha256=h("t"), checkpoint=cp, actions_executed=4, replayed_steps=0, repeated_work_steps=0, final_evaluator_score=5, terminal=True)
        pair = MatchedRecoveryComparison.create(cold_restart=cold, checkpoint_resume=resume)
        self.assertEqual(pair.cold_restart.action_budget, pair.checkpoint_resume.action_budget)
        other = EvaluatorRunMeasurement.measure_run(
            run_id="resume-other", mode=CHECKPOINT_RESUME, case=c, target_fixture_sha256=h("other"), checkpoint=cp,
            actions_executed=4, replayed_steps=0, repeated_work_steps=0, final_evaluator_score=5, terminal=True,
        )
        with self.assertRaisesRegex(TransferRecoveryBenchmarkError, "differs on target_fixture_sha256"):
            MatchedRecoveryComparison.create(cold_restart=cold, checkpoint_resume=other)

    def test_efficiency_summary_reports_deltas_not_authority(self):
        c, p, o = case(), policy(), observation()
        cp = RecoveryCheckpoint.seal(case=c, policy=p, observation=o, action_history_sha256=h("history"))
        cold = EvaluatorRunMeasurement.measure_run(run_id="cold", mode=COLD_RESTART, case=c, target_fixture_sha256=h("t"), checkpoint=None, actions_executed=7, replayed_steps=2, repeated_work_steps=3, final_evaluator_score=9, terminal=False)
        resume = EvaluatorRunMeasurement.measure_run(run_id="resume", mode=CHECKPOINT_RESUME, case=c, target_fixture_sha256=h("t"), checkpoint=cp, actions_executed=5, replayed_steps=0, repeated_work_steps=1, final_evaluator_score=10, terminal=True)
        summary = EfficiencySummary.from_comparison(MatchedRecoveryComparison.create(cold_restart=cold, checkpoint_resume=resume))
        self.assertEqual(summary.evaluator_score_delta, 1)
        self.assertEqual(summary.action_count_delta, -2)
        self.assertEqual(summary.replayed_step_delta, -2)
        self.assertEqual(summary.repeated_work_delta, -2)
        self.assertEqual(summary.terminal_delta, 1)
        self.assertEqual(summary.runtime_credit, 0)
        self.assertFalse(summary.whole_system_acceptance)


if __name__ == "__main__":
    unittest.main()
