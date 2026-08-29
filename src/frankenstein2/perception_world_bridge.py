"""Deterministic PerceptionWorldBridge contract for F2-WP-712.

This module validates bridge envelopes and capability/freshness/session fences.
It performs no network I/O, provider/VLM call, device access, persistence,
canonical world-state mutation, effect authorization, or completion minting.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

CAPABILITY_SCHEMA = "FRANKENSTEIN2_PERCEPTION_BRIDGE_CAPABILITY_VIEW/v1"
INTENT_SCHEMA = "FRANKENSTEIN2_BRIDGE_OBSERVE_INTENT/v1"
PERCEPT_SCHEMA = "FRANKENSTEIN2_TYPED_PERCEPT_EVENT/v1"
DECISION_SCHEMA = "FRANKENSTEIN2_PERCEPTION_BRIDGE_DECISION/v1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PAYLOAD_KINDS = frozenset({"TYPED_PERCEPT", "RAW_FRAME", "ROI_FRAME"})
_EPISTEMIC_KINDS = frozenset({"OBSERVED", "INFERRED", "RETRIEVED", "UNKNOWN"})


class PerceptionWorldBridgeError(ValueError):
    """Fail-closed error at the WP712 bridge boundary."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise PerceptionWorldBridgeError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PerceptionWorldBridgeError(f"{name} must not contain control characters")
    return value


def _nonnegative_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PerceptionWorldBridgeError(f"{name} must be an integer >= 0")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise PerceptionWorldBridgeError(f"{name} must be an integer > 0")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise PerceptionWorldBridgeError(f"{name} must be lowercase 64-hex sha256")
    return value


