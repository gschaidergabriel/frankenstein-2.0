#!/usr/bin/env python3
"""Fresh-process persistence/reopen falsifier for the WP900 -> WP206 -> WP901 boundary.

Repository evidence only. A passing test proves that a WP900-sealed successor persisted
through the canonical WP206 store can be reopened by a fresh Python process and admitted
through the accepted WP901 persisted-row attestation ingress. It does not establish
VPS/target-host runtime, physical GRID10/GWT/J-Space behavior, effects, completion, or
whole-system acceptance.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


PROCESS_A = textwrap.dedent(
    r"""
    import json
    from pathlib import Path
    import sqlite3
    import sys

    from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore
    from frankenstein2.whole_loop_persistence_integration import (
        persist_sealed_successor_and_readback,
    )
    from frankenstein2.whole_persistent_loop import seal_whole_persistent_loop
    from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path
    from tests.test_whole_persistent_loop import fixture_components

    db = Path(sys.argv[1])
    home = Path(sys.argv[2])
    db.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db)
    try:
        connection.execute("CREATE TABLE f2_bootstrap(id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()

    resolution = resolve_unifieddb_path(
        env={"FRANKENSTEIN2_DB": str(db)},
        home=home,
    )
    fingerprint = fingerprint_unifieddb(resolution.path)
    store = CanonicalPersistentAgencyStore.open(
        resolution=resolution,
        fingerprint=fingerprint,
    )
    try:
        store.initialize_schema()
        (
            current,
            frame,
            contract,
            plan,
            gwt,
            gwt_evidence,
            decision,
            outcome,
            successor,
        ) = fixture_components()
        seal = seal_whole_persistent_loop(
            seal_id="whole-loop-fresh-process-reopen",
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
            provenance_refs=("test:wp900-wp206-wp901:fresh-process",),
        )
        store.write_checkpoint(current)
        evidence = persist_sealed_successor_and_readback(
            store,
            seal=seal,
            next_checkpoint=successor,
        )
        payload = evidence.as_dict()
        print(
            json.dumps(
                {
                    "checkpoint_id": successor.checkpoint_id,
                    "checkpoint_sha256": successor.sha256(),
                    "evidence_sha256": evidence.sha256(),
                    "write_observed": payload["write_observed"],
                    "typed_readback_observed": payload["typed_readback_observed"],
                    "runtime_credit": payload["runtime_credit"],
                    "whole_system_acceptance": payload["whole_system_acceptance"],
                },
                sort_keys=True,
            )
        )
    finally:
        store.close()
    """
)


PROCESS_B = textwrap.dedent(
    r"""
    import json
    from pathlib import Path
    import sys

    from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore
    from frankenstein2.restart_recovery_persisted_row_attestation import (
        attest_persisted_checkpoint_load,
    )
    from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path

    db = Path(sys.argv[1])
    home = Path(sys.argv[2])
    checkpoint_id = sys.argv[3]

    resolution = resolve_unifieddb_path(
        env={"FRANKENSTEIN2_DB": str(db)},
        home=home,
    )
    fingerprint = fingerprint_unifieddb(resolution.path)
    store = CanonicalPersistentAgencyStore.open(
        resolution=resolution,
        fingerprint=fingerprint,
    )
    try:
        checkpoint, attestation = attest_persisted_checkpoint_load(
            store,
            checkpoint_id=checkpoint_id,
        )
        payload = attestation.as_dict()
        print(
            json.dumps(
                {
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "checkpoint_sha256": checkpoint.sha256(),
                    "attestation_sha256": attestation.sha256(),
                    "row_evidence_sha256": attestation.row_evidence_sha256,
                    "transaction_snapshot_binding": payload["transaction_snapshot_binding"],
                    "target_host_execution": payload["target_host_execution"],
                    "runtime_credit": payload["runtime_credit"],
                    "whole_system_acceptance": payload["whole_system_acceptance"],
                },
                sort_keys=True,
            )
        )
    finally:
        store.close()
    """
)


class WholeLoopFreshProcessReopenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.db = self.root / "canonical" / "unified.db"
        self.repo_root = Path(__file__).resolve().parents[1]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        import_roots = [
            str(self.repo_root / "src"),
            str(self.repo_root),
        ]
        prior = env.get("PYTHONPATH")
        if prior:
            import_roots.append(prior)
        env["PYTHONPATH"] = os.pathsep.join(import_roots)
        return env

    def _run(self, script: str, *args: str) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, "-c", script, *args],
            cwd=self.repo_root,
            env=self._env(),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                f"fresh-process discriminator failed with rc={completed.returncode}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertTrue(lines, msg="subprocess emitted no JSON evidence")
        return json.loads(lines[-1])

    def test_successor_survives_exit_and_enters_wp901_from_fresh_process(self) -> None:
        first = self._run(PROCESS_A, str(self.db), str(self.home))

        self.assertTrue(first["write_observed"])
        self.assertTrue(first["typed_readback_observed"])
        self.assertEqual(first["runtime_credit"], 0)
        self.assertFalse(first["whole_system_acceptance"])

        second = self._run(
            PROCESS_B,
            str(self.db),
            str(self.home),
            str(first["checkpoint_id"]),
        )

        self.assertEqual(second["checkpoint_id"], first["checkpoint_id"])
        self.assertEqual(second["checkpoint_sha256"], first["checkpoint_sha256"])
        self.assertEqual(second["transaction_snapshot_binding"], "OBSERVED")
        self.assertTrue(second["row_evidence_sha256"])
        self.assertTrue(second["attestation_sha256"])
        self.assertEqual(second["target_host_execution"], "NOT_OBSERVED")
        self.assertEqual(second["runtime_credit"], 0)
        self.assertFalse(second["whole_system_acceptance"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
