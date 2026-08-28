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
        "generation": 3,
        "claim_id": "F2-WP-002-G3-GPT56SOL-checkpoint-validator",
        "checkpoint_parent_main": "a" * 40,
        "worker_claim_commit": "b" * 40,
        "observed_parallel_frontier": {"F2-WP-005": "ACTIVE_PARALLEL_TELEMETRY_SPINE"},
        "strongest_current_evidence": [{"type": "CANONICAL_SOURCE", "path": "WORKER_PROTOCOL.md"}],
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
        "generation": 3,
        "claim_id": "F2-WP-002-G3-GPT56SOL-checkpoint-validator",
        "worker_id": "GPT-5.6-Sol",
        "trigger": "4",
        "runtime_execution_observed": False,
        "runtime_credit": 0,
    }


class CheckpointValidatorTests(unittest.TestCase):
    def test_accepts_well_formed_source_only_checkpoint(self):
        mod.validate_checkpoint(valid_checkpoint(), valid_claim())

    def test_rejects_missing_required_field(self):
        cp = valid_checkpoint()
        del cp["next_exact_action"]
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(cp, valid_claim())

    def test_rejects_malformed_commit(self):
        cp = valid_checkpoint()
        cp["worker_claim_commit"] = "not-a-commit"
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(cp, valid_claim())

    def test_rejects_runtime_credit_without_runtime_evidence(self):
        cp = valid_checkpoint()
        cp["runtime_credit"] = 1
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(cp, valid_claim())

    def test_rejects_whole_system_acceptance_without_runtime_evidence(self):
        cp = valid_checkpoint()
        cp["whole_system_acceptance"] = True
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(cp, valid_claim())

    def test_rejects_claim_identity_mismatch(self):
        claim = valid_claim()
        claim["generation"] = 2
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(valid_checkpoint(), claim)

    def test_rejects_claim_that_asserts_runtime_execution(self):
        claim = valid_claim()
        claim["runtime_execution_observed"] = True
        with self.assertRaises(mod.ValidationError):
            mod.validate_checkpoint(valid_checkpoint(), claim)


if __name__ == "__main__":
    unittest.main()
