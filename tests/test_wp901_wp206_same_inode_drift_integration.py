#!/usr/bin/env python3
"""Cross-component regression: WP206 same-inode drift guard must fence WP901 ingress."""
from __future__ import annotations

import sqlite3
import unittest

from frankenstein2.persistent_agency_kernel import CHECKPOINT_TABLE, PersistentAgencyError
from frankenstein2.restart_recovery_persisted_row_attestation import (
    plan_restart_continuation_from_persisted_row,
)
from tests.test_restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationTests,
)


class WP901WP206SameInodeDriftIntegrationTests(PersistedRowLoadAttestationTests):
    def test_external_wp206_surface_drift_fails_before_restart_plan(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()

        external = sqlite3.connect(self.db)
        try:
            external.execute(
                f"UPDATE {CHECKPOINT_TABLE} "
                "SET unifieddb_authority_receipt_sha256=? WHERE checkpoint_id=?",
                ("0" * 64, checkpoint.checkpoint_id),
            )
            external.commit()
        finally:
            external.close()

        with self.assertRaisesRegex(
            PersistentAgencyError,
            "UNIFIEDDB_WP206_OWNED_SURFACE_DRIFT",
        ):
            plan_restart_continuation_from_persisted_row(
                self.store,
                checkpoint_id=checkpoint.checkpoint_id,
                evidence=evidence,
                plan_id="restart-plan-wp901-wp206-same-inode-drift",
                expected_evidence_sha256=evidence.sha256(),
                causal_identity=causal,
                unifieddb_authority=self.authority(),
                whole_loop_seal=seal,
                outcome=outcome,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
