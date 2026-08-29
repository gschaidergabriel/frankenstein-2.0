#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "validate_workpackage_state.py"
spec = importlib.util.spec_from_file_location("validate_workpackage_state", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

COMPAT_SCHEMAS = [
    "FRANKENSTEIN2_ACTIVE_WORKPACKAGE/v1",
    "FRANKENSTEIN2_ACTIVE_WORKPACKAGE_CLAIM/v1",
    "FRANKENSTEIN2_ACTIVE_WORKPACKAGE_POINTER/v1",
]


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


def valid_pointer(state: str = "ACTIVE", schema: str = COMPAT_SCHEMAS[0]):
    return {
        "schema": schema,
        "workpackage_id": "F2-WP-002",
        "generation": 3,
        "claim_id": "F2-WP-002-G3-test",
        "worker_id": "GPT-5.6-Sol",
        "base_commit": "a" * 40,
        "state": state,
    }


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


def valid_contract():
    return {
        "schema": mod.CONTRACT_SCHEMA,
        "canonical_repository": mod.REPO,
        "scope": "SOURCE_AND_CONTINUITY_METADATA_ONLY",
        "canonical_state_schema": mod.STATE_SCHEMA,
        "compatible_active_pointer_schemas": COMPAT_SCHEMAS,
        "active_state": "ACTIVE",
        "terminal_states": ["ACCEPTED", "FAILED_TERMINAL", "RETIRED_STALE", "SUPERSEDED"],
        "state_values": ["NOT_STARTED", "IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"],
    }


class WorkpackageStateValidatorTests(unittest.TestCase):
    def test_all_observed_v1_pointer_schema_spellings_are_compatible(self):
        entry = valid_state()["workpackages"]["F2-WP-002"]
        for schema in COMPAT_SCHEMAS:
            with self.subTest(schema=schema):
                result = mod.validate_pointer(
                    filename_stem="F2-WP-002",
                    pointer=valid_pointer(schema=schema),
                    claim=valid_claim(),
                    state_entry=entry,
                    contract=valid_contract(),
                )
                self.assertEqual(result["pointer_schema"], schema)

    def test_unknown_pointer_schema_fails_closed(self):
        with self.assertRaisesRegex(mod.ValidationError, "schema not contract-admitted"):
            mod.validate_pointer(
                filename_stem="F2-WP-002",
                pointer=valid_pointer(schema="UNKNOWN/v1"),
                claim=valid_claim(),
                state_entry=valid_state()["workpackages"]["F2-WP-002"],
                contract=valid_contract(),
            )

    def test_accepted_state_requires_evidence(self):
        with self.assertRaisesRegex(mod.ValidationError, "requires evidence"):
            mod.validate_state(valid_state("ACCEPTED_AT_SCOPE", []), valid_contract())

    def test_wrong_active_filename_fails_closed(self):
        with self.assertRaisesRegex(mod.ValidationError, "filename/workpackage mismatch"):
            mod.validate_pointer(
                filename_stem="F2-WP-999",
                pointer=valid_pointer(),
                claim=valid_claim(),
                state_entry=valid_state()["workpackages"]["F2-WP-002"],
                contract=valid_contract(),
            )

    def test_generation_zero_fails_closed(self):
        pointer = valid_pointer()
        pointer["generation"] = 0
        claim = valid_claim()
        claim["generation"] = 0
        with self.assertRaisesRegex(mod.ValidationError, "generation must be integer"):
            mod.validate_pointer(
                filename_stem="F2-WP-002", pointer=pointer, claim=claim,
                state_entry=valid_state()["workpackages"]["F2-WP-002"], contract=valid_contract()
            )

    def test_claim_identity_mismatch_fails_closed(self):
        claim = valid_claim()
        claim["claim_id"] = "different"
        with self.assertRaisesRegex(mod.ValidationError, "claim/pointer identity mismatch"):
            mod.validate_pointer(
                filename_stem="F2-WP-002", pointer=valid_pointer(), claim=claim,
                state_entry=valid_state()["workpackages"]["F2-WP-002"], contract=valid_contract()
            )

    def test_claim_without_trigger_is_compatibility_admitted(self):
        claim = valid_claim()
        claim.pop("trigger")
        result = mod.validate_pointer(
            filename_stem="F2-WP-002", pointer=valid_pointer(), claim=claim,
            state_entry=valid_state()["workpackages"]["F2-WP-002"], contract=valid_contract()
        )
        self.assertEqual(result["claim_id"], "F2-WP-002-G3-test")

    def test_explicit_wrong_claim_trigger_fails_closed(self):
        claim = valid_claim()
        claim["trigger"] = "5"
        with self.assertRaisesRegex(mod.ValidationError, "claim trigger must be '4' when present"):
            mod.validate_pointer(
                filename_stem="F2-WP-002", pointer=valid_pointer(), claim=claim,
                state_entry=valid_state()["workpackages"]["F2-WP-002"], contract=valid_contract()
            )

    def test_active_pointer_rejects_not_started_and_accepted_broad_state(self):
        for status in ("NOT_STARTED", "ACCEPTED_AT_SCOPE"):
            with self.subTest(status=status), self.assertRaisesRegex(mod.ValidationError, "nonterminal broad state"):
                mod.validate_pointer(
                    filename_stem="F2-WP-002", pointer=valid_pointer(), claim=valid_claim(),
                    state_entry=valid_state(status)["workpackages"]["F2-WP-002"], contract=valid_contract()
                )

    def test_terminal_pointer_without_reconciliation_fails_closed(self):
        with self.assertRaisesRegex(mod.ValidationError, "requires reconciliation"):
            mod.validate_pointer(
                filename_stem="F2-WP-002", pointer=valid_pointer("ACCEPTED"), claim=valid_claim(),
                state_entry=valid_state()["workpackages"]["F2-WP-002"], contract=valid_contract(), reconciliation=None
            )

    def test_scoped_terminal_acceptance_can_leave_broad_workpackage_in_progress(self):
        result = mod.validate_pointer(
            filename_stem="F2-WP-002", pointer=valid_pointer("ACCEPTED"), claim=valid_claim(),
            state_entry=valid_state("IN_PROGRESS")["workpackages"]["F2-WP-002"],
            contract=valid_contract(), reconciliation=valid_reconciliation(broader="IN_PROGRESS")
        )
        self.assertTrue(result["reconciliation_bound"])

    def test_exact_legacy_whole_system_non_credit_token_is_admitted(self):
        reconciliation = valid_reconciliation(broader="IN_PROGRESS")
        reconciliation.pop("whole_system_acceptance")
        reconciliation["non_credit"] = [
            "NO_PROVIDER_RUNTIME_CREDIT",
            mod.LEGACY_WHOLE_SYSTEM_NON_CREDIT,
        ]
        result = mod.validate_pointer(
            filename_stem="F2-WP-002", pointer=valid_pointer("ACCEPTED"), claim=valid_claim(),
            state_entry=valid_state("IN_PROGRESS")["workpackages"]["F2-WP-002"],
            contract=valid_contract(), reconciliation=reconciliation,
        )
        self.assertTrue(result["reconciliation_bound"])

    def test_legacy_non_credit_without_exact_whole_system_token_fails_closed(self):
        reconciliation = valid_reconciliation(broader="IN_PROGRESS")
        reconciliation.pop("whole_system_acceptance")
        reconciliation["non_credit"] = ["NO_PROVIDER_RUNTIME_CREDIT"]
        with self.assertRaisesRegex(mod.ValidationError, "explicit zero whole-system credit"):
            mod.validate_pointer(
                filename_stem="F2-WP-002", pointer=valid_pointer("ACCEPTED"), claim=valid_claim(),
                state_entry=valid_state("IN_PROGRESS")["workpackages"]["F2-WP-002"],
                contract=valid_contract(), reconciliation=reconciliation,
            )

    def test_repository_resolves_claim_by_identity_and_reconciliation_by_tuple(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "workpackages/claims").mkdir(parents=True)
            (root / "workpackages/active").mkdir(parents=True)
            (root / "workpackages/reconciliations/F2-WP-002").mkdir(parents=True)
            (root / "WORKER_PROTOCOL.md").write_text("fixture", encoding="utf-8")
            (root / mod.CONTRACT_REL).write_text(json.dumps(valid_contract()), encoding="utf-8")
            state = valid_state("IN_PROGRESS")
            (root / "workpackages/STATE.json").write_text(json.dumps(state), encoding="utf-8")
            (root / "workpackages/claims/arbitrary-filename.json").write_text(json.dumps(valid_claim()), encoding="utf-8")
            pointer = valid_pointer("ACCEPTED", COMPAT_SCHEMAS[2])
            (root / "workpackages/active/F2-WP-002.json").write_text(json.dumps(pointer), encoding="utf-8")
            (root / "workpackages/reconciliations/F2-WP-002/not-derived-from-ref.json").write_text(
                json.dumps(valid_reconciliation()), encoding="utf-8"
            )
            result = mod.validate_repository(root)
            self.assertTrue(result["pass"])
            self.assertEqual(result["active_pointers_validated"], 1)
            self.assertEqual(result["runtime_credit_granted"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
