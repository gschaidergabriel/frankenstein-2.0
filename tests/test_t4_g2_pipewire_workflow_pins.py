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

    def test_stale_queue_exemption_is_exact_and_never_executed_only(self) -> None:
        text = workflow_text()
        self.assertIn("'33554493024': {", text)
        self.assertIn("'6cf8ba3a6ae013083b1013e782d3fff2a373d75b'", text)
        self.assertIn("'33554578605': {", text)
        self.assertIn("'eea45dbd94738adb92c4d439ea90534062044239'", text)
        self.assertIn("status == 'queued'", text)
        self.assertIn("run.get('head_sha') == stale['head_sha']", text)
        self.assertIn("run.get('event') == stale['event']", text)
        self.assertIn("/actions/runs/{run_id}/jobs?per_page=100", text)
        self.assertIn("job.get('status') == 'queued'", text)
        self.assertIn("not job.get('steps')", text)
        self.assertIn("not job.get('runner_id')", text)
        self.assertIn("not job.get('runner_name')", text)
        self.assertIn("T4_G2_STALE_INVALIDATED_QUEUED_EXEMPTION", text)
        self.assertNotIn("run.get('head_sha') !=", text)

    def test_runtime_workflow_uses_supported_sandbox_runner_cli(self) -> None:
        text = workflow_text()
        self.assertNotIn("--source-root", text)
        self.assertIn("--backend nspawn --network on -- \\\n", text)

    def test_runtime_acceptance_requires_zero_exits_exact_subject_and_guarded_singleton_receipt(self) -> None:
        text = workflow_text()
        self.assertIn("call_exit = int(call_match.group(1)) if call_match else None", text)
        self.assertIn("launcher_exit = int(launcher_match.group(1)) if launcher_match else None", text)
        self.assertIn("exit_evidence_ok = call_exit == 0 and launcher_exit == 0", text)
        self.assertIn("receipt_marker_singleton_ok = len(markers) == 1", text)
        self.assertIn("canonical_required_observables_guard", text)
        self.assertIn("guard_complete = bool(", text)
        complete_line = next(
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("complete = bool(")
        )
        for required_term in (
            "sandbox_pass",
            "harness_pass",
            "exact_subject",
            "exit_evidence_ok",
            "guard_complete",
            "receipt_marker_singleton_ok",
        ):
            self.assertIn(required_term, complete_line)
        self.assertIn("'classification': classification", text)
        self.assertIn("'exit_evidence_ok': exit_evidence_ok", text)
        self.assertIn("'receipt_marker_singleton_ok': receipt_marker_singleton_ok", text)
        self.assertIn("'canonical_required_observables_guard_complete': guard_complete", text)

    def test_exact_execution_subject_hashes_observer_and_required_guard(self) -> None:
        text = workflow_text()
        record_section = text.split("- name: Record exact execution subject", 1)[1]
        record_section = record_section.split("- name: Host-health and isolation preflight", 1)[0]
        self.assertIn("trigger4/tools/local_voice/g2_pipewire_observer.py", record_section)
        self.assertIn("trigger4/tools/local_voice/g2_required_observables_guard.py", record_section)


if __name__ == "__main__":
    unittest.main()
