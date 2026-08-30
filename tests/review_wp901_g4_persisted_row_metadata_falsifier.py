#!/usr/bin/env python3
"""REVIEW_ONLY falsifier for WP901 G4 persisted-row metadata binding.

A successful test means the candidate G4 ingress still emits the same positive row-load
attestation and restart plan after redundant persisted lineage columns are changed while
the checkpoint JSON/digest remain untouched. This is negative evidence only; it does not
claim runtime, effect, completion, GRID10, GWT/J-Space, training or whole-system failure.
"""
from __future__ import annotations

import unittest

from tests.test_restart_recovery_persisted_row import RestartRecoveryPersistedRowTests


class Wp901G4RowMetadataAttestationFalsifier(RestartRecoveryPersistedRowTests):
    def test_counterexample_reproduced(self) -> None:
        baseline = self.plan()
        baseline_attestation_sha = baseline.attestation.sha256()
        baseline_plan_sha = baseline.plan.sha256()

        forged_generation = self.checkpoint.generation + 100
        forged_parent = "review-forged-persisted-parent"
        self.store.connection.execute(
            """UPDATE f2_persistent_agency_checkpoints
               SET generation=?, previous_checkpoint_id=?
               WHERE checkpoint_id=?""",
            (forged_generation, forged_parent, self.checkpoint.checkpoint_id),
        )
        self.store.connection.commit()

        persisted = self.store.connection.execute(
            """SELECT generation, previous_checkpoint_id
               FROM f2_persistent_agency_checkpoints WHERE checkpoint_id=?""",
            (self.checkpoint.checkpoint_id,),
        ).fetchone()
        self.assertEqual(persisted, (forged_generation, forged_parent))

        reproduced = self.plan()
        self.assertEqual(reproduced.attestation.sha256(), baseline_attestation_sha)
        self.assertEqual(reproduced.plan.sha256(), baseline_plan_sha)
        self.assertEqual(
            reproduced.attestation.checkpoint_generation,
            self.checkpoint.generation,
        )
        self.assertNotEqual(
            reproduced.attestation.checkpoint_generation,
            forged_generation,
        )
        self.assertNotIn("row_evidence_sha256", reproduced.attestation.as_dict())

        print(
            "PASS_REPRODUCED_WP901_G4_ROW_METADATA_ATTESTATION_GAP: "
            "candidate G4 accepted the same checkpoint/attestation/plan after persisted "
            "generation and previous_checkpoint_id columns diverged from checkpoint JSON"
        )


if __name__ == "__main__":
    unittest.main()
