"""Deterministic host transition planning for Frankenstein 2.0.

F2-WP-1109 generation 1. Plan-only: no filesystem/host mutation, no provider
calls, no UnifiedDB mutation, no effects, and no physical-host completion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any, Iterable

TRANSITION_REQUEST_SCHEMA = "FRANKENSTEIN2_HOST_TRANSITION_REQUEST/v1"
TRANSITION_PLAN_SCHEMA = "FRANKENSTEIN2_HOST_TRANSITION_PLAN/v1"
STATE_BINDING_SCHEMA = "FRANKENSTEIN2_HOST_STATE_BINDING/v1"
HOST_ROUTE_SCHEMA = "FRANKENSTEIN2_HOST_ROUTE_EVIDENCE/v1"

OP_DISABLE = "DISABLE_ADAPTER"
OP_UNINSTALL = "UNINSTALL_ADAPTER"
OP_WITHDRAW_PERMISSIONS = "WITHDRAW_PERMISSIONS"
OP_SWITCH_HOST = "SWITCH_HOST"
OP_REENABLE = "REENABLE_ADAPTER"
_ALLOWED_OPERATIONS = frozenset({OP_DISABLE, OP_UNINSTALL, OP_WITHDRAW_PERMISSIONS, OP_SWITCH_HOST, OP_REENABLE})

ROUTE_NATIVE = "NATIVE"
ROUTE_ADAPTED = "ADAPTED"
ROUTE_DEGRADED = "DEGRADED"
ROUTE_BLOCKED = "BLOCKED"
_ALLOWED_ROUTE_STATUSES = frozenset({ROUTE_NATIVE, ROUTE_ADAPTED, ROUTE_DEGRADED, ROUTE_BLOCKED})
_SWITCHABLE_ROUTE_STATUSES = frozenset({ROUTE_NATIVE, ROUTE_ADAPTED})
STATE_CANONICAL_DURABLE = "CANONICAL_DURABLE"

STEP_FREEZE = "FREEZE_TRANSITION_INPUT"
STEP_WITHDRAW = "APPLY_PERMISSION_WITHDRAWAL"
STEP_DISABLE = "DISABLE_SOURCE_ADAPTER"
STEP_UNINSTALL = "REMOVE_SOURCE_ADAPTER_CODE"
STEP_VERIFY_SUCCESSOR = "VERIFY_SUCCESSOR_ROUTE"
STEP_BIND_SUCCESSOR = "BIND_SUCCESSOR_TO_EXISTING_STATE_LINEAGE"
STEP_READBACK = "READBACK_EXISTING_STATE_LINEAGE"
STEP_REENABLE = "REENABLE_SOURCE_ADAPTER"
STEP_RETAIN_STATE = "RETAIN_CANONICAL_STATE"
STEP_RECORD = "RECORD_TRANSITION_RECEIPT_CANDIDATE"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_TRANSIENT_PREFIXES = (PurePosixPath("/tmp"), PurePosixPath("/var/tmp"), PurePosixPath("/run"), PurePosixPath("/dev/shm"))


class HostTransitionError(ValueError):
    """Fail-closed host transition planning error."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HostTransitionError(f"{name} must be a non-empty already-trimmed string")
    if len(value) > _MAX_TEXT:
        raise HostTransitionError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise HostTransitionError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise HostTransitionError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise HostTransitionError(f"{name} must be a non-negative integer")
    return value


def _absolute_path(name: str, value: Any) -> str:
    value = _text(name, value)
    if not value.startswith("/"):
        raise HostTransitionError(f"{name} must be an absolute POSIX path")
    parsed = PurePosixPath(value)
    if str(parsed) != value or ".." in parsed.parts:
        raise HostTransitionError(f"{name} must already be normalized")
    return value


def _is_transient(path: str) -> bool:
    parsed = PurePosixPath(path)
    if ".cache" in parsed.parts:
        return True
    return any(parsed == prefix or prefix in parsed.parents for prefix in _TRANSIENT_PREFIXES)


