"""Deterministic adaptive-compute allocation candidates for logical GRID10.

F2-WP-505 generation 1.

This module combines one exact WP503 Grid10Plan with one exact WP501 ControlSnapshot
and an explicit caller-supplied allocation policy. It emits only an immutable allocation
candidate. It does not execute cognition, write GRID state, invoke models/tools/providers,
authorize effects/completion, or imply physical model/decode concurrency.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Iterable

from .cognitive_envelope import (
    ControlSnapshot,
    DISPOSITION_DEGRADED,
    DISPOSITION_HARD_LIMIT,
    DISPOSITION_UNKNOWN,
    DISPOSITION_WITHIN,
)
from .grid10_interface import GRID10_CELL_IDS, Grid10Plan

RULE_SCHEMA = "FRANKENSTEIN2_ADAPTIVE_COMPUTE_RULE/v1"
POLICY_SCHEMA = "FRANKENSTEIN2_ADAPTIVE_COMPUTE_POLICY/v1"
ALLOCATION_SCHEMA = "FRANKENSTEIN2_GRID10_ALLOCATION_CANDIDATE/v1"
CELL_ALLOCATION_SCHEMA = "FRANKENSTEIN2_GRID10_CELL_ALLOCATION/v1"
_DISPOSITIONS = (
    DISPOSITION_WITHIN,
    DISPOSITION_DEGRADED,
    DISPOSITION_HARD_LIMIT,
    DISPOSITION_UNKNOWN,
)
_DISPOSITION_SET = frozenset(_DISPOSITIONS)
_MAX_ID_LEN = 512
_MAX_WORK = 2**31 - 1
_MAX_REFS = 4096


class AdaptiveComputeError(ValueError):
    """Fail-closed adaptive-compute allocation contract error."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AdaptiveComputeError(f"{name} must be a non-empty already-trimmed string")
    if len(value) > _MAX_ID_LEN:
        raise AdaptiveComputeError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise AdaptiveComputeError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise AdaptiveComputeError(f"{name} must be a non-negative integer")
    return value


def _bounded_int(name: str, value: Any, *, maximum: int = _MAX_WORK) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise AdaptiveComputeError(f"{name} must be an integer in [0, {maximum}]")
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise AdaptiveComputeError(f"{name} must be an iterable of references")
    refs = tuple(sorted({_text(name, item) for item in values}))
    if not refs:
        raise AdaptiveComputeError(f"{name} must contain at least one reference")
    if len(refs) > _MAX_REFS:
        raise AdaptiveComputeError(f"{name} exceeds {_MAX_REFS} unique references")
    return refs


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CellWorkCap:
    cell_id: str
    max_work_units: int

    def __post_init__(self) -> None:
        if self.cell_id not in GRID10_CELL_IDS:
            raise AdaptiveComputeError(f"cell_id must be one of {GRID10_CELL_IDS}")
        object.__setattr__(
            self, "max_work_units", _bounded_int("max_work_units", self.max_work_units)
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True, init=False)
class AllocationRule:
    schema: str
    disposition: str
    max_active_cells: int
    max_total_work_units: int
    cell_priority: tuple[str, ...]
    cell_work_caps: tuple[CellWorkCap, ...]

    def __init__(
        self,
        *,
        schema: str,
        disposition: str,
        max_active_cells: int,
        max_total_work_units: int,
        cell_priority: Iterable[str],
        cell_work_caps: Iterable[CellWorkCap],
    ) -> None:
        if schema != RULE_SCHEMA:
            raise AdaptiveComputeError("allocation rule schema mismatch")
        if disposition not in _DISPOSITION_SET:
            raise AdaptiveComputeError(f"unsupported disposition {disposition!r}")
        active = _bounded_int("max_active_cells", max_active_cells, maximum=10)
        total = _bounded_int("max_total_work_units", max_total_work_units)
        priority = tuple(cell_priority)
        if (
            len(priority) != 10
            or set(priority) != set(GRID10_CELL_IDS)
            or len(set(priority)) != 10
        ):
            raise AdaptiveComputeError("cell_priority must contain each G1..G10 exactly once")
        raw_caps = tuple(cell_work_caps)
        if len(raw_caps) != 10 or any(type(cap) is not CellWorkCap for cap in raw_caps):
            raise AdaptiveComputeError(
                "cell_work_caps must contain exactly ten CellWorkCap values"
            )
        ids = [cap.cell_id for cap in raw_caps]
        if len(set(ids)) != 10 or set(ids) != set(GRID10_CELL_IDS):
            raise AdaptiveComputeError("cell_work_caps must contain each G1..G10 exactly once")
        by_id = {cap.cell_id: cap for cap in raw_caps}
        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "disposition", disposition)
        object.__setattr__(self, "max_active_cells", active)
        object.__setattr__(self, "max_total_work_units", total)
        object.__setattr__(self, "cell_priority", priority)
        object.__setattr__(
            self,
            "cell_work_caps",
            tuple(by_id[cell] for cell in GRID10_CELL_IDS),
        )

    @classmethod
    def create(
        cls,
        *,
        disposition: str,
        max_active_cells: int,
        max_total_work_units: int,
        cell_priority: Iterable[str],
        cell_work_caps: Iterable[CellWorkCap],
    ) -> "AllocationRule":
        return cls(
            schema=RULE_SCHEMA,
            disposition=disposition,
            max_active_cells=max_active_cells,
            max_total_work_units=max_total_work_units,
            cell_priority=cell_priority,
            cell_work_caps=cell_work_caps,
        )

    def cap_for(self, cell_id: str) -> int:
        if cell_id not in GRID10_CELL_IDS:
            raise AdaptiveComputeError(f"unknown GRID10 cell {cell_id!r}")
        return self.cell_work_caps[GRID10_CELL_IDS.index(cell_id)].max_work_units

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "disposition": self.disposition,
            "max_active_cells": self.max_active_cells,
            "max_total_work_units": self.max_total_work_units,
            "cell_priority": list(self.cell_priority),
            "cell_work_caps": [cap.as_dict() for cap in self.cell_work_caps],
        }


