from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "workpackages" / "STATE.json"
LEDGER_PATH = ROOT / "WORKPACKAGES.md"
ACTIVE_DIR = ROOT / "workpackages" / "active"

# G5 deliberately covers only workpackages whose granular terminal state maps
# directly to the broad ledger state. Some GRID packages (for example WP500)
# explicitly keep broad IN_PROGRESS status after component acceptance and are
# therefore outside this invariant.
G5_RECONCILED_IDS = (
    "F2-WP-200",
    "F2-WP-201",
    "F2-WP-203",
    "F2-WP-205",
    "F2-WP-206",
    "F2-WP-300",
    "F2-WP-301",
    "F2-WP-302",
    "F2-WP-303",
    "F2-WP-304",
    "F2-WP-305",
    "F2-WP-306",
)


def _aggregate_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _active_claim(workpackage_id: str) -> dict:
    return json.loads((ACTIVE_DIR / f"{workpackage_id}.json").read_text(encoding="utf-8"))


def _ledger_markers() -> dict[str, str]:
    markers: dict[str, str] = {}
    pattern = re.compile(r"^- \[(?P<marker>[ x!\-])\] (?P<id>F2-WP-\d+)\b", re.MULTILINE)
    for match in pattern.finditer(LEDGER_PATH.read_text(encoding="utf-8")):
        markers[match.group("id")] = match.group("marker")
    return markers


def _expected_projection(claim_state: str) -> tuple[str, str]:
    if claim_state == "ACCEPTED":
        return "ACCEPTED_AT_SCOPE", "x"
    if claim_state in {"ACTIVE", "IN_PROGRESS", "CLAIMED"}:
        return "IN_PROGRESS", "-"
    raise AssertionError(f"unsupported G5 claim state: {claim_state}")


class WorkpackageStateProjectionTests(unittest.TestCase):
    def test_reconciled_active_workpackages_exist_in_machine_aggregate(self) -> None:
        workpackages = _aggregate_state()["workpackages"]
        for workpackage_id in G5_RECONCILED_IDS:
            with self.subTest(workpackage_id=workpackage_id):
                self.assertIn(workpackage_id, workpackages)

    def test_pointer_state_cannot_be_downgraded_in_machine_aggregate(self) -> None:
        workpackages = _aggregate_state()["workpackages"]
        for workpackage_id in G5_RECONCILED_IDS:
            claim = _active_claim(workpackage_id)
            expected_state, _ = _expected_projection(claim["state"])
            with self.subTest(workpackage_id=workpackage_id, claim_state=claim["state"]):
                self.assertEqual(workpackages[workpackage_id]["status"], expected_state)

    def test_human_ledger_matches_same_granular_pointer_state(self) -> None:
        markers = _ledger_markers()
        for workpackage_id in G5_RECONCILED_IDS:
            claim = _active_claim(workpackage_id)
            _, expected_marker = _expected_projection(claim["state"])
            with self.subTest(workpackage_id=workpackage_id, claim_state=claim["state"]):
                self.assertIn(workpackage_id, markers)
                self.assertEqual(markers[workpackage_id], expected_marker)

    def test_accepted_projection_binds_current_existing_reconciliation(self) -> None:
        workpackages = _aggregate_state()["workpackages"]
        for workpackage_id in G5_RECONCILED_IDS:
            claim = _active_claim(workpackage_id)
            if claim["state"] != "ACCEPTED":
                continue
            evidence = workpackages[workpackage_id].get("evidence", [])
            current_reconciliation = claim.get("reconciliation_ref")
            with self.subTest(workpackage_id=workpackage_id):
                self.assertIn(f"workpackages/active/{workpackage_id}.json", evidence)
                self.assertIsInstance(current_reconciliation, str)
                self.assertTrue(current_reconciliation)
                self.assertIn(
                    current_reconciliation,
                    evidence,
                    f"{workpackage_id} aggregate evidence is stale relative to its current accepted generation",
                )
                self.assertTrue(
                    (ROOT / current_reconciliation).is_file(),
                    f"{workpackage_id} current reconciliation reference does not exist in this tree",
                )


if __name__ == "__main__":
    unittest.main()
