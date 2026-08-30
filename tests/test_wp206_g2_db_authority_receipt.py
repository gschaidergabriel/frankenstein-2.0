#!/usr/bin/env python3
"""F2-WP-206 G2 regression for checkpoint UnifiedDB authority-receipt replay binding."""
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


class WP206G2DBAuthorityReceiptReplay(unittest.TestCase):
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

    def _write_checkpoint(self) -> dict:
        result = self._probe("write")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["resolved_path"], str(self.db.resolve()))
        return payload

    def test_positive_control_untampered_authority_receipt_replays(self) -> None:
        self._write_checkpoint()
        reader = self._probe("read")
        self.assertEqual(reader.returncode, 0, msg=reader.stderr)
        payload = json.loads(reader.stdout)
        self.assertEqual(payload["checkpoint_id"], "checkpoint-0")

    def test_tampered_stored_authority_receipt_fails_closed(self) -> None:
        self._write_checkpoint()
        forged_receipt = "0" * 64
        connection = sqlite3.connect(self.db)
        try:
            before = connection.execute(
                """SELECT unifieddb_authority_receipt_sha256
                   FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertIsNotNone(before)
            self.assertNotEqual(before[0], forged_receipt)
            connection.execute(
                """UPDATE f2_persistent_agency_checkpoints
                   SET unifieddb_authority_receipt_sha256=?
                   WHERE checkpoint_id='checkpoint-0'""",
                (forged_receipt,),
            )
            connection.commit()
            after = connection.execute(
                """SELECT unifieddb_authority_receipt_sha256
                   FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertEqual(after[0], forged_receipt)
        finally:
            connection.close()

        reader = self._probe("read")
        self.assertNotEqual(
            reader.returncode,
            0,
            msg="replay unexpectedly succeeded after stored authority-receipt tamper",
        )
        self.assertIn("CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH", reader.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
