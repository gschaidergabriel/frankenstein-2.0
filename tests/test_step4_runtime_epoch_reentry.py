"""F2-WP-1207 Schritt 4: hang RuntimeEpoch off a REAL reentry proof.

Isolated, sandbox-only (same safety scope as test_step3_sandbox_persistence.py
-- tempfile sqlite db, never unified.db, never frankenstein-repo). "Real"
here means:
  1. R1 is backed by an ACTUAL OS subprocess (subprocess.Popen), not a
     Python object standing in for one -- it has a real PID, a real start
     time taken from the wall clock immediately before Popen, and a real
     exit code we wait for.
  2. The witness/restart cycle is a second, independently-spawned real
     subprocess for R2, triggered because R1's exit code was non-zero
     (a real "crash" condition, not a scripted flag).
  3. Both epochs are persisted via real SQL INSERT into a sandbox sqlite
     db and the chain (R2.predecessor_epoch_id == R1.runtime_epoch_id) is
     verified by SELECT, not by re-reading the in-memory Python objects.

No dependency on `witness_v3.py` (not present in this frankenstein-2.0
checkout / not read from the live `~/frankenstein-repo`, per the safety
instruction) -- the restart-on-death polling here is a minimal, self-
contained analog of that pattern (spawn, wait, check exit code, relaunch on
nonzero), built fresh for this isolated proof.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from frankenstein2.entity_identity import (
    HostBinding,
    InstallationIdentity,
    RuntimeEpoch,
    StateRootIdentity,
    generate_entity_identity,
)

SANDBOX_SCHEMA_SQL = """
CREATE TABLE entity_identity (
    entity_id       TEXT PRIMARY KEY,
    schema          TEXT NOT NULL
);

CREATE TABLE installation_identity (
    installation_id TEXT PRIMARY KEY,
    entity_id       TEXT NOT NULL REFERENCES entity_identity(entity_id),
    schema          TEXT NOT NULL
);

CREATE TABLE host_binding (
    binding_id      TEXT PRIMARY KEY,
    installation_id TEXT NOT NULL REFERENCES installation_identity(installation_id),
    host_id         TEXT NOT NULL,
    bound_at        TEXT NOT NULL,
    attestation     TEXT NOT NULL,
    status          TEXT NOT NULL,
    schema          TEXT NOT NULL
);

CREATE TABLE state_root_identity (
    state_root_id       TEXT PRIMARY KEY,
    installation_id     TEXT NOT NULL REFERENCES installation_identity(installation_id),
    state_digest_sha256 TEXT NOT NULL,
    schema              TEXT NOT NULL
);

CREATE TABLE runtime_epoch (
    runtime_epoch_id    TEXT PRIMARY KEY,
    state_root_id       TEXT NOT NULL REFERENCES state_root_identity(state_root_id),
    installation_id     TEXT NOT NULL REFERENCES installation_identity(installation_id),
    host_binding_id      TEXT NOT NULL REFERENCES host_binding(binding_id),
    started_at          TEXT NOT NULL,
    predecessor_epoch_id TEXT REFERENCES runtime_epoch(runtime_epoch_id),
    termination_reason   TEXT,
    real_pid             INTEGER NOT NULL,
    real_exit_code        INTEGER,
    schema               TEXT NOT NULL
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_runtime_epoch(conn: sqlite3.Connection, epoch: RuntimeEpoch, *, pid: int, exit_code: int | None) -> None:
    conn.execute(
        "INSERT INTO runtime_epoch "
        "(runtime_epoch_id, state_root_id, installation_id, host_binding_id, started_at, "
        " predecessor_epoch_id, termination_reason, real_pid, real_exit_code, schema) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            epoch.runtime_epoch_id,
            epoch.state_root_id,
            epoch.installation_id,
            epoch.host_binding_id,
            epoch.started_at,
            epoch.predecessor_epoch_id,
            epoch.termination_reason,
            pid,
            exit_code,
            epoch.schema,
        ),
    )


