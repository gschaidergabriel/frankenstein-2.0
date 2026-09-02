#!/usr/bin/env python3
"""REVIEW_ONLY exact-current falsifier for WP901 G4 cross-store authority binding.

A PASS means the post-acceptance counterexample is reproduced on the exact branch source:
a caller-supplied UnifiedDBAuthorityRef that does not describe the store which actually
loaded/attested the persisted row is still accepted by the G4 -> G3 planning boundary.

This file is counterevidence only. It does not propose a repair, mutate canonical WP901
semantics, or mint target-host/runtime/whole-system credit.
"""
from __future__ import annotations

from frankenstein2.causal_authority_binding import UnifiedDBAuthorityRef
from frankenstein2.restart_recovery_continuation import CONTINUE_UNFINISHED
from frankenstein2.restart_recovery_persisted_row_attestation import (
    plan_restart_continuation_from_persisted_row,
)
from tests.test_restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationTests,
)


class WP901CrossStoreAuthorityFalsifier(PersistedRowLoadAttestationTests):
    def test_foreign_caller_authority_ref_is_still_accepted_on_exact_current_source(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        foreign_authority = UnifiedDBAuthorityRef(
            receipt_ref="receipt:unifieddb:foreign-component",
            canonical_source="foreign/not-the-loaded-unifieddb-authority.py",
            fingerprint_schema="FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
        )
        self.assertNotEqual(foreign_authority.receipt_ref, self.authority().receipt_ref)
        self.assertNotEqual(foreign_authority.canonical_source, self.authority().canonical_source)

        result = plan_restart_continuation_from_persisted_row(
            self.store,
            checkpoint_id=checkpoint.checkpoint_id,
            evidence=evidence,
            plan_id="restart-plan-wp901-g4-exact-current-foreign-authority",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            unifieddb_authority=foreign_authority,
            whole_loop_seal=seal,
            outcome=outcome,
        )

        self.assertEqual(result.plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(result.plan.source_checkpoint_id, checkpoint.checkpoint_id)
        self.assertEqual(
            result.load_attestation.unifieddb_authority_receipt_sha256,
            self.store.authority_receipt_sha256,
        )
        self.assertNotEqual(
            foreign_authority.receipt_ref,
            result.load_attestation.unifieddb_authority_receipt_sha256,
        )


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
