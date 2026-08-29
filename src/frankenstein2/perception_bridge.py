"""Typed local-edge/VPS bridge contracts for the Frankenstein 2.0 Perception Fabric.

The bridge defaults to compact typed percept/event metadata. Raw frame/ROI transport and
external VLM escalation are separately permission-gated. This module creates immutable
transport/audit candidates only; it performs no network or sensor I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, ClassVar

from .perception_fabric import (
    ObserveIntent,
    PerceptionCapability,
    PerceptionCapabilitySnapshot,
    PerceptionFabricError,
)

BRIDGE_ENVELOPE_SCHEMA = "FRANKENSTEIN2_PERCEPTION_BRIDGE_ENVELOPE/v1"
AUDIT_RECEIPT_SCHEMA = "FRANKENSTEIN2_PERCEPTION_AUDIT_RECEIPT/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PerceptionBridgeError(ValueError):
    """Fail-closed validation error for Perception Fabric bridge contracts."""


class BridgePayloadKind(str, Enum):
    TYPED_EVENT = "TYPED_EVENT"
    RAW_ROI = "RAW_ROI"


class AuditOutcome(str, Enum):
    EXECUTED = "EXECUTED"
    REJECTED_PERMISSION = "REJECTED_PERMISSION"
    REJECTED_STALE = "REJECTED_STALE"
    DROPPED_BACKPRESSURE = "DROPPED_BACKPRESSURE"
    FAILED = "FAILED"


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise PerceptionBridgeError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PerceptionBridgeError(f"{name} must not contain control characters")
    return value


def _nonnegative(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PerceptionBridgeError(f"{name} must be an integer >= 0")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise PerceptionBridgeError(f"{name} must be lowercase sha256 hex")
    return value


def _refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise PerceptionBridgeError(f"{name} must be a non-empty immutable tuple")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise PerceptionBridgeError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PerceptionBridgeError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionBridgeEnvelope:
    envelope_id: str
    source_id: str
    observe_intent_sha256: str
    permission_snapshot_sha256: str
    payload_kind: BridgePayloadKind
    payload_sha256: str
    external_vlm_requested: bool
    created_monotonic_ns: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = BRIDGE_ENVELOPE_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_BRIDGE_TRANSPORT_CANDIDATE_NOT_OBSERVATION_TRUTH_EFFECT_OR_COMPLETION"

    def __post_init__(self) -> None:
        object.__setattr__(self, "envelope_id", _text("envelope_id", self.envelope_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _sha256("observe_intent_sha256", self.observe_intent_sha256)
        _sha256("permission_snapshot_sha256", self.permission_snapshot_sha256)
        if not isinstance(self.payload_kind, BridgePayloadKind):
            raise PerceptionBridgeError("payload_kind must be a BridgePayloadKind")
        _sha256("payload_sha256", self.payload_sha256)
        if type(self.external_vlm_requested) is not bool:
            raise PerceptionBridgeError("external_vlm_requested must be bool")
        _nonnegative("created_monotonic_ns", self.created_monotonic_ns)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))
        if self.external_vlm_requested and self.payload_kind != BridgePayloadKind.RAW_ROI:
            raise PerceptionBridgeError("external VLM requests require RAW_ROI payload kind")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "envelope_id": self.envelope_id,
            "source_id": self.source_id,
            "observe_intent_sha256": self.observe_intent_sha256,
            "permission_snapshot_sha256": self.permission_snapshot_sha256,
            "payload_kind": self.payload_kind.value,
            "payload_sha256": self.payload_sha256,
            "external_vlm_requested": self.external_vlm_requested,
            "created_monotonic_ns": self.created_monotonic_ns,
            "contains_payload_bytes": False,
            "world_truth_authority": "NONE",
            "gwt_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionAuditReceipt:
    receipt_id: str
    source_id: str
    observe_intent_sha256: str
    permission_snapshot_sha256: str
    outcome: AuditOutcome
    executed_head_ids: tuple[str, ...]
    raw_payload_persisted: bool
    remote_raw_payload_sent: bool
    external_vlm_called: bool
    event_monotonic_ns: int
    reason: str
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = AUDIT_RECEIPT_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_EXECUTION_AUDIT_NOT_WORLD_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "receipt_id", _text("receipt_id", self.receipt_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _sha256("observe_intent_sha256", self.observe_intent_sha256)
        _sha256("permission_snapshot_sha256", self.permission_snapshot_sha256)
        if not isinstance(self.outcome, AuditOutcome):
            raise PerceptionBridgeError("outcome must be an AuditOutcome")
        if type(self.executed_head_ids) is not tuple:
            raise PerceptionBridgeError("executed_head_ids must be an immutable tuple")
        checked_heads = tuple(_text("executed_head_id", item) for item in self.executed_head_ids)
        if len(checked_heads) != len(set(checked_heads)):
            raise PerceptionBridgeError("executed_head_ids must not contain duplicates")
        object.__setattr__(self, "executed_head_ids", tuple(sorted(checked_heads)))
        for name in ("raw_payload_persisted", "remote_raw_payload_sent", "external_vlm_called"):
            if type(getattr(self, name)) is not bool:
                raise PerceptionBridgeError(f"{name} must be bool")
        _nonnegative("event_monotonic_ns", self.event_monotonic_ns)
        object.__setattr__(self, "reason", _text("reason", self.reason))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))
        if self.outcome != AuditOutcome.EXECUTED:
            if self.executed_head_ids or self.remote_raw_payload_sent or self.external_vlm_called:
                raise PerceptionBridgeError("non-executed receipt cannot claim heads/remote raw/VLM execution")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "receipt_id": self.receipt_id,
            "source_id": self.source_id,
            "observe_intent_sha256": self.observe_intent_sha256,
            "permission_snapshot_sha256": self.permission_snapshot_sha256,
            "outcome": self.outcome.value,
            "executed_head_ids": list(self.executed_head_ids),
            "raw_payload_persisted": self.raw_payload_persisted,
            "remote_raw_payload_sent": self.remote_raw_payload_sent,
            "external_vlm_called": self.external_vlm_called,
            "event_monotonic_ns": self.event_monotonic_ns,
            "reason": self.reason,
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def build_bridge_envelope(
    *,
    intent: ObserveIntent,
    snapshot: PerceptionCapabilitySnapshot,
    payload_kind: BridgePayloadKind,
    payload_sha256: str,
    external_vlm_requested: bool,
    now_monotonic_ns: int,
    provenance_refs: tuple[str, ...],
) -> PerceptionBridgeEnvelope:
    """Build a transport candidate only after exact current permission validation."""
    if type(intent) is not ObserveIntent:
        raise PerceptionBridgeError("intent must be a concrete ObserveIntent")
    if type(snapshot) is not PerceptionCapabilitySnapshot:
        raise PerceptionBridgeError("snapshot must be a concrete PerceptionCapabilitySnapshot")
    try:
        intent.validate_against(snapshot, now_monotonic_ns=now_monotonic_ns)
    except PerceptionFabricError as exc:
        raise PerceptionBridgeError(str(exc)) from exc
    if not isinstance(payload_kind, BridgePayloadKind):
        raise PerceptionBridgeError("payload_kind must be a BridgePayloadKind")
    _sha256("payload_sha256", payload_sha256)
    if type(external_vlm_requested) is not bool:
        raise PerceptionBridgeError("external_vlm_requested must be bool")
    if payload_kind == BridgePayloadKind.RAW_ROI:
        if not intent.allow_remote_frame or not snapshot.allows(PerceptionCapability.REMOTE_FRAME):
            raise PerceptionBridgeError("RAW_ROI transport requires exact REMOTE_FRAME authorization")
    if external_vlm_requested:
        if payload_kind != BridgePayloadKind.RAW_ROI:
            raise PerceptionBridgeError("external VLM request requires RAW_ROI transport")
        if not intent.allow_external_vlm or not snapshot.allows(PerceptionCapability.EXTERNAL_VLM):
            raise PerceptionBridgeError("external VLM request requires exact EXTERNAL_VLM authorization")
        if not intent.allow_remote_frame or not snapshot.allows(PerceptionCapability.REMOTE_FRAME):
            raise PerceptionBridgeError("external VLM request additionally requires REMOTE_FRAME authorization")
    provenance = set(_refs("provenance_refs", provenance_refs))
    provenance.update(intent.provenance_refs)
    provenance.update(snapshot.provenance_refs)
    provenance.add(f"observe-intent-sha256:{intent.sha256()}")
    provenance.add(f"permission-snapshot-sha256:{snapshot.sha256()}")
    payload = {
        "source_id": intent.source_id,
        "intent_sha256": intent.sha256(),
        "permission_snapshot_sha256": snapshot.sha256(),
        "payload_kind": payload_kind.value,
        "payload_sha256": payload_sha256,
        "external_vlm_requested": external_vlm_requested,
        "created_monotonic_ns": now_monotonic_ns,
    }
    return PerceptionBridgeEnvelope(
        envelope_id="perception-bridge:" + _digest(payload)[:24],
        source_id=intent.source_id,
        observe_intent_sha256=intent.sha256(),
        permission_snapshot_sha256=snapshot.sha256(),
        payload_kind=payload_kind,
        payload_sha256=payload_sha256,
        external_vlm_requested=external_vlm_requested,
        created_monotonic_ns=now_monotonic_ns,
        provenance_refs=tuple(sorted(provenance)),
    )


def build_audit_receipt(
    *,
    intent: ObserveIntent,
    snapshot: PerceptionCapabilitySnapshot,
    outcome: AuditOutcome,
    executed_head_ids: tuple[str, ...],
    raw_payload_persisted: bool,
    remote_raw_payload_sent: bool,
    external_vlm_called: bool,
    event_monotonic_ns: int,
    reason: str,
    provenance_refs: tuple[str, ...],
) -> PerceptionAuditReceipt:
    """Record what an external executor reports, without promoting it to truth/completion."""
    if type(intent) is not ObserveIntent or type(snapshot) is not PerceptionCapabilitySnapshot:
        raise PerceptionBridgeError("intent/snapshot must be concrete Perception Fabric contracts")
    if intent.source_id != snapshot.source_id or intent.permission_snapshot_sha256 != snapshot.sha256():
        raise PerceptionBridgeError("receipt intent/snapshot identity mismatch")
    if not isinstance(outcome, AuditOutcome):
        raise PerceptionBridgeError("outcome must be an AuditOutcome")
    if raw_payload_persisted and not snapshot.allows(PerceptionCapability.RAW_RETENTION):
        raise PerceptionBridgeError("receipt cannot claim raw persistence without RAW_RETENTION authorization")
    if remote_raw_payload_sent and not snapshot.allows(PerceptionCapability.REMOTE_FRAME):
        raise PerceptionBridgeError("receipt cannot claim remote raw transport without REMOTE_FRAME authorization")
    if external_vlm_called:
        if not snapshot.allows(PerceptionCapability.EXTERNAL_VLM):
            raise PerceptionBridgeError("receipt cannot claim external VLM without EXTERNAL_VLM authorization")
        if not remote_raw_payload_sent:
            raise PerceptionBridgeError("external VLM receipt requires remote raw/ROI transport")
    provenance = set(_refs("provenance_refs", provenance_refs))
    provenance.add(f"observe-intent-sha256:{intent.sha256()}")
    provenance.add(f"permission-snapshot-sha256:{snapshot.sha256()}")
    payload = {
        "intent_sha256": intent.sha256(),
        "snapshot_sha256": snapshot.sha256(),
        "outcome": outcome.value,
        "executed_head_ids": sorted(executed_head_ids),
        "raw_payload_persisted": raw_payload_persisted,
        "remote_raw_payload_sent": remote_raw_payload_sent,
        "external_vlm_called": external_vlm_called,
        "event_monotonic_ns": event_monotonic_ns,
        "reason": reason,
    }
    return PerceptionAuditReceipt(
        receipt_id="perception-audit:" + _digest(payload)[:24],
        source_id=intent.source_id,
        observe_intent_sha256=intent.sha256(),
        permission_snapshot_sha256=snapshot.sha256(),
        outcome=outcome,
        executed_head_ids=executed_head_ids,
        raw_payload_persisted=raw_payload_persisted,
        remote_raw_payload_sent=remote_raw_payload_sent,
        external_vlm_called=external_vlm_called,
        event_monotonic_ns=event_monotonic_ns,
        reason=reason,
        provenance_refs=tuple(sorted(provenance)),
    )


__all__ = [
    "AUDIT_RECEIPT_SCHEMA",
    "BRIDGE_ENVELOPE_SCHEMA",
    "AuditOutcome",
    "BridgePayloadKind",
    "PerceptionAuditReceipt",
    "PerceptionBridgeEnvelope",
    "PerceptionBridgeError",
    "build_audit_receipt",
    "build_bridge_envelope",
]
