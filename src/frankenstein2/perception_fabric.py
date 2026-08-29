"""Deterministic Perception Fabric contracts for Frankenstein 2.0.

This module defines permission snapshots, sources, top-down ObserveIntent requests and a
bounded 0..4 worker-allocation candidate. It deliberately does not open sensors, read pixels,
call models/providers, persist frames, execute bridge I/O, or mint world/effect/completion
authority. Host-specific sensor binding remains a later local integration step.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, ClassVar

SOURCE_SCHEMA = "FRANKENSTEIN2_PERCEPTION_SOURCE/v1"
CAPABILITY_SNAPSHOT_SCHEMA = "FRANKENSTEIN2_PERCEPTION_CAPABILITY_SNAPSHOT/v1"
OBSERVE_INTENT_SCHEMA = "FRANKENSTEIN2_OBSERVE_INTENT/v1"
WORKER_POLICY_SCHEMA = "FRANKENSTEIN2_PERCEPTION_WORKER_POLICY/v1"
WORKER_ALLOCATION_SCHEMA = "FRANKENSTEIN2_PERCEPTION_WORKER_ALLOCATION/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PerceptionFabricError(ValueError):
    """Fail-closed validation error for Perception Fabric contracts."""


class PerceptionCapability(str, Enum):
    SEE = "SEE"
    ANALYZE = "ANALYZE"
    MEMORY = "MEMORY"
    RAW_RETENTION = "RAW_RETENTION"
    REMOTE_FRAME = "REMOTE_FRAME"
    EXTERNAL_VLM = "EXTERNAL_VLM"


class SourceKind(str, Enum):
    CAMERA = "CAMERA"
    DISPLAY = "DISPLAY"
    BROWSER_RENDERED = "BROWSER_RENDERED"
    BROWSER_STRUCTURAL = "BROWSER_STRUCTURAL"
    USER_ACTIVITY = "USER_ACTIVITY"
    OTHER = "OTHER"


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise PerceptionFabricError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PerceptionFabricError(f"{name} must not contain control characters")
    return value


def _nonnegative_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PerceptionFabricError(f"{name} must be an integer >= 0")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise PerceptionFabricError(f"{name} must be an integer > 0")
    return value


def _micros(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise PerceptionFabricError(f"{name} must be an integer in [0, 1000000]")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise PerceptionFabricError(f"{name} must be lowercase sha256 hex")
    return value


def _refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple or (not allow_empty and not value):
        suffix = "immutable tuple" if allow_empty else "non-empty immutable tuple"
        raise PerceptionFabricError(f"{name} must be a {suffix}")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise PerceptionFabricError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PerceptionFabricError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionSource:
    source_id: str
    kind: SourceKind
    clock_domain: str
    capture_owner_id: str
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = SOURCE_SCHEMA
    classification: ClassVar[str] = "PERMISSION_ADDRESSABLE_SOURCE_NOT_OBSERVATION_OR_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        if not isinstance(self.kind, SourceKind):
            raise PerceptionFabricError("kind must be a SourceKind")
        object.__setattr__(self, "clock_domain", _text("clock_domain", self.clock_domain))
        object.__setattr__(self, "capture_owner_id", _text("capture_owner_id", self.capture_owner_id))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "source_id": self.source_id,
            "kind": self.kind.value,
            "clock_domain": self.clock_domain,
            "capture_owner_id": self.capture_owner_id,
            "observation_authority": "NONE",
            "world_truth_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionCapabilitySnapshot:
    snapshot_id: str
    generation: int
    source_id: str
    capabilities: tuple[PerceptionCapability, ...]
    valid_from_monotonic_ns: int
    expires_monotonic_ns: int | None
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = CAPABILITY_SNAPSHOT_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_PERMISSION_SNAPSHOT_NOT_SENSOR_EXECUTION_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", _text("snapshot_id", self.snapshot_id))
        _nonnegative_int("generation", self.generation)
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        if type(self.capabilities) is not tuple:
            raise PerceptionFabricError("capabilities must be an immutable tuple")
        if any(not isinstance(item, PerceptionCapability) for item in self.capabilities):
            raise PerceptionFabricError("capabilities must contain PerceptionCapability values")
        if len(self.capabilities) != len(set(self.capabilities)):
            raise PerceptionFabricError("capabilities must not contain duplicates")
        object.__setattr__(self, "capabilities", tuple(sorted(self.capabilities, key=lambda item: item.value)))
        _nonnegative_int("valid_from_monotonic_ns", self.valid_from_monotonic_ns)
        if self.expires_monotonic_ns is not None:
            _positive_int("expires_monotonic_ns", self.expires_monotonic_ns)
            if self.expires_monotonic_ns <= self.valid_from_monotonic_ns:
                raise PerceptionFabricError("expires_monotonic_ns must be greater than valid_from_monotonic_ns")
        caps = set(self.capabilities)
        if PerceptionCapability.ANALYZE in caps and PerceptionCapability.SEE not in caps:
            raise PerceptionFabricError("ANALYZE requires SEE")
        if PerceptionCapability.RAW_RETENTION in caps and PerceptionCapability.SEE not in caps:
            raise PerceptionFabricError("RAW_RETENTION requires SEE")
        if PerceptionCapability.REMOTE_FRAME in caps and PerceptionCapability.SEE not in caps:
            raise PerceptionFabricError("REMOTE_FRAME requires SEE")
        if PerceptionCapability.EXTERNAL_VLM in caps and PerceptionCapability.ANALYZE not in caps:
            raise PerceptionFabricError("EXTERNAL_VLM requires ANALYZE")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def allows(self, capability: PerceptionCapability) -> bool:
        if not isinstance(capability, PerceptionCapability):
            raise PerceptionFabricError("capability must be a PerceptionCapability")
        return capability in self.capabilities

    def is_valid_at(self, monotonic_ns: int) -> bool:
        _nonnegative_int("monotonic_ns", monotonic_ns)
        if monotonic_ns < self.valid_from_monotonic_ns:
            return False
        return self.expires_monotonic_ns is None or monotonic_ns < self.expires_monotonic_ns

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "snapshot_id": self.snapshot_id,
            "generation": self.generation,
            "source_id": self.source_id,
            "capabilities": [item.value for item in self.capabilities],
            "valid_from_monotonic_ns": self.valid_from_monotonic_ns,
            "expires_monotonic_ns": self.expires_monotonic_ns,
            "sensor_execution_authority": "POLICY_INPUT_ONLY",
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class ObserveIntent:
    intent_id: str
    cycle_id: str
    generation: int
    source_id: str
    permission_snapshot_sha256: str
    requested_head_ids: tuple[str, ...]
    target_atom_ids: tuple[str, ...]
    roi_ref: str | None
    required_freshness_ns: int
    expires_monotonic_ns: int
    priority_micros: int
    max_work_units: int
    allow_remote_frame: bool
    allow_external_vlm: bool
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = OBSERVE_INTENT_SCHEMA
    classification: ClassVar[str] = "NONCANONICAL_SENSING_REQUEST_NOT_EXECUTION_WORLD_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_id", _text("intent_id", self.intent_id))
        object.__setattr__(self, "cycle_id", _text("cycle_id", self.cycle_id))
        _nonnegative_int("generation", self.generation)
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _sha256("permission_snapshot_sha256", self.permission_snapshot_sha256)
        object.__setattr__(self, "requested_head_ids", _refs("requested_head_ids", self.requested_head_ids, allow_empty=True))
        object.__setattr__(self, "target_atom_ids", _refs("target_atom_ids", self.target_atom_ids, allow_empty=True))
        if not self.requested_head_ids and not self.target_atom_ids:
            raise PerceptionFabricError("ObserveIntent requires requested heads and/or target atoms")
        if self.roi_ref is not None:
            object.__setattr__(self, "roi_ref", _text("roi_ref", self.roi_ref))
        _positive_int("required_freshness_ns", self.required_freshness_ns)
        _positive_int("expires_monotonic_ns", self.expires_monotonic_ns)
        _micros("priority_micros", self.priority_micros)
        _positive_int("max_work_units", self.max_work_units)
        if type(self.allow_remote_frame) is not bool or type(self.allow_external_vlm) is not bool:
            raise PerceptionFabricError("allow_remote_frame and allow_external_vlm must be bool")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def validate_against(self, snapshot: PerceptionCapabilitySnapshot, *, now_monotonic_ns: int) -> None:
        if type(snapshot) is not PerceptionCapabilitySnapshot:
            raise PerceptionFabricError("snapshot must be a concrete PerceptionCapabilitySnapshot")
        _nonnegative_int("now_monotonic_ns", now_monotonic_ns)
        if snapshot.source_id != self.source_id:
            raise PerceptionFabricError("ObserveIntent source_id does not match permission snapshot")
        if snapshot.sha256() != self.permission_snapshot_sha256:
            raise PerceptionFabricError("ObserveIntent permission snapshot digest is stale or mismatched")
        if not snapshot.is_valid_at(now_monotonic_ns):
            raise PerceptionFabricError("permission snapshot is not valid at execution time")
        if now_monotonic_ns >= self.expires_monotonic_ns:
            raise PerceptionFabricError("ObserveIntent is expired")
        if not snapshot.allows(PerceptionCapability.SEE):
            raise PerceptionFabricError("SEE capability is required")
        if self.requested_head_ids and not snapshot.allows(PerceptionCapability.ANALYZE):
            raise PerceptionFabricError("ANALYZE capability is required for requested heads")
        if self.allow_remote_frame and not snapshot.allows(PerceptionCapability.REMOTE_FRAME):
            raise PerceptionFabricError("REMOTE_FRAME capability is not permitted")
        if self.allow_external_vlm and not snapshot.allows(PerceptionCapability.EXTERNAL_VLM):
            raise PerceptionFabricError("EXTERNAL_VLM capability is not permitted")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "intent_id": self.intent_id,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "source_id": self.source_id,
            "permission_snapshot_sha256": self.permission_snapshot_sha256,
            "requested_head_ids": list(self.requested_head_ids),
            "target_atom_ids": list(self.target_atom_ids),
            "roi_ref": self.roi_ref,
            "required_freshness_ns": self.required_freshness_ns,
            "expires_monotonic_ns": self.expires_monotonic_ns,
            "priority_micros": self.priority_micros,
            "max_work_units": self.max_work_units,
            "allow_remote_frame": self.allow_remote_frame,
            "allow_external_vlm": self.allow_external_vlm,
            "perception_execution_authority": "NONE",
            "world_truth_authority": "NONE",
            "gwt_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionWorkerPolicy:
    policy_id: str
    generation: int
    max_active_workers: int
    max_total_work_units: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = WORKER_POLICY_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_COMPUTE_POLICY_NOT_EXECUTION_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _nonnegative_int("generation", self.generation)
        if type(self.max_active_workers) is not int or not 0 <= self.max_active_workers <= 4:
            raise PerceptionFabricError("max_active_workers must be an integer in [0, 4]")
        _nonnegative_int("max_total_work_units", self.max_total_work_units)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "max_active_workers": self.max_active_workers,
            "max_total_work_units": self.max_total_work_units,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionWorkerAllocation:
    allocation_id: str
    policy_sha256: str
    selected_intent_ids: tuple[str, ...]
    deferred_intent_ids: tuple[str, ...]
    total_work_units: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = WORKER_ALLOCATION_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_WORKER_ALLOCATION_CANDIDATE_NOT_EXECUTION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "allocation_id", _text("allocation_id", self.allocation_id))
        _sha256("policy_sha256", self.policy_sha256)
        object.__setattr__(self, "selected_intent_ids", _refs("selected_intent_ids", self.selected_intent_ids, allow_empty=True))
        object.__setattr__(self, "deferred_intent_ids", _refs("deferred_intent_ids", self.deferred_intent_ids, allow_empty=True))
        if set(self.selected_intent_ids).intersection(self.deferred_intent_ids):
            raise PerceptionFabricError("selected and deferred intent ids must be disjoint")
        _nonnegative_int("total_work_units", self.total_work_units)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "allocation_id": self.allocation_id,
            "policy_sha256": self.policy_sha256,
            "selected_intent_ids": list(self.selected_intent_ids),
            "deferred_intent_ids": list(self.deferred_intent_ids),
            "active_worker_count": len(self.selected_intent_ids),
            "total_work_units": self.total_work_units,
            "perception_execution_authority": "NONE",
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def allocate_perception_workers(
    *,
    intents: tuple[ObserveIntent, ...],
    policy: PerceptionWorkerPolicy,
    permission_snapshots: tuple[PerceptionCapabilitySnapshot, ...],
    now_monotonic_ns: int,
) -> PerceptionWorkerAllocation:
    """Select up to four currently permission-valid ObserveIntents deterministically.

    Higher priority wins, then lower requested work, then lexical intent id. Invalid/stale
    intents fail closed rather than being silently deferred as valid work.
    """
    if type(intents) is not tuple or any(type(item) is not ObserveIntent for item in intents):
        raise PerceptionFabricError("intents must be an immutable tuple of concrete ObserveIntent values")
    if type(policy) is not PerceptionWorkerPolicy:
        raise PerceptionFabricError("policy must be a concrete PerceptionWorkerPolicy")
    if type(permission_snapshots) is not tuple or any(type(item) is not PerceptionCapabilitySnapshot for item in permission_snapshots):
        raise PerceptionFabricError("permission_snapshots must be an immutable tuple of concrete snapshots")
    _nonnegative_int("now_monotonic_ns", now_monotonic_ns)
    ids = [item.intent_id for item in intents]
    if len(ids) != len(set(ids)):
        raise PerceptionFabricError("intent_id must be unique")
    by_source: dict[str, PerceptionCapabilitySnapshot] = {}
    for snapshot in permission_snapshots:
        if snapshot.source_id in by_source:
            raise PerceptionFabricError("exactly one permission snapshot per source is required")
        by_source[snapshot.source_id] = snapshot
    for intent in intents:
        snapshot = by_source.get(intent.source_id)
        if snapshot is None:
            raise PerceptionFabricError(f"missing permission snapshot for source {intent.source_id!r}")
        intent.validate_against(snapshot, now_monotonic_ns=now_monotonic_ns)

    ordered = sorted(intents, key=lambda item: (-item.priority_micros, item.max_work_units, item.intent_id))
    selected: list[ObserveIntent] = []
    deferred: list[ObserveIntent] = []
    remaining_work = policy.max_total_work_units
    for intent in ordered:
        if len(selected) >= policy.max_active_workers or intent.max_work_units > remaining_work:
            deferred.append(intent)
            continue
        selected.append(intent)
        remaining_work -= intent.max_work_units

    provenance: set[str] = set(policy.provenance_refs)
    provenance.add(f"worker-policy-sha256:{policy.sha256()}")
    for intent in intents:
        provenance.update(intent.provenance_refs)
        provenance.add(f"observe-intent-sha256:{intent.sha256()}")
    total = sum(item.max_work_units for item in selected)
    payload = {
        "policy_sha256": policy.sha256(),
        "selected": [item.intent_id for item in selected],
        "deferred": [item.intent_id for item in deferred],
        "total_work_units": total,
        "now_monotonic_ns": now_monotonic_ns,
    }
    allocation_id = "perception-allocation:" + _digest(payload)[:24]
    return PerceptionWorkerAllocation(
        allocation_id=allocation_id,
        policy_sha256=policy.sha256(),
        selected_intent_ids=tuple(item.intent_id for item in selected),
        deferred_intent_ids=tuple(item.intent_id for item in deferred),
        total_work_units=total,
        provenance_refs=tuple(sorted(provenance)),
    )


__all__ = [
    "CAPABILITY_SNAPSHOT_SCHEMA",
    "OBSERVE_INTENT_SCHEMA",
    "PerceptionCapability",
    "PerceptionCapabilitySnapshot",
    "PerceptionFabricError",
    "PerceptionSource",
    "PerceptionWorkerAllocation",
    "PerceptionWorkerPolicy",
    "SOURCE_SCHEMA",
    "SourceKind",
    "WORKER_ALLOCATION_SCHEMA",
    "WORKER_POLICY_SCHEMA",
    "ObserveIntent",
    "allocate_perception_workers",
]