def _refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise PerceptionWorldBridgeError(f"{name} must be a non-empty immutable tuple")
    cleaned = tuple(sorted(_text(f"{name} item", item) for item in value))
    if len(cleaned) != len(set(cleaned)):
        raise PerceptionWorldBridgeError(f"{name} must not contain duplicates")
    return cleaned


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PerceptionWorldBridgeError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class BridgeCapabilityView:
    """Exact current caller-supplied capability projection; not self-granting authority."""

    snapshot_id: str
    generation: int
    source_id: str
    source_generation: int
    permission_snapshot_sha256: str
    remote_frame_allowed: bool
    external_vlm_allowed: bool
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = CAPABILITY_SCHEMA
    classification: ClassVar[str] = "CURRENT_CAPABILITY_PROJECTION_REQUIRES_EXTERNAL_CANONICAL_ADMISSION"

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", _text("snapshot_id", self.snapshot_id))
        _nonnegative_int("generation", self.generation)
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative_int("source_generation", self.source_generation)
        _sha256("permission_snapshot_sha256", self.permission_snapshot_sha256)
        for name in ("remote_frame_allowed", "external_vlm_allowed"):
            if type(getattr(self, name)) is not bool:
                raise PerceptionWorldBridgeError(f"{name} must be bool")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "snapshot_id": self.snapshot_id,
            "generation": self.generation,
            "source_id": self.source_id,
            "source_generation": self.source_generation,
            "permission_snapshot_sha256": self.permission_snapshot_sha256,
            "remote_frame_allowed": self.remote_frame_allowed,
            "external_vlm_allowed": self.external_vlm_allowed,
            "canonical_admission_performed": False,
            "authority_broadening": False,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class BridgeObserveIntent:
    """Execution candidate crossing the bridge; never execution or truth authority."""

    intent_id: str
    source_id: str
    source_generation: int
    permission_snapshot_sha256: str
    bridge_generation: int
    created_monotonic_ns: int
    deadline_monotonic_ns: int
    requested_payload_kind: str
    external_vlm_requested: bool
    clock_domain: str
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = INTENT_SCHEMA
    classification: ClassVar[str] = "OBSERVE_INTENT_CANDIDATE_NOT_EXECUTION_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_id", _text("intent_id", self.intent_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative_int("source_generation", self.source_generation)
        _sha256("permission_snapshot_sha256", self.permission_snapshot_sha256)
        _nonnegative_int("bridge_generation", self.bridge_generation)
        _nonnegative_int("created_monotonic_ns", self.created_monotonic_ns)
        _nonnegative_int("deadline_monotonic_ns", self.deadline_monotonic_ns)
        if self.deadline_monotonic_ns < self.created_monotonic_ns:
            raise PerceptionWorldBridgeError("deadline_monotonic_ns must not precede creation")
        if self.requested_payload_kind not in _PAYLOAD_KINDS:
            raise PerceptionWorldBridgeError("requested_payload_kind is unsupported")
        if type(self.external_vlm_requested) is not bool:
            raise PerceptionWorldBridgeError("external_vlm_requested must be bool")
        object.__setattr__(self, "clock_domain", _text("clock_domain", self.clock_domain))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "intent_id": self.intent_id,
            "source_id": self.source_id,
            "source_generation": self.source_generation,
            "permission_snapshot_sha256": self.permission_snapshot_sha256,
            "bridge_generation": self.bridge_generation,
            "created_monotonic_ns": self.created_monotonic_ns,
            "deadline_monotonic_ns": self.deadline_monotonic_ns,
            "requested_payload_kind": self.requested_payload_kind,
            "external_vlm_requested": self.external_vlm_requested,
            "clock_domain": self.clock_domain,
            "execution_authority": "NONE",
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class TypedPerceptEvent:
    """Typed bridge payload. Raw/ROI payload bytes are never stored here."""

    event_id: str
    source_id: str
    source_generation: int
    permission_snapshot_sha256: str
    bridge_generation: int
    epistemic_kind: str
    payload_kind: str
    payload_ref: str
    source_sequence: int
    capture_monotonic_ns: int
    observed_monotonic_ns: int
    freshness_max_age_ns: int
    clock_domain: str
    clock_uncertainty_ns: int | None
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = PERCEPT_SCHEMA
    classification: ClassVar[str] = "TYPED_PERCEPT_CANDIDATE_NOT_CANONICAL_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _text("event_id", self.event_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative_int("source_generation", self.source_generation)
        _sha256("permission_snapshot_sha256", self.permission_snapshot_sha256)
        _nonnegative_int("bridge_generation", self.bridge_generation)
        if self.epistemic_kind not in _EPISTEMIC_KINDS:
            raise PerceptionWorldBridgeError("epistemic_kind is unsupported")
        if self.payload_kind not in _PAYLOAD_KINDS:
            raise PerceptionWorldBridgeError("payload_kind is unsupported")
        object.__setattr__(self, "payload_ref", _text("payload_ref", self.payload_ref))
        _positive_int("source_sequence", self.source_sequence)
        _nonnegative_int("capture_monotonic_ns", self.capture_monotonic_ns)
        _nonnegative_int("observed_monotonic_ns", self.observed_monotonic_ns)
        if self.observed_monotonic_ns < self.capture_monotonic_ns:
            raise PerceptionWorldBridgeError("observed_monotonic_ns must not precede capture")
        _nonnegative_int("freshness_max_age_ns", self.freshness_max_age_ns)
        object.__setattr__(self, "clock_domain", _text("clock_domain", self.clock_domain))
        if self.clock_uncertainty_ns is not None:
            _nonnegative_int("clock_uncertainty_ns", self.clock_uncertainty_ns)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "event_id": self.event_id,
            "source_id": self.source_id,
            "source_generation": self.source_generation,
            "permission_snapshot_sha256": self.permission_snapshot_sha256,
            "bridge_generation": self.bridge_generation,
            "epistemic_kind": self.epistemic_kind,
            "payload_kind": self.payload_kind,
            "payload_ref": self.payload_ref,
            "raw_payload": None,
            "source_sequence": self.source_sequence,
            "capture_monotonic_ns": self.capture_monotonic_ns,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "freshness_max_age_ns": self.freshness_max_age_ns,
            "clock_domain": self.clock_domain,
            "clock_uncertainty_ns": self.clock_uncertainty_ns,
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class BridgeDecision:
    decision_id: str
    operation: str
    source_id: str
    source_generation: int
    bridge_generation: int
    permission_snapshot_sha256: str
    object_ref: str
    payload_kind: str
    external_vlm: bool
    reason: str
    temporal_status: str
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = DECISION_SCHEMA
    classification: ClassVar[str] = "BRIDGE_VALIDATION_DECISION_NOT_NETWORK_EFFECT_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", _text("decision_id", self.decision_id))
        if self.operation not in {"DISPATCH_INTENT", "ADMIT_PERCEPT"}:
            raise PerceptionWorldBridgeError("operation is unsupported")
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative_int("source_generation", self.source_generation)
        _nonnegative_int("bridge_generation", self.bridge_generation)
        _sha256("permission_snapshot_sha256", self.permission_snapshot_sha256)
        object.__setattr__(self, "object_ref", _text("object_ref", self.object_ref))
        if self.payload_kind not in _PAYLOAD_KINDS:
            raise PerceptionWorldBridgeError("payload_kind is unsupported")
        if type(self.external_vlm) is not bool:
            raise PerceptionWorldBridgeError("external_vlm must be bool")
        object.__setattr__(self, "reason", _text("reason", self.reason))
        if self.temporal_status not in {"CURRENT_BOUNDED_CANDIDATE", "UNALIGNED_CANDIDATE", "NOT_APPLICABLE"}:
            raise PerceptionWorldBridgeError("temporal_status is unsupported")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "decision_id": self.decision_id,
            "operation": self.operation,
            "source_id": self.source_id,
            "source_generation": self.source_generation,
            "bridge_generation": self.bridge_generation,
            "permission_snapshot_sha256": self.permission_snapshot_sha256,
            "object_ref": self.object_ref,
            "payload_kind": self.payload_kind,
            "external_vlm": self.external_vlm,
            "reason": self.reason,
            "temporal_status": self.temporal_status,
            "network_io_performed": False,
            "provider_or_vlm_invoked": False,
            "canonical_world_mutation": False,
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }


