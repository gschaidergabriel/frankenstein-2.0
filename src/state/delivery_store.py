#!/usr/bin/env python3
"""Transactional UnifiedDB-backed recipient delivery storage for Frankenstein 2.0.

F2-WP-103 generation 1 continuation.

This module consumes, but does not replace, the accepted F2-WP-100 UnifiedDB identity
contract and the F2-WP-101 causal identity contract. A store can only be opened against
an existing SQLite file selected by a UnifiedDBResolution and fingerprinted by a
UnifiedDBFingerprint. It never invents a database path and never creates a second DB.

Every mutation is serialized with BEGIN IMMEDIATE and is bound to an exact CausalIdentity.
The tables below are WP-103-owned tables inside the canonical UnifiedDB. This module is
not an effect executor, transport, completion authority, or world-fact authority.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from frankenstein2.causal_identity import CausalIdentity
from state.delivery_lifecycle import (
    DELIVERY_SCHEMA,
    DeliveryOperation,
    DeliveryState,
    DeliveryTransition,
    RecipientDelivery,
    apply_delivery_transition,
    derive_delivery_id,
)
from state.unifieddb_identity import (
    FINGERPRINT_SCHEMA,
    RESOLUTION_SCHEMA,
    UnifiedDBFingerprint,
    UnifiedDBResolution,
)

STORE_SCHEMA = "FRANKENSTEIN2_RECIPIENT_DELIVERY_STORE/v1"
DELIVERY_TABLE = "f2_recipient_deliveries"
TRANSITION_TABLE = "f2_recipient_delivery_transitions"


class DeliveryStoreError(RuntimeError):
    """Fail-closed persistence/binding error."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _transition_payload(transition: DeliveryTransition) -> dict[str, Any]:
    operation = transition.operation
    if not isinstance(operation, DeliveryOperation):
        raise DeliveryStoreError("DELIVERY_OPERATION_ENUM_REQUIRED")
    return {
        "transition_id": transition.transition_id,
        "delivery_id": transition.delivery_id,
        "causal_event_id": transition.causal_event_id,
        "recipient_id": transition.recipient_id,
        "generation": transition.generation,
        "operation": operation.value,
        "transport_attempt_id": transition.transport_attempt_id,
    }


def _transition_digest(transition: DeliveryTransition) -> str:
    return hashlib.sha256(
        _canonical_json(_transition_payload(transition)).encode("utf-8")
    ).hexdigest()


def _encode_tuple(values: tuple[str, ...]) -> str:
    return _canonical_json(list(values))


def _decode_tuple(raw: str, *, label: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeliveryStoreError(f"CORRUPT_{label}_JSON") from exc
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise DeliveryStoreError(f"CORRUPT_{label}")
    return tuple(value)


def _same_real_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
        os.path.realpath(right)
    )


