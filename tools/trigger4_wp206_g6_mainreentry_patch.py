#!/usr/bin/env python3
"""Transplant the measured WP206 G6 owned-surface guard onto exact current main.

This is a bounded, anchor-checked continuation of the SAME active F2-WP-206 generation-6
claim. It does not persist SQLite data_version and does not make data_version the authority
verdict. The connection-local counter is only a dirty hint; a deterministic in-memory witness
of WP206-owned sqlite_schema objects and checkpoint rows is the bounded revalidation verdict.
"""
from __future__ import annotations

from pathlib import Path


SOURCE = Path("src/frankenstein2/persistent_agency_kernel.py")
G3_TEST = Path("tests/test_wp206_legacy_authority_recovery.py")


def replace_once(text: str, old: str, new: str, name: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{name} anchor mismatch: expected 1, observed {count}")
    return text.replace(old, new, 1)


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''        self.connection.execute("PRAGMA foreign_keys=ON")

    @classmethod
''',
        '''        self.connection.execute("PRAGMA foreign_keys=ON")
        data_version_row = self.connection.execute(
            "PRAGMA main.data_version"
        ).fetchone()
        if (
            data_version_row is None
            or len(data_version_row) != 1
            or type(data_version_row[0]) is not int
        ):
            raise PersistentAgencyError("UNIFIEDDB_DATA_VERSION_UNAVAILABLE")
        # Connection-local observation only. SQLite advances data_version when a different
        # connection commits. It is a dirty hint, never the authority verdict.
        self.sqlite_data_version_baseline = int(data_version_row[0])
        self._wp206_owned_surface_witness_sha256: str | None = None
        existing_wp206_table = self.connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?",
            (CHECKPOINT_TABLE,),
        ).fetchone()
        if existing_wp206_table is not None:
            # Reopen establishes a fresh same-process witness over the already admitted WP206
            # surface. Cross-reopen data_version continuity is deliberately never used.
            self._adopt_wp206_monitor_state(self._capture_wp206_monitor_state())

    @classmethod
''',
        "constructor monitor state",
    )

    text = replace_once(
        text,
        '''    def close(self) -> None:
        self.connection.close()

    def initialize_schema(self) -> None:
''',
        '''    def close(self) -> None:
        self.connection.close()

    def _read_sqlite_data_version(self) -> int:
        row = self.connection.execute("PRAGMA main.data_version").fetchone()
        if row is None or len(row) != 1 or type(row[0]) is not int:
            raise PersistentAgencyError("UNIFIEDDB_DATA_VERSION_UNAVAILABLE")
        return int(row[0])

    def _compute_wp206_owned_surface_witness(self) -> str:
        """Digest only WP206-owned schema objects and checkpoint rows.

        This witness is in-memory and same-process only. It is not persisted and is not a
        cross-reopen database authority token.
        """
        try:
            schema_rows = self.connection.execute(
                """SELECT type, name, tbl_name, sql
                   FROM sqlite_schema
                   WHERE name=? OR tbl_name=?
                   ORDER BY type, name""",
                (CHECKPOINT_TABLE, CHECKPOINT_TABLE),
            ).fetchall()
            checkpoint_rows = self.connection.execute(
                f"""SELECT checkpoint_id, previous_checkpoint_id, kernel_state_id,
                           generation, checkpoint_sha256, checkpoint_json,
                           canonical_db_path, db_device, db_inode,
                           unifieddb_authority_receipt_sha256
                    FROM {CHECKPOINT_TABLE}
                    ORDER BY checkpoint_id"""
            ).fetchall()
        except sqlite3.Error as exc:
            raise PersistentAgencyError(
                "UNIFIEDDB_WP206_OWNED_SURFACE_REVALIDATION_FAILED"
            ) from exc
        return _sha256(
            {
                "schema": "FRANKENSTEIN2_WP206_OWNED_SQLITE_SURFACE_WITNESS/v1",
                "schema_rows": [list(row) for row in schema_rows],
                "checkpoint_rows": [list(row) for row in checkpoint_rows],
            }
        )

    def _capture_wp206_monitor_state(self) -> tuple[int, str]:
        # Double-read the connection-local dirty counter around the bounded witness. If another
        # connection commits during capture, retry instead of accepting a mixed observation.
        for _ in range(3):
            before = self._read_sqlite_data_version()
            witness = self._compute_wp206_owned_surface_witness()
            after = self._read_sqlite_data_version()
            if before == after:
                return after, witness
        raise PersistentAgencyError("UNIFIEDDB_WP206_MONITOR_CAPTURE_UNSTABLE")

    def _adopt_wp206_monitor_state(self, state: tuple[int, str]) -> None:
        self.sqlite_data_version_baseline, self._wp206_owned_surface_witness_sha256 = state

    def initialize_schema(self) -> None:
