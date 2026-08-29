import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from t7_semantic_claim import SemanticObjective


class GepardSemanticClaimTests(unittest.TestCase):
    def test_gepard_source_subject_aliases_share_stable_key(self):
        a = SemanticObjective.from_inputs(
            family="german tts benchmark",
            target_surface="source-only",
            subject="gepard-1.0",
            evidence_scope="source-pin",
            generation=1,
        )
        b = SemanticObjective.from_inputs(
            family="german tts benchmark",
            target_surface="source-only",
            subject="nineninesix-gepard-1.0",
            evidence_scope="source-pin",
            generation=1,
        )
        self.assertEqual(a.semantic_key(), b.semantic_key())
        self.assertEqual(
            a.semantic_key(),
            "ef3b55ef0d284815080231bd0e697e5cf704823df8a8d4efeefebd97f0e9a52d",
        )
        self.assertEqual(
            a.claim_path(),
            "research/local_voice/semantic_claims/ef3b55ef0d284815080231bd0e697e5cf704823df8a8d4efeefebd97f0e9a52d.json",
        )


if __name__ == "__main__":
    unittest.main()
