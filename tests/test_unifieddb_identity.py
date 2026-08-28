#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from state import unifieddb_identity as uid  # noqa: E402


class ResolveUnifiedDBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.pointer = self.root / "config" / "db_pfad.txt"
        self.pointer.parent.mkdir()
        self.xdg = self.root / "data"
        self.legacy = self.root / "plugin" / "unified.db"
        self.legacy.parent.mkdir()

    def tearDown(self) -> None:
        self.td.cleanup()

    def env(self, **extra: str) -> dict[str, str]:
        base = {
            "XDG_DATA_HOME": str(self.xdg),
            "XDG_CONFIG_HOME": str(self.root / "xdg-config"),
        }
        base.update(extra)
        return base

    def make_sqlite(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS t(id INTEGER PRIMARY KEY)")
            conn.commit()
        finally:
            conn.close()
        return path

    def test_pointer_and_env_same_target_are_one_explicit_authority(self) -> None:
        pointed = self.make_sqlite(self.root / "moved" / "unified.db")
        self.pointer.write_text(str(pointed), encoding="utf-8")
        result = uid.resolve_unifieddb_path(
            env=self.env(AGENTZERO_DB=str(pointed)),
            home=self.home,
            pointer_path=self.pointer,
            legacy_path=self.legacy,
        )
        self.assertEqual(result.path, str(pointed.resolve()))
        self.assertTrue(result.source.startswith("EXPLICIT_"))
        self.assertEqual(result.explicit_sources, ("POINTER", "AGENTZERO_DB"))

    def test_pointer_and_env_disagreement_fails_closed(self) -> None:
        pointed = self.make_sqlite(self.root / "pointed.db")
        self.pointer.write_text(str(pointed), encoding="utf-8")
        with self.assertRaisesRegex(uid.UnifiedDBAuthorityConflict, "AUTHORITY_CONFLICT"):
            uid.resolve_unifieddb_path(
                env=self.env(AGENTZERO_DB=str(self.root / "env.db")),
                home=self.home,
                pointer_path=self.pointer,
                legacy_path=self.legacy,
            )

    def test_stale_pointer_fails_closed_instead_of_selecting_second_db(self) -> None:
        self.pointer.write_text(str(self.root / "missing.db"), encoding="utf-8")
        with self.assertRaisesRegex(uid.UnifiedDBIdentityError, "POINTER_TARGET_MISSING"):
            uid.resolve_unifieddb_path(
                env=self.env(AGENTZERO_DB=str(self.root / "env.db")),
                home=self.home,
                pointer_path=self.pointer,
                legacy_path=self.legacy,
            )

    def test_relative_pointer_text_is_anchored_to_pointer_file(self) -> None:
        pointed = self.make_sqlite(self.pointer.parent / "state" / "unified.db")
        self.pointer.write_text("state/unified.db\n", encoding="utf-8")
        result = uid.resolve_unifieddb_path(
            env=self.env(), home=self.home, pointer_path=self.pointer, legacy_path=self.legacy
        )
        self.assertEqual(result.path, str(pointed.resolve()))

    def test_relative_environment_db_path_is_forbidden(self) -> None:
        with self.assertRaisesRegex(uid.UnifiedDBIdentityError, "RELATIVE_PATH_FORBIDDEN"):
            uid.resolve_unifieddb_path(
                env=self.env(AGENTZERO_DB="relative/unified.db"),
                home=self.home,
                pointer_path=self.pointer,
                legacy_path=self.legacy,
            )

    def test_conflicting_environment_aliases_fail_closed(self) -> None:
        with self.assertRaisesRegex(uid.UnifiedDBAuthorityConflict, "AUTHORITY_CONFLICT"):
            uid.resolve_unifieddb_path(
                env=self.env(
                    AGENTZERO_DB=str(self.root / "primary.db"),
                    UDB_DB_PATH=str(self.root / "compat.db"),
                ),
                home=self.home,
                pointer_path=self.pointer,
                legacy_path=self.legacy,
            )

    def test_existing_xdg_target_precedes_legacy(self) -> None:
        target = self.make_sqlite(self.xdg / "agentzero" / "unified.db")
        self.make_sqlite(self.legacy)
        result = uid.resolve_unifieddb_path(
            env=self.env(), home=self.home, pointer_path=self.pointer, legacy_path=self.legacy
        )
        self.assertEqual(result.source, "XDG_EXISTING")
        self.assertEqual(result.path, str(target.resolve()))

    def test_existing_legacy_is_compatibility_fallback(self) -> None:
        self.make_sqlite(self.legacy)
        result = uid.resolve_unifieddb_path(
            env=self.env(), home=self.home, pointer_path=self.pointer, legacy_path=self.legacy
        )
        self.assertEqual(result.source, "LEGACY_EXISTING")
        self.assertEqual(result.path, str(self.legacy.resolve()))

    def test_fresh_install_targets_xdg_not_plugin_tree(self) -> None:
        result = uid.resolve_unifieddb_path(
            env=self.env(), home=self.home, pointer_path=self.pointer, legacy_path=self.legacy
        )
        expected = self.xdg / "agentzero" / "unified.db"
        self.assertEqual(result.source, "XDG_FRESH_TARGET")
        self.assertEqual(result.path, str(expected.resolve()))
        self.assertNotEqual(result.path, str(self.legacy.resolve()))
        self.assertFalse(result.exists_at_resolution)


class FingerprintUnifiedDBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self) -> None:
        self.td.cleanup()

    def make_sqlite(self, path: Path, table: str = "alpha") -> Path:
        conn = sqlite3.connect(path)
        try:
            conn.execute(f"CREATE TABLE {table}(id INTEGER PRIMARY KEY)")
            conn.commit()
        finally:
            conn.close()
        return path

    def test_missing_is_explicit_not_fabricated(self) -> None:
        target = self.root / "missing.db"
        fp = uid.fingerprint_unifieddb(target)
        self.assertEqual(fp.status, "MISSING")
        self.assertFalse(fp.exists)
        self.assertIsNone(fp.sha256)

    def test_valid_sqlite_binds_file_and_schema_identity(self) -> None:
        target = self.make_sqlite(self.root / "unified.db")
        before = target.stat()
        fp = uid.fingerprint_unifieddb(target)
        after = target.stat()
        self.assertEqual(fp.status, "SQLITE3_REGULAR_FILE")
        self.assertTrue(fp.exists)
        self.assertEqual(fp.path, str(target.absolute()))
        self.assertEqual(fp.real_path, str(target.resolve()))
        self.assertEqual(fp.size, before.st_size)
        self.assertEqual(before.st_mtime_ns, after.st_mtime_ns)
        self.assertEqual(len(fp.sha256 or ""), 64)
        self.assertEqual(len(fp.sqlite_schema_sha256 or ""), 64)
        self.assertEqual(len(fp.receipt_sha256()), 64)
        self.assertEqual(fp.classification, "SQLITE_IDENTITY_NOT_STATE_SNAPSHOT")

    def test_schema_change_changes_schema_digest(self) -> None:
        target = self.make_sqlite(self.root / "unified.db")
        first = uid.fingerprint_unifieddb(target)
        conn = sqlite3.connect(target)
        try:
            conn.execute("CREATE TABLE beta(value TEXT)")
            conn.commit()
        finally:
            conn.close()
        second = uid.fingerprint_unifieddb(target)
        self.assertNotEqual(first.sqlite_schema_sha256, second.sqlite_schema_sha256)

    def test_non_sqlite_regular_file_is_rejected(self) -> None:
        target = self.root / "fake.db"
        target.write_bytes(b"not sqlite")
        with self.assertRaisesRegex(uid.UnifiedDBIdentityError, "NOT_SQLITE3"):
            uid.fingerprint_unifieddb(target)

    def test_directory_is_rejected(self) -> None:
        with self.assertRaisesRegex(uid.UnifiedDBIdentityError, "NOT_REGULAR_FILE"):
            uid.fingerprint_unifieddb(self.root)

    def test_symlink_is_rejected(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unsupported")
        target = self.make_sqlite(self.root / "real.db")
        link = self.root / "link.db"
        try:
            os.symlink(target, link)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        with self.assertRaisesRegex(uid.UnifiedDBIdentityError, "NOT_REGULAR_FILE"):
            uid.fingerprint_unifieddb(link)

    def test_mutation_during_hash_fails_closed(self) -> None:
        target = self.make_sqlite(self.root / "unified.db")
        original_hash = uid._sha256_fd

        def hash_then_mutate(fd: int, chunk_size: int = 1024 * 1024) -> str:
            digest = original_hash(fd, chunk_size)
            with target.open("ab") as stream:
                stream.write(b"-mutated")
                stream.flush()
                os.fsync(stream.fileno())
            return digest

        with mock.patch.object(uid, "_sha256_fd", side_effect=hash_then_mutate):
            with self.assertRaisesRegex(uid.UnifiedDBIdentityError, "MUTATED_DURING_FINGERPRINT"):
                uid.fingerprint_unifieddb(target)

    def test_relative_fingerprint_path_is_forbidden(self) -> None:
        with self.assertRaisesRegex(uid.UnifiedDBIdentityError, "RELATIVE_PATH_FORBIDDEN"):
            uid.fingerprint_unifieddb("relative.db")


if __name__ == "__main__":
    unittest.main(verbosity=2)
