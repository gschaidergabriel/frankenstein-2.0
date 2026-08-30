#!/usr/bin/env python3
"""Executable G6 acceptance regression for WP206 external SQLite revision drift.

PR #728 preserved the pre-G6 discriminator: a second SQLite connection can commit logical
DML/DDL changes while device/inode remain stable and the existing file-identity guard keeps
accepting the long-lived store.  The candidate also showed that connection-local
PRAGMA main.data_version observes that external commit.

G6 accepts only that narrow mechanism.  External DELETE/WAL commits from another connection
must fail closed on the original long-lived canonical store connection, while no-change and
same-connection canonical schema work remain usable.  data_version is never persisted or
compared across reopen.  This is repository-component evidence only.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile

from frankenstein2.persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    PersistentAgencyError,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


def _bootstrap(path: Path, *, mode: str = "delete") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE bootstrap(id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO bootstrap(value) VALUES('initial')")
        conn.commit()
        if mode == "wal":
            assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        elif mode == "delete":
            assert conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() == "delete"
        else:
            raise AssertionError(f"unsupported journal mode: {mode}")
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


def _assert_external_commit_fails_closed(mode: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        db = root / "canonical" / f"{mode}.db"

        # Establish journal mode before the monitored connection opens.  Changing journal
        # mode on the monitored connection is not the external-commit discriminator here.
        _bootstrap(db, mode=mode)

        store = _open_store(db, home)
        try:
            # Canonical same-connection schema setup must remain usable and must not alter
            # the observer baseline, because SQLite data_version changes for other-connection
            # commits rather than the current connection's own committed writes.
            store.initialize_schema()
            store._assert_current_file_identity()

            observed_mode = store.connection.execute("PRAGMA journal_mode").fetchone()[0].lower()
            assert observed_mode == mode, (observed_mode, mode)
            store._assert_current_file_identity()

            before_stat = db.stat()
            before_version = int(
                store.connection.execute("PRAGMA main.data_version").fetchone()[0]
            )

            external = sqlite3.connect(db)
            try:
                external.execute(
                    "INSERT INTO bootstrap(value) VALUES(?)",
                    (f"external-{mode}",),
                )
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

            try:
                store._assert_current_file_identity()
            except PersistentAgencyError as exc:
                assert str(exc) == "UNIFIEDDB_EXTERNAL_SQLITE_REVISION_DRIFT", str(exc)
            else:
                raise AssertionError(
                    "WP206 G6 failed to reject an externally committed same-inode SQLite revision"
                )
        finally:
            store.close()


def _assert_no_change_stays_usable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        db = root / "canonical" / "no-change.db"
        _bootstrap(db)
        store = _open_store(db, home)
        try:
            store.initialize_schema()
            baseline = store.sqlite_data_version_baseline
            for _ in range(3):
                store._assert_current_file_identity()
                assert store.sqlite_data_version_baseline == baseline
        finally:
            store.close()


def main() -> int:
    _assert_no_change_stays_usable()
    _assert_external_commit_fails_closed("delete")
    _assert_external_commit_fails_closed("wal")
    print(
        "PASS_WP206_G6_EXTERNAL_SQLITE_REVISION_FENCE: no-change stayed usable and "
        "external same-inode commits failed closed in DELETE and WAL modes"
    )
    print("DATA_VERSION_SCOPE=ONE_LONG_LIVED_CONNECTION_ONLY")
    print("JOURNAL_MODE_ESTABLISHED_BEFORE_MONITORED_CONNECTION=TRUE")
    print("SAME_CONNECTION_RAW_DML=EXPLICITLY_UNCOVERED_SEPARATE_FALSIFIER")
    print("RAW_FILESYSTEM_WAL_TAMPER=EXPLICITLY_UNCOVERED_SEPARATE_FALSIFIER")
    print("TARGET_RUNTIME_CREDIT=0")
    print("PHYSICAL_GRID10_CREDIT=0")
    print("GWT_JSPACE_RUNTIME_CREDIT=0")
    print("EFFECT_COMPLETION_TRAINING_CREDIT=0")
    print("WHOLE_SYSTEM_ACCEPTANCE=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
