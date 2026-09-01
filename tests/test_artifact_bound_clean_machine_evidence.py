from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest

from frankenstein2.artifact_bound_clean_machine import ArtifactBoundAcceptanceObservation
from frankenstein2.artifact_bound_clean_machine_evidence import (
    ArtifactBoundEvidenceIngestError,
    evaluate_artifact_bound_clean_machine_evidence,
)
from frankenstein2.clean_machine_acceptance import AcceptanceObservation, REAL_HOST_EVIDENCE_SCOPE
from frankenstein2.pre_handoff_release import READY_STATUS
from frankenstein2.release_artifact_subject import (
    ArtifactBoundPreHandoffReceipt,
    ReleaseArtifactSubject,
)

MANIFEST_SHA = "a" * 64
POLICY_SHA = "c" * 64
STATIC_SHA = "d" * 64
RECEIPT_REF = "release-receipts/frankenstein-2.0-prehandoff.json"
ARTIFACT_BYTES = b"exact-release-zip-for-artifact-bound-evidence-ingest"
ARTIFACT_SHA = hashlib.sha256(ARTIFACT_BYTES).hexdigest()


class ArtifactBoundCleanMachineEvidenceTests(unittest.TestCase):
    def prehandoff(self) -> ArtifactBoundPreHandoffReceipt:
        subject = ReleaseArtifactSubject(
            artifact_filename="frankenstein-2.0.zip",
            artifact_sha256=ARTIFACT_SHA,
            artifact_size_bytes=len(ARTIFACT_BYTES),
            release_manifest_sha256=MANIFEST_SHA,
            source_commit="1" * 40,
            source_tree="2" * 40,
            release_id="f2-evidence-ingest-test",
            build_id="build-evidence-ingest-test",
            archive_policy_id="f2-release-zip-stored-posix-v1",
            archive_policy_sha256=POLICY_SHA,
            member_count=3,
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
            "environment_id": f"real-host-{case_id}",
            "release_manifest_sha256": MANIFEST_SHA,
            "prehandoff_receipt_ref": RECEIPT_REF,
            "route_result": "ACCEPTED",
            "evidence_scope": REAL_HOST_EVIDENCE_SCOPE,
            "observed_at": "2026-09-01T00:00:00Z",
            "evidence_refs": (f"controller-receipt:{case_id}",),
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

    def wrapped(self, observation: AcceptanceObservation) -> ArtifactBoundAcceptanceObservation:
        subject = self.prehandoff().subject
        return ArtifactBoundAcceptanceObservation(
            observation=observation,
            artifact_filename=subject.artifact_filename,
            artifact_sha256=subject.artifact_sha256,
            artifact_size_bytes=subject.artifact_size_bytes,
            artifact_subject_sha256=subject.sha256(),
        )

    def observation_records(self):
        return [
            self.wrapped(self.observation("claude_code")).as_dict(),
            self.wrapped(self.observation("codex_cli")).as_dict(),
            self.wrapped(self.observation("other_agent")).as_dict(),
            self.wrapped(self.observation("no_vps_baseline")).as_dict(),
            self.wrapped(self.observation("vps_bridge")).as_dict(),
        ]

    def evaluate(self, artifact_path: Path, records=None):
        return evaluate_artifact_bound_clean_machine_evidence(
            artifact_path=artifact_path,
            prehandoff_record=self.prehandoff().as_dict(),
            observation_records=self.observation_records() if records is None else records,
        )

    def test_exact_unopened_artifact_and_real_host_records_reach_review_without_credit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "frankenstein-2.0.zip"
            artifact.write_bytes(ARTIFACT_BYTES)
            result = self.evaluate(artifact)
        self.assertEqual(result.status, "READY_FOR_ADMISSION_REVIEW")
        self.assertEqual(result.violations, ())
        self.assertEqual(result.artifact_sha256, ARTIFACT_SHA)
        self.assertEqual(result.runtime_credit, 0)
        self.assertEqual(result.physical_host_credit, 0)
        self.assertEqual(result.completion_credit, 0)
        self.assertFalse(result.whole_system_acceptance)

    def test_tampered_unopened_artifact_is_rejected_before_observation_admission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "frankenstein-2.0.zip"
            artifact.write_bytes(ARTIFACT_BYTES + b"tamper")
            with self.assertRaisesRegex(ArtifactBoundEvidenceIngestError, "artifact size"):
                self.evaluate(artifact)

    def test_observation_cannot_hide_wrong_outer_artifact_digest(self) -> None:
        records = self.observation_records()
        records[1] = dict(records[1])
        records[1]["artifact_sha256"] = "e" * 64
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "frankenstein-2.0.zip"
            artifact.write_bytes(ARTIFACT_BYTES)
            result = self.evaluate(artifact, records)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("codex_cli:artifact_sha256 mismatch", result.violations)

    def test_unknown_observation_field_fails_closed(self) -> None:
        records = self.observation_records()
        records[0] = dict(records[0])
        nested = dict(records[0]["observation"])
        nested["invented_runtime_credit"] = 1
        records[0]["observation"] = nested
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "frankenstein-2.0.zip"
            artifact.write_bytes(ARTIFACT_BYTES)
            with self.assertRaisesRegex(ArtifactBoundEvidenceIngestError, "keys mismatch"):
                self.evaluate(artifact, records)

    def test_wrong_artifact_filename_fails_before_matrix_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "renamed.zip"
            artifact.write_bytes(ARTIFACT_BYTES)
            with self.assertRaisesRegex(ArtifactBoundEvidenceIngestError, "filename"):
                self.evaluate(artifact)


if __name__ == "__main__":
    unittest.main()
