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
CONTRACT = {
    "schema": "FRANKENSTEIN2_WORKPACKAGE_STATE_CONSISTENCY_CONTRACT/v1",
    "active_state": "ACTIVE",
    "terminal_states": ["ACCEPTED", "FAILED_TERMINAL", "RETIRED_STALE", "SUPERSEDED"],
}


def init_fixture(root: Path, *, status: str = "IN_PROGRESS", evidence=None) -> None:
    if evidence is None:
        evidence = []
    (root / "workpackages" / "active").mkdir(parents=True)
    (root / "workpackages" / "claims").mkdir(parents=True)
    (root / "workpackages" / "reconciliations" / WP).mkdir(parents=True)
    (root / "workpackages" / "STATE.json").write_text(
        json.dumps({"workpackages": {WP: {"status": status, "evidence": evidence}}}),
        encoding="utf-8",
    )
    (root / "workpackages" / "WORKPACKAGE_STATE_CONSISTENCY_CONTRACT_V1.json").write_text(
        json.dumps(CONTRACT), encoding="utf-8"
    )


class StateConsistencyTests(unittest.TestCase):
    def test_current_repository_generation_passes_successor_dynamically(self):
        lines = validate(ROOT, WP)
        self.assertTrue(lines[0].startswith("PASS workpackage=F2-WP-002"))
        self.assertIn("runtime_credit=0", lines)
        self.assertTrue(any(line.startswith("pointer_state=") for line in lines))

    def test_filename_workpackage_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_fixture(root)
            (root / "workpackages" / "active" / f"{WP}.json").write_text(
                json.dumps({
                    "workpackage_id": "F2-WP-999",
                    "generation": 1,
                    "claim_id": "F2-WP-002-G1-x",
                    "worker_id": "x",
                    "base_commit": "a",
                    "state": "ACTIVE",
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValidationError, "filename/workpackage_id mismatch"):
                validate(root, WP)

    def test_generation_claim_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_fixture(root)
            active = {
                "workpackage_id": WP,
                "generation": 2,
                "claim_id": "F2-WP-002-G2-x",
                "worker_id": "x",
                "base_commit": "a",
                "state": "ACTIVE",
            }
            claim = dict(active, generation=1, claim_id="F2-WP-002-G1-x", status="ACTIVE")
            (root / "workpackages" / "active" / f"{WP}.json").write_text(json.dumps(active), encoding="utf-8")
            (root / "workpackages" / "claims" / "F2-WP-002_G2_x.json").write_text(json.dumps(claim), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "no matching claim file"):
                validate(root, WP)

    def test_active_pointer_cannot_point_to_terminal_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_fixture(root)
            active = {
                "workpackage_id": WP,
                "generation": 1,
                "claim_id": "F2-WP-002-G1-x",
                "worker_id": "x",
                "base_commit": "a",
                "state": "ACTIVE",
            }
            claim = dict(active, status="ACCEPTED_AT_SCOPE")
            (root / "workpackages" / "active" / f"{WP}.json").write_text(json.dumps(active), encoding="utf-8")
            (root / "workpackages" / "claims" / "F2-WP-002_G1_x.json").write_text(json.dumps(claim), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "ACTIVE pointer cannot point at terminal claim"):
                validate(root, WP)

    def test_terminal_pointer_requires_reconciliation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_fixture(root, status="ACCEPTED_AT_SCOPE", evidence=["evidence.json"])
            active = {
                "workpackage_id": WP,
                "generation": 1,
                "claim_id": "F2-WP-002-G1-x",
                "worker_id": "x",
                "base_commit": "a",
                "state": "ACCEPTED",
            }
            claim = dict(active, status="ACTIVE_SCOPE")
            (root / "workpackages" / "active" / f"{WP}.json").write_text(json.dumps(active), encoding="utf-8")
            (root / "workpackages" / "claims" / "F2-WP-002_G1_x.json").write_text(json.dumps(claim), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "reconciliation_ref"):
                validate(root, WP)

    def test_scoped_terminal_acceptance_can_leave_broad_state_in_progress(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_fixture(root, status="IN_PROGRESS")
            reconciliation_ref = f"workpackages/reconciliations/{WP}/1-F2-WP-002-G1-x.json"
            active = {
                "workpackage_id": WP,
                "generation": 1,
                "claim_id": "F2-WP-002-G1-x",
                "worker_id": "x",
                "base_commit": "a",
                "state": "ACCEPTED",
                "reconciliation_ref": reconciliation_ref,
            }
            claim = {
                "workpackage_id": WP,
                "generation": 1,
                "claim_id": "F2-WP-002-G1-x",
                "worker_id": "x",
                "base_commit": "a",
                "status": "ACTIVE_SCOPE",
            }
            reconciliation = {
                "schema": "FRANKENSTEIN2_WORKPACKAGE_RECONCILIATION/v1",
                "workpackage_id": WP,
                "generation": 1,
                "claim_id": "F2-WP-002-G1-x",
                "terminal_state": "ACCEPTED",
                "broader_workpackage_status": "IN_PROGRESS",
                "whole_system_acceptance": False,
            }
            (root / "workpackages" / "active" / f"{WP}.json").write_text(json.dumps(active), encoding="utf-8")
            (root / "workpackages" / "claims" / "F2-WP-002_G1_x.json").write_text(json.dumps(claim), encoding="utf-8")
            (root / reconciliation_ref).write_text(json.dumps(reconciliation), encoding="utf-8")
            lines = validate(root, WP)
            self.assertIn("pointer_state=ACCEPTED", lines)
            self.assertIn(f"reconciliation={reconciliation_ref}", lines)
            self.assertIn("runtime_credit=0", lines)

    def test_terminal_reconciliation_broad_status_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init_fixture(root, status="IN_PROGRESS")
            reconciliation_ref = f"workpackages/reconciliations/{WP}/1-F2-WP-002-G1-x.json"
            active = {
                "workpackage_id": WP,
                "generation": 1,
                "claim_id": "F2-WP-002-G1-x",
                "worker_id": "x",
                "base_commit": "a",
                "state": "ACCEPTED",
                "reconciliation_ref": reconciliation_ref,
            }
            claim = {
                "workpackage_id": WP,
                "generation": 1,
                "claim_id": "F2-WP-002-G1-x",
                "worker_id": "x",
                "base_commit": "a",
                "status": "ACTIVE_SCOPE",
            }
            reconciliation = {
                "schema": "FRANKENSTEIN2_WORKPACKAGE_RECONCILIATION/v1",
                "workpackage_id": WP,
                "generation": 1,
                "claim_id": "F2-WP-002-G1-x",
                "terminal_state": "ACCEPTED",
                "broader_workpackage_status": "ACCEPTED_AT_SCOPE",
                "whole_system_acceptance": False,
            }
            (root / "workpackages" / "active" / f"{WP}.json").write_text(json.dumps(active), encoding="utf-8")
            (root / "workpackages" / "claims" / "F2-WP-002_G1_x.json").write_text(json.dumps(claim), encoding="utf-8")
            (root / reconciliation_ref).write_text(json.dumps(reconciliation), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "reconciliation/state mismatch"):
                validate(root, WP)


if __name__ == "__main__":
    unittest.main(verbosity=2)
