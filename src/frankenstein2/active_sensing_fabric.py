"""VisualNeed -> permission-bound ObserveIntent compiler for Frankenstein 2.0.

This is the top-down active-sensing link between the world-model uncertainty layer and the
Perception Fabric. It plans a bounded sensing request only; it performs no capture or model
inference and grants no sensor/world/effect/completion authority.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .perception_fabric import (
    ObserveIntent,
    PerceptionCapability,
    PerceptionCapabilitySnapshot,
    PerceptionFabricError,
    PerceptionSource,
)
from .perception_host_permissions import (
    PerceptionHostPermissionError,
    require_effective_host_bound_snapshot,
)
from .visual_need import VisualNeed


class ActiveSensingFabricError(ValueError):
    """Fail-closed VisualNeed/ObserveIntent binding error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ActiveSensingFabricError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ActiveSensingFabricError(f"{name} must not contain control characters")
    return value


def _positive(name: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise ActiveSensingFabricError(f"{name} must be an integer > 0")
    return value


def _micros(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise ActiveSensingFabricError(f"{name} must be an integer in [0, 1000000]")
    return value


def _refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple or (not allow_empty and not value):
        suffix = "immutable tuple" if allow_empty else "non-empty immutable tuple"
        raise ActiveSensingFabricError(f"{name} must be a {suffix}")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise ActiveSensingFabricError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


def compile_observe_intent(
    *,
    visual_need: VisualNeed,
    source: PerceptionSource,
    permission_snapshot: PerceptionCapabilitySnapshot,
    requested_head_ids: tuple[str, ...],
    roi_ref: str | None,
    required_freshness_ns: int,
    expires_monotonic_ns: int,
    priority_micros: int,
    max_work_units: int,
    allow_remote_frame: bool = False,
    allow_external_vlm: bool = False,
    provenance_refs: tuple[str, ...],
) -> ObserveIntent:
    """Compile one exact VisualNeed into one source-specific effective-permission request."""
    if type(visual_need) is not VisualNeed:
        raise ActiveSensingFabricError("visual_need must be a concrete VisualNeed")
    if type(source) is not PerceptionSource:
        raise ActiveSensingFabricError("source must be a concrete PerceptionSource")
    if type(permission_snapshot) is not PerceptionCapabilitySnapshot:
        raise ActiveSensingFabricError("permission_snapshot must be a concrete PerceptionCapabilitySnapshot")
    try:
        require_effective_host_bound_snapshot(permission_snapshot)
    except PerceptionHostPermissionError as exc:
        raise ActiveSensingFabricError(str(exc)) from exc
    if permission_snapshot.source_id != source.source_id:
        raise ActiveSensingFabricError("source and permission snapshot source_id mismatch")
    heads = _refs("requested_head_ids", requested_head_ids, allow_empty=True)
    if not heads:
        raise ActiveSensingFabricError("VisualNeed compilation requires at least one requested perception head")
    if not permission_snapshot.allows(PerceptionCapability.SEE):
        raise ActiveSensingFabricError("SEE capability is required to compile ObserveIntent")
    if not permission_snapshot.allows(PerceptionCapability.ANALYZE):
        raise ActiveSensingFabricError("ANALYZE capability is required to compile requested heads")
    if type(allow_remote_frame) is not bool or type(allow_external_vlm) is not bool:
        raise ActiveSensingFabricError("allow_remote_frame and allow_external_vlm must be bool")
    if allow_remote_frame and not permission_snapshot.allows(PerceptionCapability.REMOTE_FRAME):
        raise ActiveSensingFabricError("REMOTE_FRAME capability is not permitted")
    if allow_external_vlm:
        if not allow_remote_frame:
            raise ActiveSensingFabricError("external VLM escalation requires remote-frame transport to be explicitly enabled")
        if not permission_snapshot.allows(PerceptionCapability.EXTERNAL_VLM):
            raise ActiveSensingFabricError("EXTERNAL_VLM capability is not permitted")
    if roi_ref is not None:
        roi_ref = _text("roi_ref", roi_ref)
    _positive("required_freshness_ns", required_freshness_ns)
    _positive("expires_monotonic_ns", expires_monotonic_ns)
    _micros("priority_micros", priority_micros)
    _positive("max_work_units", max_work_units)
    provenance = set(_refs("provenance_refs", provenance_refs))
    provenance.update(visual_need.provenance_refs)
    provenance.update(source.provenance_refs)
    provenance.update(permission_snapshot.provenance_refs)
    provenance.add(f"visual-need-sha256:{visual_need.sha256()}")
    provenance.add(f"perception-source-sha256:{source.sha256()}")
    provenance.add(f"permission-snapshot-sha256:{permission_snapshot.sha256()}")
    target_atom_ids = tuple(target.atom_id for target in visual_need.targets)
    identity_payload = {
        "visual_need_id": visual_need.visual_need_id,
        "visual_need_sha256": visual_need.sha256(),
        "source_id": source.source_id,
        "permission_snapshot_sha256": permission_snapshot.sha256(),
        "requested_head_ids": list(heads),
        "target_atom_ids": list(target_atom_ids),
        "roi_ref": roi_ref,
        "expires_monotonic_ns": expires_monotonic_ns,
    }
    intent_id = "observe-intent:" + _digest(identity_payload)[:24]
    try:
        return ObserveIntent(
            intent_id=intent_id,
            cycle_id=visual_need.cycle_id,
            generation=visual_need.generation,
            source_id=source.source_id,
            permission_snapshot_sha256=permission_snapshot.sha256(),
            requested_head_ids=heads,
            target_atom_ids=target_atom_ids,
            roi_ref=roi_ref,
            required_freshness_ns=required_freshness_ns,
            expires_monotonic_ns=expires_monotonic_ns,
            priority_micros=priority_micros,
            max_work_units=max_work_units,
            allow_remote_frame=allow_remote_frame,
            allow_external_vlm=allow_external_vlm,
            provenance_refs=tuple(sorted(provenance)),
        )
    except PerceptionFabricError as exc:
        raise ActiveSensingFabricError(str(exc)) from exc


__all__ = ["ActiveSensingFabricError", "compile_observe_intent"]
