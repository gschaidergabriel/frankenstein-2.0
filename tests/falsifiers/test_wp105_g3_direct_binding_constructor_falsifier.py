from __future__ import annotations

import unittest

from frankenstein2.completion_evidence_gate import (
    admit_current_effect_journal_verification,
    apply_admitted_effect_bound_verification,
)
from state.execution_completion import ExecutionStage
from tests.test_completion_evidence_gate import (
    build_target_and_observed,
    current_binding,
    final_transition,
    journal_evidence,
)


class WP105G3DirectBindingConstructorFalsifier(unittest.TestCase):
    """Reproduce the direct-constructor authority-admission gap without real effects."""

    def test_direct_constructed_dummy_binding_can_mint_final_admission(self) -> None:
        target, observed = build_target_and_observed()
        transition = final_transition(target)

        # This helper constructs CurrentEntityOSEffectAuthorityBinding directly with
        # synthetic repeated-digit Git SHAs.  It does not call
        # load_current_entityos_effect_authority_binding() and therefore supplies no
        # binding document or current-epoch attestation for validation.
        synthetic_binding = current_binding()
        self.assertEqual(synthetic_binding.binding_record_blob_sha, "1" * 40)
        self.assertEqual(synthetic_binding.binding_record_commit_sha, "2" * 40)
        self.assertEqual(synthetic_binding.current_epoch_attestation_commit_sha, "3" * 40)
        self.assertEqual(synthetic_binding.implementation_commit_sha, "4" * 40)

        synthetic_journal_evidence = journal_evidence(
            target,
            observed,
            transition,
        )
        admission = admit_current_effect_journal_verification(
            observed,
            transition,
            authority_binding=synthetic_binding,
            journal_evidence=synthetic_journal_evidence,
        )
        verified = apply_admitted_effect_bound_verification(
            target,
            observed,
            transition,
            admission=admission,
        )

        # A passing falsifier means the accepted G3 boundary can finalize from a
        # directly constructed, merely well-shaped authority tuple.  This is
        # repository-only evidence; no real EffectGate/EffectJournal call occurs.
        self.assertEqual(verified.lineage.stage, ExecutionStage.VERIFIED_APPLIED)
        self.assertTrue(verified.lineage.is_verified_complete)


if __name__ == "__main__":
    unittest.main(verbosity=2)
