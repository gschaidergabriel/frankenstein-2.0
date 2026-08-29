import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from t7_semantic_claim import SemanticObjective


class CosyVoiceSemanticClaimTests(unittest.TestCase):
    def test_fun_cosyvoice3_subject_alias_is_precise_and_stable(self):
        aliases = [
            "fun-cosyvoice3-0.5b-2512",
            "cosyvoice3-0.5b-2512",
            "funaudiollm-fun-cosyvoice3-0.5b-2512",
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
        self.assertEqual(keys, {"27fc86f3259b409cb5188d5eb6d79e5e6244a6d8484537af0249a3ec88014c13"})


if __name__ == "__main__":
    unittest.main()
