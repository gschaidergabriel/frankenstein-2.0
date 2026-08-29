import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from t7_semantic_claim import SemanticObjective


class ChatterboxSemanticClaimTests(unittest.TestCase):
    def test_chatterbox_multilingual_v3_alias_is_precise_and_stable(self):
        aliases = [
            "chatterbox-multilingual-v3",
            "resembleai-chatterbox-multilingual-v3",
            "chatterbox-multilingual-v3-500m",
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
        self.assertEqual(keys, {"361e9713e4e7b14e2361379e8120ad0199c3a0145cb59263baea5f4e3c7ff512"})


if __name__ == "__main__":
    unittest.main()
