"""Deterministic VisualNeed -> ObserveIntent binding for F2-WP-708.

This module is intentionally hardware-independent.  It compiles a bounded visual
need against an exact immutable WP707 permission snapshot and can later revalidate
that binding against the *current* snapshot before capture/analysis begins.

It never opens a source, spawns a worker, persists sensor payloads, invokes a VLM,
bridges bytes, mutates canonical world state, authorizes effects, or marks work
complete.  Rights that the currently admitted WP707 snapshot cannot prove
(RAW_RETENTION, REMOTE_FRAME, EXTERNAL_VLM) fail closed instead of being inferred.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

from frankenstein2.retina_fanin import RetinaPermissionSnapshot, RetinaSourcePermission

VISUAL_NEED_SCHEMA = "FRANKENSTEIN2_VISUAL_NEED/v1"
OBSERVE_INTENT_SCHEMA = "FRANKENSTEIN2_OBSERVE_INTENT/v1"
EXECUTION_CHECK_SCHEMA = "FRANKENSTEIN2_OBSERVE_INTENT_EXECUTION_CHECK/v1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_PRIORITY = 100


class ObserveIntentError(ValueError):
    """Fail-closed error for the WP708 sensing-request boundary."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ObserveIntentError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ObserveIntentError(f"{name} must not contain control characters")
    return value


