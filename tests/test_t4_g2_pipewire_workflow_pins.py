#!/usr/bin/env python3
import hashlib
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/t4-g2-pipewire-monitor-cancel.yml"
RUNNER = ROOT / "tools/vps_sandbox/run_ubuntu_sandbox.sh"
PIN_NAME = "F2_NSPAWN_RUNNER_SHA256"


def workflow_pin() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(rf"^\s*{PIN_NAME}:\s*([0-9a-f]+)\s*$", text, re.MULTILINE)
    if not match:
        raise AssertionError(f"missing {PIN_NAME} in {WORKFLOW}")
    return match.group(1)


class Trigger4G2PipeWireWorkflowPinTests(unittest.TestCase):
    def test_runner_pin_is_sha256_hex(self) -> None:
        pin = workflow_pin()
        self.assertRegex(pin, r"^[0-9a-f]{64}$")

    def test_runner_pin_matches_current_repository_bytes(self) -> None:
        expected = hashlib.sha256(RUNNER.read_bytes()).hexdigest()
        self.assertEqual(workflow_pin(), expected)


if __name__ == "__main__":
    unittest.main()
