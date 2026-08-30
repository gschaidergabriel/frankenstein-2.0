from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from frankenstein2.final_release_materialization import (
    FINAL_MATERIALIZATION_SCOPE,
    FinalReleaseMaterializationError,
    materialize_final_release,
)
from frankenstein2.pre_handoff_release import READY_STATUS
from frankenstein2.receipt_content_binding import bind_prehandoff_receipt_content
from frankenstein2.release_archive import ReleaseArchivePolicy
from frankenstein2.release_artifact_subject import bind_release_artifact_subject

EPOCH = 1_700_000_000
RECEIPT_REF = "receipts/F2-WP-1110-g4-prehandoff.json"


class FinalReleaseMaterializationTests(unittest.TestCase):
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
        self._write(
            root,
            "AI_START_HERE_DO_NOT_SCAN_REPO/03_VERIFY_INSTALL.md",
            "verify\n",
        )
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

    def _run(self, package: Path, output: Path, **overrides):
        values = {
            "release_id": "frankenstein-2.0-final-materialization-test",
            "source_commit": "c" * 40,
            "source_tree": "t" * 40,
            "build_id": "wp1110-g4-final-materialization-test",
            "policy": self._policy(),
            "prehandoff_receipt_ref": RECEIPT_REF,
        }
        values.update(overrides)
        return materialize_final_release(package, output, **values)

    def test_exact_zip_and_exact_external_receipt_are_materialized_and_rebound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "payload"
            output = root / "handoff"
            package.mkdir()
            self._payload(package)

            result = self._run(package, output)

            artifact = output / "frankenstein-2.0.zip"
            receipt = output / RECEIPT_REF
            self.assertTrue(artifact.is_file())
            self.assertTrue(receipt.is_file())
            self.assertEqual(
                hashlib.sha256(artifact.read_bytes()).hexdigest(),
                result.artifact_sha256,
            )
            self.assertEqual(
                hashlib.sha256(receipt.read_bytes()).hexdigest(),
                result.prehandoff_receipt_sha256,
            )
            self.assertEqual(len(receipt.read_bytes()), result.prehandoff_receipt_size_bytes)
            self.assertEqual(result.status, READY_STATUS)
            self.assertEqual(result.evidence_scope, FINAL_MATERIALIZATION_SCOPE)
            self.assertEqual(result.runtime_credit, 0)
            self.assertEqual(result.physical_host_credit, 0)
            self.assertEqual(result.clean_machine_credit, 0)
            self.assertEqual(result.effect_credit, 0)
            self.assertEqual(result.completion_credit, 0)
            self.assertFalse(result.whole_system_acceptance)

            artifact_bound = bind_release_artifact_subject(
                artifact,
                policy=self._policy(),
                prehandoff_receipt_ref=RECEIPT_REF,
            )
            content_bound = bind_prehandoff_receipt_content(
                artifact_bound,
                prehandoff_receipt_ref=RECEIPT_REF,
                prehandoff_receipt_bytes=receipt.read_bytes(),
            )
            self.assertEqual(
                artifact_bound.sha256(),
                result.artifact_bound_prehandoff_sha256,
            )
            self.assertEqual(
                artifact_bound.subject.sha256(),
                result.artifact_subject_sha256,
            )
            self.assertEqual(
                content_bound.receipt_content_subject.sha256(),
                result.receipt_content_subject_sha256,
            )
            self.assertEqual(
                content_bound.sha256(),
                result.content_bound_prehandoff_sha256,
            )

    def test_same_inputs_are_byte_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "payload"
            output = root / "handoff"
            package.mkdir()
            self._payload(package)

            first = self._run(package, output)
            artifact_before = (output / "frankenstein-2.0.zip").read_bytes()
            receipt_before = (output / RECEIPT_REF).read_bytes()

            second = self._run(package, output)

            self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
            self.assertEqual(artifact_before, (output / "frankenstein-2.0.zip").read_bytes())
            self.assertEqual(receipt_before, (output / RECEIPT_REF).read_bytes())

    def test_same_receipt_ref_with_mutated_existing_bytes_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "payload"
            output = root / "handoff"
            package.mkdir()
            self._payload(package)
            self._run(package, output)

            receipt = output / RECEIPT_REF
            receipt.write_bytes(receipt.read_bytes() + b"tamper")

            with self.assertRaisesRegex(
                FinalReleaseMaterializationError,
                "pre-handoff receipt already exists with different bytes",
            ):
                self._run(package, output)

    def test_mutated_existing_zip_fails_closed_instead_of_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "payload"
            output = root / "handoff"
            package.mkdir()
            self._payload(package)
            self._run(package, output)

            artifact = output / "frankenstein-2.0.zip"
            artifact.write_bytes(artifact.read_bytes() + b"tamper")

            with self.assertRaisesRegex(
                FinalReleaseMaterializationError,
                "release artifact already exists with different bytes",
            ):
                self._run(package, output)

    def test_output_inside_package_is_rejected_before_self_inclusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "payload"
            package.mkdir()
            self._payload(package)

            with self.assertRaisesRegex(
                FinalReleaseMaterializationError,
                "outside package_root",
            ):
                self._run(package, package / "dist")

    def test_unsafe_receipt_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "payload"
            output = root / "handoff"
            package.mkdir()
            self._payload(package)

            with self.assertRaisesRegex(
                FinalReleaseMaterializationError,
                "safe relative path",
            ):
                self._run(
                    package,
                    output,
                    prehandoff_receipt_ref="../receipt.json",
                )

    def test_non_basename_artifact_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "payload"
            output = root / "handoff"
            package.mkdir()
            self._payload(package)

            with self.assertRaisesRegex(
                FinalReleaseMaterializationError,
                "basename",
            ):
                self._run(
                    package,
                    output,
                    artifact_filename="nested/frankenstein-2.0.zip",
                )

    def test_static_gate_block_prevents_external_receipt_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "payload"
            output = root / "handoff"
            package.mkdir()
            self._payload(package)
            (package / "AI_START_HERE_DO_NOT_SCAN_REPO/CODEX_CLI/00_DO_THIS.md").unlink()

            with self.assertRaisesRegex(
                FinalReleaseMaterializationError,
                "static pre-handoff gate blocked",
            ):
                self._run(package, output)

            self.assertTrue((output / "frankenstein-2.0.zip").is_file())
            self.assertFalse((output / RECEIPT_REF).exists())


if __name__ == "__main__":
    unittest.main()
