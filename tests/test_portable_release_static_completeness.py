from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from frankenstein2.portable_release_static_completeness import (
    BLOCKED,
    STATIC_COMPLETE,
    evaluate_portable_release_static_completeness,
)
from frankenstein2.release_integrity import build_release_manifest, write_release_manifest

RECEIPT_REF = "external-receipts/test-prehandoff.json"


class PortableReleaseStaticCompletenessTests(unittest.TestCase):
    def _write(self, root: Path, rel: str, value: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def _package(self, root: Path, *, omit_runtime=False, bad_perception=False) -> None:
        route_targets = {
            "PRODUCT_COMPLETION_LAW.md": "law\n",
            "architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md": "contract\n",
            "workpackages/PORTABLE_DELIVERY_PHASE.json": "{}\n",
            "provenance/frankenstein1-portable-installer-audit-20260829.json": "{}\n",
            "AI_START_HERE_DO_NOT_SCAN_REPO/03_VERIFY_INSTALL.md": "verify\n",
            "AI_START_HERE_DO_NOT_SCAN_REPO/CLAUDE_CODE/00_DO_THIS.md": "claude\n",
            "AI_START_HERE_DO_NOT_SCAN_REPO/CODEX_CLI/00_DO_THIS.md": "codex\n",
            "AI_START_HERE_DO_NOT_SCAN_REPO/OTHER_AGENT/00_DO_THIS.md": "other\n",
            "src/frankenstein2/state_migration.py": "PLAN_SCHEMA='FRANKENSTEIN2_STATE_MIGRATION_PLAN/v1'\n",
            "workpackages/receipts/F2-WP-1105_G1_STATE_MIGRATION_MAIN_CI_33253041398.json": "{}\n",
            "workpackages/receipts/F2-WP-1108_G1_CLEAN_MACHINE_MATRIX_MAIN_CI_33253634771.json": "{}\n",
            "src/frankenstein2/host_adapter_abi.py": "# abi\n",
            "architecture/PERCEPTION_FABRIC.md": "# perception\n",
            "architecture/PERCEPTION_FABRIC_HARDENING_20260829.md": "# hardening\n",
            "src/frankenstein2/perception_dashboard_policy.py": "# policy\n",
        }
        for rel, value in route_targets.items():
            self._write(root, rel, value)
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
        self._write(root, "AI_START_HERE_DO_NOT_SCAN_REPO/01_ROUTES.json", json.dumps(routes))
        contract = {
            "schema": "FRANKENSTEIN2_RELEASE_DELIVERY_CONTRACT/v1",
            "baseline_runtime": {
                "implementation": "CPython",
                "minimum_version": "3.12",
                "dependency_class": "PYTHON_STDLIB_BASELINE",
                "evidence_refs": ["workpackages/receipts/F2-WP-1108_G1_CLEAN_MACHINE_MATRIX_MAIN_CI_33253634771.json"],
            },
            "state_migration": {
                "version": "FRANKENSTEIN2_STATE_MIGRATION_PLAN/v1",
                "source_ref": "src/frankenstein2/state_migration.py",
                "acceptance_ref": "workpackages/receipts/F2-WP-1105_G1_STATE_MIGRATION_MAIN_CI_33253041398.json",
            },
            "supported_hosts": {
                "route_map_ref": "AI_START_HERE_DO_NOT_SCAN_REPO/01_ROUTES.json",
                "required_route_keys": ["claude_code", "codex_cli", "other_agent"],
            },
            "optional_feature_capabilities": {
                "host_abi_ref": "src/frankenstein2/host_adapter_abi.py",
                "perception_policy_refs": [
                    "architecture/PERCEPTION_FABRIC.md",
                    "architecture/PERCEPTION_FABRIC_HARDENING_20260829.md",
                    "src/frankenstein2/perception_dashboard_policy.py",
                ],
            },
            "perception_defaults": {
                "raw_frame_persistence": False,
                "vlm_escalation": "EXPLICIT_PERMISSION_REQUIRED",
            },
            "verifier_self_test": {
                "kind": "AGENT_PROCEDURE",
                "entry_ref": "AI_START_HERE_DO_NOT_SCAN_REPO/03_VERIFY_INSTALL.md",
            },
        }
        if omit_runtime:
            contract.pop("baseline_runtime")
        if bad_perception:
            contract["perception_defaults"]["raw_frame_persistence"] = True
        self._write(root, "AI_START_HERE_DO_NOT_SCAN_REPO/02_RELEASE_CONTRACT.json", json.dumps(contract))
        manifest = build_release_manifest(
            root,
            release_id="f2-test",
            source_commit="a" * 40,
            source_tree="b" * 40,
            build_id="test",
            prehandoff_receipt_refs=(RECEIPT_REF,),
        )
        write_release_manifest(root, manifest)

    def test_complete_contract_passes_static_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root)
            result = evaluate_portable_release_static_completeness(root, prehandoff_receipt_ref=RECEIPT_REF)
            self.assertEqual(result.status, STATIC_COMPLETE)
            self.assertEqual(result.baseline_python_minimum, "3.12")
            self.assertEqual(result.state_migration_version, "FRANKENSTEIN2_STATE_MIGRATION_PLAN/v1")
            self.assertEqual(result.runtime_credit, 0)
            self.assertEqual(result.physical_host_credit, 0)
            self.assertEqual(result.completion_credit, 0)
            self.assertFalse(result.whole_system_acceptance)

    def test_old_static_ready_shape_without_runtime_metadata_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root, omit_runtime=True)
            result = evaluate_portable_release_static_completeness(root, prehandoff_receipt_ref=RECEIPT_REF)
            self.assertEqual(result.status, BLOCKED)
            self.assertIn("baseline_runtime:missing_or_invalid", result.violations)

    def test_perception_default_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._package(root, bad_perception=True)
            result = evaluate_portable_release_static_completeness(root, prehandoff_receipt_ref=RECEIPT_REF)
            self.assertEqual(result.status, BLOCKED)
            self.assertIn("perception_defaults:raw_frame_persistence_must_be_false", result.violations)


if __name__ == "__main__":
    unittest.main()
