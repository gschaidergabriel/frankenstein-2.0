"""Bind Perception Fabric worker ceilings to the canonical Cognitive Envelope path.

Perception must not create an independent resource governor. This module derives a bounded
PerceptionWorkerPolicy from one exact ControlSnapshot plus its exact adaptive-compute
allocation candidate and an explicit perception-share policy. It performs no perception,
GRID mutation, scheduling, model call, effect or persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, ClassVar

from .adaptive_compute import ComputeAllocationCandidate
from .cognitive_envelope import (
    ControlSnapshot,
    DISPOSITION_DEGRADED,
    DISPOSITION_HARD_LIMIT,
    DISPOSITION_UNKNOWN,
    DISPOSITION_WITHIN,
)
from .perception_fabric import PerceptionWorkerPolicy

PERCEPTION_ENVELOPE_RULE_SCHEMA = "FRANKENSTEIN2_PERCEPTION_ENVELOPE_RULE/v1"
PERCEPTION_COMPUTE_BINDING_SCHEMA = "FRANKENSTEIN2_PERCEPTION_COMPUTE_BINDING_POLICY/v1"
_DISPOSITIONS = (
    DISPOSITION_WITHIN,
    DISPOSITION_DEGRADED,
    DISPOSITION_HARD_LIMIT,
    DISPOSITION_UNKNOWN,
)


class PerceptionComputeBindingError(ValueError):
    """Fail-closed Perception/Cognitive-Envelope binding error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise PerceptionComputeBindingError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PerceptionComputeBindingError(f"{name} must not contain control characters")
    return value


def _nonnegative(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PerceptionComputeBindingError(f"{name} must be an integer >= 0")
    return value


def _micros(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise PerceptionComputeBindingError(f"{name} must be an integer in [0, 1000000]")
    return value


def _refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise PerceptionComputeBindingError(f"{name} must be a non-empty immutable tuple")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise PerceptionComputeBindingError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionEnvelopeRule:
    disposition: str
    max_active_workers: int
    max_perception_work_units: int
    max_share_micros: int

    schema: ClassVar[str] = PERCEPTION_ENVELOPE_RULE_SCHEMA

    def __post_init__(self) -> None:
        if self.disposition not in _DISPOSITIONS:
            raise PerceptionComputeBindingError("unsupported cognitive-envelope disposition")
        if type(self.max_active_workers) is not int or not 0 <= self.max_active_workers <= 4:
            raise PerceptionComputeBindingError("max_active_workers must be an integer in [0, 4]")
        _nonnegative("max_perception_work_units", self.max_perception_work_units)
        _micros("max_share_micros", self.max_share_micros)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "disposition": self.disposition,
            "max_active_workers": self.max_active_workers,
            "max_perception_work_units": self.max_perception_work_units,
            "max_share_micros": self.max_share_micros,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionComputeBindingPolicy:
    policy_id: str
    generation: int
    rules: tuple[PerceptionEnvelopeRule, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = PERCEPTION_COMPUTE_BINDING_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_SHARE_POLICY_NOT_CONTROL_WRITER_OR_EXECUTION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _nonnegative("generation", self.generation)
        if type(self.rules) is not tuple or len(self.rules) != 4:
            raise PerceptionComputeBindingError("rules must contain exactly four disposition rules")
        if any(type(rule) is not PerceptionEnvelopeRule for rule in self.rules):
            raise PerceptionComputeBindingError("rules must contain concrete PerceptionEnvelopeRule values")
        by_disposition = {rule.disposition: rule for rule in self.rules}
        if len(by_disposition) != 4 or set(by_disposition) != set(_DISPOSITIONS):
            raise PerceptionComputeBindingError("rules must contain each Cognitive Envelope disposition exactly once")
        degraded = by_disposition[DISPOSITION_DEGRADED]
        for disposition in (DISPOSITION_HARD_LIMIT, DISPOSITION_UNKNOWN):
            rule = by_disposition[disposition]
            if rule.max_active_workers > degraded.max_active_workers:
                raise PerceptionComputeBindingError(f"{disposition} worker ceiling must not exceed DEGRADED")
            if rule.max_perception_work_units > degraded.max_perception_work_units:
                raise PerceptionComputeBindingError(f"{disposition} work ceiling must not exceed DEGRADED")
            if rule.max_share_micros > degraded.max_share_micros:
                raise PerceptionComputeBindingError(f"{disposition} share ceiling must not exceed DEGRADED")
        object.__setattr__(self, "rules", tuple(by_disposition[item] for item in _DISPOSITIONS))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def rule_for(self, disposition: str) -> PerceptionEnvelopeRule:
        return self.rules[_DISPOSITIONS.index(disposition)]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "rules": [item.as_dict() for item in self.rules],
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def derive_perception_worker_policy(
    *,
    control_snapshot: ControlSnapshot,
    adaptive_allocation: ComputeAllocationCandidate,
    binding_policy: PerceptionComputeBindingPolicy,
) -> PerceptionWorkerPolicy:
    """Derive the only admissible Perception worker ceiling for one latched cycle.

    The output can only shrink below the explicit share rule and exact adaptive-compute
    candidate. It never increases the canonical allocation or turns a candidate into runtime.
    """
    if type(control_snapshot) is not ControlSnapshot:
        raise PerceptionComputeBindingError("control_snapshot must be a concrete ControlSnapshot")
    if type(adaptive_allocation) is not ComputeAllocationCandidate:
        raise PerceptionComputeBindingError("adaptive_allocation must be a concrete ComputeAllocationCandidate")
    if type(binding_policy) is not PerceptionComputeBindingPolicy:
        raise PerceptionComputeBindingError("binding_policy must be a concrete PerceptionComputeBindingPolicy")
    snapshot_sha = control_snapshot.sha256()
    if adaptive_allocation.control_snapshot_sha256 != snapshot_sha:
        raise PerceptionComputeBindingError("adaptive allocation does not bind the exact ControlSnapshot")
    if adaptive_allocation.disposition != control_snapshot.disposition:
        raise PerceptionComputeBindingError("adaptive allocation disposition mismatches ControlSnapshot")
    rule = binding_policy.rule_for(control_snapshot.disposition)
    adaptive_work = adaptive_allocation.total_work_units_ceiling
    share_ceiling = (adaptive_work * rule.max_share_micros) // 1_000_000
    perception_work = min(rule.max_perception_work_units, share_ceiling)
    workers = rule.max_active_workers if perception_work > 0 else 0
    provenance = set(binding_policy.provenance_refs)
    provenance.update(adaptive_allocation.provenance_refs)
    provenance.add(f"control-snapshot-sha256:{snapshot_sha}")
    provenance.add(f"adaptive-allocation-sha256:{adaptive_allocation.sha256()}")
    provenance.add(f"perception-binding-policy-sha256:{binding_policy.sha256()}")
    return PerceptionWorkerPolicy(
        policy_id=(
            f"perception-envelope:{binding_policy.policy_id}:"
            f"{control_snapshot.policy_id}:{control_snapshot.policy_generation}:"
            f"{control_snapshot.disposition}"
        ),
        generation=binding_policy.generation,
        max_active_workers=workers,
        max_total_work_units=perception_work,
        provenance_refs=tuple(sorted(provenance)),
    )


__all__ = [
    "PERCEPTION_COMPUTE_BINDING_SCHEMA",
    "PERCEPTION_ENVELOPE_RULE_SCHEMA",
    "PerceptionComputeBindingError",
    "PerceptionComputeBindingPolicy",
    "PerceptionEnvelopeRule",
    "derive_perception_worker_policy",
]
