#!/usr/bin/env python3
"""F2-WP-901 G5 regressions for canonical UnifiedDB authority-reference binding."""
from __future__ import annotations

import unittest

from frankenstein2.causal_authority_binding import UnifiedDBAuthorityRef
from frankenstein2.restart_recovery_continuation import CONTINUE_UNFINISHED
from frankenstein2.restart_recovery_persisted_row_attestation import (
    CANONICAL_UNIFIEDDB_AUTHORITY_FINGERPRINT_SCHEMA,
    CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF,
    CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE,
    PersistedRowLoadAttestationError,
    plan_restart_continuation_from_persisted_row,
)
from tests.test_restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationTests,
)


class WP901G5StoreAuthorityRefBindingTests(PersistedRowLoadAttestationTests):
    def _plan_with_authority(self, authority: UnifiedDBAuthorityRef):
        causal, checkpoint, seal, outcome, evidence = self.sources()
        return plan_restart_continuation_from_persisted_row(
            self.store,
            checkpoint_id=checkpoint.checkpoint_id,
            evidence=evidence,
            plan_id="restart-plan-wp901-g5-authority-binding",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            unifieddb_authority=authority,
            whole_loop_seal=seal,
            outcome=outcome,
        )

    def test_canonical_f2_wp100_authority_ref_is_accepted(self) -> None:
        authority = UnifiedDBAuthorityRef(
            receipt_ref=CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF,
            canonical_source=CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE,
            fingerprint_schema=CANONICAL_UNIFIEDDB_AUTHORITY_FINGERPRINT_SCHEMA,
        )
        result = self._plan_with_authority(authority)
        self.assertEqual(result.plan.disposition, CONTINUE_UNFINISHED)
        self.assertNotEqual(
            authority.receipt_ref,
            result.load_attestation.unifieddb_authority_receipt_sha256,
        )

    def test_foreign_receipt_ref_fails_closed(self) -> None:
        foreign = UnifiedDBAuthorityRef(
            receipt_ref="workpackages/receipts/FOREIGN_UNIFIEDDB.json",
            canonical_source=CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE,
            fingerprint_schema=CANONICAL_UNIFIEDDB_AUTHORITY_FINGERPRINT_SCHEMA,
        )
        with self.assertRaisesRegex(
            PersistedRowLoadAttestationError,
            "PERSISTED_ROW_UNIFIEDDB_AUTHORITY_REF_MISMATCH",
        ):
            self._plan_with_authority(foreign)

    def test_foreign_canonical_source_fails_closed(self) -> None:
        foreign = UnifiedDBAuthorityRef(
            receipt_ref=CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF,
            canonical_source="foreign/not-the-admitted-unifieddb-identity.py",
            fingerprint_schema=CANONICAL_UNIFIEDDB_AUTHORITY_FINGERPRINT_SCHEMA,
        )
        with self.assertRaisesRegex(
            PersistedRowLoadAttestationError,
            "PERSISTED_ROW_UNIFIEDDB_AUTHORITY_REF_MISMATCH",
        ):
            self._plan_with_authority(foreign)


if __name__ == "__main__":
    unittest.main(verbosity=2)
