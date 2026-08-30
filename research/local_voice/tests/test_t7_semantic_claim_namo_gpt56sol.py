import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from t7_semantic_claim import SemanticObjective


class NamoSemanticClaimTests(unittest.TestCase):
    def test_namo_multilingual_aliases_are_precise_and_stable(self):
        aliases = [
            "namo-turn-detector-v1-multilingual",
            "namo-v1-multilingual",
            "videosdk-live-namo-turn-detector-v1-multilingual",
        ]
        keys = {
            SemanticObjective.from_inputs(
                family="german turn controller benchmark",
                target_surface="source-only",
                subject=subject,
                evidence_scope="source-pin",
                generation=1,
            ).semantic_key()
            for subject in aliases
        }
        self.assertEqual(keys, {"ef624c13104dfa4990918906f59104fd558197c8842f60ace298f23567237c6f"})


if __name__ == "__main__":
    unittest.main()
