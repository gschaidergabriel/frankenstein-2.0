#!/usr/bin/env python3
"""REVIEW_ONLY executable counterexample for F2-WP-206 generation 3.

No WP206 mutation authority is claimed. A green run means the current canonical
legacy-recovery adapter reproduced the repeat-provenance identity ambiguity: after one
successful recovery witnessed by provenance A, a repeat request with provenance B is
accepted as the same recovery and silently returns provenance A.

This is repository-component negative evidence only. It does not imply target-runtime,
VPS, physical GRID10, GWT/J-Space, effect, completion, training, or whole-system credit.
"""
from __future__ import annotations

import test_wp206_legacy_authority_recovery as base

from frankenstein2.wp206_legacy_authority_recovery import (
    ALREADY_RECOVERED,
    RECOVERY_TABLE,
    recover_legacy_g1_checkpoint_authority,
)


PROVENANCE_A = "evidence:accepted-wp206-g1-full-fingerprint-receipt:A"
PROVENANCE_B = "evidence:accepted-wp206-g1-full-fingerprint-receipt:B"


class WP206RepeatProvenanceCounterexample(base.WP206LegacyAuthorityRecoveryTests):
    def test_different_repeat_provenance_is_silently_collapsed_to_original_recovery(self) -> None:
        historical, current = self._emulate_accepted_g1_row()
        store = self._open_store()
        try:
            first = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=PROVENANCE_A,
            )
            second = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=PROVENANCE_B,
            )

            # Counterexample reproduction: provenance B is accepted as idempotent even
            # though recovery identity was minted from provenance A. The API returns the
            # old identity/provenance rather than rejecting the conflicting witness.
            self.assertEqual(second.status, ALREADY_RECOVERED)
            self.assertEqual(second.recovery_id, first.recovery_id)
            self.assertEqual(first.recovery_provenance_ref, PROVENANCE_A)
            self.assertEqual(second.recovery_provenance_ref, PROVENANCE_A)
            self.assertNotEqual(second.recovery_provenance_ref, PROVENANCE_B)
            self.assertEqual(self._stored_receipt(), current)

            rows = store.connection.execute(
                f"SELECT recovery_id, recovery_provenance_ref FROM {RECOVERY_TABLE} "
                "WHERE checkpoint_id='checkpoint-0'"
            ).fetchall()
            self.assertEqual(rows, [(first.recovery_id, PROVENANCE_A)])
        finally:
            store.close()


if __name__ == "__main__":
    base.unittest.main(verbosity=2)
