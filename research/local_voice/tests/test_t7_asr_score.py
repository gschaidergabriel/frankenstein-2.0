import importlib.util
import pathlib
import unittest

TOOL = pathlib.Path(__file__).parents[1] / "tools" / "t7_asr_score.py"
spec = importlib.util.spec_from_file_location("t7_asr_score", TOOL)
score = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(score)


class Trigger7AsrScoreTests(unittest.TestCase):
    def test_perfect_transcript_term_and_latency(self):
        result = score.score_record({
            "utterance_id": "u1",
            "reference": "Qwen3.5-4B läuft lokal.",
            "hypothesis": "Qwen3.5-4B läuft lokal",
            "technical_terms": ["Qwen3.5-4B"],
            "user_speech_end_ns": 1_000_000_000,
            "asr_final_ns": 1_150_000_000,
            "partials": ["Qwen", "Qwen3.5-4B läuft lokal"],
        })
        self.assertEqual(result["wer"], 0.0)
        self.assertEqual(result["technical_term_matches"], 1)
        self.assertEqual(result["finalization_latency_ms"], 150.0)

    def test_edit_metrics_detect_substitution(self):
        result = score.score_record({
            "utterance_id": "u1",
            "reference": "rechte Hand",
            "hypothesis": "rechter Hand",
        })
        self.assertEqual(result["word_edits"], 1)
        self.assertAlmostEqual(result["wer"], 0.5)
        self.assertGreater(result["cer"], 0.0)

    def test_corpus_comparability_fails_closed(self):
        report = score.build_report([
            {"utterance_id": "1", "reference": "a", "hypothesis": "a", "candidate_id": "A"},
            {"utterance_id": "1", "reference": "a", "hypothesis": "a", "candidate_id": "B"},
            {"utterance_id": "2", "reference": "b", "hypothesis": "b", "candidate_id": "B"},
        ])
        self.assertFalse(report["corpus_comparability"]["identical_corpus"])

    def test_causal_latency_inversion_is_rejected(self):
        with self.assertRaises(ValueError):
            score.validate_record({
                "utterance_id": "x",
                "reference": "a",
                "hypothesis": "a",
                "user_speech_end_ns": 5,
                "asr_final_ns": 4,
            }, 1)

    def test_partial_prefix_regression_is_counted(self):
        result = score.score_record({
            "utterance_id": "u",
            "reference": "ich gehe nach hause",
            "hypothesis": "ich gehe nach hause",
            "partials": ["ich gehe", "ich", "ich gehe nach hause"],
        })
        self.assertEqual(result["partial_prefix_regressions"], 1)


if __name__ == "__main__":
    unittest.main()
