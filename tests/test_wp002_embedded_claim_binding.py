#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import validate_workpackage_state as mod

WP = "F2-WP-002"
CLAIM_ID = "F2-WP-002-G3-embedded-test"


def contract() -> dict:
    return {
        "schema": mod.CONTRACT_SCHEMA,
        "canonical_repository": mod.REPO,
        "scope": "SOURCE_AND_CONTINUITY_METADATA_ONLY",
        "canonical_state_schema": mod.STATE_SCHEMA,
        "compatible_active_pointer_schemas": [
            "FRANKENSTEIN2_ACTIVE_WORKPACKAGE/v1",
            mod.ACTIVE_CLAIM_SCHEMA,
            "FRANKENSTEIN2_ACTIVE_WORKPACKAGE_POINTER/v1",
        ],
        "active_state": "ACTIVE",
        "terminal_states": ["ACCEPTED", "FAILED_TERMINAL", "RETIRED_STALE", "SUPERSEDED"],
        "state_values": ["NOT_STARTED", "IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"],
    }


def embedded_pointer(schema: str = mod.ACTIVE_CLAIM_SCHEMA) -> dict:
    return {
        "schema": schema,
        "workpackage_id": WP,
        "generation": 3,
        "claim_id": CLAIM_ID,
        "worker_id": "GPT-5.6-Sol",
        "base_commit": "a" * 40,
        "claimed_scope": "embedded-claim compatibility fixture",
        "created_at_utc": "2026-08-29T15:00:00Z",
        "state": "ACTIVE",
    }


def fixture_root(td: str, pointer: dict) -> Path:
    root = Path(td)
    (root / "workpackages/claims").mkdir(parents=True)
    (root / "workpackages/active").mkdir(parents=True)
    (root / "WORKER_PROTOCOL.md").write_text("fixture", encoding="utf-8")
    (root / mod.CONTRACT_REL).write_text(json.dumps(contract()), encoding="utf-8")
    state = {
        "schema": mod.STATE_SCHEMA,
        "canonical_repository": mod.REPO,
        "generation": 3,
        "workpackages": {
            WP: {
                "status": "IN_PROGRESS",
                "phase": 0,
                "title": "embedded claim fixture",
                "evidence": ["WORKER_PROTOCOL.md"],
            }
        },
    }
    (root / "workpackages/STATE.json").write_text(json.dumps(state), encoding="utf-8")
    (root / f"workpackages/active/{WP}.json").write_text(json.dumps(pointer), encoding="utf-8")
    return root


class EmbeddedClaimBindingTests(unittest.TestCase):
    def test_active_claim_schema_is_self_contained_claim_object(self):
        with tempfile.TemporaryDirectory() as td:
            result = mod.validate_repository(fixture_root(td, embedded_pointer()))
        self.assertTrue(result["pass"])
        self.assertEqual(result["validated"][0]["claim_binding"], "EMBEDDED_ACTIVE_CLAIM")

    def test_non_claim_pointer_without_separate_claim_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = fixture_root(td, embedded_pointer("FRANKENSTEIN2_ACTIVE_WORKPACKAGE/v1"))
            with self.assertRaisesRegex(mod.ValidationError, "no matching claim object"):
                mod.validate_repository(root)

    def test_embedded_claim_requires_protocol_claim_fields(self):
        pointer = embedded_pointer()
        pointer.pop("claimed_scope")
        with tempfile.TemporaryDirectory() as td:
            root = fixture_root(td, pointer)
            with self.assertRaisesRegex(mod.ValidationError, "embedded_claim.claimed_scope"):
                mod.validate_repository(root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