@dataclass(frozen=True, slots=True, init=False)
class AdaptiveComputePolicy:
    schema: str
    policy_id: str
    generation: int
    rules: tuple[AllocationRule, ...]
    provenance_refs: tuple[str, ...]

    def __init__(
        self,
        *,
        schema: str,
        policy_id: str,
        generation: int,
        rules: Iterable[AllocationRule],
        provenance_refs: Iterable[str],
    ) -> None:
        if schema != POLICY_SCHEMA:
            raise AdaptiveComputeError("adaptive compute policy schema mismatch")
        policy_id = _text("policy_id", policy_id)
        generation = _generation("policy generation", generation)
        raw = tuple(rules)
        if len(raw) != 4 or any(type(rule) is not AllocationRule for rule in raw):
            raise AdaptiveComputeError(
                "policy requires exactly four AllocationRule values"
            )
        dispositions = [rule.disposition for rule in raw]
        if len(set(dispositions)) != 4 or set(dispositions) != _DISPOSITION_SET:
            raise AdaptiveComputeError(
                "policy requires exactly one rule for each envelope disposition"
            )
        by_disposition = {rule.disposition: rule for rule in raw}
        degraded = by_disposition[DISPOSITION_DEGRADED]
        for conservative_name in (DISPOSITION_HARD_LIMIT, DISPOSITION_UNKNOWN):
            conservative = by_disposition[conservative_name]
            if conservative.max_active_cells > degraded.max_active_cells:
                raise AdaptiveComputeError(
                    f"{conservative_name} max_active_cells must not exceed DEGRADED"
                )
            if conservative.max_total_work_units > degraded.max_total_work_units:
                raise AdaptiveComputeError(
                    f"{conservative_name} max_total_work_units must not exceed DEGRADED"
                )
        refs = _refs("provenance_refs", provenance_refs)
        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(
            self,
            "rules",
            tuple(by_disposition[name] for name in _DISPOSITIONS),
        )
        object.__setattr__(self, "provenance_refs", refs)

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        generation: int,
        rules: Iterable[AllocationRule],
        provenance_refs: Iterable[str],
    ) -> "AdaptiveComputePolicy":
        return cls(
            schema=POLICY_SCHEMA,
            policy_id=policy_id,
            generation=generation,
            rules=rules,
            provenance_refs=provenance_refs,
        )

    def rule_for(self, disposition: str) -> AllocationRule:
        for rule in self.rules:
            if rule.disposition == disposition:
                return rule
        raise AdaptiveComputeError(f"no allocation rule for disposition {disposition!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "rules": [rule.as_dict() for rule in self.rules],
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class CellAllocation:
    schema: str
    cell_id: str
    role_label: str
    work_units_ceiling: int
    plan_cell_ceiling: int
    allocation_policy_ceiling: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ComputeAllocationCandidate:
    schema: str
    grid_plan_id: str
    grid_plan_generation: int
    grid_plan_sha256: str
    control_snapshot_sha256: str
    control_policy_id: str
    control_policy_generation: int
    control_policy_sha256: str
    adaptive_policy_id: str
    adaptive_policy_generation: int
    adaptive_policy_sha256: str
    disposition: str
    enabled_cells: tuple[CellAllocation, ...]
    deferred_cell_ids: tuple[str, ...]
    total_work_units_ceiling: int
    provenance_refs: tuple[str, ...]
    classification: str = (
        "ALLOCATION_CANDIDATE_ONLY_NOT_GRID_WRITER_OR_"
        "PHYSICAL_CONCURRENCY_EFFECT_COMPLETION_AUTHORITY"
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "grid_plan_id": self.grid_plan_id,
            "grid_plan_generation": self.grid_plan_generation,
            "grid_plan_sha256": self.grid_plan_sha256,
            "control_snapshot_sha256": self.control_snapshot_sha256,
            "control_policy_id": self.control_policy_id,
            "control_policy_generation": self.control_policy_generation,
            "control_policy_sha256": self.control_policy_sha256,
            "adaptive_policy_id": self.adaptive_policy_id,
            "adaptive_policy_generation": self.adaptive_policy_generation,
            "adaptive_policy_sha256": self.adaptive_policy_sha256,
            "disposition": self.disposition,
            "enabled_cells": [cell.as_dict() for cell in self.enabled_cells],
            "deferred_cell_ids": list(self.deferred_cell_ids),
            "total_work_units_ceiling": self.total_work_units_ceiling,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def build_allocation_candidate(
    plan: Grid10Plan,
    snapshot: ControlSnapshot,
    policy: AdaptiveComputePolicy,
) -> ComputeAllocationCandidate:
    """Build one bounded allocation candidate from exact explicit inputs only."""
    if type(plan) is not Grid10Plan:
        raise AdaptiveComputeError("plan must be concrete Grid10Plan")
    if type(snapshot) is not ControlSnapshot:
        raise AdaptiveComputeError("snapshot must be concrete ControlSnapshot")
    if type(policy) is not AdaptiveComputePolicy:
        raise AdaptiveComputeError("policy must be concrete AdaptiveComputePolicy")
    if plan.policy_id != snapshot.policy_id:
        raise AdaptiveComputeError("Grid10Plan/control snapshot policy_id mismatch")
    if plan.policy_generation != snapshot.policy_generation:
        raise AdaptiveComputeError(
            "Grid10Plan/control snapshot policy generation mismatch"
        )
    if plan.policy_sha256 != snapshot.policy_sha256:
        raise AdaptiveComputeError("Grid10Plan/control snapshot policy digest mismatch")

    rule = policy.rule_for(snapshot.disposition)
    remaining = min(rule.max_total_work_units, plan.max_total_work_units)
    enabled: list[CellAllocation] = []
    for cell_id in rule.cell_priority:
        if len(enabled) >= rule.max_active_cells or remaining <= 0:
            break
        plan_cell = plan.budget_for(cell_id)
        explicit_cap = rule.cap_for(cell_id)
        ceiling = min(plan_cell.max_work_units, explicit_cap, remaining)
        if ceiling <= 0:
            continue
        enabled.append(
            CellAllocation(
                schema=CELL_ALLOCATION_SCHEMA,
                cell_id=cell_id,
                role_label=plan_cell.role_label,
                work_units_ceiling=ceiling,
                plan_cell_ceiling=plan_cell.max_work_units,
                allocation_policy_ceiling=explicit_cap,
            )
        )
        remaining -= ceiling

    enabled_ids = {cell.cell_id for cell in enabled}
    deferred = tuple(
        cell_id for cell_id in GRID10_CELL_IDS if cell_id not in enabled_ids
    )
    total = sum(cell.work_units_ceiling for cell in enabled)
    provenance = tuple(sorted(set(plan.provenance_refs + policy.provenance_refs)))
    return ComputeAllocationCandidate(
        schema=ALLOCATION_SCHEMA,
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        control_snapshot_sha256=snapshot.sha256(),
        control_policy_id=snapshot.policy_id,
        control_policy_generation=snapshot.policy_generation,
        control_policy_sha256=snapshot.policy_sha256,
        adaptive_policy_id=policy.policy_id,
        adaptive_policy_generation=policy.generation,
        adaptive_policy_sha256=policy.sha256(),
        disposition=snapshot.disposition,
        enabled_cells=tuple(enabled),
        deferred_cell_ids=deferred,
        total_work_units_ceiling=total,
        provenance_refs=provenance,
    )


__all__ = [
    "ALLOCATION_SCHEMA",
    "AdaptiveComputeError",
    "AdaptiveComputePolicy",
    "AllocationRule",
    "CELL_ALLOCATION_SCHEMA",
    "CellAllocation",
    "CellWorkCap",
    "ComputeAllocationCandidate",
    "POLICY_SCHEMA",
    "RULE_SCHEMA",
    "build_allocation_candidate",
]
