#!/usr/bin/env python3
"""Executable acceptance regression for WP206 G5 external SQLite revision drift.

The pre-patch version of this exact scenario reproduced the gap on PR #728 head
49ea7a9a73bcda7f12545e203a5a0b704f7b6280 / Actions 33305713501: a second SQLite
connection committed logical changes, main.data_version advanced, device/inode stayed
stable, and the G4 guard accepted continued use.

G5 acceptance inverts that discriminator.  The same DELETE/WAL external commits must now
fail closed on the original long-lived canonical store connection while no-change and
same-connection canonical schema work remain usable.  This is repository-component evidence
only, not target-runtime or whole-system evidence.
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

        # Establish the requested journal mode before the monitored store connection opens.
        # Changing DELETE -> WAL on that same long-lived connection can itself advance the
        # connection-local data_version observation; that is a harness transition, not the
        # external-commit discriminator this test is meant to isolate.
        _bootstrap(db, mode=mode)

        store = _open_store(db, home)
        try:
            # Same-connection canonical schema mutation must not poison the connection-local
            # baseline: the fence is scoped to a different connection committing afterwards.
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

            try:
                store._assert_current_file_identity()
            except PersistentAgencyError as exc:
                assert str(exc) == "UNIFIEDDB_EXTERNAL_SQLITE_REVISION_DRIFT", str(exc)
            else:
                raise AssertionError(
                    "WP206 G5 failed to reject an externally committed same-inode SQLite revision"
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
        "PASS_WP206_G5_EXTERNAL_SQLITE_REVISION_FENCE: no-change stayed usable and "
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
