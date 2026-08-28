#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "validate_workpackage_state.py"
spec = importlib.util.spec_from_file_location("validate_workpackage_state", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def valid_state(status: str = "IN_PROGRESS", evidence=None):
    if evidence is None:
        evidence = ["WORKER_PROTOCOL.md"]
    return {
        "schema": mod.STATE_SCHEMA,
        "canonical_repository": mod.REPO,
        "generation": 3,
        "workpackages": {
            "F2-WP-002": {
                "status": status,
                "phase": 0,
                "title": "Machine-readable state",
                "evidence": evidence,
            }
        },
    }


def valid_pointer(state: str = "ACTIVE"):
    value = {
        "schema": mod.ACTIVE_SCHEMA,
        "workpackage_id": "F2-WP-002",
        "generation": 3,
        "claim_id": "F2-WP-002-G3-test",
        "worker_id": "GPT-5.6-Sol",
        "base_commit": "a" * 40,
        "legacy_claim_ref": "workpackages/claims/F2-WP-002_G3_test.json",
        "state": state,
    }
    if state != "ACTIVE":
        value["terminal_reconciliation_ref"] = "workpackages/reconciliations/F2-WP-002/3-test.json"
    return value


def valid_claim():
    return {
        "schema": mod.CLAIM_SCHEMA,
        "workpackage_id": "F2-WP-002",
        "generation": 3,
        "claim_id": "F2-WP-002-G3-test",
        "worker_id": "GPT-5.6-Sol",
        "trigger": "4",
    }


def valid_reconciliation(*, broader="IN_PROGRESS"):
    return {
        "schema": mod.RECON_SCHEMA,
        "workpackage_id": "F2-WP-002",
        "generation": 3,
        "claim_id": "F2-WP-002-G3-test",
        "worker_id": "GPT-5.6-Sol",
        "terminal_state": "ACCEPTED",
        "broader_workpackage_status": broader,
        "whole_system_acceptance": False,
    }


class WorkpackageStateValidatorTests(unittest.TestCase):
    def test_valid_state_and_active_pointer_pass(self):
        state = valid_state()
        entries = mod.validate_state(state)
        result = mod.validate_pointer(
            filename_stem="F2-WP-002",
            pointer=valid_pointer(),
            claim=valid_claim(),
            state_entry=entries["F2-WP-002"],
        )
        self.assertEqual(result["pointer_state"], "ACTIVE")
        self.assertEqual(result["broad_status"], "IN_PROGRESS")

    def test_accepted_state_requires_evidence(self):
        with self.assertRaisesRegex(mod.ValidationError, "requires evidence"):
            mod.validate_state(valid_state("ACCEPTED_AT_SCOPE", []))

    def test_wrong_active_filename_fails_closed(self):
        with self.assertRaisesRegex(mod.ValidationError, "filename/workpackage mismatch"):
            mod.validate_pointer(
                filename_stem="F2-WP-999",
                pointer=valid_pointer(),
                claim=valid_claim(),
                state_entry=valid_state()["workpackages"]["F2-WP-002"],
            )

    def test_generation_zero_fails_closed(self):
        pointer = valid_pointer()
        pointer["generation"] = 0
        claim = valid_claim()
        claim["generation"] = 0
        with self.assertRaisesRegex(mod.ValidationError, "generation must be integer"):
            mod.validate_pointer(
                filename_stem="F2-WP-002",
                pointer=pointer,
                claim=claim,
                state_entry=valid_state()["workpackages"]["F2-WP-002"],
            )

    def test_claim_identity_mismatch_fails_closed(self):
        claim = valid_claim()
        claim["claim_id"] = "different"
        with self.assertRaisesRegex(mod.ValidationError, "claim/pointer identity mismatch"):
            mod.validate_pointer(
                filename_stem="F2-WP-002",
                pointer=valid_pointer(),
                claim=claim,
                state_entry=valid_state()["workpackages"]["F2-WP-002"],
            )

    def test_active_pointer_requires_open_broad_state(self):
        with self.assertRaisesRegex(mod.ValidationError, "ACTIVE pointer requires open broad state"):
            mod.validate_pointer(
                filename_stem="F2-WP-002",
                pointer=valid_pointer(),
                claim=valid_claim(),
                state_entry=valid_state("ACCEPTED_AT_SCOPE")["workpackages"]["F2-WP-002"],
            )

    def test_missing_state_entry_fails_closed(self):
        with self.assertRaisesRegex(mod.ValidationError, "absent from STATE"):
            mod.validate_pointer(
                filename_stem="F2-WP-002",
                pointer=valid_pointer(),
                claim=valid_claim(),
                state_entry=None,
            )

    def test_terminal_pointer_without_reconciliation_fails_closed(self):
        with self.assertRaisesRegex(mod.ValidationError, "requires reconciliation"):
            mod.validate_pointer(
                filename_stem="F2-WP-002",
                pointer=valid_pointer("ACCEPTED"),
                claim=valid_claim(),
                state_entry=valid_state()["workpackages"]["F2-WP-002"],
                reconciliation=None,
            )

    def test_scoped_terminal_acceptance_can_leave_broad_workpackage_in_progress(self):
        result = mod.validate_pointer(
            filename_stem="F2-WP-002",
            pointer=valid_pointer("ACCEPTED"),
            claim=valid_claim(),
            state_entry=valid_state("IN_PROGRESS")["workpackages"]["F2-WP-002"],
            reconciliation=valid_reconciliation(broader="IN_PROGRESS"),
        )
        self.assertEqual(result["pointer_state"], "ACCEPTED")
        self.assertTrue(result["reconciliation_bound"])

    def test_terminal_acceptance_without_scoped_exception_requires_broad_acceptance(self):
        with self.assertRaisesRegex(mod.ValidationError, "requires broad ACCEPTED_AT_SCOPE"):
            mod.validate_pointer(
                filename_stem="F2-WP-002",
                pointer=valid_pointer("ACCEPTED"),
                claim=valid_claim(),
                state_entry=valid_state("IN_PROGRESS")["workpackages"]["F2-WP-002"],
                reconciliation=valid_reconciliation(broader="ACCEPTED_AT_SCOPE"),
            )

    def test_terminal_acceptance_with_broad_acceptance_passes(self):
        result = mod.validate_pointer(
            filename_stem="F2-WP-002",
            pointer=valid_pointer("ACCEPTED"),
            claim=valid_claim(),
            state_entry=valid_state("ACCEPTED_AT_SCOPE")["workpackages"]["F2-WP-002"],
            reconciliation=valid_reconciliation(broader="ACCEPTED_AT_SCOPE"),
        )
        self.assertEqual(result["broad_status"], "ACCEPTED_AT_SCOPE")

    def test_reconciliation_identity_mismatch_fails_closed(self):
        reconciliation = valid_reconciliation()
        reconciliation["generation"] = 4
        with self.assertRaisesRegex(mod.ValidationError, "reconciliation/pointer identity mismatch"):
            mod.validate_pointer(
                filename_stem="F2-WP-002",
                pointer=valid_pointer("ACCEPTED"),
                claim=valid_claim(),
                state_entry=valid_state()["workpackages"]["F2-WP-002"],
                reconciliation=reconciliation,
            )


if __name__ == "__main__":
    unittest.main()
