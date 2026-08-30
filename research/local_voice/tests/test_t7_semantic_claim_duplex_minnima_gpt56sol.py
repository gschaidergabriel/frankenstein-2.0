import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from t7_semantic_claim import SemanticObjective


class DuplexMinnimaSemanticClaimTests(unittest.TestCase):
    def test_duplex_minnima_source_subject_aliases_share_stable_key(self):
        aliases = (
            "duplex-minnima",
            "eddiegulay/duplex-minnima",
            "turn-taker",
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
            {"669220eee0ca36ec75a3e8ef9d536c511e804b81eb7b9f91a15f6f47c0b2c7b8"},
        )
        self.assertEqual(
            objectives[0].claim_path(),
            "research/local_voice/semantic_claims/669220eee0ca36ec75a3e8ef9d536c511e804b81eb7b9f91a15f6f47c0b2c7b8.json",
        )
        self.assertEqual(objectives[0].subject, "DUPLEX_MINNIMA_CPP")


if __name__ == "__main__":
    unittest.main()
