#!/usr/bin/env python3
"""Hosted-CI falsifiers for F2-WP-206 Persistent Agency integration."""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from frankenstein2.persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    PersistentAgencyError,
    advance_checkpoint,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).resolve().with_name("wp206_restart_probe.py")
SRC = REPO_ROOT / "src"


class PersistentAgencyIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.cwd = self.root / "unrelated-cwd"
        self.cwd.mkdir()
        self.db = self.root / "canonical" / "unified.db"
        self.db.parent.mkdir()
        self._create_sqlite(self.db)
        self.base_env = os.environ.copy()
        self.base_env["HOME"] = str(self.home)
        self.base_env["FRANKENSTEIN2_DB"] = str(self.db)
        self.base_env["PYTHONPATH"] = str(SRC)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @staticmethod
    def _create_sqlite(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS f2_test_bootstrap(id INTEGER PRIMARY KEY)"
            )
            connection.commit()
        finally:
            connection.close()

    def _probe(
        self,
        mode: str,
        *,
        extra_env: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = self.base_env.copy()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(PROBE), mode],
            cwd=str(self.cwd if cwd is None else cwd),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def _write_process_a(self) -> dict:
        result = self._probe("write")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["resolved_path"], str(self.db.resolve()))
        self.assertEqual(payload["journal_mode"], "WAL")
        self.assertTrue(payload["wal_exists_before_exit"])
        self.assertGreater(payload["wal_size_before_exit"], 0)
        self.assertTrue(Path(str(self.db) + "-wal").exists())
        return payload

    def _open_store_current_process(self) -> CanonicalPersistentAgencyStore:
        resolution = resolve_unifieddb_path(
            env=self.base_env,
            home=self.home,
        )
        fingerprint = fingerprint_unifieddb(resolution.path)
        return CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )

    def test_real_restart_recovers_wal_goal_and_next_tick_identity(self) -> None:
        writer = self._write_process_a()

        reader = self._probe("read_advance")
        self.assertEqual(reader.returncode, 0, msg=reader.stderr)
        after_restart = json.loads(reader.stdout)

        self.assertEqual(after_restart["resolved_path"], str(self.db.resolve()))
        self.assertEqual(after_restart["goal_statuses"], ["ACTIVE"])
        self.assertEqual(
            after_restart["wake_classification"], "ABSTAIN_NOT_OBSERVED"
        )
        self.assertFalse(after_restart["wake"])
        self.assertEqual(
            after_restart["pulse_eligible_actions"],
            ["WAIT", "HOLD"],
        )
        self.assertEqual(
            after_restart["pulse_suppressed_by_hold"],
            ["ACT", "DELEGATE"],
        )
        self.assertFalse(after_restart["projection_changed"])
        self.assertTrue(after_restart["identity_changed"])
        self.assertFalse(after_restart["selected_change"])
        self.assertEqual(after_restart["next_checkpoint_generation"], 1)
        self.assertNotEqual(
            writer["db_authority_receipt"],
            after_restart["checkpoint_sha256"],
            "DB authority identity must not be reused as Agency checkpoint identity",
        )

        process_c = self._probe("read_one")
        self.assertEqual(process_c.returncode, 0, msg=process_c.stderr)
        replay = json.loads(process_c.stdout)
        self.assertEqual(replay["checkpoint_id"], "checkpoint-1")
        self.assertEqual(
            replay["checkpoint_sha256"],
            after_restart["next_checkpoint_sha256"],
        )
        self.assertEqual(replay["checkpoint_generation"], 1)
        self.assertEqual(replay["goal_statuses"], ["ACTIVE"])

        db_files = sorted(self.root.rglob("*.db"))
        self.assertEqual(
            db_files,
            [self.db],
            "WP206 must not create a second SQLite truth database",
        )

    def test_fresh_process_authority_conflict_fails_before_replay(self) -> None:
        self._write_process_a()
        other_db = self.root / "other" / "other.db"
        self._create_sqlite(other_db)
        pointer = self.root / "pointer.txt"
        pointer.write_text(str(other_db), encoding="utf-8")

        reader = self._probe(
            "read",
            extra_env={"F2_POINTER_PATH": str(pointer)},
        )
        self.assertNotEqual(reader.returncode, 0)
        self.assertIn("UnifiedDBAuthorityConflict", reader.stderr)
        self.assertNotIn('"mode": "read"', reader.stdout)

    def test_same_path_replaced_file_identity_fails_closed(self) -> None:
        self._write_process_a()

        connection = sqlite3.connect(self.db)
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            connection.close()

        replacement = self.root / "replacement.sqlite"
        shutil.copy2(self.db, replacement)
        old_inode = self.db.stat().st_ino
        os.replace(replacement, self.db)
        self.assertNotEqual(old_inode, self.db.stat().st_ino)

        reader = self._probe("read")
        self.assertNotEqual(reader.returncode, 0)
        self.assertIn("CHECKPOINT_DB_FILE_IDENTITY_DRIFT", reader.stderr)

    def test_checkpoint_payload_or_change_policy_tamper_breaks_digest(self) -> None:
        self._write_process_a()
        connection = sqlite3.connect(self.db)
        try:
            row = connection.execute(
                """SELECT checkpoint_json
                   FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertIsNotNone(row)
            payload = json.loads(row[0])
            self.assertEqual(payload["change_policy"], "PROJECTION_CHANGED")
            payload["change_policy"] = "IDENTITY_CHANGED"
            connection.execute(
                """UPDATE f2_persistent_agency_checkpoints
                   SET checkpoint_json=?
                   WHERE checkpoint_id='checkpoint-0'""",
                (json.dumps(payload, sort_keys=True, separators=(",", ":")),),
            )
            connection.commit()
        finally:
            connection.close()

        reader = self._probe("read")
        self.assertNotEqual(reader.returncode, 0)
        self.assertIn("CHECKPOINT_DIGEST_MISMATCH", reader.stderr)

    def test_corrupt_parent_digest_blocks_successor_write(self) -> None:
        self._write_process_a()
        store = self._open_store_current_process()
        try:
            parent = store.load_checkpoint("checkpoint-0")
            child = advance_checkpoint(
                parent,
                checkpoint_id="checkpoint-1",
                pulse_id="pulse-1",
                observation_id="observation-none-1",
            )
        finally:
            store.close()

        connection = sqlite3.connect(self.db)
        try:
            row = connection.execute(
                """SELECT checkpoint_sha256, checkpoint_json
                   FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertIsNotNone(row)
            expected_sha, raw_json = row
            payload = json.loads(raw_json)
            self.assertEqual(
                payload["agency_state"]["interests"][0]["label"],
                "Preserve explicit restart state",
            )
            payload["agency_state"]["interests"][0]["label"] = (
                "Corrupted but schema-valid parent payload"
            )
            connection.execute(
                """UPDATE f2_persistent_agency_checkpoints
                   SET checkpoint_json=?
                   WHERE checkpoint_id='checkpoint-0'""",
                (
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ),
                ),
            )
            connection.commit()
            unchanged_sha = connection.execute(
                """SELECT checkpoint_sha256
                   FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()[0]
            self.assertEqual(unchanged_sha, expected_sha)
        finally:
            connection.close()

        store = self._open_store_current_process()
        try:
            with self.assertRaises(PersistentAgencyError):
                store.write_checkpoint(child)
        finally:
            store.close()

        connection = sqlite3.connect(self.db)
        try:
            child_count = connection.execute(
                """SELECT COUNT(*) FROM f2_persistent_agency_checkpoints
                   WHERE checkpoint_id='checkpoint-1'"""
            ).fetchone()[0]
            self.assertEqual(
                child_count,
                0,
                "a corrupt parent must never acquire a persisted descendant",
            )
        finally:
            connection.close()

    def test_wrong_parent_identity_is_rejected_transactionally(self) -> None:
        self._write_process_a()
        store = self._open_store_current_process()
        try:
            current = store.load_checkpoint("checkpoint-0")
            next_checkpoint = advance_checkpoint(
                current,
                checkpoint_id="checkpoint-1",
                pulse_id="pulse-1",
                observation_id="observation-none-1",
            )
            wrong_parent = replace(
                next_checkpoint,
                previous_checkpoint_id="checkpoint-does-not-exist",
            )
            with self.assertRaisesRegex(
                PersistentAgencyError, "CHECKPOINT_PARENT_NOT_FOUND"
            ):
                store.write_checkpoint(wrong_parent)
            with self.assertRaisesRegex(
                PersistentAgencyError, "CHECKPOINT_NOT_FOUND"
            ):
                store.load_checkpoint("checkpoint-1")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
