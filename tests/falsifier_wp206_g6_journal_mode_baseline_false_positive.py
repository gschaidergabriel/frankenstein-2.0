#!/usr/bin/env python3
"""Falsifier for the WP206 external-SQLite revision-fence baseline point.

This is REVIEW_ONLY successor-preparation evidence. It does not claim F2-WP-206 G6
mutation authority and grants no runtime/host/GRID10/GWT/J-Space/effect/completion/
training/whole-system credit.

Acceptance target for a corrected candidate:
1. open the canonical store;
2. permit the existing same-connection journal-mode setup plus initialize_schema();
3. preserve ordinary same-connection canonical writes;
4. reject a later commit from a genuinely different SQLite connection while the DB
   device/inode remain unchanged.

The pre-fix PR #728 candidate fails step 2 because its data_version baseline is captured
before PRAGMA journal_mode=WAL. On the hosted runner that same-connection journal-mode
transition advances the connection-local observation and is then misclassified as external
revision drift.
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


def _bootstrap(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE bootstrap(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO bootstrap(value) VALUES('initial')")
        connection.commit()
    finally:
        connection.close()


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


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        db = root / "canonical" / "journal-baseline.db"
        _bootstrap(db)

        store = _open_store(db, home)
        try:
            before = int(store.connection.execute("PRAGMA main.data_version").fetchone()[0])
            mode = store.connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            assert str(mode).lower() == "wal", mode
            after_journal = int(
                store.connection.execute("PRAGMA main.data_version").fetchone()[0]
            )
            assert after_journal != before, (
                "falsifier did not reproduce the journal-mode baseline transition"
            )

            store.initialize_schema()

            # Corrected successor behavior: the authorized connection-local setup phase is
            # not external revision drift.
            store._assert_current_file_identity()

            stable = int(
                store.connection.execute("PRAGMA main.data_version").fetchone()[0]
            )
            store.connection.execute(
                "INSERT INTO bootstrap(value) VALUES('same-connection')"
            )
            store.connection.commit()
            assert int(
                store.connection.execute("PRAGMA main.data_version").fetchone()[0]
            ) == stable
            store._assert_current_file_identity()

            before_stat = db.stat()
            external = sqlite3.connect(db)
            try:
                external.execute(
                    "INSERT INTO bootstrap(value) VALUES('different-connection')"
                )
                external.commit()
            finally:
                external.close()
            after_stat = db.stat()
            assert (before_stat.st_dev, before_stat.st_ino) == (
                after_stat.st_dev,
                after_stat.st_ino,
            )

            try:
                store._assert_current_file_identity()
            except PersistentAgencyError as exc:
                assert str(exc) == "UNIFIEDDB_EXTERNAL_SQLITE_REVISION_DRIFT", str(exc)
            else:
                raise AssertionError(
                    "corrected candidate failed to reject a true different-connection commit"
                )
        finally:
            store.close()

    print("PASS_WP206_G6_JOURNAL_MODE_BASELINE_FALSIFIER")
    print("CLASSIFICATION=REVIEW_ONLY_SUCCESSOR_PREPARATION")
    print("CANONICAL_WP206_MUTATION_AUTHORITY=false")
    print("TARGET_RUNTIME_CREDIT=0")
    print("PHYSICAL_GRID10_CREDIT=0")
    print("GWT_JSPACE_RUNTIME_CREDIT=0")
    print("EFFECT_COMPLETION_TRAINING_CREDIT=0")
    print("WHOLE_SYSTEM_ACCEPTANCE=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
