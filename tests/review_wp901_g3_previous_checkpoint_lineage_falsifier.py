#!/usr/bin/env python3
"""REVIEW_ONLY executable falsifier for accepted WP901 G3 source authentication.

Question: does the canonical G3 boundary verify that the concrete restart checkpoint's
`previous_checkpoint_id` is the same checkpoint that the WP900 whole-loop seal names as
`current_checkpoint_id`?

A successful test means the counterexample was reproduced: all currently accepted G3
identity/digest/provenance checks pass while that direct predecessor link is inconsistent.
No canonical workpackage mutation or runtime/whole-system credit is claimed here.
"""
from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.restart_recovery_source_authentication import bind_restart_sources
from tests.test_restart_recovery_source_authentication import (
    RestartRecoverySourceAuthenticationTests,
    authority,
)


class AcceptedG3PreviousCheckpointLineageFalsifier(unittest.TestCase):
    def test_counterexample_reproduced(self) -> None:
        fixture = RestartRecoverySourceAuthenticationTests()
        causal, checkpoint, seal, outcome, evidence = fixture.sources()

        # Keep the accepted G3 causal provenance witness on every object, generation
        # relationship, checkpoint identity, seal->next-checkpoint binding and outcome
        # binding. Change only the checkpoint's declared predecessor to a different id.
        forged_checkpoint = replace(
            checkpoint,
            previous_checkpoint_id="checkpoint-from-different-direct-lineage",
        )
        self.assertNotEqual(
            forged_checkpoint.previous_checkpoint_id,
            seal.current_checkpoint_id,
            "falsifier setup must contain a real predecessor-lineage mismatch",
        )

        # Rebind every digest that accepted G3 actually authenticates so this is not a
        # stale-hash test. The concrete source objects remain mutually hash-consistent.
        forged_seal = replace(
            seal,
            next_checkpoint_sha256=forged_checkpoint.sha256(),
        )
        forged_evidence = replace(
            evidence,
            source_checkpoint_sha256=forged_checkpoint.sha256(),
            whole_loop_seal_sha256=forged_seal.sha256(),
        )

        binding = bind_restart_sources(
            forged_evidence,
            causal_identity=causal,
            unifieddb_authority=authority(),
            source_checkpoint=forged_checkpoint,
            whole_loop_seal=forged_seal,
            outcome=outcome,
        )

        # If canonical G3 later closes this gap, this review-only reproduction test will
        # fail and should be retired/re-written as a rejection regression.
        self.assertEqual(binding.checkpoint_id, forged_checkpoint.checkpoint_id)
        self.assertNotEqual(
            forged_checkpoint.previous_checkpoint_id,
            forged_seal.current_checkpoint_id,
        )
        print(
            "PASS_REPRODUCED_WP901_G3_PREVIOUS_CHECKPOINT_LINEAGE_COUNTEREXAMPLE: "
            "canonical G3 accepted a checkpoint whose previous_checkpoint_id does not "
            "match whole_loop_seal.current_checkpoint_id"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
