from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.rumination_control import (
    CONTINUE,
    EXIT_ACT,
    EXIT_ASK,
    EXIT_DEFER_HOLD,
    EXIT_OBSERVE,
    EXIT_WAIT,
    RUMINATION_DECISION_SCHEMA,
    RuminationControlError,
    RuminationExitDecision,
    RuminationExitPolicy,
    RuminationSnapshot,
    evaluate_rumination_exit,
)

H64 = "a" * 64
W64 = "b" * 64


def snapshot(
    *,
    iteration_count: int = 1,
    unchanged_state_count: int = 0,
    remaining_work_units: int = 10,
    epistemic_state: str = "CLEAR",
    explicit_hold: bool = False,
    wake: bool = False,
) -> RuminationSnapshot:
    return RuminationSnapshot.create(
        cycle_id="cycle-1",
        cycle_generation=3,
        cycle_sha256=H64,
        iteration_count=iteration_count,
        unchanged_state_count=unchanged_state_count,
        remaining_work_units=remaining_work_units,
        epistemic_state=epistemic_state,
        explicit_hold=explicit_hold,
        wake_hold_ref="wake-eval-1" if wake else None,
        wake_hold_sha256=W64 if wake else None,
        provenance_refs=("snapshot-source",),
    )


def policy(*, allowed=(EXIT_ASK, EXIT_DEFER_HOLD, EXIT_OBSERVE, EXIT_WAIT)) -> RuminationExitPolicy:
    return RuminationExitPolicy.create(
        policy_id="rumination-policy-1",
        generation=2,
        max_iterations=5,
        max_unchanged_iterations=3,
        allowed_exits=allowed,
        provenance_refs=("policy-source",),
    )


def decide(value: RuminationSnapshot, *, wake: bool = False):
    kwargs = {}
    if wake:
        kwargs = {"expected_wake_hold_ref": "wake-eval-1", "expected_wake_hold_sha256": W64}
    return evaluate_rumination_exit(
        decision_id="decision-1",
        snapshot=value,
        policy=policy(),
        expected_cycle_id="cycle-1",
        expected_cycle_generation=3,
        expected_cycle_sha256=H64,
        provenance_refs=("decision-source",),
        **kwargs,
    )


