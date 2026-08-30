import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from t7_semantic_claim import SemanticObjective


class VoxCPM2SemanticClaimTests(unittest.TestCase):
    def test_voxcpm2_source_subject_aliases_share_stable_key(self):
        keys = []
        for subject in ("voxcpm2", "voxcpm2-2b", "openbmb-voxcpm2"):
            objective = SemanticObjective.from_inputs(
                family="german tts benchmark",
                target_surface="source-only",
                subject=subject,
                evidence_scope="source-pin",
                generation=1,
            )
            keys.append(objective.semantic_key())
        self.assertEqual(len(set(keys)), 1)
        self.assertEqual(
            keys[0],
            "2e877d0a87923c052e1bdc04434dc859e017c3114f63ba0c8ec9f76e72b3eaea",
        )
        self.assertEqual(
            SemanticObjective.from_inputs(
                family="german tts benchmark",
                target_surface="source-only",
                subject="voxcpm2",
                evidence_scope="source-pin",
                generation=1,
            ).claim_path(),
            "research/local_voice/semantic_claims/2e877d0a87923c052e1bdc04434dc859e017c3114f63ba0c8ec9f76e72b3eaea.json",
        )


if __name__ == "__main__":
    unittest.main()
