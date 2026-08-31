#!/usr/bin/env python3
"""REVIEW_ONLY crash-window discriminator stacked on the WP901 G5 fresh-process integration.

No product/runtime credit. Process A is terminated after the canonical WP206 commit but
before same-process successor readback; fresh Process B must still execute the accepted
WP901 G5 full restart planner against the exact persisted row and canonical WP100 authority.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import unittest

from tests.test_wp900_wp206_wp901_g5_fresh_process import (
    PROCESS_A,
    PROCESS_B,
    WP900WP206WP901G5FreshProcessTests,
)

_TARGET = "adapter = persist_sealed_successor_and_readback(store, seal=seal, next_checkpoint=successor)"
_REPLACEMENT = r'''
pre_crash_payload = {
    "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "canonical_db_path": store.canonical_db_path,
    "db_device": store.db_device,
    "db_inode": store.db_inode,
    "authority_receipt_sha256": store.authority_receipt_sha256,
    "checkpoint_id": successor.checkpoint_id,
    "checkpoint_sha256": successor.sha256(),
    "previous_checkpoint_id": successor.previous_checkpoint_id,
    "whole_loop_seal_sha256": seal.sha256(),
    "restart_evidence_sha256": evidence.sha256(),
}
print(json.dumps(pre_crash_payload, sort_keys=True), flush=True)

original_load = CanonicalPersistentAgencyStore.load_checkpoint
load_calls = {"count": 0}
def crash_before_same_process_successor_readback(self, checkpoint_id):
    load_calls["count"] += 1
    if load_calls["count"] == 2:
        os._exit(23)
    return original_load(self, checkpoint_id)
CanonicalPersistentAgencyStore.load_checkpoint = crash_before_same_process_successor_readback
persist_sealed_successor_and_readback(store, seal=seal, next_checkpoint=successor)
os._exit(97)
'''

if PROCESS_A.count(_TARGET) != 1:
    raise AssertionError("expected exactly one WP206 adapter invocation in stacked integration source")
PROCESS_A_POST_COMMIT_CRASH = PROCESS_A.replace(_TARGET, _REPLACEMENT, 1)


class WP901G5PostCommitCrashTests(WP900WP206WP901G5FreshProcessTests):
    def _run_expect(self, source: str, *args: object, returncode: int) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        paths = [str(self.repo_root / "src"), str(self.repo_root)]
        if env.get("PYTHONPATH"):
            paths.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(paths)
        completed = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(source), *(str(arg) for arg in args)],
            cwd=self.repo_root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, returncode, completed.stderr)
        return completed

    def test_post_commit_crash_then_fresh_process_executes_g5_full_restart_plan(self) -> None:
        producer = self._run_expect(PROCESS_A_POST_COMMIT_CRASH, self.db, self.home, returncode=23)
        expected = self._json_stdout(producer)
        consumer = self._run(PROCESS_B, self.db, self.home, json.dumps(expected, sort_keys=True))
        observed = self._json_stdout(consumer)
        self.assertEqual(observed["checkpoint_id"], expected["checkpoint_id"])
        self.assertEqual(observed["checkpoint_sha256"], expected["checkpoint_sha256"])
        self.assertEqual(observed["g5_full_restart_plan"], "OBSERVED_AT_REPOSITORY_COMPONENT_SCOPE")
        self.assertEqual(observed["target_host_execution"], "NOT_OBSERVED")
        self.assertEqual(observed["runtime_credit"], 0)
        self.assertFalse(observed["whole_system_acceptance"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
