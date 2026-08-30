#!/usr/bin/env python3
"""REVIEW_ONLY discriminator for same-inode UnifiedDB authority drift.

This test intentionally asks a narrower question than F2-WP-206 generation 2 owns.
Generation 2 repairs persisted authority-receipt replay binding. This discriminator checks
whether an already-open CanonicalPersistentAgencyStore detects a later SQLite main-file
content/schema mutation that preserves the exact device+inode identity.

A failing test is negative component evidence only. UnifiedDBFingerprint is explicitly an
identity receipt, not a full SQLite state snapshot, so failure does not by itself prove the
correct repair is live re-fingerprinting; it proves only that device+inode alone does not
notice this class of mutation while the cached authority receipt has become stale.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from frankenstein2.persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    PersistentAgencyError,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


class Wp206SameInodeFingerprintRefreshFalsifier(unittest.TestCase):
    def test_same_inode_schema_mutation_cannot_leave_cached_authority_receipt_accepted(self):
        """Preregistered desired invariant expected to FAIL on the current boundary."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            db = root / "canonical" / "unified.db"
            db.parent.mkdir()

            bootstrap = sqlite3.connect(db)
            try:
                bootstrap.execute(
                    "CREATE TABLE bootstrap_identity(id INTEGER PRIMARY KEY)"
                )
                bootstrap.commit()
            finally:
                bootstrap.close()

            env = {"FRANKENSTEIN2_DB": str(db)}
            resolution = resolve_unifieddb_path(env=env, home=home)

            # First let WP206 initialize its own table, then bind a fresh fingerprint to the
            # fully initialized file so this test is not merely detecting WP206's own setup.
            initial = fingerprint_unifieddb(db)
            initializer = CanonicalPersistentAgencyStore.open(
                resolution=resolution,
                fingerprint=initial,
            )
            try:
                initializer.initialize_schema()
            finally:
                initializer.close()

            bound = fingerprint_unifieddb(db)
            store = CanonicalPersistentAgencyStore.open(
                resolution=resolution,
                fingerprint=bound,
            )
            try:
                bound_receipt = store.authority_receipt_sha256
                before = os.stat(db)

                # Independent committed schema mutation on the same SQLite main file.
                external = sqlite3.connect(db)
                try:
                    external.execute(
                        "CREATE TABLE independently_added_after_store_open("
                        "id INTEGER PRIMARY KEY, note TEXT NOT NULL)"
                    )
                    external.commit()
                finally:
                    external.close()

                after = os.stat(db)
                self.assertEqual(
                    (before.st_dev, before.st_ino),
                    (after.st_dev, after.st_ino),
                    "discriminator requires the exact same device+inode",
                )

                refreshed = fingerprint_unifieddb(db)
                self.assertEqual(bound.device, refreshed.device)
                self.assertEqual(bound.inode, refreshed.inode)
                self.assertNotEqual(bound.sqlite_schema_sha256, refreshed.sqlite_schema_sha256)
                self.assertNotEqual(bound.receipt_sha256(), refreshed.receipt_sha256())
                self.assertEqual(store.authority_receipt_sha256, bound_receipt)
                self.assertNotEqual(store.authority_receipt_sha256, refreshed.receipt_sha256())

                # Desired fail-closed discriminator. Current store-use fencing checks only
                # device+inode, so this should fail until the architecture deliberately binds
                # the live authority-receipt policy for same-inode mutation.
                with self.assertRaisesRegex(PersistentAgencyError, "UNIFIEDDB"):
                    store._assert_current_file_identity()
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