class RuminationControlTests(unittest.TestCase):
    def test_bounded_cycle_can_continue_without_minting_authority(self) -> None:
        decision = decide(snapshot())
        self.assertEqual(decision.transition, CONTINUE)
        self.assertTrue(decision.can_continue)
        self.assertFalse(decision.as_dict()["completion_claimed"])
        self.assertEqual(decision.as_dict()["effect_authority"], "NONE")
        self.assertFalse(decision.as_dict()["wake_scheduled"])
        self.assertEqual(decision.as_dict()["runtime_credit"], 0)
        self.assertNotIn("_evaluator_origin", decision.as_dict())

    def test_explicit_hold_forces_defer_hold_and_never_completion(self) -> None:
        decision = decide(snapshot(explicit_hold=True, wake=True), wake=True)
        self.assertEqual(decision.transition, EXIT_DEFER_HOLD)
        self.assertFalse(decision.can_continue)
        self.assertIn("EXPLICIT_HOLD", decision.reasons)
        self.assertFalse(decision.as_dict()["completion_claimed"])

    def test_zero_budget_forces_wait(self) -> None:
        decision = decide(snapshot(remaining_work_units=0))
        self.assertEqual(decision.transition, EXIT_WAIT)
        self.assertEqual(decision.reasons, ("WORK_BUDGET_EXHAUSTED",))

    def test_iteration_limit_with_unknown_forces_ask_and_preserves_unknown(self) -> None:
        decision = decide(snapshot(iteration_count=5, epistemic_state="UNKNOWN"))
        self.assertEqual(decision.transition, EXIT_ASK)
        self.assertTrue(decision.unresolved_preserved)
        self.assertIn("EPISTEMIC_UNKNOWN_PRESERVED", decision.reasons)

    def test_iteration_limit_with_conflict_forces_ask_and_preserves_conflict(self) -> None:
        decision = decide(snapshot(iteration_count=6, epistemic_state="CONFLICT"))
        self.assertEqual(decision.transition, EXIT_ASK)
        self.assertTrue(decision.unresolved_preserved)
        self.assertIn("EPISTEMIC_CONFLICT_PRESERVED", decision.reasons)

    def test_iteration_limit_clear_state_forces_hold_not_completion(self) -> None:
        decision = decide(snapshot(iteration_count=5))
        self.assertEqual(decision.transition, EXIT_DEFER_HOLD)
        self.assertFalse(decision.as_dict()["completion_claimed"])

    def test_unchanged_state_limit_forces_observe(self) -> None:
        decision = decide(snapshot(iteration_count=4, unchanged_state_count=3))
        self.assertEqual(decision.transition, EXIT_OBSERVE)
        self.assertFalse(decision.can_continue)

    def test_unresolved_below_limits_remains_unresolved_while_continuing(self) -> None:
        decision = decide(snapshot(epistemic_state="UNKNOWN"))
        self.assertEqual(decision.transition, CONTINUE)
        self.assertTrue(decision.unresolved_preserved)
        self.assertIn("EPISTEMIC_UNKNOWN_PRESERVED", decision.reasons)

    def test_stale_cycle_identity_generation_and_digest_fail_closed(self) -> None:
        value = snapshot()
        base = dict(
            decision_id="decision-stale",
            snapshot=value,
            policy=policy(),
            provenance_refs=("decision-source",),
        )
        with self.assertRaisesRegex(RuminationControlError, "cycle_id binding mismatch"):
            evaluate_rumination_exit(
                **base,
                expected_cycle_id="cycle-other",
                expected_cycle_generation=3,
                expected_cycle_sha256=H64,
            )
        with self.assertRaisesRegex(RuminationControlError, "cycle generation binding mismatch"):
            evaluate_rumination_exit(
                **base,
                expected_cycle_id="cycle-1",
                expected_cycle_generation=4,
                expected_cycle_sha256=H64,
            )
        with self.assertRaisesRegex(RuminationControlError, "cycle digest binding mismatch"):
            evaluate_rumination_exit(
                **base,
                expected_cycle_id="cycle-1",
                expected_cycle_generation=3,
                expected_cycle_sha256="c" * 64,
            )

    def test_wake_hold_binding_is_exact_when_supplied(self) -> None:
        value = snapshot(explicit_hold=True, wake=True)
        with self.assertRaisesRegex(RuminationControlError, "wake/HOLD reference binding mismatch"):
            evaluate_rumination_exit(
                decision_id="decision-wake-stale",
                snapshot=value,
                policy=policy(),
                expected_cycle_id="cycle-1",
                expected_cycle_generation=3,
                expected_cycle_sha256=H64,
                expected_wake_hold_ref="wake-other",
                expected_wake_hold_sha256=W64,
                provenance_refs=("decision-source",),
            )

    def test_invalid_counters_and_epistemic_state_fail_closed(self) -> None:
        with self.assertRaisesRegex(RuminationControlError, "unchanged_state_count cannot exceed"):
            snapshot(iteration_count=1, unchanged_state_count=2)
        with self.assertRaisesRegex(RuminationControlError, "epistemic_state"):
            snapshot(epistemic_state="FACT_TRUE")

    def test_required_exit_missing_from_policy_fails_closed_not_continue(self) -> None:
        value = snapshot(remaining_work_units=0)
        with self.assertRaisesRegex(RuminationControlError, "required fail-closed transition WAIT"):
            evaluate_rumination_exit(
                decision_id="decision-no-wait",
                snapshot=value,
                policy=policy(allowed=(EXIT_ASK, EXIT_DEFER_HOLD, EXIT_OBSERVE)),
                expected_cycle_id="cycle-1",
                expected_cycle_generation=3,
                expected_cycle_sha256=H64,
                provenance_refs=("decision-source",),
            )

    def test_decision_is_deterministic_and_binds_snapshot_digest(self) -> None:
        value = snapshot(epistemic_state="CONFLICT")
        first = decide(value)
        second = decide(value)
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(first.snapshot_sha256, value.sha256())

    def test_direct_decision_constructor_cannot_bypass_exit_evaluator(self) -> None:
        value = snapshot()
        current_policy = RuminationExitPolicy.create(
            policy_id="policy-review",
            generation=3,
            max_iterations=5,
            max_unchanged_iterations=3,
            allowed_exits=(EXIT_ACT, EXIT_ASK, EXIT_DEFER_HOLD, EXIT_OBSERVE, EXIT_WAIT),
            provenance_refs=("review-policy",),
        )
        evaluated = evaluate_rumination_exit(
            decision_id="evaluated-decision",
            snapshot=value,
            policy=current_policy,
            expected_cycle_id="cycle-1",
            expected_cycle_generation=3,
            expected_cycle_sha256=H64,
            provenance_refs=("review-evaluator",),
        )
        self.assertEqual(evaluated.transition, CONTINUE)

        with self.assertRaisesRegex(
            RuminationControlError,
            "must be created by evaluate_rumination_exit",
        ):
            RuminationExitDecision(
                schema=RUMINATION_DECISION_SCHEMA,
                decision_id="forged-act-decision",
                snapshot_sha256=value.sha256(),
                policy_id=current_policy.policy_id,
                policy_generation=current_policy.generation,
                policy_sha256=current_policy.sha256(),
                transition=EXIT_ACT,
                reasons=("CALLER_FORGED_TRANSITION",),
                can_continue=False,
                unresolved_preserved=False,
                provenance_refs=("caller-supplied",),
            )

    def test_decision_object_rejects_forged_continuation_flag(self) -> None:
        decision = decide(snapshot())
        with self.assertRaisesRegex(RuminationControlError, "can_continue"):
            replace(decision, can_continue=False)

    def test_snapshot_policy_and_decision_reject_forged_classifications(self) -> None:
        value = snapshot()
        with self.assertRaisesRegex(RuminationControlError, "snapshot classification mismatch"):
            replace(value, classification="WORLD_TRUTH")
        current_policy = policy()
        with self.assertRaisesRegex(RuminationControlError, "policy classification mismatch"):
            replace(current_policy, classification="EFFECT_AUTHORITY")
        decision = decide(value)
        with self.assertRaisesRegex(RuminationControlError, "decision classification mismatch"):
            replace(decision, classification="COMPLETION_AUTHORITY")


if __name__ == "__main__":
    unittest.main()
