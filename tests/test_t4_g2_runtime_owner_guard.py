#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "trigger4/tools/local_voice/g2_runtime_owner_guard.py"
spec = importlib.util.spec_from_file_location("g2_runtime_owner_guard_test", MODULE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def run(run_id, sha, status):
    return {"id": run_id, "head_sha": sha, "status": status, "event": "workflow_dispatch"}


class Trigger4G2RuntimeOwnerGuardTests(unittest.TestCase):
    def test_self_is_ignored(self):
        item = run("123", "a" * 40, "in_progress")
        self.assertEqual(mod.classify_run(item, "123"), "SELF")

    def test_exact_invalidated_queued_predecessors_are_exempt(self):
        for run_id, sha in mod.INVALIDATED_QUEUED_SUBJECTS.items():
            item = run(run_id, sha, "queued")
            self.assertEqual(
                mod.classify_run(item, "current"),
                "EXEMPT_EXACT_INVALIDATED_QUEUED_PREDECESSOR",
            )

    def test_same_invalidated_id_with_wrong_sha_blocks(self):
        run_id = next(iter(mod.INVALIDATED_QUEUED_SUBJECTS))
        item = run(run_id, "f" * 40, "queued")
        self.assertEqual(mod.classify_run(item, "current"), "BLOCKING_NONTERMINAL_OWNER")

    def test_invalidated_subject_in_progress_still_blocks(self):
        run_id, sha = next(iter(mod.INVALIDATED_QUEUED_SUBJECTS.items()))
        item = run(run_id, sha, "in_progress")
        self.assertEqual(mod.classify_run(item, "current"), "BLOCKING_NONTERMINAL_OWNER")

    def test_unlisted_queued_or_in_progress_subject_blocks(self):
        for status in ("queued", "in_progress"):
            item = run("999", "9" * 40, status)
            self.assertEqual(mod.classify_run(item, "current"), "BLOCKING_NONTERMINAL_OWNER")

    def test_evaluate_preserves_exemption_and_blocker_separately(self):
        old_id, old_sha = next(iter(mod.INVALIDATED_QUEUED_SUBJECTS.items()))
        items = [
            run(old_id, old_sha, "queued"),
            run("999", "9" * 40, "queued"),
            run("current", "c" * 40, "in_progress"),
        ]
        blocking, exempted = mod.evaluate_runs(items, "current")
        self.assertEqual([item["id"] for item in blocking], ["999"])
        self.assertEqual([item["id"] for item in exempted], [old_id])
        self.assertEqual(exempted[0]["invalidation_evidence_ref"], mod.INVALIDATION_EVIDENCE_REF)


if __name__ == "__main__":
    unittest.main()
