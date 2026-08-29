"""Deterministic DIRECT_SMALL vs DELEGATE_BUILD routing candidate for Stage 6.

F2-WP-600 generation 1.

The router consumes only explicit bounded task-profile data, one exact concrete WP500
CycleContract, and one explicit routing policy. It emits a routing *candidate* only. It
never inspects task payload contents, spawns a child, calls a model/provider/tool, mutates
state, authorizes effects, or mints completion/runtime credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.situation_frame import CycleContract

TASK_PROFILE_SCHEMA = "FRANKENSTEIN2_DIRECT_DELEGATE_TASK_PROFILE/v1"
ROUTING_POLICY_SCHEMA = "FRANKENSTEIN2_DIRECT_DELEGATE_ROUTING_POLICY/v1"
ROUTE_DECISION_SCHEMA = "FRANKENSTEIN2_DIRECT_DELEGATE_ROUTE_DECISION/v1"
TASK_PROFILE_CLASSIFICATION = "EXPLICIT_TASK_BOUNDS_NOT_TASK_SEMANTICS_OR_WORLD_FACTS"
ROUTING_POLICY_CLASSIFICATION = "DETERMINISTIC_ROUTING_POLICY_NOT_EXECUTION_AUTHORITY"
ROUTE_DECISION_CLASSIFICATION = "ROUTING_CANDIDATE_NOT_CHILD_EXECUTION_IDENTITY_EFFECT_OR_COMPLETION_AUTHORITY"
DIRECT_SMALL = "DIRECT_SMALL"
DELEGATE_BUILD = "DELEGATE_BUILD"
_MAX_ID_LEN = 512
_MAX_REFS = 4096
_MAX_UNITS = 2**31 - 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DirectDelegateRouterError(ValueError):
    """Fail-closed validation error for the WP600 routing boundary."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise DirectDelegateRouterError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN:
        raise DirectDelegateRouterError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise DirectDelegateRouterError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise DirectDelegateRouterError(f"{name} must be a non-negative integer")
    return value


