from __future__ import annotations

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


class WP509DecisionConstructorLineageFalsifier(unittest.TestCase):
    def test_direct_decision_constructor_cannot_bypass_exit_evaluator(self) -> None:
        snapshot = RuminationSnapshot.create(
            cycle_id="cycle-review",
            cycle_generation=7,
            cycle_sha256=H64,
            iteration_count=1,
            unchanged_state_count=0,
            remaining_work_units=10,
            epistemic_state="CLEAR",
            explicit_hold=False,
            provenance_refs=("review-snapshot",),
        )
        policy = RuminationExitPolicy.create(
            policy_id="policy-review",
            generation=3,
            max_iterations=5,
            max_unchanged_iterations=3,
            allowed_exits=(EXIT_ACT, EXIT_ASK, EXIT_DEFER_HOLD, EXIT_OBSERVE, EXIT_WAIT),
            provenance_refs=("review-policy",),
        )

        evaluated = evaluate_rumination_exit(
            decision_id="evaluated-decision",
            snapshot=snapshot,
            policy=policy,
            expected_cycle_id="cycle-review",
            expected_cycle_generation=7,
            expected_cycle_sha256=H64,
            provenance_refs=("review-evaluator",),
        )
        self.assertEqual(evaluated.transition, CONTINUE)

        # Falsifier: the same bounded state/policy should not allow a caller to mint an
        # ACT transition without traversing evaluate_rumination_exit(). If this direct
        # constructor succeeds, downstream code cannot distinguish evaluated policy output
        # from a caller-forged, self-consistent decision object/digest.
        with self.assertRaises(RuminationControlError):
            RuminationExitDecision(
                schema=RUMINATION_DECISION_SCHEMA,
                decision_id="forged-act-decision",
                snapshot_sha256=snapshot.sha256(),
                policy_id=policy.policy_id,
                policy_generation=policy.generation,
                policy_sha256=policy.sha256(),
                transition=EXIT_ACT,
                reasons=("CALLER_FORGED_TRANSITION",),
                can_continue=False,
                unresolved_preserved=False,
                provenance_refs=("caller-supplied",),
            )


if __name__ == "__main__":
    unittest.main()
