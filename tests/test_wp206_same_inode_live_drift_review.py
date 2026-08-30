#!/usr/bin/env python3
"""REVIEW_ONLY executable falsifier for the open WP206 same-inode live-drift boundary.

This test deliberately specifies only the fail-closed property: once the already-open
Persistent Agency store's underlying UnifiedDB main file changes schema/content while the
same device+inode identity is retained, a subsequent checkpoint read must not silently
continue under the stale open-time authority receipt.

A failure of this review test is counterevidence at repository-component scope only. It is
not target-host, whole-system, canonical-semantics, GRID/GWT/J-Space, effect, completion or
training credit and it does not prescribe continuous full-file hashing as the repair.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from frankenstein2.persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    PersistentAgencyError,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
PROBE = REPO_ROOT / "tests" / "wp206_restart_probe.py"


class WP206SameInodeLiveDriftReview(unittest.TestCase):
    def test_same_inode_schema_drift_must_not_reuse_stale_store_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            db = root / "canonical" / "unified.db"
            db.parent.mkdir()

            bootstrap = sqlite3.connect(db)
            try:
                bootstrap.execute(
                    "CREATE TABLE f2_test_bootstrap(id INTEGER PRIMARY KEY)"
                )
                bootstrap.commit()
            finally:
                bootstrap.close()

            env = os.environ.copy()
            env["HOME"] = str(home)
            env["FRANKENSTEIN2_DB"] = str(db)
            env["PYTHONPATH"] = str(SRC)

            writer = subprocess.run(
                [sys.executable, str(PROBE), "write"],
                cwd=str(REPO_ROOT),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(writer.returncode, 0, msg=writer.stderr)

            resolution = resolve_unifieddb_path(env=env, home=home)
            before = fingerprint_unifieddb(resolution.path)
            store = CanonicalPersistentAgencyStore.open(
                resolution=resolution,
                fingerprint=before,
            )
            try:
                # Establish that the checkpoint is valid before the intervention.
                self.assertEqual(store.load_checkpoint("checkpoint-0").checkpoint_id, "checkpoint-0")

                before_inode = db.stat().st_ino
                before_device = db.stat().st_dev

                # External same-file mutation while the WP206 store remains open. Force the
                # WAL content into the main file so the post-mutation fingerprint observes
                # the changed SQLite schema at the same path/device/inode.
                other = sqlite3.connect(db)
                try:
                    other.execute(
                        "CREATE TABLE f2_same_inode_live_drift_probe("
                        "id INTEGER PRIMARY KEY, marker TEXT NOT NULL)"
                    )
                    other.commit()
                    other.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                finally:
                    other.close()

                after = fingerprint_unifieddb(resolution.path)
                self.assertEqual((before_device, before_inode), (db.stat().st_dev, db.stat().st_ino))
                self.assertEqual((before.device, before.inode), (after.device, after.inode))
                self.assertNotEqual(before.sqlite_schema_sha256, after.sqlite_schema_sha256)
                self.assertNotEqual(before.sha256, after.sha256)

                # OPEN HYPOTHESIS / acceptance property for this review-only discriminator:
                # stale open-time authority must not silently authorize a later read after
                # an externally observed same-inode schema/content change.
                with self.assertRaises(PersistentAgencyError):
                    store.load_checkpoint("checkpoint-0")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
