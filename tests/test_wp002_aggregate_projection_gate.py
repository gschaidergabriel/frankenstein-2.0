#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import rebuild_workpackage_state_projection as rebuild
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

    def test_rebuilder_preserves_existing_broad_acceptance_when_reconciliation_is_unresolved(self):
        with tempfile.TemporaryDirectory() as td:
            status, basis, unresolved = rebuild._project_status(
                Path(td), pointer("ACCEPTED"), "ACCEPTED_AT_SCOPE"
            )
        self.assertEqual(status, "ACCEPTED_AT_SCOPE")
        self.assertEqual(basis, "PRESERVE_EXISTING_ACCEPTED_PROJECTION_UNDER_UNRESOLVED_RECONCILIATION")
        self.assertIsNotNone(unresolved)

    def test_rebuilder_raises_missing_accepted_projection_only_to_in_progress(self):
        with tempfile.TemporaryDirectory() as td:
            status, basis, unresolved = rebuild._project_status(
                Path(td), pointer("ACCEPTED"), "NOT_STARTED"
            )
        self.assertEqual(status, "IN_PROGRESS")
        self.assertEqual(basis, "UNRESOLVED_RECONCILIATION_CONSERVATIVE_IN_PROGRESS")
        self.assertIsNotNone(unresolved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
