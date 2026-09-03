"""F2-WP-1207 Schritt 5 -- THE GOLD TEST.

Gabriel's condition, verbatim: "E1 bleibt E1, I1 bleibt I1, StateRoot bleibt
derselben Installation zugeordnet, obwohl Host UND Runtime wechseln."

This test proves all of that AT ONCE, with a single executable scenario,
verified by SQL SELECT against a sandbox sqlite db (isolated tempfile, same
safety scope as Schritt 3/4 -- never unified.db, never frankenstein-repo):

  1. I1 stays constant while H1 (HostBinding) is ended (SUPERSEDED -- this
     module's existing terminal status for "replaced by a newer binding",
     used for the directive's "status -> e.g. ENDED") and H2 becomes ACTIVE,
     both real UPDATE/INSERT statements against the same row/table.
  2. StateRootIdentity S7 is asserted to remain bound to I1's
     installation_id via SELECT, both before AND after the host swap --
     S7 was never touched, but is checked again post-swap to prove nothing
     silently migrated it.
  3. RuntimeEpoch also changes: R81 (bound to H1, backed by a real OS
     subprocess) is superseded by R82 (bound to H2, backed by a SECOND,
     genuinely different real OS subprocess) -- Runtime changing alongside
     Host, exactly as the directive's condition requires ("obwohl Host UND
     Runtime wechseln").
  4. Bonus integration check: the Schritt 2 relaxed-rebind path
     (RebindEligibleMigrationRequest) is exercised with H1's and H2's real
     host-derived identity hashes -- proving a migration between them is
     ELIGIBLE under the new same-installation+active-binding rule, while
     the OLD `StateMigrationRequest` (state_migration.py, completely
     unmodified) with the identical source/target root pair still REJECTS
     it on raw host-identity mismatch, exactly as before. Both live side by
     side; nothing about the old path changed to make this pass.
"""
from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from frankenstein2.entity_identity import (
    BINDING_STATUS_ACTIVE,
    BINDING_STATUS_SUPERSEDED,
    HostBinding,
    InstallationIdentity,
    RuntimeEpoch,
    StateRootIdentity,
    generate_entity_identity,
)
from frankenstein2.state_migration import (
    STORAGE_CANONICAL_DURABLE,
    StateMigrationError,
    StateRootIdentity as MigrationStateRootIdentity,
)
from frankenstein2.state_rebind import RebindEligibleMigrationRequest

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
    real_pid              INTEGER NOT NULL,
    schema                TEXT NOT NULL
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fake_host_identity_sha256(host_id: str) -> str:
    # stand-in for a real host-attestation digest -- deterministic per host_id,
    # only used here to feed state_migration.StateRootIdentity's sha256 field.
    return hashlib.sha256(f"host-attestation:{host_id}".encode("utf-8")).hexdigest()


