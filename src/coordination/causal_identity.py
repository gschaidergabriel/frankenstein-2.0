#!/usr/bin/env python3
"""Fail-closed causal identity primitives for Frankenstein 2.0.

F2-WP-101 generation 1.

This module separates a replay-stable logical causal event from a concrete telemetry /
admission record.  It deliberately does not use timestamps, process IDs, transport paths,
or the mutable UnifiedDB fingerprint receipt as causal-ID material.

The UnifiedDB receipt is carried beside the causal identity so later readers can prove
which durable-state authority a state-affecting event referenced without making ordinary
state evolution change the identity of the event itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Optional


CAUSAL_ID_SCHEMA = "FRANKENSTEIN2_CAUSAL_EVENT_ID/v1"
EVENT_RECORD_ID_SCHEMA = "FRANKENSTEIN2_EVENT_RECORD_ID/v1"
CAUSAL_ENVELOPE_SCHEMA = "FRANKENSTEIN2_CAUSAL_EVENT_ENVELOPE/v1"

_CAUSAL_RE = re.compile(r"^f2c1:[0-9a-f]{64}$")
_EVENT_RE = re.compile(r"^f2e1:[0-9a-f]{64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CausalIdentityError(ValueError):
    """Raised when a causal identity would otherwise be ambiguous or fabricated."""


def _atom(name: str, value: str, *, max_len: int = 512) -> str:
    if not isinstance(value, str):
        raise CausalIdentityError(f"{name}_MUST_BE_STRING")
    if not value:
        raise CausalIdentityError(f"{name}_EMPTY")
    if value != value.strip():
        raise CausalIdentityError(f"{name}_SURROUNDING_WHITESPACE")
    if len(value) > max_len:
        raise CausalIdentityError(f"{name}_TOO_LONG")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise CausalIdentityError(f"{name}_CONTROL_CHARACTER")
    return value


def _generation(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CausalIdentityError("generation_MUST_BE_INTEGER")
    if value < 0:
        raise CausalIdentityError("generation_NEGATIVE")
    return value


def _sha256(name: str, value: str) -> str:
    _atom(name, value, max_len=64)
    if not _SHA256_RE.fullmatch(value):
        raise CausalIdentityError(f"{name}_NOT_SHA256")
    return value


def _causal_id(value: str, *, name: str = "causal_id") -> str:
    _atom(name, value, max_len=68)
    if not _CAUSAL_RE.fullmatch(value):
        raise CausalIdentityError(f"{name}_INVALID")
    return value


def _event_id(value: str) -> str:
    _atom("event_id", value, max_len=68)
    if not _EVENT_RE.fullmatch(value):
        raise CausalIdentityError("event_id_INVALID")
    return value


def _canonical_json(payload: dict) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(payload: dict) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


@dataclass(frozen=True)
class OperationalIdentity:
    """Minimum parallel-worker identity required by Triggerword-4 coordination law."""

    session_id: str
    agent_id: str
    task_id: str
    turn_id: str
    generation: int

    def __post_init__(self) -> None:
        _atom("session_id", self.session_id)
        _atom("agent_id", self.agent_id)
        _atom("task_id", self.task_id)
        _atom("turn_id", self.turn_id)
        _generation(self.generation)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CausalEventEnvelope:
    """Identity-only envelope; not proof that the represented event actually happened."""

    schema: str
    causal_id: str
    event_id: str
    event_key: str
    event_type: str
    operational: OperationalIdentity
    parent_causal_id: Optional[str]
    root_causal_id: Optional[str]
    producer_component: str
    admission_key: str
    unifieddb_receipt_sha256: Optional[str]
    state_affecting: bool
    classification: str = "IDENTITY_BINDING_NOT_EVENT_OR_EFFECT_PROOF"

    def __post_init__(self) -> None:
        if self.schema != CAUSAL_ENVELOPE_SCHEMA:
            raise CausalIdentityError("causal_envelope_SCHEMA_INVALID")
        _causal_id(self.causal_id)
        _event_id(self.event_id)
        _atom("event_key", self.event_key)
        _atom("event_type", self.event_type)
        _atom("producer_component", self.producer_component)
        _atom("admission_key", self.admission_key)
        _validate_lineage(self.parent_causal_id, self.root_causal_id)
        if not isinstance(self.state_affecting, bool):
            raise CausalIdentityError("state_affecting_MUST_BE_BOOL")
        if self.unifieddb_receipt_sha256 is not None:
            _sha256("unifieddb_receipt_sha256", self.unifieddb_receipt_sha256)
        if self.state_affecting and self.unifieddb_receipt_sha256 is None:
            raise CausalIdentityError("STATE_AFFECTING_EVENT_WITHOUT_UNIFIEDDB_BINDING")

        expected_causal = derive_causal_id(
            operational=self.operational,
            event_key=self.event_key,
            event_type=self.event_type,
            parent_causal_id=self.parent_causal_id,
            root_causal_id=self.root_causal_id,
        )
        if self.causal_id != expected_causal:
            raise CausalIdentityError("causal_id_PREIMAGE_MISMATCH")

        expected_event = derive_event_id(
            causal_id=self.causal_id,
            producer_component=self.producer_component,
            admission_key=self.admission_key,
        )
        if self.event_id != expected_event:
            raise CausalIdentityError("event_id_PREIMAGE_MISMATCH")

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["operational"] = self.operational.to_dict()
        return payload

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict()).decode("utf-8")

    def receipt_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _validate_lineage(
    parent_causal_id: Optional[str], root_causal_id: Optional[str]
) -> None:
    # Missing lineage is never silently guessed.  A child must name both its immediate
    # parent and its chain root.  A root event names neither.
    if parent_causal_id is None and root_causal_id is None:
        return
    if parent_causal_id is None or root_causal_id is None:
        raise CausalIdentityError("CAUSAL_LINEAGE_PARTIAL")
    _causal_id(parent_causal_id, name="parent_causal_id")
    _causal_id(root_causal_id, name="root_causal_id")


def derive_causal_id(
    *,
    operational: OperationalIdentity,
    event_key: str,
    event_type: str,
    parent_causal_id: Optional[str] = None,
    root_causal_id: Optional[str] = None,
) -> str:
    """Derive replay-stable logical event identity.

    `event_key` is a producer-defined stable discriminator inside one operational turn
    (for example `tool:call-17` or `state:agency-update-2`).  It must not be a wall-clock
    timestamp, process ID, random admission token, or transport location.

    The UnifiedDB receipt is intentionally *not* an argument.  It describes the durable
    state authority observed by the event, while the event identity survives later DB
    mutation and replay against an evidence snapshot.
    """
    if not isinstance(operational, OperationalIdentity):
        raise CausalIdentityError("operational_MUST_BE_OPERATIONAL_IDENTITY")
    _atom("event_key", event_key)
    _atom("event_type", event_type)
    _validate_lineage(parent_causal_id, root_causal_id)
    payload = {
        "schema": CAUSAL_ID_SCHEMA,
        "session_id": operational.session_id,
        "agent_id": operational.agent_id,
        "task_id": operational.task_id,
        "turn_id": operational.turn_id,
        "generation": operational.generation,
        "event_key": event_key,
        "event_type": event_type,
        "parent_causal_id": parent_causal_id,
        "root_causal_id": root_causal_id,
    }
    return "f2c1:" + _digest(payload)


def derive_event_id(
    *, causal_id: str, producer_component: str, admission_key: str
) -> str:
    """Derive one concrete record/admission identity for a logical causal event.

    Re-observation can retain `causal_id` while using a new `admission_key`, yielding a
    distinct `event_id`.  Replaying the same admission key is idempotent.
    """
    _causal_id(causal_id)
    _atom("producer_component", producer_component)
    _atom("admission_key", admission_key)
    payload = {
        "schema": EVENT_RECORD_ID_SCHEMA,
        "causal_id": causal_id,
        "producer_component": producer_component,
        "admission_key": admission_key,
    }
    return "f2e1:" + _digest(payload)


def build_causal_envelope(
    *,
    operational: OperationalIdentity,
    event_key: str,
    event_type: str,
    producer_component: str,
    admission_key: str,
    unifieddb_receipt_sha256: Optional[str],
    state_affecting: bool,
    parent_causal_id: Optional[str] = None,
    root_causal_id: Optional[str] = None,
) -> CausalEventEnvelope:
    """Build and self-validate a causal event identity envelope."""
    causal = derive_causal_id(
        operational=operational,
        event_key=event_key,
        event_type=event_type,
        parent_causal_id=parent_causal_id,
        root_causal_id=root_causal_id,
    )
    event = derive_event_id(
        causal_id=causal,
        producer_component=producer_component,
        admission_key=admission_key,
    )
    return CausalEventEnvelope(
        schema=CAUSAL_ENVELOPE_SCHEMA,
        causal_id=causal,
        event_id=event,
        event_key=event_key,
        event_type=event_type,
        operational=operational,
        parent_causal_id=parent_causal_id,
        root_causal_id=root_causal_id,
        producer_component=producer_component,
        admission_key=admission_key,
        unifieddb_receipt_sha256=unifieddb_receipt_sha256,
        state_affecting=state_affecting,
    )


def validate_expected_generation(
    envelope: CausalEventEnvelope, *, expected_generation: int
) -> None:
    """Fail closed before a stale worker uses an old generation for a stateful action."""
    if not isinstance(envelope, CausalEventEnvelope):
        raise CausalIdentityError("envelope_MUST_BE_CAUSAL_EVENT_ENVELOPE")
    expected = _generation(expected_generation)
    if envelope.operational.generation != expected:
        raise CausalIdentityError(
            f"STALE_GENERATION:{envelope.operational.generation}!={expected}"
        )


def validate_unifieddb_binding(
    envelope: CausalEventEnvelope, *, expected_receipt_sha256: str
) -> None:
    """Require exact durable-state authority binding without changing causal identity."""
    if not isinstance(envelope, CausalEventEnvelope):
        raise CausalIdentityError("envelope_MUST_BE_CAUSAL_EVENT_ENVELOPE")
    expected = _sha256("expected_receipt_sha256", expected_receipt_sha256)
    if envelope.unifieddb_receipt_sha256 is None:
        raise CausalIdentityError("UNIFIEDDB_BINDING_MISSING")
    if envelope.unifieddb_receipt_sha256 != expected:
        raise CausalIdentityError("UNIFIEDDB_BINDING_MISMATCH")


__all__ = [
    "CAUSAL_ID_SCHEMA",
    "EVENT_RECORD_ID_SCHEMA",
    "CAUSAL_ENVELOPE_SCHEMA",
    "CausalIdentityError",
    "OperationalIdentity",
    "CausalEventEnvelope",
    "derive_causal_id",
    "derive_event_id",
    "build_causal_envelope",
    "validate_expected_generation",
    "validate_unifieddb_binding",
]
