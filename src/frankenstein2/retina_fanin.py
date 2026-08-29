"""Deterministic permitted-source Retina fan-in planning for F2-WP-707.

This module plans one through four logical Retina worker slots from an exact
caller-supplied permission snapshot. It does not authenticate the caller, open a
sensor, spawn a worker, inspect data, call a model/provider/tool, or persist state.
The caller remains responsible for admitting the permission snapshot through the
canonical user/dashboard authority path.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

PERMISSION_SCHEMA = "FRANKENSTEIN2_RETINA_SOURCE_PERMISSION/v1"
SNAPSHOT_SCHEMA = "FRANKENSTEIN2_RETINA_PERMISSION_SNAPSHOT/v1"
POLICY_SCHEMA = "FRANKENSTEIN2_RETINA_FANIN_POLICY/v1"
SLOT_SCHEMA = "FRANKENSTEIN2_RETINA_WORKER_SLOT/v1"
PLAN_SCHEMA = "FRANKENSTEIN2_RETINA_FANIN_PLAN/v1"

_SOURCE_KINDS = frozenset({"CAMERA", "SCREEN", "PAGE", "USER_ACTIVITY"})
_MAX_PARALLEL_RETINA = 4
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RetinaFanInError(ValueError):
    """Fail-closed error for the WP707 planning boundary."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RetinaFanInError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise RetinaFanInError(f"{name} must not contain control characters")
    return value


def _nonnegative_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise RetinaFanInError(f"{name} must be an integer >= 0")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise RetinaFanInError(f"{name} must be lowercase 64-hex sha256")
    return value


