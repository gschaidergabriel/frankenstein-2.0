#!/usr/bin/env python3
"""REVIEW_ONLY executable falsifier for WP206 G3 repeat recovery provenance identity.

No production mutation authority is claimed. The accepted G3 recovery_id binds the
recovery_provenance_ref, so a repeat request with a different provenance reference should
not be silently treated as the same exact idempotent recovery.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from test_wp206_legacy_authority_recovery import (  # noqa: E402
    LEGACY_PROVENANCE,
    WP206LegacyAuthorityRecoveryTests,
)
from frankenstein2.persistent_agency_kernel import PersistentAgencyError  # noqa: E402
from frankenstein2.wp206_legacy_authority_recovery import (  # noqa: E402
    RECOVERY_TABLE,
    recover_legacy_g1_checkpoint_authority,
)


class WP206G3RepeatProvenanceConflictReview(WP206LegacyAuthorityRecoveryTests):
    def test_repeat_with_conflicting_provenance_must_fail_closed(self) -> None:
        historical, _ = self._emulate_accepted_g1_row()
        store = self._open_store()
        try:
            first = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=LEGACY_PROVENANCE,
            )
            conflicting_provenance = "evidence:independent-conflicting-recovery-authority"
            self.assertNotEqual(conflicting_provenance, LEGACY_PROVENANCE)

            with self.assertRaisesRegex(
                PersistentAgencyError,
                "LEGACY_RECOVERY_PROVENANCE_CONFLICT",
            ):
                recover_legacy_g1_checkpoint_authority(
                    store=store,
                    checkpoint_id="checkpoint-0",
                    expected_legacy_authority_receipt_sha256=historical,
                    recovery_provenance_ref=conflicting_provenance,
                )

            rows = store.connection.execute(
                f"SELECT recovery_id, recovery_provenance_ref FROM {RECOVERY_TABLE} "
                "WHERE checkpoint_id='checkpoint-0'"
            ).fetchall()
            self.assertEqual(rows, [(first.recovery_id, LEGACY_PROVENANCE)])
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
