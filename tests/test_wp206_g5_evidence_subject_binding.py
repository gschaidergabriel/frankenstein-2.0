#!/usr/bin/env python3
"""Executable G5 content-binding and G4->G5 migration regressions for F2-WP-206."""
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
    EVIDENCE_SUBJECT_BOUND_G5,
    LEGACY_EVIDENCE_SUBJECT_UNBOUND,
    RECOVERED,
    RECOVERY_TABLE,
    LegacyRecoveryEvidenceSubject,
    recover_legacy_g1_checkpoint_authority,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "tests" / "wp206_restart_probe.py"
SRC = REPO_ROOT / "src"
PROVENANCE = "evidence:g5-review-provenance"
CLASSIFICATION = (
    "EXPLICIT_ONE_TIME_PERSISTENCE_MIGRATION_NOT_WORLD_TRUTH_OR_RUNTIME_ACCEPTANCE"
)


class WP206G5EvidenceSubjectBinding(unittest.TestCase):
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

    def _open_store(self) -> CanonicalPersistentAgencyStore:
        resolution = resolve_unifieddb_path(env=self.env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        return CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )

    def _subject(
        self,
        *,
        historical: str,
        checkpoint_sha: str,
        evidence_version: int = 1,
        source_ref: str = PROVENANCE,
    ) -> LegacyRecoveryEvidenceSubject:
        return LegacyRecoveryEvidenceSubject(
            source_ref=source_ref,
            checkpoint_id="checkpoint-0",
            checkpoint_sha256=checkpoint_sha,
            legacy_authority_receipt_sha256=historical,
            evidence={
                "kind": "g5-concrete-recovery-evidence",
                "version": evidence_version,
                "source_ref": source_ref,
                "assertion": "accepted legacy authority witness",
            },
        )

    def _recover(
        self,
        *,
        store: CanonicalPersistentAgencyStore,
        historical: str,
        subject: LegacyRecoveryEvidenceSubject,
        provenance: str = PROVENANCE,
    ):
        return recover_legacy_g1_checkpoint_authority(
            store=store,
            checkpoint_id="checkpoint-0",
            expected_legacy_authority_receipt_sha256=historical,
            recovery_provenance_ref=provenance,
            recovery_evidence_subject=subject,
        )

    def test_exact_subject_repeat_is_idempotent_and_content_bound(self) -> None:
        historical, checkpoint_sha = self._write_legacy_style_row()
        store = self._open_store()
        try:
            subject = self._subject(
                historical=historical, checkpoint_sha=checkpoint_sha
            )
            first = self._recover(
                store=store, historical=historical, subject=subject
            )
            second = self._recover(
                store=store, historical=historical, subject=subject
            )
            self.assertEqual(first.status, RECOVERED)
            self.assertEqual(second.status, ALREADY_RECOVERED)
            self.assertEqual(first.recovery_id, second.recovery_id)
            self.assertEqual(
                first.recovery_evidence_subject_state,
                EVIDENCE_SUBJECT_BOUND_G5,
            )
            self.assertRegex(str(first.recovery_evidence_sha256), r"^[0-9a-f]{64}$")
            row = store.connection.execute(
                f"""SELECT recovery_evidence_source_ref,
                           recovery_evidence_sha256,
                           recovery_evidence_subject_state
                    FROM {RECOVERY_TABLE}
                    WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertEqual(
                row,
                (
                    PROVENANCE,
                    first.recovery_evidence_sha256,
                    EVIDENCE_SUBJECT_BOUND_G5,
                ),
            )
        finally:
            store.close()

    def test_same_ref_mutated_evidence_bytes_fail_closed_without_row_mutation(self) -> None:
        historical, checkpoint_sha = self._write_legacy_style_row()
        store = self._open_store()
        try:
            first_subject = self._subject(
                historical=historical,
                checkpoint_sha=checkpoint_sha,
                evidence_version=1,
            )
            first = self._recover(
                store=store, historical=historical, subject=first_subject
            )
            before = store.connection.execute(
                f"""SELECT recovery_id, recovery_evidence_sha256,
                           recovery_evidence_subject_state
                    FROM {RECOVERY_TABLE}
                    WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            mutated_subject = self._subject(
                historical=historical,
                checkpoint_sha=checkpoint_sha,
                evidence_version=2,
            )
            with self.assertRaisesRegex(
                PersistentAgencyError,
                "LEGACY_RECOVERY_EVIDENCE_SUBJECT_CONFLICT",
            ):
                self._recover(
                    store=store,
                    historical=historical,
                    subject=mutated_subject,
                )
            after = store.connection.execute(
                f"""SELECT recovery_id, recovery_evidence_sha256,
                           recovery_evidence_subject_state
                    FROM {RECOVERY_TABLE}
                    WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertEqual(after, before)
            self.assertEqual(before[0], first.recovery_id)
            self.assertEqual(self._stored_receipt(), first.rebound_authority_receipt_sha256)
        finally:
            store.close()

    def test_missing_or_mismatched_typed_subject_is_rejected_before_rebind(self) -> None:
        historical, checkpoint_sha = self._write_legacy_style_row()
        store = self._open_store()
        try:
            with self.assertRaisesRegex(
                PersistentAgencyError, "RECOVERY_EVIDENCE_SUBJECT_REQUIRED"
            ):
                recover_legacy_g1_checkpoint_authority(
                    store=store,
                    checkpoint_id="checkpoint-0",
                    expected_legacy_authority_receipt_sha256=historical,
                    recovery_provenance_ref=PROVENANCE,
                )
            wrong = self._subject(
                historical=historical,
                checkpoint_sha="0" * 64,
            )
            with self.assertRaisesRegex(
                PersistentAgencyError,
                "RECOVERY_EVIDENCE_CHECKPOINT_DIGEST_MISMATCH",
            ):
                self._recover(
                    store=store,
                    historical=historical,
                    subject=wrong,
                )
            self.assertEqual(self._stored_receipt(), historical)
        finally:
            store.close()

    def _seed_g4_recovery_row(
        self,
        *,
        store: CanonicalPersistentAgencyStore,
        historical: str,
        checkpoint_sha: str,
    ) -> str:
        legacy_recovery_id = "4" * 64
        connection = store.connection
        connection.execute(
            f"""CREATE TABLE {RECOVERY_TABLE}(
                recovery_id TEXT PRIMARY KEY,
                checkpoint_id TEXT NOT NULL UNIQUE,
                checkpoint_sha256 TEXT NOT NULL,
                canonical_db_path TEXT NOT NULL,
                db_device INTEGER NOT NULL,
                db_inode INTEGER NOT NULL,
                legacy_authority_receipt_sha256 TEXT NOT NULL,
                rebound_authority_receipt_sha256 TEXT NOT NULL,
                recovery_provenance_ref TEXT NOT NULL,
                classification TEXT NOT NULL
            )"""
        )
        connection.execute(
            f"""INSERT INTO {RECOVERY_TABLE}(
                recovery_id, checkpoint_id, checkpoint_sha256,
                canonical_db_path, db_device, db_inode,
                legacy_authority_receipt_sha256,
                rebound_authority_receipt_sha256,
                recovery_provenance_ref, classification
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                legacy_recovery_id,
                "checkpoint-0",
                checkpoint_sha,
                store.canonical_db_path,
                store.db_device,
                store.db_inode,
                historical,
                store.authority_receipt_sha256,
                PROVENANCE,
                CLASSIFICATION,
            ),
        )
        connection.execute(
            """UPDATE f2_persistent_agency_checkpoints
               SET unifieddb_authority_receipt_sha256=?
               WHERE checkpoint_id='checkpoint-0'""",
            (store.authority_receipt_sha256,),
        )
        connection.commit()
        return legacy_recovery_id

    def test_g4_row_survives_g5_schema_evolution_without_retroactive_binding(self) -> None:
        historical, checkpoint_sha = self._write_legacy_style_row()
        store = self._open_store()
        try:
            legacy_id = self._seed_g4_recovery_row(
                store=store,
                historical=historical,
                checkpoint_sha=checkpoint_sha,
            )
            current = self._stored_receipt()
            subject = self._subject(
                historical=historical,
                checkpoint_sha=checkpoint_sha,
            )
            receipt = self._recover(
                store=store,
                historical=historical,
                subject=subject,
            )
            self.assertEqual(receipt.status, LEGACY_EVIDENCE_SUBJECT_UNBOUND)
            self.assertEqual(receipt.recovery_id, legacy_id)
            self.assertEqual(
                receipt.recovery_evidence_subject_state,
                LEGACY_EVIDENCE_SUBJECT_UNBOUND,
            )
            self.assertIsNone(receipt.recovery_evidence_sha256)
            self.assertEqual(self._stored_receipt(), current)

            columns = {
                str(row[1])
                for row in store.connection.execute(
                    f"PRAGMA table_info({RECOVERY_TABLE})"
                ).fetchall()
            }
            self.assertTrue(
                {
                    "recovery_evidence_subject_schema",
                    "recovery_evidence_source_ref",
                    "recovery_evidence_sha256",
                    "recovery_evidence_subject_state",
                }.issubset(columns)
            )
            row = store.connection.execute(
                f"""SELECT recovery_id,
                           recovery_evidence_subject_schema,
                           recovery_evidence_source_ref,
                           recovery_evidence_sha256,
                           recovery_evidence_subject_state
                    FROM {RECOVERY_TABLE}
                    WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertEqual(
                row,
                (
                    legacy_id,
                    None,
                    None,
                    None,
                    LEGACY_EVIDENCE_SUBJECT_UNBOUND,
                ),
            )

            changed_subject = self._subject(
                historical=historical,
                checkpoint_sha=checkpoint_sha,
                evidence_version=99,
            )
            again = self._recover(
                store=store,
                historical=historical,
                subject=changed_subject,
            )
            self.assertEqual(again.status, LEGACY_EVIDENCE_SUBJECT_UNBOUND)
            self.assertEqual(again.recovery_id, legacy_id)
            row_again = store.connection.execute(
                f"""SELECT recovery_id, recovery_evidence_sha256,
                           recovery_evidence_subject_state
                    FROM {RECOVERY_TABLE}
                    WHERE checkpoint_id='checkpoint-0'"""
            ).fetchone()
            self.assertEqual(
                row_again,
                (legacy_id, None, LEGACY_EVIDENCE_SUBJECT_UNBOUND),
            )
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
