import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from t7_semantic_claim import SemanticObjective


class Audio8SemanticClaimTests(unittest.TestCase):
    def test_audio8_01b_onnx_aliases_converge_on_existing_canonical_key(self):
        aliases = [
            "audio8-tts-0.1b-onnx-int8",
            "audio8-ai-audio8-tts-0.1b-onnx-int8",
            "audio8-tts-preview-0.1b-onnx-int8",
        ]
        keys = {
            SemanticObjective.from_inputs(
                family="german tts benchmark",
                target_surface="source-only",
                subject=subject,
                evidence_scope="source-pin",
                generation=1,
            ).semantic_key()
            for subject in aliases
        }
        self.assertEqual(
            keys,
            {"6798470b87f53df7caa51a83b85fac09e813028a7359c52685e7ecf879d8a1a3"},
        )

    def test_audio8_01b_is_distinct_from_audio8_06b(self):
        small = SemanticObjective.from_inputs(
            family="german tts benchmark",
            target_surface="source-only",
            subject="audio8-tts-0.1b-onnx-int8",
            evidence_scope="source-pin",
            generation=1,
        )
        large = SemanticObjective.from_inputs(
            family="german tts benchmark",
            target_surface="source-only",
            subject="audio8-tts-0.6b",
            evidence_scope="source-pin",
            generation=1,
        )
        self.assertNotEqual(small.semantic_key(), large.semantic_key())
        self.assertNotEqual(small.canonical_object()["subject"], large.canonical_object()["subject"])


if __name__ == "__main__":
    unittest.main()