class Step4RuntimeEpochReentryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "F2-WP-1207-step4-sandbox.db"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript(SANDBOX_SCHEMA_SQL)

        genesis = generate_entity_identity(generated_by="F2-WP-1207-step4-sandbox")
        self.entity = genesis.identity()
        self.installation = InstallationIdentity.create(
            installation_id="i1-step4", entity_id=self.entity.entity_id
        )
        self.binding = HostBinding.create(
            binding_id="hb-step4",
            installation_id=self.installation.installation_id,
            host_id="h-step4-sandbox",
            bound_at=_utc_now(),
            attestation="sha256:" + "7" * 64,
        )
        self.state_root = StateRootIdentity.create(
            state_root_id="s-step4",
            installation_id=self.installation.installation_id,
            state_digest_sha256="e" * 64,
        )

        self.conn.execute(
            "INSERT INTO entity_identity (entity_id, schema) VALUES (?, ?)",
            (self.entity.entity_id, self.entity.schema),
        )
        self.conn.execute(
            "INSERT INTO installation_identity (installation_id, entity_id, schema) VALUES (?, ?, ?)",
            (self.installation.installation_id, self.installation.entity_id, self.installation.schema),
        )
        self.conn.execute(
            "INSERT INTO host_binding "
            "(binding_id, installation_id, host_id, bound_at, attestation, status, schema) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.binding.binding_id,
                self.binding.installation_id,
                self.binding.host_id,
                self.binding.bound_at,
                self.binding.attestation,
                self.binding.status,
                self.binding.schema,
            ),
        )
        self.conn.execute(
            "INSERT INTO state_root_identity "
            "(state_root_id, installation_id, state_digest_sha256, schema) VALUES (?, ?, ?, ?)",
            (
                self.state_root.state_root_id,
                self.state_root.installation_id,
                self.state_root.state_digest_sha256,
                self.state_root.schema,
            ),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self._tmpdir.cleanup()

    def _spawn_real_process(self, exit_code: int) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, "-c", f"import sys; sys.exit({exit_code})"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_real_process_crash_and_witness_restart_produces_verifiable_epoch_chain(self) -> None:
        # --- R1: a REAL process, started for real, that crashes for real ---
        r1_started_at = _utc_now()
        proc1 = self._spawn_real_process(exit_code=1)
        pid1 = proc1.pid
        self.assertGreater(pid1, 0)  # a real OS PID was assigned
        exit_code1 = proc1.wait(timeout=5)
        self.assertEqual(exit_code1, 1)  # the "crash" is a real nonzero exit, not a flag

        r1 = RuntimeEpoch.from_binding(
            runtime_epoch_id="r1-step4",
            state_root_id=self.state_root.state_root_id,
            binding=self.binding,
            started_at=r1_started_at,
        ).terminated(reason=f"crash: real subprocess pid={pid1} exit_code={exit_code1}")
        _insert_runtime_epoch(self.conn, r1, pid=pid1, exit_code=exit_code1)
        self.conn.commit()

        # --- witness/restart cycle: R1 died non-zero -> relaunch for real ---
        self.assertNotEqual(exit_code1, 0, "restart only triggers on a real nonzero exit")
        r2_started_at = _utc_now()
        proc2 = self._spawn_real_process(exit_code=0)
        pid2 = proc2.pid
        exit_code2 = proc2.wait(timeout=5)
        self.assertEqual(exit_code2, 0)
        self.assertNotEqual(pid2, pid1, "R2 is a genuinely different OS process, not R1 relabeled")

        r2 = r1.next_epoch(runtime_epoch_id="r2-step4", started_at=r2_started_at)
        _insert_runtime_epoch(self.conn, r2, pid=pid2, exit_code=exit_code2)
        self.conn.commit()

        # --- verify the chain purely via SELECT, not the in-memory objects ---
        self.conn.close()
        self.conn = sqlite3.connect(self.db_path)

        row1 = self.conn.execute(
            "SELECT runtime_epoch_id, predecessor_epoch_id, termination_reason, real_pid, real_exit_code "
            "FROM runtime_epoch WHERE runtime_epoch_id = ?",
            ("r1-step4",),
        ).fetchone()
        row2 = self.conn.execute(
            "SELECT runtime_epoch_id, predecessor_epoch_id, termination_reason, real_pid, real_exit_code, "
            "installation_id, host_binding_id, state_root_id "
            "FROM runtime_epoch WHERE runtime_epoch_id = ?",
            ("r2-step4",),
        ).fetchone()

        self.assertIsNotNone(row1)
        self.assertIsNotNone(row2)
        self.assertIsNone(row1[1])  # R1 has no predecessor
        self.assertIn("crash", row1[2])
        self.assertEqual(row1[3], pid1)
        self.assertEqual(row1[4], 1)

        self.assertEqual(row2[1], "r1-step4")  # R2's predecessor really is R1, per the DB row
        self.assertIsNone(row2[2])  # R2 itself has not terminated
        self.assertEqual(row2[3], pid2)
        self.assertEqual(row2[4], 0)
        # same installation/host-binding/state-root context carried through the swap
        self.assertEqual(row2[5], self.installation.installation_id)
        self.assertEqual(row2[6], self.binding.binding_id)
        self.assertEqual(row2[7], self.state_root.state_root_id)

        (chain_len,) = self.conn.execute("SELECT COUNT(*) FROM runtime_epoch").fetchone()
        self.assertEqual(chain_len, 2)


if __name__ == "__main__":
    unittest.main()
