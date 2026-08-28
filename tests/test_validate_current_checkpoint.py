#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "validate_current_checkpoint.py"
spec = importlib.util.spec_from_file_location("validate_current_checkpoint", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def valid_checkpoint():
    return {
        "schema": "FRANKENSTEIN2_CURRENT_CHECKPOINT/v1",
        "canonical_repository": "gschaidergabriel/frankenstein-2.0",
        "trigger": "4",
        "worker_id": "GPT-5.6-Sol",
        "current_workpackage": "F2-WP-002",
        "generation": 2,
        "claim_id": "F2-WP-002-G2-GPT56SOL-cd0e056a",
        "checkpoint_parent_main": "a" * 40,
        "worker_claim_commit": "b" * 40,
        "observed_parallel_frontier": {"F2-WP-005": "ACTIVE_PARALLEL_TELEMETRY_SPINE"},
        "strongest_current_evidence": [
            {"type": "CANONICAL_SOURCE", "path": "WORKER_PROTOCOL.md", "commit": "c" * 40}
        ],
        "completed_this_checkpoint": ["validator source added"],
        "unresolved": ["repository-bound execution still required"],
        "evidence_scope": "SOURCE_AND_CONTINUITY_METADATA_ONLY",
        "runtime_execution_observed": False,
        "runtime_credit": 0,
        "whole_system_acceptance": False,
        "next_exact_action": "run deterministic validator tests",
    }


def valid_claim():
    return {
        "schema": "FRANKENSTEIN2_WORKPACKAGE_CLAIM/v1",
        "workpackage_id": "F2-WP-002",
        "generation": 2,
        "claim_id": "F2-WP-002-G2-GPT56SOL-cd0e056a",
        "worker_id": "GPT-5.6-Sol",
        "trigger": "4",
        "runtime_execution_observed": False,
        "runtime_credit": 0,
    }


def valid_active():
    return {
        "schema": "FRANKENSTEIN2_ACTIVE_WORKPACKAGE/v1",
        "workpackage_id": "F2-WP-002",
        "generation": 2,
        "claim_id": "F2-WP-002-G2-GPT56SOL-cd0e056a",
        "worker_id": "GPT-5.6-Sol",
        "base_commit": "d" * 40,
        "claimed_scope": "checkpoint validation",
        "created_at_utc": "2026-08-28T14:42:55Z",
        "state": "ACTIVE",
    }


def valid_reconciliation():
    return {
        "schema": "FRANKENSTEIN2_WORKPACKAGE_RECONCILIATION/v1",
        "workpackage_id": "F2-WP-002",
        "generation": 2,
        "claim_id": "F2-WP-002-G2-GPT56SOL-cd0e056a",
        "worker_id": "GPT-5.6-Sol",
        "terminal_state": "ACCEPTED",
        "whole_system_acceptance": False,
    }


def valid_state():
    return {
        "schema": "FRANKENSTEIN2_WORKPACKAGE_STATE/v1",
        "canonical_repository": "gschaidergabriel/frankenstein-2.0",
        "workpackages": {
            "F2-WP-002": {"status": "IN_PROGRESS", "phase": 0, "title": "Machine state", "evidence": []}
        },
    }


class CheckpointValidatorTests(unittest.TestCase):
    def test_accepts_well_formed_source_only_checkpoint(self):
        result = mod.validate_checkpoint(valid_checkpoint(), valid_claim(), valid_active(), valid_state())
        self.assertTrue(result["pass"])
        self.assertTrue(result["active_pointer_bound"])
        self.assertTrue(result["workpackage_state_bound"])
        self.assertFalse(result["reconciliation_bound"])
        self.assertEqual(result["runtime_credit_granted"], 0)

    def test_accepts_terminal_pointer_with_matching_reconciliation(self):
        active = valid_active()
        active["state"] = "ACCEPTED"
        result = mod.validate_checkpoint(
            valid_checkpoint(), valid_claim(), active, valid_state(), valid_reconciliation()
        )
        self.assertTrue(result["pass"])
        self.assertTrue(result["reconciliation_bound"])
        self.assertEqual(result["active_state"], "ACCEPTED")

    def test_rejects_missing_required_field(self):
        cp = valid_checkpoint()
        del cp["next_exact_action"]
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(cp, valid_claim(), valid_active(), valid_state())

    def test_rejects_malformed_commit(self):
        cp = valid_checkpoint()
        cp["worker_claim_commit"] = "not-a-commit"
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(cp, valid_claim(), valid_active(), valid_state())

    def test_rejects_malformed_evidence_commit(self):
        cp = valid_checkpoint()
        cp["strongest_current_evidence"][0]["commit"] = "not-a-commit"
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(cp, valid_claim(), valid_active(), valid_state())

    def test_rejects_runtime_credit_without_runtime_evidence(self):
        cp = valid_checkpoint()
        cp["runtime_credit"] = 1
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(cp, valid_claim(), valid_active(), valid_state())

    def test_rejects_whole_system_acceptance_without_runtime_evidence(self):
        cp = valid_checkpoint()
        cp["whole_system_acceptance"] = True
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(cp, valid_claim(), valid_active(), valid_state())

    def test_rejects_claim_identity_mismatch(self):
        claim = valid_claim()
        claim["generation"] = 3
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(valid_checkpoint(), claim, valid_active(), valid_state())

    def test_rejects_claim_that_asserts_runtime_execution(self):
        claim = valid_claim()
        claim["runtime_execution_observed"] = True
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(valid_checkpoint(), claim, valid_active(), valid_state())

    def test_rejects_active_generation_mismatch(self):
        active = valid_active()
        active["generation"] = 3
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(valid_checkpoint(), valid_claim(), active, valid_state())

    def test_rejects_terminal_active_pointer_without_reconciliation(self):
        active = valid_active()
        active["state"] = "ACCEPTED"
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(valid_checkpoint(), valid_claim(), active, valid_state())

    def test_rejects_wrong_terminal_reconciliation(self):
        active = valid_active()
        active["state"] = "ACCEPTED"
        reconciliation = valid_reconciliation()
        reconciliation["terminal_state"] = "SUPERSEDED"
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(valid_checkpoint(), valid_claim(), active, valid_state(), reconciliation)

    def test_rejects_not_started_state(self):
        state = valid_state()
        state["workpackages"]["F2-WP-002"]["status"] = "NOT_STARTED"
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(valid_checkpoint(), valid_claim(), valid_active(), state)

    def test_rejects_missing_state_workpackage(self):
        state = valid_state()
        del state["workpackages"]["F2-WP-002"]
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(valid_checkpoint(), valid_claim(), valid_active(), state)


if __name__ == "__main__":
    unittest.main()
