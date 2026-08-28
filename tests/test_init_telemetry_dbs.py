#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.init_telemetry_dbs import EXPECTED_TABLES, initialize_all, verify_all


class TelemetryInitializerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_materializes_exact_canonical_database_set(self) -> None:
        paths = initialize_all(self.root)
        self.assertEqual(set(paths), set(EXPECTED_TABLES))
        self.assertEqual(
            {p.name for p in (self.root / "databases").glob("*.sqlite")},
            set(EXPECTED_TABLES),
        )
        verify_all(self.root)

    def test_idempotent_reinitialization_preserves_existing_rows(self) -> None:
        initialize_all(self.root)
        path = self.root / "databases" / "system_telemetry.sqlite"
        with sqlite3.connect(path) as con:
            con.execute(
                """
                INSERT INTO component_events(
                    event_id, observed_at_utc, component, operation, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("sentinel", "2026-08-28T00:00:00Z", "test", "preserve", "{}"),
            )
        initialize_all(self.root)
        with sqlite3.connect(path) as con:
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM component_events WHERE event_id='sentinel'"
                ).fetchone()[0],
                1,
            )

    def test_grid_foreign_key_rejects_orphan_cell_event(self) -> None:
        initialize_all(self.root)
        path = self.root / "databases" / "grid10_telemetry.sqlite"
        con = sqlite3.connect(path)
        try:
            con.execute("PRAGMA foreign_keys=ON")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    """
                    INSERT INTO grid_cell_events(
                        cell_event_id, cycle_id, cell_id, event_kind, observed_at_utc
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    ("orphan", "missing-cycle", "G1", "PROPOSE", "2026-08-28T00:00:00Z"),
                )
        finally:
            con.close()

    def test_bug_fixed_state_requires_root_cause_and_regression_evidence(self) -> None:
        initialize_all(self.root)
        path = self.root / "databases" / "bugs.sqlite"
        with sqlite3.connect(path) as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    """
                    INSERT INTO bugs(
                        bug_id, title, first_seen_at_utc, status, symptom
                    ) VALUES (?, ?, ?, 'FIXED', ?)
                    """,
                    ("bug-1", "fake fixed", "2026-08-28T00:00:00Z", "symptom vanished"),
                )

    def test_verify_fails_closed_if_required_table_is_missing(self) -> None:
        initialize_all(self.root)
        path = self.root / "databases" / "communications.sqlite"
        with sqlite3.connect(path) as con:
            con.execute("DROP TABLE communication_events")
        with self.assertRaisesRegex(RuntimeError, "missing tables"):
            verify_all(self.root)

    def test_verify_fails_closed_on_schema_metadata_drift(self) -> None:
        initialize_all(self.root)
        path = self.root / "databases" / "performance.sqlite"
        with sqlite3.connect(path) as con:
            con.execute(
                "UPDATE schema_meta SET value='999' WHERE key='schema_version'"
            )
        with self.assertRaisesRegex(RuntimeError, "metadata mismatch"):
            verify_all(self.root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
