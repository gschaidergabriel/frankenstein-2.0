from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


SEMANTIC_KEY = "29bf28d8f3b3cec294de2126c002b90fedbacdec961e823503c2c4d8f11ddbdc"
EXPECTED_BLOBS = {
    "src/frankenstein2/voice_contract.py": "ad639b02ea69771014a2cad5b38103036b35bdfb",
    "src/frankenstein2/voice_packet_cortex.py": "bdecfd082fc9a88876e8cbcca8988d20b866da29",
    "src/frankenstein2/voice_packet_cortex_recovery.py": "5849a396ac7de00a905b39c3633e82d8def04b10",
    "src/frankenstein2/voice_heard_result_reentry.py": "9f6ae00bc2c8b589bd49ded03132e1faacd803c2",
}


class Trigger7ComposedVoiceSliceG4Test(unittest.TestCase):
    def test_composed_barge_restart_heard_reentry_chain(self) -> None:
        root = Path(__file__).resolve().parents[3]
        claim_path = root / "research/local_voice/semantic_claims" / f"{SEMANTIC_KEY}.json"
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        self.assertEqual(claim["semantic_key"], SEMANTIC_KEY)
        self.assertEqual(claim["semantic_objective"]["generation"], 4)
        self.assertEqual(
            claim["semantic_objective"]["family"],
            "PACKET_CORTEX_CAUSAL_TURN_IDENTITY_FALSIFIER",
        )
        self.assertEqual(claim["semantic_objective"]["evidence_scope"], "CANDIDATE_FALSIFIER")

        for path, expected in EXPECTED_BLOBS.items():
            observed = subprocess.check_output(
                ["git", "rev-parse", f"HEAD:{path}"], cwd=root, text=True
            ).strip()
            self.assertEqual(observed, expected, f"composed Voice-Slice source subject changed: {path}")

        tool = root / "research/local_voice/tools/falsify_composed_voice_slice_barge_restart_heard_reentry.py"
        env = dict(os.environ)
        src = str(root / "src")
        env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        proc = subprocess.run(
            [sys.executable, str(tool)],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertTrue(proc.stdout.strip(), msg=proc.stderr)
        report = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(
            report["schema"], "F2_T7_COMPOSED_PACKET_VOICE_SLICE_DIAGNOSTIC/v1"
        )
        self.assertEqual(report["semantic_key"], SEMANTIC_KEY)
        self.assertEqual(report["result"], "NO_COUNTEREXAMPLE", msg=json.dumps(report, sort_keys=True))
        self.assertEqual(proc.returncode, 0, msg=json.dumps(report, sort_keys=True))

        obs = report["observations"]
        self.assertEqual(obs["hold_policy_intent"], "WAIT")
        self.assertEqual(obs["presence_state"], "PRESENT_INTERRUPTIBLE")
        self.assertEqual(obs["interrupted_output_state"], "interrupted")
        self.assertEqual(obs["interrupted_heard_fraction"], 0.25)
        self.assertFalse(obs["interrupted_commit_eligible"])
        self.assertTrue(obs["late_tool_rejected_pre_restart"])
        self.assertTrue(obs["late_tool_rejected_post_restart"])
        self.assertEqual(obs["restart_reentry_event_count"], 1)
        self.assertEqual(obs["durable_output_packet_ids"], ["output-b-0"])
        self.assertTrue(obs["closed_restart_replay_idempotent"])

        latency = obs["latency_ms"]
        self.assertEqual(latency["asr_from_speech_start_ms"], 30)
        self.assertEqual(latency["decision_after_asr_ms"], 60)
        self.assertEqual(latency["first_output_after_decision_ms"], 10)
        self.assertEqual(latency["playback_after_first_output_ms"], 10)
        self.assertEqual(latency["speech_to_playback_ms"], 110)

        zeros = report["explicit_zero_credit"]
        for key in (
            "acoustic",
            "asr_runtime",
            "tts_runtime",
            "target_runtime",
            "vps_runtime",
            "physical_audio",
            "physical_presence",
            "unifieddb_write",
            "semantic_gwt_jspace",
            "effect",
            "training",
            "whole_voice_e2e",
            "whole_product",
        ):
            self.assertEqual(zeros[key], 0, key)

        print("T7_COMPOSED_VOICE_SLICE_G4_REPORT=" + json.dumps(report, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    unittest.main()
