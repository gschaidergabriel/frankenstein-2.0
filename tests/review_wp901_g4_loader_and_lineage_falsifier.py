#!/usr/bin/env python3
"""REVIEW_ONLY executable falsifiers for the in-flight WP901 G4 candidate.

A green run of these tests is NEGATIVE EVIDENCE: it means the counterexamples are
reproduced. No canonical workpackage mutation authority is claimed.
"""
from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore
from frankenstein2.restart_recovery_persisted_row_attestation import (
    attest_persisted_restart_checkpoint,
    plan_restart_continuation_from_persisted_row,
)
from tests.test_restart_recovery_persisted_row_attestation import (
    RestartRecoveryPersistedRowAttestationTests,
    authority,
    sha,
)


class Wp901G4ReviewFalsifiers(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RestartRecoveryPersistedRowAttestationTests(
            methodName="test_canonical_g4_ingress_loads_row_then_preserves_g3_g2_semantics"
        )
        self.fixture.setUp()

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def test_hostile_store_subclass_can_mint_canonical_load_attestation_without_db_read(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.fixture.sources()

        class HostileStore(CanonicalPersistentAgencyStore):
            calls = 0

            def load_checkpoint(self, checkpoint_id):
                type(self).calls += 1
                self.last_requested_id = checkpoint_id
                # Deliberately bypass CanonicalPersistentAgencyStore.load_checkpoint and
                # return the caller-selected typed object without querying SQLite.
                return checkpoint

        hostile = object.__new__(HostileStore)
        hostile.canonical_db_path = "/review/not-actually-read/unified.db"
        hostile.db_device = 424242
        hostile.db_inode = 313131
        hostile.authority_receipt_sha256 = "a" * 64

        loaded, receipt = attest_persisted_restart_checkpoint(
            evidence,
            store=hostile,
        )

        self.assertIs(loaded, checkpoint)
        self.assertEqual(HostileStore.calls, 1)
        self.assertEqual(hostile.last_requested_id, evidence.source_checkpoint_id)
        raw = receipt.as_dict()
        self.assertEqual(
            raw["persisted_checkpoint_row_attestation"],
            "OBSERVED_VIA_CANONICAL_STORE_LOAD",
        )
        self.assertEqual(raw["canonical_db_path"], hostile.canonical_db_path)
        self.assertEqual(raw["db_device"], hostile.db_device)
        self.assertEqual(raw["db_inode"], hostile.db_inode)
        self.assertNotIn(
            "row_evidence_sha256",
            raw,
            "current candidate does not bind a digest over exact consumed persisted columns",
        )
        print(
            "PASS_REPRODUCED_WP901_G4_HOSTILE_LOADER_SUBSTITUTION: "
            "isinstance accepted a CanonicalPersistentAgencyStore subclass whose overridden "
            "load_checkpoint performed no SQLite read, yet G4 emitted "
            "OBSERVED_VIA_CANONICAL_STORE_LOAD"
        )

    def test_real_row_load_does_not_close_previous_checkpoint_vs_seal_current_lineage_gap(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.fixture.sources()

        # The checkpoint is genuinely persisted and will be loaded through the real WP206
        # store. Forge only the WP900 seal's claimed current predecessor, while preserving
        # seal -> exact persisted next checkpoint and every G3 causal provenance witness.
        forged_seal = replace(
            seal,
            current_checkpoint_id="checkpoint-from-different-direct-lineage",
            current_checkpoint_sha256=sha("checkpoint-from-different-direct-lineage"),
        )
        self.assertNotEqual(
            checkpoint.previous_checkpoint_id,
            forged_seal.current_checkpoint_id,
        )
        forged_evidence = replace(
            evidence,
            whole_loop_seal_sha256=forged_seal.sha256(),
        )

        plan = plan_restart_continuation_from_persisted_row(
            forged_evidence,
            plan_id="review-g4-mixed-predecessor-plan",
            expected_evidence_sha256=forged_evidence.sha256(),
            causal_identity=causal,
            unifieddb_authority=authority(),
            store=self.fixture.store,
            whole_loop_seal=forged_seal,
            outcome=outcome,
        )

        self.assertEqual(plan.source_checkpoint_id, checkpoint.checkpoint_id)
        self.assertNotEqual(
            checkpoint.previous_checkpoint_id,
            forged_seal.current_checkpoint_id,
        )
        print(
            "PASS_REPRODUCED_WP901_G4_PERSISTED_ROW_PREDECESSOR_LINEAGE_COUNTEREXAMPLE: "
            "a real WP206 row load still admitted a WP900 seal whose current_checkpoint_id "
            "does not match the persisted restart checkpoint.previous_checkpoint_id"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
