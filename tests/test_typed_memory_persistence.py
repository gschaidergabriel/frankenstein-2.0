#!/usr/bin/env python3
"""Deterministic repository falsifiers for F2-WP-307 typed-memory persistence."""
from __future__ import annotations

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
        resolution = resolve_unifieddb_path(env=self.env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        self.agency_store = CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )
        self.store = TypedMemoryUnifiedDBStore(self.agency_store)
        self.store.initialize_schema()

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

    def test_exact_record_bytes_persist_and_read_back_from_same_unifieddb(self) -> None:
        record = self._record()
        written_sha = self.store.write_record(record)
        readback = self.store.load_record(record.memory_id, record.lifecycle_generation)

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

        db_files = sorted(self.root.rglob("*.db"))
        self.assertEqual(
            db_files,
            [self.db],
            "WP307 must reuse the canonical UnifiedDB and create no second DB",
        )

    def test_identical_replay_is_idempotent(self) -> None:
        record = self._record()
        first = self.store.write_record(record)
        second = self.store.write_record(record)
        self.assertEqual(first, second)
        count = self.agency_store.connection.execute(
            f"SELECT COUNT(*) FROM {TYPED_MEMORY_TABLE}"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_same_memory_generation_cannot_be_rebound_to_different_bytes(self) -> None:
        first = self._record(evidence_ref="evidence:first")
        conflicting = self._record(evidence_ref="evidence:second")
        self.store.write_record(first)
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "MEMORY_GENERATION_ALREADY_BOUND_TO_DIFFERENT_BYTES",
        ):
            self.store.write_record(conflicting)
        self.store.load_record(first.memory_id, first.lifecycle_generation).verify_exact_record(
            first
        )

    def test_record_json_tamper_is_rejected_by_digest_readback(self) -> None:
        record = self._record()
        self.store.write_record(record)
        connection = self.agency_store.connection
        connection.execute(
            f"UPDATE {TYPED_MEMORY_TABLE} SET record_json=? WHERE memory_id=? AND lifecycle_generation=?",
            ('{"tampered":true}', record.memory_id, record.lifecycle_generation),
        )
        connection.commit()
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "TYPED_MEMORY_DIGEST_MISMATCH|TYPED_MEMORY_ID_METADATA_MISMATCH",
        ):
            self.store.load_record(record.memory_id, record.lifecycle_generation)

    def test_indexed_metadata_tamper_is_rejected_before_semantic_use(self) -> None:
        record = self._record()
        self.store.write_record(record)
        connection = self.agency_store.connection
        connection.execute(
            f"UPDATE {TYPED_MEMORY_TABLE} SET payload_ref=? WHERE memory_id=? AND lifecycle_generation=?",
            ("payloads/other.json", record.memory_id, record.lifecycle_generation),
        )
        connection.commit()
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "indexed metadata mismatch",
        ):
            self.store.load_record(record.memory_id, record.lifecycle_generation)

    def test_authority_receipt_tamper_is_rejected(self) -> None:
        record = self._record()
        self.store.write_record(record)
        connection = self.agency_store.connection
        connection.execute(
            f"UPDATE {TYPED_MEMORY_TABLE} SET unifieddb_authority_receipt_sha256=? WHERE memory_id=? AND lifecycle_generation=?",
            ("0" * 64, record.memory_id, record.lifecycle_generation),
        )
        connection.commit()
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "TYPED_MEMORY_DB_AUTHORITY_RECEIPT_MISMATCH",
        ):
            self.store.load_record(record.memory_id, record.lifecycle_generation)

    def test_attached_second_persistent_database_fails_closed(self) -> None:
        rogue = self.root / "rogue.db"
        sqlite3.connect(rogue).close()
        self.agency_store.connection.execute(
            "ATTACH DATABASE ? AS rogue",
            (str(rogue),),
        )
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "SQLITE_SECOND_PERSISTENT_DATABASE_ATTACHED",
        ):
            TypedMemoryUnifiedDBStore(self.agency_store)

    def test_replaced_unifieddb_inode_fails_closed_before_readback(self) -> None:
        record = self._record()
        self.store.write_record(record)
        replacement = self.root / "replacement.db"
        replacement_connection = sqlite3.connect(replacement)
        replacement_connection.close()
        old_inode = self.db.stat().st_ino
        self.db.replace(self.root / "old.db")
        replacement.replace(self.db)
        self.assertNotEqual(old_inode, self.db.stat().st_ino)
        with self.assertRaisesRegex(
            TypedMemoryPersistenceError,
            "UNIFIEDDB_FILE_IDENTITY_DRIFT",
        ):
            self.store.load_record(record.memory_id, record.lifecycle_generation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
