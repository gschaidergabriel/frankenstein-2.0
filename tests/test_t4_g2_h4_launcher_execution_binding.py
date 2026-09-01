#!/usr/bin/env python3
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "trigger4/tools/local_voice/run_g2_pipewire_s2.sh"


class Trigger4G2H4ExecutionBindingTests(unittest.TestCase):
    def test_terminal_harness_executes_the_h4_cli_bridge(self) -> None:
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn(
            'export G2_ANALYZER="$PWD/research/local_voice/tools/t7_pipewire_g2_h4_guard_cli.py"',
            text,
        )
        self.assertIn('--analyzer "$G2_ANALYZER"', text)
        self.assertNotIn("G2_HARNESS_ANALYZER", text)


if __name__ == "__main__":
    unittest.main()
