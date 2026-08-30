#!/usr/bin/env python3
"""REVIEW_ONLY post-G4 falsifier for WP206 recovery provenance content binding.

This test does not propose or mutate accepted WP206 semantics. It asks one narrow question:
if external evidence bytes change while recovery_provenance_ref remains identical, can the
accepted G4 boundary observe that change? A PASS here means the counterexample is reproduced,
not that WP206 is accepted or repaired.
"""
from __future__ import annotations

import hashlib
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


REPO_ROOT = Path(__file__).resolve().parents[3]
PROBE = REPO_ROOT / "tests" / "wp206_restart_probe.py"
SRC = REPO_ROOT / "src"
PROVENANCE_REF = "evidence:mutable-external-object"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class WP206SameRefMutatedEvidenceFalsifier(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.cwd = self.root / "unrelated-cwd"
        self.cwd.mkdir()
        self.db = self.root / "canonical" / "unified.db"
        self.db.parent.mkdir()
        self.evidence = self.root / "external-evidence.json"
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
                   WHERE checkpoint_id='checkpoint-0'""",
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

    def test_same_ref_cannot_observe_mutated_external_evidence_bytes(self) -> None:
        historical = self._write_legacy_style_row()
        evidence_a = b'{"claim":"legacy receipt witnessed","version":1}\n'
        evidence_b = b'{"claim":"different evidence at same reference","version":2}\n'
        self.evidence.write_bytes(evidence_a)
        sha_a = _sha256_bytes(self.evidence.read_bytes())

        store = self._open_store()
        try:
            first = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=PROVENANCE_REF,
            )
            self.assertEqual(first.status, RECOVERED)

            self.evidence.write_bytes(evidence_b)
            sha_b = _sha256_bytes(self.evidence.read_bytes())
            self.assertNotEqual(sha_a, sha_b)

            second = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=PROVENANCE_REF,
            )

            self.assertEqual(second.status, ALREADY_RECOVERED)
            self.assertEqual(second.recovery_id, first.recovery_id)
            self.assertEqual(second.recovery_provenance_ref, PROVENANCE_REF)
            print(
                json.dumps(
                    {
                        "schema": "F2_TRIGGER6_WP206_EVIDENCE_CONTENT_FALSIFIER/v1",
                        "result": "COUNTEREXAMPLE_REPRODUCED_IF_TEST_PASS",
                        "provenance_ref": PROVENANCE_REF,
                        "evidence_sha256_before": sha_a,
                        "evidence_sha256_after": sha_b,
                        "first_status": first.status,
                        "repeat_status": second.status,
                        "runtime_credit": 0,
                        "whole_system_credit": 0,
                    },
                    sort_keys=True,
                )
            )
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
