"""F2-WP-603 generation-2 deterministic recursion-strategy router.

Canonical Stage-6 semantics are strategy classes, not recursion depths:

    R0 = deterministic local path
    R1 = model-recursion candidate
    R2 = Native Child harness candidate
    R3 = adaptive selection of one explicit R0/R1/R2 strategy

Nesting depth is orthogonal. ``remaining_nested_child_edges`` means the number of
additional Native Child edges allowed *below* the immediate R2 child. Therefore an
immediate R2 child is valid with ``remaining_nested_child_edges == 0`` and
``NativeChildRequest.resource_budget.max_nested_depth == 0``. A nested R2 reroute
must bind an exact parent recursion candidate and consume one remaining edge.

R3 never silently infers or chooses a strategy from payload semantics. The caller must
supply an explicit selected lower strategy plus exact decision identity/digest and
provenance references; all are content-bound into the need and output candidate.

All content-bound inputs are reconstructed/revalidated at the consumer boundary. This
closes post-construction mutation gaps where a stale declared content id could otherwise
be paired with changed fields. Integer fields are admitted only when they survive the
same canonical JSON domain used by hashing.

This module emits evidence/provenance candidates only. It does not spawn children,
invoke models/providers/tools, transport payloads, grant capabilities, read/write
UnifiedDB, authorize effects/completion, infer world facts, or mint runtime/GRID/GWT/
J-Space/training/whole-system credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from .direct_delegate_router import DELEGATE_BUILD, DIRECT_SMALL, RouteCandidate
from .native_child_abi import NativeChildRequest, verify_native_child_request

RECURSION_NEED_SCHEMA = "FRANKENSTEIN2_RECURSION_NEED/v3"
RECURSION_POLICY_SCHEMA = "FRANKENSTEIN2_RECURSION_POLICY/v3"
RECURSION_ROUTE_CANDIDATE_SCHEMA = "FRANKENSTEIN2_RECURSION_ROUTE_CANDIDATE/v3"
RECURSION_ROUTE_CLASSIFICATION = (
    "EVIDENCE_ONLY_NOT_MODEL_OR_CHILD_EXECUTION_TRANSPORT_EFFECT_OR_COMPLETION_AUTHORITY"
)

R0 = "R0"
R1 = "R1"
R2 = "R2"
R3 = "R3"
R0_DETERMINISTIC = R0
R1_MODEL_RECURSION = R1
R2_CHILD_HARNESS = R2
R3_ADAPTIVE_SELECTION = R3
_STRATEGY_ORDER = (R0, R1, R2, R3)
_LOWER_STRATEGY_ORDER = (R0, R1, R2)
_ALLOWED_STRATEGIES = frozenset(_STRATEGY_ORDER)
_ALLOWED_LOWER_STRATEGIES = frozenset(_LOWER_STRATEGY_ORDER)
_MAX_NESTED_CHILD_EDGES = 3
_MAX_IDENTIFIER_LENGTH = 512
_MAX_REF_COUNT = 4096
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RecursionRouterError(ValueError):
    """Fail-closed WP603 strategy/depth/identity admission error."""


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
        raise RecursionRouterError("value is outside the canonical JSON domain") from exc


def _canonical_json_integer(name: str, value: int) -> int:
    try:
        _canonical_json(value)
    except RecursionRouterError as exc:
        raise RecursionRouterError(
            f"{name} is outside the canonical JSON integer domain"
        ) from exc
    return value


def _identifier(name: str, value: Any) -> str:
    if type(value) is not str:
        raise RecursionRouterError(f"{name} must be an exact concrete string")
    if not value or value != value.strip():
        raise RecursionRouterError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise RecursionRouterError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RecursionRouterError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise RecursionRouterError(f"{name} must be a non-negative integer")
    return _canonical_json_integer(name, value)


def _remaining_edges(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_NESTED_CHILD_EDGES:
        raise RecursionRouterError(
            f"{name} must be an exact integer in [0, {_MAX_NESTED_CHILD_EDGES}]"
        )
    return _canonical_json_integer(name, value)


def _strategy(name: str, value: Any, *, allow_r3: bool = True) -> str:
    allowed = _ALLOWED_STRATEGIES if allow_r3 else _ALLOWED_LOWER_STRATEGIES
    if type(value) is not str or value not in allowed:
        suffix = "R0/R1/R2/R3" if allow_r3 else "R0/R1/R2"
        raise RecursionRouterError(f"{name} must be one of {suffix}")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise RecursionRouterError(
            f"{name} must be exact concrete lowercase 64-hex SHA-256 text"
        )
    return value


def _canonical_refs(
    name: str,
    values: Iterable[str],
    *,
    require_nonempty: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise RecursionRouterError(f"{name} must be an iterable of reference strings")
    try:
        cleaned = tuple(values)
    except TypeError as exc:
        raise RecursionRouterError(f"{name} must be an iterable of reference strings") from exc
    if len(cleaned) > _MAX_REF_COUNT:
        raise RecursionRouterError(f"{name} exceeds {_MAX_REF_COUNT} references")
    for value in cleaned:
        _identifier(f"{name} item", value)
    if len(set(cleaned)) != len(cleaned):
        raise RecursionRouterError(f"{name} must not contain duplicates")
    if cleaned != tuple(sorted(cleaned)):
        raise RecursionRouterError(f"{name} must be in canonical lexical order")
    if require_nonempty and not cleaned:
        raise RecursionRouterError(f"{name} must contain at least one explicit reference")
    return cleaned


def _canonical_strategies(
    name: str,
    values: Iterable[str],
    *,
    allow_r3: bool,
    require_nonempty: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise RecursionRouterError(f"{name} must be an iterable of strategies")
    try:
        raw = tuple(values)
    except TypeError as exc:
        raise RecursionRouterError(f"{name} must be an iterable of strategies") from exc
    for value in raw:
        _strategy(f"{name} item", value, allow_r3=allow_r3)
    if len(set(raw)) != len(raw):
        raise RecursionRouterError(f"{name} must not contain duplicate strategies")
    order = _STRATEGY_ORDER if allow_r3 else _LOWER_STRATEGY_ORDER
    canonical = tuple(strategy for strategy in order if strategy in set(raw))
    if raw != canonical:
        suffix = "R0,R1,R2,R3" if allow_r3 else "R0,R1,R2"
        raise RecursionRouterError(f"{name} must use canonical {suffix} order")
    if require_nonempty and not canonical:
        raise RecursionRouterError(f"{name} must contain at least one strategy")
    return canonical


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _rebuild_route_candidate(value: Any) -> RouteCandidate:
    if not isinstance(value, Mapping):
        raise RecursionRouterError("route_candidate must be a mapping")
    expected = {
        "schema",
        "candidate_id",
        "task_id",
        "task_generation",
        "task_sha256",
        "request_sha256",
        "cycle_contract_id",
        "cycle_generation",
        "cycle_contract_sha256",
        "policy_id",
        "policy_generation",
        "policy_sha256",
        "selected_route",
        "reason_codes",
        "classification",
    }
    if set(value.keys()) != expected:
        raise RecursionRouterError("route_candidate fields are not exact")
    reason_codes = value["reason_codes"]
    if type(reason_codes) is list:
        reason_codes = tuple(reason_codes)
    if type(reason_codes) is not tuple:
        raise RecursionRouterError("route_candidate.reason_codes must be a canonical sequence")
    if reason_codes != tuple(sorted(set(reason_codes))):
        raise RecursionRouterError("route_candidate.reason_codes are not canonical")
    try:
        return RouteCandidate(**{**dict(value), "reason_codes": reason_codes})
    except (TypeError, ValueError) as exc:
        raise RecursionRouterError(f"invalid route_candidate: {exc}") from exc


def _verify_route_candidate(route_candidate: RouteCandidate) -> str:
    if type(route_candidate) is not RouteCandidate:
        raise RecursionRouterError("route_candidate must be exact concrete RouteCandidate")
    rebuilt = _rebuild_route_candidate(route_candidate.as_dict())
    if rebuilt != route_candidate:
        raise RecursionRouterError("route_candidate canonical reconstruction mismatch")
    try:
        return route_candidate.sha256()
    except (TypeError, ValueError) as exc:
        raise RecursionRouterError(
            "route_candidate cannot cross its canonical hash boundary"
        ) from exc


def _verify_child_request(child_request: NativeChildRequest) -> str:
    if type(child_request) is not NativeChildRequest:
        raise RecursionRouterError("child_request must be exact concrete NativeChildRequest")
    try:
        request_sha = child_request.sha256()
        verify_native_child_request(
            child_request,
            expected_request_id=child_request.request_id,
            expected_request_generation=child_request.request_generation,
            expected_binding_id=child_request.binding_id,
            expected_binding_sha256=child_request.binding_sha256,
            expected_request_sha256=request_sha,
        )
    except (TypeError, ValueError) as exc:
        raise RecursionRouterError(f"invalid child_request: {exc}") from exc
    return request_sha


def _verify_route_child_relation(
    route_candidate: RouteCandidate,
    child_request: NativeChildRequest,
) -> None:
    if route_candidate.selected_route != DELEGATE_BUILD:
        raise RecursionRouterError("Native Child harness requires DELEGATE_BUILD upstream route")
    if route_candidate.task_id != child_request.binding.parent.task_id:
        raise RecursionRouterError("routed task_id does not match child binding parent task_id")
    if route_candidate.task_sha256 != child_request.payload_sha256:
        raise RecursionRouterError("routed task digest does not match child payload digest")


def _policy_identity_payload(
    *,
    policy_id: str,
    generation: int,
    admitted_strategies: tuple[str, ...],
    max_nested_child_edges: int,
    provenance_refs: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "policy_id": policy_id,
        "generation": generation,
        "admitted_strategies": list(admitted_strategies),
        "max_nested_child_edges": max_nested_child_edges,
        "provenance_refs": list(provenance_refs),
    }


def _need_identity_payload(
    *,
    generation: int,
    route_candidate_id: str,
    route_candidate_sha256: str,
    requested_strategy: str,
    r3_available_strategies: tuple[str, ...],
    r3_selected_strategy: str | None,
    r3_decision_id: str | None,
    r3_decision_sha256: str | None,
    r3_decision_provenance_refs: tuple[str, ...],
    remaining_nested_child_edges: int,
    child_request_id: str | None,
    child_request_generation: int | None,
    child_request_sha256: str | None,
    parent_candidate_id: str | None,
    parent_candidate_sha256: str | None,
    parent_child_remaining_nested_edges: int | None,
    provenance_refs: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "generation": generation,
        "route_candidate_id": route_candidate_id,
        "route_candidate_sha256": route_candidate_sha256,
        "requested_strategy": requested_strategy,
        "r3_available_strategies": list(r3_available_strategies),
        "r3_selected_strategy": r3_selected_strategy,
        "r3_decision_id": r3_decision_id,
        "r3_decision_sha256": r3_decision_sha256,
        "r3_decision_provenance_refs": list(r3_decision_provenance_refs),
        "remaining_nested_child_edges": remaining_nested_child_edges,
        "child_request_id": child_request_id,
        "child_request_generation": child_request_generation,
        "child_request_sha256": child_request_sha256,
        "parent_candidate_id": parent_candidate_id,
        "parent_candidate_sha256": parent_candidate_sha256,
        "parent_child_remaining_nested_edges": parent_child_remaining_nested_edges,
        "provenance_refs": list(provenance_refs),
    }


def _need_id(**identity_fields: Any) -> str:
    return "recursion-need:" + _digest(_need_identity_payload(**identity_fields))


def _candidate_identity_payload(
    *,
    need_id: str,
    need_sha256: str,
    route_candidate_id: str,
    route_candidate_sha256: str,
    child_request_id: str | None,
    child_request_sha256: str | None,
    policy_id: str,
    policy_generation: int,
    policy_sha256: str,
    requested_strategy: str,
    selected_strategy: str,
    r3_decision_id: str | None,
    r3_decision_sha256: str | None,
    r3_decision_provenance_refs: tuple[str, ...],
    remaining_nested_child_edges: int,
    child_remaining_nested_child_edges: int | None,
    reason_codes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "need_id": need_id,
        "need_sha256": need_sha256,
        "route_candidate_id": route_candidate_id,
        "route_candidate_sha256": route_candidate_sha256,
        "child_request_id": child_request_id,
        "child_request_sha256": child_request_sha256,
        "policy_id": policy_id,
        "policy_generation": policy_generation,
        "policy_sha256": policy_sha256,
        "requested_strategy": requested_strategy,
        "selected_strategy": selected_strategy,
        "r3_decision_id": r3_decision_id,
        "r3_decision_sha256": r3_decision_sha256,
        "r3_decision_provenance_refs": list(r3_decision_provenance_refs),
        "remaining_nested_child_edges": remaining_nested_child_edges,
        "child_remaining_nested_child_edges": child_remaining_nested_child_edges,
        "reason_codes": list(reason_codes),
    }


def _candidate_id(**identity_fields: Any) -> str:
    return "recursion-route:" + _digest(_candidate_identity_payload(**identity_fields))


@dataclass(frozen=True, slots=True)
class RecursionPolicy:
    """Explicit strategy/depth policy; never model/child/effect authority."""

    schema: str
    policy_id: str
    generation: int
    admitted_strategies: tuple[str, ...]
    max_nested_child_edges: int
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.schema) is not str or self.schema != RECURSION_POLICY_SCHEMA:
            raise RecursionRouterError("recursion policy schema mismatch")
        _identifier("policy_id", self.policy_id)
        _generation("policy generation", self.generation)
        strategies = _canonical_strategies(
            "admitted_strategies",
            self.admitted_strategies,
            allow_r3=True,
            require_nonempty=True,
        )
        object.__setattr__(self, "admitted_strategies", strategies)
        _remaining_edges("max_nested_child_edges", self.max_nested_child_edges)
        refs = _canonical_refs("provenance_refs", self.provenance_refs, require_nonempty=True)
        object.__setattr__(self, "provenance_refs", refs)

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        generation: int,
        admitted_strategies: Iterable[str] = _STRATEGY_ORDER,
        max_nested_child_edges: int = _MAX_NESTED_CHILD_EDGES,
        provenance_refs: Iterable[str],
    ) -> "RecursionPolicy":
        return cls(
            schema=RECURSION_POLICY_SCHEMA,
            policy_id=policy_id,
            generation=generation,
            admitted_strategies=tuple(admitted_strategies),
            max_nested_child_edges=max_nested_child_edges,
            provenance_refs=tuple(provenance_refs),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RecursionPolicy":
        if not isinstance(value, Mapping):
            raise RecursionRouterError("recursion policy input must be a mapping")
        expected = set(cls.__dataclass_fields__)
        if set(value.keys()) != expected:
            raise RecursionRouterError("recursion policy fields are not exact")
        admitted = value["admitted_strategies"]
        refs = value["provenance_refs"]
        if type(admitted) is list:
            admitted = tuple(admitted)
        if type(refs) is list:
            refs = tuple(refs)
        try:
            return cls(**{**dict(value), "admitted_strategies": admitted, "provenance_refs": refs})
        except (TypeError, ValueError) as exc:
            raise RecursionRouterError(f"invalid recursion policy: {exc}") from exc

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            **_policy_identity_payload(
                policy_id=self.policy_id,
                generation=self.generation,
                admitted_strategies=self.admitted_strategies,
                max_nested_child_edges=self.max_nested_child_edges,
                provenance_refs=self.provenance_refs,
            ),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RecursionRouteCandidate:
    """Evidence-only selected strategy bound to exact upstream identities."""

    schema: str
    candidate_id: str
    need_id: str
    need_sha256: str
    route_candidate_id: str
    route_candidate_sha256: str
    child_request_id: str | None
    child_request_sha256: str | None
    policy_id: str
    policy_generation: int
    policy_sha256: str
    requested_strategy: str
    selected_strategy: str
    r3_decision_id: str | None
    r3_decision_sha256: str | None
    r3_decision_provenance_refs: tuple[str, ...]
    remaining_nested_child_edges: int
    child_remaining_nested_child_edges: int | None
    reason_codes: tuple[str, ...]
    classification: str = RECURSION_ROUTE_CLASSIFICATION

    def __post_init__(self) -> None:
        if type(self.schema) is not str or self.schema != RECURSION_ROUTE_CANDIDATE_SCHEMA:
            raise RecursionRouterError("recursion route candidate schema mismatch")
        if type(self.classification) is not str or self.classification != RECURSION_ROUTE_CLASSIFICATION:
            raise RecursionRouterError("recursion route candidate classification mismatch")
        _identifier("candidate_id", self.candidate_id)
        _identifier("need_id", self.need_id)
        _sha256("need_sha256", self.need_sha256)
        _identifier("route_candidate_id", self.route_candidate_id)
        _sha256("route_candidate_sha256", self.route_candidate_sha256)
        if (self.child_request_id is None) != (self.child_request_sha256 is None):
            raise RecursionRouterError(
                "candidate child request identity/digest must be both present or both absent"
            )
        if self.child_request_id is not None:
            _identifier("child_request_id", self.child_request_id)
            _sha256("child_request_sha256", self.child_request_sha256)
        _identifier("policy_id", self.policy_id)
        _generation("policy_generation", self.policy_generation)
        _sha256("policy_sha256", self.policy_sha256)
        _strategy("requested_strategy", self.requested_strategy)
        _strategy("selected_strategy", self.selected_strategy, allow_r3=False)
        _remaining_edges("remaining_nested_child_edges", self.remaining_nested_child_edges)

        if self.requested_strategy == R3:
            _identifier("r3_decision_id", self.r3_decision_id)
            _sha256("r3_decision_sha256", self.r3_decision_sha256)
            decision_refs = _canonical_refs(
                "r3_decision_provenance_refs",
                self.r3_decision_provenance_refs,
                require_nonempty=True,
            )
            object.__setattr__(self, "r3_decision_provenance_refs", decision_refs)
        else:
            if self.selected_strategy != self.requested_strategy:
                raise RecursionRouterError(
                    "non-adaptive requested strategy must equal selected strategy"
                )
            if (
                self.r3_decision_id is not None
                or self.r3_decision_sha256 is not None
                or self.r3_decision_provenance_refs
            ):
                raise RecursionRouterError(
                    "non-R3 candidate cannot expose R3 decision evidence"
                )

        if self.selected_strategy == R2:
            if self.child_request_id is None:
                raise RecursionRouterError("R2 selected strategy requires child request evidence")
            if self.child_remaining_nested_child_edges is None:
                raise RecursionRouterError(
                    "R2 selected strategy requires child remaining-depth evidence"
                )
            _remaining_edges(
                "child_remaining_nested_child_edges",
                self.child_remaining_nested_child_edges,
            )
            if self.child_remaining_nested_child_edges != self.remaining_nested_child_edges:
                raise RecursionRouterError("selected child remaining-depth evidence mismatch")
        else:
            if self.child_request_id is not None:
                raise RecursionRouterError(
                    "non-R2 selected strategy cannot expose child request evidence"
                )
            if self.child_remaining_nested_child_edges is not None:
                raise RecursionRouterError(
                    "non-R2 selected strategy cannot expose child remaining-depth evidence"
                )
            if self.remaining_nested_child_edges != 0:
                raise RecursionRouterError(
                    "non-R2 selected strategy must expose zero nested-child edges"
                )

        reasons = _canonical_refs("reason_codes", self.reason_codes, require_nonempty=True)
        object.__setattr__(self, "reason_codes", reasons)
        identity = {
            "need_id": self.need_id,
            "need_sha256": self.need_sha256,
            "route_candidate_id": self.route_candidate_id,
            "route_candidate_sha256": self.route_candidate_sha256,
            "child_request_id": self.child_request_id,
            "child_request_sha256": self.child_request_sha256,
            "policy_id": self.policy_id,
            "policy_generation": self.policy_generation,
            "policy_sha256": self.policy_sha256,
            "requested_strategy": self.requested_strategy,
            "selected_strategy": self.selected_strategy,
            "r3_decision_id": self.r3_decision_id,
            "r3_decision_sha256": self.r3_decision_sha256,
            "r3_decision_provenance_refs": self.r3_decision_provenance_refs,
            "remaining_nested_child_edges": self.remaining_nested_child_edges,
            "child_remaining_nested_child_edges": self.child_remaining_nested_child_edges,
            "reason_codes": self.reason_codes,
        }
        if self.candidate_id != _candidate_id(**identity):
            raise RecursionRouterError(
                "candidate_id does not bind exact recursion route content"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RecursionRouteCandidate":
        if not isinstance(value, Mapping):
            raise RecursionRouterError("recursion route candidate input must be a mapping")
        expected = set(cls.__dataclass_fields__)
        if set(value.keys()) != expected:
            raise RecursionRouterError("recursion route candidate fields are not exact")
        reasons = value["reason_codes"]
        decision_refs = value["r3_decision_provenance_refs"]
        if type(reasons) is list:
            reasons = tuple(reasons)
        if type(decision_refs) is list:
            decision_refs = tuple(decision_refs)
        try:
            return cls(
                **{
                    **dict(value),
                    "reason_codes": reasons,
                    "r3_decision_provenance_refs": decision_refs,
                }
            )
        except (TypeError, ValueError) as exc:
            raise RecursionRouterError(
                f"invalid recursion route candidate: {exc}"
            ) from exc

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["r3_decision_provenance_refs"] = list(self.r3_decision_provenance_refs)
        value["reason_codes"] = list(self.reason_codes)
        return value

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _verify_recursion_candidate(candidate: RecursionRouteCandidate) -> str:
    if type(candidate) is not RecursionRouteCandidate:
        raise RecursionRouterError(
            "recursion candidate must be exact concrete RecursionRouteCandidate"
        )
    rebuilt = RecursionRouteCandidate.from_mapping(candidate.as_dict())
    if rebuilt != candidate:
        raise RecursionRouterError("recursion candidate canonical reconstruction mismatch")
    return candidate.sha256()


@dataclass(frozen=True, slots=True)
class RecursionNeed:
    """Caller-supplied strategy need plus orthogonal nested-child budget evidence."""

    schema: str
    need_id: str
    generation: int
    route_candidate_id: str
    route_candidate_sha256: str
    requested_strategy: str
    r3_available_strategies: tuple[str, ...]
    r3_selected_strategy: str | None
    r3_decision_id: str | None
    r3_decision_sha256: str | None
    r3_decision_provenance_refs: tuple[str, ...]
    remaining_nested_child_edges: int
    child_request_id: str | None
    child_request_generation: int | None
    child_request_sha256: str | None
    parent_candidate_id: str | None
    parent_candidate_sha256: str | None
    parent_child_remaining_nested_edges: int | None
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.schema) is not str or self.schema != RECURSION_NEED_SCHEMA:
            raise RecursionRouterError("recursion need schema mismatch")
        _identifier("need_id", self.need_id)
        _generation("need generation", self.generation)
        _identifier("route_candidate_id", self.route_candidate_id)
        _sha256("route_candidate_sha256", self.route_candidate_sha256)
        _strategy("requested_strategy", self.requested_strategy)
        _remaining_edges("remaining_nested_child_edges", self.remaining_nested_child_edges)
        refs = _canonical_refs("provenance_refs", self.provenance_refs, require_nonempty=True)
        object.__setattr__(self, "provenance_refs", refs)

        if self.requested_strategy == R3:
            available = _canonical_strategies(
                "r3_available_strategies",
                self.r3_available_strategies,
                allow_r3=False,
                require_nonempty=True,
            )
            object.__setattr__(self, "r3_available_strategies", available)
            selected = _strategy(
                "r3_selected_strategy",
                self.r3_selected_strategy,
                allow_r3=False,
            )
            if selected not in available:
                raise RecursionRouterError(
                    "r3_selected_strategy must be explicitly present in r3_available_strategies"
                )
            _identifier("r3_decision_id", self.r3_decision_id)
            _sha256("r3_decision_sha256", self.r3_decision_sha256)
            decision_refs = _canonical_refs(
                "r3_decision_provenance_refs",
                self.r3_decision_provenance_refs,
                require_nonempty=True,
            )
            object.__setattr__(self, "r3_decision_provenance_refs", decision_refs)
        else:
            if self.r3_available_strategies:
                raise RecursionRouterError(
                    "r3_available_strategies is only valid for R3 adaptive selection"
                )
            if self.r3_selected_strategy is not None:
                raise RecursionRouterError(
                    "r3_selected_strategy is only valid for R3 adaptive selection"
                )
            if self.r3_decision_id is not None or self.r3_decision_sha256 is not None:
                raise RecursionRouterError(
                    "R3 decision identity is only valid for R3 adaptive selection"
                )
            if self.r3_decision_provenance_refs:
                raise RecursionRouterError(
                    "R3 decision provenance is only valid for R3 adaptive selection"
                )

        child_fields = (
            self.child_request_id,
            self.child_request_generation,
            self.child_request_sha256,
        )
        if all(value is None for value in child_fields):
            pass
        elif any(value is None for value in child_fields):
            raise RecursionRouterError(
                "child request identity fields must be all present or all absent"
            )
        else:
            _identifier("child_request_id", self.child_request_id)
            _generation("child_request_generation", self.child_request_generation)
            _sha256("child_request_sha256", self.child_request_sha256)

        parent_fields = (
            self.parent_candidate_id,
            self.parent_candidate_sha256,
            self.parent_child_remaining_nested_edges,
        )
        if all(value is None for value in parent_fields):
            pass
        elif any(value is None for value in parent_fields):
            raise RecursionRouterError(
                "parent recursion candidate fields must be all present or all absent"
            )
        else:
            _identifier("parent_candidate_id", self.parent_candidate_id)
            _sha256("parent_candidate_sha256", self.parent_candidate_sha256)
            _remaining_edges(
                "parent_child_remaining_nested_edges",
                self.parent_child_remaining_nested_edges,
            )

        selected = (
            self.r3_selected_strategy if self.requested_strategy == R3 else self.requested_strategy
        )
        if selected == R2:
            if self.child_request_id is None:
                raise RecursionRouterError(
                    "R2 selected strategy requires exact child request identity"
                )
        else:
            if self.child_request_id is not None:
                raise RecursionRouterError(
                    "non-R2 selected strategy must not carry child request identity"
                )
            if self.remaining_nested_child_edges != 0:
                raise RecursionRouterError(
                    "non-R2 selected strategy must use zero nested-child edges"
                )

        if self.parent_candidate_id is not None and selected == R2:
            if self.parent_child_remaining_nested_edges == 0:
                raise RecursionRouterError(
                    "parent recursion candidate has no remaining nested-child edge"
                )
            if (
                self.remaining_nested_child_edges
                != self.parent_child_remaining_nested_edges - 1
            ):
                raise RecursionRouterError(
                    "nested R2 reroute must consume exactly one remaining child edge"
                )

        identity = {
            "generation": self.generation,
            "route_candidate_id": self.route_candidate_id,
            "route_candidate_sha256": self.route_candidate_sha256,
            "requested_strategy": self.requested_strategy,
            "r3_available_strategies": self.r3_available_strategies,
            "r3_selected_strategy": self.r3_selected_strategy,
            "r3_decision_id": self.r3_decision_id,
            "r3_decision_sha256": self.r3_decision_sha256,
            "r3_decision_provenance_refs": self.r3_decision_provenance_refs,
            "remaining_nested_child_edges": self.remaining_nested_child_edges,
            "child_request_id": self.child_request_id,
            "child_request_generation": self.child_request_generation,
            "child_request_sha256": self.child_request_sha256,
            "parent_candidate_id": self.parent_candidate_id,
            "parent_candidate_sha256": self.parent_candidate_sha256,
            "parent_child_remaining_nested_edges": self.parent_child_remaining_nested_edges,
            "provenance_refs": self.provenance_refs,
        }
        if self.need_id != _need_id(**identity):
            raise RecursionRouterError(
                "need_id does not bind exact recursion need content"
            )

    @classmethod
    def create(
        cls,
        *,
        route_candidate: RouteCandidate,
        requested_strategy: str,
        generation: int,
        provenance_refs: Iterable[str],
        r3_available_strategies: Iterable[str] = (),
        r3_selected_strategy: str | None = None,
        r3_decision_id: str | None = None,
        r3_decision_sha256: str | None = None,
        r3_decision_provenance_refs: Iterable[str] = (),
        remaining_nested_child_edges: int = 0,
        child_request: NativeChildRequest | None = None,
        parent_candidate: RecursionRouteCandidate | None = None,
    ) -> "RecursionNeed":
        route_sha = _verify_route_candidate(route_candidate)
        _strategy("requested_strategy", requested_strategy)
        _generation("need generation", generation)
        remaining_nested_child_edges = _remaining_edges(
            "remaining_nested_child_edges",
            remaining_nested_child_edges,
        )
        refs = _canonical_refs(
            "provenance_refs",
            tuple(provenance_refs),
            require_nonempty=True,
        )
        r3_available = tuple(r3_available_strategies)
        r3_decision_refs = tuple(r3_decision_provenance_refs)

        if child_request is None:
            child_request_id = None
            child_request_generation = None
            child_request_sha256 = None
        else:
            child_request_sha256 = _verify_child_request(child_request)
            child_request_id = child_request.request_id
            child_request_generation = child_request.request_generation

        if parent_candidate is None:
            parent_candidate_id = None
            parent_candidate_sha256 = None
            parent_child_remaining_nested_edges = None
        else:
            parent_candidate_sha256 = _verify_recursion_candidate(parent_candidate)
            if parent_candidate.selected_strategy != R2:
                raise RecursionRouterError(
                    "parent_candidate must have selected R2 child harness"
                )
            if parent_candidate.child_remaining_nested_child_edges is None:
                raise RecursionRouterError(
                    "parent_candidate lacks child remaining-depth evidence"
                )
            parent_candidate_id = parent_candidate.candidate_id
            parent_child_remaining_nested_edges = (
                parent_candidate.child_remaining_nested_child_edges
            )

        identity = {
            "generation": generation,
            "route_candidate_id": route_candidate.candidate_id,
            "route_candidate_sha256": route_sha,
            "requested_strategy": requested_strategy,
            "r3_available_strategies": r3_available,
            "r3_selected_strategy": r3_selected_strategy,
            "r3_decision_id": r3_decision_id,
            "r3_decision_sha256": r3_decision_sha256,
            "r3_decision_provenance_refs": r3_decision_refs,
            "remaining_nested_child_edges": remaining_nested_child_edges,
            "child_request_id": child_request_id,
            "child_request_generation": child_request_generation,
            "child_request_sha256": child_request_sha256,
            "parent_candidate_id": parent_candidate_id,
            "parent_candidate_sha256": parent_candidate_sha256,
            "parent_child_remaining_nested_edges": parent_child_remaining_nested_edges,
            "provenance_refs": refs,
        }
        return cls(
            schema=RECURSION_NEED_SCHEMA,
            need_id=_need_id(**identity),
            **identity,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RecursionNeed":
        if not isinstance(value, Mapping):
            raise RecursionRouterError("recursion need input must be a mapping")
        expected = set(cls.__dataclass_fields__)
        if set(value.keys()) != expected:
            raise RecursionRouterError("recursion need fields are not exact")
        converted = dict(value)
        for key in (
            "r3_available_strategies",
            "r3_decision_provenance_refs",
            "provenance_refs",
        ):
            if type(converted[key]) is list:
                converted[key] = tuple(converted[key])
        try:
            return cls(**converted)
        except (TypeError, ValueError) as exc:
            raise RecursionRouterError(f"invalid recursion need: {exc}") from exc

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["r3_available_strategies"] = list(self.r3_available_strategies)
        value["r3_decision_provenance_refs"] = list(
            self.r3_decision_provenance_refs
        )
        value["provenance_refs"] = list(self.provenance_refs)
        return value

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _verify_need(need: RecursionNeed) -> str:
    if type(need) is not RecursionNeed:
        raise RecursionRouterError("need must be exact concrete RecursionNeed")
    rebuilt = RecursionNeed.from_mapping(need.as_dict())
    if rebuilt != need:
        raise RecursionRouterError("recursion need canonical reconstruction mismatch")
    return need.sha256()


def _verify_policy(policy: RecursionPolicy) -> str:
    if type(policy) is not RecursionPolicy:
        raise RecursionRouterError("policy must be exact concrete RecursionPolicy")
    rebuilt = RecursionPolicy.from_mapping(policy.as_dict())
    if rebuilt != policy:
        raise RecursionRouterError("recursion policy canonical reconstruction mismatch")
    return policy.sha256()


def _verify_parent_binding(
    need: RecursionNeed,
    parent_candidate: RecursionRouteCandidate | None,
) -> None:
    if need.parent_candidate_id is None:
        if parent_candidate is not None:
            raise RecursionRouterError("unexpected parent recursion candidate")
        return
    if parent_candidate is None:
        raise RecursionRouterError("exact parent recursion candidate is required")
    parent_sha = _verify_recursion_candidate(parent_candidate)
    if parent_candidate.candidate_id != need.parent_candidate_id:
        raise RecursionRouterError("parent recursion candidate id mismatch")
    if parent_sha != need.parent_candidate_sha256:
        raise RecursionRouterError("parent recursion candidate digest mismatch")
    if parent_candidate.selected_strategy != R2:
        raise RecursionRouterError("parent recursion candidate must have selected R2")
    if (
        parent_candidate.child_remaining_nested_child_edges
        != need.parent_child_remaining_nested_edges
    ):
        raise RecursionRouterError(
            "parent remaining nested-child evidence mismatch"
        )


def _verify_child_binding(
    *,
    route_candidate: RouteCandidate,
    need: RecursionNeed,
    child_request: NativeChildRequest | None,
) -> tuple[str | None, str | None]:
    if need.child_request_id is None:
        if child_request is not None:
            raise RecursionRouterError("unexpected child request for non-R2 strategy")
        return None, None
    if child_request is None:
        raise RecursionRouterError("exact NativeChildRequest is required for R2 strategy")
    child_sha = _verify_child_request(child_request)
    if child_request.request_id != need.child_request_id:
        raise RecursionRouterError("recursion need child request id mismatch")
    if child_request.request_generation != need.child_request_generation:
        raise RecursionRouterError("recursion need child request generation mismatch")
    if child_sha != need.child_request_sha256:
        raise RecursionRouterError("recursion need child request digest mismatch")
    _verify_route_child_relation(route_candidate, child_request)
    if (
        need.remaining_nested_child_edges
        > child_request.resource_budget.max_nested_depth
    ):
        raise RecursionRouterError(
            "remaining nested-child edges exceed NativeChildRequest max_nested_depth"
        )
    return child_request.request_id, child_sha


def _route_compatible_strategies(route_candidate: RouteCandidate) -> frozenset[str]:
    if route_candidate.selected_route == DIRECT_SMALL:
        return frozenset((R0,))
    if route_candidate.selected_route == DELEGATE_BUILD:
        return frozenset((R1, R2))
    raise RecursionRouterError("unsupported upstream route candidate")


def route_recursion(
    *,
    route_candidate: RouteCandidate,
    need: RecursionNeed,
    policy: RecursionPolicy,
    child_request: NativeChildRequest | None = None,
    parent_candidate: RecursionRouteCandidate | None = None,
) -> RecursionRouteCandidate:
    """Emit one deterministic evidence-only recursion-strategy candidate."""

    route_sha = _verify_route_candidate(route_candidate)
    need_sha = _verify_need(need)
    policy_sha = _verify_policy(policy)

    if need.route_candidate_id != route_candidate.candidate_id:
        raise RecursionRouterError("recursion need route candidate id mismatch")
    if need.route_candidate_sha256 != route_sha:
        raise RecursionRouterError("recursion need route candidate digest mismatch")
    _verify_parent_binding(need, parent_candidate)

    if need.remaining_nested_child_edges > policy.max_nested_child_edges:
        raise RecursionRouterError(
            "remaining nested-child edges exceed policy ceiling"
        )

    compatible = _route_compatible_strategies(route_candidate)
    requested = need.requested_strategy
    if requested == R3:
        if R3 not in policy.admitted_strategies:
            raise RecursionRouterError("R3 adaptive selection is not policy-admitted")
        declared = set(need.r3_available_strategies)
        incompatible = declared - compatible
        if incompatible:
            raise RecursionRouterError(
                "R3 availability contains strategy incompatible with upstream route"
            )
        selected = need.r3_selected_strategy
        if selected not in declared:
            raise RecursionRouterError(
                "R3 selected strategy is not explicitly available"
            )
        if selected not in policy.admitted_strategies:
            raise RecursionRouterError(
                "R3 selected lower strategy is not policy-admitted"
            )
    else:
        selected = requested
        if requested not in policy.admitted_strategies:
            raise RecursionRouterError("requested strategy is not policy-admitted")

    if selected not in compatible:
        raise RecursionRouterError("selected strategy contradicts upstream route")

    child_request_id, child_request_sha = _verify_child_binding(
        route_candidate=route_candidate,
        need=need,
        child_request=child_request,
    )

    if selected == R0:
        reason_codes = (
            "R3_ADAPTIVE_SELECTED_R0" if requested == R3 else "R0_DETERMINISTIC_ADMITTED",
        )
        child_remaining = None
    elif selected == R1:
        reason_codes = (
            "R3_ADAPTIVE_SELECTED_R1"
            if requested == R3
            else "R1_MODEL_RECURSION_CANDIDATE_ADMITTED",
        )
        child_remaining = None
    elif selected == R2:
        if child_request_id is None:
            raise RecursionRouterError(
                "R2 child harness requires exact child request evidence"
            )
        reason_codes = (
            "R3_ADAPTIVE_SELECTED_R2"
            if requested == R3
            else "R2_NATIVE_CHILD_HARNESS_ADMITTED",
        )
        child_remaining = need.remaining_nested_child_edges
    else:
        raise RecursionRouterError("unsupported selected lower strategy")

    r3_decision_refs = (
        need.r3_decision_provenance_refs if requested == R3 else ()
    )
    identity = {
        "need_id": need.need_id,
        "need_sha256": need_sha,
        "route_candidate_id": route_candidate.candidate_id,
        "route_candidate_sha256": route_sha,
        "child_request_id": child_request_id,
        "child_request_sha256": child_request_sha,
        "policy_id": policy.policy_id,
        "policy_generation": policy.generation,
        "policy_sha256": policy_sha,
        "requested_strategy": requested,
        "selected_strategy": selected,
        "r3_decision_id": need.r3_decision_id if requested == R3 else None,
        "r3_decision_sha256": need.r3_decision_sha256 if requested == R3 else None,
        "r3_decision_provenance_refs": r3_decision_refs,
        "remaining_nested_child_edges": need.remaining_nested_child_edges,
        "child_remaining_nested_child_edges": child_remaining,
        "reason_codes": reason_codes,
    }
    return RecursionRouteCandidate(
        schema=RECURSION_ROUTE_CANDIDATE_SCHEMA,
        candidate_id=_candidate_id(**identity),
        **identity,
    )
