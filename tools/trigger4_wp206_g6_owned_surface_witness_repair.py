#!/usr/bin/env python3
"""Apply the bounded WP206 G6 owned-surface witness repair to exact candidate source.

This tool is intentionally anchor-checked and single-purpose.  It converts connection-local
SQLite data_version from a database-wide authority verdict into a dirty hint, while preserving
a deterministic in-memory witness over WP206-owned sqlite_schema objects and checkpoint rows.
It does not persist the witness or grant cross-reopen authority.
"""
from __future__ import annotations

from pathlib import Path


SOURCE = Path("src/frankenstein2/persistent_agency_kernel.py")


def replace_once(text: str, old: str, new: str, name: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{name} anchor mismatch: expected 1, observed {count}")
    return text.replace(old, new, 1)


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''        # Connection-local observation only.  SQLite advances data_version when a
        # *different* connection commits.  Never persist or compare it across reopen.
        self.sqlite_data_version_baseline = int(data_version_row[0])

    @classmethod
''',
        '''        # Connection-local observation only.  SQLite advances data_version when a
        # *different* connection commits.  It is a dirty hint, never the authority verdict.
        self.sqlite_data_version_baseline = int(data_version_row[0])
        self._wp206_owned_surface_witness_sha256: str | None = None

    @classmethod
''',
        "constructor",
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

        This is an in-memory same-process revalidation witness. It is deliberately not
        persisted and is not cross-reopen UnifiedDB authority.
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
        # Double-read the connection-local dirty counter around the bounded witness so an
        # overlapping external commit cannot be silently folded into one inconsistent view.
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
        "helper insertion",
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
        "initialize_schema",
    )

    text = replace_once(
        text,
        '''        data_version_row = self.connection.execute(
            "PRAGMA main.data_version"
        ).fetchone()
        if (
            data_version_row is None
            or len(data_version_row) != 1
            or type(data_version_row[0]) is not int
        ):
            raise PersistentAgencyError("UNIFIEDDB_DATA_VERSION_UNAVAILABLE")
        if int(data_version_row[0]) != self.sqlite_data_version_baseline:
            raise PersistentAgencyError("UNIFIEDDB_EXTERNAL_SQLITE_REVISION_DRIFT")
''',
        '''        current_data_version = self._read_sqlite_data_version()
        if self._wp206_owned_surface_witness_sha256 is None:
            # Before initialize_schema there is no admitted WP206-owned SQL surface to witness.
            return
        if current_data_version == self.sqlite_data_version_baseline:
            return
        observed_state = self._capture_wp206_monitor_state()
        if observed_state[1] != self._wp206_owned_surface_witness_sha256:
            raise PersistentAgencyError("UNIFIEDDB_WP206_OWNED_SURFACE_DRIFT")
        # Another connection changed only non-WP206 state. Refresh the connection-local dirty
        # hint after bounded revalidation proved the WP206-owned surface unchanged.
        self._adopt_wp206_monitor_state(observed_state)
''',
        "current identity guard",
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
        "write BEGIN",
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
        "idempotent write",
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
        "final write",
    )

    SOURCE.write_text(text, encoding="utf-8")
    print("PATCHED_WP206_G6_OWNED_SURFACE_WITNESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
