#!/usr/bin/env python3
"""Trigger-6 research-only Python sqlite3 transaction-ABI matrix.

Compares the transaction lifecycle assumptions used by F2's manual BEGIN IMMEDIATE
writer against omitted defaults and explicit Python sqlite3 autocommit modes.
This is not Frankenstein-2.0 runtime/integration evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import tempfile


def run_mode(path: Path, name: str, kwargs: dict) -> dict:
    connection = sqlite3.connect(path, **kwargs)
    row = {
        "mode": name,
        "autocommit": repr(getattr(connection, "autocommit", "UNAVAILABLE")),
        "isolation_level": connection.isolation_level,
        "in_transaction_after_connect": connection.in_transaction,
    }
    try:
        connection.execute("BEGIN IMMEDIATE")
        row["begin_immediate"] = "OK"
    except Exception as exc:
        row["begin_immediate"] = "ERROR"
        row["begin_error_type"] = type(exc).__name__
        row["begin_error"] = str(exc)
    row["in_transaction_after_begin_attempt"] = connection.in_transaction

    try:
        if row["begin_immediate"] == "OK":
            connection.execute("CREATE TABLE IF NOT EXISTS t(id INTEGER)")
            connection.execute("INSERT INTO t VALUES(1)")
        connection.commit()
        row["commit"] = "CALLED_OK"
    except Exception as exc:
        row["commit"] = "ERROR"
        row["commit_error"] = str(exc)
    row["in_transaction_after_commit"] = connection.in_transaction

    try:
        connection.execute("BEGIN IMMEDIATE")
        row["second_begin_immediate"] = "OK"
    except Exception as exc:
        row["second_begin_immediate"] = "ERROR"
        row["second_begin_error"] = str(exc)
    row["in_transaction_after_second_begin"] = connection.in_transaction

    try:
        connection.rollback()
        row["rollback"] = "CALLED_OK"
    except Exception as exc:
        row["rollback"] = "ERROR"
        row["rollback_error"] = str(exc)
    row["in_transaction_after_rollback"] = connection.in_transaction

    try:
        observer = sqlite3.connect(path)
        row["row_count_external"] = observer.execute(
            "SELECT count(*) FROM t"
        ).fetchone()[0]
        observer.close()
    except Exception as exc:
        row["row_count_external"] = "ERROR:" + str(exc)
    connection.close()
    return row


def run() -> dict:
    modes = [
        ("omitted_default", {}),
        (
            "legacy_manual",
            {
                "autocommit": sqlite3.LEGACY_TRANSACTION_CONTROL,
                "isolation_level": None,
            },
        ),
        ("pep249_false", {"autocommit": False}),
        ("sqlite_autocommit_true", {"autocommit": True}),
    ]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        return {
            "schema": "TRIGGER6_PYTHON_SQLITE_TXN_ABI_REPRO/v1",
            "classification": "RESEARCH_ONLY_NOT_F2_RUNTIME_EVIDENCE",
            "python": sys.version,
            "sqlite": sqlite3.sqlite_version,
            "modes": [
                run_mode(root / f"{name}.db", name, kwargs)
                for name, kwargs in modes
            ],
        }


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, separators=(",", ":")))
