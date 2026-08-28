#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from validate_checkpoint import CheckpointValidationError, validate_checkpoint


GOOD_CLAIM = {
    "schema": "FRANKENSTEIN2_WORKPACKAGE_CLAIM/v1",
    "workpackage_id": "F2-WP-002",
    "generation": 2,
    "claim_id": "F2-WP-002-G2-GPT56SOL-test",
    "worker_id": "GPT-5.6-Sol",
    "trigger": "4",
}

GOOD_CP = {
    "schema": "FRANKENSTEIN2_CURRENT_CHECKPOINT/v1",
    "canonical_repository": "gschaidergabriel/frankenstein-2.0",
    "trigger": "4",
    "worker_id": "GPT-5.6-Sol",
    "current_workpackage": "F2-WP-002",
    "generation": 2,
    "claim_id": "F2-WP-002-G2-GPT56SOL-test",
    "checkpoint_parent_main": "a" * 40,
    "worker_claim_commit": "b" * 40,
    "strongest_current_evidence": [
        {"type": "CANONICAL_SOURCE", "claim": "checkpoint continuity is required"}
    ],
    "completed_this_checkpoint": ["created checkpoint"],
    "unresolved": ["runtime acceptance remains open"],
    "evidence_scope": "SOURCE_AND_CONTINUITY_METADATA_ONLY",
    "runtime_execution_observed": False,
    "runtime_credit": 0,
    "whole_system_acceptance": False,
    "next_exact_action": "Run a separate bounded validator test and archive its receipt.",
}


def write_fixture(root: Path, cp: dict, claim: dict = GOOD_CLAIM) -> None:
    (root / "checkpoints").mkdir(parents=True)
    (root / "workpackages" / "claims").mkdir(parents=True)
    (root / "checkpoints" / "CURRENT.json").write_text(json.dumps(cp), encoding="utf-8")
    (root / "workpackages" / "STATE.json").write_text(
        json.dumps({
            "schema": "FRANKENSTEIN2_WORKPACKAGE_STATE/v1",
            "workpackages": {"F2-WP-002": {"status": "IN_PROGRESS"}},
        }),
        encoding="utf-8",
    )
    (root / "workpackages" / "claims" / "claim.json").write_text(json.dumps(claim), encoding="utf-8")


class CheckpointValidatorTests(unittest.TestCase):
    def test_accepts_bound_source_only_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_fixture(root, GOOD_CP)
            result = validate_checkpoint(root)
            self.assertTrue(result["pass"])
            self.assertEqual(result["runtime_credit"], 0)

    def test_rejects_claim_generation_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad_claim = copy.deepcopy(GOOD_CLAIM)
            bad_claim["generation"] = 3
            write_fixture(root, GOOD_CP, bad_claim)
            with self.assertRaisesRegex(CheckpointValidationError, "claim binding mismatch generation"):
                validate_checkpoint(root)

    def test_rejects_runtime_credit_without_runtime_observation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad_cp = copy.deepcopy(GOOD_CP)
            bad_cp["runtime_credit"] = 1
            write_fixture(root, bad_cp)
            with self.assertRaisesRegex(CheckpointValidationError, "must be 0"):
                validate_checkpoint(root)

    def test_rejects_terminal_placeholder_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad_cp = copy.deepcopy(GOOD_CP)
            bad_cp["next_exact_action"] = "done"
            write_fixture(root, bad_cp)
            with self.assertRaisesRegex(CheckpointValidationError, "executable continuation"):
                validate_checkpoint(root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
