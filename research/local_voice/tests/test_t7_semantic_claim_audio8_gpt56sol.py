import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from t7_semantic_claim import SemanticObjective


class Audio8SemanticClaimTests(unittest.TestCase):
    def test_audio8_tts_06b_alias_is_precise_and_stable(self):
        aliases = [
            "audio8-tts-0.6b",
            "audio8-ai-audio8-tts-0.6b",
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
        self.assertEqual(keys, {"934196a3a4dbd14cf0a709a3cb1e243d4b44c08af205547d83216b3e1097e3f5"})


if __name__ == "__main__":
    unittest.main()
