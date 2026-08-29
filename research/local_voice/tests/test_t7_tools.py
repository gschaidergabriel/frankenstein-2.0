#!/usr/bin/env python3
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "research" / "local_voice" / "tools"
INVENTORY = TOOLS / "t7_hardware_inventory.py"
DOWNLOADER = TOOLS / "t7_hf_quarantine_download.py"
VALID_REVISION = "0123456789abcdef0123456789abcdef01234567"


class Trigger7ResearchToolsTest(unittest.TestCase):
    def test_hardware_inventory_emits_parseable_schema(self):
        proc = subprocess.run(
            [sys.executable, str(INVENTORY)],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], 1)
        self.assertIn("memory", payload)
        self.assertIn("disk", payload)
        self.assertIn("commands", payload)

    def _fake_hf_env(self, temp_root: Path):
        fake_bin = temp_root / "bin"
        fake_bin.mkdir()
        hf = fake_bin / "hf"
        hf.write_text("#!/bin/sh\nexit 0\n")
        hf.chmod(hf.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
        return env

    def test_downloader_dry_run_requires_immutable_revision_and_executes_no_remote_code(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            env = self._fake_hf_env(temp_root)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(DOWNLOADER),
                    "--repo-id",
                    "Qwen/Qwen3-ASR-0.6B-hf",
                    "--revision",
                    VALID_REVISION,
                    "--name",
                    "qwen3-asr-06b",
                    "--root",
                    str(temp_root / "models"),
                    "--dry-run",
                ],
                text=True,
                capture_output=True,
                check=False,
                env=env,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["revision"], VALID_REVISION)
            self.assertFalse(payload["executes_remote_code"])
            self.assertEqual(payload["repo_id"], "Qwen/Qwen3-ASR-0.6B-hf")

    def test_downloader_rejects_mutable_main_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(DOWNLOADER),
                    "--repo-id",
                    "Qwen/Qwen3-ASR-0.6B-hf",
                    "--revision",
                    "main",
                    "--name",
                    "qwen3-asr-06b",
                    "--root",
                    str(Path(temp) / "models"),
                    "--dry-run",
                ],
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("immutable 40-hex commit SHA", proc.stderr)


if __name__ == "__main__":
    unittest.main()
