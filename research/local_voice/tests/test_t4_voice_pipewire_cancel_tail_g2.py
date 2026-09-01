import importlib.util
from array import array
import pathlib
import sys
import unittest


MODULE = pathlib.Path(__file__).resolve().parents[1] / "tools" / "t4_voice_pipewire_cancel_tail_g2.py"
spec = importlib.util.spec_from_file_location("t4_voice_pipewire_cancel_tail_g2", MODULE)
probe = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


def pcm(values):
    data = array("h", values)
    if sys.byteorder != "little":
        data.byteswap()
    return data.tobytes()


def waveform(sample_rate=1000, samples=1200):
    # Deterministic nonperiodic signed-16 fixture; not runtime/acoustic evidence.
    value = 137
    out = []
    for index in range(samples):
        value = (value * 109 + 1021 + index * 17) & 0x7FFF
        sample = value - 16384
        if sample == 0:
            sample = 1
        out.append(sample)
    return pcm(out)


class Trigger4PipeWireCancelTailAnalysisTests(unittest.TestCase):
    def test_control_alignment_prefers_exact_pcm_identity(self):
        source = waveform()
        capture = pcm([0] * 123) + source + pcm([0] * 200)
        alignment = probe.align_pcm(source, capture, 1000)
        self.assertTrue(alignment.valid)
        self.assertEqual(alignment.method, "EXACT_PCM_SUBSTRING")
        self.assertEqual(alignment.offset_samples, 123)
        self.assertEqual(alignment.score, 1.0)
        self.assertEqual(alignment.error_bound_ms, 0.0)

    def test_cancel_tail_measures_already_admitted_old_waveform_then_quiet(self):
        source = waveform(samples=1200)
        source_samples = probe._samples(source)
        # Monitor sees 100 samples of latency, then 520 samples of the old packet,
        # then a long post-cancel quiet interval.  This is deliberately different
        # from the obsolete false-green sentinel that was offered only after the fence.
        capture = pcm([0] * 100 + source_samples[:520] + [0] * 500)
        tail = probe.measure_cancel_tail(
            source,
            capture,
            source_offset_samples=100,
            sample_rate=1000,
            cancel_capture_sample=400,
            frame_ms=20,
            corr_threshold=0.94,
        )
        self.assertTrue(tail.valid)
        self.assertIsNotNone(tail.last_correlated_capture_sample)
        self.assertGreater(tail.cancel_to_last_old_sample_ms, 0.0)
        self.assertGreaterEqual(tail.post_bound_quiet_ms, probe.MIN_POST_BOUND_QUIET_MS)
        self.assertGreater(tail.matched_frames, 0)

    def test_cancel_tail_fails_closed_when_old_waveform_cannot_be_bound(self):
        source = waveform(samples=1200)
        capture = pcm([0] * 1200)
        tail = probe.measure_cancel_tail(
            source,
            capture,
            source_offset_samples=100,
            sample_rate=1000,
            cancel_capture_sample=400,
        )
        self.assertFalse(tail.valid)
        self.assertEqual(tail.reason, "old_waveform_not_bound")

    def test_alignment_rejects_unrelated_nonzero_monitor_data(self):
        source = waveform(samples=1200)
        other = waveform(samples=1200)[::-1]
        alignment = probe.align_pcm(source, other, 1000)
        self.assertFalse(alignment.valid)
        self.assertIsNone(alignment.offset_samples)

    def test_scope_constants_do_not_offer_physical_credit(self):
        source = MODULE.read_text(encoding="utf-8")
        for literal in (
            '"physical_microphone": 0',
            '"physical_speaker": 0',
            '"human_heard_output": 0',
            '"whole_voice_e2e": 0',
            '"whole_product": 0',
            '"gwt_jspace": 0',
            '"effect": 0',
            '"unifieddb_write": 0',
            '"training": 0',
        ):
            self.assertIn(literal, source)
        self.assertIn("F2_EXTERNAL_INFERENCE_API_CALLS", source)
        self.assertIn("F2_SUBJECT_SHA", source)
        self.assertIn("cancel_for_barge_in", source)


if __name__ == "__main__":
    unittest.main()
