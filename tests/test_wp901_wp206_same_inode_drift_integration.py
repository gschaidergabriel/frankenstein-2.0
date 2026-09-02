#!/usr/bin/env python3
"""Cross-component regression: WP901 ingress must preserve WP206 same-inode drift fence.

Repository-component evidence only. This test does not mint target-host, reboot, effect,
completion, or whole-system credit.
"""
from __future__ import annotations

import sqlite3

from frankenstein2.persistent_agency_kernel import CHECKPOINT_TABLE, PersistentAgencyError
from frankenstein2.restart_recovery_persisted_row_attestation import attest_persisted_checkpoint_load
from tests.test_restart_recovery_persisted_row_attestation import PersistedRowLoadAttestationTests


class WP901WP206SameInodeDriftIntegrationTests(PersistedRowLoadAttestationTests):
    def test_wp901_ingress_fails_closed_on_external_wp206_same_inode_surface_drift(self) -> None:
        _, checkpoint, _, _, _ = self.sources()
        before = self.db.stat()

        external = sqlite3.connect(self.db)
        try:
            external.execute(
                f"CREATE INDEX idx_wp901_wp206_external_drift "
                f"ON {CHECKPOINT_TABLE}(checkpoint_id)"
            )
            external.commit()
        finally:
            external.close()

        after = self.db.stat()
        self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))

        with self.assertRaisesRegex(
            PersistentAgencyError,
            "UNIFIEDDB_WP206_OWNED_SURFACE_DRIFT",
        ):
            attest_persisted_checkpoint_load(
                self.store,
                checkpoint_id=checkpoint.checkpoint_id,
            )


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