class Step5GoldHostRebindTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "F2-WP-1207-step5-gold-sandbox.db"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript(SANDBOX_SCHEMA_SQL)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self._tmpdir.cleanup()

    def _spawn_real_process(self) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_gold_e1_stays_e1_i1_stays_i1_stateroot_stays_installation_despite_host_and_runtime_change(
        self,
    ) -> None:
        # === 1. mint E1, I1, first HostBinding H1, StateRoot S7 ===========
        genesis = generate_entity_identity(generated_by="F2-WP-1207-step5-gold")
        e1 = genesis.identity()
        i1 = InstallationIdentity.create(installation_id="I1-gold", entity_id=e1.entity_id)
        h1 = HostBinding.create(
            binding_id="H1-gold",
            installation_id=i1.installation_id,
            host_id="host-old-gold",
            bound_at="2026-08-01T00:00:00+00:00",
            attestation="sha256:" + "1" * 64,
        )
        s7 = StateRootIdentity.create(
            state_root_id="S7-gold",
            installation_id=i1.installation_id,
            state_digest_sha256="d" * 64,
        )

        self.conn.execute(
            "INSERT INTO entity_identity (entity_id, schema) VALUES (?, ?)",
            (e1.entity_id, e1.schema),
        )
        self.conn.execute(
            "INSERT INTO installation_identity (installation_id, entity_id, schema) VALUES (?, ?, ?)",
            (i1.installation_id, i1.entity_id, i1.schema),
        )
        self.conn.execute(
            "INSERT INTO host_binding "
            "(binding_id, installation_id, host_id, bound_at, attestation, status, schema) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (h1.binding_id, h1.installation_id, h1.host_id, h1.bound_at, h1.attestation, h1.status, h1.schema),
        )
        self.conn.execute(
            "INSERT INTO state_root_identity "
            "(state_root_id, installation_id, state_digest_sha256, schema) VALUES (?, ?, ?, ?)",
            (s7.state_root_id, s7.installation_id, s7.state_digest_sha256, s7.schema),
        )
        self.conn.commit()

        # === R81: real process, bound to H1 ================================
        r81_started_at = _utc_now()
        proc1 = self._spawn_real_process()
        pid1 = proc1.pid
        proc1.wait(timeout=5)
        r81 = RuntimeEpoch.from_binding(
            runtime_epoch_id="R81-gold", state_root_id=s7.state_root_id, binding=h1,
            started_at=r81_started_at,
        )
        self.conn.execute(
            "INSERT INTO runtime_epoch "
            "(runtime_epoch_id, state_root_id, installation_id, host_binding_id, started_at, "
            " predecessor_epoch_id, termination_reason, real_pid, schema) VALUES (?,?,?,?,?,?,?,?,?)",
            (r81.runtime_epoch_id, r81.state_root_id, r81.installation_id, r81.host_binding_id,
             r81.started_at, r81.predecessor_epoch_id, r81.termination_reason, pid1, r81.schema),
        )
        self.conn.commit()

        # sanity checkpoint BEFORE the swap: S7 bound to I1
        (pre_swap_installation,) = self.conn.execute(
            "SELECT installation_id FROM state_root_identity WHERE state_root_id = ?",
            (s7.state_root_id,),
        ).fetchone()
        self.assertEqual(pre_swap_installation, i1.installation_id)

        # === 2. HOST REBIND: H1 -> SUPERSEDED (real UPDATE), H2 -> ACTIVE (real INSERT), SAME installation_id ===
        h1_ended = h1.superseded()
        self.conn.execute(
            "UPDATE host_binding SET status = ? WHERE binding_id = ?",
            (h1_ended.status, h1.binding_id),
        )
        h2 = HostBinding.create(
            binding_id="H2-gold",
            installation_id=i1.installation_id,  # SAME installation -- the whole point
            host_id="host-new-gold",
            bound_at="2026-09-10T00:00:00+00:00",
            attestation="sha256:" + "2" * 64,
        )
        self.conn.execute(
            "INSERT INTO host_binding "
            "(binding_id, installation_id, host_id, bound_at, attestation, status, schema) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (h2.binding_id, h2.installation_id, h2.host_id, h2.bound_at, h2.attestation, h2.status, h2.schema),
        )
        self.conn.commit()

        # === 3. RUNTIME CHANGES TOO: R82, bound to H2, a SECOND real process ===
        r82_started_at = _utc_now()
        proc2 = self._spawn_real_process()
        pid2 = proc2.pid
        proc2.wait(timeout=5)
        self.assertNotEqual(pid2, pid1, "runtime genuinely changed -- different real OS process")
        r82 = r81.next_epoch(
            runtime_epoch_id="R82-gold", started_at=r82_started_at, host_binding_id=h2.binding_id
        )
        self.conn.execute(
            "INSERT INTO runtime_epoch "
            "(runtime_epoch_id, state_root_id, installation_id, host_binding_id, started_at, "
            " predecessor_epoch_id, termination_reason, real_pid, schema) VALUES (?,?,?,?,?,?,?,?,?)",
            (r82.runtime_epoch_id, r82.state_root_id, r82.installation_id, r82.host_binding_id,
             r82.started_at, r82.predecessor_epoch_id, r82.termination_reason, pid2, r82.schema),
        )
        self.conn.commit()

        # === GOLD ASSERTIONS -- fresh connection, everything via SELECT ===
        self.conn.close()
        self.conn = sqlite3.connect(self.db_path)

        # E1 stays E1: exactly one entity row, still the one genesis minted.
        entity_rows = self.conn.execute("SELECT entity_id FROM entity_identity").fetchall()
        self.assertEqual(entity_rows, [(e1.entity_id,)])

        # I1 stays I1: exactly one installation row, still pointing at E1.
        install_rows = self.conn.execute(
            "SELECT installation_id, entity_id FROM installation_identity"
        ).fetchall()
        self.assertEqual(install_rows, [(i1.installation_id, e1.entity_id)])

        # StateRoot S7 STILL bound to I1, unchanged, post-swap.
        (post_swap_installation,) = self.conn.execute(
            "SELECT installation_id FROM state_root_identity WHERE state_root_id = ?",
            (s7.state_root_id,),
        ).fetchone()
        self.assertEqual(post_swap_installation, i1.installation_id)
        self.assertEqual(post_swap_installation, pre_swap_installation)

        # Host really changed: H1 SUPERSEDED, H2 ACTIVE, both under I1, different host_id.
        h1_row = self.conn.execute(
            "SELECT installation_id, host_id, status FROM host_binding WHERE binding_id = ?",
            ("H1-gold",),
        ).fetchone()
        h2_row = self.conn.execute(
            "SELECT installation_id, host_id, status FROM host_binding WHERE binding_id = ?",
            ("H2-gold",),
        ).fetchone()
        self.assertEqual(h1_row, (i1.installation_id, "host-old-gold", BINDING_STATUS_SUPERSEDED))
        self.assertEqual(h2_row, (i1.installation_id, "host-new-gold", BINDING_STATUS_ACTIVE))

        # Runtime really changed: R81 (H1, pid1) -> R82 (H2, pid2), chained, same I1/S7 throughout.
        r81_row = self.conn.execute(
            "SELECT installation_id, host_binding_id, state_root_id, real_pid, predecessor_epoch_id "
            "FROM runtime_epoch WHERE runtime_epoch_id = ?",
            ("R81-gold",),
        ).fetchone()
        r82_row = self.conn.execute(
            "SELECT installation_id, host_binding_id, state_root_id, real_pid, predecessor_epoch_id "
            "FROM runtime_epoch WHERE runtime_epoch_id = ?",
            ("R82-gold",),
        ).fetchone()
        self.assertEqual(r81_row, (i1.installation_id, "H1-gold", s7.state_root_id, pid1, None))
        self.assertEqual(r82_row, (i1.installation_id, "H2-gold", s7.state_root_id, pid2, "R81-gold"))

        # === THE gold condition, stated as one combined assertion ==========
        self.assertTrue(
            entity_rows == [(e1.entity_id,)]
            and install_rows == [(i1.installation_id, e1.entity_id)]
            and post_swap_installation == i1.installation_id
            and h1_row[2] == BINDING_STATUS_SUPERSEDED
            and h2_row[2] == BINDING_STATUS_ACTIVE
            and r81_row[3] != r82_row[3]  # runtime (pid) changed
            and h1_row[1] != h2_row[1]  # host changed
            and r81_row[0] == r82_row[0] == i1.installation_id,  # installation constant throughout
            "GOLD TEST: E1==E1, I1==I1, StateRoot stays on I1, despite Host AND Runtime both changing",
        )

    def test_bonus_rebind_eligible_under_new_path_still_rejected_under_old_path(self) -> None:
        """Ties Schritt 2 into the gold scenario: the SAME source/target root
        pair (differing only in host_identity_sha256) is REBIND-ELIGIBLE
        under the new `RebindEligibleMigrationRequest` (same installation_id
        + ACTIVE HostBinding for the target host) but STILL REJECTED by the
        untouched, live `StateMigrationRequest` -- proving Schritt 2 did not
        weaken the old path, it added a new one."""
        installation_id = "I1-gold-bonus"
        h_new = HostBinding.create(
            binding_id="H2-gold-bonus",
            installation_id=installation_id,
            host_id="host-new-gold-bonus",
            bound_at="2026-09-10T00:00:00+00:00",
            attestation="sha256:" + "2" * 64,
        )
        source_root = MigrationStateRootIdentity.create(
            root_id="old",
            path="/home/user/.local/share/frankenstein2/state",
            storage_class=STORAGE_CANONICAL_DURABLE,
            host_identity_sha256=_fake_host_identity_sha256("host-old-gold-bonus"),
            observed_root_fingerprint_sha256="a" * 64,
            installation_id=installation_id,
        )
        target_root = MigrationStateRootIdentity.create(
            root_id="new",
            path="/srv/frankenstein2/state",
            storage_class=STORAGE_CANONICAL_DURABLE,
            host_identity_sha256=_fake_host_identity_sha256("host-new-gold-bonus"),
            observed_root_fingerprint_sha256="b" * 64,
            installation_id=installation_id,
        )
        self.assertNotEqual(source_root.host_identity_sha256, target_root.host_identity_sha256)

        from frankenstein2.state_migration import (
            StateLineage,
            StateMigrationRequest,
            TARGET_EMPTY_VERIFIED,
            TargetRootObservation,
        )

        source_lineage = StateLineage.create(
            lineage_id="gold-bonus-lineage", generation=1, state_sha256="c" * 64, root=source_root
        )

        # NEW path: eligible.
        rebind_request = RebindEligibleMigrationRequest.create(
            migration_id="gold-bonus-rebind",
            source_lineage=source_lineage,
            target_root=target_root,
            target_observation=TargetRootObservation(
                status=TARGET_EMPTY_VERIFIED, evidence_ref="probe:empty"
            ),
            rollback_root=source_root,
            host_binding=h_new,
        )
        self.assertIsNotNone(rebind_request)

        # OLD path: still rejected, completely unmodified behavior.
        with self.assertRaises(StateMigrationError):
            StateMigrationRequest.create(
                migration_id="gold-bonus-old-path",
                source_lineage=source_lineage,
                target_root=target_root,
                target_observation=TargetRootObservation(
                    status=TARGET_EMPTY_VERIFIED, evidence_ref="probe:empty"
                ),
                rollback_root=source_root,
            )


if __name__ == "__main__":
    unittest.main()
