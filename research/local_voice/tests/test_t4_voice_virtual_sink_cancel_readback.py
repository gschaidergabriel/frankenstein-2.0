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
    def test_software_reference_rejects_stale_generation_and_preserves_zero_credit(self):
        result = probe.run("software")
        self.assertTrue(result["pass"])
        self.assertEqual(result["classification"], "CANDIDATE_FALSIFIER_VIRTUAL_SINK_ONLY")
        self.assertEqual(result["execution_scope"], "REPOSITORY_SIMULATION_ONLY")
        self.assertFalse(result["late_old_generation_accepted"])
        self.assertEqual(result["stale_chunks_rejected"], 1)
        self.assertEqual(result["old_sentinel_exact_occurrences"], 0)
        self.assertEqual(result["new_sentinel_exact_occurrences"], 1)
        self.assertEqual(result["measured_credit"]["virtual_sink_output_consumption_control"], 1)
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


if __name__ == "__main__":
    unittest.main()
