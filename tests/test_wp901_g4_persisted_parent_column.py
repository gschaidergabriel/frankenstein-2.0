#!/usr/bin/env python3
"""Regression promoted from REVIEW_ONLY PR #715 executable counterevidence."""
from __future__ import annotations

import unittest

from frankenstein2.persistent_agency_kernel import CHECKPOINT_TABLE
from frankenstein2.restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationError,
    plan_restart_continuation_from_persisted_row,
)
from tests.test_restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationTests,
)


class WP901G4PersistedParentColumnRegression(PersistedRowLoadAttestationTests):
    def test_persisted_previous_checkpoint_id_must_match_loaded_checkpoint(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()

        forged_parent = checkpoint.checkpoint_id
        self.assertNotEqual(forged_parent, checkpoint.previous_checkpoint_id)
        self.store.connection.execute(
            f"""UPDATE {CHECKPOINT_TABLE}
                SET previous_checkpoint_id=? WHERE checkpoint_id=?""",
            (forged_parent, checkpoint.checkpoint_id),
        )
        self.store.connection.commit()

        persisted = self.store.connection.execute(
            f"SELECT previous_checkpoint_id FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?",
            (checkpoint.checkpoint_id,),
        ).fetchone()
        self.assertEqual(persisted[0], forged_parent)

        with self.assertRaisesRegex(
            PersistedRowLoadAttestationError,
            "PERSISTED_ROW_PREVIOUS_CHECKPOINT_ID_MISMATCH",
        ):
            plan_restart_continuation_from_persisted_row(
                self.store,
                checkpoint_id=checkpoint.checkpoint_id,
                evidence=evidence,
                plan_id="regression-persisted-parent-column-plan",
                expected_evidence_sha256=evidence.sha256(),
                causal_identity=causal,
                unifieddb_authority=self.authority(),
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_positive_attestation_exposes_loaded_checkpoint_parent(self) -> None:
        result, _, checkpoint, _, _, _ = self.plan()
        raw = result.load_attestation.as_dict()
        self.assertEqual(
            result.load_attestation.checkpoint_previous_checkpoint_id,
            checkpoint.previous_checkpoint_id,
        )
        self.assertEqual(
            raw["checkpoint_previous_checkpoint_id"],
            checkpoint.previous_checkpoint_id,
        )
        self.assertEqual(len(raw["row_evidence_sha256"]), 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
