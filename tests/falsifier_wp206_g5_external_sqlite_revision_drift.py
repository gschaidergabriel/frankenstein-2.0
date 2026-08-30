#!/usr/bin/env python3
"""Executable failing-before ablation for WP206 external same-inode SQLite drift.

This is the Trigger-4 repository reproduction of the Trigger-6 E3 handoff.  It proves
that a second SQLite connection can commit a logical database revision while the bound
main file keeps the same device/inode, and that the current WP206 file-identity guard
therefore accepts continued use.

A zero exit code means the pre-G5 gap was reproduced.  This script is negative evidence,
not acceptance of the successor repair and not target-runtime evidence.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile

from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


def _bootstrap(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE bootstrap(id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO bootstrap(value) VALUES('initial')")
        conn.commit()
    finally:
        conn.close()


def _open_store(db: Path, home: Path) -> CanonicalPersistentAgencyStore:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["FRANKENSTEIN2_DB"] = str(db)
    resolution = resolve_unifieddb_path(env=env, home=home)
    fingerprint = fingerprint_unifieddb(resolution.path)
    return CanonicalPersistentAgencyStore.open(
        resolution=resolution,
        fingerprint=fingerprint,
    )


def _reproduce(mode: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        db = root / "canonical" / f"{mode}.db"
        _bootstrap(db)

        store = _open_store(db, home)
        try:
            store.initialize_schema()
            if mode == "wal":
                assert store.connection.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
            else:
                store.connection.execute("PRAGMA journal_mode=DELETE")

            before_stat = db.stat()
            before_version = int(
                store.connection.execute("PRAGMA main.data_version").fetchone()[0]
            )

            external = sqlite3.connect(db)
            try:
                external.execute("INSERT INTO bootstrap(value) VALUES(?)", (f"external-{mode}",))
                external.execute(
                    "CREATE TABLE IF NOT EXISTS external_schema_delta(id INTEGER PRIMARY KEY)"
                )
                external.commit()
            finally:
                external.close()

            after_stat = db.stat()
            after_version = int(
                store.connection.execute("PRAGMA main.data_version").fetchone()[0]
            )

            assert (before_stat.st_dev, before_stat.st_ino) == (
                after_stat.st_dev,
                after_stat.st_ino,
            ), "external SQLite commit unexpectedly replaced the database inode"
            assert after_version != before_version, (
                "observer PRAGMA main.data_version did not witness the external commit"
            )

            # Current G4 guard checks only path/device/inode.  If this call succeeds while
            # data_version changed, the exact pre-G5 logical-revision gap is reproduced.
            store._assert_current_file_identity()
        finally:
            store.close()


def main() -> int:
    _reproduce("delete")
    _reproduce("wal")
    print(
        "PASS_REPRODUCED_WP206_G5_PREPATCH_GAP: external SQLite commits advanced "
        "main.data_version in DELETE and WAL modes while device/inode stayed stable and "
        "the current WP206 file-identity guard accepted continued use"
    )
    print("TARGET_RUNTIME_CREDIT=0")
    print("PHYSICAL_GRID10_CREDIT=0")
    print("GWT_JSPACE_RUNTIME_CREDIT=0")
    print("EFFECT_COMPLETION_TRAINING_CREDIT=0")
    print("WHOLE_SYSTEM_ACCEPTANCE=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
