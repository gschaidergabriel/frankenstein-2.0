#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import validate_workpackage_state as mod


IDENTITY = {
    "schema": mod.RECON_SCHEMA,
    "workpackage_id": "F2-WP-506",
    "generation": 4,
    "claim_id": "F2-WP-506-G4-test",
    "terminal_state": "ACCEPTED",
    "whole_system_acceptance": False,
}


def write_reconciliation(root: Path, rel: str, **extra) -> tuple[Path, dict]:
    value = dict(IDENTITY)
    value.update(extra)
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path, value


class ReconciliationChainTests(unittest.TestCase):
    def test_unique_append_only_leaf_is_selected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            external_rel = "workpackages/reconciliations/F2-WP-506/5-prior-generation.json"
            external = dict(IDENTITY)
            external["generation"] = 3
            external["claim_id"] = "F2-WP-506-G3-test"
            external_path = root / external_rel
            external_path.parent.mkdir(parents=True, exist_ok=True)
            external_path.write_text(json.dumps(external), encoding="utf-8")

            r6_rel = "workpackages/reconciliations/F2-WP-506/6-acceptance.json"
            r7_rel = "workpackages/reconciliations/F2-WP-506/7-correction.json"
            r6 = write_reconciliation(root, r6_rel, parent_reconciliation_ref=external_rel)
            r7 = write_reconciliation(root, r7_rel, parent_reconciliation_ref=r6_rel,
                                      reconciliation_class="POST_ACCEPTANCE_EVIDENCE_CORRECTION")

            selected = mod._select_terminal_reconciliation(root, [r6, r7], context="fixture")
            self.assertEqual(selected["reconciliation_class"], "POST_ACCEPTANCE_EVIDENCE_CORRECTION")

    def test_unlinked_same_identity_reconciliations_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parent_a = "workpackages/reconciliations/F2-WP-506/prior-a.json"
            parent_b = "workpackages/reconciliations/F2-WP-506/prior-b.json"
            for rel, generation in ((parent_a, 2), (parent_b, 3)):
                value = dict(IDENTITY)
                value["generation"] = generation
                value["claim_id"] = f"older-{generation}"
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value), encoding="utf-8")
            r1 = write_reconciliation(root, "workpackages/reconciliations/F2-WP-506/a.json",
                                      parent_reconciliation_ref=parent_a)
            r2 = write_reconciliation(root, "workpackages/reconciliations/F2-WP-506/b.json",
                                      parent_reconciliation_ref=parent_b)
            with self.assertRaisesRegex(mod.ValidationError, "unique append-only chain leaf"):
                mod._select_terminal_reconciliation(root, [r1, r2], context="fixture")

    def test_unknown_parent_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            r1_rel = "workpackages/reconciliations/F2-WP-506/a.json"
            r2_rel = "workpackages/reconciliations/F2-WP-506/b.json"
            r1 = write_reconciliation(root, r1_rel,
                                      parent_reconciliation_ref="workpackages/reconciliations/F2-WP-506/missing.json")
            r2 = write_reconciliation(root, r2_rel, parent_reconciliation_ref=r1_rel)
            with self.assertRaisesRegex(mod.ValidationError, "unknown parent"):
                mod._select_terminal_reconciliation(root, [r1, r2], context="fixture")

    def test_parent_cycle_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            r1_rel = "workpackages/reconciliations/F2-WP-506/a.json"
            r2_rel = "workpackages/reconciliations/F2-WP-506/b.json"
            r1 = write_reconciliation(root, r1_rel, parent_reconciliation_ref=r2_rel)
            r2 = write_reconciliation(root, r2_rel, parent_reconciliation_ref=r1_rel)
            with self.assertRaisesRegex(mod.ValidationError, "parent cycle"):
                mod._select_terminal_reconciliation(root, [r1, r2], context="fixture")


if __name__ == "__main__":
    unittest.main(verbosity=2)
