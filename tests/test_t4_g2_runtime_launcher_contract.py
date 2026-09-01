#!/usr/bin/env python3
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "trigger4/tools/local_voice/run_g2_pipewire_s2.sh"
HARNESS = ROOT / "trigger4/tools/local_voice/g2_pipewire_s2_runtime.py"


class Trigger4G2RuntimeLauncherContractTests(unittest.TestCase):
    def test_launcher_supplies_every_required_harness_input(self) -> None:
        launcher = LAUNCHER.read_text(encoding="utf-8")
        harness = HARNESS.read_text(encoding="utf-8")
        required = set(
            re.findall(
                r'ap\.add_argument\("(--[a-z0-9-]+)"[^\n]*required=True',
                harness,
            )
        )
        self.assertTrue(required, "required harness flags were not discovered")
        missing = sorted(flag for flag in required if flag not in launcher)
        self.assertEqual([], missing, f"launcher is missing required harness flags: {missing}")

    def test_live_bound_and_h4_cli_analyzer_are_wired(self) -> None:
        launcher = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('pw-metadata -n settings >"$G2_WORK/pipewire-settings-preflight.txt"', launcher)
        self.assertIn('"$G2_EVIDENCE_HELPER" derive-bound', launcher)
        self.assertIn('--bound-preflight-receipt "$G2_WORK/pipewire-bound-preflight.json"', launcher)
        self.assertIn('--max-inflight-ms "$G2_MAX_INFLIGHT_MS"', launcher)
        self.assertIn(
            'G2_ANALYZER="$PWD/research/local_voice/tools/t7_pipewire_g2_h4_guard_cli.py"',
            launcher,
        )
        self.assertIn('--analyzer "$G2_ANALYZER"', launcher)
        self.assertNotIn("G2_HARNESS_ANALYZER", launcher)

    def test_harness_exit_is_not_erased_by_launcher(self) -> None:
        launcher = LAUNCHER.read_text(encoding="utf-8")
        marker = 'printf "G2_PIPEWIRE_HARNESS_EXIT=%s\\n" "$harness_status"'
        self.assertIn(marker, launcher)
        self.assertIn('exit "$harness_status"', launcher)
        tail = launcher.split(marker, 1)[1]
        self.assertNotIn("exit 0", tail)


if __name__ == "__main__":
    unittest.main()
