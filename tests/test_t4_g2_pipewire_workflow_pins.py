#!/usr/bin/env python3
import hashlib
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/t4-g2-pipewire-monitor-cancel.yml"
RUNNER = ROOT / "tools/vps_sandbox/run_ubuntu_sandbox.sh"
PIN_NAME = "F2_NSPAWN_RUNNER_SHA256"
CONCURRENCY_GROUP = "t4-g2-pipewire-monitor-cancel-s2"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def workflow_pin() -> str:
    text = workflow_text()
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

    def test_runtime_workflow_is_manual_only(self) -> None:
        text = workflow_text()
        self.assertIn("on:\n  workflow_dispatch:\n", text)
        self.assertNotRegex(text, r"(?m)^\s{2}push:\s*$")

    def test_runtime_workflow_has_singleton_concurrency_group(self) -> None:
        text = workflow_text()
        self.assertIn(
            "concurrency:\n"
            f"  group: {CONCURRENCY_GROUP}\n"
            "  cancel-in-progress: false\n",
            text,
        )

    def test_runtime_workflow_has_duplicate_nonterminal_owner_guard(self) -> None:
        text = workflow_text()
        self.assertIn("Fail closed on duplicate nonterminal G2 runtime owner", text)
        self.assertIn("for status in ('queued', 'in_progress'):", text)
        self.assertIn("T4_G2_SINGLETON_OWNER=PASS", text)
        self.assertIn("raise SystemExit(3)", text)

    def test_runtime_workflow_uses_supported_sandbox_runner_cli(self) -> None:
        text = workflow_text()
        self.assertNotIn("--source-root", text)
        self.assertIn("--backend nspawn --network on -- \\\n", text)


if __name__ == "__main__":
    unittest.main()
