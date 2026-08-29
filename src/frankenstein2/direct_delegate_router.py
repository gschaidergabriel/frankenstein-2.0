"""Deterministic DIRECT_SMALL vs DELEGATE_BUILD routing candidate for Frankenstein 2.0.

F2-WP-600 generation 1.

This component is deliberately persistence-agnostic and authority-free. It binds one
explicit caller-supplied task profile to one exact F2-WP-500 CycleContract and one explicit
routing policy, then emits only an immutable route candidate. It does not inspect task
payloads, infer complexity or semantics, spawn a child, execute tools/models/providers,
read/write UnifiedDB, authorize effects/completion, or mint runtime/GWT/GRID credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from .situation_frame import CycleContract

TASK_ROUTE_REQUEST_SCHEMA = "FRANKENSTEIN2_TASK_ROUTE_REQUEST/v1"
ROUTING_POLICY_SCHEMA = "FRANKENSTEIN2_DIRECT_DELEGATE_POLICY/v1"
ROUTE_CANDIDATE_SCHEMA = "FRANKENSTEIN2_DIRECT_DELEGATE_ROUTE_CANDIDATE/v1"
ROUTE_CANDIDATE_CLASSIFICATION = "ROUTE_CANDIDATE_NOT_CHILD_EFFECT_OR_COMPLETION_AUTHORITY"
DIRECT_SMALL = "DIRECT_SMALL"
DELEGATE_BUILD = "DELEGATE_BUILD"
_ROUTE_ORDER = (DIRECT_SMALL, DELEGATE_BUILD)
_ALLOWED_ROUTES = frozenset(_ROUTE_ORDER)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_REF_COUNT = 4096
_MAX_WORK_UNITS = 1_000_000_000
_MAX_CONTEXT_TOKENS = 100_000_000


class DirectDelegateRouterError(ValueError):
    """Fail-closed route-request/policy/candidate validation error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise DirectDelegateRouterError(f"{name} must be a string")
    if not value or value != value.strip():
        raise DirectDelegateRouterError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise DirectDelegateRouterError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise DirectDelegateRouterError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise DirectDelegateRouterError(f"{name} must be a non-negative integer")
    return value


def _bounded_int(name: str, value: Any, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise DirectDelegateRouterError(f"{name} must be an integer in [0, {maximum}]")
    return value


def _boolean(name: str, value: Any) -> bool:
    if type(value) is not bool:
        raise DirectDelegateRouterError(f"{name} must be a boolean")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise DirectDelegateRouterError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str], *, require_nonempty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise DirectDelegateRouterError(f"{name} must be an iterable of reference strings")
    cleaned = tuple(sorted({_identifier(name, value) for value in values}))
    if len(cleaned) > _MAX_REF_COUNT:
        raise DirectDelegateRouterError(f"{name} exceeds {_MAX_REF_COUNT} unique references")
    if require_nonempty and not cleaned:
        raise DirectDelegateRouterError(f"{name} must contain at least one explicit reference")
    return cleaned


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _route_candidate_identity_payload(
    *,
    task_id: str,
    task_generation: int,
    task_sha256: str,
    request_sha256: str,
    cycle_contract_id: str,
    cycle_generation: int,
    cycle_contract_sha256: str,
    policy_id: str,
    policy_generation: int,
    policy_sha256: str,
    selected_route: str,
    reason_codes: Iterable[str],
) -> dict[str, Any]:
    """Return the exact immutable content bound by ``RouteCandidate.candidate_id``."""
    return {
        "task_id": task_id,
        "task_generation": task_generation,
        "task_sha256": task_sha256,
        "request_sha256": request_sha256,
        "cycle_contract_id": cycle_contract_id,
        "cycle_generation": cycle_generation,
        "cycle_contract_sha256": cycle_contract_sha256,
        "policy_id": policy_id,
        "policy_generation": policy_generation,
        "policy_sha256": policy_sha256,
        "selected_route": selected_route,
        "reason_codes": list(reason_codes),
    }


def _route_candidate_id(**identity_fields: Any) -> str:
    return "route:" + _digest(_route_candidate_identity_payload(**identity_fields))