def _canonical_permissions(values: Iterable[str]) -> tuple[str, ...]:
    raw = tuple(values)
    normalized = tuple(sorted({_text("permission", item) for item in raw}))
    if len(normalized) != len(raw):
        raise HostTransitionError("permissions must be unique")
    return normalized


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CanonicalStateBinding:
    schema: str
    lineage_id: str
    generation: int
    state_sha256: str
    root_path: str
    storage_class: str = STATE_CANONICAL_DURABLE

    def __post_init__(self) -> None:
        if self.schema != STATE_BINDING_SCHEMA:
            raise HostTransitionError("state binding schema mismatch")
        object.__setattr__(self, "lineage_id", _text("lineage_id", self.lineage_id))
        object.__setattr__(self, "generation", _generation("generation", self.generation))
        object.__setattr__(self, "state_sha256", _sha256("state_sha256", self.state_sha256))
        object.__setattr__(self, "root_path", _absolute_path("root_path", self.root_path))
        if self.storage_class != STATE_CANONICAL_DURABLE:
            raise HostTransitionError("canonical state must use CANONICAL_DURABLE storage class")
        if _is_transient(self.root_path):
            raise HostTransitionError("canonical state root cannot be transient or cache-like")

    @classmethod
    def create(cls, *, lineage_id: str, generation: int, state_sha256: str, root_path: str) -> "CanonicalStateBinding":
        return cls(schema=STATE_BINDING_SCHEMA, lineage_id=lineage_id, generation=generation, state_sha256=state_sha256, root_path=root_path)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class HostRouteEvidence:
    schema: str
    host_id: str
    route_id: str
    route_status: str
    capability_evidence_ref: str
    lifecycle_firing_evidence_ref: str | None
    state_readback_evidence_ref: str | None
    state_readback_lineage_id: str | None = None
    state_readback_generation: int | None = None
    state_readback_state_sha256: str | None = None
    state_readback_binding_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.schema != HOST_ROUTE_SCHEMA:
            raise HostTransitionError("host route schema mismatch")
        object.__setattr__(self, "host_id", _text("host_id", self.host_id))
        object.__setattr__(self, "route_id", _text("route_id", self.route_id))
        if self.route_status not in _ALLOWED_ROUTE_STATUSES:
            raise HostTransitionError(f"unsupported route status: {self.route_status!r}")
        object.__setattr__(self, "capability_evidence_ref", _text("capability_evidence_ref", self.capability_evidence_ref))
        for field_name in ("lifecycle_firing_evidence_ref", "state_readback_evidence_ref"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _text(field_name, value))
        typed_state_fields = (
            self.state_readback_lineage_id,
            self.state_readback_generation,
            self.state_readback_state_sha256,
            self.state_readback_binding_sha256,
        )
        if any(value is not None for value in typed_state_fields):
            if any(value is None for value in typed_state_fields):
                raise HostTransitionError("state readback identity must be complete")
            object.__setattr__(
                self,
                "state_readback_lineage_id",
                _text("state_readback_lineage_id", self.state_readback_lineage_id),
            )
            object.__setattr__(
                self,
                "state_readback_generation",
                _generation("state_readback_generation", self.state_readback_generation),
            )
            object.__setattr__(
                self,
                "state_readback_state_sha256",
                _sha256("state_readback_state_sha256", self.state_readback_state_sha256),
            )
            object.__setattr__(
                self,
                "state_readback_binding_sha256",
                _sha256("state_readback_binding_sha256", self.state_readback_binding_sha256),
            )

    @classmethod
    def create(
        cls,
        *,
        host_id: str,
        route_id: str,
        route_status: str,
        capability_evidence_ref: str,
        lifecycle_firing_evidence_ref: str | None = None,
        state_readback_evidence_ref: str | None = None,
        state_readback_lineage_id: str | None = None,
        state_readback_generation: int | None = None,
        state_readback_state_sha256: str | None = None,
        state_readback_binding_sha256: str | None = None,
    ) -> "HostRouteEvidence":
        return cls(
            schema=HOST_ROUTE_SCHEMA,
            host_id=host_id,
            route_id=route_id,
            route_status=route_status,
            capability_evidence_ref=capability_evidence_ref,
            lifecycle_firing_evidence_ref=lifecycle_firing_evidence_ref,
            state_readback_evidence_ref=state_readback_evidence_ref,
            state_readback_lineage_id=state_readback_lineage_id,
            state_readback_generation=state_readback_generation,
            state_readback_state_sha256=state_readback_state_sha256,
            state_readback_binding_sha256=state_readback_binding_sha256,
        )

    def assert_ready(self, *, role: str, state: CanonicalStateBinding) -> None:
        if self.route_status not in _SWITCHABLE_ROUTE_STATUSES:
            raise HostTransitionError(f"{role} route must be NATIVE or ADAPTED")
        if self.lifecycle_firing_evidence_ref is None:
            raise HostTransitionError(f"{role} route lacks lifecycle firing evidence")
        if self.state_readback_evidence_ref is None:
            raise HostTransitionError(f"{role} route lacks durable state readback evidence")
        if type(state) is not CanonicalStateBinding:
            raise HostTransitionError(f"{role} state must be exact CanonicalStateBinding")
        state = CanonicalStateBinding(**state.as_dict())
        if any(
            value is None
            for value in (
                self.state_readback_lineage_id,
                self.state_readback_generation,
                self.state_readback_state_sha256,
                self.state_readback_binding_sha256,
            )
        ):
            raise HostTransitionError(f"{role} route lacks typed durable state readback identity")
        if self.state_readback_lineage_id != state.lineage_id:
            raise HostTransitionError(f"{role} state readback lineage mismatch")
        if self.state_readback_generation != state.generation:
            raise HostTransitionError(f"{role} state readback generation mismatch")
        if self.state_readback_state_sha256 != state.state_sha256:
            raise HostTransitionError(f"{role} state readback state digest mismatch")
        if self.state_readback_binding_sha256 != state.sha256():
            raise HostTransitionError(f"{role} state readback binding digest mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HostTransitionRequest:
    schema: str
    transition_id: str
    operation: str
    source_host_id: str
    source_route_id: str
    state: CanonicalStateBinding
    expected_state_binding_sha256: str
    permissions_before: tuple[str, ...]
    permissions_after: tuple[str, ...]
    successor_route: HostRouteEvidence | None = None
    rollback_route: HostRouteEvidence | None = None
    destructive_state_authority_ref: str | None = None

    def __post_init__(self) -> None:
        if self.schema != TRANSITION_REQUEST_SCHEMA:
            raise HostTransitionError("transition request schema mismatch")
        object.__setattr__(self, "transition_id", _text("transition_id", self.transition_id))
        if self.operation not in _ALLOWED_OPERATIONS:
            raise HostTransitionError(f"unsupported operation: {self.operation!r}")
        object.__setattr__(self, "source_host_id", _text("source_host_id", self.source_host_id))
        object.__setattr__(self, "source_route_id", _text("source_route_id", self.source_route_id))
        if type(self.state) is not CanonicalStateBinding:
            raise HostTransitionError("state must be exact CanonicalStateBinding")
        state = CanonicalStateBinding(**self.state.as_dict())
        object.__setattr__(self, "state", state)
        if _sha256("expected_state_binding_sha256", self.expected_state_binding_sha256) != state.sha256():
            raise HostTransitionError("state binding digest fence mismatch")
        before = _canonical_permissions(self.permissions_before)
        after = _canonical_permissions(self.permissions_after)
        object.__setattr__(self, "permissions_before", before)
        object.__setattr__(self, "permissions_after", after)
        if not set(after).issubset(before):
            raise HostTransitionError("host transition cannot expand permissions")
        if self.destructive_state_authority_ref is not None:
            raise HostTransitionError("this workpackage has no authority to delete or retire canonical state")
        successor = self.successor_route
        if successor is not None:
            if type(successor) is not HostRouteEvidence:
                raise HostTransitionError("successor_route must be exact HostRouteEvidence")
            successor = HostRouteEvidence(**successor.as_dict())
            object.__setattr__(self, "successor_route", successor)
        rollback = self.rollback_route
        if rollback is not None:
            if type(rollback) is not HostRouteEvidence:
                raise HostTransitionError("rollback_route must be exact HostRouteEvidence")
            rollback = HostRouteEvidence(**rollback.as_dict())
            object.__setattr__(self, "rollback_route", rollback)

        if self.operation == OP_SWITCH_HOST:
            if successor is None:
                raise HostTransitionError("SWITCH_HOST requires successor_route")
            if successor.host_id == self.source_host_id:
                raise HostTransitionError("successor host must differ from source host")
            successor.assert_ready(role="successor", state=state)
        elif successor is not None:
            raise HostTransitionError("successor_route is only valid for SWITCH_HOST")

        if self.operation == OP_WITHDRAW_PERMISSIONS:
            if before == after:
                raise HostTransitionError("WITHDRAW_PERMISSIONS must remove at least one permission")
        elif before != after:
            raise HostTransitionError("permission changes require explicit WITHDRAW_PERMISSIONS operation")

        if self.operation == OP_REENABLE:
            if rollback is None:
                raise HostTransitionError("REENABLE_ADAPTER requires rollback_route evidence")
            rollback.assert_ready(role="rollback", state=state)
        if rollback is not None:
            if rollback.host_id != self.source_host_id:
                raise HostTransitionError("rollback route must bind the source host identity")
            if rollback.route_id != self.source_route_id:
                raise HostTransitionError("rollback route must bind the source route identity")

    @classmethod
    def create(cls, *, transition_id: str, operation: str, source_host_id: str, source_route_id: str, state: CanonicalStateBinding, permissions_before: Iterable[str], permissions_after: Iterable[str], successor_route: HostRouteEvidence | None = None, rollback_route: HostRouteEvidence | None = None, destructive_state_authority_ref: str | None = None) -> "HostTransitionRequest":
        return cls(schema=TRANSITION_REQUEST_SCHEMA, transition_id=transition_id, operation=operation, source_host_id=source_host_id, source_route_id=source_route_id, state=state, expected_state_binding_sha256=state.sha256(), permissions_before=tuple(permissions_before), permissions_after=tuple(permissions_after), successor_route=successor_route, rollback_route=rollback_route, destructive_state_authority_ref=destructive_state_authority_ref)

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "transition_id": self.transition_id, "operation": self.operation, "source_host_id": self.source_host_id, "source_route_id": self.source_route_id, "state": self.state.as_dict(), "expected_state_binding_sha256": self.expected_state_binding_sha256, "permissions_before": list(self.permissions_before), "permissions_after": list(self.permissions_after), "successor_route": None if self.successor_route is None else self.successor_route.as_dict(), "rollback_route": None if self.rollback_route is None else self.rollback_route.as_dict(), "destructive_state_authority_ref": None}

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class HostTransitionPlan:
    schema: str
    transition_id: str
    operation: str
    request_sha256: str
    state_lineage_id: str
    state_generation: int
    state_binding_sha256: str
    steps: tuple[str, ...]
    withdrawn_permissions: tuple[str, ...]
    target_host_id: str | None
    target_route_id: str | None
    rollback_host_id: str | None
    rollback_route_id: str | None
    candidate_status: str = "PLAN_READY"
    runtime_credit: int = 0
    physical_host_credit: int = 0
    whole_system_acceptance: bool = False

    def __post_init__(self) -> None:
        if self.schema != TRANSITION_PLAN_SCHEMA:
            raise HostTransitionError("transition plan schema mismatch")
        _text("transition_id", self.transition_id)
        if self.operation not in _ALLOWED_OPERATIONS:
            raise HostTransitionError("transition plan operation mismatch")
        _sha256("request_sha256", self.request_sha256)
        _text("state_lineage_id", self.state_lineage_id)
        _generation("state_generation", self.state_generation)
        _sha256("state_binding_sha256", self.state_binding_sha256)
        if not self.steps:
            raise HostTransitionError("transition plan must contain steps")
        if self.runtime_credit != 0 or self.physical_host_credit != 0 or self.whole_system_acceptance is not False:
            raise HostTransitionError("plan-only component cannot mint runtime/host/whole-system credit")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def plan_host_transition(request: HostTransitionRequest) -> HostTransitionPlan:
    if type(request) is not HostTransitionRequest:
        raise HostTransitionError("request must be exact HostTransitionRequest")
    request = HostTransitionRequest(schema=request.schema, transition_id=request.transition_id, operation=request.operation, source_host_id=request.source_host_id, source_route_id=request.source_route_id, state=CanonicalStateBinding(**request.state.as_dict()), expected_state_binding_sha256=request.expected_state_binding_sha256, permissions_before=request.permissions_before, permissions_after=request.permissions_after, successor_route=None if request.successor_route is None else HostRouteEvidence(**request.successor_route.as_dict()), rollback_route=None if request.rollback_route is None else HostRouteEvidence(**request.rollback_route.as_dict()), destructive_state_authority_ref=None)
    steps = [STEP_FREEZE]
    target_host_id = target_route_id = rollback_host_id = rollback_route_id = None
    if request.operation == OP_WITHDRAW_PERMISSIONS:
        steps.append(STEP_WITHDRAW)
    elif request.operation == OP_DISABLE:
        steps.append(STEP_DISABLE)
    elif request.operation == OP_UNINSTALL:
        steps.extend((STEP_DISABLE, STEP_UNINSTALL))
    elif request.operation == OP_SWITCH_HOST:
        assert request.successor_route is not None
        target_host_id = request.successor_route.host_id
        target_route_id = request.successor_route.route_id
        steps.extend((STEP_VERIFY_SUCCESSOR, STEP_DISABLE, STEP_BIND_SUCCESSOR, STEP_READBACK))
    elif request.operation == OP_REENABLE:
        assert request.rollback_route is not None
        rollback_host_id = request.rollback_route.host_id
        rollback_route_id = request.rollback_route.route_id
        steps.extend((STEP_REENABLE, STEP_READBACK))
    steps.extend((STEP_RETAIN_STATE, STEP_RECORD))
    withdrawn = tuple(sorted(set(request.permissions_before) - set(request.permissions_after)))
    return HostTransitionPlan(schema=TRANSITION_PLAN_SCHEMA, transition_id=request.transition_id, operation=request.operation, request_sha256=request.sha256(), state_lineage_id=request.state.lineage_id, state_generation=request.state.generation, state_binding_sha256=request.state.sha256(), steps=tuple(steps), withdrawn_permissions=withdrawn, target_host_id=target_host_id, target_route_id=target_route_id, rollback_host_id=rollback_host_id, rollback_route_id=rollback_route_id)