def _refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise RetinaFanInError(f"{name} must be an immutable tuple")
    if not value and not allow_empty:
        raise RetinaFanInError(f"{name} must be non-empty")
    cleaned = tuple(_text(f"{name} item", item) for item in value)
    if len(cleaned) != len(set(cleaned)):
        raise RetinaFanInError(f"{name} must not contain duplicates")
    return cleaned


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RetinaFanInError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class RetinaSourcePermission:
    source_id: str
    source_kind: str
    locator_ref: str
    capture_allowed: bool
    cognition_allowed: bool
    persistence_allowed: bool
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = PERMISSION_SCHEMA
    classification: ClassVar[str] = "CALLER_SUPPLIED_SOURCE_PERMISSION_NOT_SELF_GRANTING_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        if self.source_kind not in _SOURCE_KINDS:
            raise RetinaFanInError("source_kind must be CAMERA, SCREEN, PAGE or USER_ACTIVITY")
        object.__setattr__(self, "locator_ref", _text("locator_ref", self.locator_ref))
        for name in ("capture_allowed", "cognition_allowed", "persistence_allowed"):
            if type(getattr(self, name)) is not bool:
                raise RetinaFanInError(f"{name} must be bool")
        object.__setattr__(self, "provenance_refs", tuple(sorted(_refs("provenance_refs", self.provenance_refs))))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "locator_ref": self.locator_ref,
            "capture_allowed": self.capture_allowed,
            "cognition_allowed": self.cognition_allowed,
            "persistence_allowed": self.persistence_allowed,
            "capture_permission_can_be_broadened_by_other_flags": False,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class RetinaPermissionSnapshot:
    snapshot_id: str
    generation: int
    permission_epoch: str
    permission_authority_ref: str
    permissions: tuple[RetinaSourcePermission, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = SNAPSHOT_SCHEMA
    classification: ClassVar[str] = "EXACT_PERMISSION_SNAPSHOT_INPUT_REQUIRES_EXTERNAL_CANONICAL_ADMISSION"

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", _text("snapshot_id", self.snapshot_id))
        _nonnegative_int("generation", self.generation)
        object.__setattr__(self, "permission_epoch", _text("permission_epoch", self.permission_epoch))
        object.__setattr__(self, "permission_authority_ref", _text("permission_authority_ref", self.permission_authority_ref))
        if type(self.permissions) is not tuple or not self.permissions:
            raise RetinaFanInError("permissions must be a non-empty immutable tuple")
        for item in self.permissions:
            if type(item) is not RetinaSourcePermission:
                raise RetinaFanInError("permissions must contain concrete RetinaSourcePermission instances")
        ordered = tuple(sorted(self.permissions, key=lambda item: item.source_id))
        if len({item.source_id for item in ordered}) != len(ordered):
            raise RetinaFanInError("source_id must be unique within permission snapshot")
        if len({item.locator_ref for item in ordered}) != len(ordered):
            raise RetinaFanInError("locator_ref must be unique within permission snapshot")
        object.__setattr__(self, "permissions", ordered)
        object.__setattr__(self, "provenance_refs", tuple(sorted(_refs("provenance_refs", self.provenance_refs))))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "snapshot_id": self.snapshot_id,
            "generation": self.generation,
            "permission_epoch": self.permission_epoch,
            "permission_authority_ref": self.permission_authority_ref,
            "permissions": [item.as_dict() for item in self.permissions],
            "dashboard_authentication_performed": False,
            "canonical_admission_performed": False,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class RetinaFanInPolicy:
    policy_id: str
    generation: int
    max_parallel_workers: int
    priority_source_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = POLICY_SCHEMA
    classification: ClassVar[str] = "RETINA_FANIN_BUDGET_POLICY_NOT_EXECUTION_OR_PERMISSION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _nonnegative_int("generation", self.generation)
        if type(self.max_parallel_workers) is not int or not 1 <= self.max_parallel_workers <= _MAX_PARALLEL_RETINA:
            raise RetinaFanInError("max_parallel_workers must be an integer in [1, 4]")
        object.__setattr__(self, "priority_source_ids", _refs("priority_source_ids", self.priority_source_ids))
        object.__setattr__(self, "provenance_refs", tuple(sorted(_refs("provenance_refs", self.provenance_refs))))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "max_parallel_workers": self.max_parallel_workers,
            "hard_parallel_worker_ceiling": _MAX_PARALLEL_RETINA,
            "priority_source_ids": list(self.priority_source_ids),
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class RetinaWorkerSlot:
    slot_id: str
    source_id: str
    source_kind: str
    locator_ref: str
    persistence_allowed: bool
    permission_sha256: str

    schema: ClassVar[str] = SLOT_SCHEMA
    classification: ClassVar[str] = "LOGICAL_RETINA_SLOT_PLAN_NOT_RUNNING_WORKER_OR_SENSOR_HANDLE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "slot_id", _text("slot_id", self.slot_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        if self.source_kind not in _SOURCE_KINDS:
            raise RetinaFanInError("unsupported source_kind")
        object.__setattr__(self, "locator_ref", _text("locator_ref", self.locator_ref))
        if type(self.persistence_allowed) is not bool:
            raise RetinaFanInError("persistence_allowed must be bool")
        _sha256("permission_sha256", self.permission_sha256)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "slot_id": self.slot_id,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "locator_ref": self.locator_ref,
            "persistence_allowed": self.persistence_allowed,
            "permission_sha256": self.permission_sha256,
            "worker_running": False,
            "sensor_open": False,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class RetinaFanInPlan:
    plan_id: str
    permission_snapshot_id: str
    permission_snapshot_generation: int
    permission_snapshot_sha256: str
    policy_id: str
    policy_generation: int
    policy_sha256: str
    requested_source_ids: tuple[str, ...]
    worker_slots: tuple[RetinaWorkerSlot, ...]
    deferred_source_ids: tuple[str, ...]
    denied_source_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = PLAN_SCHEMA
    classification: ClassVar[str] = "RETINA_FANIN_PLAN_CANDIDATE_NOT_EXECUTION_SENSOR_EFFECT_OR_COMPLETION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _text("plan_id", self.plan_id))
        object.__setattr__(self, "permission_snapshot_id", _text("permission_snapshot_id", self.permission_snapshot_id))
        _nonnegative_int("permission_snapshot_generation", self.permission_snapshot_generation)
        _sha256("permission_snapshot_sha256", self.permission_snapshot_sha256)
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _nonnegative_int("policy_generation", self.policy_generation)
        _sha256("policy_sha256", self.policy_sha256)
        object.__setattr__(self, "requested_source_ids", tuple(sorted(_refs("requested_source_ids", self.requested_source_ids))))
        if type(self.worker_slots) is not tuple:
            raise RetinaFanInError("worker_slots must be an immutable tuple")
        if len(self.worker_slots) > _MAX_PARALLEL_RETINA:
            raise RetinaFanInError("worker_slots exceeds hard parallel ceiling")
        for slot in self.worker_slots:
            if type(slot) is not RetinaWorkerSlot:
                raise RetinaFanInError("worker_slots must contain concrete RetinaWorkerSlot instances")
        expected_slots = tuple(f"R{i}" for i in range(1, len(self.worker_slots) + 1))
        if tuple(slot.slot_id for slot in self.worker_slots) != expected_slots:
            raise RetinaFanInError("worker slot identities must be canonical R1..Rn")
        if len({slot.source_id for slot in self.worker_slots}) != len(self.worker_slots):
            raise RetinaFanInError("worker slot source identities must be unique")
        for name in ("deferred_source_ids", "denied_source_ids"):
            object.__setattr__(self, name, tuple(sorted(_refs(name, getattr(self, name), allow_empty=True))))
        object.__setattr__(self, "provenance_refs", tuple(sorted(_refs("provenance_refs", self.provenance_refs))))
        partition = {slot.source_id for slot in self.worker_slots} | set(self.deferred_source_ids) | set(self.denied_source_ids)
        if partition != set(self.requested_source_ids):
            raise RetinaFanInError("enabled/deferred/denied partition must exactly cover requested sources")
        if (set(self.deferred_source_ids) & set(self.denied_source_ids)) or ({slot.source_id for slot in self.worker_slots} & (set(self.deferred_source_ids) | set(self.denied_source_ids))):
            raise RetinaFanInError("plan source categories must be disjoint")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "plan_id": self.plan_id,
            "permission_snapshot_id": self.permission_snapshot_id,
            "permission_snapshot_generation": self.permission_snapshot_generation,
            "permission_snapshot_sha256": self.permission_snapshot_sha256,
            "policy_id": self.policy_id,
            "policy_generation": self.policy_generation,
            "policy_sha256": self.policy_sha256,
            "requested_source_ids": list(self.requested_source_ids),
            "worker_slots": [slot.as_dict() for slot in self.worker_slots],
            "deferred_source_ids": list(self.deferred_source_ids),
            "denied_source_ids": list(self.denied_source_ids),
            "planned_parallel_workers": len(self.worker_slots),
            "hard_parallel_worker_ceiling": _MAX_PARALLEL_RETINA,
            "workers_spawned": 0,
            "sensors_opened": 0,
            "permission_broadening": False,
            "runtime_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def build_retina_fanin_plan(
    *,
    plan_id: str,
    permission_snapshot: RetinaPermissionSnapshot,
    expected_permission_snapshot_sha256: str,
    policy: RetinaFanInPolicy,
    expected_policy_sha256: str,
    requested_source_ids: tuple[str, ...],
    provenance_refs: tuple[str, ...],
) -> RetinaFanInPlan:
    """Plan bounded logical Retina slots without opening or executing any source."""
    if type(permission_snapshot) is not RetinaPermissionSnapshot:
        raise RetinaFanInError("permission_snapshot must be a concrete RetinaPermissionSnapshot")
    if type(policy) is not RetinaFanInPolicy:
        raise RetinaFanInError("policy must be a concrete RetinaFanInPolicy")
    _sha256("expected_permission_snapshot_sha256", expected_permission_snapshot_sha256)
    _sha256("expected_policy_sha256", expected_policy_sha256)
    if permission_snapshot.sha256() != expected_permission_snapshot_sha256:
        raise RetinaFanInError("permission snapshot digest mismatch")
    if policy.sha256() != expected_policy_sha256:
        raise RetinaFanInError("policy digest mismatch")

    requested = _refs("requested_source_ids", requested_source_ids)
    requested_set = set(requested)
    permissions = {item.source_id: item for item in permission_snapshot.permissions}
    unknown = requested_set - set(permissions)
    if unknown:
        raise RetinaFanInError("requested source is absent from exact permission snapshot")
    priority_set = set(policy.priority_source_ids)
    if requested_set - priority_set:
        raise RetinaFanInError("every requested source must be present in explicit policy priority order")
    if priority_set - set(permissions):
        raise RetinaFanInError("policy priority contains source absent from permission snapshot")

    ordered_requested = [source_id for source_id in policy.priority_source_ids if source_id in requested_set]
    eligible: list[RetinaSourcePermission] = []
    denied: list[str] = []
    for source_id in ordered_requested:
        permission = permissions[source_id]
        # Hard invariant: cognition/persistence flags never broaden capture permission.
        if not permission.capture_allowed or not permission.cognition_allowed:
            denied.append(source_id)
        else:
            eligible.append(permission)

    selected = eligible[: policy.max_parallel_workers]
    deferred = [item.source_id for item in eligible[policy.max_parallel_workers :]]
    slots = tuple(
        RetinaWorkerSlot(
            slot_id=f"R{index}",
            source_id=permission.source_id,
            source_kind=permission.source_kind,
            locator_ref=permission.locator_ref,
            persistence_allowed=permission.persistence_allowed,
            permission_sha256=permission.sha256(),
        )
        for index, permission in enumerate(selected, start=1)
    )

    all_provenance = set(_refs("provenance_refs", provenance_refs))
    all_provenance.update(permission_snapshot.provenance_refs)
    all_provenance.update(policy.provenance_refs)
    for permission in permission_snapshot.permissions:
        all_provenance.update(permission.provenance_refs)

    return RetinaFanInPlan(
        plan_id=plan_id,
        permission_snapshot_id=permission_snapshot.snapshot_id,
        permission_snapshot_generation=permission_snapshot.generation,
        permission_snapshot_sha256=expected_permission_snapshot_sha256,
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=expected_policy_sha256,
        requested_source_ids=tuple(sorted(requested_set)),
        worker_slots=slots,
        deferred_source_ids=tuple(sorted(deferred)),
        denied_source_ids=tuple(sorted(denied)),
        provenance_refs=tuple(sorted(all_provenance)),
    )
