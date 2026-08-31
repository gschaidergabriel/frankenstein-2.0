"""Same-UnifiedDB persistence adapter for deterministic TypedMemoryRecord bytes.

F2-WP-307 generation 1.

This module closes only the persistence boundary between the accepted F2-WP-303
``TypedMemoryRecord`` contract and the already-authoritative F2-WP-206
``CanonicalPersistentAgencyStore`` connection. It never creates or opens a second
SQLite database, never infers world truth or memory semantics, never performs retrieval,
never invokes a model/provider/tool, and never authorizes effects or completion.

All WP307 SQL is schema-qualified to ``main``. Exact ``record_sha256`` is the durable row
identity; ``(memory_id, lifecycle_generation)`` is deliberately non-unique because WP303
admits multiple valid typed records for one lifecycle state. Authenticated readback requires
an independently retained expected record SHA-256, and exact replay revalidates the full row
and current database authority before returning success.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from frankenstein2.persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    PersistentAgencyError,
)
from frankenstein2.typed_memory import TypedMemoryRecord

PERSISTENCE_SCHEMA = "FRANKENSTEIN2_TYPED_MEMORY_UNIFIEDDB_PERSISTENCE/v1"
READBACK_SCHEMA = "FRANKENSTEIN2_TYPED_MEMORY_UNIFIEDDB_READBACK/v1"
TYPED_MEMORY_TABLE = "f2_typed_memory_records"
_MAX_ID_LEN = 512


class TypedMemoryPersistenceError(RuntimeError):
    """Fail-closed typed-memory persistence contract error."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_bytes(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise TypedMemoryPersistenceError(f"{name} must be a string")
    if not value or value != value.strip():
        raise TypedMemoryPersistenceError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise TypedMemoryPersistenceError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TypedMemoryPersistenceError(f"{name} contains control characters")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise TypedMemoryPersistenceError(
            "lifecycle_generation must be a non-negative integer"
        )
    return value


def _sha256_identity(name: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise TypedMemoryPersistenceError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _same_real_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
        os.path.realpath(right)
    )


@dataclass(frozen=True, slots=True)
class TypedMemoryReadback:
    """Authenticated exact persisted bytes; never world-truth or effect authority."""

    schema: str
    memory_id: str
    lifecycle_generation: int
    record_sha256: str
    record_json: str
    canonical_db_path: str
    db_device: int
    db_inode: int
    unifieddb_authority_receipt_sha256: str
    classification: str = (
        "EXACT_TYPED_MEMORY_BYTES_READBACK_NOT_WORLD_TRUTH_RETRIEVAL_EFFECT_OR_COMPLETION_AUTHORITY"
    )

    def __post_init__(self) -> None:
        if self.schema != READBACK_SCHEMA:
            raise TypedMemoryPersistenceError("typed-memory readback schema mismatch")
        object.__setattr__(self, "memory_id", _identifier("memory_id", self.memory_id))
        object.__setattr__(
            self, "lifecycle_generation", _generation(self.lifecycle_generation)
        )
        object.__setattr__(
            self,
            "record_sha256",
            _sha256_identity("record_sha256", self.record_sha256),
        )
        if not isinstance(self.record_json, str) or not self.record_json:
            raise TypedMemoryPersistenceError(
                "record_json must be non-empty canonical JSON"
            )
        try:
            decoded = json.loads(self.record_json)
        except json.JSONDecodeError as exc:
            raise TypedMemoryPersistenceError("CORRUPT_TYPED_MEMORY_JSON") from exc
        if not isinstance(decoded, dict):
            raise TypedMemoryPersistenceError(
                "typed-memory JSON must decode to an object"
            )
        if _canonical_json(decoded) != self.record_json:
            raise TypedMemoryPersistenceError("TYPED_MEMORY_JSON_NOT_CANONICAL")
        if _sha256_bytes(self.record_json) != self.record_sha256:
            raise TypedMemoryPersistenceError("TYPED_MEMORY_DIGEST_MISMATCH")
        if decoded.get("memory_id") != self.memory_id:
            raise TypedMemoryPersistenceError("TYPED_MEMORY_ID_METADATA_MISMATCH")
        if decoded.get("lifecycle_generation") != self.lifecycle_generation:
            raise TypedMemoryPersistenceError(
                "TYPED_MEMORY_GENERATION_METADATA_MISMATCH"
            )
        _identifier("canonical_db_path", self.canonical_db_path)
        if type(self.db_device) is not int or type(self.db_inode) is not int:
            raise TypedMemoryPersistenceError(
                "database device/inode identity must be integers"
            )
        if self.db_device < 0 or self.db_inode < 0:
            raise TypedMemoryPersistenceError(
                "database device/inode identity must be non-negative"
            )
        object.__setattr__(
            self,
            "unifieddb_authority_receipt_sha256",
            _sha256_identity(
                "unifieddb_authority_receipt_sha256",
                self.unifieddb_authority_receipt_sha256,
            ),
        )
        if (
            self.classification
            != "EXACT_TYPED_MEMORY_BYTES_READBACK_NOT_WORLD_TRUTH_RETRIEVAL_EFFECT_OR_COMPLETION_AUTHORITY"
        ):
            raise TypedMemoryPersistenceError(
                "typed-memory readback classification mismatch"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "memory_id": self.memory_id,
            "lifecycle_generation": self.lifecycle_generation,
            "record_sha256": self.record_sha256,
            "record_json": self.record_json,
            "canonical_db_path": self.canonical_db_path,
            "db_device": self.db_device,
            "db_inode": self.db_inode,
            "unifieddb_authority_receipt_sha256": self.unifieddb_authority_receipt_sha256,
            "classification": self.classification,
        }

    def record_dict(self) -> dict[str, Any]:
        value = json.loads(self.record_json)
        if not isinstance(value, dict):
            raise TypedMemoryPersistenceError(
                "typed-memory JSON must decode to an object"
            )
        return value

    def verify_exact_record(self, record: TypedMemoryRecord) -> None:
        if not isinstance(record, TypedMemoryRecord):
            raise TypedMemoryPersistenceError("record must be a TypedMemoryRecord")
        mismatches: list[str] = []
        if self.memory_id != record.memory_id:
            mismatches.append("memory_id")
        if self.lifecycle_generation != record.lifecycle_generation:
            mismatches.append("lifecycle_generation")
        if self.record_sha256 != record.sha256():
            mismatches.append("record_sha256")
        if self.record_json != record.canonical_json():
            mismatches.append("record_json")
        if mismatches:
            raise TypedMemoryPersistenceError(
                f"typed-memory exact readback mismatch: {mismatches!r}"
            )


