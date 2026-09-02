#!/usr/bin/env python3
"""REVIEW_ONLY counterexample: WP901 can resume a valid stale WP206 ancestor.

This test intentionally characterizes the currently documented freshness gap. It changes no
product source and grants no runtime/completion credit. PASS means a caller can select an
older still-valid checkpoint even after the same WP206 lineage has a newer authoritative
head in the canonical store.
"""
from __future__ import annotations

import unittest

from frankenstein2.persistent_agency_kernel import advance_checkpoint
from frankenstein2.restart_recovery_persisted_row_attestation import (
    plan_restart_continuation_from_persisted_row,
)
from tests.test_restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationTests,
)


class WP901RollbackFreshnessCounterexample(PersistedRowLoadAttestationTests):
    def test_valid_stale_ancestor_is_currently_accepted_after_newer_lineage_head_exists(self) -> None:
        causal, stale_checkpoint, seal, outcome, evidence = self.sources()

        newer_checkpoint = advance_checkpoint(
            stale_checkpoint,
            checkpoint_id="checkpoint-wp901-freshness-newer-head",
            pulse_id="pulse-wp901-freshness-newer-head",
            observation_id="observation-wp901-freshness-newer-head",
            provenance_refs=stale_checkpoint.provenance_refs,
        )
        self.store.write_checkpoint(newer_checkpoint)

        latest = self.store.latest_checkpoint(stale_checkpoint.kernel_state_id)
        self.assertEqual(latest.checkpoint_id, newer_checkpoint.checkpoint_id)
        self.assertGreater(latest.generation, stale_checkpoint.generation)

        result = plan_restart_continuation_from_persisted_row(
            self.store,
            checkpoint_id=stale_checkpoint.checkpoint_id,
            evidence=evidence,
            plan_id="restart-plan-wp901-stale-ancestor-counterexample",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            unifieddb_authority=self.authority(),
            whole_loop_seal=seal,
            outcome=outcome,
        )

        # Positive reproduction of the known gap: the old row remains byte-valid and is
        # accepted even though WP206's own authoritative latest_checkpoint() is newer.
        self.assertEqual(result.plan.source_checkpoint_id, stale_checkpoint.checkpoint_id)
        self.assertEqual(
            result.load_attestation.as_dict()["freshness_attestation"],
            "NOT_OBSERVED",
        )
        self.assertEqual(result.as_dict()["runtime_credit"], 0)
        self.assertFalse(result.as_dict()["whole_system_acceptance"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
