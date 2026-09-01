#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import validate_workpackage_state as mod


def contract() -> dict:
    return {
        "schema": mod.CONTRACT_SCHEMA,
        "canonical_repository": mod.REPO,
        "scope": "SOURCE_AND_CONTINUITY_METADATA_ONLY",
        "canonical_state_schema": mod.STATE_SCHEMA,
        "compatible_active_pointer_schemas": ["FRANKENSTEIN2_ACTIVE_WORKPACKAGE_CLAIM/v1"],
        "active_state": "ACTIVE",
        "terminal_states": ["ACCEPTED", "FAILED_TERMINAL", "RETIRED_STALE", "SUPERSEDED"],
        "state_values": ["NOT_STARTED", "IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"],
    }


def build_root(root: Path) -> None:
    (root / "workpackages/claims").mkdir(parents=True)
    (root / "workpackages/active").mkdir(parents=True)
    (root / mod.CONTRACT_REL).write_text(json.dumps(contract()), encoding="utf-8")
    (root / mod.STATE_VIEW_V2_REL).write_text("{}", encoding="utf-8")
    state = {
        "schema": mod.STATE_SCHEMA,
        "canonical_repository": mod.REPO,
        "generation": 18,
        "workpackages": {
            "F2-WP-1200": {
                "status": "NOT_STARTED",
                "phase": 12,
                "title": "stale compatibility snapshot fixture",
                "evidence": [],
            }
        },
    }
    (root / "workpackages/STATE.json").write_text(json.dumps(state), encoding="utf-8")
    pointer = {
        "schema": "FRANKENSTEIN2_ACTIVE_WORKPACKAGE_CLAIM/v1",
        "workpackage_id": "F2-WP-1200",
        "generation": 1,
        "claim_id": "F2-WP-1200-G1-fixture",
        "worker_id": "fixture",
        "base_commit": "a" * 40,
        "state": "ACCEPTED",
    }
    (root / "workpackages/active/F2-WP-1200.json").write_text(json.dumps(pointer), encoding="utf-8")


class StateV2SuccessorTests(unittest.TestCase):
    def test_migrated_row_delegates_to_validated_v2_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            build_root(root)
            resolved = {
                "migrated_event_heads": {
                    "F2-WP-1200": "workpackages/state_events/F2-WP-1200/000001.json"
                }
            }
            with mock.patch.object(mod.state_v2, "resolve_effective_state", return_value=resolved) as resolver:
                result = mod.validate_repository(root)
            resolver.assert_called_once_with(root.resolve(), check_active=True)
            self.assertTrue(result["pass"])
            self.assertEqual(result["v2_migrated_workpackages_validated"], 1)
            self.assertEqual(result["v2_active_pointers_delegated"], 1)
            self.assertEqual(result["legacy_active_pointers_validated"], 0)
            self.assertEqual(result["validated"][0]["authority"], "STATE_EVENT_V2")
            self.assertEqual(result["runtime_credit_granted"], 0)
            self.assertFalse(result["whole_system_acceptance"])

    def test_v2_validation_failure_never_falls_back_to_legacy_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            build_root(root)
            with mock.patch.object(
                mod.state_v2,
                "resolve_effective_state",
                side_effect=mod.state_v2.ValidationError("stale active pointer blob"),
            ):
                with self.assertRaisesRegex(mod.ValidationError, "state-v2 validation failed"):
                    mod.validate_repository(root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
