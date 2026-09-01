from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class Trigger7RecoveryImportBoundsDiagnosticTest(unittest.TestCase):
    def test_rbound_diagnostic_executes_and_emits_complete_matrix(self) -> None:
        root = Path(__file__).resolve().parents[3]
        tool = root / "research/local_voice/tools/falsify_voice_packet_cortex_import_bounds.py"
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
        self.assertEqual(report["schema"], "F2_T7_RECOVERY_IMPORT_BOUNDS_DIAGNOSTIC/v1")
        ids = {case["probe_id"] for case in report["cases"]}
        self.assertEqual(
            ids,
            {
                "RBOUND1_INPUT_SEEN_IMPORT_CAP",
                "RBOUND2_OUTPUT_IMPORT_CAP",
                "RBOUND3_TOOL_IMPORT_CAP",
                "RBOUND4_EVENT_IMPORT_CAP",
                "RBOUND5_SEQUENCE_PROJECTION_CONSISTENCY",
            },
        )
        self.assertEqual(len(report["cases"]), 5)
        self.assertIn(report["result"], ("NO_COUNTEREXAMPLE", "PRODUCT_NEGATIVE_CANDIDATE"))
        print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
