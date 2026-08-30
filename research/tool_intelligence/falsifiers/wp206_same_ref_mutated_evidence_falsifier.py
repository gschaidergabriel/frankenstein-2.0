#!/usr/bin/env python3
"""REVIEW_ONLY successor-dynamic falsifier for WP206 recovery evidence binding.

Historical G4 behavior reproduced a real counterexample: external evidence bytes could change
while recovery_provenance_ref stayed identical and an exact repeat still returned
ALREADY_RECOVERED. G5 closes that deficit by requiring a typed content-bearing evidence
subject and binding its internally derived digest into the recovery row/identity.

A PASS now means the historical counterexample is CLOSED at repository-component scope:
identical provenance with changed evidence content must fail closed without mutating the first
recovery. This remains review evidence only and mints no runtime or whole-system credit.
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
)
from frankenstein2.wp206_legacy_authority_recovery import (
    EVIDENCE_SUBJECT_BOUND_G5,
    RECOVERED,
    LegacyRecoveryEvidenceSubject,
    recover_legacy_g1_checkpoint_authority,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


REPO_ROOT = Path(__file__).resolve().parents[3]
PROBE = REPO_ROOT / "tests" / "wp206_restart_probe.py"
SRC = REPO_ROOT / "src"
PROVENANCE_REF = "evidence:mutable-external-object"


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

    def _write_legacy_style_row(self) -> tuple[str, str]:
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
            row = connection.execute(
                """SELECT checkpoint_sha256, unifieddb_authority_receipt_sha256
                   FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertIsNotNone(row)
            checkpoint_sha, current_receipt = str(row[0]), str(row[1])
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
        return historical_receipt, checkpoint_sha

    def _open_store(self) -> CanonicalPersistentAgencyStore:
        resolution = resolve_unifieddb_path(env=self.env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        return CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )

    @staticmethod
    def _subject(
        *, historical: str, checkpoint_sha: str, evidence_text: str
    ) -> LegacyRecoveryEvidenceSubject:
        return LegacyRecoveryEvidenceSubject(
            source_ref=PROVENANCE_REF,
            checkpoint_id="checkpoint-0",
            checkpoint_sha256=checkpoint_sha,
            legacy_authority_receipt_sha256=historical,
            evidence={
                "kind": "review-only-external-evidence",
                "raw_utf8": evidence_text,
            },
        )

    def test_same_ref_mutated_external_evidence_is_rejected_under_g5(self) -> None:
        historical, checkpoint_sha = self._write_legacy_style_row()
        evidence_a = '{"claim":"legacy receipt witnessed","version":1}\n'
        evidence_b = '{"claim":"different evidence at same reference","version":2}\n'

        store = self._open_store()
        try:
            first = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=PROVENANCE_REF,
                recovery_evidence_subject=self._subject(
                    historical=historical,
                    checkpoint_sha=checkpoint_sha,
                    evidence_text=evidence_a,
                ),
            )
            self.assertEqual(first.status, RECOVERED)
            self.assertEqual(
                first.recovery_evidence_subject_state,
                EVIDENCE_SUBJECT_BOUND_G5,
            )
            self.assertRegex(str(first.recovery_evidence_sha256), r"^[0-9a-f]{64}$")

            with self.assertRaisesRegex(
                PersistentAgencyError,
                "LEGACY_RECOVERY_EVIDENCE_SUBJECT_CONFLICT",
            ):
                recover_legacy_g1_checkpoint_authority(
                    store=store,
                    checkpoint_id="checkpoint-0",
                    expected_legacy_authority_receipt_sha256=historical,
                    recovery_provenance_ref=PROVENANCE_REF,
                    recovery_evidence_subject=self._subject(
                        historical=historical,
                        checkpoint_sha=checkpoint_sha,
                        evidence_text=evidence_b,
                    ),
                )

            row = store.connection.execute(
                """SELECT recovery_id, recovery_evidence_sha256,
                          recovery_evidence_subject_state
                   FROM f2_wp206_legacy_authority_recoveries
                   WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertEqual(
                row,
                (
                    first.recovery_id,
                    first.recovery_evidence_sha256,
                    EVIDENCE_SUBJECT_BOUND_G5,
                ),
            )
            print(
                json.dumps(
                    {
                        "schema": "F2_TRIGGER6_WP206_EVIDENCE_CONTENT_FALSIFIER/v2",
                        "result": "HISTORICAL_COUNTEREXAMPLE_CLOSED_G5_IF_TEST_PASS",
                        "provenance_ref": PROVENANCE_REF,
                        "first_recovery_id": first.recovery_id,
                        "first_evidence_sha256": first.recovery_evidence_sha256,
                        "mutated_repeat": "FAIL_CLOSED",
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
