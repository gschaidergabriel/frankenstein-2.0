"""Deterministic dashboard control/audit plane for the Perception Fabric.

WP713 deliberately reuses :mod:`perception_dashboard_policy` as the single
Frankenstein-level capability policy authority.  This module adds immutable audit
receipts, exact receipt chaining and a headless visibility projection.  It does not
implement a web UI, OS permission acquisition, sensor execution, bridge/network I/O,
raw-frame persistence, provider/VLM calls, world-truth mutation, effects or completion.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, ClassVar

from .perception_dashboard_policy import (
    PerceptionDashboardError,
    PerceptionDashboardState,
    capability_snapshot_from_dashboard,
    set_global_pause,
    set_source_policy,
)
from .perception_fabric import PerceptionCapability, PerceptionCapabilitySnapshot

AUDIT_RECEIPT_SCHEMA = "FRANKENSTEIN2_PERCEPTION_AUDIT_RECEIPT/v1"
AUDIT_CURSOR_SCHEMA = "FRANKENSTEIN2_PERCEPTION_AUDIT_CURSOR/v1"
VISIBILITY_SCHEMA = "FRANKENSTEIN2_PERCEPTION_VISIBILITY/v1"
SOURCE_VISIBILITY_SCHEMA = "FRANKENSTEIN2_PERCEPTION_SOURCE_VISIBILITY/v1"
WORKER_VISIBILITY_SCHEMA = "FRANKENSTEIN2_PERCEPTION_WORKER_VISIBILITY/v1"

BASELINE_HIGH_SENSITIVITY_CAPTURE_EXCLUDED = (
    "CLIPBOARD_CONTENT",
    "PASSWORD_FIELD_CONTENT",
    "RAW_KEYSTROKES",
)


class DashboardAuditAction(str, Enum):
    SET_SOURCE_POLICY = "SET_SOURCE_POLICY"
    REVOKE_CAPABILITIES = "REVOKE_CAPABILITIES"
    SET_GLOBAL_PAUSE = "SET_GLOBAL_PAUSE"
    COMPILE_PERMISSION_SNAPSHOT = "COMPILE_PERMISSION_SNAPSHOT"
    OBSERVATION_EXECUTION = "OBSERVATION_EXECUTION"


class ObservationExecutionResult(str, Enum):
    EXECUTED = "EXECUTED"
    DENIED = "DENIED"
    DROPPED = "DROPPED"


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise PerceptionDashboardError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PerceptionDashboardError(f"{name} must not contain control characters")
    return value


def _nonnegative(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PerceptionDashboardError(f"{name} must be an integer >= 0")
    return value


def _refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple or (not allow_empty and not value):
        suffix = "immutable tuple" if allow_empty else "non-empty immutable tuple"
        raise PerceptionDashboardError(f"{name} must be a {suffix}")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise PerceptionDashboardError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PerceptionDashboardError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _caps(value: Any) -> tuple[PerceptionCapability, ...]:
    if type(value) is not tuple or any(not isinstance(item, PerceptionCapability) for item in value):
        raise PerceptionDashboardError("capabilities must be an immutable tuple of PerceptionCapability values")
    if len(value) != len(set(value)):
        raise PerceptionDashboardError("capabilities must not contain duplicates")
    return tuple(sorted(value, key=lambda item: item.value))


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionAuditCursor:
    """Caller-held append-only audit cursor; no persistence authority is implied."""

    next_sequence: int = 0
    prior_receipt_sha256: str | None = None

    schema: ClassVar[str] = AUDIT_CURSOR_SCHEMA
    classification: ClassVar[str] = "APPEND_ONLY_AUDIT_CURSOR_NOT_CANONICAL_STATE_OR_EFFECT_AUTHORITY"

    def __post_init__(self) -> None:
        _nonnegative("next_sequence", self.next_sequence)
        if self.next_sequence == 0 and self.prior_receipt_sha256 is not None:
            raise PerceptionDashboardError("sequence zero must not have a prior receipt")
        if self.next_sequence > 0:
            prior = _text("prior_receipt_sha256", self.prior_receipt_sha256)
            if len(prior) != 64 or any(ch not in "0123456789abcdef" for ch in prior):
                raise PerceptionDashboardError("prior_receipt_sha256 must be lowercase sha256 hex")


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionAuditReceipt:
    receipt_id: str
    sequence: int
    action: DashboardAuditAction
    actor_id: str
    reason: str
    monotonic_ns: int
    source_id: str | None
    dashboard_generation_before: int
    dashboard_generation_after: int
    dashboard_state_sha256_before: str
    dashboard_state_sha256_after: str
    permission_snapshot_sha256: str | None
    observation_result: ObservationExecutionResult | None
    worker_id: str | None
    prior_receipt_sha256: str | None
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = AUDIT_RECEIPT_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_AUDIT_EVIDENCE_NOT_WORLD_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "receipt_id", _text("receipt_id", self.receipt_id))
        _nonnegative("sequence", self.sequence)
        if not isinstance(self.action, DashboardAuditAction):
            raise PerceptionDashboardError("action must be DashboardAuditAction")
        object.__setattr__(self, "actor_id", _text("actor_id", self.actor_id))
        object.__setattr__(self, "reason", _text("reason", self.reason))
        _nonnegative("monotonic_ns", self.monotonic_ns)
        if self.source_id is not None:
            object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative("dashboard_generation_before", self.dashboard_generation_before)
        _nonnegative("dashboard_generation_after", self.dashboard_generation_after)
        for name, value in (
            ("dashboard_state_sha256_before", self.dashboard_state_sha256_before),
            ("dashboard_state_sha256_after", self.dashboard_state_sha256_after),
        ):
            value = _text(name, value)
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise PerceptionDashboardError(f"{name} must be lowercase sha256 hex")
        if self.permission_snapshot_sha256 is not None:
            value = _text("permission_snapshot_sha256", self.permission_snapshot_sha256)
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise PerceptionDashboardError("permission_snapshot_sha256 must be lowercase sha256 hex")
        if self.observation_result is not None and not isinstance(self.observation_result, ObservationExecutionResult):
            raise PerceptionDashboardError("observation_result must be ObservationExecutionResult")
        if self.worker_id is not None:
            object.__setattr__(self, "worker_id", _text("worker_id", self.worker_id))
        if self.sequence == 0 and self.prior_receipt_sha256 is not None:
            raise PerceptionDashboardError("first receipt must not have prior_receipt_sha256")
        if self.sequence > 0:
            prior = _text("prior_receipt_sha256", self.prior_receipt_sha256)
            if len(prior) != 64 or any(ch not in "0123456789abcdef" for ch in prior):
                raise PerceptionDashboardError("prior_receipt_sha256 must be lowercase sha256 hex")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "receipt_id": self.receipt_id,
            "sequence": self.sequence,
            "action": self.action.value,
            "actor_id": self.actor_id,
            "reason": self.reason,
            "monotonic_ns": self.monotonic_ns,
            "source_id": self.source_id,
            "dashboard_generation_before": self.dashboard_generation_before,
            "dashboard_generation_after": self.dashboard_generation_after,
            "dashboard_state_sha256_before": self.dashboard_state_sha256_before,
            "dashboard_state_sha256_after": self.dashboard_state_sha256_after,
            "permission_snapshot_sha256": self.permission_snapshot_sha256,
            "observation_result": None if self.observation_result is None else self.observation_result.value,
            "worker_id": self.worker_id,
            "prior_receipt_sha256": self.prior_receipt_sha256,
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerVisibility:
    worker_id: str
    source_id: str
    reason: str

    schema: ClassVar[str] = WORKER_VISIBILITY_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "worker_id", _text("worker_id", self.worker_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        object.__setattr__(self, "reason", _text("reason", self.reason))

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "worker_id": self.worker_id, "source_id": self.source_id, "reason": self.reason}


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceVisibility:
    source_id: str
    source_generation: int
    enabled: bool
    capabilities: tuple[PerceptionCapability, ...]
    active_worker_ids: tuple[str, ...]
    reasons: tuple[str, ...]

    schema: ClassVar[str] = SOURCE_VISIBILITY_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative("source_generation", self.source_generation)
        if type(self.enabled) is not bool:
            raise PerceptionDashboardError("enabled must be bool")
        object.__setattr__(self, "capabilities", _caps(self.capabilities))
        object.__setattr__(self, "active_worker_ids", _refs("active_worker_ids", self.active_worker_ids, allow_empty=True))
        object.__setattr__(self, "reasons", _refs("reasons", self.reasons, allow_empty=True))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_id": self.source_id,
            "source_generation": self.source_generation,
            "enabled": self.enabled,
            "capabilities": [item.value for item in self.capabilities],
            "active_worker_ids": list(self.active_worker_ids),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionVisibilitySnapshot:
    dashboard_state_sha256: str
    dashboard_generation: int
    global_pause: bool
    max_active_cortex_workers: int
    sources: tuple[SourceVisibility, ...]
    workers: tuple[WorkerVisibility, ...]
    baseline_high_sensitivity_capture_excluded: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = VISIBILITY_SCHEMA
    classification: ClassVar[str] = "HEADLESS_VISIBILITY_PROJECTION_NOT_POLICY_AUTHORITY_OR_WORLD_TRUTH"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "dashboard_state_sha256": self.dashboard_state_sha256,
            "dashboard_generation": self.dashboard_generation,
            "global_pause": self.global_pause,
            "max_active_cortex_workers": self.max_active_cortex_workers,
            "sources": [item.as_dict() for item in self.sources],
            "workers": [item.as_dict() for item in self.workers],
            "baseline_high_sensitivity_capture_excluded": list(self.baseline_high_sensitivity_capture_excluded),
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _receipt(
    *, cursor: PerceptionAuditCursor, action: DashboardAuditAction, actor_id: str, reason: str,
    monotonic_ns: int, before: PerceptionDashboardState, after: PerceptionDashboardState,
    source_id: str | None = None, permission_snapshot_sha256: str | None = None,
    observation_result: ObservationExecutionResult | None = None, worker_id: str | None = None,
    provenance_refs: tuple[str, ...],
) -> tuple[PerceptionAuditReceipt, PerceptionAuditCursor]:
    if type(cursor) is not PerceptionAuditCursor:
        raise PerceptionDashboardError("cursor must be a concrete PerceptionAuditCursor")
    if type(before) is not PerceptionDashboardState or type(after) is not PerceptionDashboardState:
        raise PerceptionDashboardError("before and after must be concrete PerceptionDashboardState values")
    actor_id = _text("actor_id", actor_id)
    reason = _text("reason", reason)
    _nonnegative("monotonic_ns", monotonic_ns)
    provenance = set(_refs("provenance_refs", provenance_refs))
    provenance.add(f"dashboard-before-sha256:{before.sha256()}")
    provenance.add(f"dashboard-after-sha256:{after.sha256()}")
    if cursor.prior_receipt_sha256 is not None:
        provenance.add(f"prior-audit-receipt-sha256:{cursor.prior_receipt_sha256}")
    identity = {
        "sequence": cursor.next_sequence,
        "action": action.value,
        "actor_id": actor_id,
        "reason": reason,
        "monotonic_ns": monotonic_ns,
        "source_id": source_id,
        "before": before.sha256(),
        "after": after.sha256(),
        "permission_snapshot_sha256": permission_snapshot_sha256,
        "observation_result": None if observation_result is None else observation_result.value,
        "worker_id": worker_id,
        "prior_receipt_sha256": cursor.prior_receipt_sha256,
    }
    receipt = PerceptionAuditReceipt(
        receipt_id="perception-audit:" + _digest(identity)[:24],
        sequence=cursor.next_sequence,
        action=action,
        actor_id=actor_id,
        reason=reason,
        monotonic_ns=monotonic_ns,
        source_id=source_id,
        dashboard_generation_before=before.generation,
        dashboard_generation_after=after.generation,
        dashboard_state_sha256_before=before.sha256(),
        dashboard_state_sha256_after=after.sha256(),
        permission_snapshot_sha256=permission_snapshot_sha256,
        observation_result=observation_result,
        worker_id=worker_id,
        prior_receipt_sha256=cursor.prior_receipt_sha256,
        provenance_refs=tuple(sorted(provenance)),
    )
    return receipt, PerceptionAuditCursor(next_sequence=cursor.next_sequence + 1, prior_receipt_sha256=receipt.sha256())


def apply_source_policy(
    *, state: PerceptionDashboardState, cursor: PerceptionAuditCursor, source_id: str,
    enabled: bool, capabilities: tuple[PerceptionCapability, ...], actor_id: str, reason: str,
    monotonic_ns: int, provenance_refs: tuple[str, ...],
) -> tuple[PerceptionDashboardState, PerceptionAuditReceipt, PerceptionAuditCursor]:
    capabilities = _caps(capabilities)
    after = set_source_policy(
        state=state, source_id=source_id, enabled=enabled, capabilities=capabilities,
        provenance_refs=provenance_refs,
    )
    receipt, next_cursor = _receipt(
        cursor=cursor, action=DashboardAuditAction.SET_SOURCE_POLICY, actor_id=actor_id,
        reason=reason, monotonic_ns=monotonic_ns, before=state, after=after,
        source_id=source_id, provenance_refs=provenance_refs,
    )
    return after, receipt, next_cursor


def revoke_capabilities(
    *, state: PerceptionDashboardState, cursor: PerceptionAuditCursor, source_id: str,
    capabilities: tuple[PerceptionCapability, ...], actor_id: str, reason: str,
    monotonic_ns: int, provenance_refs: tuple[str, ...],
) -> tuple[PerceptionDashboardState, PerceptionAuditReceipt, PerceptionAuditCursor]:
    revoked = set(_caps(capabilities))
    if not revoked:
        raise PerceptionDashboardError("revoke_capabilities requires at least one capability")
    policy = state.policy_for(source_id)
    if policy is None:
        raise PerceptionDashboardError("source has no dashboard policy")
    remaining = tuple(item for item in policy.capabilities if item not in revoked)
    # Preserve dependency closure: removing SEE revokes all; removing ANALYZE also revokes VLM.
    if PerceptionCapability.SEE not in remaining:
        remaining = ()
    elif PerceptionCapability.ANALYZE not in remaining:
        remaining = tuple(item for item in remaining if item is not PerceptionCapability.EXTERNAL_VLM)
    after = set_source_policy(
        state=state, source_id=source_id, enabled=policy.enabled,
        capabilities=remaining, provenance_refs=provenance_refs,
    )
    receipt, next_cursor = _receipt(
        cursor=cursor, action=DashboardAuditAction.REVOKE_CAPABILITIES, actor_id=actor_id,
        reason=reason, monotonic_ns=monotonic_ns, before=state, after=after,
        source_id=source_id, provenance_refs=provenance_refs,
    )
    return after, receipt, next_cursor


def apply_global_pause(
    *, state: PerceptionDashboardState, cursor: PerceptionAuditCursor, paused: bool,
    actor_id: str, reason: str, monotonic_ns: int, provenance_refs: tuple[str, ...],
) -> tuple[PerceptionDashboardState, PerceptionAuditReceipt, PerceptionAuditCursor]:
    after = set_global_pause(state=state, paused=paused, provenance_refs=provenance_refs)
    receipt, next_cursor = _receipt(
        cursor=cursor, action=DashboardAuditAction.SET_GLOBAL_PAUSE, actor_id=actor_id,
        reason=reason, monotonic_ns=monotonic_ns, before=state, after=after,
        provenance_refs=provenance_refs,
    )
    return after, receipt, next_cursor


def compile_permission_snapshot_with_audit(
    *, state: PerceptionDashboardState, cursor: PerceptionAuditCursor, source_id: str,
    valid_from_monotonic_ns: int, expires_monotonic_ns: int | None, actor_id: str,
    reason: str, monotonic_ns: int, provenance_refs: tuple[str, ...],
) -> tuple[PerceptionCapabilitySnapshot, PerceptionAuditReceipt, PerceptionAuditCursor]:
    snapshot = capability_snapshot_from_dashboard(
        state=state, source_id=source_id, valid_from_monotonic_ns=valid_from_monotonic_ns,
        expires_monotonic_ns=expires_monotonic_ns, provenance_refs=provenance_refs,
    )
    receipt, next_cursor = _receipt(
        cursor=cursor, action=DashboardAuditAction.COMPILE_PERMISSION_SNAPSHOT,
        actor_id=actor_id, reason=reason, monotonic_ns=monotonic_ns,
        before=state, after=state, source_id=source_id,
        permission_snapshot_sha256=snapshot.sha256(), provenance_refs=provenance_refs,
    )
    return snapshot, receipt, next_cursor


def record_observation_execution(
    *, state: PerceptionDashboardState, cursor: PerceptionAuditCursor,
    snapshot: PerceptionCapabilitySnapshot, worker_id: str, result: ObservationExecutionResult,
    actor_id: str, reason: str, monotonic_ns: int, provenance_refs: tuple[str, ...],
) -> tuple[PerceptionAuditReceipt, PerceptionAuditCursor]:
    if type(snapshot) is not PerceptionCapabilitySnapshot:
        raise PerceptionDashboardError("snapshot must be a concrete PerceptionCapabilitySnapshot")
    if not isinstance(result, ObservationExecutionResult):
        raise PerceptionDashboardError("result must be ObservationExecutionResult")
    worker_id = _text("worker_id", worker_id)
    current_ref = f"dashboard-state-sha256:{state.sha256()}"
    if current_ref not in snapshot.provenance_refs:
        raise PerceptionDashboardError("permission snapshot is not bound to the current dashboard state")
    if not snapshot.is_valid_at(monotonic_ns):
        raise PerceptionDashboardError("permission snapshot is not valid at observation execution time")
    policy = state.policy_for(snapshot.source_id)
    if policy is None:
        raise PerceptionDashboardError("source has no dashboard policy")
    if result is ObservationExecutionResult.EXECUTED:
        if state.global_pause or not policy.enabled:
            raise PerceptionDashboardError("executed observation cannot be recorded while source is paused or disabled")
        if not snapshot.allows(PerceptionCapability.SEE):
            raise PerceptionDashboardError("executed observation requires SEE in the bound permission snapshot")
    receipt, next_cursor = _receipt(
        cursor=cursor, action=DashboardAuditAction.OBSERVATION_EXECUTION,
        actor_id=actor_id, reason=reason, monotonic_ns=monotonic_ns,
        before=state, after=state, source_id=snapshot.source_id,
        permission_snapshot_sha256=snapshot.sha256(), observation_result=result,
        worker_id=worker_id, provenance_refs=provenance_refs,
    )
    return receipt, next_cursor


def build_visibility_snapshot(
    *, state: PerceptionDashboardState, workers: tuple[WorkerVisibility, ...],
    provenance_refs: tuple[str, ...],
) -> PerceptionVisibilitySnapshot:
    if type(state) is not PerceptionDashboardState:
        raise PerceptionDashboardError("state must be a concrete PerceptionDashboardState")
    if type(workers) is not tuple or any(type(item) is not WorkerVisibility for item in workers):
        raise PerceptionDashboardError("workers must be an immutable tuple of concrete WorkerVisibility values")
    ids = [item.worker_id for item in workers]
    if len(ids) != len(set(ids)):
        raise PerceptionDashboardError("worker_id must be unique")
    if len(workers) > state.max_active_cortex_workers:
        raise PerceptionDashboardError("active workers exceed dashboard max_active_cortex_workers")
    if state.global_pause and workers:
        raise PerceptionDashboardError("global pause requires zero active workers in visibility")
    policies = {item.source_id: item for item in state.source_policies}
    for worker in workers:
        policy = policies.get(worker.source_id)
        if policy is None:
            raise PerceptionDashboardError("worker references an unknown source")
        if not policy.enabled:
            raise PerceptionDashboardError("worker references a disabled source")
    source_views = []
    for policy in state.source_policies:
        source_workers = tuple(sorted(item.worker_id for item in workers if item.source_id == policy.source_id))
        reasons = tuple(sorted({item.reason for item in workers if item.source_id == policy.source_id}))
        source_views.append(SourceVisibility(
            source_id=policy.source_id,
            source_generation=policy.generation,
            enabled=policy.enabled,
            capabilities=policy.capabilities if not state.global_pause else (),
            active_worker_ids=source_workers,
            reasons=reasons,
        ))
    provenance = set(_refs("provenance_refs", provenance_refs))
    provenance.update(state.provenance_refs)
    provenance.add(f"dashboard-state-sha256:{state.sha256()}")
    return PerceptionVisibilitySnapshot(
        dashboard_state_sha256=state.sha256(),
        dashboard_generation=state.generation,
        global_pause=state.global_pause,
        max_active_cortex_workers=state.max_active_cortex_workers,
        sources=tuple(source_views),
        workers=tuple(sorted(workers, key=lambda item: item.worker_id)),
        baseline_high_sensitivity_capture_excluded=BASELINE_HIGH_SENSITIVITY_CAPTURE_EXCLUDED,
        provenance_refs=tuple(sorted(provenance)),
    )


__all__ = [
    "AUDIT_CURSOR_SCHEMA",
    "AUDIT_RECEIPT_SCHEMA",
    "BASELINE_HIGH_SENSITIVITY_CAPTURE_EXCLUDED",
    "DashboardAuditAction",
    "ObservationExecutionResult",
    "PerceptionAuditCursor",
    "PerceptionAuditReceipt",
    "PerceptionVisibilitySnapshot",
    "SourceVisibility",
    "WorkerVisibility",
    "apply_global_pause",
    "apply_source_policy",
    "build_visibility_snapshot",
    "compile_permission_snapshot_with_audit",
    "record_observation_execution",
    "revoke_capabilities",
]
