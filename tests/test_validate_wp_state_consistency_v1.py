#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.validate_wp_state_consistency_v1 import ValidationError, validate


WP = "F2-WP-002"


class StateConsistencyTests(unittest.TestCase):
    def test_current_active_generation_passes(self):
        lines = validate(ROOT, WP)
        self.assertTrue(lines[0].startswith("PASS workpackage=F2-WP-002"))
        self.assertIn("runtime_credit=0", lines)

    def test_filename_workpackage_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "workpackages" / "active").mkdir(parents=True)
            (root / "workpackages" / "claims").mkdir(parents=True)
            (root / "workpackages").joinpath("STATE.json").write_text(
                json.dumps({"workpackages": {WP: {"status": "IN_PROGRESS", "evidence": []}}}),
                encoding="utf-8",
            )
            (root / "workpackages" / "active" / f"{WP}.json").write_text(
                json.dumps({
                    "workpackage_id": "F2-WP-999",
                    "generation": 1,
                    "claim_id": "F2-WP-002-G1-x",
                    "worker_id": "x",
                    "base_commit": "a",
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValidationError, "filename/workpackage_id mismatch"):
                validate(root, WP)

    def test_generation_claim_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "workpackages" / "active").mkdir(parents=True)
            (root / "workpackages" / "claims").mkdir(parents=True)
            (root / "workpackages").joinpath("STATE.json").write_text(
                json.dumps({"workpackages": {WP: {"status": "IN_PROGRESS", "evidence": []}}}),
                encoding="utf-8",
            )
            active = {
                "workpackage_id": WP,
                "generation": 2,
                "claim_id": "F2-WP-002-G2-x",
                "worker_id": "x",
                "base_commit": "a",
            }
            claim = dict(active, generation=1, claim_id="F2-WP-002-G1-x")
            (root / "workpackages" / "active" / f"{WP}.json").write_text(json.dumps(active), encoding="utf-8")
            (root / "workpackages" / "claims" / "F2-WP-002_G2_x.json").write_text(json.dumps(claim), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "no matching claim file"):
                validate(root, WP)

    def test_active_state_cannot_point_to_terminal_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "workpackages" / "active").mkdir(parents=True)
            (root / "workpackages" / "claims").mkdir(parents=True)
            (root / "workpackages").joinpath("STATE.json").write_text(
                json.dumps({"workpackages": {WP: {"status": "IN_PROGRESS", "evidence": []}}}),
                encoding="utf-8",
            )
            active = {
                "workpackage_id": WP,
                "generation": 1,
                "claim_id": "F2-WP-002-G1-x",
                "worker_id": "x",
                "base_commit": "a",
            }
            claim = dict(active, status="ACCEPTED_AT_SCOPE")
            (root / "workpackages" / "active" / f"{WP}.json").write_text(json.dumps(active), encoding="utf-8")
            (root / "workpackages" / "claims" / "F2-WP-002_G1_x.json").write_text(json.dumps(claim), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "IN_PROGRESS STATE cannot point at terminal claim"):
                validate(root, WP)

    def test_terminal_state_requires_reconciliation_and_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "workpackages" / "active").mkdir(parents=True)
            (root / "workpackages" / "claims").mkdir(parents=True)
            (root / "workpackages").joinpath("STATE.json").write_text(
                json.dumps({"workpackages": {WP: {"status": "ACCEPTED_AT_SCOPE", "evidence": []}}}),
                encoding="utf-8",
            )
            active = {
                "workpackage_id": WP,
                "generation": 1,
                "claim_id": "F2-WP-002-G1-x",
                "worker_id": "x",
                "base_commit": "a",
            }
            claim = dict(active, status="ACCEPTED_AT_SCOPE")
            (root / "workpackages" / "active" / f"{WP}.json").write_text(json.dumps(active), encoding="utf-8")
            (root / "workpackages" / "claims" / "F2-WP-002_G1_x.json").write_text(json.dumps(claim), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "reconciliation_ref"):
                validate(root, WP)


if __name__ == "__main__":
    unittest.main(verbosity=2)
