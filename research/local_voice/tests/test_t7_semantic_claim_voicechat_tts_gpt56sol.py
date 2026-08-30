import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from t7_semantic_claim import SemanticObjective


class VoiceChatTTSSemanticClaimTests(unittest.TestCase):
    def test_voicechat_tts_source_subject_aliases_share_stable_key(self):
        aliases = [
            "voicechat-tts",
            "nvidia-voicechat-tts",
            "voicechat-tts-2026",
        ]
        keys = []
        for subject in aliases:
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
            "a8ab9e5ba922f370e175574d8bea6659a8a2af2432cd87e3f708709518cd13dd",
        )
        self.assertEqual(
            SemanticObjective.from_inputs(
                family="german tts benchmark",
                target_surface="source-only",
                subject="voicechat-tts",
                evidence_scope="source-pin",
                generation=1,
            ).claim_path(),
            "research/local_voice/semantic_claims/a8ab9e5ba922f370e175574d8bea6659a8a2af2432cd87e3f708709518cd13dd.json",
        )


if __name__ == "__main__":
    unittest.main()