class CanonicalDeliveryStore:
    """Recipient-delivery writer bound to one authorized canonical UnifiedDB file."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        resolution: UnifiedDBResolution,
        fingerprint: UnifiedDBFingerprint,
    ):
        if not isinstance(connection, sqlite3.Connection):
            raise DeliveryStoreError("SQLITE_CONNECTION_REQUIRED")
        if not isinstance(resolution, UnifiedDBResolution):
            raise DeliveryStoreError("UNIFIEDDB_RESOLUTION_REQUIRED")
        if not isinstance(fingerprint, UnifiedDBFingerprint):
            raise DeliveryStoreError("UNIFIEDDB_FINGERPRINT_REQUIRED")
        if resolution.schema != RESOLUTION_SCHEMA:
            raise DeliveryStoreError("UNIFIEDDB_RESOLUTION_SCHEMA_MISMATCH")
        if fingerprint.schema != FINGERPRINT_SCHEMA:
            raise DeliveryStoreError("UNIFIEDDB_FINGERPRINT_SCHEMA_MISMATCH")
        if not resolution.exists_at_resolution:
            raise DeliveryStoreError("UNIFIEDDB_MUST_EXIST_BEFORE_DELIVERY_WRITER_OPEN")
        if not fingerprint.exists or fingerprint.status != "SQLITE3_REGULAR_FILE":
            raise DeliveryStoreError("UNIFIEDDB_FINGERPRINT_NOT_WRITABLE_SQLITE_IDENTITY")
        if not _same_real_path(resolution.path, fingerprint.real_path):
            raise DeliveryStoreError("UNIFIEDDB_RESOLUTION_FINGERPRINT_PATH_MISMATCH")

        expected = Path(fingerprint.real_path)
        try:
            current_stat = expected.stat()
        except OSError as exc:
            raise DeliveryStoreError("UNIFIEDDB_FILE_MISSING_AT_WRITER_OPEN") from exc
        if fingerprint.device is None or fingerprint.inode is None:
            raise DeliveryStoreError("UNIFIEDDB_FINGERPRINT_FILE_IDENTITY_MISSING")
        if (current_stat.st_dev, current_stat.st_ino) != (
            fingerprint.device,
            fingerprint.inode,
        ):
            raise DeliveryStoreError("UNIFIEDDB_REPLACED_AFTER_FINGERPRINT")
        if connection.in_transaction:
            raise DeliveryStoreError("CALLER_TRANSACTION_ALREADY_OPEN")

        database_rows = connection.execute("PRAGMA database_list").fetchall()
        main_paths = [
            row[2] for row in database_rows if len(row) >= 3 and row[1] == "main"
        ]
        if len(main_paths) != 1 or not main_paths[0]:
            raise DeliveryStoreError("SQLITE_MAIN_DATABASE_PATH_UNAVAILABLE")
        if not _same_real_path(main_paths[0], fingerprint.real_path):
            raise DeliveryStoreError(
                "SQLITE_CONNECTION_NOT_BOUND_TO_FINGERPRINTED_UNIFIEDDB"
            )

        self.connection = connection
        self.resolution = resolution
        self.fingerprint = fingerprint
        self.canonical_db_path = os.path.realpath(fingerprint.real_path)
        self.authority_receipt_sha256 = fingerprint.receipt_sha256()
        self.connection.execute("PRAGMA foreign_keys=ON")

    @classmethod
    def open(
        cls,
        *,
        resolution: UnifiedDBResolution,
        fingerprint: UnifiedDBFingerprint,
        timeout: float = 5.0,
    ) -> "CanonicalDeliveryStore":
        """Open the fingerprinted UnifiedDB read/write, never create it."""
        if not isinstance(fingerprint, UnifiedDBFingerprint) or not fingerprint.real_path:
            raise DeliveryStoreError("UNIFIEDDB_FINGERPRINT_REQUIRED")
        uri = Path(fingerprint.real_path).as_uri() + "?mode=rw"
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=timeout)
        except sqlite3.Error as exc:
            raise DeliveryStoreError("UNIFIEDDB_READWRITE_OPEN_FAILED") from exc
        try:
            return cls(connection, resolution=resolution, fingerprint=fingerprint)
        except Exception:
            connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def initialize_schema(self) -> None:
        """Create WP-103 tables only inside the selected canonical UnifiedDB."""
        if self.connection.in_transaction:
            raise DeliveryStoreError("CALLER_TRANSACTION_ALREADY_OPEN")
        statements = (
            f"""CREATE TABLE IF NOT EXISTS {DELIVERY_TABLE}(
                  delivery_id TEXT PRIMARY KEY,
                  causal_event_id TEXT NOT NULL,
                  recipient_id TEXT NOT NULL,
                  causal_identity_digest TEXT NOT NULL,
                  causal_identity_json TEXT NOT NULL,
                  canonical_db_path TEXT NOT NULL,
                  generation INTEGER NOT NULL CHECK(generation >= 1),
                  state TEXT NOT NULL CHECK(state IN ('PENDING','OFFERED','ACKED')),
                  transport_attempt_ids_json TEXT NOT NULL,
                  applied_transition_ids_json TEXT NOT NULL,
                  acknowledged_attempt_id TEXT,
                  revision INTEGER NOT NULL CHECK(revision >= 0),
                  UNIQUE(causal_event_id, recipient_id)
                )""",
            f"""CREATE TABLE IF NOT EXISTS {TRANSITION_TABLE}(
                  transition_id TEXT PRIMARY KEY,
                  delivery_id TEXT NOT NULL REFERENCES {DELIVERY_TABLE}(delivery_id),
                  transition_digest TEXT NOT NULL,
                  causal_identity_digest TEXT NOT NULL,
                  unifieddb_authority_receipt_sha256 TEXT NOT NULL,
                  generation INTEGER NOT NULL CHECK(generation >= 1),
                  operation TEXT NOT NULL CHECK(operation IN ('OFFER','ACK')),
                  transport_attempt_id TEXT NOT NULL,
                  applied_revision INTEGER NOT NULL CHECK(applied_revision >= 1)
                )""",
            f"""CREATE INDEX IF NOT EXISTS idx_f2_delivery_causal_recipient
                  ON {DELIVERY_TABLE}(causal_event_id, recipient_id)""",
            f"""CREATE INDEX IF NOT EXISTS idx_f2_delivery_transition_delivery
                  ON {TRANSITION_TABLE}(delivery_id)""",
        )
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            for statement in statements:
                self.connection.execute(statement)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    @staticmethod
    def _bind_identity(
        identity: CausalIdentity, transition: DeliveryTransition
    ) -> tuple[str, str]:
        if not isinstance(identity, CausalIdentity):
            raise DeliveryStoreError("CAUSAL_IDENTITY_REQUIRED")
        if identity.generation < 1:
            raise DeliveryStoreError("DELIVERY_CAUSAL_GENERATION_MUST_BE_POSITIVE")
        if not isinstance(transition, DeliveryTransition):
            raise DeliveryStoreError("DELIVERY_TRANSITION_REQUIRED")
        _transition_payload(transition)
        if transition.causal_event_id != identity.causal_id:
            raise DeliveryStoreError("TRANSITION_CAUSAL_ID_NOT_BOUND_TO_CAUSAL_IDENTITY")
        if transition.generation != identity.generation:
            raise DeliveryStoreError("TRANSITION_GENERATION_NOT_BOUND_TO_CAUSAL_IDENTITY")
        identity_json = identity.canonical_json()
        return identity_json, identity.sha256()

    @staticmethod
    def _record_from_row(row: sqlite3.Row | tuple[Any, ...]) -> RecipientDelivery:
        return RecipientDelivery(
            schema=DELIVERY_SCHEMA,
            delivery_id=row[0],
            causal_event_id=row[1],
            recipient_id=row[2],
            generation=int(row[6]),
            state=DeliveryState(row[7]),
            transport_attempt_ids=_decode_tuple(row[8], label="TRANSPORT_ATTEMPT_IDS"),
            applied_transition_ids=_decode_tuple(row[9], label="APPLIED_TRANSITION_IDS"),
            acknowledged_attempt_id=row[10],
        )

    def _select_delivery(self, delivery_id: str):
        try:
            return self.connection.execute(
                f"""SELECT delivery_id, causal_event_id, recipient_id,
                           causal_identity_digest, causal_identity_json, canonical_db_path,
                           generation, state, transport_attempt_ids_json,
                           applied_transition_ids_json, acknowledged_attempt_id, revision
                    FROM {DELIVERY_TABLE} WHERE delivery_id=?""",
                (delivery_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                raise DeliveryStoreError("DELIVERY_STORE_SCHEMA_NOT_INITIALIZED") from exc
            raise

    def get_delivery(
        self, *, causal_event_id: str, recipient_id: str
    ) -> RecipientDelivery | None:
        delivery_id = derive_delivery_id(causal_event_id, recipient_id)
        row = self._select_delivery(delivery_id)
        return None if row is None else self._record_from_row(row)

    def transition_count(self, delivery_id: str) -> int:
        try:
            row = self.connection.execute(
                f"SELECT COUNT(*) FROM {TRANSITION_TABLE} WHERE delivery_id=?",
                (delivery_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                raise DeliveryStoreError("DELIVERY_STORE_SCHEMA_NOT_INITIALIZED") from exc
            raise
        return int(row[0])

    def apply(
        self, identity: CausalIdentity, transition: DeliveryTransition
    ) -> RecipientDelivery:
        """Atomically apply or replay one transition bound to exact causal identity."""
        identity_json, identity_digest = self._bind_identity(identity, transition)
        transition_digest = _transition_digest(transition)
        if self.connection.in_transaction:
            raise DeliveryStoreError("CALLER_TRANSACTION_ALREADY_OPEN")

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self._select_delivery(transition.delivery_id)
            if row is None:
                expected_delivery_id = derive_delivery_id(
                    identity.causal_id, transition.recipient_id
                )
                if transition.delivery_id != expected_delivery_id:
                    raise DeliveryStoreError(
                        "DELIVERY_ID_NOT_DERIVED_FROM_CAUSAL_RECIPIENT"
                    )
                record = RecipientDelivery.pending(
                    causal_event_id=identity.causal_id,
                    recipient_id=transition.recipient_id,
                    generation=identity.generation,
                )
                self.connection.execute(
                    f"""INSERT INTO {DELIVERY_TABLE}(
                           delivery_id, causal_event_id, recipient_id,
                           causal_identity_digest, causal_identity_json, canonical_db_path,
                           generation, state, transport_attempt_ids_json,
                           applied_transition_ids_json, acknowledged_attempt_id, revision
                         ) VALUES(?,?,?,?,?,?,?,?,?,?,?,0)""",
                    (
                        record.delivery_id,
                        record.causal_event_id,
                        record.recipient_id,
                        identity_digest,
                        identity_json,
                        self.canonical_db_path,
                        record.generation,
                        record.state.value,
                        _encode_tuple(record.transport_attempt_ids),
                        _encode_tuple(record.applied_transition_ids),
                        record.acknowledged_attempt_id,
                    ),
                )
                revision = 0
            else:
                record = self._record_from_row(row)
                stored_identity_digest = row[3]
                stored_identity_json = row[4]
                stored_db_path = row[5]
                revision = int(row[11])
                if (
                    stored_identity_digest != identity_digest
                    or stored_identity_json != identity_json
                ):
                    raise DeliveryStoreError("CAUSAL_IDENTITY_DRIFT_FOR_EXISTING_DELIVERY")
                if not _same_real_path(stored_db_path, self.canonical_db_path):
                    raise DeliveryStoreError("DELIVERY_CANONICAL_DB_PATH_DRIFT")

            prior = self.connection.execute(
                f"""SELECT transition_digest, causal_identity_digest
                    FROM {TRANSITION_TABLE} WHERE transition_id=?""",
                (transition.transition_id,),
            ).fetchone()
            if prior is not None:
                if prior[0] != transition_digest:
                    raise DeliveryStoreError("TRANSITION_ID_REUSED_WITH_CHANGED_PAYLOAD")
                if prior[1] != identity_digest:
                    raise DeliveryStoreError(
                        "TRANSITION_ID_REUSED_WITH_CHANGED_CAUSAL_IDENTITY"
                    )
                self.connection.commit()
                current = self._select_delivery(transition.delivery_id)
                if current is None:
                    raise DeliveryStoreError("TRANSITION_EXISTS_WITHOUT_DELIVERY")
                return self._record_from_row(current)

            updated = apply_delivery_transition(record, transition)
            next_revision = revision + 1
            changed = self.connection.execute(
                f"""UPDATE {DELIVERY_TABLE}
                    SET state=?, transport_attempt_ids_json=?, applied_transition_ids_json=?,
                        acknowledged_attempt_id=?, revision=?
                    WHERE delivery_id=? AND revision=? AND causal_identity_digest=?""",
                (
                    updated.state.value,
                    _encode_tuple(updated.transport_attempt_ids),
                    _encode_tuple(updated.applied_transition_ids),
                    updated.acknowledged_attempt_id,
                    next_revision,
                    updated.delivery_id,
                    revision,
                    identity_digest,
                ),
            ).rowcount
            if changed != 1:
                raise DeliveryStoreError("DELIVERY_REVISION_CONFLICT")

            self.connection.execute(
                f"""INSERT INTO {TRANSITION_TABLE}(
                       transition_id, delivery_id, transition_digest,
                       causal_identity_digest, unifieddb_authority_receipt_sha256,
                       generation, operation, transport_attempt_id, applied_revision
                     ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    transition.transition_id,
                    updated.delivery_id,
                    transition_digest,
                    identity_digest,
                    self.authority_receipt_sha256,
                    transition.generation,
                    transition.operation.value,
                    transition.transport_attempt_id,
                    next_revision,
                ),
            )
            self.connection.commit()
            return updated
        except Exception:
            self.connection.rollback()
            raise
