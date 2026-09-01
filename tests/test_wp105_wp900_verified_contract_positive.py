from __future__ import annotations

import unittest

from frankenstein2.completion_evidence_gate import (
    admit_current_effect_journal_verification,
    apply_admitted_effect_bound_verification,
)
from frankenstein2.whole_persistent_loop import (
    EFFECT_VERIFIED_APPLIED,
    LoopOutcomeEvidence,
)
from state.execution_completion import ExecutionStage
from test_completion_evidence_gate import (
    build_target_and_observed,
    current_binding,
    final_transition,
    journal_evidence,
)


class WP105WP900VerifiedContractPositiveTests(unittest.TestCase):
    """Prove the existing admitted WP105 finalization composes into WP900."""

    def test_admitted_verified_applied_target_is_accepted_by_wp900(self) -> None:
        target, observed = build_target_and_observed()
        transition = final_transition(target)
        journal = journal_evidence(target, observed, transition)

        self.assertEqual(target.lineage.stage, ExecutionStage.EXECUTION_RECORDED)

        admission = admit_current_effect_journal_verification(
            observed,
            transition,
            authority_binding=current_binding(),
            journal_evidence=journal,
        )
        verified = apply_admitted_effect_bound_verification(
            target,
            observed,
            transition,
            admission=admission,
        )

        self.assertIs(verified.lineage.stage, ExecutionStage.VERIFIED_APPLIED)
        self.assertTrue(verified.lineage.is_verified_complete)

        outcome = LoopOutcomeEvidence(
            outcome_id="outcome-wp105-wp900-verified-applied",
            status=EFFECT_VERIFIED_APPLIED,
            effect_call=observed,
            verification_target=verified,
            provenance_refs=(
                "trigger4:wp105-wp900:existing-completion-authority-path",
            ),
        )
        payload = outcome.as_dict()

        self.assertEqual(payload["status"], EFFECT_VERIFIED_APPLIED)
        self.assertEqual(payload["effect"]["stage"], "RESULT_OBSERVED")
        self.assertEqual(payload["verification"]["stage"], "VERIFIED_APPLIED")
        self.assertEqual(payload["truth_authority"], "NONE")
        self.assertEqual(payload["effect_authority"], "NONE")
        self.assertEqual(payload["completion_authority"], "NONE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
