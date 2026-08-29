import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "tools" / "validate_wp002_projection_v2.py"
spec = importlib.util.spec_from_file_location("wp002_projection_v2", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
assert spec.loader is not None
spec.loader.exec_module(mod)


class WP002ProjectionV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "workpackages/active").mkdir(parents=True)
        (self.root / "workpackages/state_events").mkdir(parents=True)
        (self.root / "workpackages/reconciliations/F2-WP-900").mkdir(parents=True)
        (self.root / "workpackages/STATE_VIEW_CONTRACT_V2.json").write_text(
            json.dumps({
                "schema": "FRANKENSTEIN2_WORKPACKAGE_STATE_VIEW_CONTRACT/v2",
                "authority_order": ["event", "snapshot"],
            }),
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _state(self, rows):
        (self.root / "workpackages/STATE.json").write_text(
            json.dumps({
                "schema": "FRANKENSTEIN2_WORKPACKAGE_STATE/v1",
                "generation": 15,
                "workpackages": rows,
            }),
            encoding="utf-8",
        )

    def _pointer(self, wp, state, *, reconciliation_ref=None):
        value = {
            "schema": "FRANKENSTEIN2_ACTIVE_WORKPACKAGE_CLAIM/v1",
            "workpackage_id": wp,
            "generation": 1,
            "claim_id": f"{wp}-G1-test",
            "state": state,
        }
        if reconciliation_ref is not None:
            value["reconciliation_ref"] = reconciliation_ref
        (self.root / f"workpackages/active/{wp}.json").write_text(
            json.dumps(value), encoding="utf-8"
        )

    def _reconciliation(self, *, broader_status):
        rel = "workpackages/reconciliations/F2-WP-900/1-test.json"
        value = {
            "schema": "FRANKENSTEIN2_WORKPACKAGE_RECONCILIATION/v1",
            "workpackage_id": "F2-WP-900",
            "generation": 1,
            "claim_id": "F2-WP-900-G1-test",
            "terminal_state": "ACCEPTED",
            "broader_workpackage_status": broader_status,
            "whole_system_acceptance": False,
        }
        (self.root / rel).write_text(json.dumps(value), encoding="utf-8")
        return rel

    def test_active_pointer_absent_from_effective_view_fails_closed(self):
        self._state({})
        self._pointer("F2-WP-900", "ACTIVE")
        with self.assertRaisesRegex(mod.ProjectionValidationError, "absent from effective"):
            mod.validate_projection(self.root)

    def test_active_pointer_cannot_project_not_started(self):
        self._state({
            "F2-WP-900": {"status": "NOT_STARTED", "phase": 9, "title": "x", "evidence": []}
        })
        self._pointer("F2-WP-900", "ACTIVE")
        with self.assertRaisesRegex(mod.ProjectionValidationError, "cannot project as NOT_STARTED"):
            mod.validate_projection(self.root)

    def test_active_pointer_may_project_in_progress(self):
        self._state({
            "F2-WP-900": {"status": "IN_PROGRESS", "phase": 9, "title": "x", "evidence": []}
        })
        self._pointer("F2-WP-900", "ACTIVE")
        result = mod.validate_projection(self.root)
        self.assertEqual(result["checked_active_pointers"], ["F2-WP-900"])
        self.assertEqual(result["runtime_credit"], 0)
        self.assertFalse(result["whole_system_acceptance"])

    def test_accepted_pointer_without_explicit_broader_status_requires_accepted_at_scope(self):
        self._state({
            "F2-WP-900": {"status": "IN_PROGRESS", "phase": 9, "title": "x", "evidence": []}
        })
        self._pointer("F2-WP-900", "ACCEPTED")
        with self.assertRaisesRegex(mod.ProjectionValidationError, "requires broad ACCEPTED_AT_SCOPE"):
            mod.validate_projection(self.root)

    def test_accepted_pointer_accepts_accepted_at_scope_fallback(self):
        self._state({
            "F2-WP-900": {"status": "ACCEPTED_AT_SCOPE", "phase": 9, "title": "x", "evidence": []}
        })
        self._pointer("F2-WP-900", "ACCEPTED")
        result = mod.validate_projection(self.root)
        self.assertEqual(result["checked_count"], 1)

    def test_scoped_acceptance_may_explicitly_keep_broader_workpackage_in_progress(self):
        self._state({
            "F2-WP-900": {"status": "IN_PROGRESS", "phase": 9, "title": "x", "evidence": []}
        })
        reconciliation_ref = self._reconciliation(broader_status="IN_PROGRESS")
        self._pointer("F2-WP-900", "ACCEPTED", reconciliation_ref=reconciliation_ref)
        result = mod.validate_projection(self.root)
        self.assertEqual(result["checked_count"], 1)

    def test_explicit_broader_status_mismatch_fails_closed(self):
        self._state({
            "F2-WP-900": {"status": "ACCEPTED_AT_SCOPE", "phase": 9, "title": "x", "evidence": []}
        })
        reconciliation_ref = self._reconciliation(broader_status="IN_PROGRESS")
        self._pointer("F2-WP-900", "ACCEPTED", reconciliation_ref=reconciliation_ref)
        with self.assertRaisesRegex(mod.ProjectionValidationError, "requires broad IN_PROGRESS"):
            mod.validate_projection(self.root)


if __name__ == "__main__":
    unittest.main()
