#!/usr/bin/env python3
"""Repository-level contract tests for the guarded S2 booted-systemd sandbox mode.

These tests intentionally do not mint runtime evidence. They prove only the fail-closed
CLI/implementation contract that must exist before a real clay-host S2 discriminator is legal.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "vps_sandbox" / "run_ubuntu_sandbox.sh"


class VpsSandboxSystemdBootContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_shell_syntax_is_valid(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_help_exposes_explicit_opt_in(self) -> None:
        completed = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("--boot-systemd", completed.stderr)

    def test_boot_mode_fails_closed_outside_nspawn(self) -> None:
        completed = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--backend",
                "docker",
                "--boot-systemd",
                "--",
                "true",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 74)
        self.assertIn("requires --backend nspawn", completed.stderr)

    def test_boot_path_reuses_existing_s2_authority_and_cleanup_fences(self) -> None:
        required_fragments = (
            'boot_systemd=0',
            '--boot-systemd) boot_systemd=1',
            '"$boot_systemd" == "1" && "$backend" != "nspawn"',
            '--boot',
            '--register=yes',
            'machinectl show "$name" --property=State --value',
            'systemd-run',
            '--machine="$name"',
            'machinectl poweroff "$name"',
            'machinectl terminate "$name"',
            ': > \'$run_root/etc/machine-id\'',
            '--bind-ro="$workspace:/f2-src"',
            'host_survival_sentinel=PASS',
            'physical_local_credit=0',
            'whole_system_acceptance=false',
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.text)

    def test_boot_path_does_not_create_a_second_sandbox_runner(self) -> None:
        # The new mode must remain inside run_nspawn() rather than introducing a
        # parallel helper/execution authority.
        self.assertEqual(self.text.count("run_nspawn()"), 1)
        self.assertNotIn("run_systemd_sandbox()", self.text)
        self.assertGreaterEqual(self.text.count('--bind-ro="$workspace:/f2-src"'), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
