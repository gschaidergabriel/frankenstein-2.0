#!/usr/bin/env python3
"""Trigger-6 E3 SQLite WAL snapshot interleave falsifier.

Research-only mechanism probe. This is not Frankenstein target-runtime evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import tempfile


def one_run() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "snapshot.db"
        reader = sqlite3.connect(db, isolation_level=None)
        writer = sqlite3.connect(db, isolation_level=None)
        try:
            journal_mode = reader.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            reader.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, val TEXT)")
            reader.execute("INSERT INTO t(id,val) VALUES(1,'v1')")
            writer.execute("PRAGMA journal_mode=WAL").fetchone()

            reader.execute("BEGIN")
            first_read = reader.execute(
                "SELECT val FROM t WHERE id=1"
            ).fetchone()[0]
            data_version_before_writer = reader.execute(
                "PRAGMA main.data_version"
            ).fetchone()[0]

            writer.execute("BEGIN IMMEDIATE")
            writer.execute("UPDATE t SET val='v2' WHERE id=1")
            writer.execute("COMMIT")

            data_version_after_writer_inside_reader_tx = reader.execute(
                "PRAGMA main.data_version"
            ).fetchone()[0]
            second_read_same_tx = reader.execute(
                "SELECT val FROM t WHERE id=1"
            ).fetchone()[0]
            reader.execute("COMMIT")

            data_version_after_reader_tx = reader.execute(
                "PRAGMA main.data_version"
            ).fetchone()[0]
            read_after_tx = reader.execute(
                "SELECT val FROM t WHERE id=1"
            ).fetchone()[0]

            return {
                "journal_mode": journal_mode,
                "first_read": first_read,
                "second_read_same_tx": second_read_same_tx,
                "read_after_tx": read_after_tx,
                "data_version_before_writer": data_version_before_writer,
                "data_version_after_writer_inside_reader_tx": (
                    data_version_after_writer_inside_reader_tx
                ),
                "data_version_after_reader_tx": data_version_after_reader_tx,
            }
        finally:
            reader.close()
            writer.close()


def expected(result: dict[str, object]) -> bool:
    return (
        result["journal_mode"] == "wal"
        and result["first_read"] == "v1"
        and result["second_read_same_tx"] == "v1"
        and result["read_after_tx"] == "v2"
        and result["data_version_before_writer"]
        == result["data_version_after_writer_inside_reader_tx"]
        and result["data_version_after_reader_tx"]
        != result["data_version_after_writer_inside_reader_tx"]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be >=1")
    runs = [one_run() for _ in range(args.runs)]
    matching = sum(expected(result) for result in runs)
    summary = {
        "schema": "FRANKENSTEIN2_TRIGGER6_WP901_WAL_SNAPSHOT_INTERLEAVE_E3/v1",
        "sqlite_version": sqlite3.sqlite_version,
        "python_version": sys.version.split()[0],
        "runs": args.runs,
        "matching_expected": matching,
        "all_match": matching == args.runs,
        "unique_results": list({json.dumps(r, sort_keys=True) for r in runs}),
        "evidence_scope": "LOCAL_SQLITE_MECHANISM_REPRODUCTION_ONLY",
        "f2_target_runtime_credit": 0,
        "whole_system_credit": 0,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["all_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
