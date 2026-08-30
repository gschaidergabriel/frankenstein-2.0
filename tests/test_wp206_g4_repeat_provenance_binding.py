#!/usr/bin/env python3
"""Executable successor regression for WP206 G4 repeat-provenance binding."""
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
)
from frankenstein2.wp206_legacy_authority_recovery import (
    ALREADY_RECOVERED,
    RECOVERED,
    recover_legacy_g1_checkpoint_authority,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "tests" / "wp206_restart_probe.py"
SRC = REPO_ROOT / "src"
PROVENANCE_A = "evidence:first-authoritative-provenance"
PROVENANCE_B = "evidence:conflicting-repeat-provenance"


class WP206G4RepeatProvenanceBinding(unittest.TestCase):
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

    def _write_legacy_style_row(self) -> str:
        written = subprocess.run(
            [sys.executable, str(PROBE), "write"],
            cwd=str(self.cwd),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(written.returncode, 0, msg=written.stderr)
        historical_receipt = str(json.loads(written.stdout)["db_authority_receipt"])
        connection = sqlite3.connect(self.db)
        try:
            current = connection.execute(
                """SELECT unifieddb_authority_receipt_sha256
                   FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertIsNotNone(current)
            self.assertNotEqual(historical_receipt, str(current[0]))
            connection.execute(
                """UPDATE f2_persistent_agency_checkpoints
                   SET unifieddb_authority_receipt_sha256=?
                   WHERE checkpoint_id='checkpoint-0'""",
                (historical_receipt,),
            )
            connection.commit()
        finally:
            connection.close()
        return historical_receipt

    def _open_store(self) -> CanonicalPersistentAgencyStore:
        resolution = resolve_unifieddb_path(env=self.env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        return CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )

    def test_same_provenance_is_exact_idempotent_repeat(self) -> None:
        historical = self._write_legacy_style_row()
        store = self._open_store()
        try:
            first = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=PROVENANCE_A,
            )
            second = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=PROVENANCE_A,
            )
            self.assertEqual(first.status, RECOVERED)
            self.assertEqual(second.status, ALREADY_RECOVERED)
            self.assertEqual(second.recovery_id, first.recovery_id)
            self.assertEqual(second.recovery_provenance_ref, PROVENANCE_A)
        finally:
            store.close()

    def test_conflicting_repeat_provenance_fails_closed(self) -> None:
        historical = self._write_legacy_style_row()
        store = self._open_store()
        try:
            first = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=PROVENANCE_A,
            )
            self.assertEqual(first.status, RECOVERED)
            with self.assertRaisesRegex(
                PersistentAgencyError, "LEGACY_RECOVERY_PROVENANCE_CONFLICT"
            ):
                recover_legacy_g1_checkpoint_authority(
                    store=store,
                    checkpoint_id="checkpoint-0",
                    expected_legacy_authority_receipt_sha256=historical,
                    recovery_provenance_ref=PROVENANCE_B,
                )
            # The failed repeat must not mutate the authoritative stored provenance.
            exact_repeat = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=PROVENANCE_A,
            )
            self.assertEqual(exact_repeat.status, ALREADY_RECOVERED)
            self.assertEqual(exact_repeat.recovery_id, first.recovery_id)
            self.assertEqual(exact_repeat.recovery_provenance_ref, PROVENANCE_A)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
