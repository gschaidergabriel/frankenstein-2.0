#!/usr/bin/env python3
"""Trigger-6 research-only SQLite WAL semantics reproduction.

Scope: reproduce single-writer contention, stale WAL snapshot write rejection,
and checkpoint blockage by a held reader. This is not Frankenstein-2.0 runtime
or integration evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile


def error_payload(exc: sqlite3.OperationalError) -> dict[str, object]:
    return {
        "message": str(exc),
        "sqlite_errorcode": getattr(exc, "sqlite_errorcode", None),
        "sqlite_errorname": getattr(exc, "sqlite_errorname", None),
    }


def run() -> dict[str, object]:
    result: dict[str, object] = {
        "schema": "TRIGGER6_SQLITE_WAL_SEMANTICS_REPRO/v1",
        "classification": "RESEARCH_ONLY_NOT_F2_RUNTIME_EVIDENCE",
        "python_sqlite_version": sqlite3.sqlite_version,
        "python_sqlite_version_info": list(sqlite3.sqlite_version_info),
    }
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "repro.db"
        initial = sqlite3.connect(path)
        result["journal_mode"] = initial.execute(
            "PRAGMA journal_mode=WAL"
        ).fetchone()[0]
        initial.execute("PRAGMA wal_autocheckpoint=0")
        initial.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
        initial.execute("INSERT INTO t(v) VALUES('a')")
        initial.commit()
        initial.close()

        writer_a = sqlite3.connect(path, timeout=0, isolation_level=None)
        writer_b = sqlite3.connect(path, timeout=0, isolation_level=None)
        writer_a.execute("BEGIN IMMEDIATE")
        try:
            writer_b.execute("BEGIN IMMEDIATE")
            result["single_writer_second_begin"] = "UNEXPECTED_SUCCESS"
        except sqlite3.OperationalError as exc:
            result["single_writer_second_begin"] = "BUSY"
            result["single_writer_error"] = error_payload(exc)
        writer_a.rollback()
        writer_a.close()
        writer_b.close()

        reader_a = sqlite3.connect(path, timeout=0, isolation_level=None)
        writer_c = sqlite3.connect(path, timeout=0, isolation_level=None)
        reader_a.execute("BEGIN")
        result["snapshot_initial"] = reader_a.execute(
            "SELECT v FROM t WHERE id=1"
        ).fetchone()[0]
        writer_c.execute("BEGIN IMMEDIATE")
        writer_c.execute("UPDATE t SET v='b' WHERE id=1")
        writer_c.commit()
        result["writer_committed_value"] = writer_c.execute(
            "SELECT v FROM t WHERE id=1"
        ).fetchone()[0]
        result["snapshot_still_sees"] = reader_a.execute(
            "SELECT v FROM t WHERE id=1"
        ).fetchone()[0]
        try:
            reader_a.execute("UPDATE t SET v='c' WHERE id=1")
            result["stale_snapshot_write"] = "UNEXPECTED_SUCCESS"
        except sqlite3.OperationalError as exc:
            result["stale_snapshot_write"] = "REJECTED"
            result["stale_snapshot_error"] = error_payload(exc)
        reader_a.rollback()
        reader_a.close()
        writer_c.close()

        reader_b = sqlite3.connect(path, timeout=0, isolation_level=None)
        writer_d = sqlite3.connect(path, timeout=0, isolation_level=None)
        checkpoint = sqlite3.connect(path, timeout=0, isolation_level=None)
        reader_b.execute("BEGIN")
        reader_b.execute("SELECT count(*) FROM t").fetchone()
        for index in range(200):
            writer_d.execute("BEGIN IMMEDIATE")
            writer_d.execute("INSERT INTO t(v) VALUES(?)", (f"x{index}",))
            writer_d.commit()
        wal = Path(str(path) + "-wal")
        result["wal_size_with_reader"] = wal.stat().st_size if wal.exists() else 0
        result["checkpoint_while_reader"] = list(
            checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        )
        result["wal_size_after_blocked_checkpoint"] = (
            wal.stat().st_size if wal.exists() else 0
        )
        reader_b.rollback()
        reader_b.close()
        result["checkpoint_after_reader_release"] = list(
            checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        )
        result["wal_size_after_release_checkpoint"] = (
            wal.stat().st_size if wal.exists() else 0
        )
        writer_d.close()
        checkpoint.close()
    return result


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, separators=(",", ":")))
