"""Durable per-recipient coordination delivery for Frankenstein 2.0.

Implements the F2-WP-103 core state machine:

    PENDING -> OFFERED -> ACKED
                  |
                  +-- lease expiry -> OFFERED (redelivery, new offer token)

Messages are never consumed by read. Delivery state is keyed by
(event_id, recipient_id), so one recipient acknowledging a message cannot consume it
for another recipient. Stable event identity is caller supplied; duplicate registration
is idempotent only when the immutable message body and generation match exactly.

This module is a coordination primitive. It does not grant effect authority, infer
identity, create causal ids, or promote message content to canonical truth.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class DeliveryError(ValueError):
    """Base error for recipient-delivery contract violations."""


class DeliveryConflict(DeliveryError):
    """Raised when a stable identity is reused with different immutable content."""


class DeliveryStateError(DeliveryError):
    """Raised for stale/invalid delivery transitions."""


_ALLOWED_STATES = frozenset({"PENDING", "OFFERED", "ACKED"})
_MAX_ID_LEN = 512


def _clean_id(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise DeliveryError(f"{name} must be a string")
    if not value or value != value.strip():
        raise DeliveryError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise DeliveryError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise DeliveryError(f"{name} contains control characters")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise DeliveryError("generation must be a non-negative integer")
    return value


def _finite_time(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DeliveryError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise DeliveryError(f"{name} must be finite")
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DeliveryError(f"payload must be canonical-JSON serializable: {exc}") from exc


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _offer_token(event_id: str, recipient_id: str, generation: int, attempt: int) -> str:
    # Attempt is persisted transactionally, so each redelivery receives a distinct token
    # without depending on process-local randomness or wall-clock identity.
    material = f"F2_DELIVERY_OFFER/v1\0{event_id}\0{recipient_id}\0{generation}\0{attempt}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    event_id: str
    recipient_id: str
    state: str
    generation: int
    attempt_count: int
    offer_token: str | None
    offered_at: float | None
    offer_expires_at: float | None
    acked_at: float | None
    payload: Any
    payload_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "recipient_id": self.recipient_id,
            "state": self.state,
            "generation": self.generation,
            "attempt_count": self.attempt_count,
            "offer_token": self.offer_token,
            "offered_at": self.offered_at,
            "offer_expires_at": self.offer_expires_at,
            "acked_at": self.acked_at,
            "payload": self.payload,
            "payload_sha256": self.payload_sha256,
        }


class RecipientDeliveryStore:
    """SQLite-backed durable coordination-delivery store.

    The store intentionally owns only delivery state. The supplied ``db_path`` may point
    at the canonical UnifiedDB once its schema owner integrates this table set, or at an
    isolated test database. No alternate truth/effect authority is created here.
    """

    def __init__(self, db_path: str | Path, *, timeout: float = 5.0) -> None:
        self.db_path = str(db_path)
        self.timeout = float(timeout)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=self.timeout, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=5000")
        return con

    def _init_schema(self) -> None:
        with self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS coordination_events (
                    event_id TEXT PRIMARY KEY,
                    generation INTEGER NOT NULL CHECK (generation >= 0),
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS coordination_deliveries (
                    event_id TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('PENDING','OFFERED','ACKED')),
                    generation INTEGER NOT NULL CHECK (generation >= 0),
                    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                    offer_token TEXT,
                    offered_at REAL,
                    offer_expires_at REAL,
                    acked_at REAL,
                    PRIMARY KEY (event_id, recipient_id),
                    FOREIGN KEY (event_id) REFERENCES coordination_events(event_id)
                        ON DELETE RESTRICT,
                    CHECK (
                        (state = 'PENDING' AND offer_token IS NULL AND offered_at IS NULL
                         AND offer_expires_at IS NULL AND acked_at IS NULL)
                        OR
                        (state = 'OFFERED' AND offer_token IS NOT NULL AND offered_at IS NOT NULL
                         AND offer_expires_at IS NOT NULL AND acked_at IS NULL)
                        OR
                        (state = 'ACKED' AND offer_token IS NOT NULL AND offered_at IS NOT NULL
                         AND offer_expires_at IS NOT NULL AND acked_at IS NOT NULL)
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_coordination_delivery_recipient_state
                    ON coordination_deliveries(recipient_id, state, offer_expires_at, event_id);
                """
            )

    def register(
        self,
        *,
        event_id: str,
        generation: int,
        payload: Any,
        recipients: Iterable[str],
        created_at: float | None = None,
    ) -> None:
        """Register a stable event and its independent recipient deliveries.

        Re-registering the same event with byte-equivalent canonical payload and generation
        is idempotent. Reuse with changed payload/generation fails closed. New recipients may
        be added idempotently to an existing matching event.
        """
        event_id = _clean_id("event_id", event_id)
        generation = _generation(generation)
        payload_json = _canonical_json(payload)
        payload_sha256 = _digest(payload_json)
        created_at = time.time() if created_at is None else _finite_time("created_at", created_at)

        cleaned: list[str] = []
        seen: set[str] = set()
        for recipient in recipients:
            recipient = _clean_id("recipient_id", recipient)
            if recipient not in seen:
                seen.add(recipient)
                cleaned.append(recipient)
        if not cleaned:
            raise DeliveryError("recipients must contain at least one recipient_id")

        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT generation,payload_sha256 FROM coordination_events WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO coordination_events(event_id,generation,payload_json,payload_sha256,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (event_id, generation, payload_json, payload_sha256, created_at),
                )
            elif row["generation"] != generation or row["payload_sha256"] != payload_sha256:
                raise DeliveryConflict(
                    "event_id already exists with different generation or payload digest"
                )

            for recipient_id in cleaned:
                con.execute(
                    "INSERT OR IGNORE INTO coordination_deliveries("
                    "event_id,recipient_id,state,generation,attempt_count"
                    ") VALUES(?,?, 'PENDING', ?, 0)",
                    (event_id, recipient_id, generation),
                )
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def offer(
        self,
        *,
        recipient_id: str,
        generation: int,
        lease_seconds: float,
        limit: int = 1,
        now: float | None = None,
    ) -> list[DeliveryRecord]:
        """Offer pending or lease-expired messages to one recipient.

        A currently live OFFERED row is not offered again. An expired row is redelivered
        with incremented attempt_count and a new deterministic offer token. Generation is a
        hard fence: callers cannot consume messages from another task generation.
        """
        recipient_id = _clean_id("recipient_id", recipient_id)
        generation = _generation(generation)
        lease_seconds = _finite_time("lease_seconds", lease_seconds)
        if lease_seconds <= 0:
            raise DeliveryError("lease_seconds must be > 0")
        if type(limit) is not int or limit <= 0 or limit > 1000:
            raise DeliveryError("limit must be an integer in [1, 1000]")
        now = time.time() if now is None else _finite_time("now", now)
        expires = now + lease_seconds

        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            rows = con.execute(
                """
                SELECT d.event_id,d.attempt_count
                FROM coordination_deliveries d
                WHERE d.recipient_id=? AND d.generation=? AND (
                    d.state='PENDING' OR
                    (d.state='OFFERED' AND d.offer_expires_at <= ?)
                )
                ORDER BY d.event_id
                LIMIT ?
                """,
                (recipient_id, generation, now, limit),
            ).fetchall()

            selected: list[str] = []
            for row in rows:
                attempt = int(row["attempt_count"]) + 1
                token = _offer_token(row["event_id"], recipient_id, generation, attempt)
                cur = con.execute(
                    """
                    UPDATE coordination_deliveries
                    SET state='OFFERED', attempt_count=?, offer_token=?, offered_at=?,
                        offer_expires_at=?, acked_at=NULL
                    WHERE event_id=? AND recipient_id=? AND generation=? AND (
                        state='PENDING' OR (state='OFFERED' AND offer_expires_at <= ?)
                    )
                    """,
                    (
                        attempt,
                        token,
                        now,
                        expires,
                        row["event_id"],
                        recipient_id,
                        generation,
                        now,
                    ),
                )
                if cur.rowcount == 1:
                    selected.append(row["event_id"])
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

        return [self.get(event_id=eid, recipient_id=recipient_id) for eid in selected]

    def ack(
        self,
        *,
        event_id: str,
        recipient_id: str,
        generation: int,
        offer_token: str,
        now: float | None = None,
    ) -> DeliveryRecord:
        """Acknowledge the exact live offer instance.

        ACK fails closed for a stale generation, wrong/stale offer token, non-OFFERED row,
        or expired lease. This prevents a delayed worker from acknowledging a later
        redelivery that it did not actually receive.
        """
        event_id = _clean_id("event_id", event_id)
        recipient_id = _clean_id("recipient_id", recipient_id)
        generation = _generation(generation)
        offer_token = _clean_id("offer_token", offer_token)
        now = time.time() if now is None else _finite_time("now", now)

        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                """
                SELECT state,generation,offer_token,offer_expires_at
                FROM coordination_deliveries
                WHERE event_id=? AND recipient_id=?
                """,
                (event_id, recipient_id),
            ).fetchone()
            if row is None:
                raise DeliveryStateError("delivery does not exist")
            if row["generation"] != generation:
                raise DeliveryStateError("generation mismatch")
            if row["state"] != "OFFERED":
                raise DeliveryStateError(f"delivery is {row['state']}, not OFFERED")
            if row["offer_token"] != offer_token:
                raise DeliveryStateError("offer token mismatch or stale redelivery token")
            if row["offer_expires_at"] < now:
                raise DeliveryStateError("offer lease expired; redelivery required")

            cur = con.execute(
                """
                UPDATE coordination_deliveries
                SET state='ACKED', acked_at=?
                WHERE event_id=? AND recipient_id=? AND generation=?
                  AND state='OFFERED' AND offer_token=? AND offer_expires_at >= ?
                """,
                (now, event_id, recipient_id, generation, offer_token, now),
            )
            if cur.rowcount != 1:
                raise DeliveryStateError("delivery changed concurrently before ACK")
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()
        return self.get(event_id=event_id, recipient_id=recipient_id)

    def get(self, *, event_id: str, recipient_id: str) -> DeliveryRecord:
        event_id = _clean_id("event_id", event_id)
        recipient_id = _clean_id("recipient_id", recipient_id)
        with self._connect() as con:
            row = con.execute(
                """
                SELECT d.event_id,d.recipient_id,d.state,d.generation,d.attempt_count,
                       d.offer_token,d.offered_at,d.offer_expires_at,d.acked_at,
                       e.payload_json,e.payload_sha256
                FROM coordination_deliveries d
                JOIN coordination_events e ON e.event_id=d.event_id
                WHERE d.event_id=? AND d.recipient_id=?
                """,
                (event_id, recipient_id),
            ).fetchone()
        if row is None:
            raise DeliveryStateError("delivery does not exist")
        if row["state"] not in _ALLOWED_STATES:
            raise DeliveryStateError("database contains invalid delivery state")
        return DeliveryRecord(
            event_id=row["event_id"],
            recipient_id=row["recipient_id"],
            state=row["state"],
            generation=row["generation"],
            attempt_count=row["attempt_count"],
            offer_token=row["offer_token"],
            offered_at=row["offered_at"],
            offer_expires_at=row["offer_expires_at"],
            acked_at=row["acked_at"],
            payload=json.loads(row["payload_json"]),
            payload_sha256=row["payload_sha256"],
        )

    def delivery_counts(self, *, recipient_id: str | None = None) -> Mapping[str, int]:
        params: Sequence[Any]
        where: str
        if recipient_id is None:
            params = ()
            where = ""
        else:
            recipient_id = _clean_id("recipient_id", recipient_id)
            params = (recipient_id,)
            where = "WHERE recipient_id=?"
        with self._connect() as con:
            rows = con.execute(
                f"SELECT state,COUNT(*) AS n FROM coordination_deliveries {where} GROUP BY state",
                params,
            ).fetchall()
        counts = {state: 0 for state in sorted(_ALLOWED_STATES)}
        counts.update({row["state"]: int(row["n"]) for row in rows})
        return counts
