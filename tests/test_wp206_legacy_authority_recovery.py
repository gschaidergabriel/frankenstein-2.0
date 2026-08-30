#!/usr/bin/env python3
"""Executable migration/tamper regressions for F2-WP-206 generation 3."""
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
    RECOVERY_TABLE,
    recover_legacy_g1_checkpoint_authority,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "tests" / "wp206_restart_probe.py"
SRC = REPO_ROOT / "src"
LEGACY_PROVENANCE = "evidence:accepted-wp206-g1-full-fingerprint-receipt"


class WP206LegacyAuthorityRecoveryTests(unittest.TestCase):
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

    def _replace_receipt(self, value: str) -> None:
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

    def _open_store(self) -> CanonicalPersistentAgencyStore:
        resolution = resolve_unifieddb_path(env=self.env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        return CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )

    def _emulate_accepted_g1_row(self) -> tuple[str, str]:
        payload = self._write_current_checkpoint()
        historical_g1_receipt = str(payload["db_authority_receipt"])
        current_bound_file_receipt = self._stored_receipt()
        self.assertRegex(historical_g1_receipt, r"^[0-9a-f]{64}$")
        self.assertRegex(current_bound_file_receipt, r"^[0-9a-f]{64}$")
        self.assertNotEqual(historical_g1_receipt, current_bound_file_receipt)
        self._replace_receipt(historical_g1_receipt)
        return historical_g1_receipt, current_bound_file_receipt

    def test_explicit_g1_recovery_restores_current_reader_without_silent_acceptance(self) -> None:
        historical, current = self._emulate_accepted_g1_row()
        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                PersistentAgencyError, "CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH"
            ):
                store.load_checkpoint("checkpoint-0")

            receipt = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=LEGACY_PROVENANCE,
            )
            self.assertEqual(receipt.status, RECOVERED)
            self.assertEqual(receipt.legacy_authority_receipt_sha256, historical)
            self.assertEqual(receipt.rebound_authority_receipt_sha256, current)
            self.assertEqual(self._stored_receipt(), current)

            checkpoint = store.load_checkpoint("checkpoint-0")
            self.assertEqual(checkpoint.checkpoint_id, "checkpoint-0")
            row = store.connection.execute(
                f"SELECT recovery_id, checkpoint_sha256 FROM {RECOVERY_TABLE} "
                "WHERE checkpoint_id='checkpoint-0'"
            ).fetchone()
            self.assertEqual(row, (receipt.recovery_id, receipt.checkpoint_sha256))
        finally:
            store.close()

    def test_wrong_external_legacy_receipt_cannot_rebind_row(self) -> None:
        historical, _ = self._emulate_accepted_g1_row()
        wrong = "0" * 64 if historical != "0" * 64 else "1" * 64
        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                PersistentAgencyError, "LEGACY_RECOVERY_EXPECTED_RECEIPT_MISMATCH"
            ):
                recover_legacy_g1_checkpoint_authority(
                    store=store,
                    checkpoint_id="checkpoint-0",
                    expected_legacy_authority_receipt_sha256=wrong,
                    recovery_provenance_ref=LEGACY_PROVENANCE,
                )
            self.assertEqual(self._stored_receipt(), historical)
            with self.assertRaisesRegex(
                PersistentAgencyError, "CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH"
            ):
                store.load_checkpoint("checkpoint-0")
        finally:
            store.close()

    def test_checkpoint_payload_tamper_is_rejected_before_rebinding(self) -> None:
        historical, _ = self._emulate_accepted_g1_row()
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                """UPDATE f2_persistent_agency_checkpoints
                   SET checkpoint_json='{}'
                   WHERE checkpoint_id='checkpoint-0'"""
            )
            connection.commit()
        finally:
            connection.close()
        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                PersistentAgencyError, "CHECKPOINT_DIGEST_MISMATCH"
            ):
                recover_legacy_g1_checkpoint_authority(
                    store=store,
                    checkpoint_id="checkpoint-0",
                    expected_legacy_authority_receipt_sha256=historical,
                    recovery_provenance_ref=LEGACY_PROVENANCE,
                )
            self.assertEqual(self._stored_receipt(), historical)
        finally:
            store.close()

    def test_file_identity_metadata_tamper_is_rejected_before_rebinding(self) -> None:
        historical, _ = self._emulate_accepted_g1_row()
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                """UPDATE f2_persistent_agency_checkpoints
                   SET db_inode=db_inode+1
                   WHERE checkpoint_id='checkpoint-0'"""
            )
            connection.commit()
        finally:
            connection.close()
        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                PersistentAgencyError, "CHECKPOINT_DB_FILE_IDENTITY_DRIFT"
            ):
                recover_legacy_g1_checkpoint_authority(
                    store=store,
                    checkpoint_id="checkpoint-0",
                    expected_legacy_authority_receipt_sha256=historical,
                    recovery_provenance_ref=LEGACY_PROVENANCE,
                )
        finally:
            store.close()

    def test_exact_repeat_is_idempotent_while_post_migration_drift_fails_closed(self) -> None:
        historical, current = self._emulate_accepted_g1_row()
        store = self._open_store()
        try:
            first = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=LEGACY_PROVENANCE,
            )
            second = recover_legacy_g1_checkpoint_authority(
                store=store,
                checkpoint_id="checkpoint-0",
                expected_legacy_authority_receipt_sha256=historical,
                recovery_provenance_ref=LEGACY_PROVENANCE,
            )
            self.assertEqual(first.recovery_id, second.recovery_id)
            self.assertEqual(second.status, ALREADY_RECOVERED)
            self.assertEqual(self._stored_receipt(), current)

            tampered = "f" * 64 if current != "f" * 64 else "e" * 64
            self._replace_receipt(tampered)
            with self.assertRaisesRegex(
                PersistentAgencyError,
                "LEGACY_RECOVERY_POST_MIGRATION_AUTHORITY_DRIFT",
            ):
                recover_legacy_g1_checkpoint_authority(
                    store=store,
                    checkpoint_id="checkpoint-0",
                    expected_legacy_authority_receipt_sha256=historical,
                    recovery_provenance_ref=LEGACY_PROVENANCE,
                )
            with self.assertRaisesRegex(
                PersistentAgencyError, "CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH"
            ):
                store.load_checkpoint("checkpoint-0")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
