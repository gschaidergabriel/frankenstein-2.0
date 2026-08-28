#!/usr/bin/env python3
"""Review-only F5 discriminator for F2-WP-206.

Proves that ordinary unrelated content churn inside the same canonical UnifiedDB may
change the mutable UnifiedDB fingerprint receipt while an already-admitted Persistent
Agency checkpoint keeps the same typed checkpoint identity and remains replayable.

CANDIDATE_FALSIFIER / REVIEW_ONLY. This file grants no mutation authority or runtime credit.
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

from state.unifieddb_identity import fingerprint_unifieddb


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).resolve().with_name("wp206_restart_probe.py")
SRC = REPO_ROOT / "src"


class WP206DBChurnIdentityFalsifier(unittest.TestCase):
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
                "CREATE TABLE f2_test_bootstrap(id INTEGER PRIMARY KEY)"
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

    def _probe(self, mode: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(PROBE), mode],
            cwd=str(self.cwd),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return json.loads(result.stdout)

    def test_unrelated_db_churn_changes_db_receipt_not_agency_checkpoint_identity(self) -> None:
        writer = self._probe("write")
        self.assertEqual(writer["journal_mode"], "WAL")
        self.assertTrue(writer["wal_exists_before_exit"])
        self.assertGreater(writer["wal_size_before_exit"], 0)

        before_replay = self._probe("read")
        checkpoint_sha_before = before_replay["checkpoint_sha256"]
        self.assertEqual(before_replay["checkpoint_id"], "checkpoint-0")
        self.assertEqual(before_replay["goal_statuses"], ["ACTIVE"])

        db_identity_before = fingerprint_unifieddb(self.db)
        receipt_before = db_identity_before.receipt_sha256()
        device_inode_before = (db_identity_before.device, db_identity_before.inode)

        # Mutate an unrelated namespace, then checkpoint WAL into the main DB so the
        # main-file fingerprint receipt is required to observe real content/schema churn.
        connection = sqlite3.connect(self.db)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA wal_autocheckpoint=0")
            connection.execute(
                "CREATE TABLE f2_unrelated_churn(k TEXT PRIMARY KEY, v TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO f2_unrelated_churn(k, v) VALUES('unrelated', 'mutation')"
            )
            connection.commit()
            row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            self.assertIsNotNone(row)
        finally:
            connection.close()

        db_identity_after = fingerprint_unifieddb(self.db)
        receipt_after = db_identity_after.receipt_sha256()
        self.assertEqual(
            (db_identity_after.device, db_identity_after.inode),
            device_inode_before,
            "ordinary content churn must not masquerade as DB-file replacement",
        )
        self.assertNotEqual(
            receipt_after,
            receipt_before,
            "the mutable UnifiedDB fingerprint receipt must observe checkpointed DB churn",
        )

        after_replay = self._probe("read")
        self.assertEqual(after_replay["checkpoint_id"], "checkpoint-0")
        self.assertEqual(after_replay["goal_statuses"], ["ACTIVE"])
        self.assertEqual(
            after_replay["checkpoint_sha256"],
            checkpoint_sha_before,
            "unrelated UnifiedDB content churn must not rewrite Agency checkpoint identity",
        )
        self.assertNotEqual(
            receipt_after,
            after_replay["checkpoint_sha256"],
            "UnifiedDB authority/fingerprint identity must remain distinct from Agency state identity",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
