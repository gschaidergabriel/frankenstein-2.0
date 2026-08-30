#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


def one(connection: sqlite3.Connection, sql: str):
    row = connection.execute(sql).fetchone()
    assert row is not None
    return row[0]


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "unified.db"
        a = sqlite3.connect(path, isolation_level=None)
        try:
            a.execute("PRAGMA journal_mode=WAL")
            a.execute("CREATE TABLE protected(id INTEGER PRIMARY KEY, payload TEXT, digest TEXT)")
            a.execute("CREATE TABLE unrelated(id INTEGER PRIMARY KEY, value TEXT)")
            a.execute("INSERT INTO protected VALUES(1,'alpha','digest-alpha')")
            b = sqlite3.connect(path, isolation_level=None)
            try:
                inode0 = os.stat(path).st_ino
                dv0 = int(one(a, "PRAGMA data_version"))
                sv0 = int(one(a, "PRAGMA schema_version"))
                protected0 = a.execute(
                    "SELECT payload,digest FROM protected WHERE id=1"
                ).fetchone()

                b.execute("INSERT INTO unrelated(value) VALUES('foreign')")
                inode1 = os.stat(path).st_ino
                dv1 = int(one(a, "PRAGMA data_version"))
                sv1 = int(one(a, "PRAGMA schema_version"))
                protected1 = a.execute(
                    "SELECT payload,digest FROM protected WHERE id=1"
                ).fetchone()

                a.execute("INSERT INTO unrelated(value) VALUES('self')")
                dv2 = int(one(a, "PRAGMA data_version"))
                sv2 = int(one(a, "PRAGMA schema_version"))

                b.execute("CREATE TABLE foreign_schema(id INTEGER PRIMARY KEY)")
                inode3 = os.stat(path).st_ino
                dv3 = int(one(a, "PRAGMA data_version"))
                sv3 = int(one(a, "PRAGMA schema_version"))

                assertions = {
                    "inode_stable": inode0 == inode1 == inode3,
                    "foreign_commit_changed_data_version": dv1 != dv0,
                    "same_connection_commit_did_not_change_data_version": dv2 == dv1,
                    "foreign_schema_changed_data_version": dv3 != dv2,
                    "foreign_schema_changed_schema_version": sv3 != sv2,
                    "unrelated_foreign_write_left_protected_row_unchanged": protected1 == protected0,
                }
                if not all(assertions.values()):
                    raise AssertionError(assertions)
                print(json.dumps({
                    "python": sys.version.split()[0],
                    "sqlite_runtime": sqlite3.sqlite_version,
                    "journal_mode": str(one(a, "PRAGMA journal_mode")).upper(),
                    "inode": [inode0, inode1, inode3],
                    "data_version": [dv0, dv1, dv2, dv3],
                    "schema_version": [sv0, sv1, sv2, sv3],
                    "protected_row": [protected0, protected1],
                    "assertions": assertions,
                }, sort_keys=True))
            finally:
                b.close()
        finally:
            a.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
