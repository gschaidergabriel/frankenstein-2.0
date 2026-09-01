#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "trigger4/tools/local_voice/g2_runtime_singleton_guard.py"
SPEC = importlib.util.spec_from_file_location("g2_runtime_singleton_guard", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


class Trigger4G2RuntimeSingletonGuardTests(unittest.TestCase):
    def run_record(self, run_id, head_sha, status="queued", event="push"):
        return {
            "id": run_id,
            "head_sha": head_sha,
            "status": status,
            "event": event,
        }

    def test_exact_invalidated_queued_predecessors_are_exempt(self):
        runs = [
            self.run_record(
                33554493024,
                "6cf8ba3a6ae013083b1013e782d3fff2a373d75b",
            ),
            self.run_record(
                33554578605,
                "eea45dbd94738adb92c4d439ea90534062044239",
            ),
        ]
        blockers, exempted = GUARD.blocking_owners(runs, "999")
        self.assertEqual([], blockers)
        self.assertEqual(["33554493024", "33554578605"], [r["id"] for r in exempted])
        self.assertTrue(all(r["classification"] == GUARD.INVALIDATION_CLASS for r in exempted))

    def test_same_run_id_wrong_sha_fails_closed(self):
        runs = [self.run_record(33554493024, "0" * 40)]
        blockers, exempted = GUARD.blocking_owners(runs, "999")
        self.assertEqual([], exempted)
        self.assertEqual("33554493024", blockers[0]["id"])

    def test_same_run_id_in_progress_is_never_exempt(self):
        runs = [
            self.run_record(
                33554493024,
                "6cf8ba3a6ae013083b1013e782d3fff2a373d75b",
                status="in_progress",
            )
        ]
        blockers, exempted = GUARD.blocking_owners(runs, "999")
        self.assertEqual([], exempted)
        self.assertEqual("in_progress", blockers[0]["status"])

    def test_same_run_id_wrong_event_fails_closed(self):
        runs = [
            self.run_record(
                33554578605,
                "eea45dbd94738adb92c4d439ea90534062044239",
                event="workflow_dispatch",
            )
        ]
        blockers, exempted = GUARD.blocking_owners(runs, "999")
        self.assertEqual([], exempted)
        self.assertEqual(1, len(blockers))

    def test_unclassified_queued_current_semantic_owner_blocks(self):
        runs = [self.run_record(40000000000, "a" * 40, event="workflow_dispatch")]
        blockers, exempted = GUARD.blocking_owners(runs, "999")
        self.assertEqual([], exempted)
        self.assertEqual("40000000000", blockers[0]["id"])

    def test_current_run_self_is_ignored(self):
        runs = [self.run_record(40000000000, "a" * 40, event="workflow_dispatch")]
        blockers, exempted = GUARD.blocking_owners(runs, "40000000000")
        self.assertEqual([], blockers)
        self.assertEqual([], exempted)

    def test_terminal_run_is_not_a_nonterminal_owner(self):
        runs = [self.run_record(40000000000, "a" * 40, status="completed")]
        blockers, exempted = GUARD.blocking_owners(runs, "999")
        self.assertEqual([], blockers)
        self.assertEqual([], exempted)


if __name__ == "__main__":
    unittest.main()
