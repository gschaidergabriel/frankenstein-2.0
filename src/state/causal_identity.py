#!/usr/bin/env python3
"""Replay-stable causal identity and concrete admission identity primitives.

F2-WP-101 generation 1 source candidate.

A real-world/logical causal event and a concrete observation/admission of that event are
separate identities. Replaying the same event must preserve ``causal_event_id`` while a
new transport/admission receives a distinct ``admission_id``. Conversely, two distinct
source events must never collapse merely because their payload bytes are equal.

This module is deterministic and side-effect free. It does not write UnifiedDB and does
not grant runtime/canonical-effect credit by constructing an identity object.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Optional


CAUSAL_IDENTITY_SCHEMA = "FRANKENSTEIN2_CAUSAL_IDENTITY/v1"
CAUSAL_EVENT_SCHEMA = "FRANKENSTEIN2_CAUSAL_EVENT_KEY/v1"
ADMISSION_SCHEMA = "FRANKENSTEIN2_ADMISSION_KEY/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}$")


class CausalIdentityError(ValueError):
    """Fail-closed causal/admission identity error."""


@dataclass(frozen=True)
class CausalIdentity:
    schema: str
    session_id: str
    agent_id: str
    task_id: str
    turn_id: str
    generation: int
    source: str
    source_event_key: str
    payload_sha256: str
    causal_event_id: str
    admission_id: str
    transport_id: str
    admission_nonce: str
    parent_causal_event_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    def receipt_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(namespace: str, value: Mapping[str, Any]) -> str:
    payload = f"{namespace}\n{_canonical_json(value)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _token(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not TOKEN_RE.fullmatch(value):
        raise CausalIdentityError(f"INVALID_{field.upper()}")
    return value


def _generation(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CausalIdentityError("INVALID_GENERATION")
    return value


def _sha256(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise CausalIdentityError(f"INVALID_{field.upper()}")
    return value


def derive_causal_event_id(
    *,
    session_id: str,
    agent_id: str,
    task_id: str,
    turn_id: str,
    generation: int,
    source: str,
    source_event_key: str,
    payload_sha256: str,
    parent_causal_event_id: Optional[str] = None,
) -> str:
    """Derive a replay-stable event id from source-owned event identity.

    ``source_event_key`` is mandatory specifically to prevent content-addressing from
    collapsing two distinct events that happen to carry the same bytes. Transport,
    receive time and admission attempt are deliberately excluded so replay/re-admission
    cannot mint a different causal event.
    """
    event = {
        "schema": CAUSAL_EVENT_SCHEMA,
        "session_id": _token(session_id, field="session_id"),
        "agent_id": _token(agent_id, field="agent_id"),
        "task_id": _token(task_id, field="task_id"),
        "turn_id": _token(turn_id, field="turn_id"),
        "generation": _generation(generation),
        "source": _token(source, field="source"),
        "source_event_key": _token(source_event_key, field="source_event_key"),
        "payload_sha256": _sha256(payload_sha256, field="payload_sha256"),
        "parent_causal_event_id": parent_causal_event_id,
    }
    if parent_causal_event_id is not None:
        _sha256(parent_causal_event_id, field="parent_causal_event_id")
    return _digest(CAUSAL_EVENT_SCHEMA, event)


def derive_admission_id(
    *,
    causal_event_id: str,
    transport_id: str,
    admission_nonce: str,
) -> str:
    """Derive one concrete admission identity for an already identified event."""
    admission = {
        "schema": ADMISSION_SCHEMA,
        "causal_event_id": _sha256(causal_event_id, field="causal_event_id"),
        "transport_id": _token(transport_id, field="transport_id"),
        "admission_nonce": _token(admission_nonce, field="admission_nonce"),
    }
    return _digest(ADMISSION_SCHEMA, admission)


def build_causal_identity(
    *,
    session_id: str,
    agent_id: str,
    task_id: str,
    turn_id: str,
    generation: int,
    source: str,
    source_event_key: str,
    payload_sha256: str,
    transport_id: str,
    admission_nonce: str,
    parent_causal_event_id: Optional[str] = None,
) -> CausalIdentity:
    causal_event_id = derive_causal_event_id(
        session_id=session_id,
        agent_id=agent_id,
        task_id=task_id,
        turn_id=turn_id,
        generation=generation,
        source=source,
        source_event_key=source_event_key,
        payload_sha256=payload_sha256,
        parent_causal_event_id=parent_causal_event_id,
    )
    if parent_causal_event_id == causal_event_id:
        raise CausalIdentityError("SELF_PARENT_CAUSAL_EVENT_FORBIDDEN")
    admission_id = derive_admission_id(
        causal_event_id=causal_event_id,
        transport_id=transport_id,
        admission_nonce=admission_nonce,
    )
    return CausalIdentity(
        schema=CAUSAL_IDENTITY_SCHEMA,
        session_id=session_id,
        agent_id=agent_id,
        task_id=task_id,
        turn_id=turn_id,
        generation=generation,
        source=source,
        source_event_key=source_event_key,
        payload_sha256=payload_sha256,
        causal_event_id=causal_event_id,
        admission_id=admission_id,
        transport_id=transport_id,
        admission_nonce=admission_nonce,
        parent_causal_event_id=parent_causal_event_id,
    )


def assert_same_causal_event(left: CausalIdentity, right: CausalIdentity) -> None:
    """Fail closed if two records claimed as re-admissions are not the same event."""
    if left.causal_event_id != right.causal_event_id:
        raise CausalIdentityError("CAUSAL_EVENT_ID_MISMATCH")
    stable_fields = (
        "session_id",
        "agent_id",
        "task_id",
        "turn_id",
        "generation",
        "source",
        "source_event_key",
        "payload_sha256",
        "parent_causal_event_id",
    )
    for field in stable_fields:
        if getattr(left, field) != getattr(right, field):
            raise CausalIdentityError(f"CAUSAL_EVENT_STABLE_FIELD_MISMATCH:{field}")


def assert_distinct_admission(left: CausalIdentity, right: CausalIdentity) -> None:
    """Require two observations of one event to carry different admission identity."""
    assert_same_causal_event(left, right)
    if left.admission_id == right.admission_id:
        raise CausalIdentityError("DUPLICATE_ADMISSION_ID")


__all__ = [
    "ADMISSION_SCHEMA",
    "CAUSAL_EVENT_SCHEMA",
    "CAUSAL_IDENTITY_SCHEMA",
    "CausalIdentity",
    "CausalIdentityError",
    "assert_distinct_admission",
    "assert_same_causal_event",
    "build_causal_identity",
    "derive_admission_id",
    "derive_causal_event_id",
]
