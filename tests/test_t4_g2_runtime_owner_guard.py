#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "trigger4/tools/local_voice/g2_runtime_owner_guard.py"
spec = importlib.util.spec_from_file_location("g2_runtime_owner_guard_test", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


OLD_RUN = {
    "id": 33554493024,
    "head_sha": "6cf8ba3a6ae013083b1013e782d3fff2a373d75b",
    "event": "push",
    "status": "queued",
    "conclusion": None,
}
DUP_RUN = {
    "id": 33554578605,
    "head_sha": "eea45dbd94738adb92c4d439ea90534062044239",
    "event": "push",
    "status": "queued",
    "conclusion": None,
}
QUEUED_JOB = {"id": 1, "status": "queued", "conclusion": None, "steps": None}


class Trigger4G2RuntimeOwnerGuardTests(unittest.TestCase):
    def test_exact_invalidated_queued_never_started_subjects_are_exemptable(self):
        self.assertTrue(mod.can_exempt_stale_queued_run(OLD_RUN, [QUEUED_JOB]))
        self.assertTrue(mod.can_exempt_stale_queued_run(DUP_RUN, [QUEUED_JOB]))

    def test_unknown_queued_subject_remains_blocking(self):
        unknown = dict(OLD_RUN, id=99999999999)
        self.assertFalse(mod.can_exempt_stale_queued_run(unknown, [QUEUED_JOB]))

    def test_changed_sha_remains_blocking(self):
        changed = dict(OLD_RUN, head_sha="f" * 40)
        self.assertFalse(mod.can_exempt_stale_queued_run(changed, [QUEUED_JOB]))

    def test_in_progress_or_manual_subject_never_inherits_exemption(self):
        self.assertFalse(mod.can_exempt_stale_queued_run(dict(OLD_RUN, status="in_progress"), [QUEUED_JOB]))
        self.assertFalse(mod.can_exempt_stale_queued_run(dict(OLD_RUN, event="workflow_dispatch"), [QUEUED_JOB]))

    def test_missing_or_started_job_evidence_fails_closed(self):
        self.assertFalse(mod.can_exempt_stale_queued_run(OLD_RUN, []))
        self.assertFalse(
            mod.can_exempt_stale_queued_run(
                OLD_RUN,
                [{"id": 1, "status": "in_progress", "conclusion": None, "steps": [{"status": "in_progress"}]}],
            )
        )
        self.assertFalse(
            mod.can_exempt_stale_queued_run(
                OLD_RUN,
                [{"id": 1, "status": "queued", "conclusion": None, "steps": [{"status": "completed"}]}],
            )
        )

    def test_evaluate_keeps_invariant_queue_and_in_progress_as_owners(self):
        invariant = {
            "id": 777,
            "head_sha": "a" * 40,
            "event": "workflow_dispatch",
            "status": "queued",
            "conclusion": None,
        }
        running = {
            "id": 888,
            "head_sha": "b" * 40,
            "event": "workflow_dispatch",
            "status": "in_progress",
            "conclusion": None,
        }
        owners, exempted = mod.evaluate_runs(
            [OLD_RUN, invariant, running],
            current_run_id="999",
            jobs_by_run={
                str(OLD_RUN["id"]): [QUEUED_JOB],
                "777": [QUEUED_JOB],
                "888": [{"id": 2, "status": "in_progress", "conclusion": None, "steps": None}],
            },
        )
        self.assertEqual([item["id"] for item in exempted], [str(OLD_RUN["id"])])
        self.assertEqual({item["id"] for item in owners}, {"777", "888"})

    def test_current_run_is_ignored_without_exempting_other_owners(self):
        owners, exempted = mod.evaluate_runs(
            [OLD_RUN, DUP_RUN],
            current_run_id=str(OLD_RUN["id"]),
            jobs_by_run={str(DUP_RUN["id"]): [QUEUED_JOB]},
        )
        self.assertEqual(owners, [])
        self.assertEqual([item["id"] for item in exempted], [str(DUP_RUN["id"])])


if __name__ == "__main__":
    unittest.main()
