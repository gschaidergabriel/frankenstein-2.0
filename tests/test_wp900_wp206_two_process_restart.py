#!/usr/bin/env python3
"""Fresh-process restart falsifiers for the WP900 -> WP206 -> WP901 boundary.

These tests deliberately do not grant target-host/runtime/whole-system credit. They prove
only that the repository implementation can persist a WP900-sealed successor in one Python
process and load the exact persisted row through the accepted WP901/WP206 ingress in a
separate Python process. A second variant terminates Process A after the WP206 commit and
before the integration adapter can perform its same-process readback.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import unittest


PROCESS_A_CLEAN = r'''
import json
from pathlib import Path
import subprocess
import sys

from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore
from frankenstein2.whole_loop_persistence_integration import persist_sealed_successor_and_readback
from frankenstein2.whole_persistent_loop import seal_whole_persistent_loop
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path
from tests.test_whole_persistent_loop import fixture_components


def sealed_fixture():
    current, frame, contract, plan, gwt, gwt_evidence, decision, outcome, successor = fixture_components()
    seal = seal_whole_persistent_loop(
        seal_id="whole-loop-two-process-restart",
        generation=0,
        current_checkpoint=current,
        frame=frame,
        contract=contract,
        plan=plan,
        gwt_seal=gwt,
        gwt_evidence=gwt_evidence,
        decision=decision,
        outcome=outcome,
        next_checkpoint=successor,
        provenance_refs=("test:wp900-wp206:two-process",),
    )
    return current, successor, seal


db = Path(sys.argv[1])
home = Path(sys.argv[2])
resolution = resolve_unifieddb_path(env={"FRANKENSTEIN2_DB": str(db)}, home=home)
fingerprint = fingerprint_unifieddb(resolution.path)
store = CanonicalPersistentAgencyStore.open(resolution=resolution, fingerprint=fingerprint)
store.initialize_schema()
current, successor, seal = sealed_fixture()
store.write_checkpoint(current)
evidence = persist_sealed_successor_and_readback(store, seal=seal, next_checkpoint=successor)
payload = {
    "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "canonical_db_path": store.canonical_db_path,
    "db_device": store.db_device,
    "db_inode": store.db_inode,
    "authority_receipt_sha256": store.authority_receipt_sha256,
    "current_checkpoint_id": current.checkpoint_id,
    "current_checkpoint_sha256": current.sha256(),
    "next_checkpoint_id": successor.checkpoint_id,
    "next_checkpoint_sha256": successor.sha256(),
    "next_previous_checkpoint_id": successor.previous_checkpoint_id,
    "whole_loop_seal_sha256": seal.sha256(),
    "adapter_evidence_sha256": evidence.sha256(),
}
store.close()
print(json.dumps(payload, sort_keys=True))
'''


PROCESS_A_CRASH_AFTER_COMMIT = r'''
import json
import os
from pathlib import Path
import subprocess
import sys

from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore
from frankenstein2.whole_loop_persistence_integration import persist_sealed_successor_and_readback
from frankenstein2.whole_persistent_loop import seal_whole_persistent_loop
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path
from tests.test_whole_persistent_loop import fixture_components


def sealed_fixture():
    current, frame, contract, plan, gwt, gwt_evidence, decision, outcome, successor = fixture_components()
    seal = seal_whole_persistent_loop(
        seal_id="whole-loop-two-process-crash-window",
        generation=0,
        current_checkpoint=current,
        frame=frame,
        contract=contract,
        plan=plan,
        gwt_seal=gwt,
        gwt_evidence=gwt_evidence,
        decision=decision,
        outcome=outcome,
        next_checkpoint=successor,
        provenance_refs=("test:wp900-wp206:crash-window",),
    )
    return current, successor, seal


db = Path(sys.argv[1])
home = Path(sys.argv[2])
metadata_path = Path(sys.argv[3])
resolution = resolve_unifieddb_path(env={"FRANKENSTEIN2_DB": str(db)}, home=home)
fingerprint = fingerprint_unifieddb(resolution.path)
store = CanonicalPersistentAgencyStore.open(resolution=resolution, fingerprint=fingerprint)
store.initialize_schema()
current, successor, seal = sealed_fixture()
store.write_checkpoint(current)
metadata = {
    "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "canonical_db_path": store.canonical_db_path,
    "db_device": store.db_device,
    "db_inode": store.db_inode,
    "authority_receipt_sha256": store.authority_receipt_sha256,
    "current_checkpoint_id": current.checkpoint_id,
    "current_checkpoint_sha256": current.sha256(),
    "next_checkpoint_id": successor.checkpoint_id,
    "next_checkpoint_sha256": successor.sha256(),
    "next_previous_checkpoint_id": successor.previous_checkpoint_id,
    "whole_loop_seal_sha256": seal.sha256(),
}
with metadata_path.open("w", encoding="utf-8") as handle:
    json.dump(metadata, handle, sort_keys=True)
    handle.flush()
    os.fsync(handle.fileno())

original_load = CanonicalPersistentAgencyStore.load_checkpoint
calls = {"count": 0}


def crash_before_same_process_successor_readback(self, checkpoint_id):
    calls["count"] += 1
    if calls["count"] == 2:
        # The adapter has already returned from WP206 write_checkpoint(), whose transaction
        # commits before returning. Exit before the adapter can read the successor back.
        os._exit(23)
    return original_load(self, checkpoint_id)


CanonicalPersistentAgencyStore.load_checkpoint = crash_before_same_process_successor_readback
persist_sealed_successor_and_readback(store, seal=seal, next_checkpoint=successor)
os._exit(97)
'''


PROCESS_B_FRESH_WP901_LOAD = r'''
import json
import os
from pathlib import Path
import subprocess
import sys

from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore
from frankenstein2.restart_recovery_persisted_row_attestation import attest_persisted_checkpoint_load
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


db = Path(sys.argv[1])
home = Path(sys.argv[2])
expected = json.loads(sys.argv[3])
resolution = resolve_unifieddb_path(env={"FRANKENSTEIN2_DB": str(db)}, home=home)
fingerprint = fingerprint_unifieddb(resolution.path)
store = CanonicalPersistentAgencyStore.open(resolution=resolution, fingerprint=fingerprint)
checkpoint, attestation = attest_persisted_checkpoint_load(
    store,
    checkpoint_id=expected["next_checkpoint_id"],
)
current_head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
assert current_head == expected["source_head"]
assert os.path.realpath(expected["canonical_db_path"]) == store.canonical_db_path
assert expected["db_device"] == store.db_device
assert expected["db_inode"] == store.db_inode
assert expected["authority_receipt_sha256"] == store.authority_receipt_sha256
assert checkpoint.checkpoint_id == expected["next_checkpoint_id"]
assert checkpoint.sha256() == expected["next_checkpoint_sha256"]
assert checkpoint.previous_checkpoint_id == expected["next_previous_checkpoint_id"]
assert checkpoint.previous_checkpoint_id == expected["current_checkpoint_id"]
assert attestation.checkpoint_id == expected["next_checkpoint_id"]
assert attestation.checkpoint_sha256 == expected["next_checkpoint_sha256"]
assert attestation.checkpoint_previous_checkpoint_id == expected["current_checkpoint_id"]
assert attestation.canonical_db_path == store.canonical_db_path
assert attestation.db_device == store.db_device
assert attestation.db_inode == store.db_inode
assert attestation.unifieddb_authority_receipt_sha256 == store.authority_receipt_sha256
payload = {
    "source_head": current_head,
    "checkpoint_id": checkpoint.checkpoint_id,
    "checkpoint_sha256": checkpoint.sha256(),
    "previous_checkpoint_id": checkpoint.previous_checkpoint_id,
    "row_evidence_sha256": attestation.row_evidence_sha256,
    "fresh_process_persisted_row_load": "OBSERVED_AT_REPOSITORY_COMPONENT_SCOPE",
    "target_host_execution": "NOT_OBSERVED",
    "runtime_credit": 0,
    "whole_system_acceptance": False,
}
store.close()
print(json.dumps(payload, sort_keys=True))
'''


class WP900WP206TwoProcessRestartTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.db = self.root / "canonical" / "unified.db"
        self.db.parent.mkdir()
        connection = sqlite3.connect(self.db)
        try:
            connection.execute("CREATE TABLE f2_bootstrap(id INTEGER PRIMARY KEY)")
            connection.commit()
        finally:
            connection.close()
        self.repo_root = Path(__file__).resolve().parents[1]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, source: str, *args: object, expected_returncode: int = 0) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        python_paths = [str(self.repo_root / "src"), str(self.repo_root)]
        if env.get("PYTHONPATH"):
            python_paths.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        completed = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(source), *(str(arg) for arg in args)],
            cwd=self.repo_root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != expected_returncode:
            self.fail(
                "subprocess returncode mismatch "
                f"expected={expected_returncode} actual={completed.returncode}\n"
                f"stdout={completed.stdout}\nstderr={completed.stderr}"
            )
        return completed

    @staticmethod
    def _json_stdout(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            raise AssertionError("subprocess emitted no JSON line")
        return json.loads(lines[-1])

    def test_clean_exit_then_fresh_process_wp901_loads_exact_successor(self) -> None:
        producer = self._run(PROCESS_A_CLEAN, self.db, self.home)
        expected = self._json_stdout(producer)
        consumer = self._run(
            PROCESS_B_FRESH_WP901_LOAD,
            self.db,
            self.home,
            json.dumps(expected, sort_keys=True),
        )
        observed = self._json_stdout(consumer)
        self.assertEqual(observed["checkpoint_id"], expected["next_checkpoint_id"])
        self.assertEqual(observed["checkpoint_sha256"], expected["next_checkpoint_sha256"])
        self.assertEqual(observed["previous_checkpoint_id"], expected["current_checkpoint_id"])
        self.assertEqual(
            observed["fresh_process_persisted_row_load"],
            "OBSERVED_AT_REPOSITORY_COMPONENT_SCOPE",
        )
        self.assertEqual(observed["target_host_execution"], "NOT_OBSERVED")
        self.assertEqual(observed["runtime_credit"], 0)
        self.assertFalse(observed["whole_system_acceptance"])

    def test_post_commit_pre_readback_process_exit_recovers_exact_successor(self) -> None:
        metadata_path = self.root / "crash-metadata.json"
        self._run(
            PROCESS_A_CRASH_AFTER_COMMIT,
            self.db,
            self.home,
            metadata_path,
            expected_returncode=23,
        )
        self.assertTrue(metadata_path.is_file())
        expected = json.loads(metadata_path.read_text(encoding="utf-8"))
        consumer = self._run(
            PROCESS_B_FRESH_WP901_LOAD,
            self.db,
            self.home,
            json.dumps(expected, sort_keys=True),
        )
        observed = self._json_stdout(consumer)
        self.assertEqual(observed["checkpoint_id"], expected["next_checkpoint_id"])
        self.assertEqual(observed["checkpoint_sha256"], expected["next_checkpoint_sha256"])
        self.assertEqual(observed["previous_checkpoint_id"], expected["current_checkpoint_id"])
        self.assertEqual(observed["runtime_credit"], 0)
        self.assertFalse(observed["whole_system_acceptance"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
