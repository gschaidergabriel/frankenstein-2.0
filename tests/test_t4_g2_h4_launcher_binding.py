#!/usr/bin/env python3
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "trigger4/tools/local_voice/run_g2_pipewire_s2.sh"
H4_GUARD = "research/local_voice/tools/t7_pipewire_g2_h4_guard_cli.py"
DIRECT_ANALYZER = "research/local_voice/tools/t7_pipewire_monitor_cancel_analyze.py"


class Trigger4G2H4LauncherBindingTests(unittest.TestCase):
    def test_promotion_launcher_routes_through_h4_guard(self) -> None:
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn(f'export G2_ANALYZER="$PWD/{H4_GUARD}"', text)
        self.assertNotIn(f'export G2_ANALYZER="$PWD/{DIRECT_ANALYZER}"', text)

    def test_h4_guard_entrypoint_exists(self) -> None:
        self.assertTrue((ROOT / H4_GUARD).is_file())


if __name__ == "__main__":
    unittest.main()
