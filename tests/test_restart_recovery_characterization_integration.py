#!/usr/bin/env python3
"""Cross-component discriminator for WP901 restart recovery -> WP902 characterization.

Repository integration evidence only. The test exercises the existing WP901 persisted-row
planner through the existing WP902 source-bound measurement producer. It intentionally mints
no target-host, runtime, effect, completion, or whole-system authority.
"""
from __future__ import annotations

from pathlib import Path
import unittest

from frankenstein2.restart_recovery_continuation import CONTINUE_UNFINISHED
from frankenstein2.whole_system_measurement import measure_characterization_sample
from tests import test_restart_recovery_persisted_row_attestation as wp901_test


_ACTIVE_CASE: wp901_test.PersistedRowLoadAttestationTests | None = None


def exercise_persisted_restart_plan():
    """Run the existing WP901 persisted-row restart/readback path without a second adapter."""
    if _ACTIVE_CASE is None:
        raise AssertionError("integration fixture is not active")
    return _ACTIVE_CASE.plan()


def score_persisted_restart_plan(result_bundle) -> int:
    """Score only an exact continued plan whose load attestation remains fail-closed in scope."""
    result, _causal, checkpoint, _seal, _outcome, _evidence = result_bundle
    attestation = result.load_attestation
    accepted = (
        result.plan.disposition == CONTINUE_UNFINISHED
        and result.plan.source_checkpoint_id == checkpoint.checkpoint_id
        and result.plan.source_checkpoint_sha256 == checkpoint.sha256()
        and attestation.checkpoint_id == checkpoint.checkpoint_id
        and attestation.checkpoint_generation == checkpoint.generation
        and attestation.checkpoint_sha256 == checkpoint.sha256()
        and attestation.runtime_credit == 0
        and attestation.whole_system_acceptance is False
    )
    return 1_000_000 if accepted else 0


class RestartRecoveryCharacterizationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        global _ACTIVE_CASE
        self.case = wp901_test.PersistedRowLoadAttestationTests(
            methodName="test_real_wp206_row_load_is_attested_before_g3_g2_planning"
        )
        self.case.setUp()
        _ACTIVE_CASE = self.case
        self.repo_root = Path(__file__).resolve().parents[1]

    def tearDown(self) -> None:
        global _ACTIVE_CASE
        _ACTIVE_CASE = None
        self.case.tearDown()

    def test_wp901_restart_readback_is_measured_by_existing_wp902_producer(self) -> None:
        source_paths = (
            "tests/test_restart_recovery_characterization_integration.py",
            "tests/test_restart_recovery_persisted_row_attestation.py",
            "tests/test_whole_persistent_loop.py",
            "src/frankenstein2/persistent_agency_kernel.py",
            "src/frankenstein2/restart_recovery_continuation.py",
            "src/frankenstein2/restart_recovery_persisted_row_attestation.py",
            "src/frankenstein2/restart_recovery_source_authentication.py",
            "src/frankenstein2/whole_persistent_loop.py",
            "src/frankenstein2/whole_system_characterization.py",
            "src/frankenstein2/whole_system_measurement.py",
            "src/state/unifieddb_identity.py",
        )
        _causal, _checkpoint, whole_loop_seal, _outcome, _evidence = self.case.sources()

        sample = measure_characterization_sample(
            run_id="wp901-wp902-restart-characterization",
            trial_index=0,
            repo_root=self.repo_root,
            source_paths=source_paths,
            whole_loop_seal=whole_loop_seal,
            operation=exercise_persisted_restart_plan,
            quality_scorer=score_persisted_restart_plan,
            provenance_refs=(
                "integration:wp901:persisted-row-restart-readback",
                "integration:wp902:source-bound-characterization",
            ),
        )

        self.assertEqual(sample.whole_loop_seal_sha256, whole_loop_seal.sha256())
        self.assertEqual(sample.quality_micros, 1_000_000)
        self.assertIn(
            "integration:wp901:persisted-row-restart-readback",
            sample.provenance_refs,
        )
        self.assertIn(
            "integration:wp902:source-bound-characterization",
            sample.provenance_refs,
        )

        result, _causal, checkpoint, _seal, _outcome, _evidence = exercise_persisted_restart_plan()
        self.assertEqual(result.plan.source_checkpoint_id, checkpoint.checkpoint_id)
        raw = result.load_attestation.as_dict()
        self.assertEqual(raw["target_host_execution"], "NOT_OBSERVED")
        self.assertEqual(raw["runtime_credit"], 0)
        self.assertFalse(raw["whole_system_acceptance"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
