#!/usr/bin/env python3
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "trigger4/tools/local_voice/run_g2_pipewire_s2.sh"
HARNESS = ROOT / "trigger4/tools/local_voice/g2_pipewire_s2_runtime.py"
WORKFLOW = ROOT / ".github/workflows/t4-g2-pipewire-monitor-cancel.yml"


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

    def test_terminal_exit_is_owned_by_required_observables_guard(self) -> None:
        launcher = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('printf "G2_PIPEWIRE_HARNESS_EXIT=%s\\n" "$harness_status"', launcher)
        self.assertIn('printf "G2_PIPEWIRE_OBSERVER_EXIT=%s\\n" "$observer_status"', launcher)
        marker = 'printf "G2_REQUIRED_OBSERVABLES_GUARD_EXIT=%s\\n" "$guard_status"'
        self.assertIn(marker, launcher)
        self.assertIn('exit "$guard_status"', launcher)
        tail = launcher.split(marker, 1)[1]
        self.assertNotIn("exit 0", tail)

    def test_promotion_workflow_hashes_observer_and_required_guard(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("trigger4/tools/local_voice/g2_pipewire_observer.py", workflow)
        self.assertIn("trigger4/tools/local_voice/g2_required_observables_guard.py", workflow)
        record_section = workflow.split("- name: Record exact execution subject", 1)[1]
        record_section = record_section.split("- name: Host-health and isolation preflight", 1)[0]
        self.assertIn("trigger4/tools/local_voice/g2_pipewire_observer.py", record_section)
        self.assertIn("trigger4/tools/local_voice/g2_required_observables_guard.py", record_section)

    def test_promotion_workflow_requires_single_guarded_receipt(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("markers = re.findall", workflow)
        self.assertIn("receipt_marker_singleton_ok = len(markers) == 1", workflow)
        self.assertIn("canonical_required_observables_guard", workflow)
        self.assertIn("guard_complete", workflow)
        complete_line = next(
            line for line in workflow.splitlines()
            if line.strip().startswith("complete = bool(")
        )
        self.assertIn("guard_complete", complete_line)
        self.assertIn("receipt_marker_singleton_ok", complete_line)


if __name__ == "__main__":
    unittest.main()
