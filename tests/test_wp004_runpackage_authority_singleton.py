from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _json(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _load_verifier():
    path = ROOT / "runpackages" / "verify_run_package.py"
    spec = importlib.util.spec_from_file_location("wp004_runpackage_verifier", path)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load canonical run-package verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WP004RunPackageAuthoritySingletonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = _load_verifier()
        cls.contract = (ROOT / "telemetry" / "RUN_PACKAGE_CONTRACT.md").read_text(encoding="utf-8")
        cls.readme = (ROOT / "runpackages" / "README.md").read_text(encoding="utf-8")
        cls.manifest_schema = _json("schemas/run_package_manifest.schema.json")
        cls.artifact_schema = _json("schemas/run_artifact_index.schema.json")
        cls.closed_schema = _json("schemas/run_closed_receipt.schema.json")
        cls.g2_reconciliation = _json(
            "workpackages/reconciliations/F2-WP-004/"
            "2-F2-WP-004-G2-VERIFIER-HARDENING-GPT56SOL-20260828T2142P0700.json"
        )

    def test_retired_single_manifest_authority_is_absent_and_explicitly_retired(self) -> None:
        retired = ROOT / "runpackages" / "RUN_PACKAGE_SCHEMA_V1.json"
        self.assertFalse(retired.exists(), "retired single-manifest authority unexpectedly exists")
        self.assertEqual(
            self.g2_reconciliation.get("retired_competing_authority"),
            "runpackages/RUN_PACKAGE_SCHEMA_V1.json",
        )
        self.assertIn("runpackages/RUN_PACKAGE_SCHEMA_V1.json", self.contract)
        self.assertIn("retired historical", self.contract)
        self.assertIn("MUST NOT be recreated", self.contract)
        self.assertIn("FRANKENSTEIN2_IMMUTABLE_RUN_PACKAGE/v1", self.contract)
        self.assertIn("historical/superseded", self.readme)

    def test_current_authority_surfaces_agree_with_accepted_g2_reconciliation(self) -> None:
        expected = {
            "telemetry/RUN_PACKAGE_CONTRACT.md",
            "schemas/run_package_manifest.schema.json",
            "schemas/run_artifact_index.schema.json",
            "schemas/run_closed_receipt.schema.json",
            "runpackages/verify_run_package.py",
            "tests/test_verify_run_package.py",
            ".github/workflows/runpackage-verifier-ci.yml",
        }
        self.assertEqual(set(self.g2_reconciliation.get("authority", [])), expected)
        for rel in sorted(expected):
            self.assertTrue((ROOT / rel).is_file(), f"accepted authority surface missing: {rel}")

        for rel in (
            "schemas/run_package_manifest.schema.json",
            "schemas/run_artifact_index.schema.json",
            "schemas/run_closed_receipt.schema.json",
            "runpackages/verify_run_package.py",
        ):
            self.assertIn(rel, self.contract)
            self.assertIn(rel, self.readme)

    def test_schema_ids_match_executable_verifier_constants(self) -> None:
        self.assertIsNot(self.manifest_schema.get("deprecated"), True)
        self.assertEqual(
            self.manifest_schema["properties"]["schema"]["const"],
            self.verifier.MANIFEST_SCHEMA,
        )
        self.assertEqual(
            self.artifact_schema["properties"]["schema"]["const"],
            self.verifier.ARTIFACT_SCHEMA,
        )
        self.assertEqual(
            self.closed_schema["properties"]["schema"]["const"],
            self.verifier.CLOSED_SCHEMA,
        )
        self.assertEqual(self.verifier.MANIFEST_SCHEMA, "FRANKENSTEIN2_RUN_PACKAGE_MANIFEST/v1")
        self.assertEqual(self.verifier.ARTIFACT_SCHEMA, "FRANKENSTEIN2_RUN_ARTIFACT_INDEX/v1")
        self.assertEqual(self.verifier.CLOSED_SCHEMA, "FRANKENSTEIN2_RUN_CLOSED_RECEIPT/v1")

    def test_closure_filenames_match_contract_and_readme(self) -> None:
        expected = {
            "MANIFEST_NAME": "manifest.json",
            "ARTIFACTS_NAME": "ARTIFACTS.json",
            "SUMS_NAME": "SHA256SUMS",
            "CLOSED_NAME": "CLOSED.json",
        }
        for attr, filename in expected.items():
            self.assertEqual(getattr(self.verifier, attr), filename)
            self.assertIn(filename, self.contract)
            self.assertIn(filename, self.readme)

    def test_manifest_schema_metadata_declares_current_closure_authority(self) -> None:
        comment = self.manifest_schema.get("$comment", "")
        self.assertIn("Active canonical manifest schema", comment)
        self.assertIn("closure-style F2-WP-004", comment)
        self.assertIn("runpackages/verify_run_package.py", comment)
        self.assertIn("retired single-manifest", comment)


if __name__ == "__main__":
    unittest.main()
