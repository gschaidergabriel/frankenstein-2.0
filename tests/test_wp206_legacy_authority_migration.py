#!/usr/bin/env python3
"""Repository-hosted falsifiers for the WP206 G1 -> stable authority migration."""
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

from frankenstein2.persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    PersistentAgencyError,
)
from frankenstein2.persistent_agency_migration import (
    LegacyAuthorityMigrationManifest,
    LegacyAuthorityReceiptBinding,
    migrate_g1_authority_receipts,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).resolve().with_name("wp206_restart_probe.py")
SRC = REPO_ROOT / "src"


def _fake_receipt(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class LegacyAuthorityMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.cwd = self.root / "cwd"
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

    def _open_store(self) -> CanonicalPersistentAgencyStore:
        resolution = resolve_unifieddb_path(env=self.env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        return CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )

    def _checkpoint_row(self, checkpoint_id: str) -> tuple[str, str]:
        connection = sqlite3.connect(self.db)
        try:
            row = connection.execute(
                """SELECT checkpoint_sha256, unifieddb_authority_receipt_sha256
                   FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id=?""",
                (checkpoint_id,),
            ).fetchone()
        finally:
            connection.close()
        self.assertIsNotNone(row)
        return str(row[0]), str(row[1])

    def _set_receipt(self, checkpoint_id: str, receipt: str) -> None:
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                """UPDATE f2_persistent_agency_checkpoints
                   SET unifieddb_authority_receipt_sha256=?
                   WHERE checkpoint_id=?""",
                (receipt, checkpoint_id),
            )
            connection.commit()
        finally:
            connection.close()

    def _manifest(
        self,
        *,
        migration_id: str,
        bindings: tuple[tuple[str, str], ...],
    ) -> LegacyAuthorityMigrationManifest:
        items = []
        for checkpoint_id, legacy_receipt in bindings:
            checkpoint_sha, _ = self._checkpoint_row(checkpoint_id)
            items.append(
                LegacyAuthorityReceiptBinding(
                    checkpoint_id=checkpoint_id,
                    checkpoint_sha256=checkpoint_sha,
                    legacy_authority_receipt_sha256=legacy_receipt,
                )
            )
        return LegacyAuthorityMigrationManifest.create(
            migration_id=migration_id,
            bindings=tuple(items),
            provenance_refs=(
                "wp206:g1-accepted-representation",
                "supervisor:9.13-migration-compatibility-gate",
            ),
        )

    def test_g1_style_row_is_rejected_then_explicitly_migrated_and_tamper_stays_red(self) -> None:
        writer = self._probe("write")
        self.assertEqual(writer.returncode, 0, msg=writer.stderr)

        legacy_receipt = _fake_receipt("accepted-g1-mutable-full-fingerprint-receipt")
        self._set_receipt("checkpoint-0", legacy_receipt)

        before = self._probe("read")
        self.assertNotEqual(before.returncode, 0)
        self.assertIn("CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH", before.stderr)

        manifest = self._manifest(
            migration_id="wp206-g1-to-bound-file-v1",
            bindings=(("checkpoint-0", legacy_receipt),),
        )
        store = self._open_store()
        try:
            result = migrate_g1_authority_receipts(store, manifest)
            self.assertEqual(result.status, "MIGRATED")
            migrated = store.load_checkpoint("checkpoint-0")
            self.assertEqual(migrated.checkpoint_id, "checkpoint-0")
            stable_receipt = store.authority_receipt_sha256
        finally:
            store.close()

        _, stored_after = self._checkpoint_row("checkpoint-0")
        self.assertEqual(stored_after, stable_receipt)
        after = self._probe("read")
        self.assertEqual(after.returncode, 0, msg=after.stderr)

        forged_after_migration = _fake_receipt("post-migration-attacker-tamper")
        self._set_receipt("checkpoint-0", forged_after_migration)
        tampered_reader = self._probe("read")
        self.assertNotEqual(tampered_reader.returncode, 0)
        self.assertIn("CHECKPOINT_DB_AUTHORITY_RECEIPT_MISMATCH", tampered_reader.stderr)

        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                PersistentAgencyError,
                "MIGRATED_ROW_AUTHORITY_RECEIPT_TAMPER",
            ):
                migrate_g1_authority_receipts(store, manifest)
        finally:
            store.close()
        _, still_forged = self._checkpoint_row("checkpoint-0")
        self.assertEqual(
            still_forged,
            forged_after_migration,
            "a recorded migration must never become a generic tamper-healing path",
        )

    def test_manifest_must_bind_the_exact_pre_migration_receipt(self) -> None:
        writer = self._probe("write")
        self.assertEqual(writer.returncode, 0, msg=writer.stderr)
        actual_legacy = _fake_receipt("actual-g1-receipt")
        self._set_receipt("checkpoint-0", actual_legacy)

        forged_manifest = self._manifest(
            migration_id="wp206-g1-forged-manifest",
            bindings=(("checkpoint-0", _fake_receipt("wrong-g1-receipt")),),
        )
        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                PersistentAgencyError,
                "LEGACY_AUTHORITY_RECEIPT_MANIFEST_MISMATCH",
            ):
                migrate_g1_authority_receipts(store, forged_manifest)
        finally:
            store.close()
        _, stored = self._checkpoint_row("checkpoint-0")
        self.assertEqual(stored, actual_legacy)

    def test_manifest_must_cover_every_nonstable_row_atomically(self) -> None:
        writer = self._probe("write")
        self.assertEqual(writer.returncode, 0, msg=writer.stderr)
        successor = self._probe("read_advance")
        self.assertEqual(successor.returncode, 0, msg=successor.stderr)

        legacy_zero = _fake_receipt("legacy-row-zero")
        legacy_one = _fake_receipt("legacy-row-one")
        self._set_receipt("checkpoint-0", legacy_zero)
        self._set_receipt("checkpoint-1", legacy_one)

        partial_manifest = self._manifest(
            migration_id="wp206-g1-partial-manifest",
            bindings=(("checkpoint-0", legacy_zero),),
        )
        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                PersistentAgencyError,
                "LEGACY_MANIFEST_DOES_NOT_COVER_ALL_NONSTABLE_ROWS",
            ):
                migrate_g1_authority_receipts(store, partial_manifest)
        finally:
            store.close()

        self.assertEqual(self._checkpoint_row("checkpoint-0")[1], legacy_zero)
        self.assertEqual(self._checkpoint_row("checkpoint-1")[1], legacy_one)


if __name__ == "__main__":
    unittest.main(verbosity=2)
