import importlib.util
import pathlib
import sys
import unittest


MODULE = pathlib.Path(__file__).resolve().parents[1] / "tools" / "t4_voice_virtual_sink_cancel_readback.py"
spec = importlib.util.spec_from_file_location("t4_voice_virtual_sink_cancel_readback_ci", MODULE)
probe = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


class Trigger4VirtualSinkCancelReadbackTests(unittest.TestCase):
    def test_software_reference_bounds_inflight_and_rejects_late_old_generation(self):
        result = probe.run("software")
        self.assertTrue(result["pass"])
        self.assertEqual(result["schema"], "F2_T4_VOICE_VIRTUAL_SINK_CANCEL_READBACK/v2")
        self.assertEqual(result["execution_scope"], "REPOSITORY_SIMULATION_ONLY")
        self.assertFalse(result["late_old_generation_accepted"])
        self.assertEqual(result["stale_chunks_rejected"], 1)
        self.assertGreater(result["pre_samples_before_new_generation"], 0)
        self.assertEqual(result["old_inflight_samples_after_new_generation"], 0)
        self.assertEqual(result["late_old_samples_observed"], 0)
        self.assertGreater(result["new_generation_samples_observed"], 0)
        self.assertLessEqual(
            result["observed_old_audio_before_new_generation_ms"],
            result["declared_pre_cancel_inflight_bound_ms"],
        )
        self.assertEqual(result["declared_pre_cancel_inflight_bound_ms"], 30)
        self.assertEqual(result["measured_credit"]["virtual_sink_output_consumption_control"], 1)
        # Software reference cannot mint target monitor-readback credit.
        self.assertEqual(result["measured_credit"]["bounded_inflight_old_audio_monitor_readback"], 0)
        for key in (
            "physical_speaker",
            "physical_microphone",
            "human_heard_output",
            "acoustic_playback_readback",
            "whole_voice_e2e",
            "gwt_jspace",
            "effect",
            "unifieddb_write",
            "training",
            "whole_product",
        ):
            self.assertEqual(result["measured_credit"][key], 0)

    def test_generation_fence_rejects_wrong_session_and_old_generation(self):
        fence = probe.GenerationFence("session-a")
        self.assertTrue(fence.admit(probe.Chunk("session-a", "p0", 1, 0, b"a")))
        self.assertFalse(fence.admit(probe.Chunk("session-b", "p1", 1, 0, b"b")))
        old, new = fence.cancel()
        self.assertEqual((old, new), (1, 2))
        self.assertFalse(fence.admit(probe.Chunk("session-a", "p2", 1, 1, b"c")))
        self.assertTrue(fence.admit(probe.Chunk("session-a", "p3", 2, 0, b"d")))
        self.assertEqual(fence.rejected, 2)

    def test_pulse_mode_source_keeps_physical_credit_zero(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("module-null-sink", source)
        self.assertIn('"physical_speaker": 0', source)
        self.assertIn('"human_heard_output": 0', source)
        self.assertIn('"whole_product": 0', source)
        self.assertIn("INFLIGHT_BOUND_MS", source)


if __name__ == "__main__":
    unittest.main()