def _optional_text(name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _text(name, value)


def _nonnegative_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ObserveIntentError(f"{name} must be an integer >= 0")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise ObserveIntentError(f"{name} must be an integer > 0")
    return value


def _bool(name: str, value: Any) -> bool:
    if type(value) is not bool:
        raise ObserveIntentError(f"{name} must be bool")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ObserveIntentError(f"{name} must be lowercase 64-hex sha256")
    return value


def _refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise ObserveIntentError(f"{name} must be an immutable tuple")
    if not value and not allow_empty:
        raise ObserveIntentError(f"{name} must be non-empty")
    cleaned = tuple(_text(f"{name} item", item) for item in value)
    if len(cleaned) != len(set(cleaned)):
        raise ObserveIntentError(f"{name} must not contain duplicates")
    return tuple(sorted(cleaned))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ObserveIntentError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _permission_for_source(snapshot: RetinaPermissionSnapshot, source_id: str) -> RetinaSourcePermission:
    for permission in snapshot.permissions:
        if permission.source_id == source_id:
            return permission
    raise ObserveIntentError("source_id absent from exact permission snapshot")


@dataclass(frozen=True, slots=True, kw_only=True)
class VisualNeed:
    """Bounded top-down request for new visual/perceptual evidence."""

    need_id: str
    cycle_id: str
    generation: int
    source_id: str
    roi_ref: str | None
    requested_head_ids: tuple[str, ...]
    target_world_atom_ids: tuple[str, ...]
    reason_refs: tuple[str, ...]
    max_age_ms: int
    deadline_monotonic_ns: int
    priority: int
    max_compute_ms: int
    memory_write_requested: bool
    raw_payload_requested: bool
    remote_frame_requested: bool
    external_vlm_requested: bool
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = VISUAL_NEED_SCHEMA
    classification: ClassVar[str] = "CANDIDATE_SENSING_NEED_NOT_EXECUTION_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "need_id", _text("need_id", self.need_id))
        object.__setattr__(self, "cycle_id", _text("cycle_id", self.cycle_id))
        _nonnegative_int("generation", self.generation)
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        object.__setattr__(self, "roi_ref", _optional_text("roi_ref", self.roi_ref))
        object.__setattr__(self, "requested_head_ids", _refs("requested_head_ids", self.requested_head_ids))
        object.__setattr__(self, "target_world_atom_ids", _refs("target_world_atom_ids", self.target_world_atom_ids, allow_empty=True))
        object.__setattr__(self, "reason_refs", _refs("reason_refs", self.reason_refs))
        _positive_int("max_age_ms", self.max_age_ms)
        _positive_int("deadline_monotonic_ns", self.deadline_monotonic_ns)
        if type(self.priority) is not int or not 0 <= self.priority <= _MAX_PRIORITY:
            raise ObserveIntentError(f"priority must be an integer in [0, {_MAX_PRIORITY}]")
        _positive_int("max_compute_ms", self.max_compute_ms)
        for name in (
            "memory_write_requested",
            "raw_payload_requested",
            "remote_frame_requested",
            "external_vlm_requested",
        ):
            _bool(name, getattr(self, name))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "need_id": self.need_id,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "source_id": self.source_id,
            "roi_ref": self.roi_ref,
            "requested_head_ids": list(self.requested_head_ids),
            "target_world_atom_ids": list(self.target_world_atom_ids),
            "reason_refs": list(self.reason_refs),
            "max_age_ms": self.max_age_ms,
            "deadline_monotonic_ns": self.deadline_monotonic_ns,
            "priority": self.priority,
            "max_compute_ms": self.max_compute_ms,
            "memory_write_requested": self.memory_write_requested,
            "raw_payload_requested": self.raw_payload_requested,
            "remote_frame_requested": self.remote_frame_requested,
            "external_vlm_requested": self.external_vlm_requested,
            "capture_performed": False,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class ObserveIntent:
    """Immutable sensing candidate bound to one exact permission snapshot."""

    intent_id: str
    need_id: str
    need_sha256: str
    cycle_id: str
    generation: int
    source_id: str
    source_kind: str
    locator_ref: str
    permission_snapshot_id: str
    permission_snapshot_generation: int
    permission_snapshot_sha256: str
    source_permission_sha256: str
    roi_ref: str | None
    requested_head_ids: tuple[str, ...]
    target_world_atom_ids: tuple[str, ...]
    reason_refs: tuple[str, ...]
    max_age_ms: int
    admitted_monotonic_ns: int
    deadline_monotonic_ns: int
    priority: int
    max_compute_ms: int
    memory_write_allowed: bool
    raw_payload_allowed: bool
    remote_frame_allowed: bool
    external_vlm_allowed: bool
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = OBSERVE_INTENT_SCHEMA
    classification: ClassVar[str] = "CANDIDATE_OBSERVE_INTENT_NOT_CAPTURE_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_id", _text("intent_id", self.intent_id))
        object.__setattr__(self, "need_id", _text("need_id", self.need_id))
        _sha256("need_sha256", self.need_sha256)
        object.__setattr__(self, "cycle_id", _text("cycle_id", self.cycle_id))
        _nonnegative_int("generation", self.generation)
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        object.__setattr__(self, "source_kind", _text("source_kind", self.source_kind))
        object.__setattr__(self, "locator_ref", _text("locator_ref", self.locator_ref))
        object.__setattr__(self, "permission_snapshot_id", _text("permission_snapshot_id", self.permission_snapshot_id))
        _nonnegative_int("permission_snapshot_generation", self.permission_snapshot_generation)
        _sha256("permission_snapshot_sha256", self.permission_snapshot_sha256)
        _sha256("source_permission_sha256", self.source_permission_sha256)
        object.__setattr__(self, "roi_ref", _optional_text("roi_ref", self.roi_ref))
        object.__setattr__(self, "requested_head_ids", _refs("requested_head_ids", self.requested_head_ids))
        object.__setattr__(self, "target_world_atom_ids", _refs("target_world_atom_ids", self.target_world_atom_ids, allow_empty=True))
        object.__setattr__(self, "reason_refs", _refs("reason_refs", self.reason_refs))
        _positive_int("max_age_ms", self.max_age_ms)
        _nonnegative_int("admitted_monotonic_ns", self.admitted_monotonic_ns)
        _positive_int("deadline_monotonic_ns", self.deadline_monotonic_ns)
        if self.deadline_monotonic_ns <= self.admitted_monotonic_ns:
            raise ObserveIntentError("deadline_monotonic_ns must be after admitted_monotonic_ns")
        if type(self.priority) is not int or not 0 <= self.priority <= _MAX_PRIORITY:
            raise ObserveIntentError(f"priority must be an integer in [0, {_MAX_PRIORITY}]")
        _positive_int("max_compute_ms", self.max_compute_ms)
        for name in (
            "memory_write_allowed",
            "raw_payload_allowed",
            "remote_frame_allowed",
            "external_vlm_allowed",
        ):
            _bool(name, getattr(self, name))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "intent_id": self.intent_id,
            "need_id": self.need_id,
            "need_sha256": self.need_sha256,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "locator_ref": self.locator_ref,
            "permission_snapshot_id": self.permission_snapshot_id,
            "permission_snapshot_generation": self.permission_snapshot_generation,
            "permission_snapshot_sha256": self.permission_snapshot_sha256,
            "source_permission_sha256": self.source_permission_sha256,
            "roi_ref": self.roi_ref,
            "requested_head_ids": list(self.requested_head_ids),
            "target_world_atom_ids": list(self.target_world_atom_ids),
            "reason_refs": list(self.reason_refs),
            "max_age_ms": self.max_age_ms,
            "admitted_monotonic_ns": self.admitted_monotonic_ns,
            "deadline_monotonic_ns": self.deadline_monotonic_ns,
            "priority": self.priority,
            "max_compute_ms": self.max_compute_ms,
            "memory_write_allowed": self.memory_write_allowed,
            "raw_payload_allowed": self.raw_payload_allowed,
            "remote_frame_allowed": self.remote_frame_allowed,
            "external_vlm_allowed": self.external_vlm_allowed,
            "capture_performed": False,
            "analysis_performed": False,
            "bridge_transfer_performed": False,
            "external_vlm_invoked": False,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class ObserveIntentExecutionCheck:
    """Deterministic validation result; still not a sensor/device execution token."""

    intent_id: str
    intent_sha256: str
    source_id: str
    current_permission_snapshot_sha256: str
    current_source_permission_sha256: str
    checked_monotonic_ns: int
    capture_allowed: bool
    cognition_allowed: bool
    memory_write_allowed: bool
    raw_payload_allowed: bool
    remote_frame_allowed: bool
    external_vlm_allowed: bool

    schema: ClassVar[str] = EXECUTION_CHECK_SCHEMA
    classification: ClassVar[str] = "VALIDATED_PERMISSION_BINDING_NOT_CAPTURE_EFFECT_OR_COMPLETION_AUTHORITY"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "intent_id": self.intent_id,
            "intent_sha256": self.intent_sha256,
            "source_id": self.source_id,
            "current_permission_snapshot_sha256": self.current_permission_snapshot_sha256,
            "current_source_permission_sha256": self.current_source_permission_sha256,
            "checked_monotonic_ns": self.checked_monotonic_ns,
            "capture_allowed": self.capture_allowed,
            "cognition_allowed": self.cognition_allowed,
            "memory_write_allowed": self.memory_write_allowed,
            "raw_payload_allowed": self.raw_payload_allowed,
            "remote_frame_allowed": self.remote_frame_allowed,
            "external_vlm_allowed": self.external_vlm_allowed,
            "execution_performed": False,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def build_observe_intent(
    *,
    intent_id: str,
    visual_need: VisualNeed,
    permission_snapshot: RetinaPermissionSnapshot,
    expected_permission_snapshot_sha256: str,
    admitted_monotonic_ns: int,
    provenance_refs: tuple[str, ...],
) -> ObserveIntent:
    """Compile a VisualNeed into an immutable candidate ObserveIntent."""
    if type(visual_need) is not VisualNeed:
        raise ObserveIntentError("visual_need must be a concrete VisualNeed")
    if type(permission_snapshot) is not RetinaPermissionSnapshot:
        raise ObserveIntentError("permission_snapshot must be a concrete RetinaPermissionSnapshot")
    _sha256("expected_permission_snapshot_sha256", expected_permission_snapshot_sha256)
    _nonnegative_int("admitted_monotonic_ns", admitted_monotonic_ns)
    if permission_snapshot.sha256() != expected_permission_snapshot_sha256:
        raise ObserveIntentError("permission snapshot digest mismatch")
    if admitted_monotonic_ns >= visual_need.deadline_monotonic_ns:
        raise ObserveIntentError("VisualNeed is expired at ObserveIntent admission")

    permission = _permission_for_source(permission_snapshot, visual_need.source_id)
    if not permission.capture_allowed:
        raise ObserveIntentError("source capture permission is denied")
    if not permission.cognition_allowed:
        raise ObserveIntentError("source cognition permission is denied")
    if visual_need.memory_write_requested and not permission.persistence_allowed:
        raise ObserveIntentError("memory write requested but source persistence permission is denied")

    # WP707 currently proves capture/cognition/persistence only.  The broader
    # Perception Fabric names RAW_RETENTION, REMOTE_FRAME and EXTERNAL_VLM as
    # separate capabilities; until an admitted snapshot represents them, they
    # must not be inferred from capture/cognition/persistence.
    if visual_need.raw_payload_requested:
        raise ObserveIntentError("RAW_RETENTION capability is not proven by current permission snapshot")
    if visual_need.remote_frame_requested:
        raise ObserveIntentError("REMOTE_FRAME capability is not proven by current permission snapshot")
    if visual_need.external_vlm_requested:
        raise ObserveIntentError("EXTERNAL_VLM capability is not proven by current permission snapshot")

    return ObserveIntent(
        intent_id=_text("intent_id", intent_id),
        need_id=visual_need.need_id,
        need_sha256=visual_need.sha256(),
        cycle_id=visual_need.cycle_id,
        generation=visual_need.generation,
        source_id=permission.source_id,
        source_kind=permission.source_kind,
        locator_ref=permission.locator_ref,
        permission_snapshot_id=permission_snapshot.snapshot_id,
        permission_snapshot_generation=permission_snapshot.generation,
        permission_snapshot_sha256=expected_permission_snapshot_sha256,
        source_permission_sha256=permission.sha256(),
        roi_ref=visual_need.roi_ref,
        requested_head_ids=visual_need.requested_head_ids,
        target_world_atom_ids=visual_need.target_world_atom_ids,
        reason_refs=visual_need.reason_refs,
        max_age_ms=visual_need.max_age_ms,
        admitted_monotonic_ns=admitted_monotonic_ns,
        deadline_monotonic_ns=visual_need.deadline_monotonic_ns,
        priority=visual_need.priority,
        max_compute_ms=visual_need.max_compute_ms,
        memory_write_allowed=visual_need.memory_write_requested,
        raw_payload_allowed=False,
        remote_frame_allowed=False,
        external_vlm_allowed=False,
        provenance_refs=tuple(sorted(set(visual_need.provenance_refs) | set(_refs("provenance_refs", provenance_refs)))),
    )


