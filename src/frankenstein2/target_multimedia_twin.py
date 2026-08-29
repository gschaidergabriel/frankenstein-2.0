"""Deterministic T2 desktop/session multimedia topology twin primitives.

F2-WP-1203 models interface and failure-surface semantics only. It does not
probe a physical host, grant target-host completion credit, or treat an active
service as proof that a session/device path is usable.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
from typing import Any


class TopologyError(ValueError):
    """Raised when a topology snapshot violates the T2 contract."""


class SessionType(str, Enum):
    WAYLAND = "WAYLAND"
    X11 = "X11"
    UNKNOWN = "UNKNOWN"


class EndpointKind(str, Enum):
    AUDIO_SOURCE = "AUDIO_SOURCE"
    AUDIO_SINK = "AUDIO_SINK"
    VIDEO_SOURCE = "VIDEO_SOURCE"
    DISPLAY = "DISPLAY"
    BROWSER = "BROWSER"


class IssueCode(str, Enum):
    SESSION_DBUS_UNAVAILABLE = "SESSION_DBUS_UNAVAILABLE"
    SERVICE_ACTIVE_UNUSABLE = "SERVICE_ACTIVE_UNUSABLE"
    PORTAL_UNREACHABLE = "PORTAL_UNREACHABLE"
    SESSION_OWNER_MISMATCH = "SESSION_OWNER_MISMATCH"
    STALE_SESSION_GENERATION = "STALE_SESSION_GENERATION"
    ENDPOINT_DEPENDENCY_UNAVAILABLE = "ENDPOINT_DEPENDENCY_UNAVAILABLE"
    WAYLAND_PORTAL_REQUIRED = "WAYLAND_PORTAL_REQUIRED"


def _clean_identifier(name: str, value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TopologyError(f"{name} must be a non-empty trimmed string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TopologyError(f"{name} contains control characters")
    return value


def _generation(name: str, value: int) -> int:
    if type(value) is not int or value < 1:
        raise TopologyError(f"{name} must be an integer >= 1")
    return value


def _uid(value: int | None) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise TopologyError("uid must be a non-negative integer or None")
    return value


@dataclass(frozen=True, slots=True)
class SessionContext:
    generation: int
    uid: int | None
    session_type: SessionType
    xdg_runtime_dir: str | None
    session_dbus_available: bool

    def __post_init__(self) -> None:
        _generation("session generation", self.generation)
        _uid(self.uid)
        if self.xdg_runtime_dir is not None:
            _clean_identifier("xdg_runtime_dir", self.xdg_runtime_dir)
        if type(self.session_dbus_available) is not bool:
            raise TopologyError("session_dbus_available must be bool")


@dataclass(frozen=True, slots=True)
class ServiceState:
    name: str
    generation: int
    active: bool
    usable: bool
    bus_owner: str | None = None

    def __post_init__(self) -> None:
        _clean_identifier("service name", self.name)
        _generation(f"{self.name} generation", self.generation)
        if type(self.active) is not bool or type(self.usable) is not bool:
            raise TopologyError("service active/usable must be bool")
        if self.bus_owner is not None:
            _clean_identifier("bus_owner", self.bus_owner)
        if self.usable and not self.active:
            raise TopologyError(f"{self.name}: usable service cannot be inactive")


@dataclass(frozen=True, slots=True)
class SyntheticEndpoint:
    endpoint_id: str
    kind: EndpointKind
    generation: int
    session_generation: int
    owner_uid: int | None
    present: bool
    usable: bool
    requires_portal: bool = False

    def __post_init__(self) -> None:
        _clean_identifier("endpoint_id", self.endpoint_id)
        _generation("endpoint generation", self.generation)
        _generation("endpoint session_generation", self.session_generation)
        _uid(self.owner_uid)
        for name in ("present", "usable", "requires_portal"):
            if type(getattr(self, name)) is not bool:
                raise TopologyError(f"{name} must be bool")
        if self.usable and not self.present:
            raise TopologyError("usable endpoint must be present")


@dataclass(frozen=True, slots=True)
class TopologyIssue:
    code: IssueCode
    subject: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "subject": self.subject, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class TopologyEvaluation:
    issues: tuple[TopologyIssue, ...]
    usable_endpoint_ids: tuple[str, ...]

    @property
    def healthy(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "usable_endpoint_ids": list(self.usable_endpoint_ids),
            "issues": [issue.as_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class MultimediaTopologySnapshot:
    session: SessionContext
    pipewire: ServiceState
    wireplumber: ServiceState
    portal: ServiceState
    endpoints: tuple[SyntheticEndpoint, ...]

    def __post_init__(self) -> None:
        expected_service_names = (
            ("pipewire", self.pipewire),
            ("wireplumber", self.wireplumber),
            ("portal", self.portal),
        )
        for role, service in expected_service_names:
            if service.name != role:
                raise TopologyError(
                    f"{role} role requires canonical service name {role!r}; "
                    f"got {service.name!r}"
                )

        ids = [endpoint.endpoint_id for endpoint in self.endpoints]
        if len(ids) != len(set(ids)):
            raise TopologyError("endpoint_id values must be unique")

    def as_dict(self) -> dict[str, Any]:
        return {
            "session": {
                "generation": self.session.generation,
                "uid": self.session.uid,
                "session_type": self.session.session_type.value,
                "xdg_runtime_dir": self.session.xdg_runtime_dir,
                "session_dbus_available": self.session.session_dbus_available,
            },
            "services": {
                service.name: {
                    "generation": service.generation,
                    "active": service.active,
                    "usable": service.usable,
                    "bus_owner": service.bus_owner,
                }
                for service in (self.pipewire, self.wireplumber, self.portal)
            },
            "endpoints": [
                {
                    "endpoint_id": endpoint.endpoint_id,
                    "kind": endpoint.kind.value,
                    "generation": endpoint.generation,
                    "session_generation": endpoint.session_generation,
                    "owner_uid": endpoint.owner_uid,
                    "present": endpoint.present,
                    "usable": endpoint.usable,
                    "requires_portal": endpoint.requires_portal,
                }
                for endpoint in sorted(self.endpoints, key=lambda item: item.endpoint_id)
            ],
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _service_issues(service: ServiceState) -> list[TopologyIssue]:
    if service.active and not service.usable:
        return [
            TopologyIssue(
                IssueCode.SERVICE_ACTIVE_UNUSABLE,
                service.name,
                "service is active but the independently modelled path is unusable",
            )
        ]
    if service.active and service.bus_owner is None and service.name == "portal":
        return [
            TopologyIssue(
                IssueCode.PORTAL_UNREACHABLE,
                service.name,
                "portal is active but no session-bus owner is observed",
            )
        ]
    return []


def evaluate_topology(snapshot: MultimediaTopologySnapshot) -> TopologyEvaluation:
    """Evaluate independently observable T2 usability/failure surfaces.

    The result is deliberately fail-closed: an active service does not erase a
    missing session bus, stale endpoint generation, ownership mismatch, or
    dependency failure.
    """

    issues: list[TopologyIssue] = []
    session = snapshot.session

    if not session.session_dbus_available:
        issues.append(
            TopologyIssue(
                IssueCode.SESSION_DBUS_UNAVAILABLE,
                "session",
                "session D-Bus is unavailable",
            )
        )

    for service in (snapshot.pipewire, snapshot.wireplumber, snapshot.portal):
        issues.extend(_service_issues(service))

    if snapshot.portal.active and not session.session_dbus_available:
        issues.append(
            TopologyIssue(
                IssueCode.PORTAL_UNREACHABLE,
                "portal",
                "active portal cannot be reached without the session D-Bus",
            )
        )

    usable_ids: list[str] = []
    audio_kinds = {EndpointKind.AUDIO_SOURCE, EndpointKind.AUDIO_SINK}
    for endpoint in sorted(snapshot.endpoints, key=lambda item: item.endpoint_id):
        endpoint_usable = endpoint.present and endpoint.usable

        if endpoint.session_generation != session.generation:
            issues.append(
                TopologyIssue(
                    IssueCode.STALE_SESSION_GENERATION,
                    endpoint.endpoint_id,
                    (
                        f"endpoint session generation {endpoint.session_generation} "
                        f"!= current {session.generation}"
                    ),
                )
            )
            endpoint_usable = False

        if session.uid is not None and endpoint.owner_uid is not None and endpoint.owner_uid != session.uid:
            issues.append(
                TopologyIssue(
                    IssueCode.SESSION_OWNER_MISMATCH,
                    endpoint.endpoint_id,
                    f"endpoint uid {endpoint.owner_uid} != session uid {session.uid}",
                )
            )
            endpoint_usable = False

        if endpoint.kind in audio_kinds and not (
            snapshot.pipewire.active
            and snapshot.pipewire.usable
            and snapshot.wireplumber.active
            and snapshot.wireplumber.usable
        ):
            issues.append(
                TopologyIssue(
                    IssueCode.ENDPOINT_DEPENDENCY_UNAVAILABLE,
                    endpoint.endpoint_id,
                    "audio endpoint requires usable PipeWire and WirePlumber",
                )
            )
            endpoint_usable = False

        if endpoint.requires_portal and not (
            session.session_dbus_available
            and snapshot.portal.active
            and snapshot.portal.usable
            and snapshot.portal.bus_owner is not None
        ):
            issues.append(
                TopologyIssue(
                    IssueCode.ENDPOINT_DEPENDENCY_UNAVAILABLE,
                    endpoint.endpoint_id,
                    "endpoint requires a usable portal on the session D-Bus",
                )
            )
            endpoint_usable = False

        if (
            session.session_type is SessionType.WAYLAND
            and endpoint.kind in {EndpointKind.DISPLAY, EndpointKind.BROWSER}
            and not endpoint.requires_portal
        ):
            issues.append(
                TopologyIssue(
                    IssueCode.WAYLAND_PORTAL_REQUIRED,
                    endpoint.endpoint_id,
                    "Wayland display/browser capture must model the portal permission boundary",
                )
            )
            endpoint_usable = False

        if endpoint_usable:
            usable_ids.append(endpoint.endpoint_id)

    return TopologyEvaluation(
        issues=tuple(issues),
        usable_endpoint_ids=tuple(usable_ids),
    )


def rebind_endpoint(
    snapshot: MultimediaTopologySnapshot,
    endpoint_id: str,
    *,
    new_generation: int,
    present: bool = True,
    usable: bool = True,
) -> MultimediaTopologySnapshot:
    """Return a snapshot with one endpoint rebound to the current session epoch."""

    _clean_identifier("endpoint_id", endpoint_id)
    _generation("new_generation", new_generation)
    updated: list[SyntheticEndpoint] = []
    found = False
    for endpoint in snapshot.endpoints:
        if endpoint.endpoint_id != endpoint_id:
            updated.append(endpoint)
            continue
        found = True
        if new_generation <= endpoint.generation:
            raise TopologyError("new_generation must advance the endpoint generation")
        updated.append(
            replace(
                endpoint,
                generation=new_generation,
                session_generation=snapshot.session.generation,
                owner_uid=snapshot.session.uid,
                present=present,
                usable=usable,
            )
        )
    if not found:
        raise TopologyError(f"unknown endpoint_id: {endpoint_id}")
    return replace(snapshot, endpoints=tuple(updated))


def advance_session(
    snapshot: MultimediaTopologySnapshot,
    *,
    generation: int,
    session_dbus_available: bool | None = None,
) -> MultimediaTopologySnapshot:
    """Advance the session epoch without silently rebinding endpoints/services."""

    if generation <= snapshot.session.generation:
        raise TopologyError("session generation must advance")
    return replace(
        snapshot,
        session=replace(
            snapshot.session,
            generation=generation,
            session_dbus_available=(
                snapshot.session.session_dbus_available
                if session_dbus_available is None
                else session_dbus_available
            ),
        ),
    )
