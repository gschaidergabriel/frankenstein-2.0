#!/usr/bin/env python3
"""REVIEW_ONLY falsifier for F2-WP-206 parent-checkpoint integrity.

A successor checkpoint must never bind to a parent row whose stored
checkpoint_json no longer matches its persisted checkpoint_sha256.
"""
from __future__ import annotations

import json
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
    advance_checkpoint,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).resolve().with_name("wp206_restart_probe.py")
SRC = REPO_ROOT / "src"


class ParentDigestFalsifier(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.cwd = self.root / "unrelated-cwd"
        self.cwd.mkdir()
        self.db = self.root / "canonical" / "unified.db"
        self.db.parent.mkdir()
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS f2_test_bootstrap(id INTEGER PRIMARY KEY)"
            )
            connection.commit()
        finally:
            connection.close()
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.home)
        self.env["FRANKENSTEIN2_DB"] = str(self.db)
        self.env["PYTHONPATH"] = str(SRC)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _open_store(self) -> CanonicalPersistentAgencyStore:
        resolution = resolve_unifieddb_path(env=self.env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        return CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )

    def test_corrupt_parent_digest_must_block_successor_write(self) -> None:
        writer = subprocess.run(
            [sys.executable, str(PROBE), "write"],
            cwd=str(self.cwd),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(writer.returncode, 0, msg=writer.stderr)

        store = self._open_store()
        try:
            parent = store.load_checkpoint("checkpoint-0")
            child = advance_checkpoint(
                parent,
                checkpoint_id="checkpoint-1",
                pulse_id="pulse-1",
                observation_id="observation-none-1",
            )
        finally:
            store.close()

        connection = sqlite3.connect(self.db)
        try:
            row = connection.execute(
                """SELECT checkpoint_sha256, checkpoint_json
                   FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertIsNotNone(row)
            expected_sha, raw_json = row
            payload = json.loads(raw_json)
            self.assertEqual(
                payload["agency_state"]["interests"][0]["label"],
                "Preserve explicit restart state",
            )
            payload["agency_state"]["interests"][0]["label"] = (
                "Corrupted but schema-valid parent payload"
            )
            corrupted_json = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            connection.execute(
                """UPDATE f2_persistent_agency_checkpoints
                   SET checkpoint_json=?
                   WHERE checkpoint_id='checkpoint-0'""",
                (corrupted_json,),
            )
            connection.commit()
            unchanged_sha = connection.execute(
                """SELECT checkpoint_sha256
                   FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()[0]
            self.assertEqual(unchanged_sha, expected_sha)
        finally:
            connection.close()

        store = self._open_store()
        try:
            with self.assertRaises(PersistentAgencyError):
                store.write_checkpoint(child)
        finally:
            store.close()

        connection = sqlite3.connect(self.db)
        try:
            child_count = connection.execute(
                """SELECT COUNT(*) FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id='checkpoint-1'"""
            ).fetchone()[0]
            self.assertEqual(
                child_count,
                0,
                "a corrupt parent must never acquire a persisted descendant",
            )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
