#!/usr/bin/env python3
"""Deterministic repository falsifiers for F2-WP-307 typed-memory persistence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from frankenstein2.memory_lifecycle import create_memory
from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore
from frankenstein2.typed_memory import KIND_FACT, create_typed_memory
from frankenstein2.typed_memory_persistence import (
    TYPED_MEMORY_TABLE,
    TypedMemoryPersistenceError,
    TypedMemoryUnifiedDBStore,
)
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


PAYLOAD_SHA = "1" * 64


class TypedMemoryPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.db = self.root / "canonical" / "unified.db"
        self.db.parent.mkdir()
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "CREATE TABLE f2_test_bootstrap(id INTEGER PRIMARY KEY)"
            )
            connection.commit()
        finally:
            connection.close()
        self.env = {"FRANKENSTEIN2_DB": str(self.db)}
        self._open_stores()

    def _open_stores(self) -> None:
        resolution = resolve_unifieddb_path(env=self.env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        self.agency_store = CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )
        self.store = TypedMemoryUnifiedDBStore(self.agency_store)

    def tearDown(self) -> None:
        self.agency_store.close()
        self._tmp.cleanup()

    def _record(self, *, evidence_ref: str = "evidence:obs-1"):
        state = create_memory(
            memory_id="memory-001",
            payload_ref="payloads/memory-001.json",
            payload_sha256=PAYLOAD_SHA,
            provenance_refs=("event:alpha", "source:wp307-test"),
        )
        return create_typed_memory(
            state=state,
            memory_kind=KIND_FACT,
            refs={"evidence": (evidence_ref,)},
        )

    def _load(self, record):
        return self.store.load_record(
            record.memory_id,
            record.lifecycle_generation,
            expected_record_sha256=record.sha256(),
        )

    def test_exact_record_bytes_persist_and_read_back_from_same_unifieddb(self) -> None:
        self.store.initialize_schema()
        record = self._record()
        written_sha = self.store.write_record(record)
        readback = self._load(record)
        self.assertEqual(written_sha, record.sha256())
        self.assertEqual(readback.record_sha256, record.sha256())
        self.assertEqual(readback.record_json, record.canonical_json())
        self.assertEqual(readback.canonical_db_path, str(self.db.resolve()))
        self.assertEqual(readback.db_device, self.db.stat().st_dev)
        self.assertEqual(readback.db_inode, self.db.stat().st_ino)
        self.assertEqual(
            readback.unifieddb_authority_receipt_sha256,
            self.agency_store.authority_receipt_sha256,
        )
        readback.verify_exact_record(record)
        self.assertEqual(sorted(self.root.rglob("*.db")), [self.db])

    def test_identical_replay_is_idempotent(self) -> None:
        self.store.initialize_schema()
        record = self._record()
        first = self.store.write_record(record)
        second = self.store.write_record(record)
        self.assertEqual(first, second)
        self.assertEqual(
            self.agency_store.connection.execute(
                f"SELECT COUNT(*) FROM main.{TYPED_MEMORY_TABLE}"
            ).fetchone()[0],
            1,
        )
        self._load(record).verify_exact_record(record)

    def test_idempotent_replay_revalidates_corrupted_existing_row(self) -> None:
        """TMU03: identical replay must not acknowledge invalid persisted metadata."""
        self.store.initialize_schema()
        record = self._record()
        self.store.write_record(record)
        self.agency_store.connection.execute(
            f"UPDATE main.{TYPED_MEMORY_TABLE} SET payload_ref=? WHERE memory_id=? AND lifecycle_generation=?",
            ("payloads/corrupted-on-disk.json", record.memory_id, record.lifecycle_generation),
        )
        self.agency_store.connection.commit()
        with self.assertRaisesRegex(TypedMemoryPersistenceError, "indexed metadata mismatch"):
            self.store.write_record(record)
        with self.assertRaisesRegex(TypedMemoryPersistenceError, "indexed metadata mismatch"):
            self._load(record)

    def test_idempotent_replay_revalidates_corrupt_existing_authority(self) -> None:
        """TMU03 authority variant."""
        self.store.initialize_schema()
        record = self._record()
        self.store.write_record(record)
        self.agency_store.connection.execute(
            f"UPDATE main.{TYPED_MEMORY_TABLE} SET unifieddb_authority_receipt_sha256=? WHERE memory_id=? AND lifecycle_generation=?",
            ("0" * 64, record.memory_id, record.lifecycle_generation),
        )
        self.agency_store.connection.commit()
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "TYPED_MEMORY_DB_AUTHORITY_RECEIPT_MISMATCH",
        ):
            self.store.write_record(record)

    def test_same_memory_generation_cannot_be_rebound_to_different_bytes(self) -> None:
        self.store.initialize_schema()
        first = self._record(evidence_ref="evidence:first")
        conflicting = self._record(evidence_ref="evidence:second")
        self.store.write_record(first)
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "MEMORY_GENERATION_ALREADY_BOUND_TO_DIFFERENT_BYTES",
        ):
            self.store.write_record(conflicting)
        self._load(first).verify_exact_record(first)

    def test_record_json_tamper_is_rejected_by_digest_readback(self) -> None:
        self.store.initialize_schema()
        record = self._record()
        self.store.write_record(record)
        self.agency_store.connection.execute(
            f"UPDATE main.{TYPED_MEMORY_TABLE} SET record_json=? WHERE memory_id=? AND lifecycle_generation=?",
            ('{"tampered":true}', record.memory_id, record.lifecycle_generation),
        )
        self.agency_store.connection.commit()
        with self.assertRaisesRegex(TypedMemoryPersistenceError, "TYPED_MEMORY_DIGEST_MISMATCH"):
            self._load(record)

    def test_coherent_row_rewrite_cannot_self_authenticate(self) -> None:
        """TMU02: coherent mutable-row rewrite cannot replace expected record identity."""
        self.store.initialize_schema()
        record = self._record(evidence_ref="evidence:original")
        self.store.write_record(record)
        rewritten = record.as_dict()
        rewritten["typed_refs"] = [
            {
                "schema": "FRANKENSTEIN2_TYPED_MEMORY_REFSET/v1",
                "tag": "evidence",
                "refs": ["evidence:coherent-rewrite"],
            }
        ]
        rewritten_json = json.dumps(
            rewritten,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        rewritten_sha = hashlib.sha256(rewritten_json.encode("utf-8")).hexdigest()
        self.agency_store.connection.execute(
            f"""UPDATE main.{TYPED_MEMORY_TABLE}
                SET record_json=?, record_sha256=?
                WHERE memory_id=? AND lifecycle_generation=?""",
            (rewritten_json, rewritten_sha, record.memory_id, record.lifecycle_generation),
        )
        self.agency_store.connection.commit()
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "TYPED_MEMORY_EXPECTED_DIGEST_MISMATCH",
        ):
            self._load(record)
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "MEMORY_GENERATION_ALREADY_BOUND_TO_DIFFERENT_BYTES",
        ):
            self.store.write_record(record)

    def test_indexed_metadata_tamper_is_rejected_before_semantic_use(self) -> None:
        self.store.initialize_schema()
        record = self._record()
        self.store.write_record(record)
        self.agency_store.connection.execute(
            f"UPDATE main.{TYPED_MEMORY_TABLE} SET payload_ref=? WHERE memory_id=? AND lifecycle_generation=?",
            ("payloads/other.json", record.memory_id, record.lifecycle_generation),
        )
        self.agency_store.connection.commit()
        with self.assertRaisesRegex(TypedMemoryPersistenceError, "indexed metadata mismatch"):
            self._load(record)

    def test_authority_receipt_tamper_is_rejected(self) -> None:
        self.store.initialize_schema()
        record = self._record()
        self.store.write_record(record)
        self.agency_store.connection.execute(
            f"UPDATE main.{TYPED_MEMORY_TABLE} SET unifieddb_authority_receipt_sha256=? WHERE memory_id=? AND lifecycle_generation=?",
            ("0" * 64, record.memory_id, record.lifecycle_generation),
        )
        self.agency_store.connection.commit()
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "TYPED_MEMORY_DB_AUTHORITY_RECEIPT_MISMATCH",
        ):
            self._load(record)

    def test_failed_conflict_rolls_back_without_partial_authority(self) -> None:
        """TMDB06: failed admission leaves the original exact one-row authority intact."""
        self.store.initialize_schema()
        original = self._record(evidence_ref="evidence:original")
        conflicting = self._record(evidence_ref="evidence:conflict")
        self.store.write_record(original)
        before = self.agency_store.connection.execute(
            f"SELECT record_sha256, record_json FROM main.{TYPED_MEMORY_TABLE}"
        ).fetchall()
        with self.assertRaises(TypedMemoryPersistenceError):
            self.store.write_record(conflicting)
        after = self.agency_store.connection.execute(
            f"SELECT record_sha256, record_json FROM main.{TYPED_MEMORY_TABLE}"
        ).fetchall()
        self.assertEqual(after, before)
        self.assertFalse(self.agency_store.connection.in_transaction)
        self._load(original).verify_exact_record(original)

    def test_attached_second_persistent_database_fails_closed(self) -> None:
        rogue = self.root / "rogue.db"
        sqlite3.connect(rogue).close()
        self.agency_store.connection.execute("ATTACH DATABASE ? AS rogue", (str(rogue),))
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "SQLITE_SECOND_PERSISTENT_DATABASE_ATTACHED",
        ):
            TypedMemoryUnifiedDBStore(self.agency_store)

    def test_replaced_unifieddb_inode_fails_closed_before_readback(self) -> None:
        self.store.initialize_schema()
        record = self._record()
        self.store.write_record(record)
        replacement = self.root / "replacement.db"
        sqlite3.connect(replacement).close()
        old_inode = self.db.stat().st_ino
        self.db.replace(self.root / "old.db")
        replacement.replace(self.db)
        self.assertNotEqual(old_inode, self.db.stat().st_ino)
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "UNIFIEDDB_FILE_IDENTITY_DRIFT|UNIFIEDDB_AGENCY_AUTHORITY_REVALIDATION_FAILED",
        ):
            self._load(record)

    def test_temp_shadow_cannot_capture_or_satisfy_canonical_main_persistence(self) -> None:
        """TMU01: same-name TEMP state must never satisfy canonical UnifiedDB credit."""
        self.store.initialize_schema()
        connection = self.agency_store.connection
        connection.execute(
            f"""CREATE TEMP TABLE {TYPED_MEMORY_TABLE}(
                memory_id TEXT,
                lifecycle_generation INTEGER,
                memory_kind TEXT,
                lifecycle_state_sha256 TEXT,
                payload_ref TEXT,
                payload_sha256 TEXT,
                record_sha256 TEXT,
                record_json TEXT,
                canonical_db_path TEXT,
                db_device INTEGER,
                db_inode INTEGER,
                unifieddb_authority_receipt_sha256 TEXT
            )"""
        )
        record = self._record()
        self.store.write_record(record)
        self.assertEqual(
            connection.execute(f"SELECT COUNT(*) FROM temp.{TYPED_MEMORY_TABLE}").fetchone()[0],
            0,
        )
        self.assertEqual(
            connection.execute(f"SELECT COUNT(*) FROM main.{TYPED_MEMORY_TABLE}").fetchone()[0],
            1,
        )
        self._load(record).verify_exact_record(record)

    def test_fresh_connection_reopen_reads_identical_main_bytes(self) -> None:
        self.store.initialize_schema()
        record = self._record()
        expected_sha = self.store.write_record(record)
        original_authority = self.agency_store.authority_receipt_sha256
        self.agency_store.close()
        self._open_stores()
        readback = self.store.load_record(
            record.memory_id,
            record.lifecycle_generation,
            expected_record_sha256=expected_sha,
        )
        self.assertEqual(self.agency_store.authority_receipt_sha256, original_authority)
        readback.verify_exact_record(record)
        self.assertEqual(
            self.agency_store.connection.execute(
                f"SELECT COUNT(*) FROM main.{TYPED_MEMORY_TABLE}"
            ).fetchone()[0],
            1,
        )

    def test_readback_requires_explicit_expected_digest(self) -> None:
        self.store.initialize_schema()
        record = self._record()
        self.store.write_record(record)
        with self.assertRaises(TypeError):
            self.store.load_record(record.memory_id, record.lifecycle_generation)
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "expected_record_sha256 must be lowercase 64-hex SHA-256",
        ):
            self.store.load_record(
                record.memory_id,
                record.lifecycle_generation,
                expected_record_sha256="not-a-digest",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
