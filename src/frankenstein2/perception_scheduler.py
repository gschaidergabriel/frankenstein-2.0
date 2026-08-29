"""Bounded dynamic analysis scheduler for the Frankenstein 2.0 Perception Fabric.

The scheduler operates only on typed ObserveIntent descriptors. It never opens devices,
reads raw frames, invokes providers/VLMs, persists sensor payloads, or grants world/effect/
completion authority. Its job is to keep perception analysis inside an explicit 0..4 worker
and compute envelope while preserving deterministic backpressure and fail-closed permission
revalidation at dispatch time.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, ClassVar

from .perception_fabric import (
    ObserveIntent,
    PerceptionCapabilitySnapshot,
    PerceptionFabricError,
)

SCHEDULER_POLICY_SCHEMA = "FRANKENSTEIN2_PERCEPTION_SCHEDULER_POLICY/v1"
SCHEDULER_STATE_SCHEMA = "FRANKENSTEIN2_PERCEPTION_SCHEDULER_STATE/v1"
SCHEDULER_PLAN_SCHEMA = "FRANKENSTEIN2_PERCEPTION_SCHEDULER_PLAN/v1"


class PerceptionSchedulerError(ValueError):
    """Fail-closed scheduler contract error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise PerceptionSchedulerError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PerceptionSchedulerError(f"{name} must not contain control characters")
    return value