def validate_observe_intent_for_execution(
    *,
    intent: ObserveIntent,
    current_permission_snapshot: RetinaPermissionSnapshot,
    expected_current_permission_snapshot_sha256: str,
    checked_monotonic_ns: int,
) -> ObserveIntentExecutionCheck:
    """Revalidate an ObserveIntent immediately before capture/analysis execution.

    Exact snapshot equality is deliberate: a newer snapshot, even one that appears
    semantically equivalent, requires explicit replanning so queued work cannot
    revive stale authority after revoke/rebind/reconnect.
    """
    if type(intent) is not ObserveIntent:
        raise ObserveIntentError("intent must be a concrete ObserveIntent")
    if type(current_permission_snapshot) is not RetinaPermissionSnapshot:
        raise ObserveIntentError("current_permission_snapshot must be a concrete RetinaPermissionSnapshot")
    _sha256("expected_current_permission_snapshot_sha256", expected_current_permission_snapshot_sha256)
    _nonnegative_int("checked_monotonic_ns", checked_monotonic_ns)
    actual_current_digest = current_permission_snapshot.sha256()
    if actual_current_digest != expected_current_permission_snapshot_sha256:
        raise ObserveIntentError("current permission snapshot digest mismatch")
    if checked_monotonic_ns >= intent.deadline_monotonic_ns:
        raise ObserveIntentError("ObserveIntent expired before execution")
    if current_permission_snapshot.snapshot_id != intent.permission_snapshot_id:
        raise ObserveIntentError("permission snapshot identity changed; replan required")
    if current_permission_snapshot.generation != intent.permission_snapshot_generation:
        raise ObserveIntentError("permission snapshot generation changed; replan required")
    if actual_current_digest != intent.permission_snapshot_sha256:
        raise ObserveIntentError("permission snapshot changed; stale ObserveIntent rejected")

    permission = _permission_for_source(current_permission_snapshot, intent.source_id)
    if permission.sha256() != intent.source_permission_sha256:
        raise ObserveIntentError("source permission changed; stale ObserveIntent rejected")
    if not permission.capture_allowed:
        raise ObserveIntentError("source capture permission was revoked")
    if not permission.cognition_allowed:
        raise ObserveIntentError("source cognition permission was revoked")
    if intent.memory_write_allowed and not permission.persistence_allowed:
        raise ObserveIntentError("source persistence permission was revoked")
    if intent.raw_payload_allowed or intent.remote_frame_allowed or intent.external_vlm_allowed:
        raise ObserveIntentError("intent contains capability not provable by current WP707 snapshot")

    return ObserveIntentExecutionCheck(
        intent_id=intent.intent_id,
        intent_sha256=intent.sha256(),
        source_id=intent.source_id,
        current_permission_snapshot_sha256=actual_current_digest,
        current_source_permission_sha256=permission.sha256(),
        checked_monotonic_ns=checked_monotonic_ns,
        capture_allowed=True,
        cognition_allowed=True,
        memory_write_allowed=intent.memory_write_allowed,
        raw_payload_allowed=False,
        remote_frame_allowed=False,
        external_vlm_allowed=False,
    )
