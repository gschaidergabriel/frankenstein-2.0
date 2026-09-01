from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class Trigger7RecoveryCommitCancelCompositionTest(unittest.TestCase):
    def test_recovery_composition_diagnostic_executes_complete_matrix(self) -> None:
        root = Path(__file__).resolve().parents[3]
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
        self.assertIn(proc.returncode, (0, 2), msg=proc.stderr)
        line = proc.stdout.strip().splitlines()[-1]
        report = json.loads(line)
        self.assertEqual(report["schema"], "F2_T7_RECOVERY_COMMIT_CANCEL_COMPOSITION_DIAGNOSTIC/v1")
        self.assertEqual(report["research_id"], "T7-20260901-RECOVERY-COMMIT-CANCEL-COMPOSITION")
        ids = {case["probe_id"] for case in report["cases"]}
        self.assertEqual(
            ids,
            {
                "RCOMP1_COMPLETED_HEARD_COMMIT_PROJECTION",
                "RCOMP2_TOOL_HISTORY_PROJECTION_DROP",
                "RCOMP3_VALID_ACTIVE_TOOL_RESTART_FENCE",
                "RCOMP4_OUTPUT_SEQUENCE_PROJECTION",
                "RCOMP5_DUPLICATE_OUTPUT_PACKET_ID",
                "RCOMP6_CORRUPT_QUEUED_HEARD_FRACTION",
            },
        )
        self.assertEqual(len(report["cases"]), 6)
        self.assertIn(report["result"], ("NO_COUNTEREXAMPLE", "PRODUCT_NEGATIVE_CANDIDATE"))
        self.assertEqual(report["explicit_zero_credit"]["whole_product"], 0)
        print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
