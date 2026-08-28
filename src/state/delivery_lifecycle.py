#!/usr/bin/env python3
"""Recipient-scoped delivery lifecycle primitives for Frankenstein 2.0.

F2-WP-103 keeps causal-event identity, recipient-delivery identity and concrete
transport-attempt identity separate.  This module is deliberately persistence-
agnostic: UnifiedDB remains the canonical state authority; callers persist the
returned immutable records transactionally in that substrate.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
from typing import Tuple


DELIVERY_SCHEMA = "FRANKENSTEIN2_RECIPIENT_DELIVERY/v1"


class DeliveryLifecycleError(RuntimeError):
    """Fail-closed delivery lifecycle error."""


class DeliveryState(str, Enum):
    PENDING = "PENDING"
    OFFERED = "OFFERED"
    ACKED = "ACKED"


class DeliveryOperation(str, Enum):
    OFFER = "OFFER"
    ACK = "ACK"


def _require_token(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeliveryLifecycleError(f"EMPTY_{name.upper()}")
    return value.strip()


def derive_delivery_id(causal_event_id: str, recipient_id: str) -> str:
    """Derive one stable recipient-delivery id from one causal event.

    The generation and transport-attempt are intentionally excluded: replay or
    retry must not mint a second recipient-delivery identity for the same causal
    event and recipient.
    """
    causal = _require_token("causal_event_id", causal_event_id)
    recipient = _require_token("recipient_id", recipient_id)
    payload = f"{DELIVERY_SCHEMA}\x00{causal}\x00{recipient}".encode("utf-8")
    return "delivery:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class RecipientDelivery:
    schema: str
    delivery_id: str
    causal_event_id: str
    recipient_id: str
    generation: int
    state: DeliveryState
    transport_attempt_ids: Tuple[str, ...] = ()
    applied_transition_ids: Tuple[str, ...] = ()
    acknowledged_attempt_id: str | None = None

    @classmethod
    def pending(cls, *, causal_event_id: str, recipient_id: str, generation: int) -> "RecipientDelivery":
        if int(generation) < 1:
            raise DeliveryLifecycleError("INVALID_GENERATION")
        causal = _require_token("causal_event_id", causal_event_id)
        recipient = _require_token("recipient_id", recipient_id)
        return cls(
            schema=DELIVERY_SCHEMA,
            delivery_id=derive_delivery_id(causal, recipient),
            causal_event_id=causal,
            recipient_id=recipient,
            generation=int(generation),
            state=DeliveryState.PENDING,
        )


@dataclass(frozen=True)
class DeliveryTransition:
    transition_id: str
    delivery_id: str
    causal_event_id: str
    recipient_id: str
    generation: int
    operation: DeliveryOperation
    transport_attempt_id: str


def _validate_identity(record: RecipientDelivery, transition: DeliveryTransition) -> None:
    if record.schema != DELIVERY_SCHEMA:
        raise DeliveryLifecycleError("DELIVERY_SCHEMA_MISMATCH")
    if transition.delivery_id != record.delivery_id:
        raise DeliveryLifecycleError("DELIVERY_ID_MISMATCH")
    if transition.causal_event_id != record.causal_event_id:
        raise DeliveryLifecycleError("CAUSAL_EVENT_ID_MISMATCH")
    if transition.recipient_id != record.recipient_id:
        raise DeliveryLifecycleError("RECIPIENT_ID_MISMATCH")
    if int(transition.generation) != int(record.generation):
        raise DeliveryLifecycleError("STALE_GENERATION")


def apply_delivery_transition(record: RecipientDelivery, transition: DeliveryTransition) -> RecipientDelivery:
    """Apply one immutable recipient-delivery transition.

    Replaying the exact same transition_id is idempotent. A transport retry gets
    a new transport_attempt_id but does not mint a second delivery. ACK must bind
    to an actually observed offer attempt. Backward/skipped transitions fail
    closed.
    """
    _validate_identity(record, transition)
    transition_id = _require_token("transition_id", transition.transition_id)
    attempt_id = _require_token("transport_attempt_id", transition.transport_attempt_id)

    if transition_id in record.applied_transition_ids:
        return record

    applied = record.applied_transition_ids + (transition_id,)

    if transition.operation == DeliveryOperation.OFFER:
        if record.state == DeliveryState.ACKED:
            raise DeliveryLifecycleError("OFFER_AFTER_ACK_FORBIDDEN")
        if attempt_id in record.transport_attempt_ids:
            raise DeliveryLifecycleError("TRANSPORT_ATTEMPT_REUSED_WITH_NEW_TRANSITION")
        return replace(
            record,
            state=DeliveryState.OFFERED,
            transport_attempt_ids=record.transport_attempt_ids + (attempt_id,),
            applied_transition_ids=applied,
        )

    if transition.operation == DeliveryOperation.ACK:
        if record.state == DeliveryState.PENDING:
            raise DeliveryLifecycleError("ACK_BEFORE_OFFER_FORBIDDEN")
        if record.state == DeliveryState.ACKED:
            raise DeliveryLifecycleError("SECOND_ACK_WITH_NEW_TRANSITION_FORBIDDEN")
        if attempt_id not in record.transport_attempt_ids:
            raise DeliveryLifecycleError("ACK_UNKNOWN_TRANSPORT_ATTEMPT")
        return replace(
            record,
            state=DeliveryState.ACKED,
            applied_transition_ids=applied,
            acknowledged_attempt_id=attempt_id,
        )

    raise DeliveryLifecycleError("UNKNOWN_DELIVERY_OPERATION")
