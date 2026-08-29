"""Headless dashboard policy state for Frankenstein 2.0 Perception Fabric.

The web UI is a presentation/control surface over this deterministic policy model. It does
not own sensor authority by itself. OS/hardware permission remains a separate local binding;
this layer expresses the user's Frankenstein-level permission intent and produces exact
capability snapshots for execution checks.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, ClassVar

from .perception_fabric import PerceptionCapability, PerceptionCapabilitySnapshot

DASHBOARD_SOURCE_POLICY_SCHEMA = "FRANKENSTEIN2_DASHBOARD_SOURCE_POLICY/v1"
DASHBOARD_STATE_SCHEMA = "FRANKENSTEIN2_PERCEPTION_DASHBOARD_STATE/v1"


class PerceptionDashboardError(ValueError):
    """Fail-closed dashboard policy error."""


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
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class DashboardSourcePolicy:
    source_id: str
    enabled: bool
    capabilities: tuple[PerceptionCapability, ...]
    generation: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = DASHBOARD_SOURCE_POLICY_SCHEMA
    classification: ClassVar[str] = "USER_PERCEPTION_POLICY_INTENT_NOT_OS_PERMISSION_OR_SENSOR_EXECUTION"

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        if type(self.enabled) is not bool:
            raise PerceptionDashboardError("enabled must be bool")
        if type(self.capabilities) is not tuple or any(not isinstance(item, PerceptionCapability) for item in self.capabilities):
            raise PerceptionDashboardError("capabilities must be an immutable tuple of PerceptionCapability values")
        if len(self.capabilities) != len(set(self.capabilities)):
            raise PerceptionDashboardError("capabilities must not contain duplicates")
        object.__setattr__(self, "capabilities", tuple(sorted(self.capabilities, key=lambda item: item.value)))
        _nonnegative("generation", self.generation)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))
        if not self.enabled and self.capabilities:
            raise PerceptionDashboardError("disabled source policy must not retain active capabilities")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "source_id": self.source_id,
            "enabled": self.enabled,
            "capabilities": [item.value for item in self.capabilities],
            "generation": self.generation,
            "os_permission_proven": False,
            "sensor_execution_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionDashboardState:
    state_id: str
    generation: int
    global_pause: bool
    max_active_cortex_workers: int
    source_policies: tuple[DashboardSourcePolicy, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = DASHBOARD_STATE_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_DASHBOARD_POLICY_STATE_NOT_OS_PERMISSION_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_id", _text("state_id", self.state_id))
        _nonnegative("generation", self.generation)
        if type(self.global_pause) is not bool:
            raise PerceptionDashboardError("global_pause must be bool")
        if type(self.max_active_cortex_workers) is not int or not 0 <= self.max_active_cortex_workers <= 4:
            raise PerceptionDashboardError("max_active_cortex_workers must be in [0, 4]")
        if type(self.source_policies) is not tuple or any(type(item) is not DashboardSourcePolicy for item in self.source_policies):
            raise PerceptionDashboardError("source_policies must be an immutable tuple of concrete DashboardSourcePolicy values")
        ids = [item.source_id for item in self.source_policies]
        if len(ids) != len(set(ids)):
            raise PerceptionDashboardError("source_id must be unique")
        object.__setattr__(self, "source_policies", tuple(sorted(self.source_policies, key=lambda item: item.source_id)))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def policy_for(self, source_id: str) -> DashboardSourcePolicy | None:
        source_id = _text("source_id", source_id)
        return next((item for item in self.source_policies if item.source_id == source_id), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "state_id": self.state_id,
            "generation": self.generation,
            "global_pause": self.global_pause,
            "max_active_cortex_workers": self.max_active_cortex_workers,
            "source_policies": [item.as_dict() for item in self.source_policies],
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def create_dashboard_state(
    *,
    state_id: str,
    max_active_cortex_workers: int = 4,
    provenance_refs: tuple[str, ...],
) -> PerceptionDashboardState:
    return PerceptionDashboardState(
        state_id=state_id,
        generation=0,
        global_pause=False,
        max_active_cortex_workers=max_active_cortex_workers,
        source_policies=(),
        provenance_refs=provenance_refs,
    )


def set_source_policy(
    *,
    state: PerceptionDashboardState,
    source_id: str,
    enabled: bool,
    capabilities: tuple[PerceptionCapability, ...],
    provenance_refs: tuple[str, ...],
) -> PerceptionDashboardState:
    if type(state) is not PerceptionDashboardState:
        raise PerceptionDashboardError("state must be a concrete PerceptionDashboardState")
    source_id = _text("source_id", source_id)
    if type(enabled) is not bool:
        raise PerceptionDashboardError("enabled must be bool")
    caps = capabilities if enabled else ()
    prior = state.policy_for(source_id)
    next_source_generation = 0 if prior is None else prior.generation + 1
    policy = DashboardSourcePolicy(
        source_id=source_id,
        enabled=enabled,
        capabilities=caps,
        generation=next_source_generation,
        provenance_refs=provenance_refs,
    )
    policies = {item.source_id: item for item in state.source_policies}
    policies[source_id] = policy
    provenance = set(state.provenance_refs)
    provenance.update(_refs("provenance_refs", provenance_refs))
    provenance.add(f"prior-dashboard-state-sha256:{state.sha256()}")
    provenance.add(f"source-policy-sha256:{policy.sha256()}")
    return PerceptionDashboardState(
        state_id=state.state_id,
        generation=state.generation + 1,
        global_pause=state.global_pause,
        max_active_cortex_workers=state.max_active_cortex_workers,
        source_policies=tuple(policies.values()),
        provenance_refs=tuple(sorted(provenance)),
    )


def set_global_pause(
    *,
    state: PerceptionDashboardState,
    paused: bool,
    provenance_refs: tuple[str, ...],
) -> PerceptionDashboardState:
    if type(state) is not PerceptionDashboardState:
        raise PerceptionDashboardError("state must be a concrete PerceptionDashboardState")
    if type(paused) is not bool:
        raise PerceptionDashboardError("paused must be bool")
    provenance = set(state.provenance_refs)
    provenance.update(_refs("provenance_refs", provenance_refs))
    provenance.add(f"prior-dashboard-state-sha256:{state.sha256()}")
    return PerceptionDashboardState(
        state_id=state.state_id,
        generation=state.generation + 1,
        global_pause=paused,
        max_active_cortex_workers=state.max_active_cortex_workers,
        source_policies=state.source_policies,
        provenance_refs=tuple(sorted(provenance)),
    )


def capability_snapshot_from_dashboard(
    *,
    state: PerceptionDashboardState,
    source_id: str,
    valid_from_monotonic_ns: int,
    expires_monotonic_ns: int | None,
    provenance_refs: tuple[str, ...],
) -> PerceptionCapabilitySnapshot:
    """Compile dashboard intent to an exact snapshot; global pause/revocation yields no caps."""
    if type(state) is not PerceptionDashboardState:
        raise PerceptionDashboardError("state must be a concrete PerceptionDashboardState")
    source_id = _text("source_id", source_id)
    policy = state.policy_for(source_id)
    if policy is None:
        raise PerceptionDashboardError("source has no dashboard policy")
    effective_caps = () if state.global_pause or not policy.enabled else policy.capabilities
    provenance = set(_refs("provenance_refs", provenance_refs))
    provenance.update(state.provenance_refs)
    provenance.update(policy.provenance_refs)
    provenance.add(f"dashboard-state-sha256:{state.sha256()}")
    provenance.add(f"dashboard-source-policy-sha256:{policy.sha256()}")
    snapshot_payload = {
        "dashboard_state_sha256": state.sha256(),
        "source_policy_sha256": policy.sha256(),
        "source_id": source_id,
        "effective_capabilities": [item.value for item in effective_caps],
        "valid_from_monotonic_ns": valid_from_monotonic_ns,
        "expires_monotonic_ns": expires_monotonic_ns,
    }
    return PerceptionCapabilitySnapshot(
        snapshot_id="dashboard-permission:" + _digest(snapshot_payload)[:24],
        generation=state.generation,
        source_id=source_id,
        capabilities=effective_caps,
        valid_from_monotonic_ns=valid_from_monotonic_ns,
        expires_monotonic_ns=expires_monotonic_ns,
        provenance_refs=tuple(sorted(provenance)),
    )


__all__ = [
    "DASHBOARD_SOURCE_POLICY_SCHEMA",
    "DASHBOARD_STATE_SCHEMA",
    "DashboardSourcePolicy",
    "PerceptionDashboardError",
    "PerceptionDashboardState",
    "capability_snapshot_from_dashboard",
    "create_dashboard_state",
    "set_global_pause",
    "set_source_policy",
]