@dataclass(frozen=True, slots=True)
class TaskRouteRequest:
    """Explicit task-shape claims bound to one exact cognitive cycle contract.

    The shape fields are caller assertions. This component validates their type/range but
    does not infer or verify whether the task really has those properties.
    """

    schema: str
    task_id: str
    task_generation: int
    task_sha256: str
    cycle_contract_id: str
    cycle_id: str
    cycle_generation: int
    cycle_contract_sha256: str
    estimated_work_units: int
    estimated_context_tokens: int
    requires_child_context_isolation: bool
    requires_parallelism: bool
    requires_long_horizon: bool
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != TASK_ROUTE_REQUEST_SCHEMA:
            raise DirectDelegateRouterError("task route request schema mismatch")
        object.__setattr__(self, "task_id", _identifier("task_id", self.task_id))
        object.__setattr__(self, "task_generation", _generation("task_generation", self.task_generation))
        object.__setattr__(self, "task_sha256", _sha256("task_sha256", self.task_sha256))
        object.__setattr__(self, "cycle_contract_id", _identifier("cycle_contract_id", self.cycle_contract_id))
        object.__setattr__(self, "cycle_id", _identifier("cycle_id", self.cycle_id))
        object.__setattr__(self, "cycle_generation", _generation("cycle_generation", self.cycle_generation))
        object.__setattr__(self, "cycle_contract_sha256", _sha256("cycle_contract_sha256", self.cycle_contract_sha256))
        object.__setattr__(self, "estimated_work_units", _bounded_int("estimated_work_units", self.estimated_work_units, _MAX_WORK_UNITS))
        object.__setattr__(self, "estimated_context_tokens", _bounded_int("estimated_context_tokens", self.estimated_context_tokens, _MAX_CONTEXT_TOKENS))
        object.__setattr__(self, "requires_child_context_isolation", _boolean("requires_child_context_isolation", self.requires_child_context_isolation))
        object.__setattr__(self, "requires_parallelism", _boolean("requires_parallelism", self.requires_parallelism))
        object.__setattr__(self, "requires_long_horizon", _boolean("requires_long_horizon", self.requires_long_horizon))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs, require_nonempty=True))

    @classmethod
    def for_cycle(
        cls,
        cycle_contract: CycleContract,
        *,
        task_id: str,
        task_generation: int,
        task_sha256: str,
        estimated_work_units: int,
        estimated_context_tokens: int,
        requires_child_context_isolation: bool = False,
        requires_parallelism: bool = False,
        requires_long_horizon: bool = False,
        provenance_refs: Iterable[str],
    ) -> "TaskRouteRequest":
        if type(cycle_contract) is not CycleContract:
            raise DirectDelegateRouterError("cycle_contract must be concrete CycleContract")
        return cls(
            schema=TASK_ROUTE_REQUEST_SCHEMA,
            task_id=task_id,
            task_generation=task_generation,
            task_sha256=task_sha256,
            cycle_contract_id=cycle_contract.contract_id,
            cycle_id=cycle_contract.cycle_id,
            cycle_generation=cycle_contract.cycle_generation,
            cycle_contract_sha256=cycle_contract.sha256(),
            estimated_work_units=estimated_work_units,
            estimated_context_tokens=estimated_context_tokens,
            requires_child_context_isolation=requires_child_context_isolation,
            requires_parallelism=requires_parallelism,
            requires_long_horizon=requires_long_horizon,
            provenance_refs=tuple(provenance_refs),
        )

    def assert_matches(self, cycle_contract: CycleContract) -> None:
        if type(cycle_contract) is not CycleContract:
            raise DirectDelegateRouterError("cycle_contract must be concrete CycleContract")
        if self.cycle_contract_id != cycle_contract.contract_id:
            raise DirectDelegateRouterError("cycle contract id mismatch")
        if self.cycle_id != cycle_contract.cycle_id:
            raise DirectDelegateRouterError("cycle id mismatch")
        if self.cycle_generation != cycle_contract.cycle_generation:
            raise DirectDelegateRouterError("cycle generation mismatch")
        if self.cycle_contract_sha256 != cycle_contract.sha256():
            raise DirectDelegateRouterError("cycle contract digest mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    """Explicit deterministic bounds; policy does not grant execution authority."""

    schema: str
    policy_id: str
    generation: int
    max_direct_work_units: int
    max_direct_context_tokens: int
    allowed_routes: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != ROUTING_POLICY_SCHEMA:
            raise DirectDelegateRouterError("routing policy schema mismatch")
        object.__setattr__(self, "policy_id", _identifier("policy_id", self.policy_id))
        object.__setattr__(self, "generation", _generation("policy generation", self.generation))
        object.__setattr__(self, "max_direct_work_units", _bounded_int("max_direct_work_units", self.max_direct_work_units, _MAX_WORK_UNITS))
        object.__setattr__(self, "max_direct_context_tokens", _bounded_int("max_direct_context_tokens", self.max_direct_context_tokens, _MAX_CONTEXT_TOKENS))
        routes = tuple(self.allowed_routes)
        if not routes:
            raise DirectDelegateRouterError("allowed_routes must contain at least one route")
        if any(route not in _ALLOWED_ROUTES for route in routes):
            raise DirectDelegateRouterError(f"allowed_routes must be a subset of {list(_ROUTE_ORDER)}")
        object.__setattr__(self, "allowed_routes", tuple(route for route in _ROUTE_ORDER if route in set(routes)))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs, require_nonempty=True))

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        generation: int,
        max_direct_work_units: int,
        max_direct_context_tokens: int,
        allowed_routes: Iterable[str] = _ROUTE_ORDER,
        provenance_refs: Iterable[str],
    ) -> "RoutingPolicy":
        return cls(
            schema=ROUTING_POLICY_SCHEMA,
            policy_id=policy_id,
            generation=generation,
            max_direct_work_units=max_direct_work_units,
            max_direct_context_tokens=max_direct_context_tokens,
            allowed_routes=tuple(allowed_routes),
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    """Non-authoritative route proposal bound to exact request/cycle/policy identities."""

    schema: str
    candidate_id: str
    task_id: str
    task_generation: int
    task_sha256: str
    request_sha256: str
    cycle_contract_id: str
    cycle_generation: int
    cycle_contract_sha256: str
    policy_id: str
    policy_generation: int
    policy_sha256: str
    selected_route: str
    reason_codes: tuple[str, ...]
    classification: str = ROUTE_CANDIDATE_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != ROUTE_CANDIDATE_SCHEMA:
            raise DirectDelegateRouterError("route candidate schema mismatch")
        if self.classification != ROUTE_CANDIDATE_CLASSIFICATION:
            raise DirectDelegateRouterError("route candidate classification mismatch")
        object.__setattr__(self, "candidate_id", _identifier("candidate_id", self.candidate_id))
        object.__setattr__(self, "task_id", _identifier("task_id", self.task_id))
        object.__setattr__(self, "task_generation", _generation("task_generation", self.task_generation))
        object.__setattr__(self, "task_sha256", _sha256("task_sha256", self.task_sha256))
        object.__setattr__(self, "request_sha256", _sha256("request_sha256", self.request_sha256))
        object.__setattr__(self, "cycle_contract_id", _identifier("cycle_contract_id", self.cycle_contract_id))
        object.__setattr__(self, "cycle_generation", _generation("cycle_generation", self.cycle_generation))
        object.__setattr__(self, "cycle_contract_sha256", _sha256("cycle_contract_sha256", self.cycle_contract_sha256))
        object.__setattr__(self, "policy_id", _identifier("policy_id", self.policy_id))
        object.__setattr__(self, "policy_generation", _generation("policy_generation", self.policy_generation))
        object.__setattr__(self, "policy_sha256", _sha256("policy_sha256", self.policy_sha256))
        if self.selected_route not in _ALLOWED_ROUTES:
            raise DirectDelegateRouterError("selected_route is invalid")
        object.__setattr__(self, "reason_codes", _refs("reason_codes", self.reason_codes, require_nonempty=True))
        expected_candidate_id = _route_candidate_id(
            task_id=self.task_id,
            task_generation=self.task_generation,
            task_sha256=self.task_sha256,
            request_sha256=self.request_sha256,
            cycle_contract_id=self.cycle_contract_id,
            cycle_generation=self.cycle_generation,
            cycle_contract_sha256=self.cycle_contract_sha256,
            policy_id=self.policy_id,
            policy_generation=self.policy_generation,
            policy_sha256=self.policy_sha256,
            selected_route=self.selected_route,
            reason_codes=self.reason_codes,
        )
        if self.candidate_id != expected_candidate_id:
            raise DirectDelegateRouterError("candidate_id does not bind exact route candidate content")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def route_task(
    *,
    cycle_contract: CycleContract,
    request: TaskRouteRequest,
    policy: RoutingPolicy,
) -> RouteCandidate:
    """Return one deterministic non-authoritative route candidate.

    DIRECT_SMALL requires every explicit direct-work constraint to be satisfied. Any explicit
    boundary exceedance or child-isolation/parallel/long-horizon requirement routes to
    DELEGATE_BUILD when that route is policy-admitted; otherwise the function fails closed.
    """

    if type(cycle_contract) is not CycleContract:
        raise DirectDelegateRouterError("cycle_contract must be concrete CycleContract")
    if type(request) is not TaskRouteRequest:
        raise DirectDelegateRouterError("request must be concrete TaskRouteRequest")
    if type(policy) is not RoutingPolicy:
        raise DirectDelegateRouterError("policy must be concrete RoutingPolicy")
    request.assert_matches(cycle_contract)

    delegate_reasons: list[str] = []
    if request.estimated_work_units > policy.max_direct_work_units:
        delegate_reasons.append("WORK_UNITS_EXCEED_DIRECT_BOUND")
    if request.estimated_context_tokens > policy.max_direct_context_tokens:
        delegate_reasons.append("CONTEXT_EXCEEDS_DIRECT_BOUND")
    if request.requires_child_context_isolation:
        delegate_reasons.append("CHILD_CONTEXT_ISOLATION_REQUIRED")
    if request.requires_parallelism:
        delegate_reasons.append("PARALLELISM_REQUIRED")
    if request.requires_long_horizon:
        delegate_reasons.append("LONG_HORIZON_REQUIRED")

    if not delegate_reasons and DIRECT_SMALL in policy.allowed_routes:
        selected_route = DIRECT_SMALL
        reasons = ("DIRECT_BOUNDS_SATISFIED",)
    else:
        if not delegate_reasons:
            delegate_reasons.append("DIRECT_ROUTE_NOT_ALLOWED")
        if DELEGATE_BUILD not in policy.allowed_routes:
            raise DirectDelegateRouterError("task requires delegation but DELEGATE_BUILD is not policy-admitted")
        selected_route = DELEGATE_BUILD
        reasons = tuple(sorted(set(delegate_reasons)))

    request_sha = request.sha256()
    cycle_sha = cycle_contract.sha256()
    policy_sha = policy.sha256()
    candidate_id = _route_candidate_id(
        task_id=request.task_id,
        task_generation=request.task_generation,
        task_sha256=request.task_sha256,
        request_sha256=request_sha,
        cycle_contract_id=cycle_contract.contract_id,
        cycle_generation=cycle_contract.cycle_generation,
        cycle_contract_sha256=cycle_sha,
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=policy_sha,
        selected_route=selected_route,
        reason_codes=reasons,
    )
    return RouteCandidate(
        schema=ROUTE_CANDIDATE_SCHEMA,
        candidate_id=candidate_id,
        task_id=request.task_id,
        task_generation=request.task_generation,
        task_sha256=request.task_sha256,
        request_sha256=request_sha,
        cycle_contract_id=cycle_contract.contract_id,
        cycle_generation=cycle_contract.cycle_generation,
        cycle_contract_sha256=cycle_sha,
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=policy_sha,
        selected_route=selected_route,
        reason_codes=reasons,
        classification=ROUTE_CANDIDATE_CLASSIFICATION,
    )
