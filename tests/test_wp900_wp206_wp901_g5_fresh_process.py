#!/usr/bin/env python3
"""Fresh-process integration discriminator for WP900 -> WP206 -> WP901 G5.

Repository-component evidence only. This proves that a WP900-sealed successor persisted
through the canonical WP206 store in Process A can be consumed by the accepted WP901 G5
full restart planner in a fresh Process B while preserving the canonical WP100 UnifiedDB
authority reference. It grants no target-host/runtime/whole-system credit.
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


PROCESS_A = r'''
import json
from pathlib import Path
import subprocess
import sys

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore, advance_checkpoint
from frankenstein2.restart_recovery_continuation import PersistedRestartEvidence
from frankenstein2.restart_recovery_source_authentication import causal_identity_ref
from frankenstein2.whole_loop_persistence_integration import persist_sealed_successor_and_readback
from frankenstein2.whole_persistent_loop import LoopOutcomeEvidence, NO_EFFECT, required_reentry_refs, seal_whole_persistent_loop
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path
from tests.test_whole_persistent_loop import fixture_components


def build_sources():
    current, frame, contract, grid_plan, gwt_seal, gwt_evidence, decision, _, _ = fixture_components()
    causal = CausalIdentity(
        session_id="session-wp901-g5-fresh",
        agent_id="agent-wp901-g5-fresh",
        task_id="task-wp901-g5-fresh",
        turn_id="turn-wp901-g5-fresh",
        causal_id="causal-wp901-g5-fresh",
        generation=current.generation + 1,
        parent_causal_id="causal-wp901-g5-fresh-parent",
    )
    causal_ref = causal_identity_ref(causal)
    outcome = LoopOutcomeEvidence(
        outcome_id="outcome-wp901-g5-fresh",
        status=NO_EFFECT,
        provenance_refs=(causal_ref, "test:wp901:g5:fresh:outcome"),
    )
    reentry_refs = required_reentry_refs(
        current_checkpoint=current,
        frame=frame,
        contract=contract,
        plan=grid_plan,
        gwt_seal=gwt_seal,
        decision=decision,
        outcome=outcome,
    )
    successor = advance_checkpoint(
        current,
        checkpoint_id="checkpoint-wp901-g5-fresh",
        pulse_id="pulse-wp901-g5-fresh",
        observation_id="observation-wp901-g5-fresh",
        provenance_refs=tuple(sorted(set(reentry_refs) | {causal_ref})),
    )
    seal = seal_whole_persistent_loop(
        seal_id="whole-loop-wp901-g5-fresh",
        generation=current.generation,
        current_checkpoint=current,
        frame=frame,
        contract=contract,
        plan=grid_plan,
        gwt_seal=gwt_seal,
        gwt_evidence=gwt_evidence,
        decision=decision,
        outcome=outcome,
        next_checkpoint=successor,
        provenance_refs=(causal_ref, "test:wp901:g5:fresh:whole-loop"),
    )
    evidence = PersistedRestartEvidence(
        evidence_id="restart-evidence-wp901-g5-fresh",
        source_checkpoint_id=successor.checkpoint_id,
        source_checkpoint_generation=successor.generation,
        source_checkpoint_sha256=successor.sha256(),
        whole_loop_seal_id=seal.seal_id,
        whole_loop_seal_sha256=seal.sha256(),
        outcome_status=outcome.status,
        outcome_sha256=outcome.sha256(),
        unfinished_work_refs=("work:alpha", "work:beta"),
        completed_work_refs=("work:done",),
        effect_attempt_refs=(),
        provenance_refs=(causal_ref, "receipt:wp900", "receipt:wp206"),
    )
    return current, successor, seal, evidence


db = Path(sys.argv[1])
home = Path(sys.argv[2])
resolution = resolve_unifieddb_path(env={"FRANKENSTEIN2_DB": str(db)}, home=home)
fingerprint = fingerprint_unifieddb(resolution.path)
store = CanonicalPersistentAgencyStore.open(resolution=resolution, fingerprint=fingerprint)
store.initialize_schema()
current, successor, seal, evidence = build_sources()
store.write_checkpoint(current)
adapter = persist_sealed_successor_and_readback(store, seal=seal, next_checkpoint=successor)
payload = {
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
    "adapter_evidence_sha256": adapter.sha256(),
}
store.close()
print(json.dumps(payload, sort_keys=True))
'''


PROCESS_B = r'''
import json
import os
from pathlib import Path
import subprocess
import sys

from frankenstein2.causal_authority_binding import UnifiedDBAuthorityRef
from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore, advance_checkpoint
from frankenstein2.restart_recovery_continuation import CONTINUE_UNFINISHED, PersistedRestartEvidence
from frankenstein2.restart_recovery_persisted_row_attestation import (
    CANONICAL_UNIFIEDDB_AUTHORITY_FINGERPRINT_SCHEMA,
    CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF,
    CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE,
    plan_restart_continuation_from_persisted_row,
)
from frankenstein2.restart_recovery_source_authentication import causal_identity_ref
from frankenstein2.whole_persistent_loop import LoopOutcomeEvidence, NO_EFFECT, required_reentry_refs, seal_whole_persistent_loop
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path
from tests.test_whole_persistent_loop import fixture_components


def build_sources():
    current, frame, contract, grid_plan, gwt_seal, gwt_evidence, decision, _, _ = fixture_components()
    causal = CausalIdentity(
        session_id="session-wp901-g5-fresh",
        agent_id="agent-wp901-g5-fresh",
        task_id="task-wp901-g5-fresh",
        turn_id="turn-wp901-g5-fresh",
        causal_id="causal-wp901-g5-fresh",
        generation=current.generation + 1,
        parent_causal_id="causal-wp901-g5-fresh-parent",
    )
    causal_ref = causal_identity_ref(causal)
    outcome = LoopOutcomeEvidence(
        outcome_id="outcome-wp901-g5-fresh",
        status=NO_EFFECT,
        provenance_refs=(causal_ref, "test:wp901:g5:fresh:outcome"),
    )
    reentry_refs = required_reentry_refs(
        current_checkpoint=current,
        frame=frame,
        contract=contract,
        plan=grid_plan,
        gwt_seal=gwt_seal,
        decision=decision,
        outcome=outcome,
    )
    successor = advance_checkpoint(
        current,
        checkpoint_id="checkpoint-wp901-g5-fresh",
        pulse_id="pulse-wp901-g5-fresh",
        observation_id="observation-wp901-g5-fresh",
        provenance_refs=tuple(sorted(set(reentry_refs) | {causal_ref})),
    )
    seal = seal_whole_persistent_loop(
        seal_id="whole-loop-wp901-g5-fresh",
        generation=current.generation,
        current_checkpoint=current,
        frame=frame,
        contract=contract,
        plan=grid_plan,
        gwt_seal=gwt_seal,
        gwt_evidence=gwt_evidence,
        decision=decision,
        outcome=outcome,
        next_checkpoint=successor,
        provenance_refs=(causal_ref, "test:wp901:g5:fresh:whole-loop"),
    )
    evidence = PersistedRestartEvidence(
        evidence_id="restart-evidence-wp901-g5-fresh",
        source_checkpoint_id=successor.checkpoint_id,
        source_checkpoint_generation=successor.generation,
        source_checkpoint_sha256=successor.sha256(),
        whole_loop_seal_id=seal.seal_id,
        whole_loop_seal_sha256=seal.sha256(),
        outcome_status=outcome.status,
        outcome_sha256=outcome.sha256(),
        unfinished_work_refs=("work:alpha", "work:beta"),
        completed_work_refs=("work:done",),
        effect_attempt_refs=(),
        provenance_refs=(causal_ref, "receipt:wp900", "receipt:wp206"),
    )
    return causal, successor, seal, outcome, evidence


db = Path(sys.argv[1])
home = Path(sys.argv[2])
expected = json.loads(sys.argv[3])
resolution = resolve_unifieddb_path(env={"FRANKENSTEIN2_DB": str(db)}, home=home)
fingerprint = fingerprint_unifieddb(resolution.path)
store = CanonicalPersistentAgencyStore.open(resolution=resolution, fingerprint=fingerprint)
causal, checkpoint, seal, outcome, evidence = build_sources()
authority = UnifiedDBAuthorityRef(
    receipt_ref=CANONICAL_UNIFIEDDB_AUTHORITY_RECEIPT_REF,
    canonical_source=CANONICAL_UNIFIEDDB_AUTHORITY_SOURCE,
    fingerprint_schema=CANONICAL_UNIFIEDDB_AUTHORITY_FINGERPRINT_SCHEMA,
)
result = plan_restart_continuation_from_persisted_row(
    store,
    checkpoint_id=checkpoint.checkpoint_id,
    evidence=evidence,
    plan_id="restart-plan-wp901-g5-fresh",
    expected_evidence_sha256=evidence.sha256(),
    causal_identity=causal,
    unifieddb_authority=authority,
    whole_loop_seal=seal,
    outcome=outcome,
)
current_head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
assert current_head == expected["source_head"]
assert os.path.realpath(expected["canonical_db_path"]) == store.canonical_db_path
assert expected["db_device"] == store.db_device
assert expected["db_inode"] == store.db_inode
assert expected["authority_receipt_sha256"] == store.authority_receipt_sha256
assert checkpoint.checkpoint_id == expected["checkpoint_id"]
assert checkpoint.sha256() == expected["checkpoint_sha256"]
assert checkpoint.previous_checkpoint_id == expected["previous_checkpoint_id"]
assert seal.sha256() == expected["whole_loop_seal_sha256"]
assert evidence.sha256() == expected["restart_evidence_sha256"]
assert result.plan.disposition == CONTINUE_UNFINISHED
assert result.plan.source_checkpoint_id == checkpoint.checkpoint_id
assert result.plan.source_checkpoint_sha256 == checkpoint.sha256()
assert result.load_attestation.checkpoint_id == checkpoint.checkpoint_id
assert result.load_attestation.checkpoint_sha256 == checkpoint.sha256()
assert result.load_attestation.canonical_db_path == store.canonical_db_path
assert result.load_attestation.unifieddb_authority_receipt_sha256 == store.authority_receipt_sha256
payload = {
    "source_head": current_head,
    "checkpoint_id": checkpoint.checkpoint_id,
    "checkpoint_sha256": checkpoint.sha256(),
    "restart_plan_sha256": result.plan.sha256(),
    "row_evidence_sha256": result.load_attestation.row_evidence_sha256,
    "g5_full_restart_plan": "OBSERVED_AT_REPOSITORY_COMPONENT_SCOPE",
    "target_host_execution": "NOT_OBSERVED",
    "runtime_credit": 0,
    "whole_system_acceptance": False,
}
store.close()
print(json.dumps(payload, sort_keys=True))
'''


class WP900WP206WP901G5FreshProcessTests(unittest.TestCase):
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

    def _run(self, source: str, *args: object) -> subprocess.CompletedProcess[str]:
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
        if completed.returncode != 0:
            self.fail(
                f"subprocess failed rc={completed.returncode}\nstdout={completed.stdout}\nstderr={completed.stderr}"
            )
        return completed

    @staticmethod
    def _json_stdout(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            raise AssertionError("subprocess emitted no JSON line")
        return json.loads(lines[-1])

    def test_fresh_process_executes_current_wp901_g5_full_restart_plan(self) -> None:
        producer = self._run(PROCESS_A, self.db, self.home)
        expected = self._json_stdout(producer)
        consumer = self._run(
            PROCESS_B,
            self.db,
            self.home,
            json.dumps(expected, sort_keys=True),
        )
        observed = self._json_stdout(consumer)
        self.assertEqual(observed["checkpoint_id"], expected["checkpoint_id"])
        self.assertEqual(observed["checkpoint_sha256"], expected["checkpoint_sha256"])
        self.assertEqual(
            observed["g5_full_restart_plan"],
            "OBSERVED_AT_REPOSITORY_COMPONENT_SCOPE",
        )
        self.assertEqual(observed["target_host_execution"], "NOT_OBSERVED")
        self.assertEqual(observed["runtime_credit"], 0)
        self.assertFalse(observed["whole_system_acceptance"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
