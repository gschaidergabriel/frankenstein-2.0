from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from frankenstein2.pre_handoff_release import BLOCKED_STATUS, READY_STATUS
from frankenstein2.release_archive import (
    ReleaseArchiveError,
    ReleaseArchivePolicy,
    build_release_archive,
    write_release_archive,
)
from frankenstein2.release_artifact_subject import (
    ARTIFACT_BOUND_SCOPE,
    bind_release_artifact_subject,
)

RECEIPT_REF = "receipts/F2-WP-1110-g2-prehandoff.json"
EPOCH = 1_700_000_000


class ReleaseArtifactSubjectTests(unittest.TestCase):
    def _write(self, root: Path, rel: str, value: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def _payload(self, root: Path) -> None:
        self._write(root, "PRODUCT_COMPLETION_LAW.md", "completion law\n")
        self._write(
            root,
            "architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md",
            "distribution contract\n",
        )
        self._write(root, "workpackages/PORTABLE_DELIVERY_PHASE.json", "{}\n")
        self._write(
            root,
            "provenance/frankenstein1-portable-installer-audit-20260829.json",
            "{}\n",
        )
        self._write(root, "AI_START_HERE_DO_NOT_SCAN_REPO/03_VERIFY_INSTALL.md", "verify\n")
        self._write(
            root,
            "AI_START_HERE_DO_NOT_SCAN_REPO/CLAUDE_CODE/00_DO_THIS.md",
            "claude route\n",
        )
        self._write(
            root,
            "AI_START_HERE_DO_NOT_SCAN_REPO/CODEX_CLI/00_DO_THIS.md",
            "codex route\n",
        )
        self._write(
            root,
            "AI_START_HERE_DO_NOT_SCAN_REPO/OTHER_AGENT/00_DO_THIS.md",
            "generic route\n",
        )
        routes = {
            "schema": "FRANKENSTEIN2_AI_INSTALL_ROUTE/v1",
            "root_rule": "ROOT = parent(directory_containing_this_file)",
            "product_completion_law": "../PRODUCT_COMPLETION_LAW.md",
            "distribution_contract": "../architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md",
            "portable_delivery_phase": "../workpackages/PORTABLE_DELIVERY_PHASE.json",
            "donor_installer_audit": "../provenance/frankenstein1-portable-installer-audit-20260829.json",
            "verify_install": "03_VERIFY_INSTALL.md",
            "claude_code": "CLAUDE_CODE/00_DO_THIS.md",
            "codex_cli": "CODEX_CLI/00_DO_THIS.md",
            "other_agent": "OTHER_AGENT/00_DO_THIS.md",
            "state_rule": "ONE_CANONICAL_DURABLE_LOCAL_F2_STATE_OUTSIDE_DISPOSABLE_HOST_CACHE",
            "vps_rule": "OPTIONAL_EXTENSION_NOT_BASELINE_PRODUCT_LOCATION",
            "production_ready_condition": "PORTABLE_ONE_HANDOFF_RELEASE_GATE_ACCEPTED",
        }
        self._write(
            root,
            "AI_START_HERE_DO_NOT_SCAN_REPO/01_ROUTES.json",
            json.dumps(routes, sort_keys=True, indent=2) + "\n",
        )

    def _policy(self) -> ReleaseArchivePolicy:
        return ReleaseArchivePolicy(
            policy_id="f2-release-zip-stored-posix-v1",
            source_date_epoch=EPOCH,
        )

    def _build(self, root: Path, *, receipt_ref: str = RECEIPT_REF):
        self._payload(root)
        return build_release_archive(
            root,
            release_id="frankenstein-2.0-artifact-test",
            source_commit="c" * 40,
            source_tree="t" * 40,
            build_id="wp1110-g2-artifact-test",
            policy=self._policy(),
            prehandoff_receipt_refs=(receipt_ref,),
        )

    def test_exact_unopened_zip_is_bound_before_static_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            payload = tmp_root / "payload"
            payload.mkdir()
            build = self._build(payload)
            artifact = write_release_archive(tmp_root / "frankenstein-2.0.zip", build)

            first = bind_release_artifact_subject(
                artifact,
                policy=self._policy(),
                prehandoff_receipt_ref=RECEIPT_REF,
                expected_archive_receipt=build.receipt,
            )
            second = bind_release_artifact_subject(
                artifact,
                policy=self._policy(),
                prehandoff_receipt_ref=RECEIPT_REF,
                expected_archive_receipt=build.receipt,
            )

            self.assertEqual(first.status, READY_STATUS)
            self.assertEqual(first.artifact_filename, "frankenstein-2.0.zip")
            self.assertEqual(first.artifact_sha256, build.receipt.archive_sha256)
            self.assertEqual(first.artifact_size_bytes, len(build.archive_bytes))
            self.assertEqual(first.release_manifest_sha256, build.receipt.manifest_sha256)
            self.assertEqual(first.prehandoff_receipt_ref, RECEIPT_REF)
            self.assertEqual(first.evidence_scope, ARTIFACT_BOUND_SCOPE)
            self.assertEqual(first.runtime_credit, 0)
            self.assertEqual(first.physical_host_credit, 0)
            self.assertEqual(first.effect_credit, 0)
            self.assertEqual(first.completion_credit, 0)
            self.assertFalse(first.whole_system_acceptance)
            self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
            self.assertEqual(first.sha256(), second.sha256())

    def test_wrong_expected_outer_digest_fails_before_static_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            payload = tmp_root / "payload"
            payload.mkdir()
            build = self._build(payload)
            artifact = write_release_archive(tmp_root / "frankenstein-2.0.zip", build)
            wrong = replace(build.receipt, archive_sha256="0" * 64)

            with self.assertRaisesRegex(ReleaseArchiveError, "receipt identity mismatch"):
                bind_release_artifact_subject(
                    artifact,
                    policy=self._policy(),
                    prehandoff_receipt_ref=RECEIPT_REF,
                    expected_archive_receipt=wrong,
                )

    def test_unbound_prehandoff_reference_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            payload = tmp_root / "payload"
            payload.mkdir()
            build = self._build(payload, receipt_ref="receipts/other.json")
            artifact = write_release_archive(tmp_root / "frankenstein-2.0.zip", build)

            result = bind_release_artifact_subject(
                artifact,
                policy=self._policy(),
                prehandoff_receipt_ref=RECEIPT_REF,
                expected_archive_receipt=build.receipt,
            )
            self.assertEqual(result.status, BLOCKED_STATUS)
            self.assertIn(
                "prehandoff_receipt_ref:not_bound_in_release_manifest",
                result.static_violations,
            )

    def test_mutated_outer_archive_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            payload = tmp_root / "payload"
            payload.mkdir()
            build = self._build(payload)
            artifact = write_release_archive(tmp_root / "frankenstein-2.0.zip", build)
            artifact.write_bytes(build.archive_bytes + b"trailing-tamper")

            with self.assertRaises(ReleaseArchiveError):
                bind_release_artifact_subject(
                    artifact,
                    policy=self._policy(),
                    prehandoff_receipt_ref=RECEIPT_REF,
                    expected_archive_receipt=build.receipt,
                )


if __name__ == "__main__":
    unittest.main()
