"""Deliver canonical deferred child returns through F2-WP-103.

This module closes the identity gap between:
- F2-WP-102 NativeChildBinding (delegation/result provenance),
- F2-WP-104 DeferredReturnEnvelope (eligible causal re-entry), and
- F2-WP-103 RecipientDeliveryStore (durable PENDING/OFFERED/ACKED delivery).

Routing is never session-singleton based. Each delivery recipient key is derived from the
exact resume CausalIdentity, which includes session, agent, task, turn, causal id and
generation. Therefore two returns for the same agent/session cannot cross-talk merely
because a mutable "current effect/result" pointer changed.

This component transports an already-valid return envelope. It does not spawn children,
decide task success, authorize effects, or convert model output into world fact.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .causal_identity import CausalIdentity
from .deferred_return import DeferredReturnEnvelope, DeferredReturnError
from .recipient_delivery import DeliveryRecord, RecipientDeliveryStore


_PAYLOAD_SCHEMA = "F2_DEFERRED_RETURN_DELIVERY/v1"


class DeferredReturnDeliveryError(ValueError):
    """Raised when deferred-return transport identity fails closed."""


def causal_recipient_id(resume: CausalIdentity) -> str:
    if not isinstance(resume, CausalIdentity):
        raise DeferredReturnDeliveryError("resume must be a CausalIdentity")
    digest = hashlib.sha256(resume.canonical_json().encode("utf-8")).hexdigest()
    return "causal-recipient:" + digest


def delivery_event_id(return_id: str) -> str:
    if not isinstance(return_id, str) or not return_id or return_id != return_id.strip():
        raise DeferredReturnDeliveryError("return_id must be non-empty and already trimmed")
    # Hash only the stable return identity. If the same return_id is replayed with mutated
    # envelope content, RecipientDeliveryStore sees the same event_id and rejects the
    # payload digest conflict instead of quietly creating a second message.
    digest = hashlib.sha256(return_id.encode("utf-8")).hexdigest()
    return "deferred-return:" + digest


def _payload(envelope: DeferredReturnEnvelope) -> dict[str, Any]:
    return {
        "schema": _PAYLOAD_SCHEMA,
        "return_id": envelope.return_id,
        "return_sha256": envelope.sha256(),
        "envelope": envelope.as_dict(),
    }


@dataclass(frozen=True, slots=True)
class OfferedDeferredReturn:
    delivery: DeliveryRecord
    envelope: DeferredReturnEnvelope


def enqueue_deferred_return(
    store: RecipientDeliveryStore,
    envelope: DeferredReturnEnvelope,
    *,
    created_at: float | None = None,
) -> DeliveryRecord:
    """Persist an eligible child result for its exact parent resume identity."""
    if not isinstance(store, RecipientDeliveryStore):
        raise DeferredReturnDeliveryError("store must be a RecipientDeliveryStore")
    if not isinstance(envelope, DeferredReturnEnvelope):
        raise DeferredReturnDeliveryError("envelope must be a DeferredReturnEnvelope")

    event_id = delivery_event_id(envelope.return_id)
    recipient = causal_recipient_id(envelope.resume)
    store.register(
        event_id=event_id,
        generation=envelope.resume.generation,
        payload=_payload(envelope),
        recipients=[recipient],
        created_at=created_at,
    )
    return store.get(event_id=event_id, recipient_id=recipient)


def _decode_and_verify(record: DeliveryRecord, expected_resume: CausalIdentity) -> OfferedDeferredReturn:
    payload = record.payload
    if not isinstance(payload, dict) or payload.get("schema") != _PAYLOAD_SCHEMA:
        raise DeferredReturnDeliveryError("delivery payload schema mismatch")
    try:
        envelope = DeferredReturnEnvelope.from_mapping(payload["envelope"])
    except (KeyError, TypeError, ValueError, DeferredReturnError) as exc:
        raise DeferredReturnDeliveryError(f"invalid deferred-return payload: {exc}") from exc

    if envelope.resume != expected_resume:
        raise DeferredReturnDeliveryError("offered return resume identity mismatch")
    if payload.get("return_id") != envelope.return_id:
        raise DeferredReturnDeliveryError("return_id payload mismatch")
    if payload.get("return_sha256") != envelope.sha256():
        raise DeferredReturnDeliveryError("return envelope digest mismatch")
    if record.event_id != delivery_event_id(envelope.return_id):
        raise DeferredReturnDeliveryError("delivery event identity mismatch")
    if record.recipient_id != causal_recipient_id(expected_resume):
        raise DeferredReturnDeliveryError("delivery recipient identity mismatch")
    if record.generation != expected_resume.generation:
        raise DeferredReturnDeliveryError("delivery generation mismatch")
    return OfferedDeferredReturn(delivery=record, envelope=envelope)


def offer_deferred_returns(
    store: RecipientDeliveryStore,
    *,
    resume: CausalIdentity,
    lease_seconds: float,
    limit: int = 1,
    now: float | None = None,
) -> list[OfferedDeferredReturn]:
    """Offer only returns addressed to this exact resume causal identity."""
    if not isinstance(resume, CausalIdentity):
        raise DeferredReturnDeliveryError("resume must be a CausalIdentity")
    records = store.offer(
        recipient_id=causal_recipient_id(resume),
        generation=resume.generation,
        lease_seconds=lease_seconds,
        limit=limit,
        now=now,
    )
    return [_decode_and_verify(record, resume) for record in records]


def ack_deferred_return(
    store: RecipientDeliveryStore,
    offered: OfferedDeferredReturn,
    *,
    now: float | None = None,
) -> DeliveryRecord:
    """ACK the exact offered attempt after the parent has accepted its re-entry data."""
    if not isinstance(offered, OfferedDeferredReturn):
        raise DeferredReturnDeliveryError("offered must be an OfferedDeferredReturn")
    token = offered.delivery.offer_token
    if token is None:
        raise DeferredReturnDeliveryError("offered delivery has no offer_token")
    return store.ack(
        event_id=offered.delivery.event_id,
        recipient_id=offered.delivery.recipient_id,
        generation=offered.delivery.generation,
        offer_token=token,
        now=now,
    )


__all__ = [
    "DeferredReturnDeliveryError",
    "OfferedDeferredReturn",
    "ack_deferred_return",
    "causal_recipient_id",
    "delivery_event_id",
    "enqueue_deferred_return",
    "offer_deferred_returns",
]
