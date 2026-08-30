import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from t7_semantic_claim import SemanticObjective


class HuggingFaceSpeechToSpeechSemanticClaimTests(unittest.TestCase):
    def test_realtime_cascade_subject_aliases_share_stable_key(self):
        aliases = (
            "huggingface/speech-to-speech",
            "huggingface-speech-to-speech",
            "hf-speech-to-speech",
        )
        objectives = [
            SemanticObjective.from_inputs(
                family="full duplex german falsifier",
                target_surface="clay-direct-dev",
                subject=subject,
                evidence_scope="component-benchmark",
                generation=1,
            )
            for subject in aliases
        ]
        keys = {objective.semantic_key() for objective in objectives}
        self.assertEqual(
            keys,
            {"8c53f25ed47c458bb727dd4dc82f788241cee699e428c4d97401a965a4eb375e"},
        )
        self.assertEqual(
            objectives[0].claim_path(),
            "research/local_voice/semantic_claims/8c53f25ed47c458bb727dd4dc82f788241cee699e428c4d97401a965a4eb375e.json",
        )
        self.assertEqual(
            objectives[0].subject,
            "HUGGINGFACE_SPEECH_TO_SPEECH_REALTIME",
        )


if __name__ == "__main__":
    unittest.main()
