#!/usr/bin/env python3
"""Repository regressions for F2-WP-901 G5 store-bound authority closure."""
from __future__ import annotations

from dataclasses import replace

from frankenstein2.causal_authority_binding import UnifiedDBAuthorityRef
from frankenstein2.restart_recovery_continuation import CONTINUE_UNFINISHED
from frankenstein2.restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationError,
)
from frankenstein2.restart_recovery_store_authority_binding import (
    STORE_BOUND_AUTHORITY_REF_PREFIX,
    STORE_BOUND_AUTHORITY_SOURCE,
    plan_restart_continuation_from_store_bound_persisted_row,
    store_bound_unifieddb_authority_ref,
)
from tests.test_restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationTests,
)


class WP901G5StoreAuthorityBindingTests(PersistedRowLoadAttestationTests):
    """Successor tests reuse the accepted G4 fixture and add only the G5 boundary."""

    def _plan_g5(self, authority: UnifiedDBAuthorityRef):
        causal, checkpoint, seal, outcome, evidence = self.sources()
        result = plan_restart_continuation_from_store_bound_persisted_row(
            self.store,
            checkpoint_id=checkpoint.checkpoint_id,
            evidence=evidence,
            plan_id="restart-plan-wp901-g5",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            unifieddb_authority=authority,
            whole_loop_seal=seal,
            outcome=outcome,
        )
        return result, checkpoint

    def test_store_bound_authority_is_derived_from_exact_store_receipt(self) -> None:
        authority = store_bound_unifieddb_authority_ref(self.store)
        self.assertEqual(
            authority.receipt_ref,
            STORE_BOUND_AUTHORITY_REF_PREFIX + self.store.authority_receipt_sha256,
        )
        self.assertEqual(authority.canonical_source, STORE_BOUND_AUTHORITY_SOURCE)
        self.assertEqual(
            authority.fingerprint_schema,
            "FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
        )

    def test_store_bound_authority_preserves_g4_g3_g2_continuation(self) -> None:
        authority = store_bound_unifieddb_authority_ref(self.store)
        result, checkpoint = self._plan_g5(authority)
        self.assertEqual(result.plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(result.plan.source_checkpoint_id, checkpoint.checkpoint_id)
        self.assertEqual(
            result.load_attestation.unifieddb_authority_receipt_sha256,
            self.store.authority_receipt_sha256,
        )

    def test_pr719_foreign_caller_authority_ref_now_fails_closed(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        foreign_authority = UnifiedDBAuthorityRef(
            receipt_ref="receipt:unifieddb:foreign-component",
            canonical_source="foreign/not-the-loaded-unifieddb-authority.py",
            fingerprint_schema="FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
        )
        with self.assertRaisesRegex(
            PersistedRowLoadAttestationError,
            "PERSISTED_ROW_G3_UNIFIEDDB_AUTHORITY_REF_MISMATCH",
        ):
            plan_restart_continuation_from_store_bound_persisted_row(
                self.store,
                checkpoint_id=checkpoint.checkpoint_id,
                evidence=evidence,
                plan_id="restart-plan-wp901-g5-foreign-authority",
                expected_evidence_sha256=evidence.sha256(),
                causal_identity=causal,
                unifieddb_authority=foreign_authority,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_same_receipt_with_wrong_identity_source_fails_closed(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        authority = store_bound_unifieddb_authority_ref(self.store)
        wrong_source = replace(
            authority,
            canonical_source="foreign/not-the-canonical-unifieddb-identity.py",
        )
        with self.assertRaisesRegex(
            PersistedRowLoadAttestationError,
            "PERSISTED_ROW_G3_UNIFIEDDB_AUTHORITY_REF_MISMATCH",
        ):
            plan_restart_continuation_from_store_bound_persisted_row(
                self.store,
                checkpoint_id=checkpoint.checkpoint_id,
                evidence=evidence,
                plan_id="restart-plan-wp901-g5-wrong-source",
                expected_evidence_sha256=evidence.sha256(),
                causal_identity=causal,
                unifieddb_authority=wrong_source,
                whole_loop_seal=seal,
                outcome=outcome,
            )


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
