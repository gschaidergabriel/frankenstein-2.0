#!/usr/bin/env python3
import hashlib
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/t4-g2-pipewire-monitor-cancel.yml"
RUNNER = ROOT / "tools/vps_sandbox/run_ubuntu_sandbox.sh"
OWNER_GUARD = ROOT / "trigger4/tools/local_voice/g2_runtime_owner_guard.py"
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

    def test_runtime_workflow_routes_duplicate_guard_through_exact_helper(self) -> None:
        text = workflow_text()
        helper = "trigger4/tools/local_voice/g2_runtime_owner_guard.py"
        self.assertTrue(OWNER_GUARD.is_file())
        self.assertIn("Fail closed on duplicate nonterminal G2 runtime owner", text)
        self.assertIn(f"python3 {helper}", text)
        self.assertIn(helper + " \\\n", text)
        self.assertNotIn("for status in ('queued', 'in_progress'):", text)

    def test_runtime_workflow_uses_supported_sandbox_runner_cli(self) -> None:
        text = workflow_text()
        self.assertNotIn("--source-root", text)
        self.assertIn("--backend nspawn --network on -- \\\n", text)

    def test_receipt_preserves_exact_harness_scope(self) -> None:
        text = workflow_text()
        self.assertIn("T4_G2_PIPEWIRE_S2_WORKFLOW_RECEIPT/v2", text)
        self.assertIn("measured_credit = dict(harness.get('measured_credit') or {})", text)
        self.assertIn("'autonomous_production_playback_executor': 0", text)
        self.assertIn("'producer_tts_generation_cancel': 0", text)
        self.assertNotIn("'bounded_cancellation_to_virtual_audio_monitor_silence': 1 if complete else 0", text)


if __name__ == "__main__":
    unittest.main()
