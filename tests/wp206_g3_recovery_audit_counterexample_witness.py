#!/usr/bin/env python3
"""Positive REVIEW_ONLY witness for the WP206 G3 recovery-audit counterexample.

Unlike the fail-closed falsifier, this probe is expected to PASS on the current merged
implementation by observing the unwanted behavior directly. It is evidence only and
must not be interpreted as desired semantics.
"""
from __future__ import annotations

from frankenstein2.wp206_legacy_authority_recovery import (
    ALREADY_RECOVERED,
    RECOVERY_TABLE,
    recover_legacy_g1_checkpoint_authority,
)
from tests.test_wp206_legacy_authority_recovery import (
    LEGACY_PROVENANCE,
    WP206LegacyAuthorityRecoveryTests,
)


class WP206G3RecoveryAuditCounterexampleWitness(WP206LegacyAuthorityRecoveryTests):
    def test_current_reader_accepts_tampered_recovery_provenance_on_repeat(self) -> None:
        historical, _ = self._emulate_accepted_g1_row()
        store = self._open_store()
        try:
            first = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=LEGACY_PROVENANCE,
            )
            tampered_provenance = "evidence:tampered-after-recovery"
            store.connection.execute(
                f"UPDATE {RECOVERY_TABLE} SET recovery_provenance_ref=? "
                "WHERE checkpoint_id='checkpoint-0'",
                (tampered_provenance,),
            )
            store.connection.commit()

            second = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=LEGACY_PROVENANCE,
            )

            # Counterexample witness: the persisted field changed but the repeat is
            # still accepted as idempotent. The recovery_id is also returned unchanged,
            # so it no longer authenticates the returned provenance field.
            self.assertEqual(second.status, ALREADY_RECOVERED)
            self.assertEqual(second.recovery_id, first.recovery_id)
            self.assertEqual(second.recovery_provenance_ref, tampered_provenance)
            self.assertNotEqual(second.recovery_provenance_ref, LEGACY_PROVENANCE)
        finally:
            store.close()


if __name__ == "__main__":
    import unittest

    suite = unittest.TestSuite()
    suite.addTest(
        WP206G3RecoveryAuditCounterexampleWitness(
            "test_current_reader_accepts_tampered_recovery_provenance_on_repeat"
        )
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
