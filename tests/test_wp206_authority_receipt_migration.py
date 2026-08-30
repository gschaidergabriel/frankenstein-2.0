#!/usr/bin/env python3
"""Executable review donor for WP206 G1 -> stable authority receipt migration."""
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
from frankenstein2.wp206_authority_receipt_migration import (
    MIGRATION_AUDIT_TABLE,
    MIGRATION_SCHEMA,
    LegacyAuthorityReceiptMigrationPermit,
    migrate_legacy_checkpoint_authority_receipt,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "tests" / "wp206_restart_probe.py"
SRC = REPO_ROOT / "src"
CHECKPOINT_TABLE = "f2_persistent_agency_checkpoints"


class WP206AuthorityReceiptMigrationTests(unittest.TestCase):
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

    def _write_fixture(self) -> dict:
        result = self._probe("write")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return json.loads(result.stdout)

    def _row(self) -> tuple:
        connection = sqlite3.connect(self.db)
        try:
            row = connection.execute(
                f"""SELECT checkpoint_sha256, canonical_db_path, db_device, db_inode,
                           unifieddb_authority_receipt_sha256
                    FROM {CHECKPOINT_TABLE} WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertIsNotNone(row)
            return row
        finally:
            connection.close()

    def _replace_receipt(self, receipt: str) -> None:
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                f"""UPDATE {CHECKPOINT_TABLE}
                    SET unifieddb_authority_receipt_sha256=?
                    WHERE checkpoint_id='checkpoint-0'""",
                (receipt,),
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

    def _permit(
        self,
        *,
        legacy_receipt: str,
        checkpoint_sha: str,
        path: str,
        device: int,
        inode: int,
        migration_id: str = "migration-g1-checkpoint-0",
    ) -> LegacyAuthorityReceiptMigrationPermit:
        return LegacyAuthorityReceiptMigrationPermit(
            schema=MIGRATION_SCHEMA,
            migration_id=migration_id,
            checkpoint_id="checkpoint-0",
            checkpoint_sha256=checkpoint_sha,
            legacy_authority_receipt_sha256=legacy_receipt,
            canonical_db_path=path,
            db_device=device,
            db_inode=inode,
            provenance_refs=(
                "wp206:g1-accepted-checkpoint",
                "review:pr663-migration-counterevidence",
            ),
        )

    def test_accepted_g1_style_row_requires_explicit_migration_then_replays(self) -> None:
        writer = self._write_fixture()
        checkpoint_sha, path, device, inode, stable_receipt = self._row()
        legacy_receipt = writer["db_authority_receipt"]
        self.assertNotEqual(legacy_receipt, stable_receipt)

        # Reproduce the accepted-G1 representation: the checkpoint row carries the
        # full mutable UnifiedDBFingerprint receipt rather than the new stable receipt.
        self._replace_receipt(legacy_receipt)

        before = self._probe("read")
        self.assertNotEqual(before.returncode, 0)
        self.assertIn("CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH", before.stderr)

        store = self._open_store()
        try:
            receipt = migrate_legacy_checkpoint_authority_receipt(
                store,
                self._permit(
                    legacy_receipt=legacy_receipt,
                    checkpoint_sha=checkpoint_sha,
                    path=path,
                    device=device,
                    inode=inode,
                ),
            )
            self.assertEqual(receipt.old_authority_receipt_sha256, legacy_receipt)
            self.assertEqual(receipt.new_authority_receipt_sha256, stable_receipt)
            audit = store.connection.execute(
                f"""SELECT checkpoint_id, checkpoint_sha256,
                           old_authority_receipt_sha256,
                           new_authority_receipt_sha256, permit_sha256, receipt_sha256
                    FROM {MIGRATION_AUDIT_TABLE} WHERE migration_id=?""",
                (receipt.migration_id,),
            ).fetchone()
            self.assertIsNotNone(audit)
            self.assertEqual(audit[0], "checkpoint-0")
            self.assertEqual(audit[1], checkpoint_sha)
            self.assertEqual(audit[2], legacy_receipt)
            self.assertEqual(audit[3], stable_receipt)
            self.assertEqual(audit[4], receipt.permit_sha256)
            self.assertEqual(audit[5], receipt.sha256())
        finally:
            store.close()

        after = self._probe("read")
        self.assertEqual(after.returncode, 0, msg=after.stderr)
        self.assertEqual(json.loads(after.stdout)["checkpoint_id"], "checkpoint-0")

        # Post-migration receipt tampering must remain a hard failure.
        self._replace_receipt("0" * 64)
        tampered = self._probe("read")
        self.assertNotEqual(tampered.returncode, 0)
        self.assertIn("CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH", tampered.stderr)

    def test_wrong_external_legacy_receipt_cannot_authorize_migration(self) -> None:
        writer = self._write_fixture()
        checkpoint_sha, path, device, inode, stable_receipt = self._row()
        legacy_receipt = writer["db_authority_receipt"]
        self._replace_receipt(legacy_receipt)

        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                Exception,
                "WP206_MIGRATION_LEGACY_RECEIPT_MISMATCH",
            ):
                migrate_legacy_checkpoint_authority_receipt(
                    store,
                    self._permit(
                        legacy_receipt="f" * 64,
                        checkpoint_sha=checkpoint_sha,
                        path=path,
                        device=device,
                        inode=inode,
                        migration_id="migration-wrong-receipt",
                    ),
                )
        finally:
            store.close()

        self.assertEqual(self._row()[4], legacy_receipt)
        self.assertNotEqual(self._row()[4], stable_receipt)

    def test_current_receipt_is_not_reclassified_as_legacy(self) -> None:
        self._write_fixture()
        checkpoint_sha, path, device, inode, stable_receipt = self._row()
        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                Exception,
                "WP206_LEGACY_RECEIPT_ALREADY_CURRENT",
            ):
                migrate_legacy_checkpoint_authority_receipt(
                    store,
                    self._permit(
                        legacy_receipt=stable_receipt,
                        checkpoint_sha=checkpoint_sha,
                        path=path,
                        device=device,
                        inode=inode,
                        migration_id="migration-current-receipt",
                    ),
                )
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
