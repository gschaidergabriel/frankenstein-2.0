#!/usr/bin/env python3
"""REVIEW_ONLY characterization for WP206 G3 repeat-provenance semantics.

This does not claim WP206 mutation authority.  It records whether a second recovery
call with a different provenance reference is treated as an exact idempotent repeat.
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

from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore
from frankenstein2.wp206_legacy_authority_recovery import (
    ALREADY_RECOVERED,
    RECOVERED,
    recover_legacy_g1_checkpoint_authority,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "tests" / "wp206_restart_probe.py"
SRC = REPO_ROOT / "src"


class WP206G3ProvenanceRepeatFalsifier(unittest.TestCase):
    def test_different_repeat_provenance_is_currently_accepted_as_already_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            cwd = root / "unrelated-cwd"
            cwd.mkdir()
            db = root / "canonical" / "unified.db"
            db.parent.mkdir()
            connection = sqlite3.connect(db)
            try:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS f2_test_bootstrap(id INTEGER PRIMARY KEY)"
                )
                connection.commit()
            finally:
                connection.close()

            env = os.environ.copy()
            env["HOME"] = str(home)
            env["FRANKENSTEIN2_DB"] = str(db)
            env["PYTHONPATH"] = str(SRC)
            written = subprocess.run(
                [sys.executable, str(PROBE), "write"],
                cwd=str(cwd),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(written.returncode, 0, msg=written.stderr)
            historical_receipt = str(json.loads(written.stdout)["db_authority_receipt"])

            connection = sqlite3.connect(db)
            try:
                current_receipt_row = connection.execute(
                    """SELECT unifieddb_authority_receipt_sha256
                       FROM f2_persistent_agency_checkpoints
                       WHERE checkpoint_id='checkpoint-0'"""
                ).fetchone()
                self.assertIsNotNone(current_receipt_row)
                current_receipt = str(current_receipt_row[0])
                self.assertNotEqual(historical_receipt, current_receipt)
                connection.execute(
                    """UPDATE f2_persistent_agency_checkpoints
                       SET unifieddb_authority_receipt_sha256=?
                       WHERE checkpoint_id='checkpoint-0'""",
                    (historical_receipt,),
                )
                connection.commit()
            finally:
                connection.close()

            resolution = resolve_unifieddb_path(env=env, home=home)
            fingerprint = fingerprint_unifieddb(resolution.path)
            store = CanonicalPersistentAgencyStore.open(
                resolution=resolution,
                fingerprint=fingerprint,
            )
            try:
                first = recover_legacy_g1_checkpoint_authority(
                    store=store,
                    checkpoint_id="checkpoint-0",
                    expected_legacy_authority_receipt_sha256=historical_receipt,
                    recovery_provenance_ref="evidence:first-authoritative-provenance",
                )
                self.assertEqual(first.status, RECOVERED)

                second = recover_legacy_g1_checkpoint_authority(
                    store=store,
                    checkpoint_id="checkpoint-0",
                    expected_legacy_authority_receipt_sha256=historical_receipt,
                    recovery_provenance_ref="evidence:conflicting-repeat-provenance",
                )

                # Current G3 behavior: the different caller provenance is ignored and
                # the recorded first provenance is returned as an idempotent repeat.
                self.assertEqual(second.status, ALREADY_RECOVERED)
                self.assertEqual(second.recovery_id, first.recovery_id)
                self.assertEqual(
                    second.recovery_provenance_ref,
                    "evidence:first-authoritative-provenance",
                )
                self.assertNotEqual(
                    second.recovery_provenance_ref,
                    "evidence:conflicting-repeat-provenance",
                )
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
