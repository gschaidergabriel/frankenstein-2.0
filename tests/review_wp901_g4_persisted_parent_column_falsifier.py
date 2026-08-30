#!/usr/bin/env python3
"""REVIEW_ONLY exact-current falsifier for WP901 G4 persisted parent-column binding.

A green test is NEGATIVE EVIDENCE: the current G4 candidate can load/attest/plan from a
checkpoint row whose separately persisted `previous_checkpoint_id` column disagrees with the
canonical checkpoint JSON and typed checkpoint that G3 authenticates.

No canonical mutation, runtime, effect, completion, training or whole-system authority.
"""
from __future__ import annotations

import unittest

from frankenstein2.persistent_agency_kernel import CHECKPOINT_TABLE
from frankenstein2.restart_recovery_persisted_row_attestation import (
    plan_restart_continuation_from_persisted_row,
)
from tests.test_restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationTests,
)


class WP901G4PersistedParentColumnFalsifier(PersistedRowLoadAttestationTests):
    def test_counterexample_reproduced(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()

        before = self.store.connection.execute(
            f"""SELECT previous_checkpoint_id, checkpoint_json
                FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
            (checkpoint.checkpoint_id,),
        ).fetchone()
        self.assertIsNotNone(before)
        original_parent, original_json = before
        self.assertEqual(original_parent, checkpoint.previous_checkpoint_id)

        # Keep the row foreign-key-valid while making the redundant persisted parent column
        # disagree with the checkpoint JSON. A self-reference names an existing row and is
        # therefore sufficient to isolate the omitted-column question.
        forged_parent = checkpoint.checkpoint_id
        self.assertNotEqual(forged_parent, checkpoint.previous_checkpoint_id)
        self.store.connection.execute(
            f"""UPDATE {CHECKPOINT_TABLE}
                SET previous_checkpoint_id=? WHERE checkpoint_id=?""",
            (forged_parent, checkpoint.checkpoint_id),
        )
        self.store.connection.commit()

        after = self.store.connection.execute(
            f"""SELECT previous_checkpoint_id, checkpoint_json
                FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
            (checkpoint.checkpoint_id,),
        ).fetchone()
        self.assertEqual(after[0], forged_parent)
        self.assertEqual(after[1], original_json)

        result = plan_restart_continuation_from_persisted_row(
            self.store,
            checkpoint_id=checkpoint.checkpoint_id,
            evidence=evidence,
            plan_id="review-persisted-parent-column-plan",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            unifieddb_authority=self.authority(),
            whole_loop_seal=seal,
            outcome=outcome,
        )

        # The typed checkpoint reconstructed from JSON still has the original direct parent,
        # so G3 correctly sees it as seal-consistent. The question here is only whether G4's
        # persisted-row attestation notices the separately stored FK-column disagreement.
        loaded = self.store.load_checkpoint(checkpoint.checkpoint_id)
        self.assertEqual(loaded.previous_checkpoint_id, checkpoint.previous_checkpoint_id)
        self.assertNotEqual(after[0], loaded.previous_checkpoint_id)
        self.assertEqual(result.plan.source_checkpoint_id, checkpoint.checkpoint_id)
        raw = result.load_attestation.as_dict()
        self.assertIn("row_evidence_sha256", raw)
        self.assertNotIn("previous_checkpoint_id", raw)

        print(
            "PASS_REPRODUCED_WP901_G4_PERSISTED_PARENT_COLUMN_GAP: "
            "G4 emitted positive persisted-row attestation and a restart plan while the "
            "row previous_checkpoint_id column disagreed with the loaded checkpoint JSON"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
