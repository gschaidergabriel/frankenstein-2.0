from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.artifact_bound_clean_machine import (
    ArtifactBoundAcceptanceObservation,
    ArtifactBoundCleanMachineError,
    evaluate_artifact_bound_clean_machine_acceptance,
)
from frankenstein2.clean_machine_acceptance import (
    AcceptanceObservation,
    REAL_HOST_EVIDENCE_SCOPE,
)
from frankenstein2.pre_handoff_release import READY_STATUS
from frankenstein2.release_artifact_subject import (
    ArtifactBoundPreHandoffReceipt,
    ReleaseArtifactSubject,
)

MANIFEST_SHA = "a" * 64
ARTIFACT_SHA = "b" * 64
POLICY_SHA = "c" * 64
STATIC_SHA = "d" * 64
RECEIPT_REF = "receipts/F2-WP-1110-g2-prehandoff.json"


class ArtifactBoundCleanMachineTests(unittest.TestCase):
    def prehandoff(self) -> ArtifactBoundPreHandoffReceipt:
        subject = ReleaseArtifactSubject(
            artifact_filename="frankenstein-2.0.zip",
            artifact_sha256=ARTIFACT_SHA,
            artifact_size_bytes=123456,
            release_manifest_sha256=MANIFEST_SHA,
            source_commit="1" * 40,
            source_tree="2" * 40,
            release_id="f2-release-test",
            build_id="build-test",
            archive_policy_id="f2-release-zip-stored-posix-v1",
            archive_policy_sha256=POLICY_SHA,
            member_count=42,
        )
        return ArtifactBoundPreHandoffReceipt(
            subject=subject,
            prehandoff_receipt_ref=RECEIPT_REF,
            static_prehandoff_sha256=STATIC_SHA,
            static_status=READY_STATUS,
            static_violations=(),
            status=READY_STATUS,
        )

    def observation(self, case_id: str, **overrides) -> AcceptanceObservation:
        values = {
            "case_id": case_id,
            "environment_id": f"clean-env-{case_id}",
            "release_manifest_sha256": MANIFEST_SHA,
            "prehandoff_receipt_ref": RECEIPT_REF,
            "route_result": "ACCEPTED",
            "evidence_scope": REAL_HOST_EVIDENCE_SCOPE,
            "observed_at": "2026-08-30T00:00:00Z",
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
        if case_id in {"claude_code", "codex_cli"}:
            values.update(route_result="NATIVE", lifecycle_firing_observed=True)
        elif case_id == "other_agent":
            values.update(route_result="ADAPTED", lifecycle_firing_observed=True)
        elif case_id == "vps_bridge":
            values.update(
                vps_configured=True,
                vps_bridge_attach_observed=True,
                vps_bridge_detach_observed=True,
            )
        values.update(overrides)
        return AcceptanceObservation(**values)

    def wrap(self, observation: AcceptanceObservation, **overrides):
        subject = self.prehandoff().subject
        values = {
            "observation": observation,
            "artifact_filename": subject.artifact_filename,
            "artifact_sha256": subject.artifact_sha256,
            "artifact_size_bytes": subject.artifact_size_bytes,
            "artifact_subject_sha256": subject.sha256(),
        }
        values.update(overrides)
        return ArtifactBoundAcceptanceObservation(**values)

    def matrix(self):
        return [
            self.wrap(self.observation("claude_code")),
            self.wrap(self.observation("codex_cli")),
            self.wrap(self.observation("other_agent")),
            self.wrap(self.observation("no_vps_baseline")),
            self.wrap(self.observation("vps_bridge")),
        ]

    def test_exact_artifact_bound_matrix_is_ready_but_mints_zero_credit(self) -> None:
        prehandoff = self.prehandoff()
        result = evaluate_artifact_bound_clean_machine_acceptance(
            self.matrix(), artifact_bound_prehandoff=prehandoff
        )
        self.assertEqual(result.status, "READY_FOR_ADMISSION_REVIEW")
        self.assertEqual(result.violations, ())
        self.assertEqual(result.artifact_sha256, ARTIFACT_SHA)
        self.assertEqual(result.artifact_size_bytes, 123456)
        self.assertEqual(result.release_manifest_sha256, MANIFEST_SHA)
        self.assertEqual(result.prehandoff_receipt_ref, RECEIPT_REF)
        self.assertEqual(result.artifact_bound_prehandoff_sha256, prehandoff.sha256())
        self.assertEqual(result.runtime_credit, 0)
        self.assertEqual(result.physical_host_credit, 0)
        self.assertEqual(result.completion_credit, 0)
        self.assertFalse(result.whole_system_acceptance)

    def test_one_host_row_with_wrong_outer_digest_blocks(self) -> None:
        observations = self.matrix()
        observations[1] = replace(observations[1], artifact_sha256="e" * 64)
        result = evaluate_artifact_bound_clean_machine_acceptance(
            observations, artifact_bound_prehandoff=self.prehandoff()
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("codex_cli:artifact_sha256 mismatch", result.violations)

    def test_one_host_row_with_wrong_artifact_size_blocks(self) -> None:
        observations = self.matrix()
        observations[2] = replace(observations[2], artifact_size_bytes=123457)
        result = evaluate_artifact_bound_clean_machine_acceptance(
            observations, artifact_bound_prehandoff=self.prehandoff()
        )
        self.assertIn("other_agent:artifact_size_bytes mismatch", result.violations)

    def test_manifest_and_receipt_binding_still_fail_closed_through_base_matrix(self) -> None:
        observations = self.matrix()
        observations[0] = replace(
            observations[0],
            observation=replace(
                observations[0].observation,
                release_manifest_sha256="f" * 64,
            ),
        )
        result = evaluate_artifact_bound_clean_machine_acceptance(
            observations, artifact_bound_prehandoff=self.prehandoff()
        )
        self.assertIn("claude_code:release_manifest_sha256 mismatch", result.violations)

    def test_duplicate_case_is_rejected_before_ambiguous_lineage_can_form(self) -> None:
        observations = self.matrix()
        observations.append(self.wrap(self.observation("claude_code", environment_id="dup")))
        with self.assertRaisesRegex(ArtifactBoundCleanMachineError, "duplicate"):
            evaluate_artifact_bound_clean_machine_acceptance(
                observations, artifact_bound_prehandoff=self.prehandoff()
            )


if __name__ == "__main__":
    unittest.main()
