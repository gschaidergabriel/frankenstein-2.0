import importlib.util
from pathlib import Path
import sys
import unittest

MODULE = (
    Path(__file__).parents[1]
    / "research" / "local_voice" / "tools"
    / "t4_voice_virtual_sink_cancel_readback_g2.py"
)
spec = importlib.util.spec_from_file_location("t4_voice_virtual_sink_cancel_readback_g2", MODULE)
probe = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


class VoiceVirtualSinkCancelReadbackG2Tests(unittest.TestCase):
    def test_reference_queues_old_sentinel_before_cancel_then_proves_it_absent(self):
        result = probe.run("software")
        self.assertTrue(result["pass"])
        self.assertEqual(result["execution_scope"], "REPOSITORY_REFERENCE_ONLY")
        self.assertTrue(result["old_sentinel_queued_before_cancel"])
        self.assertTrue(result["generation_advanced_before_sink_cancel"])
        self.assertFalse(result["late_old_generation_accepted"])
        self.assertEqual(result["stale_chunks_rejected"], 1)
        self.assertEqual(result["old_sentinel_samples"], 0)
        self.assertEqual(result["new_sentinel_samples"], result["expected_new_sentinel_samples"])
        self.assertGreater(result["software_discarded_pending_bytes"], 0)

    def test_broken_cancel_that_keeps_pending_old_audio_is_product_negative(self):
        result = probe.run("software", software_cancel_discards_pending=False)
        self.assertFalse(result["pass"])
        self.assertEqual(result["failure_class"], "PRODUCT_NEGATIVE")
        self.assertTrue(result["old_sentinel_queued_before_cancel"])
        self.assertGreater(result["old_sentinel_samples"], 0)

    def test_generation_fence_is_session_bound_and_monotonic(self):
        fence = probe.GenerationFence("session-a")
        current = probe.Chunk("session-a", "p1", 1, 0, b"a")
        wrong_session = probe.Chunk("session-b", "p2", 1, 0, b"b")
        self.assertTrue(fence.admit(current))
        self.assertFalse(fence.admit(wrong_session))
        old, new, advanced_ns = fence.cancel_generation()
        self.assertEqual((old, new), (1, 2))
        self.assertGreater(advanced_ns, 0)
        self.assertFalse(fence.admit(current))
        self.assertTrue(fence.admit(probe.Chunk("session-a", "p3", 2, 0, b"c")))
        self.assertEqual(fence.rejected, 2)

    def test_reference_pass_cannot_mint_runtime_or_adjacent_voice_credit(self):
        result = probe.run("software")
        self.assertEqual(result["evidence"]["repository_reference_pass"], 1)
        self.assertEqual(result["evidence"]["pulse_virtual_sink_promotion_candidate"], 0)
        for key in (
            "target_runtime_credit_from_probe_alone",
            "producer_generation_cancel",
            "true_streaming_partial_asr",
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
            self.assertEqual(result["evidence"][key], 0, key)

    def test_pulse_path_is_virtual_sink_only_and_avoids_drain_semantics(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("PIPEWIRE_PULSE_NULL_SINK", source)
        self.assertIn("module-null-sink", source)
        self.assertIn("SIGTERM closes", source)
        self.assertNotIn("snd_pcm_drain", source)
        self.assertIn("producer-side TTS cancel", source)
        self.assertIn("reserve physical speaker/mic/human-heard for S4", source)


if __name__ == "__main__":
    unittest.main()