''',
        "monitor helper insertion",
    )

    text = replace_once(
        text,
        '''            self.connection.execute(
                f"""CREATE INDEX IF NOT EXISTS idx_f2_persistent_agency_lineage
                    ON {CHECKPOINT_TABLE}(kernel_state_id, generation)"""
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
''',
        '''            self.connection.execute(
                f"""CREATE INDEX IF NOT EXISTS idx_f2_persistent_agency_lineage
                    ON {CHECKPOINT_TABLE}(kernel_state_id, generation)"""
            )
            pending_monitor_state = self._capture_wp206_monitor_state()
            self.connection.commit()
            self._adopt_wp206_monitor_state(pending_monitor_state)
        except Exception:
            self.connection.rollback()
            raise
''',
        "schema monitor adoption",
    )

    text = replace_once(
        text,
        '''        if (st.st_dev, st.st_ino) != (self.db_device, self.db_inode):
            raise PersistentAgencyError("UNIFIEDDB_FILE_IDENTITY_DRIFT")

    def write_checkpoint(self, checkpoint: PersistentAgencyCheckpoint) -> str:
''',
        '''        if (st.st_dev, st.st_ino) != (self.db_device, self.db_inode):
            raise PersistentAgencyError("UNIFIEDDB_FILE_IDENTITY_DRIFT")
        current_data_version = self._read_sqlite_data_version()
        if self._wp206_owned_surface_witness_sha256 is None:
            # Before schema admission there is no WP206-owned SQL surface to witness.
            return
        if current_data_version == self.sqlite_data_version_baseline:
            return
        observed_state = self._capture_wp206_monitor_state()
        if observed_state[1] != self._wp206_owned_surface_witness_sha256:
            raise PersistentAgencyError("UNIFIEDDB_WP206_OWNED_SURFACE_DRIFT")
        # Another connection changed only non-WP206 state. Refresh the connection-local dirty
        # hint only after bounded WP206 revalidation proved the owned surface unchanged.
        self._adopt_wp206_monitor_state(observed_state)

    def write_checkpoint(self, checkpoint: PersistentAgencyCheckpoint) -> str:
''',
        "owned-surface guard",
    )

    text = replace_once(
        text,
        '''        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self.connection.execute(
''',
        '''        try:
            self.connection.execute("BEGIN IMMEDIATE")
            # Close the race between the pre-BEGIN check and acquisition of the write lock.
            self._assert_current_file_identity()
            existing = self.connection.execute(
''',
        "write lock recheck",
    )

    text = replace_once(
        text,
        '''            if existing is not None:
                if existing == (checkpoint_sha, checkpoint_json):
                    self.connection.commit()
                    return checkpoint_sha
''',
        '''            if existing is not None:
                if existing == (checkpoint_sha, checkpoint_json):
                    pending_monitor_state = self._capture_wp206_monitor_state()
                    self.connection.commit()
                    self._adopt_wp206_monitor_state(pending_monitor_state)
                    return checkpoint_sha
''',
        "idempotent write monitor adoption",
    )

    text = replace_once(
        text,
        '''            self.connection.execute(
                f"""INSERT INTO {CHECKPOINT_TABLE}(
                    checkpoint_id, previous_checkpoint_id, kernel_state_id,
                    generation, checkpoint_sha256, checkpoint_json,
                    canonical_db_path, db_device, db_inode,
                    unifieddb_authority_receipt_sha256
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    checkpoint.checkpoint_id,
                    checkpoint.previous_checkpoint_id,
                    checkpoint.kernel_state_id,
                    checkpoint.generation,
                    checkpoint_sha,
                    checkpoint_json,
                    self.canonical_db_path,
                    self.db_device,
                    self.db_inode,
                    self.authority_receipt_sha256,
                ),
            )
            self.connection.commit()
            return checkpoint_sha
''',
        '''            self.connection.execute(
                f"""INSERT INTO {CHECKPOINT_TABLE}(
                    checkpoint_id, previous_checkpoint_id, kernel_state_id,
                    generation, checkpoint_sha256, checkpoint_json,
                    canonical_db_path, db_device, db_inode,
                    unifieddb_authority_receipt_sha256
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    checkpoint.checkpoint_id,
                    checkpoint.previous_checkpoint_id,
                    checkpoint.kernel_state_id,
                    checkpoint.generation,
                    checkpoint_sha,
                    checkpoint_json,
                    self.canonical_db_path,
                    self.db_device,
                    self.db_inode,
                    self.authority_receipt_sha256,
                ),
            )
            pending_monitor_state = self._capture_wp206_monitor_state()
            self.connection.commit()
            self._adopt_wp206_monitor_state(pending_monitor_state)
            return checkpoint_sha
''',
        "new write monitor adoption",
    )

    SOURCE.write_text(text, encoding="utf-8")

    g3 = G3_TEST.read_text(encoding="utf-8")
    g3 = replace_once(
        g3,
        '''            tampered = "f" * 64 if current != "f" * 64 else "e" * 64
            self._replace_receipt(tampered)
            with self.assertRaisesRegex(
                PersistentAgencyError,
                "LEGACY_RECOVERY_POST_MIGRATION_AUTHORITY_DRIFT",
            ):
                self._recover(
                    store=store, expected_legacy=historical, subject=subject
                )
            with self.assertRaisesRegex(
                PersistentAgencyError, "CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH"
            ):
                store.load_checkpoint("checkpoint-0")
''',
        '''            tampered = "f" * 64 if current != "f" * 64 else "e" * 64
            self._replace_receipt(tampered)
            with self.assertRaisesRegex(
                PersistentAgencyError,
                "LEGACY_RECOVERY_POST_MIGRATION_AUTHORITY_DRIFT",
            ):
                self._recover(
                    store=store, expected_legacy=historical, subject=subject
                )

            # G6 is the earlier same-process live fence: this external write changed a
            # WP206-owned checkpoint row and must fail before the older row-level G3 check.
            with self.assertRaisesRegex(
                PersistentAgencyError, "UNIFIEDDB_WP206_OWNED_SURFACE_DRIFT"
            ):
                store.load_checkpoint("checkpoint-0")

            # Re-entry deliberately establishes a fresh same-process G6 witness. The older G3
            # row-level authority invariant remains independently enforceable after reopen.
            store.close()
            store = self._open_store()
            with self.assertRaisesRegex(
                PersistentAgencyError, "CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH"
            ):
                store.load_checkpoint("checkpoint-0")
''',
        "G3 predecessor layering",
    )
    G3_TEST.write_text(g3, encoding="utf-8")

    print("PATCHED_WP206_G6_ON_EXACT_MAIN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
