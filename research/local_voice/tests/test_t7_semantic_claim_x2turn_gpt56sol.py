import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from t7_semantic_claim import SemanticObjective


class X2TurnSemanticClaimTests(unittest.TestCase):
    def test_x2_turn_source_subject_aliases_share_stable_key(self):
        aliases = (
            "x2-turn-4b",
            "x2-turn-4b-0812",
            "x-square-robot/X2-Turn-4B-0812",
        )
        objectives = [
            SemanticObjective.from_inputs(
                family="german turn controller benchmark",
                target_surface="source-only",
                subject=subject,
                evidence_scope="source-pin",
                generation=1,
            )
            for subject in aliases
        ]
        keys = {objective.semantic_key() for objective in objectives}
        self.assertEqual(
            keys,
            {"d581486a8b8721b4c9fb9c2ea3990ddc1f783a03da7fb920419893f5d6ba0e42"},
        )
        self.assertEqual(
            objectives[0].claim_path(),
            "research/local_voice/semantic_claims/d581486a8b8721b4c9fb9c2ea3990ddc1f783a03da7fb920419893f5d6ba0e42.json",
        )
        self.assertEqual(objectives[0].subject, "X2_TURN_4B_0812")


if __name__ == "__main__":
    unittest.main()
