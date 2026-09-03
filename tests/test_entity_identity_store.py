"""F2-WP-1207 continuation: the cross-instance invariant is enforced BY THE
DATABASE, not by Python caller discipline.

The directive, verbatim: "erzwinge 'maximal EINE ACTIVE HostBinding pro
installation_id' NICHT nur als Python-Prüfung im Aufrufer-Code, sondern
ATOMAR im Persistenzlayer selbst" and -- the part that makes it a proof --
"Zeig dass ein naiver Bypass-Versuch (direkter SQL-INSERT unter Umgehung der
Python-Wrapper-Funktion) trotzdem von der DB abgelehnt wird -- das ist der
eigentliche Beweis für 'atomar erzwungen'".

Mechanism: a partial UNIQUE index (SQLite >= 3.8.0)
    CREATE UNIQUE INDEX ux_host_binding_one_active_per_installation
        ON host_binding (installation_id) WHERE status = 'ACTIVE'
so the engine itself refuses any INSERT/UPDATE that would leave two ACTIVE
rows for one installation_id -- regardless of which code path (wrapper, raw
SQL, second connection, another process) issues it.

SAFETY, unchanged from Schritt 3/4/5: every database in this file is a
`tempfile`-scoped sandbox sqlite file, created and destroyed per test. This
NEVER touches `~/.local/share/agentzero/unified.db` and NEVER touches
`~/frankenstein-repo`.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from frankenstein2.entity_identity import (
    BINDING_STATUS_ACTIVE,
    BINDING_STATUS_REVOKED,
    BINDING_STATUS_SUPERSEDED,
    HostBinding,
    InstallationIdentity,
    RuntimeEpoch,
    StateRootIdentity,
    generate_entity_identity,
)
from frankenstein2.entity_identity_store import (
    HOST_BINDING_ONE_ACTIVE_PER_INSTALLATION_INDEX_NAME,
    IdentityStoreError,
    active_host_binding,
    bind_active_host,
    connect,
    create_schema,
    ensure_host_binding_atomicity,
    insert_host_binding,
    insert_installation,
    insert_runtime_epoch,
    insert_state_root,
    set_host_binding_status,
)

_INDEX_NAME = "ux_host_binding_one_active_per_installation"
# status value the dataclass would already refuse -- used to prove the DB's
# CHECK constraint is an independent, engine-level backstop
BINDING_STATUS_UNKNOWN = "ENDED"


class EntityIdentityStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "F2-WP-1207-atomic-binding-sandbox.db"
        self.conn = connect(self.db_path)
        create_schema(self.conn)
        # Base fixture: one entity, one installation, one ACTIVE binding.
        self.genesis = generate_entity_identity(generated_by="F2-WP-1207-atomic-binding")
        self.installation = InstallationIdentity.create(
            installation_id="I1-atomic", entity_id=self.genesis.entity_id
        )
        self.conn.execute(
            "INSERT INTO entity_identity (entity_id, schema, created_at, generated_by, "
            "entropy_bytes) VALUES (?,?,?,?,?)",
            (
                self.genesis.entity_id,
                self.genesis.schema,
                self.genesis.created_at,
                self.genesis.generated_by,
                self.genesis.entropy_bytes,
            ),
        )
        self.conn.execute(
            "INSERT INTO installation_identity (installation_id, entity_id, schema) VALUES (?,?,?)",
            (
                self.installation.installation_id,
                self.installation.entity_id,
                self.installation.schema,
            ),
        )

    def tearDown(self) -> None:
        self.conn.close()
        self._tmpdir.cleanup()

    # -- helpers ----------------------------------------------------------

    def _binding(self, binding_id: str, host_id: str, status: str = BINDING_STATUS_ACTIVE):
        return HostBinding.create(
            binding_id=binding_id,
            installation_id=self.installation.installation_id,
            host_id=host_id,
            bound_at="2026-09-03T00:00:00+00:00",
            attestation="sha256:" + "1" * 64,
            status=status,
        )

    def _raw_insert_binding_sql(self, binding) -> tuple[str, tuple]:
        return (
            "INSERT INTO host_binding "
            "(binding_id, installation_id, host_id, bound_at, attestation, status, schema) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                binding.binding_id,
                binding.installation_id,
                binding.host_id,
                binding.bound_at,
                binding.attestation,
                binding.status,
                binding.schema,
            ),
        )

    def _active_count(self, conn, installation_id: str) -> int:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM host_binding WHERE installation_id = ? AND status = ?",
            (installation_id, BINDING_STATUS_ACTIVE),
        ).fetchone()
        return count

    # -- the index is real schema, not a runtime flag ----------------------

    def test_index_exists_as_partial_unique_index_and_survives_reopen(self) -> None:
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name = ?", (_INDEX_NAME,)
        ).fetchone()
        self.assertIsNotNone(row, "partial unique index must exist in sqlite_master")
        sql = row[0]
        self.assertIn("UNIQUE", sql.upper())
        self.assertIn("installation_id", sql)
        self.assertIn("status = 'ACTIVE'", sql.replace('"', "'"))
        # durable, not connection-local: reopen the file and check again
        self.conn.close()
        self.conn = connect(self.db_path)
        (name,) = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name = ?", (_INDEX_NAME,)
        ).fetchone()
        self.assertEqual(name, _INDEX_NAME)

    # -- wrapper path (the uninteresting one) ------------------------------

    def test_second_active_insert_via_wrapper_rejected_by_engine(self) -> None:
        insert_host_binding(self.conn, self._binding("H1", "host-1"))
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            insert_host_binding(self.conn, self._binding("H2", "host-2"))
        self.assertIn("UNIQUE constraint failed", str(ctx.exception))

    # -- THE PROOF: every wrapper bypassed, engine still refuses -----------

    def test_naive_raw_sql_insert_bypassing_all_wrappers_still_rejected(self) -> None:
        """The directive's core demand: a hand-written INSERT that knows
        nothing about the Python layer must still be refused BY THE DATABASE."""
        insert_host_binding(self.conn, self._binding("H1", "host-1"))
        sql, params = self._raw_insert_binding_sql(self._binding("H2-raw", "host-2"))
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(sql, params)
        self.assertIn("UNIQUE constraint failed", str(ctx.exception))
        # nothing half-written
        self.assertEqual(self._active_count(self.conn, self.installation.installation_id), 1)
        (only,) = self.conn.execute(
            "SELECT binding_id FROM host_binding WHERE status = ?",
            (BINDING_STATUS_ACTIVE,),
        ).fetchone()
        self.assertEqual(only, "H1")

    def test_naive_raw_sql_update_flip_to_active_still_rejected(self) -> None:
        """INSERT is not the only bypass: flipping a dormant row to ACTIVE by
        raw UPDATE is the equally naive second attempt."""
        insert_host_binding(self.conn, self._binding("H1", "host-1"))
        insert_host_binding(
            self.conn, self._binding("H2-dormant", "host-2", BINDING_STATUS_SUPERSEDED)
        )
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "UPDATE host_binding SET status = ? WHERE binding_id = ?",
                (BINDING_STATUS_ACTIVE, "H2-dormant"),
            )
        self.assertIn("UNIQUE constraint failed", str(ctx.exception))
        # and the legal order of the same two statements works: end old first
        set_host_binding_status(self.conn, binding_id="H1", status=BINDING_STATUS_SUPERSEDED)
        self.conn.execute(
            "UPDATE host_binding SET status = ? WHERE binding_id = ?",
            (BINDING_STATUS_ACTIVE, "H2-dormant"),
        )
        self.assertEqual(self._active_count(self.conn, self.installation.installation_id), 1)

    def test_second_connection_raw_sql_still_rejected_in_and_out_of_tx(self) -> None:
        """Cross-instance by construction: a DIFFERENT connection (what a second
        process would get after opening the same file) issuing raw SQL."""
        insert_host_binding(self.conn, self._binding("H1", "host-1"))
        other = connect(self.db_path)
        try:
            sql, params = self._raw_insert_binding_sql(self._binding("H2-other", "host-2"))
            # plain autocommit statement
            with self.assertRaises(sqlite3.IntegrityError) as ctx:
                other.execute(sql, params)
            self.assertIn("UNIQUE constraint failed", str(ctx.exception))
            # ...and inside its own explicit transaction: still rejected at the
            # statement, not deferred to some commit-time hope
            other.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.IntegrityError):
                other.execute(sql, params)
            other.execute("ROLLBACK")
            # conn A's view is untouched throughout
            self.assertEqual(
                self._active_count(self.conn, self.installation.installation_id), 1
            )
        finally:
            other.close()

    # -- the legitimate path: one atomic swap, no observable window --------

    def test_bind_active_host_swaps_in_one_transaction(self) -> None:
        insert_host_binding(self.conn, self._binding("H1", "host-1"))
        superseded = bind_active_host(self.conn, self._binding("H2", "host-2"))
        self.assertEqual(superseded, 1)
        rows = self.conn.execute(
            "SELECT binding_id, status FROM host_binding ORDER BY binding_id"
        ).fetchall()
        self.assertEqual(
            rows,
            [("H1", BINDING_STATUS_SUPERSEDED), ("H2", BINDING_STATUS_ACTIVE)],
        )
        self.assertEqual(self._active_count(self.conn, self.installation.installation_id), 1)

    def test_no_other_connection_ever_observes_zero_or_two_active_rows(self) -> None:
        """Atomicity as observed from OUTSIDE the writing connection: while the
        swap transaction is open (old already marked SUPERSEDED, new not yet
        inserted), a second connection still sees exactly the old binding as
        the single ACTIVE row -- never a half-state."""
        insert_host_binding(self.conn, self._binding("H1", "host-1"))
        other = connect(self.db_path)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                "UPDATE host_binding SET status = ? WHERE binding_id = ? AND status = ?",
                (BINDING_STATUS_SUPERSEDED, "H1", BINDING_STATUS_ACTIVE),
            )
            # mid-transaction, from the OTHER connection: old still the one ACTIVE
            (mid_active,) = other.execute(
                "SELECT binding_id FROM host_binding WHERE status = ?",
                (BINDING_STATUS_ACTIVE,),
            ).fetchone()
            self.assertEqual(mid_active, "H1")
            self.conn.execute(
                "INSERT INTO host_binding "
                "(binding_id, installation_id, host_id, bound_at, attestation, status, schema) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    "H2",
                    self.installation.installation_id,
                    "host-2",
                    "2026-09-03T00:00:00+00:00",
                    "sha256:" + "1" * 64,
                    BINDING_STATUS_ACTIVE,
                    "FRANKENSTEIN2_HOST_BINDING/v1",
                ),
            )
            self.conn.execute("COMMIT")
            # post-commit: exactly one ACTIVE, and it is the new one
            (post_active,) = other.execute(
                "SELECT binding_id FROM host_binding WHERE status = ?",
                (BINDING_STATUS_ACTIVE,),
            ).fetchone()
            self.assertEqual(post_active, "H2")
        finally:
            other.close()

    def test_supersede_update_that_would_leave_two_active_is_rejected_mid_swap(self) -> None:
        """Even the *inverse* ordering attempt (insert new ACTIVE first, then
        try to retire the old one) cannot create the two-ACTIVE moment: the
        INSERT itself dies."""
        insert_host_binding(self.conn, self._binding("H1", "host-1"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute(*self._raw_insert_binding_sql(self._binding("H2", "host-2")))
            finally:
                self.conn.execute("ROLLBACK")
        self.assertEqual(self._active_count(self.conn, self.installation.installation_id), 1)

    # -- scope of the invariant -------------------------------------------

    def test_terminal_history_is_not_restricted_by_the_partial_index(self) -> None:
        insert_host_binding(self.conn, self._binding("H1", "host-1"))
        for i in range(5):
            bind_active_host(self.conn, self._binding(f"H{10 + i}", f"host-{10 + i}"))
        insert_host_binding(self.conn, self._binding("HR", "host-r", BINDING_STATUS_REVOKED))
        (total,) = self.conn.execute("SELECT COUNT(*) FROM host_binding").fetchone()
        self.assertEqual(total, 7)  # H1, H10..H14 (H14 = the ACTIVE one), HR
        self.assertEqual(self._active_count(self.conn, self.installation.installation_id), 1)

    def test_two_installations_each_keep_their_own_active_binding(self) -> None:
        """The invariant is PER installation_id, not global: a second
        installation of the same entity legitimately has its own ACTIVE
        binding."""
        second = InstallationIdentity.create(
            installation_id="I2-atomic", entity_id=self.genesis.entity_id
        )
        self.conn.execute(
            "INSERT INTO installation_identity (installation_id, entity_id, schema) VALUES (?,?,?)",
            (second.installation_id, second.entity_id, second.schema),
        )
        insert_host_binding(self.conn, self._binding("H1", "host-1"))
        self.conn.execute(
            "INSERT INTO host_binding "
            "(binding_id, installation_id, host_id, bound_at, attestation, status, schema) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                "H9",
                second.installation_id,
                "host-9",
                "2026-09-03T00:00:00+00:00",
                "sha256:" + "1" * 64,
                BINDING_STATUS_ACTIVE,
                "FRANKENSTEIN2_HOST_BINDING/v1",
            ),
        )
        self.assertEqual(self._active_count(self.conn, "I1-atomic"), 1)
        self.assertEqual(self._active_count(self.conn, "I2-atomic"), 1)

    # -- other engine-level hardening that came with the store ------------

    def test_check_constraint_rejects_unknown_status_via_raw_sql(self) -> None:
        binding = self._binding("HX", "host-x")
        sql, params = self._raw_insert_binding_sql(binding)
        # bypass the dataclass's own status validation by hand-writing the row
        bad = tuple(BINDING_STATUS_UNKNOWN if p == binding.status else p for p in params)
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(sql, bad)
        self.assertIn("CHECK", str(ctx.exception))

    def test_foreign_keys_are_actively_enforced_in_the_store(self) -> None:
        (fk,) = self.conn.execute("PRAGMA foreign_keys").fetchone()
        self.assertEqual(fk, 1, "store connections must turn FK enforcement on")
        root = StateRootIdentity.create(
            state_root_id="S1",
            installation_id="no-such-installation",
            state_digest_sha256="d" * 64,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            insert_state_root(self.conn, root)
        epoch = RuntimeEpoch.from_binding(
            runtime_epoch_id="R1",
            state_root_id="no-such-root",
            binding=self._binding("H1", "host-1"),
            started_at="2026-09-03T00:00:00+00:00",
        )
        with self.assertRaises(sqlite3.IntegrityError):
            insert_runtime_epoch(self.conn, epoch)

    # -- retro-fitting an older sandbox db (Schritt-5 schema, no index) ----

    def test_ensure_host_binding_atomicity_hardens_preexisting_sandbox_db(self) -> None:
        """A Schritt-5-style sandbox db (plain schema, no invariant index, no
        store involved) can be retro-fitted by adding exactly the index."""
        with tempfile.TemporaryDirectory() as legacy_dir:
            legacy = sqlite3.connect(Path(legacy_dir) / "legacy-sandbox.db")
            try:
                legacy.executescript(
                    """
                    CREATE TABLE host_binding (binding_id TEXT PRIMARY KEY,
                        installation_id TEXT NOT NULL, host_id TEXT NOT NULL,
                        bound_at TEXT NOT NULL, attestation TEXT NOT NULL,
                        status TEXT NOT NULL, schema TEXT NOT NULL);
                    INSERT INTO host_binding VALUES
                     ('H1','I1-atomic','host-1','2026-09-03T00:00:00+00:00','a','ACTIVE','x');
                    """
                )
                ensure_host_binding_atomicity(legacy)
                with self.assertRaises(sqlite3.IntegrityError):
                    legacy.execute(
                        "INSERT INTO host_binding VALUES "
                        "('H2','I1-atomic','host-2','2026-09-03T00:00:00+00:00','a','ACTIVE','x')"
                    )
                # non-ACTIVE rows for the same installation stay legal
                legacy.execute(
                    "INSERT INTO host_binding VALUES "
                    "('H3','I1-atomic','host-3','2026-09-03T00:00:00+00:00','a','SUPERSEDED','x')"
                )
            finally:
                legacy.close()

    def test_ensure_host_binding_atomicity_refuses_index_over_violating_data(self) -> None:
        """A db that ALREADY has two ACTIVE rows for one installation cannot be
        retro-fitted silently -- the CREATE INDEX itself fails, which surfaces
        the pre-existing violation instead of hiding it."""
        with tempfile.TemporaryDirectory() as broken_dir:
            broken = sqlite3.connect(Path(broken_dir) / "broken-sandbox.db")
            try:
                broken.executescript(
                    """
                    CREATE TABLE host_binding (binding_id TEXT PRIMARY KEY,
                        installation_id TEXT NOT NULL, host_id TEXT NOT NULL,
                        bound_at TEXT NOT NULL, attestation TEXT NOT NULL,
                        status TEXT NOT NULL, schema TEXT NOT NULL);
                    INSERT INTO host_binding VALUES
                     ('HA','I1-atomic','host-a','2026-09-03T00:00:00+00:00','a','ACTIVE','x');
                    INSERT INTO host_binding VALUES
                     ('HB','I1-atomic','host-b','2026-09-03T00:00:00+00:00','a','ACTIVE','x');
                    """
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    ensure_host_binding_atomicity(broken)
            finally:
                broken.close()

    def test_rejection_is_caused_by_the_partial_index_not_something_else(self) -> None:
        """Causality, not correlation: the SAME raw INSERT that the engine
        refuses while the partial index exists succeeds once the index is
        dropped -- so the refusal really is the invariant, and it returns the
        moment the index does. Also the discriminating evidence that this is
        the PARTIAL index and not a plain unique index on installation_id: a
        second non-ACTIVE row for the same installation is perfectly legal."""
        insert_host_binding(self.conn, self._binding("H1", "host-1"))
        sql, params = self._raw_insert_binding_sql(self._binding("H2", "host-2"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(sql, params)
        self.conn.execute(*self._raw_insert_binding_sql(
            self._binding("H2-dormant", "host-2", BINDING_STATUS_SUPERSEDED)
        ))
        self.conn.execute(f"DROP INDEX {_INDEX_NAME}")
        self.conn.execute(sql, params)  # invariant gone -> bypass works now
        self.assertEqual(self._active_count(self.conn, self.installation.installation_id), 2)
        # Recreating the index over data that CURRENTLY violates it must fail
        # (proven separately by test_ensure_host_binding_atomicity_refuses_
        # index_over_violating_data) -- so first repair the data the same way
        # any real recovery would: demote one ACTIVE row by raw UPDATE (still
        # no wrapper), leaving exactly one ACTIVE row again.
        self.conn.execute(
            "UPDATE host_binding SET status = ? WHERE binding_id = ?",
            (BINDING_STATUS_SUPERSEDED, "H1"),
        )
        self.assertEqual(self._active_count(self.conn, self.installation.installation_id), 1)
        ensure_host_binding_atomicity(self.conn)  # invariant back, data now compliant
        sql3, params3 = self._raw_insert_binding_sql(self._binding("H3", "host-3"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(sql3, params3)

    # -- Gold-Test flow under the index -----------------------------------

    def test_step5_gold_rebind_flow_still_works_under_the_index(self) -> None:
        """The Gold-Test's exact Host-swap order (H1 -> SUPERSEDED via UPDATE,
        then H2 -> ACTIVE via INSERT, same installation) must remain legal with
        the invariant in place -- the invariant must not break the scenario it
        is meant to protect."""
        insert_host_binding(self.conn, self._binding("H1-gold", "host-old-gold"))
        root = StateRootIdentity.create(
            state_root_id="S7-gold",
            installation_id=self.installation.installation_id,
            state_digest_sha256="d" * 64,
        )
        insert_state_root(self.conn, root)
        r81 = RuntimeEpoch.from_binding(
            runtime_epoch_id="R81-gold",
            state_root_id=root.state_root_id,
            binding=self._binding("H1-gold", "host-old-gold"),
            started_at="2026-09-03T00:00:00+00:00",
        )
        insert_runtime_epoch(self.conn, r81)
        # H1 -> SUPERSEDED (real UPDATE), H2 -> ACTIVE (real INSERT)
        set_host_binding_status(
            self.conn, binding_id="H1-gold", status=BINDING_STATUS_SUPERSEDED
        )
        insert_host_binding(self.conn, self._binding("H2-gold", "host-new-gold"))
        r82 = r81.next_epoch(
            runtime_epoch_id="R82-gold",
            started_at="2026-09-03T01:00:00+00:00",
            host_binding_id="H2-gold",
        )
        insert_runtime_epoch(self.conn, r82)
        self.assertEqual(self._active_count(self.conn, self.installation.installation_id), 1)
        # ...and a third ACTIVE for the same installation is still impossible
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(*self._raw_insert_binding_sql(self._binding("H3", "host-3")))

    # -- readback helper ---------------------------------------------------

    def test_active_host_binding_readback(self) -> None:
        self.assertIsNone(active_host_binding(self.conn, self.installation.installation_id))
        insert_host_binding(self.conn, self._binding("H1", "host-1"))
        active = active_host_binding(self.conn, self.installation.installation_id)
        self.assertEqual(active["binding_id"], "H1")
        self.assertEqual(active["host_id"], "host-1")
        set_host_binding_status(self.conn, binding_id="H1", status=BINDING_STATUS_REVOKED)
        self.assertIsNone(active_host_binding(self.conn, self.installation.installation_id))

    def test_set_host_binding_status_fails_closed_on_unknown_status(self) -> None:
        insert_host_binding(self.conn, self._binding("H1", "host-1"))
        with self.assertRaises(IdentityStoreError):
            set_host_binding_status(self.conn, binding_id="H1", status="ENDED")
        with self.assertRaises(IdentityStoreError):
            set_host_binding_status(self.conn, binding_id="does-not-exist", status=BINDING_STATUS_ACTIVE)


if __name__ == "__main__":
    unittest.main()