def _validate_current_authority(
    *,
    source_id: str,
    source_generation: int,
    permission_snapshot_sha256: str,
    bridge_generation: int,
    current_capability: BridgeCapabilityView,
    current_bridge_generation: int,
) -> None:
    if type(current_capability) is not BridgeCapabilityView:
        raise PerceptionWorldBridgeError("current_capability must be a concrete BridgeCapabilityView")
    _nonnegative_int("current_bridge_generation", current_bridge_generation)
    if source_id != current_capability.source_id:
        raise PerceptionWorldBridgeError("source_id no longer matches current capability")
    if source_generation != current_capability.source_generation:
        raise PerceptionWorldBridgeError("source generation is stale or mismatched")
    if permission_snapshot_sha256 != current_capability.permission_snapshot_sha256:
        raise PerceptionWorldBridgeError("permission snapshot is stale, revoked or mismatched")
    if bridge_generation != current_bridge_generation:
        raise PerceptionWorldBridgeError("bridge generation is stale after disconnect/reconnect")


def validate_observe_intent_for_dispatch(
    *,
    decision_id: str,
    intent: BridgeObserveIntent,
    current_capability: BridgeCapabilityView,
    current_bridge_generation: int,
    now_monotonic_ns: int,
    now_clock_domain: str,
    provenance_refs: tuple[str, ...],
) -> BridgeDecision:
    """Validate an ObserveIntent for dispatch without performing network/provider I/O."""
    if type(intent) is not BridgeObserveIntent:
        raise PerceptionWorldBridgeError("intent must be a concrete BridgeObserveIntent")
    _nonnegative_int("now_monotonic_ns", now_monotonic_ns)
    now_clock_domain = _text("now_clock_domain", now_clock_domain)
    if now_clock_domain != intent.clock_domain:
        raise PerceptionWorldBridgeError("ObserveIntent expiry cannot be established across clock domains")
    _validate_current_authority(
        source_id=intent.source_id,
        source_generation=intent.source_generation,
        permission_snapshot_sha256=intent.permission_snapshot_sha256,
        bridge_generation=intent.bridge_generation,
        current_capability=current_capability,
        current_bridge_generation=current_bridge_generation,
    )
    if now_monotonic_ns > intent.deadline_monotonic_ns:
        raise PerceptionWorldBridgeError("ObserveIntent is expired and non-replayable")
    if intent.requested_payload_kind in {"RAW_FRAME", "ROI_FRAME"} and not current_capability.remote_frame_allowed:
        raise PerceptionWorldBridgeError("REMOTE_FRAME capability is required at transfer time")
    if intent.external_vlm_requested and not current_capability.external_vlm_allowed:
        raise PerceptionWorldBridgeError("EXTERNAL_VLM capability is required at dispatch time")
    return BridgeDecision(
        decision_id=decision_id,
        operation="DISPATCH_INTENT",
        source_id=intent.source_id,
        source_generation=intent.source_generation,
        bridge_generation=current_bridge_generation,
        permission_snapshot_sha256=current_capability.permission_snapshot_sha256,
        object_ref=intent.intent_id,
        payload_kind=intent.requested_payload_kind,
        external_vlm=intent.external_vlm_requested,
        reason="CURRENT_CAPABILITY_SESSION_AND_EXPIRY_FENCES_PASS",
        temporal_status="NOT_APPLICABLE",
        provenance_refs=provenance_refs,
    )


