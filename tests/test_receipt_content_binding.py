from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from frankenstein2.artifact_bound_clean_machine import ArtifactBoundAcceptanceObservation
from frankenstein2.clean_machine_acceptance import (
    AcceptanceObservation,
    REAL_HOST_EVIDENCE_SCOPE,
)
from frankenstein2.pre_handoff_release import READY_STATUS
from frankenstein2.receipt_content_binding import (
    ReceiptContentBindingError,
    ReceiptContentBoundAcceptanceObservation,
    bind_prehandoff_receipt_content,
    evaluate_receipt_content_bound_clean_machine_acceptance,
)
from frankenstein2.release_artifact_subject import (
    ArtifactBoundPreHandoffReceipt,
    ReleaseArtifactSubject,
)

MANIFEST_SHA = "a" * 64
ARTIFACT_SHA = "b" * 64
POLICY_SHA = "c" * 64
STATIC_SHA = "d" * 64
RECEIPT_REF = "receipts/F2-WP-1110-g3-prehandoff.json"


class ReceiptContentBindingTests(unittest.TestCase):
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

    def content_bound(self):
        prehandoff = self.prehandoff()
        exact_bytes = prehandoff.canonical_bytes()
        return bind_prehandoff_receipt_content(
            prehandoff,
            prehandoff_receipt_ref=RECEIPT_REF,
            prehandoff_receipt_bytes=exact_bytes,
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

    def artifact_wrap(self, observation: AcceptanceObservation, **overrides):
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

    def content_wrap(self, case_id: str, **overrides):
        bound = self.content_bound()
        subject = bound.receipt_content_subject
        values = {
            "artifact_observation": self.artifact_wrap(self.observation(case_id)),
            "prehandoff_receipt_ref": subject.prehandoff_receipt_ref,
            "prehandoff_receipt_sha256": subject.prehandoff_receipt_sha256,
            "prehandoff_receipt_size_bytes": subject.prehandoff_receipt_size_bytes,
            "receipt_content_subject_sha256": subject.sha256(),
        }
        values.update(overrides)
        return ReceiptContentBoundAcceptanceObservation(**values)

    def matrix(self):
        return [
            self.content_wrap("claude_code"),
            self.content_wrap("codex_cli"),
            self.content_wrap("other_agent"),
            self.content_wrap("no_vps_baseline"),
            self.content_wrap("vps_bridge"),
        ]

    def test_exact_canonical_receipt_bytes_are_bound_and_zero_credit(self) -> None:
        prehandoff = self.prehandoff()
        exact_bytes = prehandoff.canonical_bytes()
        bound = bind_prehandoff_receipt_content(
            prehandoff,
            prehandoff_receipt_ref=RECEIPT_REF,
            prehandoff_receipt_bytes=exact_bytes,
        )
        self.assertEqual(
            bound.prehandoff_receipt_sha256,
            hashlib.sha256(exact_bytes).hexdigest(),
        )
        self.assertEqual(bound.prehandoff_receipt_size_bytes, len(exact_bytes))
        self.assertEqual(bound.status, READY_STATUS)
        self.assertEqual(bound.runtime_credit, 0)
        self.assertEqual(bound.physical_host_credit, 0)
        self.assertEqual(bound.effect_credit, 0)
        self.assertEqual(bound.completion_credit, 0)
        self.assertFalse(bound.whole_system_acceptance)

    def test_same_ref_with_different_receipt_bytes_fails_closed(self) -> None:
        prehandoff = self.prehandoff()
        mutated = prehandoff.canonical_bytes() + b" "
        with self.assertRaisesRegex(
            ReceiptContentBindingError,
            "differ from canonical artifact-bound receipt",
        ):
            bind_prehandoff_receipt_content(
                prehandoff,
                prehandoff_receipt_ref=RECEIPT_REF,
                prehandoff_receipt_bytes=mutated,
            )

    def test_different_textual_ref_fails_before_content_admission(self) -> None:
        prehandoff = self.prehandoff()
        with self.assertRaisesRegex(ReceiptContentBindingError, "differs"):
            bind_prehandoff_receipt_content(
                prehandoff,
                prehandoff_receipt_ref="receipts/replaced.json",
                prehandoff_receipt_bytes=prehandoff.canonical_bytes(),
            )

    def test_exact_receipt_content_bound_matrix_is_ready_but_zero_credit(self) -> None:
        bound = self.content_bound()
        result = evaluate_receipt_content_bound_clean_machine_acceptance(
            self.matrix(),
            content_bound_prehandoff=bound,
        )
        self.assertEqual(result.status, "READY_FOR_ADMISSION_REVIEW")
        self.assertEqual(result.violations, ())
        self.assertEqual(
            result.prehandoff_receipt_sha256,
            bound.prehandoff_receipt_sha256,
        )
        self.assertEqual(
            result.prehandoff_receipt_size_bytes,
            bound.prehandoff_receipt_size_bytes,
        )
        self.assertEqual(
            result.receipt_content_subject_sha256,
            bound.receipt_content_subject.sha256(),
        )
        self.assertEqual(result.runtime_credit, 0)
        self.assertEqual(result.physical_host_credit, 0)
        self.assertEqual(result.completion_credit, 0)
        self.assertFalse(result.whole_system_acceptance)

    def test_one_row_with_same_ref_but_wrong_receipt_digest_blocks(self) -> None:
        observations = self.matrix()
        observations[1] = replace(
            observations[1],
            prehandoff_receipt_sha256="e" * 64,
        )
        result = evaluate_receipt_content_bound_clean_machine_acceptance(
            observations,
            content_bound_prehandoff=self.content_bound(),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn(
            "codex_cli:prehandoff_receipt_sha256 mismatch",
            result.violations,
        )

    def test_one_row_with_wrong_receipt_size_blocks(self) -> None:
        observations = self.matrix()
        observations[2] = replace(
            observations[2],
            prehandoff_receipt_size_bytes=(
                observations[2].prehandoff_receipt_size_bytes + 1
            ),
        )
        result = evaluate_receipt_content_bound_clean_machine_acceptance(
            observations,
            content_bound_prehandoff=self.content_bound(),
        )
        self.assertIn(
            "other_agent:prehandoff_receipt_size_bytes mismatch",
            result.violations,
        )

    def test_one_row_with_wrong_receipt_subject_digest_blocks(self) -> None:
        observations = self.matrix()
        observations[0] = replace(
            observations[0],
            receipt_content_subject_sha256="f" * 64,
        )
        result = evaluate_receipt_content_bound_clean_machine_acceptance(
            observations,
            content_bound_prehandoff=self.content_bound(),
        )
        self.assertIn(
            "claude_code:receipt_content_subject_sha256 mismatch",
            result.violations,
        )

    def test_generation2_artifact_mismatch_still_propagates(self) -> None:
        observations = self.matrix()
        observations[3] = replace(
            observations[3],
            artifact_observation=replace(
                observations[3].artifact_observation,
                artifact_sha256="9" * 64,
            ),
        )
        result = evaluate_receipt_content_bound_clean_machine_acceptance(
            observations,
            content_bound_prehandoff=self.content_bound(),
        )
        self.assertIn("no_vps_baseline:artifact_sha256 mismatch", result.violations)

    def test_duplicate_case_rejected_before_receipt_lineage_can_ambiguate(self) -> None:
        observations = self.matrix()
        observations.append(self.content_wrap("claude_code"))
        with self.assertRaisesRegex(ReceiptContentBindingError, "duplicate"):
            evaluate_receipt_content_bound_clean_machine_acceptance(
                observations,
                content_bound_prehandoff=self.content_bound(),
            )


if __name__ == "__main__":
    unittest.main()
