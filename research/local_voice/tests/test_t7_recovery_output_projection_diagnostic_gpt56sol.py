from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class Trigger7RecoveryOutputProjectionDiagnosticTest(unittest.TestCase):
    def test_rbound6_executes_and_reports_exact_scope(self) -> None:
        root = Path(__file__).resolve().parents[3]
        tool = root / "research/local_voice/tools/falsify_voice_packet_cortex_output_projection.py"
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
        self.assertEqual(report["schema"], "F2_T7_RECOVERY_OUTPUT_PROJECTION_DIAGNOSTIC/v1")
        self.assertEqual(report["case"]["probe_id"], "RBOUND6_OUTPUT_SEQUENCE_PROJECTION_CONSISTENCY")
        self.assertIn(report["result"], ("NO_COUNTEREXAMPLE", "PRODUCT_NEGATIVE_CANDIDATE"))
        self.assertEqual(report["explicit_zero_credit"]["whole_product"], 0)
        print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
