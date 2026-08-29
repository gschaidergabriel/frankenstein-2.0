"""Resolve user dashboard policy with real host/OS permission evidence.

Dashboard intent is not proof that a camera/display/browser primitive is currently available
or OS-authorized. This module intersects a requested PerceptionCapabilitySnapshot with a
host-produced grant and marks the resulting snapshot as effective host-bound permission for
ObserveIntent compilation.

The grant is still an input contract, not world truth. The local host adapter is responsible
for producing it from actual OS/native capability checks during final integration.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, ClassVar

from .perception_fabric import PerceptionCapability, PerceptionCapabilitySnapshot

HOST_PERMISSION_GRANT_SCHEMA = "FRANKENSTEIN2_HOST_PERMISSION_GRANT/v1"
EFFECTIVE_PERMISSION_MARKER = "effective-host-permission:"


class PerceptionHostPermissionError(ValueError):
    """Fail-closed host-permission resolution error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise PerceptionHostPermissionError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PerceptionHostPermissionError(f"{name} must not contain control characters")
    return value


def _nonnegative(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PerceptionHostPermissionError(f"{name} must be an integer >= 0")
    return value


def _positive_optional(name: str, value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise PerceptionHostPermissionError(f"{name} must be None or an integer > 0")
    return value


def _refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise PerceptionHostPermissionError(f"{name} must be a non-empty immutable tuple")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise PerceptionHostPermissionError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class HostPermissionGrant:
    grant_id: str
    source_id: str
    generation: int
    granted_capabilities: tuple[PerceptionCapability, ...]
    valid_from_monotonic_ns: int
    expires_monotonic_ns: int | None
    host_adapter_id: str
    native_permission_ref: str
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = HOST_PERMISSION_GRANT_SCHEMA
    classification: ClassVar[str] = "HOST_PERMISSION_EVIDENCE_INPUT_NOT_USER_POLICY_WORLD_TRUTH_OR_EFFECT_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "grant_id", _text("grant_id", self.grant_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative("generation", self.generation)
        if type(self.granted_capabilities) is not tuple or any(
            not isinstance(item, PerceptionCapability) for item in self.granted_capabilities
        ):
            raise PerceptionHostPermissionError(
                "granted_capabilities must be an immutable tuple of PerceptionCapability values"
            )
        if len(self.granted_capabilities) != len(set(self.granted_capabilities)):
            raise PerceptionHostPermissionError("granted_capabilities must not contain duplicates")
        object.__setattr__(
            self,
            "granted_capabilities",
            tuple(sorted(self.granted_capabilities, key=lambda item: item.value)),
        )
        _nonnegative("valid_from_monotonic_ns", self.valid_from_monotonic_ns)
        _positive_optional("expires_monotonic_ns", self.expires_monotonic_ns)
        if self.expires_monotonic_ns is not None and self.expires_monotonic_ns <= self.valid_from_monotonic_ns:
            raise PerceptionHostPermissionError(
                "expires_monotonic_ns must be greater than valid_from_monotonic_ns"
            )
        object.__setattr__(self, "host_adapter_id", _text("host_adapter_id", self.host_adapter_id))
        object.__setattr__(self, "native_permission_ref", _text("native_permission_ref", self.native_permission_ref))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def is_valid_at(self, monotonic_ns: int) -> bool:
        _nonnegative("monotonic_ns", monotonic_ns)
        return (
            monotonic_ns >= self.valid_from_monotonic_ns
            and (self.expires_monotonic_ns is None or monotonic_ns < self.expires_monotonic_ns)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "grant_id": self.grant_id,
            "source_id": self.source_id,
            "generation": self.generation,
            "granted_capabilities": [item.value for item in self.granted_capabilities],
            "valid_from_monotonic_ns": self.valid_from_monotonic_ns,
            "expires_monotonic_ns": self.expires_monotonic_ns,
            "host_adapter_id": self.host_adapter_id,
            "native_permission_ref": self.native_permission_ref,
            "sensor_execution_authority": "EVIDENCE_INPUT_ONLY",
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def is_effective_host_bound_snapshot(snapshot: PerceptionCapabilitySnapshot) -> bool:
    if type(snapshot) is not PerceptionCapabilitySnapshot:
        raise PerceptionHostPermissionError(
            "snapshot must be a concrete PerceptionCapabilitySnapshot"
        )
    return any(ref.startswith(EFFECTIVE_PERMISSION_MARKER) for ref in snapshot.provenance_refs)


def require_effective_host_bound_snapshot(snapshot: PerceptionCapabilitySnapshot) -> None:
    if not is_effective_host_bound_snapshot(snapshot):
        raise PerceptionHostPermissionError(
            "ObserveIntent requires effective user+host permission; dashboard policy alone is not OS permission proof"
        )


def resolve_effective_perception_snapshot(
    *,
    requested_snapshot: PerceptionCapabilitySnapshot,
    host_grant: HostPermissionGrant,
    now_monotonic_ns: int,
    provenance_refs: tuple[str, ...],
) -> PerceptionCapabilitySnapshot:
    """Intersect user policy and host grant into an execution-checkable snapshot."""
    if type(requested_snapshot) is not PerceptionCapabilitySnapshot:
        raise PerceptionHostPermissionError(
            "requested_snapshot must be a concrete PerceptionCapabilitySnapshot"
        )
    if type(host_grant) is not HostPermissionGrant:
        raise PerceptionHostPermissionError("host_grant must be a concrete HostPermissionGrant")
    _nonnegative("now_monotonic_ns", now_monotonic_ns)
    if requested_snapshot.source_id != host_grant.source_id:
        raise PerceptionHostPermissionError("requested snapshot / host grant source_id mismatch")
    if not requested_snapshot.is_valid_at(now_monotonic_ns):
        raise PerceptionHostPermissionError("requested dashboard policy snapshot is not currently valid")
    if not host_grant.is_valid_at(now_monotonic_ns):
        raise PerceptionHostPermissionError("host permission grant is not currently valid")

    caps = set(requested_snapshot.capabilities).intersection(host_grant.granted_capabilities)
    # Dependency closure after intersection: dependent privileges cannot survive a missing prerequisite.
    if PerceptionCapability.SEE not in caps:
        caps.difference_update(
            {
                PerceptionCapability.ANALYZE,
                PerceptionCapability.RAW_RETENTION,
                PerceptionCapability.REMOTE_FRAME,
                PerceptionCapability.EXTERNAL_VLM,
            }
        )
    if PerceptionCapability.ANALYZE not in caps:
        caps.discard(PerceptionCapability.EXTERNAL_VLM)

    valid_from = max(
        requested_snapshot.valid_from_monotonic_ns,
        host_grant.valid_from_monotonic_ns,
    )
    expiries = [
        value
        for value in (
            requested_snapshot.expires_monotonic_ns,
            host_grant.expires_monotonic_ns,
        )
        if value is not None
    ]
    expires = min(expiries) if expiries else None
    provenance = set(_refs("provenance_refs", provenance_refs))
    provenance.update(requested_snapshot.provenance_refs)
    provenance.update(host_grant.provenance_refs)
    provenance.add(f"requested-policy-sha256:{requested_snapshot.sha256()}")
    provenance.add(f"host-permission-grant-sha256:{host_grant.sha256()}")
    marker_payload = {
        "requested": requested_snapshot.sha256(),
        "host_grant": host_grant.sha256(),
        "effective_capabilities": sorted(item.value for item in caps),
        "valid_from": valid_from,
        "expires": expires,
    }
    provenance.add(EFFECTIVE_PERMISSION_MARKER + _digest(marker_payload))
    return PerceptionCapabilitySnapshot(
        snapshot_id="effective-permission:" + _digest(marker_payload)[:24],
        generation=max(requested_snapshot.generation, host_grant.generation),
        source_id=requested_snapshot.source_id,
        capabilities=tuple(sorted(caps, key=lambda item: item.value)),
        valid_from_monotonic_ns=valid_from,
        expires_monotonic_ns=expires,
        provenance_refs=tuple(sorted(provenance)),
    )


__all__ = [
    "EFFECTIVE_PERMISSION_MARKER",
    "HOST_PERMISSION_GRANT_SCHEMA",
    "HostPermissionGrant",
    "PerceptionHostPermissionError",
    "is_effective_host_bound_snapshot",
    "require_effective_host_bound_snapshot",
    "resolve_effective_perception_snapshot",
]
