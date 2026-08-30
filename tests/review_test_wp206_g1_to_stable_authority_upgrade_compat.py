#!/usr/bin/env python3
"""REVIEW_ONLY: characterize G1 checkpoint compatibility after the stable authority-receipt change.

This is deliberately not mutation authority.  The historical G1 writer stored
UnifiedDBFingerprint.receipt_sha256() captured when the store was opened.  Current source
stores a restart-stable bound-file authority receipt.  Existing G1 rows must not be silently
assumed compatible unless the new reader can prove/recover that transition explicitly.
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


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "tests" / "wp206_restart_probe.py"
SRC = REPO_ROOT / "src"


class WP206G1UpgradeCompatibilityReview(unittest.TestCase):
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

    def _probe(self, mode: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(PROBE), mode],
            cwd=str(self.cwd),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def _write_current_checkpoint(self) -> dict:
        result = self._probe("write")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return json.loads(result.stdout)

    def _stored_receipt(self) -> str:
        connection = sqlite3.connect(self.db)
        try:
            row = connection.execute(
                """SELECT unifieddb_authority_receipt_sha256
                   FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertIsNotNone(row)
            return str(row[0])
        finally:
            connection.close()

    def _replace_stored_receipt(self, value: str) -> None:
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                """UPDATE f2_persistent_agency_checkpoints
                   SET unifieddb_authority_receipt_sha256=?
                   WHERE checkpoint_id='checkpoint-0'""",
                (value,),
            )
            connection.commit()
        finally:
            connection.close()

    def test_current_stable_authority_row_replays(self) -> None:
        self._write_current_checkpoint()
        reader = self._probe("read")
        self.assertEqual(reader.returncode, 0, msg=reader.stderr)
        self.assertEqual(json.loads(reader.stdout)["checkpoint_id"], "checkpoint-0")

    def test_historical_g1_full_fingerprint_receipt_row_remains_replayable(self) -> None:
        payload = self._write_current_checkpoint()
        historical_g1_receipt = str(payload["db_authority_receipt"])
        current_stable_receipt = self._stored_receipt()

        # The discriminator is meaningful only if the two semantic receipt families differ.
        self.assertRegex(historical_g1_receipt, r"^[0-9a-f]{64}$")
        self.assertRegex(current_stable_receipt, r"^[0-9a-f]{64}$")
        self.assertNotEqual(historical_g1_receipt, current_stable_receipt)

        # Emulate a durable checkpoint row written by accepted WP206 G1: same checkpoint
        # bytes/path/device/inode, but the authority column contains the historical full
        # fingerprint receipt captured by the writer before its legitimate SQLite writes.
        self._replace_stored_receipt(historical_g1_receipt)

        reader = self._probe("read")
        self.assertEqual(
            reader.returncode,
            0,
            msg=(
                "accepted G1 durable checkpoint became unreadable after the stable-authority "
                "semantic change; an explicit versioned migration/compatibility contract is "
                f"required. stderr={reader.stderr!r}"
            ),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
