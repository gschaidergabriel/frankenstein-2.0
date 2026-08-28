from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "research" / "tool_intelligence" / "experiments" / "agentsight_e3_fixture_adapter.py"
SPEC = importlib.util.spec_from_file_location("agentsight_e3_fixture_adapter", MODULE_PATH)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)

FIXTURE = ROOT / "tests" / "fixtures" / "agentsight_schema_v1_mixed_provenance.json"
BASELINE = ROOT / "tests" / "fixtures" / "f2_native_telemetry_baseline.json"


class AgentSightE3FixtureTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads(FIXTURE.read_text())
        self.baseline = json.loads(BASELINE.read_text())

    def test_schema_version_fails_closed(self):
        bad = dict(self.snapshot)
        bad["schema_version"] = 2
        with self.assertRaises(MOD.SnapshotSchemaError):
            MOD.adapt_agentsight_snapshot(bad)

    def test_direct_and_native_provenance_are_not_collapsed(self):
        adapted = MOD.adapt_agentsight_snapshot(self.snapshot)
        tool_rows = [r for r in adapted["records"] if r["witness_kind"] == "tool_call"]
        classes = {r["evidence_class"] for r in tool_rows}
        self.assertIn("DIRECT_CAPTURE_WITNESS", classes)
        self.assertIn("AGENT_NATIVE_FALLBACK_WITNESS", classes)
        for row in adapted["records"]:
            self.assertEqual(row["causal_binding_status"], "UNBOUND_FOREIGN_ID")

    def test_sensitive_payloads_are_minimized(self):
        adapted = MOD.adapt_agentsight_snapshot(self.snapshot)
        serialized = json.dumps(adapted, sort_keys=True)
        self.assertNotIn("SUPERSECRET", serialized)
        self.assertNotIn("/secret/path", serialized)
        self.assertNotIn("/home/private", serialized)
        for forbidden in ("input", "output", "details", "argv", "command", "cwd", "target", "subject", "attributes"):
            self.assertNotIn(f'"{forbidden}"', serialized)

    def test_adapter_cannot_mint_authority_or_completion(self):
        adapted = MOD.adapt_agentsight_snapshot(self.snapshot)
        self.assertEqual(adapted["authority_scope"], "NONCANONICAL_OBSERVABILITY_WITNESS_ONLY")
        self.assertFalse(adapted["canonical_state_writer"])
        self.assertFalse(adapted["effect_gate_authority"])
        self.assertFalse(adapted["effect_journal_authority"])
        self.assertFalse(adapted["completion_authority"])
        for row in adapted["records"]:
            self.assertFalse(row["canonical_truth_credit"])
            self.assertFalse(row["effect_authority_credit"])
            self.assertFalse(row["completion_authority_credit"])

    def test_foreign_ids_are_not_relabelled_as_f2_causal_ids(self):
        adapted = MOD.adapt_agentsight_snapshot(self.snapshot)
        serialized = json.dumps(adapted, sort_keys=True)
        self.assertIn("foreign-tc-1", serialized)
        self.assertNotIn('"invocation_id"', serialized)
        self.assertNotIn('"causal_id"', serialized)
        self.assertNotIn('"tool_use_id"', serialized)

    def test_fixture_coverage_is_scoped_not_performance_claim(self):
        adapted = MOD.adapt_agentsight_snapshot(self.snapshot)
        coverage = MOD.compare_fixture_coverage(adapted, self.baseline)
        self.assertEqual(coverage["measurement_scope"], "FIXTURE_EVENT_KIND_COVERAGE_ONLY")
        self.assertIn("tool_call", coverage["shared_kinds"])
        self.assertIn("audit_event", coverage["incremental_kinds"])
        self.assertIn("process_node", coverage["incremental_kinds"])
        self.assertFalse(coverage["capture_overhead_measured"])
        self.assertFalse(coverage["latency_overhead_measured"])
        self.assertFalse(coverage["privilege_requirement_runtime_tested"])


if __name__ == "__main__":
    unittest.main()
