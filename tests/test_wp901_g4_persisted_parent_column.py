#!/usr/bin/env python3
"""Regression for the executable WP901 G4 persisted parent-column counterexample.

PR #715 reproduced that the separately persisted SQL ``previous_checkpoint_id`` column could
disagree with the canonical checkpoint JSON while G4 still emitted positive persisted-row
attestation.  The canonical G4 repair must fail closed on that exact mismatch without
broadening into global same-inode freshness or target-runtime claims.
"""
from __future__ import annotations

from frankenstein2.persistent_agency_kernel import CHECKPOINT_TABLE
from frankenstein2.restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationError,
    plan_restart_continuation_from_persisted_row,
)
from tests.test_restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationTests,
)


class WP901G4PersistedParentColumnRegression(PersistedRowLoadAttestationTests):
    def test_persisted_parent_column_mismatch_fails_closed(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()

        before = self.store.connection.execute(
            f"""SELECT previous_checkpoint_id, checkpoint_json
                FROM {CHECKPOINT_TABLE} WHERE checkpoint_id=?""",
            (checkpoint.checkpoint_id,),
        ).fetchone()
        self.assertIsNotNone(before)
        original_parent, original_json = before
        self.assertEqual(original_parent, checkpoint.previous_checkpoint_id)

        # Keep the FK valid while changing only the redundant persisted parent column.
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

        with self.assertRaisesRegex(
            PersistedRowLoadAttestationError,
            "PERSISTED_ROW_PREVIOUS_CHECKPOINT_ID_MISMATCH",
        ):
            plan_restart_continuation_from_persisted_row(
                self.store,
                checkpoint_id=checkpoint.checkpoint_id,
                evidence=evidence,
                plan_id="regress-persisted-parent-column-plan",
                expected_evidence_sha256=evidence.sha256(),
                causal_identity=causal,
                unifieddb_authority=self.authority(),
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_positive_attestation_binds_persisted_parent_column(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        result = plan_restart_continuation_from_persisted_row(
            self.store,
            checkpoint_id=checkpoint.checkpoint_id,
            evidence=evidence,
            plan_id="positive-persisted-parent-column-plan",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            unifieddb_authority=self.authority(),
            whole_loop_seal=seal,
            outcome=outcome,
        )
        raw = result.load_attestation.as_dict()
        self.assertEqual(
            raw["previous_checkpoint_id"],
            checkpoint.previous_checkpoint_id,
        )
        self.assertEqual(raw["persisted_row_attestation"], "OBSERVED_AT_REPOSITORY_COMPONENT_SCOPE")
        self.assertEqual(raw["target_host_execution"], "NOT_OBSERVED")
        self.assertEqual(raw["runtime_credit"], 0)
        self.assertFalse(raw["whole_system_acceptance"])


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
