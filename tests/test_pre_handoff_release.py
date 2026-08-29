from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from frankenstein2.pre_handoff_release import (
    BLOCKED_STATUS,
    EVIDENCE_SCOPE,
    READY_STATUS,
    evaluate_pre_handoff_release,
)
from frankenstein2.release_integrity import (
    ReleaseIntegrityError,
    build_release_manifest,
    write_release_manifest,
)


RECEIPT_REF = "receipts/F2-WP-1110-prehandoff.json"


class PreHandoffReleaseTests(unittest.TestCase):
    def _write(self, root: Path, rel: str, value: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def _package(
        self,
        root: Path,
        *,
        bound_ref: str = RECEIPT_REF,
        missing_route_target: bool = False,
        escape_route: bool = False,
        production_ready_condition: str = "PORTABLE_ONE_HANDOFF_RELEASE_GATE_ACCEPTED",
    ):
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
        if not missing_route_target:
            self._write(
                root,
                "AI_START_HERE_DO_NOT_SCAN_REPO/OTHER_AGENT/00_DO_THIS.md",
                "generic route\n",
            )

        routes = {
            "schema": "FRANKENSTEIN2_AI_INSTALL_ROUTE/v1",
            "root_rule": "ROOT = parent(directory_containing_this_file)",
            "product_completion_law": "../../../outside.md" if escape_route else "../PRODUCT_COMPLETION_LAW.md",
            "distribution_contract": "../architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md",
            "portable_delivery_phase": "../workpackages/PORTABLE_DELIVERY_PHASE.json",
            "donor_installer_audit": "../provenance/frankenstein1-portable-installer-audit-20260829.json",
            "verify_install": "03_VERIFY_INSTALL.md",
            "claude_code": "CLAUDE_CODE/00_DO_THIS.md",
            "codex_cli": "CODEX_CLI/00_DO_THIS.md",
            "other_agent": "OTHER_AGENT/00_DO_THIS.md",
            "state_rule": "ONE_CANONICAL_DURABLE_LOCAL_F2_STATE_OUTSIDE_DISPOSABLE_HOST_CACHE",
            "vps_rule": "OPTIONAL_EXTENSION_NOT_BASELINE_PRODUCT_LOCATION",
            "production_ready_condition": production_ready_condition,
        }
        self._write(
            root,
            "AI_START_HERE_DO_NOT_SCAN_REPO/01_ROUTES.json",
            json.dumps(routes, indent=2, sort_keys=True) + "\n",
        )

        manifest = build_release_manifest(
            root,
            release_id="f2-test-release",
            source_commit="c" * 40,
            source_tree="t" * 40,
            build_id="build-test",
            prehandoff_receipt_refs=(bound_ref,),
        )
        write_release_manifest(root, manifest)
        return manifest

    def test_ready_receipt_binds_manifest_routes_and_never_grants_runtime_credit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._package(root)
            first = evaluate_pre_handoff_release(root, prehandoff_receipt_ref=RECEIPT_REF)
            second = evaluate_pre_handoff_release(root, prehandoff_receipt_ref=RECEIPT_REF)

            self.assertEqual(first.status, READY_STATUS)
            self.assertEqual(first.violations, ())
            self.assertEqual(first.release_manifest_sha256, manifest.sha256())
            self.assertEqual(first.prehandoff_receipt_ref, RECEIPT_REF)
            self.assertEqual(first.evidence_scope, EVIDENCE_SCOPE)
            self.assertEqual(first.runtime_credit, 0)
            self.assertEqual(first.physical_host_credit, 0)
            self.assertEqual(first.effect_credit, 0)
            self.assertEqual(first.completion_credit, 0)
            self.assertFalse(first.whole_system_acceptance)
            self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
            self.assertEqual(first.sha256(), second.sha256())
            self.assertEqual(len(first.resolved_routes), 8)

    def test_unbound_receipt_reference_blocks_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root, bound_ref="receipts/other.json")
            result = evaluate_pre_handoff_release(root, prehandoff_receipt_ref=RECEIPT_REF)
            self.assertEqual(result.status, BLOCKED_STATUS)
            self.assertIn(
                "prehandoff_receipt_ref:not_bound_in_release_manifest",
                result.violations,
            )

    def test_missing_declared_route_target_blocks_without_faking_manifest_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root, missing_route_target=True)
            result = evaluate_pre_handoff_release(root, prehandoff_receipt_ref=RECEIPT_REF)
            self.assertEqual(result.status, BLOCKED_STATUS)
            self.assertIn("routes:other_agent:missing", result.violations)

    def test_route_escape_and_stale_completion_condition_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(
                root,
                escape_route=True,
                production_ready_condition="SOURCE_ONLY_IS_ENOUGH",
            )
            result = evaluate_pre_handoff_release(root, prehandoff_receipt_ref=RECEIPT_REF)
            self.assertEqual(result.status, BLOCKED_STATUS)
            self.assertIn("routes:product_completion_law:missing", result.violations)
            self.assertIn("routes:production_ready_condition_mismatch", result.violations)

    def test_payload_tamper_remains_release_integrity_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root)
            self._write(root, "PRODUCT_COMPLETION_LAW.md", "tampered\n")
            with self.assertRaises(ReleaseIntegrityError):
                evaluate_pre_handoff_release(root, prehandoff_receipt_ref=RECEIPT_REF)


if __name__ == "__main__":
    unittest.main()
