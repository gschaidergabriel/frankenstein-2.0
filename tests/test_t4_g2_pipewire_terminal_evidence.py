#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "trigger4/tools/local_voice/g2_pipewire_evidence.py"
spec = importlib.util.spec_from_file_location("g2_pipewire_evidence_test", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


SETTINGS = """Found \"settings\" metadata 30\nupdate: id:0 key:'clock.rate' value:'48000' type:''\nupdate: id:0 key:'clock.quantum' value:'1024' type:''\n"""


def pw_object(object_id, serial, name, media_class):
    return {
        "id": object_id,
        "info": {
            "props": {
                "object.serial": serial,
                "node.name": name,
                "node.description": name,
                "media.class": media_class,
            }
        },
    }


class Trigger4G2TerminalEvidenceTests(unittest.TestCase):
    def test_bound_is_deterministic_and_predeclared_from_clock(self):
        receipt = mod.derive_bound_receipt(SETTINGS)
        self.assertEqual(receipt["clock_rate_hz"], 48000)
        self.assertEqual(receipt["clock_quantum_frames"], 1024)
        self.assertEqual(receipt["policy_quanta"], 16)
        self.assertAlmostEqual(receipt["derived_max_inflight_ms"], 341.334, places=3)
        mod.validate_bound_receipt(receipt, SETTINGS, receipt["derived_max_inflight_ms"])

    def test_bound_rejects_posthoc_or_graph_mismatch(self):
        receipt = mod.derive_bound_receipt(SETTINGS)
        with self.assertRaisesRegex(ValueError, "SUPPLIED_VALUE_MISMATCH"):
            mod.validate_bound_receipt(receipt, SETTINGS, 250.0)
        changed = SETTINGS.replace("1024", "512")
        with self.assertRaisesRegex(ValueError, "CURRENT_GRAPH_MISMATCH"):
            mod.validate_bound_receipt(receipt, changed, receipt["derived_max_inflight_ms"])

    def test_exact_sink_monitor_identity_and_cleanup(self):
        before = json.dumps([
            pw_object(41, 1001, "f2_voice_g2_sink", "Audio/Sink"),
            pw_object(42, 1002, "f2_voice_g2_sink.monitor", "Audio/Source"),
            pw_object(50, 2000, "unrelated", "Audio/Sink"),
        ])
        binding = mod.resolve_pipewire_objects(before, "f2_voice_g2_sink", "f2_voice_g2_sink.monitor")
        self.assertEqual(binding["sink"]["object_serial"], "1001")
        self.assertEqual(binding["monitor"]["object_serial"], "1002")
        after = json.dumps([pw_object(50, 2000, "unrelated", "Audio/Sink")])
        self.assertTrue(mod.identities_absent(after, binding))
        self.assertFalse(mod.identities_absent(before, binding))

    def test_identity_fails_closed_on_ambiguity_or_missing_serial(self):
        ambiguous = json.dumps([
            pw_object(41, 1001, "f2_voice_g2_sink", "Audio/Sink"),
            pw_object(42, 1002, "f2_voice_g2_sink", "Audio/Sink"),
            pw_object(43, 1003, "f2_voice_g2_sink.monitor", "Audio/Source"),
        ])
        with self.assertRaisesRegex(ValueError, "SINK_IDENTITY_AMBIGUOUS"):
            mod.resolve_pipewire_objects(ambiguous, "f2_voice_g2_sink", "f2_voice_g2_sink.monitor")
        missing_serial = json.dumps([
            {"id": 41, "info": {"props": {"node.name": "f2_voice_g2_sink"}}},
            pw_object(43, 1003, "f2_voice_g2_sink.monitor", "Audio/Source"),
        ])
        with self.assertRaisesRegex(ValueError, "SERIAL_MISSING"):
            mod.resolve_pipewire_objects(missing_serial, "f2_voice_g2_sink", "f2_voice_g2_sink.monitor")


if __name__ == "__main__":
    unittest.main()
