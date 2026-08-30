#!/usr/bin/env python3
"""Executable G6 regression for external same-inode WP206-owned SQLite drift.

Review PR #746 proved that connection-local PRAGMA main.data_version is too broad to be the
verdict: a legitimate WP103 commit changes it without mutating WP206. G6 therefore uses
`data_version` only as a dirty hint and fails closed only when bounded revalidation shows that
the WP206-owned checkpoint surface changed.

This discriminator mutates WP206-owned sqlite_schema state through another connection while
preserving device/inode, in both DELETE and WAL modes. Repository-component evidence only.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile

from frankenstein2.persistent_agency_kernel import (
    CHECKPOINT_TABLE,
    CanonicalPersistentAgencyStore,
    PersistentAgencyError,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


def _bootstrap(path: Path, *, mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE bootstrap(id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO bootstrap(value) VALUES('initial')")
        conn.commit()
        observed = conn.execute(f"PRAGMA journal_mode={mode}").fetchone()[0]
        assert str(observed).lower() == mode, (observed, mode)
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


def _assert_external_wp206_schema_commit_fails_closed(mode: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        db = root / "canonical" / f"{mode}.db"
        _bootstrap(db, mode=mode)

        store = _open_store(db, home)
        try:
            store.initialize_schema()
            store._assert_current_file_identity()
            before_stat = db.stat()
            before_version = int(
                store.connection.execute("PRAGMA main.data_version").fetchone()[0]
            )

            external = sqlite3.connect(db)
            try:
                external.execute(
                    f"CREATE INDEX idx_wp206_external_{mode}_tamper "
                    f"ON {CHECKPOINT_TABLE}(checkpoint_id)"
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
            )
            assert after_version != before_version, (before_version, after_version)

            try:
                store._assert_current_file_identity()
            except PersistentAgencyError as exc:
                assert str(exc) == "UNIFIEDDB_WP206_OWNED_SURFACE_DRIFT", exc
            else:
                raise AssertionError(
                    f"{mode}: external WP206-owned same-inode schema mutation did not fail closed"
                )
        finally:
            store.close()


def _assert_no_change_remains_valid(mode: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        db = root / "canonical" / f"no-change-{mode}.db"
        _bootstrap(db, mode=mode)
        store = _open_store(db, home)
        try:
            store.initialize_schema()
            store._assert_current_file_identity()
            store._assert_current_file_identity()
        finally:
            store.close()


def main() -> int:
    for mode in ("delete", "wal"):
        _assert_no_change_remains_valid(mode)
        _assert_external_wp206_schema_commit_fails_closed(mode)
    print("PASS_WP206_G6_EXTERNAL_OWNED_SURFACE_SQLITE_REVISION_DRIFT")
    print("DATA_VERSION_ROLE=DIRTY_HINT_NOT_DATABASE_WIDE_VERDICT")
    print("SCOPE=ONE_LONG_LIVED_WP206_STORE_CONNECTION")
    print("TARGET_RUNTIME_CREDIT=0")
    print("PHYSICAL_GRID10_CREDIT=0")
    print("GWT_JSPACE_RUNTIME_CREDIT=0")
    print("EFFECT_COMPLETION_TRAINING_CREDIT=0")
    print("WHOLE_SYSTEM_ACCEPTANCE=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
