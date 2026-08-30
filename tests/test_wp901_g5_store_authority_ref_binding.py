#!/usr/bin/env python3
"""Repository regressions for F2-WP-901 G5 component/store authority separation."""
from __future__ import annotations

from dataclasses import replace

from frankenstein2.causal_authority_binding import UnifiedDBAuthorityRef
from frankenstein2.restart_recovery_continuation import CONTINUE_UNFINISHED
from frankenstein2.restart_recovery_persisted_row_attestation import (
    CANONICAL_UNIFIEDDB_COMPONENT_RECEIPT_REF,
    CANONICAL_UNIFIEDDB_COMPONENT_SOURCE,
    CANONICAL_UNIFIEDDB_FINGERPRINT_SCHEMA,
    PersistedRowLoadAttestationError,
    canonical_unifieddb_component_authority_ref,
    plan_restart_continuation_from_persisted_row,
)
from tests.test_restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationTests,
)


class WP901G5StoreAuthorityRefBindingTests(PersistedRowLoadAttestationTests):
    """G5 adds only the exact F2-WP-100 component-ref check above accepted G4."""

    def _plan_with(self, authority: UnifiedDBAuthorityRef):
        causal, checkpoint, seal, outcome, evidence = self.sources()
        return plan_restart_continuation_from_persisted_row(
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

    def test_canonical_component_ref_names_f2_wp100_receipt_not_store_digest(self) -> None:
        authority = canonical_unifieddb_component_authority_ref()
        self.assertEqual(authority.receipt_ref, CANONICAL_UNIFIEDDB_COMPONENT_RECEIPT_REF)
        self.assertEqual(authority.canonical_source, CANONICAL_UNIFIEDDB_COMPONENT_SOURCE)
        self.assertEqual(authority.fingerprint_schema, CANONICAL_UNIFIEDDB_FINGERPRINT_SCHEMA)
        self.assertEqual(
            authority.receipt_ref,
            "workpackages/receipts/F2-WP-100_G1_SOURCE_CI_ACCEPTANCE.json",
        )
        self.assertEqual(authority.canonical_source, "src/state/unifieddb_identity.py")
        self.assertEqual(
            authority.fingerprint_schema,
            "FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
        )
        self.assertNotEqual(authority.receipt_ref, self.store.authority_receipt_sha256)
        self.assertNotIn(self.store.authority_receipt_sha256, authority.receipt_ref)

    def test_canonical_component_ref_preserves_g4_g3_g2_continuation(self) -> None:
        authority = canonical_unifieddb_component_authority_ref()
        result = self._plan_with(authority)
        self.assertEqual(result.plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(
            result.load_attestation.unifieddb_authority_receipt_sha256,
            self.store.authority_receipt_sha256,
        )
        self.assertNotEqual(
            authority.receipt_ref,
            result.load_attestation.unifieddb_authority_receipt_sha256,
        )

    def test_pr739_foreign_component_ref_fails_closed_before_g3_planning(self) -> None:
        foreign = UnifiedDBAuthorityRef(
            receipt_ref="receipt:unifieddb:foreign-component",
            canonical_source="foreign/not-the-canonical-unifieddb-identity.py",
            fingerprint_schema="FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
        )
        with self.assertRaisesRegex(
            PersistedRowLoadAttestationError,
            "PERSISTED_ROW_G3_UNIFIEDDB_AUTHORITY_REF_MISMATCH",
        ):
            self._plan_with(foreign)

    def test_same_component_receipt_with_wrong_source_fails_closed(self) -> None:
        wrong_source = replace(
            canonical_unifieddb_component_authority_ref(),
            canonical_source="foreign/not-the-canonical-unifieddb-identity.py",
        )
        with self.assertRaisesRegex(
            PersistedRowLoadAttestationError,
            "PERSISTED_ROW_G3_UNIFIEDDB_AUTHORITY_REF_MISMATCH",
        ):
            self._plan_with(wrong_source)

    def test_concrete_store_receipt_cannot_masquerade_as_component_receipt_ref(self) -> None:
        conflated = UnifiedDBAuthorityRef(
            receipt_ref=f"f2:unifieddb-fingerprint:{self.store.authority_receipt_sha256}",
            canonical_source=CANONICAL_UNIFIEDDB_COMPONENT_SOURCE,
            fingerprint_schema=CANONICAL_UNIFIEDDB_FINGERPRINT_SCHEMA,
        )
        with self.assertRaisesRegex(
            PersistedRowLoadAttestationError,
            "PERSISTED_ROW_G3_UNIFIEDDB_AUTHORITY_REF_MISMATCH",
        ):
            self._plan_with(conflated)


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
