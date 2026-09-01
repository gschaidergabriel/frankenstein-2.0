from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class Trigger7MicroturnPresenceExecutionTest(unittest.TestCase):
    def test_current_presence_diagnostic_executes_and_emits_bounded_report(self) -> None:
        repo = Path(__file__).resolve().parents[3]
        env = os.environ.copy()
        src = str(repo / "src")
        env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        proc = subprocess.run(
            [sys.executable, "research/local_voice/tools/falsify_voice_packet_microturn_presence.py"],
            cwd=repo,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertTrue(lines, msg="diagnostic emitted no JSON report")
        report = json.loads(lines[-1])
        self.assertEqual(report["schema"], "F2_T7_MICROTURN_PRESENCE_DIAGNOSTIC/v1")
        self.assertIn(
            report["result"],
            {
                "DISCOVERY_PRESENCE_METADATA_ONLY_AT_PROBED_BOUNDARY",
                "COMPOSED_MICROTURN_BEHAVIOR_DIFFERS_OR_PROBE_FAILED",
            },
        )
        self.assertIn("interruptible", report)
        self.assertIn("busy", report)
        self.assertIn("presence_behavior_equivalent", report)
        self.assertTrue(report["interruptible"]["transition_ok"])
        self.assertTrue(report["busy"]["transition_ok"])
        self.assertEqual(report["explicit_zero_credit"]["whole_product"], 0)
        self.assertEqual(report["explicit_zero_credit"]["whole_voice_e2e"], 0)


if __name__ == "__main__":
    unittest.main()
