from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.clean_machine_acceptance import (
    AcceptanceObservation,
    CleanMachineAcceptanceError,
    REAL_HOST_EVIDENCE_SCOPE,
    evaluate_clean_machine_acceptance,
)

MANIFEST_SHA = "a" * 64
RECEIPT = "workpackages/receipts/pre-handoff.json"


class CleanMachineAcceptanceTests(unittest.TestCase):
    def observation(self, case_id: str, **overrides) -> AcceptanceObservation:
        values = {
            "case_id": case_id,
            "environment_id": f"clean-env-{case_id}",
            "release_manifest_sha256": MANIFEST_SHA,
            "prehandoff_receipt_ref": RECEIPT,
            "route_result": "ACCEPTED",
            "evidence_scope": REAL_HOST_EVIDENCE_SCOPE,
            "observed_at": "2026-08-29T12:55:00Z",
            "evidence_refs": (f"receipt:{case_id}",),
            "lifecycle_firing_observed": False,
            "durable_state_readback_observed": True,
            "restart_recovery_observed": True,
            "reinstall_update_persistence_observed": True,
            "uninstall_disable_observed": True,
            "baseline_local_boot_observed": True,
            "single_state_lineage_verified": True,
            "vps_configured": False,
            "vps_bridge_attach_observed": False,
            "vps_bridge_detach_observed": False,
            "remote_second_state_authority_observed": False,
            "perception_enabled": False,
            "perception_binding_observed": False,
            "perception_permission_revocation_observed": False,
            "limitations": (),
            "adapted_route_evidence_ref": None,
        }
        if case_id == "claude_code":
            values.update(route_result="NATIVE", lifecycle_firing_observed=True)
        elif case_id == "codex_cli":
            values.update(route_result="NATIVE", lifecycle_firing_observed=True)
        elif case_id == "other_agent":
            values.update(route_result="ADAPTED", lifecycle_firing_observed=True)
        elif case_id == "vps_bridge":
            values.update(
                vps_configured=True,
                vps_bridge_attach_observed=True,
                vps_bridge_detach_observed=True,
            )
        elif case_id == "perception_enabled":
            values.update(
                perception_enabled=True,
                perception_binding_observed=True,
                perception_permission_revocation_observed=True,
            )
        values.update(overrides)
        return AcceptanceObservation(**values)

    def base_matrix(self):
        return [
            self.observation("claude_code"),
            self.observation("codex_cli"),
            self.observation("other_agent"),
            self.observation("no_vps_baseline"),
            self.observation("vps_bridge"),
        ]

    def evaluate(self, observations, *, perception_required=False):
        return evaluate_clean_machine_acceptance(
            observations,
            release_manifest_sha256=MANIFEST_SHA,
            prehandoff_receipt_ref=RECEIPT,
            perception_required=perception_required,
        )

    def test_complete_matrix_is_ready_for_review_but_mints_zero_credit(self):
        result = self.evaluate(self.base_matrix())
        self.assertEqual(result.status, "READY_FOR_ADMISSION_REVIEW")
        self.assertEqual(result.violations, ())
        self.assertEqual(result.runtime_credit, 0)
        self.assertEqual(result.physical_host_credit, 0)
        self.assertEqual(result.completion_credit, 0)
        self.assertFalse(result.whole_system_acceptance)

    def test_result_is_deterministic_across_observation_order(self):
        observations = self.base_matrix()
        first = self.evaluate(observations)
        second = self.evaluate(list(reversed(observations)))
        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
        self.assertEqual(first.sha256(), second.sha256())

    def test_missing_required_case_blocks(self):
        result = self.evaluate(self.base_matrix()[:-1])
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("vps_bridge:missing", result.violations)

    def test_duplicate_case_is_structurally_rejected(self):
        observations = self.base_matrix()
        observations.append(self.observation("claude_code", environment_id="other-env"))
        with self.assertRaisesRegex(CleanMachineAcceptanceError, "duplicate"):
            self.evaluate(observations)

    def test_release_manifest_mismatch_blocks(self):
        observations = self.base_matrix()
        observations[1] = replace(
            observations[1], release_manifest_sha256="b" * 64
        )
        result = self.evaluate(observations)
        self.assertIn("codex_cli:release_manifest_sha256 mismatch", result.violations)

    def test_source_only_scope_cannot_masquerade_as_real_clean_machine_evidence(self):
        observations = self.base_matrix()
        observations[0] = replace(observations[0], evidence_scope="REPOSITORY_CI_ONLY")
        result = self.evaluate(observations)
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(
            any("claude_code:evidence_scope" in item for item in result.violations)
        )

    def test_claude_adapted_route_requires_explicit_exception_evidence(self):
        observations = self.base_matrix()
        observations[0] = replace(observations[0], route_result="ADAPTED")
        result = self.evaluate(observations)
        self.assertIn(
            "claude_code:ADAPTED requires adapted_route_evidence_ref",
            result.violations,
        )

    def test_other_agent_degraded_requires_precise_limitations(self):
        observations = self.base_matrix()
        observations[2] = replace(observations[2], route_result="DEGRADED")
        result = self.evaluate(observations)
        self.assertIn(
            "other_agent:DEGRADED/BLOCKED requires precise limitations",
            result.violations,
        )
        observations[2] = replace(
            observations[2], limitations=("BACKGROUND_WAKE unavailable",)
        )
        result = self.evaluate(observations)
        self.assertNotIn(
            "other_agent:DEGRADED/BLOCKED requires precise limitations",
            result.violations,
        )

    def test_no_vps_baseline_must_really_boot_without_vps(self):
        observations = self.base_matrix()
        observations[3] = replace(
            observations[3], baseline_local_boot_observed=False
        )
        result = self.evaluate(observations)
        self.assertIn(
            "no_vps_baseline:baseline_local_boot_observed=false",
            result.violations,
        )

    def test_vps_bridge_requires_attach_detach_and_local_continuity(self):
        observations = self.base_matrix()
        observations[4] = replace(
            observations[4],
            vps_bridge_detach_observed=False,
            single_state_lineage_verified=False,
        )
        result = self.evaluate(observations)
        self.assertIn(
            "vps_bridge:vps_bridge_detach_observed=false", result.violations
        )
        self.assertIn(
            "vps_bridge:single_state_lineage_verified=false", result.violations
        )

    def test_second_remote_state_authority_always_blocks(self):
        observations = self.base_matrix()
        observations[4] = replace(
            observations[4], remote_second_state_authority_observed=True
        )
        result = self.evaluate(observations)
        self.assertIn(
            "vps_bridge:remote_second_state_authority_observed=true",
            result.violations,
        )

    def test_perception_row_and_permission_revocation_are_conditional_but_mandatory(self):
        result = self.evaluate(self.base_matrix(), perception_required=True)
        self.assertIn("perception_enabled:missing", result.violations)

        observations = self.base_matrix() + [self.observation("perception_enabled")]
        result = self.evaluate(observations, perception_required=True)
        self.assertEqual(result.status, "READY_FOR_ADMISSION_REVIEW")

        observations[-1] = replace(
            observations[-1], perception_permission_revocation_observed=False
        )
        result = self.evaluate(observations, perception_required=True)
        self.assertIn(
            "perception_enabled:perception_permission_revocation_observed=false",
            result.violations,
        )

    def test_environment_identity_reuse_across_cases_blocks(self):
        observations = self.base_matrix()
        observations[1] = replace(
            observations[1], environment_id=observations[0].environment_id
        )
        result = self.evaluate(observations)
        self.assertIn(
            "environment_id must be unique per clean-machine case",
            result.violations,
        )


if __name__ == "__main__":
    unittest.main()
