#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "state" / "unifieddb_identity.py"
SPEC = importlib.util.spec_from_file_location("f2_unifieddb_identity", MODULE_PATH)
assert SPEC and SPEC.loader
uid = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(uid)


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
        base = {"XDG_DATA_HOME": str(self.xdg)}
        base.update(extra)
        return base

    def test_existing_pointer_beats_environment(self) -> None:
        pointed = self.root / "moved" / "unified.db"
        pointed.parent.mkdir()
        pointed.write_bytes(b"pointer")
        self.pointer.write_text(str(pointed), encoding="utf-8")
        result = uid.resolve_unifieddb_path(
            env=self.env(AGENTZERO_DB=str(self.root / "env.db")),
            home=self.home,
            pointer_path=self.pointer,
            legacy_path=self.legacy,
        )
        self.assertEqual(result.source, "POINTER_EXISTING")
        self.assertEqual(result.path, str(pointed.absolute()))

    def test_stale_pointer_falls_through_to_environment(self) -> None:
        self.pointer.write_text(str(self.root / "missing.db"), encoding="utf-8")
        env_db = self.root / "selected-by-env.db"
        result = uid.resolve_unifieddb_path(
            env=self.env(AGENTZERO_DB=str(env_db)),
            home=self.home,
            pointer_path=self.pointer,
            legacy_path=self.legacy,
        )
        self.assertEqual(result.source, "ENV_AGENTZERO_DB")
        self.assertEqual(result.path, str(env_db.absolute()))
        self.assertFalse(result.exists_at_resolution)

    def test_agentzero_env_precedes_compatibility_alias(self) -> None:
        primary = self.root / "primary.db"
        compat = self.root / "compat.db"
        result = uid.resolve_unifieddb_path(
            env=self.env(AGENTZERO_DB=str(primary), UDB_DB_PATH=str(compat)),
            home=self.home,
            pointer_path=self.pointer,
            legacy_path=self.legacy,
        )
        self.assertEqual(result.source, "ENV_AGENTZERO_DB")
        self.assertEqual(result.path, str(primary.absolute()))

    def test_existing_xdg_target_precedes_legacy(self) -> None:
        target = self.xdg / "agentzero" / "unified.db"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"xdg")
        self.legacy.write_bytes(b"legacy")
        result = uid.resolve_unifieddb_path(
            env=self.env(), home=self.home, pointer_path=self.pointer, legacy_path=self.legacy
        )
        self.assertEqual(result.source, "XDG_EXISTING")
        self.assertEqual(result.path, str(target.absolute()))

    def test_existing_legacy_is_compatibility_fallback(self) -> None:
        self.legacy.write_bytes(b"legacy")
        result = uid.resolve_unifieddb_path(
            env=self.env(), home=self.home, pointer_path=self.pointer, legacy_path=self.legacy
        )
        self.assertEqual(result.source, "LEGACY_EXISTING")
        self.assertEqual(result.path, str(self.legacy.absolute()))

    def test_fresh_install_targets_xdg_not_plugin_tree(self) -> None:
        result = uid.resolve_unifieddb_path(
            env=self.env(), home=self.home, pointer_path=self.pointer, legacy_path=self.legacy
        )
        expected = self.xdg / "agentzero" / "unified.db"
        self.assertEqual(result.source, "XDG_FRESH_TARGET")
        self.assertEqual(result.path, str(expected.absolute()))
        self.assertNotEqual(result.path, str(self.legacy.absolute()))
        self.assertFalse(result.exists_at_resolution)


class FingerprintUnifiedDBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self) -> None:
        self.td.cleanup()

    def test_missing_is_explicit_not_fabricated(self) -> None:
        target = self.root / "missing.db"
        fp = uid.fingerprint_unifieddb(target)
        self.assertEqual(fp.status, "MISSING")
        self.assertFalse(fp.exists)
        self.assertIsNone(fp.sha256)

    def test_regular_file_binds_content_and_file_identity(self) -> None:
        target = self.root / "unified.db"
        payload = b"SQLite format 3\x00fixture"
        target.write_bytes(payload)
        fp = uid.fingerprint_unifieddb(target)
        self.assertEqual(fp.status, "REGULAR_FILE")
        self.assertTrue(fp.exists)
        self.assertEqual(fp.sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(fp.size, len(payload))
        self.assertIsInstance(fp.device, int)
        self.assertIsInstance(fp.inode, int)

    def test_content_change_changes_digest(self) -> None:
        target = self.root / "unified.db"
        target.write_bytes(b"a")
        first = uid.fingerprint_unifieddb(target)
        target.write_bytes(b"b")
        second = uid.fingerprint_unifieddb(target)
        self.assertNotEqual(first.sha256, second.sha256)

    def test_directory_is_rejected(self) -> None:
        with self.assertRaisesRegex(uid.UnifiedDBIdentityError, "NOT_REGULAR_FILE"):
            uid.fingerprint_unifieddb(self.root)

    def test_symlink_is_rejected(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unsupported")
        target = self.root / "real.db"
        link = self.root / "link.db"
        target.write_bytes(b"db")
        try:
            os.symlink(target, link)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        with self.assertRaisesRegex(uid.UnifiedDBIdentityError, "NOT_REGULAR_FILE"):
            uid.fingerprint_unifieddb(link)

    def test_mutation_during_hash_fails_closed(self) -> None:
        target = self.root / "unified.db"
        target.write_bytes(b"stable-before-hash")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
