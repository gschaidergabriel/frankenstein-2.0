#!/usr/bin/env python3
"""Fail-closed authority-drift regression for F2-WP-004 generation 3."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "telemetry" / "RUN_PACKAGE_CONTRACT.md"
README = ROOT / "runpackages" / "README.md"
VERIFIER = ROOT / "runpackages" / "verify_run_package.py"
MISSING_COMPETING_SCHEMA = ROOT / "runpackages" / "RUN_PACKAGE_SCHEMA_V1.json"
MANIFEST_SCHEMA_PATH = ROOT / "schemas" / "run_package_manifest.schema.json"
ARTIFACT_SCHEMA_PATH = ROOT / "schemas" / "run_artifact_index.schema.json"
CLOSED_SCHEMA_PATH = ROOT / "schemas" / "run_closed_receipt.schema.json"

EXPECTED = {
    "manifest": "FRANKENSTEIN2_RUN_PACKAGE_MANIFEST/v1",
    "artifact": "FRANKENSTEIN2_RUN_ARTIFACT_INDEX/v1",
    "closed": "FRANKENSTEIN2_RUN_CLOSED_RECEIPT/v1",
}
CLOSURE_FILES = ("manifest.json", "ARTIFACTS.json", "SHA256SUMS", "CLOSED.json")


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path} did not decode to an object")
    return value


def load_verifier_module():
    spec = importlib.util.spec_from_file_location("wp004_verifier_authority_probe", VERIFIER)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load run-package verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WP004AuthoritySingletonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = CONTRACT.read_text(encoding="utf-8")
        self.readme = README.read_text(encoding="utf-8")
        self.manifest_schema = load_json(MANIFEST_SCHEMA_PATH)
        self.artifact_schema = load_json(ARTIFACT_SCHEMA_PATH)
        self.closed_schema = load_json(CLOSED_SCHEMA_PATH)
        self.verifier = load_verifier_module()

    def test_missing_single_manifest_authority_is_not_materialized(self) -> None:
        self.assertFalse(
            MISSING_COMPETING_SCHEMA.exists(),
            "a second run-package authority appeared at the historically stale path",
        )
        stale_positive_claim = (
            "Active canonical manifest ABI is runpackages/RUN_PACKAGE_SCHEMA_V1.json"
        )
        self.assertNotIn(stale_positive_claim, self.contract)
        self.assertNotIn(stale_positive_claim, self.readme)
        self.assertNotIn(stale_positive_claim, json.dumps(self.manifest_schema, sort_keys=True))
        self.assertIn("is **not** part of the current ABI", self.contract)
        self.assertIn("is not a current authority", self.readme)

    def test_executable_verifier_and_schema_ids_are_identical(self) -> None:
        self.assertEqual(self.verifier.MANIFEST_SCHEMA, EXPECTED["manifest"])
        self.assertEqual(self.verifier.ARTIFACT_SCHEMA, EXPECTED["artifact"])
        self.assertEqual(self.verifier.CLOSED_SCHEMA, EXPECTED["closed"])
        self.assertEqual(
            self.manifest_schema["properties"]["schema"]["const"], EXPECTED["manifest"]
        )
        self.assertEqual(
            self.artifact_schema["properties"]["schema"]["const"], EXPECTED["artifact"]
        )
        self.assertEqual(
            self.closed_schema["properties"]["schema"]["const"], EXPECTED["closed"]
        )

    def test_manifest_schema_is_current_closure_schema_not_retired_alias(self) -> None:
        self.assertNotEqual(self.manifest_schema.get("deprecated"), True)
        self.assertNotIn("RETIRED", self.manifest_schema.get("title", "").upper())
        self.assertEqual(
            self.manifest_schema["properties"]["artifacts_index"]["const"],
            "ARTIFACTS.json",
        )
        self.assertEqual(
            self.manifest_schema["properties"]["closure_receipt"]["const"],
            "CLOSED.json",
        )
        self.assertNotIn(
            "RUN_PACKAGE_SCHEMA_V1.json", self.manifest_schema.get("$comment", "")
        )

    def test_contract_and_readme_describe_same_closure_shape(self) -> None:
        for filename in CLOSURE_FILES:
            self.assertIn(filename, self.contract)
            self.assertIn(filename, self.readme)
        for schema_id in EXPECTED.values():
            self.assertIn(schema_id, self.contract)
            self.assertIn(schema_id, self.readme)
        self.assertIn("fail-closed executable authority", self.readme)
        self.assertIn("fail-closed executable authority", self.contract)

    def test_single_manifest_design_is_explicitly_historical(self) -> None:
        historical_id = "FRANKENSTEIN2_IMMUTABLE_RUN_PACKAGE/v1"
        self.assertIn(historical_id, self.contract)
        self.assertIn(historical_id, self.readme)
        self.assertIn("historical", self.contract.lower())
        self.assertIn("historical", self.readme.lower())
        self.assertNotEqual(self.verifier.MANIFEST_SCHEMA, historical_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
