import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "t7_voice_receipt.py"
spec = importlib.util.spec_from_file_location("t7_voice_receipt", TOOL)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class VoiceReceiptTests(unittest.TestCase):
    def _records(self):
        return [
            {
                "kind": "run",
                "schema_version": 1,
                "run_id": "r1",
                "language": "de",
                "runtime_mode": "LOCAL_SOLO",
                "network_counters": {
                    "outbound_model_api_calls": 0,
                    "outbound_asr_api_calls": 0,
                    "outbound_tts_api_calls": 0,
                },
            },
            {
                "kind": "turn",
                "schema_version": 1,
                "turn_id": "t1",
                "scenario": "short_answer",
                "timestamps_ns": {
                    "user_speech_end": 1_000_000_000,
                    "asr_final": 1_100_000_000,
                    "inference_request": 1_110_000_000,
                    "inference_first_token": 1_210_000_000,
                    "first_speakable_clause": 1_260_000_000,
                    "tts_request": 1_270_000_000,
                    "tts_first_audio_ready": 1_350_000_000,
                    "first_audio_played": 1_380_000_000,
                },
                "flags": {},
            },
        ]

    def test_summary_local_solo(self):
        out = mod.summarize(self._records())
        self.assertEqual(out["turn_count"], 1)
        self.assertEqual(out["metrics_ms"]["speech_end_to_first_audio_ms"]["p50"], 380.0)
        self.assertTrue(out["local_solo_zero_external_inference"])
        self.assertTrue(out["causal_voice_commit_ok"])

    def test_barge_in_violation_is_visible(self):
        records = self._records()
        records[1]["timestamps_ns"].update({
            "barge_in_detected": 1_500_000_000,
            "playback_stopped": 1_540_000_000,
        })
        records[1]["flags"] = {"barge_in_expected": True, "generation_cancelled": False}
        out = mod.summarize(records)
        self.assertEqual(out["metrics_ms"]["barge_in_to_stop_ms"]["p50"], 40.0)
        self.assertEqual(out["violations"]["barge_in_without_generation_cancel"], 1)
        self.assertFalse(out["causal_voice_commit_ok"])

    def test_rejects_timestamp_inversion(self):
        records = self._records()
        records[1]["timestamps_ns"]["first_audio_played"] = 900_000_000
        with self.assertRaises(mod.ReceiptError):
            mod.summarize(records)

    def test_local_solo_external_call_fails_offline_gate(self):
        records = self._records()
        records[0]["network_counters"]["outbound_model_api_calls"] = 1
        out = mod.summarize(records)
        self.assertFalse(out["local_solo_zero_external_inference"])


if __name__ == "__main__":
    unittest.main()