def _nonnegative(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PerceptionSchedulerError(f"{name} must be an integer >= 0")
    return value


def _micros(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise PerceptionSchedulerError(f"{name} must be an integer in [0, 1000000]")
    return value


def _refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple or (not allow_empty and not value):
        suffix = "immutable tuple" if allow_empty else "non-empty immutable tuple"
        raise PerceptionSchedulerError(f"{name} must be a {suffix}")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise PerceptionSchedulerError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PerceptionSchedulerError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _rank(intent: ObserveIntent) -> tuple[int, int, int, str]:
    # Highest value first, then earliest expiry, then cheapest work, then stable id.
    return (-intent.priority_micros, intent.expires_monotonic_ns, intent.max_work_units, intent.intent_id)


def _coalesce_key(intent: ObserveIntent) -> tuple[Any, ...]:
    return (
        intent.source_id,
        intent.requested_head_ids,
        intent.target_atom_ids,
        intent.roi_ref,
        intent.allow_remote_frame,
        intent.allow_external_vlm,
    )


def _preferred_coalesced(a: ObserveIntent, b: ObserveIntent) -> ObserveIntent:
    """Choose one equivalent queued need deterministically.

    Higher intent generation wins. Within the same generation prefer higher priority,
    later expiry/freshness opportunity, lower work cost, then lexicographically stable id.
    """
    key_a = (a.generation, a.priority_micros, a.expires_monotonic_ns, -a.max_work_units, a.intent_id)
    key_b = (b.generation, b.priority_micros, b.expires_monotonic_ns, -b.max_work_units, b.intent_id)
    return a if key_a >= key_b else b


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionSchedulerPolicy:
    policy_id: str
    generation: int
    max_active_workers: int
    max_queue_items: int
    max_perception_work_units: int
    pressure_drop_below_priority_micros: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = SCHEDULER_POLICY_SCHEMA
    classification: ClassVar[str] = "DETERMINISTIC_PERCEPTION_COMPUTE_POLICY_NOT_EXECUTION_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _nonnegative("generation", self.generation)
        if type(self.max_active_workers) is not int or not 0 <= self.max_active_workers <= 4:
            raise PerceptionSchedulerError("max_active_workers must be an integer in [0, 4]")
        if type(self.max_queue_items) is not int or not 1 <= self.max_queue_items <= 4096:
            raise PerceptionSchedulerError("max_queue_items must be an integer in [1, 4096]")
        _nonnegative("max_perception_work_units", self.max_perception_work_units)
        _micros("pressure_drop_below_priority_micros", self.pressure_drop_below_priority_micros)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "max_active_workers": self.max_active_workers,
            "max_queue_items": self.max_queue_items,
            "max_perception_work_units": self.max_perception_work_units,
            "pressure_drop_below_priority_micros": self.pressure_drop_below_priority_micros,
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionSchedulerState:
    scheduler_id: str
    generation: int
    queued_intents: tuple[ObserveIntent, ...]
    dropped_intent_count: int
    recent_dropped_intent_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = SCHEDULER_STATE_SCHEMA
    classification: ClassVar[str] = "BOUNDED_PERCEPTION_ANALYSIS_QUEUE_NOT_SENSOR_OR_WORLD_STATE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "scheduler_id", _text("scheduler_id", self.scheduler_id))
        _nonnegative("generation", self.generation)
        if type(self.queued_intents) is not tuple or any(type(item) is not ObserveIntent for item in self.queued_intents):
            raise PerceptionSchedulerError("queued_intents must be an immutable tuple of concrete ObserveIntent values")
        ids = tuple(item.intent_id for item in self.queued_intents)
        if len(ids) != len(set(ids)):
            raise PerceptionSchedulerError("queued_intents must not contain duplicate intent_id values")
        _nonnegative("dropped_intent_count", self.dropped_intent_count)
        drops = _refs("recent_dropped_intent_ids", self.recent_dropped_intent_ids, allow_empty=True)
        if self.dropped_intent_count < len(drops):
            raise PerceptionSchedulerError("dropped_intent_count cannot be smaller than retained drop ids")
        object.__setattr__(self, "recent_dropped_intent_ids", drops)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "scheduler_id": self.scheduler_id,
            "generation": self.generation,
            "queued_intent_ids": [item.intent_id for item in self.queued_intents],
            "queued_source_ids": [item.source_id for item in self.queued_intents],
            "dropped_intent_count": self.dropped_intent_count,
            "recent_dropped_intent_ids": list(self.recent_dropped_intent_ids),
            "raw_frame_persistence": False,
            "provider_or_vlm_invocation": False,
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionSchedulePlan:
    plan_id: str
    scheduler_generation: int
    policy_sha256: str
    selected_intent_ids: tuple[str, ...]
    deferred_intent_ids: tuple[str, ...]
    dropped_intent_ids: tuple[str, ...]
    active_workers: int
    consumed_work_units: int
    effective_perception_budget_units: int
    control_reserve_units: int
    pressure_degraded: bool
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = SCHEDULER_PLAN_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_ANALYSIS_SCHEDULE_CANDIDATE_NOT_EXECUTION_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _text("plan_id", self.plan_id))
        _nonnegative("scheduler_generation", self.scheduler_generation)
        _text("policy_sha256", self.policy_sha256)
        selected = _refs("selected_intent_ids", self.selected_intent_ids, allow_empty=True)
        deferred = _refs("deferred_intent_ids", self.deferred_intent_ids, allow_empty=True)
        dropped = _refs("dropped_intent_ids", self.dropped_intent_ids, allow_empty=True)
        if set(selected) & set(deferred) or set(selected) & set(dropped) or set(deferred) & set(dropped):
            raise PerceptionSchedulerError("selected/deferred/dropped intent ids must be disjoint")
        object.__setattr__(self, "selected_intent_ids", selected)
        object.__setattr__(self, "deferred_intent_ids", deferred)
        object.__setattr__(self, "dropped_intent_ids", dropped)
        if type(self.active_workers) is not int or not 0 <= self.active_workers <= 4:
            raise PerceptionSchedulerError("active_workers must be an integer in [0, 4]")
        if self.active_workers != len(selected):
            raise PerceptionSchedulerError("active_workers must equal selected intent count")
        _nonnegative("consumed_work_units", self.consumed_work_units)
        _nonnegative("effective_perception_budget_units", self.effective_perception_budget_units)
        _nonnegative("control_reserve_units", self.control_reserve_units)
        if self.consumed_work_units > self.effective_perception_budget_units:
            raise PerceptionSchedulerError("consumed work exceeds effective perception budget")
        if type(self.pressure_degraded) is not bool:
            raise PerceptionSchedulerError("pressure_degraded must be bool")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "plan_id": self.plan_id,
            "scheduler_generation": self.scheduler_generation,
            "policy_sha256": self.policy_sha256,
            "selected_intent_ids": list(self.selected_intent_ids),
            "deferred_intent_ids": list(self.deferred_intent_ids),
            "dropped_intent_ids": list(self.dropped_intent_ids),
            "active_workers": self.active_workers,
            "consumed_work_units": self.consumed_work_units,
            "effective_perception_budget_units": self.effective_perception_budget_units,
            "control_reserve_units": self.control_reserve_units,
            "pressure_degraded": self.pressure_degraded,
            "raw_frame_persistence": False,
            "provider_or_vlm_invocation": False,
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def create_scheduler(*, scheduler_id: str, provenance_refs: tuple[str, ...]) -> PerceptionSchedulerState:
    return PerceptionSchedulerState(
        scheduler_id=scheduler_id,
        generation=0,
        queued_intents=(),
        dropped_intent_count=0,
        recent_dropped_intent_ids=(),
        provenance_refs=_refs("provenance_refs", provenance_refs),
    )


def enqueue_intents(
    *,
    state: PerceptionSchedulerState,
    policy: PerceptionSchedulerPolicy,
    intents: tuple[ObserveIntent, ...],
) -> PerceptionSchedulerState:
    """Add work with deterministic coalescing and bounded overflow accounting."""
    if type(state) is not PerceptionSchedulerState:
        raise PerceptionSchedulerError("state must be a concrete PerceptionSchedulerState")
    if type(policy) is not PerceptionSchedulerPolicy:
        raise PerceptionSchedulerError("policy must be a concrete PerceptionSchedulerPolicy")
    if type(intents) is not tuple or any(type(item) is not ObserveIntent for item in intents):
        raise PerceptionSchedulerError("intents must be an immutable tuple of concrete ObserveIntent values")

    combined = list(state.queued_intents) + list(intents)
    ids = [item.intent_id for item in combined]
    if len(ids) != len(set(ids)):
        raise PerceptionSchedulerError("duplicate intent_id cannot be enqueued")

    by_key: dict[tuple[Any, ...], ObserveIntent] = {}
    coalesced_ids: list[str] = []
    for intent in combined:
        key = _coalesce_key(intent)
        previous = by_key.get(key)
        if previous is None:
            by_key[key] = intent
            continue
        preferred = _preferred_coalesced(previous, intent)
        rejected = intent if preferred is previous else previous
        by_key[key] = preferred
        coalesced_ids.append(rejected.intent_id)

    ordered = sorted(by_key.values(), key=_rank)
    overflow = ordered[policy.max_queue_items :]
    kept = tuple(ordered[: policy.max_queue_items])
    dropped_now = coalesced_ids + [item.intent_id for item in overflow]
    recent = tuple(sorted((list(state.recent_dropped_intent_ids) + dropped_now)[-policy.max_queue_items :]))
    provenance = set(state.provenance_refs)
    provenance.update(policy.provenance_refs)
    provenance.add(f"scheduler-prior-sha256:{state.sha256()}")
    provenance.add(f"scheduler-policy-sha256:{policy.sha256()}")

    return PerceptionSchedulerState(
        scheduler_id=state.scheduler_id,
        generation=state.generation + 1,
        queued_intents=kept,
        dropped_intent_count=state.dropped_intent_count + len(dropped_now),
        recent_dropped_intent_ids=recent,
        provenance_refs=tuple(sorted(provenance)),
    )


def plan_perception_cycle(
    *,
    state: PerceptionSchedulerState,
    policy: PerceptionSchedulerPolicy,
    permission_snapshots: tuple[PerceptionCapabilitySnapshot, ...],
    now_monotonic_ns: int,
    available_compute_units: int,
    control_reserve_units: int,
) -> tuple[PerceptionSchedulerState, PerceptionSchedulePlan]:
    """Select at most 0..4 analysis intents while preserving control reserve.

    Permission is revalidated at dispatch. Missing, stale, revoked or expired authority causes
    the queued intent to be dropped fail-closed. Under resource pressure, low-priority work is
    discarded before the scheduler consumes the caller-declared control reserve.
    """
    if type(state) is not PerceptionSchedulerState:
        raise PerceptionSchedulerError("state must be a concrete PerceptionSchedulerState")
    if type(policy) is not PerceptionSchedulerPolicy:
        raise PerceptionSchedulerError("policy must be a concrete PerceptionSchedulerPolicy")
    _nonnegative("now_monotonic_ns", now_monotonic_ns)
    _nonnegative("available_compute_units", available_compute_units)
    _nonnegative("control_reserve_units", control_reserve_units)
    if type(permission_snapshots) is not tuple or any(
        type(item) is not PerceptionCapabilitySnapshot for item in permission_snapshots
    ):
        raise PerceptionSchedulerError(
            "permission_snapshots must be an immutable tuple of concrete PerceptionCapabilitySnapshot values"
        )

    snapshots: dict[str, PerceptionCapabilitySnapshot] = {}
    for snapshot in permission_snapshots:
        if snapshot.source_id in snapshots:
            raise PerceptionSchedulerError("permission_snapshots must contain at most one current snapshot per source")
        snapshots[snapshot.source_id] = snapshot

    pressure_degraded = available_compute_units <= control_reserve_units
    free_after_reserve = max(0, available_compute_units - control_reserve_units)
    effective_budget = min(policy.max_perception_work_units, free_after_reserve)

    valid: list[ObserveIntent] = []
    dropped: list[str] = []
    for intent in state.queued_intents:
        snapshot = snapshots.get(intent.source_id)
        if snapshot is None:
            dropped.append(intent.intent_id)
            continue
        try:
            intent.validate_against(snapshot, now_monotonic_ns=now_monotonic_ns)
        except PerceptionFabricError:
            dropped.append(intent.intent_id)
            continue
        if pressure_degraded and intent.priority_micros < policy.pressure_drop_below_priority_micros:
            dropped.append(intent.intent_id)
            continue
        valid.append(intent)

    ordered = sorted(valid, key=_rank)
    selected: list[ObserveIntent] = []
    selected_ids: set[str] = set()
    used_sources: set[str] = set()
    remaining_budget = effective_budget

    # First pass gives useful independent sources a chance before a second task from one source.
    for intent in ordered:
        if len(selected) >= policy.max_active_workers:
            break
        if intent.source_id in used_sources or intent.max_work_units > remaining_budget:
            continue
        selected.append(intent)
        selected_ids.add(intent.intent_id)
        used_sources.add(intent.source_id)
        remaining_budget -= intent.max_work_units

    # Second pass may use remaining slots for additional work from already represented sources.
    for intent in ordered:
        if len(selected) >= policy.max_active_workers:
            break
        if intent.intent_id in selected_ids or intent.max_work_units > remaining_budget:
            continue
        selected.append(intent)
        selected_ids.add(intent.intent_id)
        remaining_budget -= intent.max_work_units

    deferred = [item for item in ordered if item.intent_id not in selected_ids]
    if len(deferred) > policy.max_queue_items:
        overflow = deferred[policy.max_queue_items :]
        dropped.extend(item.intent_id for item in overflow)
        deferred = deferred[: policy.max_queue_items]

    dropped = sorted(set(dropped))
    recent = tuple(sorted((list(state.recent_dropped_intent_ids) + dropped)[-policy.max_queue_items :]))
    provenance = set(state.provenance_refs)
    provenance.update(policy.provenance_refs)
    provenance.add(f"scheduler-prior-sha256:{state.sha256()}")
    provenance.add(f"scheduler-policy-sha256:{policy.sha256()}")

    next_state = PerceptionSchedulerState(
        scheduler_id=state.scheduler_id,
        generation=state.generation + 1,
        queued_intents=tuple(deferred),
        dropped_intent_count=state.dropped_intent_count + len(dropped),
        recent_dropped_intent_ids=recent,
        provenance_refs=tuple(sorted(provenance)),
    )
    consumed = effective_budget - remaining_budget
    plan_payload = {
        "scheduler_id": state.scheduler_id,
        "scheduler_generation": next_state.generation,
        "policy_sha256": policy.sha256(),
        "selected": sorted(selected_ids),
        "deferred": sorted(item.intent_id for item in deferred),
        "dropped": dropped,
        "budget": effective_budget,
        "control_reserve": control_reserve_units,
    }
    plan = PerceptionSchedulePlan(
        plan_id=f"perception-plan:{_digest(plan_payload)}",
        scheduler_generation=next_state.generation,
        policy_sha256=policy.sha256(),
        selected_intent_ids=tuple(sorted(selected_ids)),
        deferred_intent_ids=tuple(sorted(item.intent_id for item in deferred)),
        dropped_intent_ids=tuple(dropped),
        active_workers=len(selected),
        consumed_work_units=consumed,
        effective_perception_budget_units=effective_budget,
        control_reserve_units=control_reserve_units,
        pressure_degraded=pressure_degraded,
        provenance_refs=tuple(sorted(provenance)),
    )
    return next_state, plan


__all__ = [
    "PerceptionSchedulePlan",
    "PerceptionSchedulerError",
    "PerceptionSchedulerPolicy",
    "PerceptionSchedulerState",
    "SCHEDULER_PLAN_SCHEMA",
    "SCHEDULER_POLICY_SCHEMA",
    "SCHEDULER_STATE_SCHEMA",
    "create_scheduler",
    "enqueue_intents",
    "plan_perception_cycle",
]
