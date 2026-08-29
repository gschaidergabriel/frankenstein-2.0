#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools import validate_workpackage_state as mod

WP = "F2-WP-999"
CLAIM_ID = "F2-WP-999-G1-projection-fixture"


def contract() -> dict:
    return {"compatible_active_pointer_schemas": ["FRANKENSTEIN2_ACTIVE_WORKPACKAGE_CLAIM/v1"], "active_state": "ACTIVE", "terminal_states": ["ACCEPTED", "FAILED_TERMINAL", "RETIRED_STALE", "SUPERSEDED"], "state_values": ["NOT_STARTED", "IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"]}


def pointer(state: str = "ACTIVE") -> dict:
    return {"schema": "FRANKENSTEIN2_ACTIVE_WORKPACKAGE_CLAIM/v1", "workpackage_id": WP, "generation": 1, "claim_id": CLAIM_ID, "worker_id": "fixture-worker", "base_commit": "a" * 40, "state": state}


def claim() -> dict:
    return {"schema": mod.CLAIM_SCHEMA, "workpackage_id": WP, "generation": 1, "claim_id": CLAIM_ID, "worker_id": "fixture-worker", "trigger": "4"}


def state_entry(status: str) -> dict:
    return {"status": status, "phase": 99, "title": "projection fixture", "evidence": ["fixture-evidence"]}


def reconciliation(broader: str) -> dict:
    return {"schema": mod.RECON_SCHEMA, "workpackage_id": WP, "generation": 1, "claim_id": CLAIM_ID, "worker_id": "fixture-worker", "terminal_state": "ACCEPTED", "broader_workpackage_status": broader, "whole_system_acceptance": False}


def _selected_reconciliation(root: Path, pointer_path: Path, pointer_value: dict) -> tuple[dict | None, str | None]:
    if pointer_value.get("state") != "ACCEPTED":
        return None, None
    pointer_ref = pointer_path.relative_to(root).as_posix()
    matches = mod._matching_reconciliations(root, pointer_value)
    selected = mod._select_terminal_reconciliation(root, matches, context=pointer_ref)
    for path, candidate in matches:
        if candidate is selected or candidate == selected:
            return selected, path.relative_to(root).as_posix()
    return selected, None


def _required_projection(root: Path, pointer_path: Path, pointer_value: dict, current_entry: dict | None) -> tuple[str, list[str]]:
    pointer_state = pointer_value.get("state")
    pointer_ref = pointer_path.relative_to(root).as_posix()
    evidence = [pointer_ref]
    current_status = current_entry.get("status") if isinstance(current_entry, dict) else None

    if pointer_state == "ACTIVE":
        return "IN_PROGRESS", evidence

    if pointer_state == "ACCEPTED":
        selected, recon_ref = _selected_reconciliation(root, pointer_path, pointer_value)
        if recon_ref:
            evidence.append(recon_ref)
        broader = selected.get("broader_workpackage_status") if selected else None
        if broader in {"IN_PROGRESS", "ACCEPTED_AT_SCOPE"}:
            return broader, evidence
        # Legacy accepted reconciliations may predate broader_workpackage_status.
        # Preserve an existing non-NOT_STARTED aggregate projection; for missing/stale
        # NOT_STARTED entries, the terminal accepted pointer supports only scoped aggregate
        # acceptance, never runtime/whole-system credit.
        if current_status in {"IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"}:
            return current_status, evidence
        return "ACCEPTED_AT_SCOPE", evidence

    # SUPERSEDED/RETIRED/FAILED pointers do not mint aggregate acceptance. Preserve any
    # existing non-NOT_STARTED broad state; otherwise project conservatively as IN_PROGRESS.
    if current_status in {"IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"}:
        return current_status, evidence
    return "IN_PROGRESS", evidence


class AggregateProjectionGateTests(unittest.TestCase):
    def test_active_pointer_absent_from_state_fails_closed(self):
        with self.assertRaisesRegex(mod.ValidationError, "absent from STATE"):
            mod.validate_pointer(filename_stem=WP, pointer=pointer(), claim=claim(), state_entry=None, contract=contract())

    def test_active_pointer_cannot_remain_not_started(self):
        with self.assertRaisesRegex(mod.ValidationError, "nonterminal broad state"):
            mod.validate_pointer(filename_stem=WP, pointer=pointer(), claim=claim(), state_entry=state_entry("NOT_STARTED"), contract=contract())

    def test_terminal_acceptance_with_broad_acceptance_cannot_project_in_progress(self):
        with self.assertRaisesRegex(mod.ValidationError, "requires broad ACCEPTED_AT_SCOPE"):
            mod.validate_pointer(filename_stem=WP, pointer=pointer("ACCEPTED"), claim=claim(), state_entry=state_entry("IN_PROGRESS"), contract=contract(), reconciliation=reconciliation("ACCEPTED_AT_SCOPE"))

    def test_scoped_acceptance_may_explicitly_keep_broad_workpackage_in_progress(self):
        result = mod.validate_pointer(filename_stem=WP, pointer=pointer("ACCEPTED"), claim=claim(), state_entry=state_entry("IN_PROGRESS"), contract=contract(), reconciliation=reconciliation("IN_PROGRESS"))
        self.assertEqual(result["broad_status"], "IN_PROGRESS")
        self.assertTrue(result["reconciliation_bound"])

    def test_repository_aggregate_matches_granular_pointer_projection(self):
        self.maxDiff = None
        root = Path(__file__).resolve().parents[1]
        state = json.loads((root / "workpackages" / "STATE.json").read_text(encoding="utf-8"))
        projected = state["workpackages"]
        repairs = []
        for pointer_path in sorted((root / "workpackages" / "active").glob("F2-WP-*.json")):
            pointer_value = json.loads(pointer_path.read_text(encoding="utf-8"))
            wp = pointer_path.stem
            entry = projected.get(wp)
            required_status, evidence = _required_projection(root, pointer_path, pointer_value, entry)
            if not isinstance(entry, dict) or entry.get("status") != required_status:
                repairs.append({
                    "workpackage_id": wp,
                    "pointer_state": pointer_value.get("state"),
                    "required_status": required_status,
                    "current_status": entry.get("status") if isinstance(entry, dict) else None,
                    "minimum_evidence": evidence,
                })
        self.assertEqual(repairs, [], "aggregate projection repairs required: " + json.dumps(repairs, sort_keys=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
