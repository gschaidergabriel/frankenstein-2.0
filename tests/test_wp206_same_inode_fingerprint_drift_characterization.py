#!/usr/bin/env python3
"""REVIEW_ONLY characterization for the WP206 UnifiedDB authority boundary.

This file intentionally does not modify F2-WP-206 production semantics or claim mutation
authority.  It answers one narrower question left explicit by the current supervisor:
is the *full* UnifiedDBFingerprint receipt stable across legitimate mutations of the same
SQLite file/inode?

If the receipt changes while path/device/inode remain stable, that receipt cannot by itself
serve as an immutable replay epoch without an additional binding rule.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from state.unifieddb_identity import fingerprint_unifieddb


class SameInodeFingerprintDriftCharacterization(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "unified.db"
        connection = sqlite3.connect(self.db)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute(
                "CREATE TABLE stable_payload(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.commit()
        finally:
            connection.close()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def assert_same_file_identity(self, before, after) -> None:
        self.assertEqual(before.real_path, after.real_path)
        self.assertEqual(before.device, after.device)
        self.assertEqual(before.inode, after.inode)

    def test_legitimate_data_write_changes_full_receipt_without_inode_change(self) -> None:
        before = fingerprint_unifieddb(self.db)

        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "INSERT INTO stable_payload(id, value) VALUES(?, ?)", (1, "legitimate")
            )
            connection.commit()
        finally:
            connection.close()

        after = fingerprint_unifieddb(self.db)
        self.assert_same_file_identity(before, after)
        self.assertEqual(
            before.sqlite_schema_sha256,
            after.sqlite_schema_sha256,
            "data-only mutation should not need a schema change to move the full receipt",
        )
        self.assertNotEqual(before.sha256, after.sha256)
        self.assertNotEqual(
            before.receipt_sha256(),
            after.receipt_sha256(),
            "full fingerprint receipt is content-sensitive even on one stable inode",
        )

    def test_legitimate_schema_write_changes_full_receipt_without_inode_change(self) -> None:
        before = fingerprint_unifieddb(self.db)

        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "CREATE TABLE legitimate_checkpoint(id TEXT PRIMARY KEY, digest TEXT NOT NULL)"
            )
            connection.commit()
        finally:
            connection.close()

        after = fingerprint_unifieddb(self.db)
        self.assert_same_file_identity(before, after)
        self.assertNotEqual(before.sqlite_schema_sha256, after.sqlite_schema_sha256)
        self.assertNotEqual(before.sha256, after.sha256)
        self.assertNotEqual(
            before.receipt_sha256(),
            after.receipt_sha256(),
            "full fingerprint receipt is schema-sensitive even on one stable inode",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
