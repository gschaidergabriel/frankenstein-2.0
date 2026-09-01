from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


SEMANTIC_KEY = "ec05977feabb70523bee9f6cf7cd99b0e83f80a4a34a6632f4ff8e2f9102f86f"
EXPECTED_CORTEX_BLOB = "bdecfd082fc9a88876e8cbcca8988d20b866da29"
EXPECTED_RECOVERY_BLOB = "5849a396ac7de00a905b39c3633e82d8def04b10"


class Trigger7RecoveryCompositionRevalidationTest(unittest.TestCase):
    def test_repaired_current_subject_closes_rcomp_matrix(self) -> None:
        root = Path(__file__).resolve().parents[3]
        claim_path = root / "research/local_voice/semantic_claims" / f"{SEMANTIC_KEY}.json"
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        self.assertEqual(claim["semantic_key"], SEMANTIC_KEY)
        self.assertEqual(claim["semantic_objective"]["generation"], 3)
        self.assertEqual(claim["semantic_objective"]["evidence_scope"], "CANDIDATE_FALSIFIER")

        cortex_blob = subprocess.check_output(
            ["git", "rev-parse", "HEAD:src/frankenstein2/voice_packet_cortex.py"],
            cwd=root,
            text=True,
        ).strip()
        recovery_blob = subprocess.check_output(
            ["git", "rev-parse", "HEAD:src/frankenstein2/voice_packet_cortex_recovery.py"],
            cwd=root,
            text=True,
        ).strip()
        self.assertEqual(cortex_blob, EXPECTED_CORTEX_BLOB, "packet-cortex subject changed after claim")
        self.assertEqual(recovery_blob, EXPECTED_RECOVERY_BLOB, "recovery subject changed after claim")

        tool = root / "research/local_voice/tools/falsify_voice_packet_cortex_recovery_commit_cancel_composition.py"
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
        line = proc.stdout.strip().splitlines()[-1]
        report = json.loads(line)
        self.assertEqual(report["schema"], "F2_T7_RECOVERY_COMMIT_CANCEL_COMPOSITION_DIAGNOSTIC/v1")
        self.assertEqual(report["result"], "NO_COUNTEREXAMPLE", msg=json.dumps(report, sort_keys=True))
        self.assertEqual(proc.returncode, 0, msg=json.dumps(report, sort_keys=True))
        self.assertEqual(report["failed_closed_probe_ids"], [])
        self.assertEqual(len(report["cases"]), 6)
        self.assertTrue(all(case["fail_closed"] for case in report["cases"]), msg=json.dumps(report, sort_keys=True))
        self.assertEqual(report["explicit_zero_credit"]["whole_voice_e2e"], 0)
        self.assertEqual(report["explicit_zero_credit"]["whole_product"], 0)
        print("T7_RECOVERY_REVALIDATION_REPORT=" + json.dumps(report, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    unittest.main()