class TypedMemoryUnifiedDBStore:
    """WP307 table on the exact WP206-bound canonical UnifiedDB connection."""

    def __init__(self, agency_store: CanonicalPersistentAgencyStore) -> None:
        if not isinstance(agency_store, CanonicalPersistentAgencyStore):
            raise TypedMemoryPersistenceError(
                "agency_store must be CanonicalPersistentAgencyStore"
            )
        self.agency_store = agency_store
        self.connection = agency_store.connection
        self.canonical_db_path = os.path.realpath(agency_store.canonical_db_path)
        self.db_device = int(agency_store.db_device)
        self.db_inode = int(agency_store.db_inode)
        self.unifieddb_authority_receipt_sha256 = agency_store.authority_receipt_sha256
        self._assert_current_unifieddb_identity()

    def _assert_no_second_persistent_database(self) -> None:
        try:
            rows = self.connection.execute("PRAGMA database_list").fetchall()
        except sqlite3.Error as exc:
            raise TypedMemoryPersistenceError(
                "SQLITE_DATABASE_LIST_UNAVAILABLE"
            ) from exc
        main_rows = [row for row in rows if len(row) >= 3 and row[1] == "main"]
        if len(main_rows) != 1 or not main_rows[0][2]:
            raise TypedMemoryPersistenceError(
                "SQLITE_MAIN_DATABASE_PATH_UNAVAILABLE"
            )
        if not _same_real_path(main_rows[0][2], self.canonical_db_path):
            raise TypedMemoryPersistenceError(
                "SQLITE_CONNECTION_NOT_BOUND_TO_CANONICAL_UNIFIEDDB"
            )
        attached_persistent = [
            row
            for row in rows
            if len(row) >= 3 and row[1] != "main" and bool(row[2])
        ]
        if attached_persistent:
            raise TypedMemoryPersistenceError(
                "SQLITE_SECOND_PERSISTENT_DATABASE_ATTACHED"
            )

    def _assert_current_unifieddb_identity(self) -> None:
        try:
            self.agency_store._assert_current_file_identity()
        except PersistentAgencyError as exc:
            raise TypedMemoryPersistenceError(
                "UNIFIEDDB_AGENCY_AUTHORITY_REVALIDATION_FAILED"
            ) from exc
        try:
            stat = Path(self.canonical_db_path).stat()
        except OSError as exc:
            raise TypedMemoryPersistenceError(
                "UNIFIEDDB_FILE_MISSING_DURING_TYPED_MEMORY_USE"
            ) from exc
        if (stat.st_dev, stat.st_ino) != (self.db_device, self.db_inode):
            raise TypedMemoryPersistenceError("UNIFIEDDB_FILE_IDENTITY_DRIFT")
        self._assert_no_second_persistent_database()

    def _assert_no_caller_transaction(self) -> None:
        if self.connection.in_transaction:
            raise TypedMemoryPersistenceError("CALLER_TRANSACTION_ALREADY_OPEN")

    def _fetch_row(self, expected_record_sha256: str):
        return self.connection.execute(
            f"""SELECT memory_id, lifecycle_generation, memory_kind,
                       lifecycle_state_sha256, payload_ref, payload_sha256,
                       record_sha256, record_json, canonical_db_path,
                       db_device, db_inode, unifieddb_authority_receipt_sha256
                FROM main.{TYPED_MEMORY_TABLE}
                WHERE record_sha256=?""",
            (expected_record_sha256,),
        ).fetchone()

    def _validated_readback(
        self,
        *,
        memory_id: str,
        lifecycle_generation: int,
        expected_record_sha256: str,
        row,
    ) -> TypedMemoryReadback:
        if row is None:
            raise TypedMemoryPersistenceError("TYPED_MEMORY_RECORD_NOT_FOUND")
        (
            stored_memory_id,
            stored_generation,
            stored_kind,
            stored_lifecycle_sha,
            stored_payload_ref,
            stored_payload_sha,
            record_sha256,
            record_json,
            stored_path,
            stored_device,
            stored_inode,
            stored_authority_sha,
        ) = row
        if stored_memory_id != memory_id:
            raise TypedMemoryPersistenceError("TYPED_MEMORY_ROW_MEMORY_ID_MISMATCH")
        if stored_generation != lifecycle_generation:
            raise TypedMemoryPersistenceError("TYPED_MEMORY_ROW_GENERATION_MISMATCH")
        if not isinstance(stored_path, str) or not _same_real_path(
            stored_path, self.canonical_db_path
        ):
            raise TypedMemoryPersistenceError(
                "TYPED_MEMORY_DB_PATH_AUTHORITY_MISMATCH"
            )
        if (stored_device, stored_inode) != (self.db_device, self.db_inode):
            raise TypedMemoryPersistenceError(
                "TYPED_MEMORY_DB_FILE_IDENTITY_DRIFT"
            )
        if stored_authority_sha != self.unifieddb_authority_receipt_sha256:
            raise TypedMemoryPersistenceError(
                "TYPED_MEMORY_DB_AUTHORITY_RECEIPT_MISMATCH"
            )
        if record_sha256 != expected_record_sha256:
            raise TypedMemoryPersistenceError(
                "TYPED_MEMORY_EXPECTED_DIGEST_MISMATCH"
            )
        readback = TypedMemoryReadback(
            schema=READBACK_SCHEMA,
            memory_id=memory_id,
            lifecycle_generation=lifecycle_generation,
            record_sha256=record_sha256,
            record_json=record_json,
            canonical_db_path=self.canonical_db_path,
            db_device=self.db_device,
            db_inode=self.db_inode,
            unifieddb_authority_receipt_sha256=self.unifieddb_authority_receipt_sha256,
        )
        decoded = readback.record_dict()
        metadata_checks = {
            "memory_kind": (stored_kind, decoded.get("memory_kind")),
            "lifecycle_state_sha256": (
                stored_lifecycle_sha,
                decoded.get("lifecycle_state_sha256"),
            ),
            "payload_ref": (stored_payload_ref, decoded.get("payload_ref")),
            "payload_sha256": (stored_payload_sha, decoded.get("payload_sha256")),
        }
        mismatches = [
            name
            for name, (stored, encoded) in metadata_checks.items()
            if stored != encoded
        ]
        if mismatches:
            raise TypedMemoryPersistenceError(
                f"typed-memory indexed metadata mismatch: {mismatches!r}"
            )
        return readback

    def initialize_schema(self) -> None:
        """Create WP307 table with exact record digest as sole durable row identity."""
        self._assert_no_caller_transaction()
        self._assert_current_unifieddb_identity()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self._assert_current_unifieddb_identity()
            self.connection.execute(
                f"""CREATE TABLE IF NOT EXISTS main.{TYPED_MEMORY_TABLE}(
                    record_sha256 TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    lifecycle_generation INTEGER NOT NULL CHECK(lifecycle_generation >= 0),
                    memory_kind TEXT NOT NULL,
                    lifecycle_state_sha256 TEXT NOT NULL,
                    payload_ref TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    canonical_db_path TEXT NOT NULL,
                    db_device INTEGER NOT NULL,
                    db_inode INTEGER NOT NULL,
                    unifieddb_authority_receipt_sha256 TEXT NOT NULL
                )"""
            )
            columns = self.connection.execute(
                f"PRAGMA main.table_info({TYPED_MEMORY_TABLE})"
            ).fetchall()
            pk_columns = [row[1] for row in columns if row[5] > 0]
            if pk_columns != ["record_sha256"]:
                raise TypedMemoryPersistenceError(
                    "TYPED_MEMORY_SCHEMA_INCOMPATIBLE_PRIMARY_KEY"
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def write_record(self, record: TypedMemoryRecord) -> str:
        """Persist one exact WP303 record; multiple records may share lifecycle identity."""
        if not isinstance(record, TypedMemoryRecord):
            raise TypedMemoryPersistenceError("record must be a TypedMemoryRecord")
        self._assert_no_caller_transaction()
        self._assert_current_unifieddb_identity()
        record_json = record.canonical_json()
        record_sha256 = record.sha256()
        if _sha256_bytes(record_json) != record_sha256:
            raise TypedMemoryPersistenceError(
                "TYPED_MEMORY_SOURCE_DIGEST_MISMATCH"
            )
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self._assert_current_unifieddb_identity()
            existing = self._fetch_row(record_sha256)
            if existing is not None:
                readback = self._validated_readback(
                    memory_id=record.memory_id,
                    lifecycle_generation=record.lifecycle_generation,
                    expected_record_sha256=record_sha256,
                    row=existing,
                )
                readback.verify_exact_record(record)
                self.connection.commit()
                return record_sha256

            self.connection.execute(
                f"""INSERT INTO main.{TYPED_MEMORY_TABLE}(
                    record_sha256, memory_id, lifecycle_generation, memory_kind,
                    lifecycle_state_sha256, payload_ref, payload_sha256,
                    record_json, canonical_db_path, db_device, db_inode,
                    unifieddb_authority_receipt_sha256
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record_sha256,
                    record.memory_id,
                    record.lifecycle_generation,
                    record.memory_kind,
                    record.lifecycle_state_sha256,
                    record.payload_ref,
                    record.payload_sha256,
                    record_json,
                    self.canonical_db_path,
                    self.db_device,
                    self.db_inode,
                    self.unifieddb_authority_receipt_sha256,
                ),
            )
            readback = self._validated_readback(
                memory_id=record.memory_id,
                lifecycle_generation=record.lifecycle_generation,
                expected_record_sha256=record_sha256,
                row=self._fetch_row(record_sha256),
            )
            readback.verify_exact_record(record)
            self.connection.commit()
            return record_sha256
        except Exception:
            self.connection.rollback()
            raise

    def load_record(
        self,
        memory_id: str,
        lifecycle_generation: int,
        *,
        expected_record_sha256: str,
    ) -> TypedMemoryReadback:
        """Authenticate one exact record; lifecycle-only selection is never performed."""
        memory_id = _identifier("memory_id", memory_id)
        lifecycle_generation = _generation(lifecycle_generation)
        expected_record_sha256 = _sha256_identity(
            "expected_record_sha256", expected_record_sha256
        )
        self._assert_no_caller_transaction()
        self._assert_current_unifieddb_identity()
        try:
            row = self._fetch_row(expected_record_sha256)
        except sqlite3.Error as exc:
            raise TypedMemoryPersistenceError("TYPED_MEMORY_READ_FAILED") from exc
        return self._validated_readback(
            memory_id=memory_id,
            lifecycle_generation=lifecycle_generation,
            expected_record_sha256=expected_record_sha256,
            row=row,
        )


__all__ = [
    "PERSISTENCE_SCHEMA",
    "READBACK_SCHEMA",
    "TYPED_MEMORY_TABLE",
    "TypedMemoryPersistenceError",
    "TypedMemoryReadback",
    "TypedMemoryUnifiedDBStore",
]