def _bounded(name: str, value: Any, *, maximum: int = _MAX_UNITS) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise DirectDelegateRouterError(f"{name} must be an integer in [0, {maximum}]")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise DirectDelegateRouterError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _boolean(name: str, value: Any) -> bool:
    if type(value) is not bool:
        raise DirectDelegateRouterError(f"{name} must be a concrete bool")
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise DirectDelegateRouterError(f"{name} must be an iterable of references")
    cleaned = tuple(_identifier(f"{name} item", value) for value in values)
    if len(cleaned) > _MAX_REFS:
        raise DirectDelegateRouterError(f"{name} exceeds {_MAX_REFS} references")
    if len(set(cleaned)) != len(cleaned):
        raise DirectDelegateRouterError(f"{name} must not contain duplicates")
    return tuple(sorted(cleaned))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DirectDelegateRouterError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskProfile:
    """Caller-declared bounded task shape; no task payload or semantic content."""

    schema: str
    task_id: str
    generation: int
    task_sha256: str
    cycle_contract_id: str
    cycle_generation: int
    cycle_contract_sha256: str
    declared_work_units: int
    declared_artifact_count: int
    declared_dependency_count: int
    recursion_depth: int
    direct_capability_admitted: bool
    provenance_refs: tuple[str, ...]
    classification: str = TASK_PROFILE_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != TASK_PROFILE_SCHEMA:
            raise DirectDelegateRouterError("task profile schema mismatch")
        if self.classification != TASK_PROFILE_CLASSIFICATION:
            raise DirectDelegateRouterError("task profile classification mismatch")
        object.__setattr__(self, "task_id", _identifier("task_id", self.task_id))
        _generation("generation", self.generation)
        object.__setattr__(self, "task_sha256", _sha256("task_sha256", self.task_sha256))
        object.__setattr__(
            self, "cycle_contract_id", _identifier("cycle_contract_id", self.cycle_contract_id)
        )
        _generation("cycle_generation", self.cycle_generation)
        object.__setattr__(
            self,
            "cycle_contract_sha256",
            _sha256("cycle_contract_sha256", self.cycle_contract_sha256),
        )
        _bounded("declared_work_units", self.declared_work_units)
        _bounded("declared_artifact_count", self.declared_artifact_count)
        _bounded("declared_dependency_count", self.declared_dependency_count)
        _bounded("recursion_depth", self.recursion_depth)
        _boolean("direct_capability_admitted", self.direct_capability_admitted)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))
        if not self.provenance_refs:
            raise DirectDelegateRouterError("provenance_refs must not be empty")

    @classmethod
    def for_cycle(
        cls,
        cycle_contract: CycleContract,
        *,
        task_id: str,
        generation: int,
        task_sha256: str,
        declared_work_units: int,
        declared_artifact_count: int,
        declared_dependency_count: int,
        recursion_depth: int,
        direct_capability_admitted: bool,
        provenance_refs: Iterable[str],
    ) -> "TaskProfile":
        if type(cycle_contract) is not CycleContract:
            raise DirectDelegateRouterError("cycle_contract must be concrete CycleContract")
        return cls(
            schema=TASK_PROFILE_SCHEMA,
            task_id=task_id,
            generation=generation,
            task_sha256=task_sha256,
            cycle_contract_id=cycle_contract.contract_id,
            cycle_generation=cycle_contract.cycle_generation,
            cycle_contract_sha256=cycle_contract.sha256(),
            declared_work_units=declared_work_units,
            declared_artifact_count=declared_artifact_count,
            declared_dependency_count=declared_dependency_count,
            recursion_depth=recursion_depth,
            direct_capability_admitted=direct_capability_admitted,
            provenance_refs=tuple(provenance_refs),
            classification=TASK_PROFILE_CLASSIFICATION,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "task_id": self.task_id,
            "generation": self.generation,
            "task_sha256": self.task_sha256,
            "cycle_contract_id": self.cycle_contract_id,
            "cycle_generation": self.cycle_generation,
            "cycle_contract_sha256": self.cycle_contract_sha256,
            "declared_work_units": self.declared_work_units,
            "declared_artifact_count": self.declared_artifact_count,
            "declared_dependency_count": self.declared_dependency_count,
            "recursion_depth": self.recursion_depth,
            "direct_capability_admitted": self.direct_capability_admitted,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class RoutingPolicy:
    schema: str
    policy_id: str
    generation: int
    max_direct_work_units: int
    max_direct_artifacts: int
    max_direct_dependencies: int
    max_recursion_depth: int
    direct_route_enabled: bool
    provenance_refs: tuple[str, ...]
    classification: str = ROUTING_POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != ROUTING_POLICY_SCHEMA:
            raise DirectDelegateRouterError("routing policy schema mismatch")
        if self.classification != ROUTING_POLICY_CLASSIFICATION:
            raise DirectDelegateRouterError("routing policy classification mismatch")
        object.__setattr__(self, "policy_id", _identifier("policy_id", self.policy_id))
        _generation("generation", self.generation)
        _bounded("max_direct_work_units", self.max_direct_work_units)
        _bounded("max_direct_artifacts", self.max_direct_artifacts)
        _bounded("max_direct_dependencies", self.max_direct_dependencies)
        _bounded("max_recursion_depth", self.max_recursion_depth)
        _boolean("direct_route_enabled", self.direct_route_enabled)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))
        if not self.provenance_refs:
            raise DirectDelegateRouterError("policy provenance_refs must not be empty")

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        generation: int,
        max_direct_work_units: int,
        max_direct_artifacts: int,
        max_direct_dependencies: int,
        max_recursion_depth: int,
        direct_route_enabled: bool,
        provenance_refs: Iterable[str],
    ) -> "RoutingPolicy":
        return cls(
            schema=ROUTING_POLICY_SCHEMA,
            policy_id=policy_id,
            generation=generation,
            max_direct_work_units=max_direct_work_units,
            max_direct_artifacts=max_direct_artifacts,
            max_direct_dependencies=max_direct_dependencies,
            max_recursion_depth=max_recursion_depth,
            direct_route_enabled=direct_route_enabled,
            provenance_refs=tuple(provenance_refs),
            classification=ROUTING_POLICY_CLASSIFICATION,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "max_direct_work_units": self.max_direct_work_units,
            "max_direct_artifacts": self.max_direct_artifacts,
            "max_direct_dependencies": self.max_direct_dependencies,
            "max_recursion_depth": self.max_recursion_depth,
            "direct_route_enabled": self.direct_route_enabled,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class RouteDecision:
    schema: str
    decision_id: str
    task_id: str
    task_generation: int
    task_sha256: str
    task_profile_sha256: str
    cycle_contract_id: str
    cycle_generation: int
    cycle_contract_sha256: str
    policy_id: str
    policy_generation: int
    policy_sha256: str
    route: str
    reason_codes: tuple[str, ...]
    classification: str = ROUTE_DECISION_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != ROUTE_DECISION_SCHEMA:
            raise DirectDelegateRouterError("route decision schema mismatch")
        if self.classification != ROUTE_DECISION_CLASSIFICATION:
            raise DirectDelegateRouterError("route decision classification mismatch")
        object.__setattr__(self, "decision_id", _identifier("decision_id", self.decision_id))
        object.__setattr__(self, "task_id", _identifier("task_id", self.task_id))
        _generation("task_generation", self.task_generation)
        object.__setattr__(self, "task_sha256", _sha256("task_sha256", self.task_sha256))
        object.__setattr__(
            self, "task_profile_sha256", _sha256("task_profile_sha256", self.task_profile_sha256)
        )
        object.__setattr__(
            self, "cycle_contract_id", _identifier("cycle_contract_id", self.cycle_contract_id)
        )
        _generation("cycle_generation", self.cycle_generation)
        object.__setattr__(
            self,
            "cycle_contract_sha256",
            _sha256("cycle_contract_sha256", self.cycle_contract_sha256),
        )
        object.__setattr__(self, "policy_id", _identifier("policy_id", self.policy_id))
        _generation("policy_generation", self.policy_generation)
        object.__setattr__(self, "policy_sha256", _sha256("policy_sha256", self.policy_sha256))
        if self.route not in {DIRECT_SMALL, DELEGATE_BUILD}:
            raise DirectDelegateRouterError("route must be DIRECT_SMALL or DELEGATE_BUILD")
        reasons = tuple(_identifier("reason_code", value) for value in self.reason_codes)
        if not reasons or len(set(reasons)) != len(reasons):
            raise DirectDelegateRouterError("reason_codes must be non-empty and unique")
        object.__setattr__(self, "reason_codes", tuple(sorted(reasons)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "decision_id": self.decision_id,
            "task_id": self.task_id,
            "task_generation": self.task_generation,
            "task_sha256": self.task_sha256,
            "task_profile_sha256": self.task_profile_sha256,
            "cycle_contract_id": self.cycle_contract_id,
            "cycle_generation": self.cycle_generation,
            "cycle_contract_sha256": self.cycle_contract_sha256,
            "policy_id": self.policy_id,
            "policy_generation": self.policy_generation,
            "policy_sha256": self.policy_sha256,
            "route": self.route,
            "reason_codes": list(self.reason_codes),
            "classification": self.classification,
            "child_identity_minted": False,
            "execution_observed": False,
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def route_task(
    *,
    decision_id: str,
    task_profile: TaskProfile,
    cycle_contract: CycleContract,
    policy: RoutingPolicy,
) -> RouteDecision:
    """Return one deterministic routing candidate bound to exact input identities."""
    if type(task_profile) is not TaskProfile:
        raise DirectDelegateRouterError("task_profile must be concrete TaskProfile")
    if type(cycle_contract) is not CycleContract:
        raise DirectDelegateRouterError("cycle_contract must be concrete CycleContract")
    if type(policy) is not RoutingPolicy:
        raise DirectDelegateRouterError("policy must be concrete RoutingPolicy")

    contract_sha = cycle_contract.sha256()
    if task_profile.cycle_contract_id != cycle_contract.contract_id:
        raise DirectDelegateRouterError("cycle contract id mismatch")
    if task_profile.cycle_generation != cycle_contract.cycle_generation:
        raise DirectDelegateRouterError("cycle contract generation mismatch")
    if task_profile.cycle_contract_sha256 != contract_sha:
        raise DirectDelegateRouterError("cycle contract digest mismatch")
    if task_profile.recursion_depth > policy.max_recursion_depth:
        raise DirectDelegateRouterError("recursion depth exceeds policy limit")

    reasons: list[str] = []
    if not task_profile.direct_capability_admitted:
        reasons.append("DIRECT_CAPABILITY_NOT_ADMITTED")
    if not policy.direct_route_enabled:
        reasons.append("DIRECT_ROUTE_DISABLED")
    if task_profile.declared_work_units > policy.max_direct_work_units:
        reasons.append("DIRECT_WORK_BOUND_EXCEEDED")
    if task_profile.declared_artifact_count > policy.max_direct_artifacts:
        reasons.append("DIRECT_ARTIFACT_BOUND_EXCEEDED")
    if task_profile.declared_dependency_count > policy.max_direct_dependencies:
        reasons.append("DIRECT_DEPENDENCY_BOUND_EXCEEDED")

    if reasons:
        route = DELEGATE_BUILD
    else:
        route = DIRECT_SMALL
        reasons.append("ALL_DIRECT_BOUNDS_ADMITTED")

    return RouteDecision(
        schema=ROUTE_DECISION_SCHEMA,
        decision_id=decision_id,
        task_id=task_profile.task_id,
        task_generation=task_profile.generation,
        task_sha256=task_profile.task_sha256,
        task_profile_sha256=task_profile.sha256(),
        cycle_contract_id=cycle_contract.contract_id,
        cycle_generation=cycle_contract.cycle_generation,
        cycle_contract_sha256=contract_sha,
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=policy.sha256(),
        route=route,
        reason_codes=tuple(reasons),
        classification=ROUTE_DECISION_CLASSIFICATION,
    )
