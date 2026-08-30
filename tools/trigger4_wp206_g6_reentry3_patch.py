#!/usr/bin/env python3
"""Transplant the measured WP206 G6 owned-surface guard onto exact current main.

Bounded continuation of the SAME active F2-WP-206 generation-6 claim. PRAGMA
main.data_version is only a connection-local dirty hint. The verdict is a deterministic
in-memory witness of WP206-owned sqlite_schema objects and checkpoint rows.
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
        '''        self.connection.execute("PRAGMA foreign_keys=ON")\n\n    @classmethod\n''',
        '''        self.connection.execute("PRAGMA foreign_keys=ON")\n        data_version_row = self.connection.execute(\n            "PRAGMA main.data_version"\n        ).fetchone()\n        if (\n            data_version_row is None\n            or len(data_version_row) != 1\n            or type(data_version_row[0]) is not int\n        ):\n            raise PersistentAgencyError("UNIFIEDDB_DATA_VERSION_UNAVAILABLE")\n        # Connection-local observation only. SQLite advances data_version when a different\n        # connection commits. It is a dirty hint, never the authority verdict.\n        self.sqlite_data_version_baseline = int(data_version_row[0])\n        self._wp206_owned_surface_witness_sha256: str | None = None\n        existing_wp206_table = self.connection.execute(\n            "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?",\n            (CHECKPOINT_TABLE,),\n        ).fetchone()\n        if existing_wp206_table is not None:\n            # Reopen establishes a fresh same-process witness over the already admitted WP206\n            # surface. Cross-reopen data_version continuity is deliberately never used.\n            self._adopt_wp206_monitor_state(self._capture_wp206_monitor_state())\n\n    @classmethod\n''',
        "constructor monitor state",
    )

    text = replace_once(
        text,
        '''    def close(self) -> None:\n        self.connection.close()\n\n    def initialize_schema(self) -> None:\n''',
        '''    def close(self) -> None:\n        self.connection.close()\n\n    def _read_sqlite_data_version(self) -> int:\n        row = self.connection.execute("PRAGMA main.data_version").fetchone()\n        if row is None or len(row) != 1 or type(row[0]) is not int:\n            raise PersistentAgencyError("UNIFIEDDB_DATA_VERSION_UNAVAILABLE")\n        return int(row[0])\n\n    def _compute_wp206_owned_surface_witness(self) -> str:\n        """Digest only WP206-owned schema objects and checkpoint rows."""\n        try:\n            schema_rows = self.connection.execute(\n                """SELECT type, name, tbl_name, sql\n                   FROM sqlite_schema\n                   WHERE name=? OR tbl_name=?\n                   ORDER BY type, name""",\n                (CHECKPOINT_TABLE, CHECKPOINT_TABLE),\n            ).fetchall()\n            checkpoint_rows = self.connection.execute(\n                f"""SELECT checkpoint_id, previous_checkpoint_id, kernel_state_id,\n                           generation, checkpoint_sha256, checkpoint_json,\n                           canonical_db_path, db_device, db_inode,\n                           unifieddb_authority_receipt_sha256\n                    FROM {CHECKPOINT_TABLE}\n                    ORDER BY checkpoint_id"""\n            ).fetchall()\n        except sqlite3.Error as exc:\n            raise PersistentAgencyError(\n                "UNIFIEDDB_WP206_OWNED_SURFACE_REVALIDATION_FAILED"\n            ) from exc\n        return _sha256(\n            {\n                "schema": "FRANKENSTEIN2_WP206_OWNED_SQLITE_SURFACE_WITNESS/v1",\n                "schema_rows": [list(row) for row in schema_rows],\n                "checkpoint_rows": [list(row) for row in checkpoint_rows],\n            }\n        )\n\n    def _capture_wp206_monitor_state(self) -> tuple[int, str]:\n        # Double-read the connection-local dirty counter around the bounded witness. If another\n        # connection commits during capture, retry instead of accepting a mixed observation.\n        for _ in range(3):\n            before = self._read_sqlite_data_version()\n            witness = self._compute_wp206_owned_surface_witness()\n            after = self._read_sqlite_data_version()\n            if before == after:\n                return after, witness\n        raise PersistentAgencyError("UNIFIEDDB_WP206_MONITOR_CAPTURE_UNSTABLE")\n\n    def _adopt_wp206_monitor_state(self, state: tuple[int, str]) -> None:\n        self.sqlite_data_version_baseline, self._wp206_owned_surface_witness_sha256 = state\n\n    def initialize_schema(self) -> None:\n''',
        "monitor helper insertion",
    )

    text = replace_once(
        text,
        '''            self.connection.execute(\n                f"""CREATE INDEX IF NOT EXISTS idx_f2_persistent_agency_lineage\n                    ON {CHECKPOINT_TABLE}(kernel_state_id, generation)"""\n            )\n            self.connection.commit()\n        except Exception:\n            self.connection.rollback()\n            raise\n''',
        '''            self.connection.execute(\n                f"""CREATE INDEX IF NOT EXISTS idx_f2_persistent_agency_lineage\n                    ON {CHECKPOINT_TABLE}(kernel_state_id, generation)"""\n            )\n            pending_monitor_state = self._capture_wp206_monitor_state()\n            self.connection.commit()\n            self._adopt_wp206_monitor_state(pending_monitor_state)\n        except Exception:\n            self.connection.rollback()\n            raise\n''',
        "schema monitor adoption",
    )

    text = replace_once(
        text,
        '''        if (st.st_dev, st.st_ino) != (self.db_device, self.db_inode):\n            raise PersistentAgencyError("UNIFIEDDB_FILE_IDENTITY_DRIFT")\n\n    def write_checkpoint(self, checkpoint: PersistentAgencyCheckpoint) -> str:\n''',
        '''        if (st.st_dev, st.st_ino) != (self.db_device, self.db_inode):\n            raise PersistentAgencyError("UNIFIEDDB_FILE_IDENTITY_DRIFT")\n        current_data_version = self._read_sqlite_data_version()\n        if self._wp206_owned_surface_witness_sha256 is None:\n            return\n        if current_data_version == self.sqlite_data_version_baseline:\n            return\n        observed_state = self._capture_wp206_monitor_state()\n        if observed_state[1] != self._wp206_owned_surface_witness_sha256:\n            raise PersistentAgencyError("UNIFIEDDB_WP206_OWNED_SURFACE_DRIFT")\n        self._adopt_wp206_monitor_state(observed_state)\n\n    def write_checkpoint(self, checkpoint: PersistentAgencyCheckpoint) -> str:\n''',
        "owned-surface guard",
    )

    text = replace_once(
        text,
        '''        try:\n            self.connection.execute("BEGIN IMMEDIATE")\n            existing = self.connection.execute(\n''',
        '''        try:\n            self.connection.execute("BEGIN IMMEDIATE")\n            # Close the race between pre-BEGIN validation and acquisition of the write lock.\n            self._assert_current_file_identity()\n            existing = self.connection.execute(\n''',
        "write lock recheck",
    )

    text = replace_once(
        text,
        '''            if existing is not None:\n                if existing == (checkpoint_sha, checkpoint_json):\n                    self.connection.commit()\n                    return checkpoint_sha\n''',
        '''            if existing is not None:\n                if existing == (checkpoint_sha, checkpoint_json):\n                    pending_monitor_state = self._capture_wp206_monitor_state()\n                    self.connection.commit()\n                    self._adopt_wp206_monitor_state(pending_monitor_state)\n                    return checkpoint_sha\n''',
        "idempotent write monitor adoption",
    )

    text = replace_once(
        text,
        '''            self.connection.execute(\n                f"""INSERT INTO {CHECKPOINT_TABLE}(\n                    checkpoint_id, previous_checkpoint_id, kernel_state_id,\n                    generation, checkpoint_sha256, checkpoint_json,\n                    canonical_db_path, db_device, db_inode,\n                    unifieddb_authority_receipt_sha256\n                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",\n                (\n                    checkpoint.checkpoint_id,\n                    checkpoint.previous_checkpoint_id,\n                    checkpoint.kernel_state_id,\n                    checkpoint.generation,\n                    checkpoint_sha,\n                    checkpoint_json,\n                    self.canonical_db_path,\n                    self.db_device,\n                    self.db_inode,\n                    self.authority_receipt_sha256,\n                ),\n            )\n            self.connection.commit()\n            return checkpoint_sha\n''',
        '''            self.connection.execute(\n                f"""INSERT INTO {CHECKPOINT_TABLE}(\n                    checkpoint_id, previous_checkpoint_id, kernel_state_id,\n                    generation, checkpoint_sha256, checkpoint_json,\n                    canonical_db_path, db_device, db_inode,\n                    unifieddb_authority_receipt_sha256\n                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",\n                (\n                    checkpoint.checkpoint_id,\n                    checkpoint.previous_checkpoint_id,\n                    checkpoint.kernel_state_id,\n                    checkpoint.generation,\n                    checkpoint_sha,\n                    checkpoint_json,\n                    self.canonical_db_path,\n                    self.db_device,\n                    self.db_inode,\n                    self.authority_receipt_sha256,\n                ),\n            )\n            pending_monitor_state = self._capture_wp206_monitor_state()\n            self.connection.commit()\n            self._adopt_wp206_monitor_state(pending_monitor_state)\n            return checkpoint_sha\n''',
        "new write monitor adoption",
    )

    SOURCE.write_text(text, encoding="utf-8")

    g3 = G3_TEST.read_text(encoding="utf-8")
    g3 = replace_once(
        g3,
        '''            tampered = "f" * 64 if current != "f" * 64 else "e" * 64\n            self._replace_receipt(tampered)\n            with self.assertRaisesRegex(\n                PersistentAgencyError,\n                "LEGACY_RECOVERY_POST_MIGRATION_AUTHORITY_DRIFT",\n            ):\n                self._recover(\n                    store=store, expected_legacy=historical, subject=subject\n                )\n            with self.assertRaisesRegex(\n                PersistentAgencyError, "CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH"\n            ):\n                store.load_checkpoint("checkpoint-0")\n''',
        '''            tampered = "f" * 64 if current != "f" * 64 else "e" * 64\n            self._replace_receipt(tampered)\n            with self.assertRaisesRegex(\n                PersistentAgencyError,\n                "LEGACY_RECOVERY_POST_MIGRATION_AUTHORITY_DRIFT",\n            ):\n                self._recover(\n                    store=store, expected_legacy=historical, subject=subject\n                )\n\n            with self.assertRaisesRegex(\n                PersistentAgencyError, "UNIFIEDDB_WP206_OWNED_SURFACE_DRIFT"\n            ):\n                store.load_checkpoint("checkpoint-0")\n\n            store.close()\n            store = self._open_store()\n            with self.assertRaisesRegex(\n                PersistentAgencyError, "CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH"\n            ):\n                store.load_checkpoint("checkpoint-0")\n''',
        "G3 predecessor layering",
    )
    G3_TEST.write_text(g3, encoding="utf-8")

    print("PATCHED_WP206_G6_ON_EXACT_MAIN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
