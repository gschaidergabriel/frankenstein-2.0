#!/usr/bin/env python3
"""Regression promoted from PR704 post-G3 predecessor-lineage counterevidence."""
from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.restart_recovery_source_authentication import (
    RestartSourceAuthenticationError,
    bind_restart_sources,
)
from tests.test_restart_recovery_source_authentication import (
    RestartRecoverySourceAuthenticationTests,
    authority,
)


class WP901G4PreviousCheckpointLineageRegression(unittest.TestCase):
    def test_direct_predecessor_mismatch_fails_closed(self) -> None:
        fixture = RestartRecoverySourceAuthenticationTests()
        causal, checkpoint, seal, outcome, evidence = fixture.sources()

        forged_checkpoint = replace(
            checkpoint,
            previous_checkpoint_id="checkpoint-from-different-direct-lineage",
        )
        forged_seal = replace(
            seal,
            next_checkpoint_sha256=forged_checkpoint.sha256(),
        )
        forged_evidence = replace(
            evidence,
            source_checkpoint_sha256=forged_checkpoint.sha256(),
            whole_loop_seal_sha256=forged_seal.sha256(),
        )

        with self.assertRaisesRegex(
            RestartSourceAuthenticationError,
            "SOURCE_AUTH_DIRECT_PREDECESSOR_CHECKPOINT_MISMATCH",
        ):
            bind_restart_sources(
                forged_evidence,
                causal_identity=causal,
                unifieddb_authority=authority(),
                source_checkpoint=forged_checkpoint,
                whole_loop_seal=forged_seal,
                outcome=outcome,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