def validate_remote_percept_for_admission(
    *,
    decision_id: str,
    event: TypedPerceptEvent,
    current_capability: BridgeCapabilityView,
    current_bridge_generation: int,
    receive_monotonic_ns: int,
    receive_clock_domain: str,
    provenance_refs: tuple[str, ...],
) -> BridgeDecision:
    """Validate a remote percept candidate without promoting it to canonical world truth."""
    if type(event) is not TypedPerceptEvent:
        raise PerceptionWorldBridgeError("event must be a concrete TypedPerceptEvent")
    _nonnegative_int("receive_monotonic_ns", receive_monotonic_ns)
    receive_clock_domain = _text("receive_clock_domain", receive_clock_domain)
    _validate_current_authority(
        source_id=event.source_id,
        source_generation=event.source_generation,
        permission_snapshot_sha256=event.permission_snapshot_sha256,
        bridge_generation=event.bridge_generation,
        current_capability=current_capability,
        current_bridge_generation=current_bridge_generation,
    )
    if event.payload_kind in {"RAW_FRAME", "ROI_FRAME"} and not current_capability.remote_frame_allowed:
        raise PerceptionWorldBridgeError("REMOTE_FRAME capability is required at transfer time")

    if receive_clock_domain == event.clock_domain:
        if receive_monotonic_ns < event.observed_monotonic_ns:
            raise PerceptionWorldBridgeError("receive time cannot precede observation in the same monotonic domain")
        age = receive_monotonic_ns - event.observed_monotonic_ns
        if age > event.freshness_max_age_ns:
            raise PerceptionWorldBridgeError("remote percept is stale and cannot be treated as current")
        temporal_status = "CURRENT_BOUNDED_CANDIDATE"
        reason = "CURRENT_CAPABILITY_SESSION_AND_SAME_CLOCK_FRESHNESS_FENCES_PASS"
    else:
        temporal_status = "UNALIGNED_CANDIDATE"
        reason = "CURRENT_CAPABILITY_SESSION_PASS_TEMPORAL_RELATION_UNALIGNED"

    return BridgeDecision(
        decision_id=decision_id,
        operation="ADMIT_PERCEPT",
        source_id=event.source_id,
        source_generation=event.source_generation,
        bridge_generation=current_bridge_generation,
        permission_snapshot_sha256=current_capability.permission_snapshot_sha256,
        object_ref=event.event_id,
        payload_kind=event.payload_kind,
        external_vlm=False,
        reason=reason,
        temporal_status=temporal_status,
        provenance_refs=provenance_refs,
    )
