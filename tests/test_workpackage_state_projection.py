from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "workpackages" / "STATE.json"
LEDGER_PATH = ROOT / "WORKPACKAGES.md"
ACTIVE_DIR = ROOT / "workpackages" / "active"

# Exact stale set admitted by F2-WP-002 generation 5. This deliberately
# avoids claiming authority over unrelated active workpackages.
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
    if claim_state in {"ACTIVE", "IN_PROGRESS"}:
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

    def test_accepted_projection_has_granular_reconciliation_reference(self) -> None:
        workpackages = _aggregate_state()["workpackages"]
        for workpackage_id in G5_RECONCILED_IDS:
            claim = _active_claim(workpackage_id)
            if claim["state"] != "ACCEPTED":
                continue
            evidence = workpackages[workpackage_id].get("evidence", [])
            with self.subTest(workpackage_id=workpackage_id):
                self.assertIn(f"workpackages/active/{workpackage_id}.json", evidence)
                self.assertTrue(
                    any(ref.startswith(f"workpackages/reconciliations/{workpackage_id}/") for ref in evidence),
                    f"{workpackage_id} accepted projection lacks terminal reconciliation evidence",
                )


if __name__ == "__main__":
    unittest.main()
