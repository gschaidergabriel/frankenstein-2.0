#!/usr/bin/env python3
"""REVIEW_ONLY post-merge falsifier for F2-WP-206 generation 3.

This test owns no WP206 mutation authority. It checks only whether the persisted
legacy-recovery audit record remains self-authenticating on an idempotent repeat.
The current G3 claim describes that record as append-only/one-per-checkpoint evidence.
"""
from __future__ import annotations

from frankenstein2.persistent_agency_kernel import PersistentAgencyError
from frankenstein2.wp206_legacy_authority_recovery import (
    RECOVERY_TABLE,
    recover_legacy_g1_checkpoint_authority,
)
from tests.test_wp206_legacy_authority_recovery import (
    LEGACY_PROVENANCE,
    WP206LegacyAuthorityRecoveryTests,
)


class WP206G3RecoveryAuditFalsifier(WP206LegacyAuthorityRecoveryTests):
    def test_recovery_audit_provenance_tamper_must_fail_closed_on_repeat(self) -> None:
        historical, _ = self._emulate_accepted_g1_row()
        store = self._open_store()
        try:
            first = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=LEGACY_PROVENANCE,
            )
            self.assertEqual(first.recovery_provenance_ref, LEGACY_PROVENANCE)

            tampered_provenance = "evidence:tampered-after-recovery"
            store.connection.execute(
                f"UPDATE {RECOVERY_TABLE} SET recovery_provenance_ref=? "
                "WHERE checkpoint_id='checkpoint-0'",
                (tampered_provenance,),
            )
            store.connection.commit()

            # Claimed invariant under test: a persisted recovery audit record must
            # not be accepted idempotently after one of the fields bound into its
            # recovery_id has changed. The current implementation is expected to
            # falsify this by returning ALREADY_RECOVERED instead of failing closed.
            with self.assertRaises(PersistentAgencyError):
                recover_legacy_g1_checkpoint_authority(
                    store=store,
                    checkpoint_id="checkpoint-0",
                    expected_legacy_authority_receipt_sha256=historical,
                    recovery_provenance_ref=LEGACY_PROVENANCE,
                )
        finally:
            store.close()


if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    suite.addTest(
        WP206G3RecoveryAuditFalsifier(
            "test_recovery_audit_provenance_tamper_must_fail_closed_on_repeat"
        )
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
