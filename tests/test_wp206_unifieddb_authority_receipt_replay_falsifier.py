#!/usr/bin/env python3
"""Review-only acceptance regression for the WP206 authority-receipt repair donor."""
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


class WP206AuthorityReceiptRepairTests(unittest.TestCase):
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

    def _write(self) -> None:
        result = self._probe("write")
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_untampered_replay_still_succeeds(self) -> None:
        self._write()
        reader = self._probe("read")
        self.assertEqual(reader.returncode, 0, msg=reader.stderr)
        self.assertEqual(json.loads(reader.stdout)["checkpoint_id"], "checkpoint-0")

    def test_tampered_stored_authority_receipt_is_rejected(self) -> None:
        self._write()
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                """UPDATE f2_persistent_agency_checkpoints
                   SET unifieddb_authority_receipt_sha256=?
                   WHERE checkpoint_id='checkpoint-0'""",
                ("0" * 64,),
            )
            connection.commit()
        finally:
            connection.close()

        reader = self._probe("read")
        self.assertNotEqual(reader.returncode, 0)
        self.assertIn("CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH", reader.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
