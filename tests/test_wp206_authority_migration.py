#!/usr/bin/env python3
"""Hosted-CI falsifiers for F2-WP-206 G3 authority-receipt migration."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from frankenstein2.persistent_agency_authority_migration import (
    AuthorityMigrationError,
    CURRENT_RECEIPT_SCHEMA,
    LEGACY_RECEIPT_SCHEMA,
    MIGRATION_TABLE,
    migrate_legacy_authority_receipt,
)
from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "tests" / "wp206_restart_probe.py"
SRC = REPO_ROOT / "src"


class WP206AuthorityMigrationTests(unittest.TestCase):
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

    def _open_store(self) -> CanonicalPersistentAgencyStore:
        resolution = resolve_unifieddb_path(env=self.env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        return CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )

    def _emulate_accepted_g1_row(self) -> tuple[dict, str, str]:
        payload = self._write_current_checkpoint()
        legacy_receipt = str(payload["db_authority_receipt"])
        current_receipt = self._stored_receipt()
        self.assertRegex(legacy_receipt, r"^[0-9a-f]{64}$")
        self.assertRegex(current_receipt, r"^[0-9a-f]{64}$")
        self.assertNotEqual(legacy_receipt, current_receipt)
        self._replace_stored_receipt(legacy_receipt)
        return payload, legacy_receipt, current_receipt

    def _migrate(self, payload: dict, legacy_receipt: str, *, migration_id: str = "migration-1"):
        store = self._open_store()
        try:
            return migrate_legacy_authority_receipt(
                store,
                migration_id=migration_id,
                checkpoint_id="checkpoint-0",
                expected_checkpoint_sha256=payload["checkpoint_sha256"],
                expected_legacy_receipt_sha256=legacy_receipt,
                evidence_refs=("receipt:accepted-wp206-g1", "review:pr663"),
            )
        finally:
            store.close()

    def test_accepted_g1_row_migrates_then_current_reader_replays(self) -> None:
        payload, legacy_receipt, current_receipt = self._emulate_accepted_g1_row()

        before = self._probe("read")
        self.assertNotEqual(before.returncode, 0)
        self.assertIn("CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH", before.stderr)

        receipt = self._migrate(payload, legacy_receipt)
        self.assertEqual(receipt.from_schema, LEGACY_RECEIPT_SCHEMA)
        self.assertEqual(receipt.to_schema, CURRENT_RECEIPT_SCHEMA)
        self.assertEqual(receipt.from_receipt_sha256, legacy_receipt)
        self.assertEqual(receipt.to_receipt_sha256, current_receipt)
        self.assertEqual(receipt.checkpoint_sha256, payload["checkpoint_sha256"])

        after = self._probe("read")
        self.assertEqual(after.returncode, 0, msg=after.stderr)
        replay = json.loads(after.stdout)
        self.assertEqual(replay["checkpoint_id"], "checkpoint-0")
        self.assertEqual(replay["checkpoint_sha256"], payload["checkpoint_sha256"])

        connection = sqlite3.connect(self.db)
        try:
            migrated_row = connection.execute(
                f"""SELECT receipt_sha256, receipt_json, from_schema, to_schema,
                           from_receipt_sha256, to_receipt_sha256, checkpoint_sha256
                    FROM {MIGRATION_TABLE}
                    WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertIsNotNone(migrated_row)
            self.assertEqual(migrated_row[0], receipt.sha256())
            self.assertEqual(json.loads(migrated_row[1]), receipt.as_dict())
            self.assertEqual(migrated_row[2], LEGACY_RECEIPT_SCHEMA)
            self.assertEqual(migrated_row[3], CURRENT_RECEIPT_SCHEMA)
            self.assertEqual(migrated_row[4], legacy_receipt)
            self.assertEqual(migrated_row[5], current_receipt)
            self.assertEqual(migrated_row[6], payload["checkpoint_sha256"])
        finally:
            connection.close()

    def test_wrong_external_legacy_receipt_fails_without_mutation(self) -> None:
        payload, legacy_receipt, _ = self._emulate_accepted_g1_row()
        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                AuthorityMigrationError, "EXPECTED_LEGACY_RECEIPT_MISMATCH"
            ):
                migrate_legacy_authority_receipt(
                    store,
                    migration_id="migration-wrong-legacy",
                    checkpoint_id="checkpoint-0",
                    expected_checkpoint_sha256=payload["checkpoint_sha256"],
                    expected_legacy_receipt_sha256="0" * 64,
                    evidence_refs=("receipt:wrong",),
                )
        finally:
            store.close()
        self.assertEqual(self._stored_receipt(), legacy_receipt)

    def test_wrong_checkpoint_digest_fails_without_mutation(self) -> None:
        payload, legacy_receipt, _ = self._emulate_accepted_g1_row()
        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                AuthorityMigrationError, "EXPECTED_CHECKPOINT_DIGEST_MISMATCH"
            ):
                migrate_legacy_authority_receipt(
                    store,
                    migration_id="migration-wrong-checkpoint",
                    checkpoint_id="checkpoint-0",
                    expected_checkpoint_sha256="f" * 64,
                    expected_legacy_receipt_sha256=legacy_receipt,
                    evidence_refs=("receipt:accepted-wp206-g1",),
                )
        finally:
            store.close()
        self.assertEqual(self._stored_receipt(), legacy_receipt)
        self.assertEqual(payload["checkpoint_sha256"], payload["checkpoint_sha256"])

    def test_conflicting_second_migration_id_is_rejected(self) -> None:
        payload, legacy_receipt, _ = self._emulate_accepted_g1_row()
        first = self._migrate(payload, legacy_receipt, migration_id="migration-first")
        replay = self._migrate(payload, legacy_receipt, migration_id="migration-first")
        self.assertEqual(replay.sha256(), first.sha256())

        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                AuthorityMigrationError, "CHECKPOINT_ALREADY_MIGRATED_BY_OTHER_ID"
            ):
                migrate_legacy_authority_receipt(
                    store,
                    migration_id="migration-conflict",
                    checkpoint_id="checkpoint-0",
                    expected_checkpoint_sha256=payload["checkpoint_sha256"],
                    expected_legacy_receipt_sha256=legacy_receipt,
                    evidence_refs=("receipt:accepted-wp206-g1", "review:pr663"),
                )
        finally:
            store.close()

    def test_post_migration_authority_receipt_tamper_fails_closed(self) -> None:
        payload, legacy_receipt, _ = self._emulate_accepted_g1_row()
        self._migrate(payload, legacy_receipt)
        self._replace_stored_receipt("0" * 64)

        reader = self._probe("read")
        self.assertNotEqual(reader.returncode, 0)
        self.assertIn("CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH", reader.stderr)

        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                Exception, "CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH"
            ):
                migrate_legacy_authority_receipt(
                    store,
                    migration_id="migration-1",
                    checkpoint_id="checkpoint-0",
                    expected_checkpoint_sha256=payload["checkpoint_sha256"],
                    expected_legacy_receipt_sha256=legacy_receipt,
                    evidence_refs=("receipt:accepted-wp206-g1", "review:pr663"),
                )
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
