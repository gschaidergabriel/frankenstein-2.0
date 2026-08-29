"""F2-WP-603 deterministic R0/R1/R2/R3 recursion-mechanism router.

Canonical Stage-6 semantics are mechanism classes, not recursion depths:

    R0 = deterministic local path
    R1 = model-recursion candidate
    R2 = Native Child harness candidate
    R3 = adaptive selection among explicitly admitted R0/R1/R2 mechanisms

Nested-child depth is an orthogonal resource dimension.  In this WP603 contract,
``remaining_nested_child_edges`` means the number of *additional* Native Child edges
allowed below the immediate R2 child.  Therefore an immediate R2 child is valid with
``remaining_nested_child_edges == 0`` and ``NativeChildRequest.resource_budget.
max_nested_depth == 0``.  A nested child may expose another R2 path only with a
strictly smaller remaining-edge value bound to its exact parent recursion candidate.

This module never inspects task payload text or infers task semantics/complexity.
All mechanism availability, requested mode, policy admission and R3 preference are
explicit inputs.  Outputs are immutable evidence/provenance candidates only.  Nothing
here spawns a child, invokes a model/provider, transports payloads, grants capabilities,
reads/writes UnifiedDB, authorizes effects/completion, or mints runtime/GRID/GWT/
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

RECURSION_NEED_SCHEMA = "FRANKENSTEIN2_RECURSION_NEED/v2"
RECURSION_POLICY_SCHEMA = "FRANKENSTEIN2_RECURSION_POLICY/v2"
RECURSION_ROUTE_CANDIDATE_SCHEMA = "FRANKENSTEIN2_RECURSION_ROUTE_CANDIDATE/v2"
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
_MODE_ORDER = (R0, R1, R2, R3)
_LOWER_MODE_ORDER = (R0, R1, R2)
_ALLOWED_MODES = frozenset(_MODE_ORDER)
_ALLOWED_LOWER_MODES = frozenset(_LOWER_MODE_ORDER)
_MAX_NESTED_CHILD_EDGES = 3
_MAX_IDENTIFIER_LENGTH = 512
_MAX_REF_COUNT = 4096
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RecursionRouterError(ValueError):
    """Fail-closed WP603 mechanism/depth admission error."""


def _identifier(name: str, value: Any) -> str:
    if type(value) is not str:
        raise RecursionRouterError(f"{name} must be a string")
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
    return value


def _remaining_edges(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_NESTED_CHILD_EDGES:
        raise RecursionRouterError(
            f"{name} must be an exact integer in [0, {_MAX_NESTED_CHILD_EDGES}]"
        )
    return value


def _mode(name: str, value: Any, *, allow_r3: bool = True) -> str:
    allowed = _ALLOWED_MODES if allow_r3 else _ALLOWED_LOWER_MODES
    if type(value) is not str or value not in allowed:
        suffix = "R0/R1/R2/R3" if allow_r3 else "R0/R1/R2"
        raise RecursionRouterError(f"{name} must be one of {suffix}")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise RecursionRouterError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _canonical_refs(name: str, values: Iterable[str], *, require_nonempty: bool = False) -> tuple[str, ...]:
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


def _canonical_modes(name: str, values: Iterable[str], *, require_nonempty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise RecursionRouterError(f"{name} must be an iterable of modes")
    try:
        raw = tuple(values)
    except TypeError as exc:
        raise RecursionRouterError(f"{name} must be an iterable of modes") from exc
    for value in raw:
        _mode(f"{name} item", value, allow_r3=False)
    if len(set(raw)) != len(raw):
        raise RecursionRouterError(f"{name} must not contain duplicate modes")
    canonical = tuple(mode for mode in _LOWER_MODE_ORDER if mode in set(raw))
    if raw != canonical:
        raise RecursionRouterError(f"{name} must use canonical R0,R1,R2 order")
    if require_nonempty and not canonical:
        raise RecursionRouterError(f"{name} must contain at least one lower mechanism")
    return canonical


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


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
    return route_candidate.sha256()


def _verify_child_request(child_request: NativeChildRequest) -> str:
    if type(child_request) is not NativeChildRequest:
        raise RecursionRouterError("child_request must be exact concrete NativeChildRequest")
    request_sha = child_request.sha256()
    try:
        verify_native_child_request(
            child_request,
            expected_request_id=child_request.request_id,
            expected_request_generation=child_request.request_generation,
            expected_binding_id=child_request.binding_id,
            expected_binding_sha256=child_request.binding_sha256,
            expected_request_sha256=request_sha,
        )
    except ValueError as exc:
        raise RecursionRouterError(f"invalid child_request: {exc}") from exc
    return request_sha


def _verify_route_child_relation(route_candidate: RouteCandidate, child_request: NativeChildRequest) -> None:
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
    admitted_modes: tuple[str, ...],
    r3_preference_order: tuple[str, ...],
    max_nested_child_edges: int,
    provenance_refs: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "policy_id": policy_id,
        "generation": generation,
        "admitted_modes": list(admitted_modes),
        "r3_preference_order": list(r3_preference_order),
        "max_nested_child_edges": max_nested_child_edges,
        "provenance_refs": list(provenance_refs),
    }


def _need_identity_payload(
    *,
    generation: int,
    route_candidate_id: str,
    route_candidate_sha256: str,
    requested_mode: str,
    r3_available_modes: tuple[str, ...],
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
        "requested_mode": requested_mode,
        "r3_available_modes": list(r3_available_modes),
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
    requested_mode: str,
    selected_mechanism: str,
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
        "requested_mode": requested_mode,
        "selected_mechanism": selected_mechanism,
        "remaining_nested_child_edges": remaining_nested_child_edges,
        "child_remaining_nested_child_edges": child_remaining_nested_child_edges,
        "reason_codes": list(reason_codes),
    }


def _candidate_id(**identity_fields: Any) -> str:
    return "recursion-route:" + _digest(_candidate_identity_payload(**identity_fields))


@dataclass(frozen=True, slots=True)
class RecursionPolicy:
    """Explicit mechanism/depth policy; not model/child/effect authority."""

    schema: str
    policy_id: str
    generation: int
    admitted_modes: tuple[str, ...]
    r3_preference_order: tuple[str, ...]
    max_nested_child_edges: int
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != RECURSION_POLICY_SCHEMA:
            raise RecursionRouterError("recursion policy schema mismatch")
        _identifier("policy_id", self.policy_id)
        _generation("policy generation", self.generation)
        if type(self.admitted_modes) is not tuple or not self.admitted_modes:
            raise RecursionRouterError("admitted_modes must be a non-empty immutable tuple")
        for value in self.admitted_modes:
            _mode("admitted mode", value)
        canonical = tuple(mode for mode in _MODE_ORDER if mode in set(self.admitted_modes))
        if len(set(self.admitted_modes)) != len(self.admitted_modes) or self.admitted_modes != canonical:
            raise RecursionRouterError("admitted_modes must be unique canonical R0,R1,R2,R3 order")
        if type(self.r3_preference_order) is not tuple or not self.r3_preference_order:
            raise RecursionRouterError("r3_preference_order must be a non-empty immutable tuple")
        for value in self.r3_preference_order:
            _mode("r3 preference", value, allow_r3=False)
        if len(set(self.r3_preference_order)) != len(self.r3_preference_order):
            raise RecursionRouterError("r3_preference_order must not contain duplicates")
        _remaining_edges("max_nested_child_edges", self.max_nested_child_edges)
        refs = _canonical_refs("provenance_refs", self.provenance_refs, require_nonempty=True)
        object.__setattr__(self, "provenance_refs", refs)

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        generation: int,
        admitted_modes: Iterable[str] = _MODE_ORDER,
        r3_preference_order: Iterable[str] = (R2, R1, R0),
        max_nested_child_edges: int = _MAX_NESTED_CHILD_EDGES,
        provenance_refs: Iterable[str],
    ) -> "RecursionPolicy":
        return cls(
            schema=RECURSION_POLICY_SCHEMA,
            policy_id=policy_id,
            generation=generation,
            admitted_modes=tuple(admitted_modes),
            r3_preference_order=tuple(r3_preference_order),
            max_nested_child_edges=max_nested_child_edges,
            provenance_refs=tuple(provenance_refs),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RecursionPolicy":
        if not isinstance(value, Mapping):
            raise RecursionRouterError("recursion policy input must be a mapping")
        expected = {field.name for field in cls.__dataclass_fields__.values()}
        if set(value.keys()) != expected:
            raise RecursionRouterError("recursion policy fields are not exact")
        admitted_modes = value["admitted_modes"]
        r3_preference_order = value["r3_preference_order"]
        provenance_refs = value["provenance_refs"]
        if type(admitted_modes) is list:
            admitted_modes = tuple(admitted_modes)
        if type(r3_preference_order) is list:
            r3_preference_order = tuple(r3_preference_order)
        if type(provenance_refs) is list:
            provenance_refs = tuple(provenance_refs)
        try:
            return cls(
                schema=value["schema"],
                policy_id=value["policy_id"],
                generation=value["generation"],
                admitted_modes=admitted_modes,
                r3_preference_order=r3_preference_order,
                max_nested_child_edges=value["max_nested_child_edges"],
                provenance_refs=provenance_refs,
            )
        except (TypeError, ValueError) as exc:
            raise RecursionRouterError(f"invalid recursion policy: {exc}") from exc

    def as_dict(self) -> dict[str, Any]:
        return _policy_identity_payload(
            policy_id=self.policy_id,
            generation=self.generation,
            admitted_modes=self.admitted_modes,
            r3_preference_order=self.r3_preference_order,
            max_nested_child_edges=self.max_nested_child_edges,
            provenance_refs=self.provenance_refs,
        ) | {"schema": self.schema}

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RecursionRouteCandidate:
    """Evidence-only mechanism choice bound to exact need/route/policy dependencies."""

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
    requested_mode: str
    selected_mechanism: str
    remaining_nested_child_edges: int
    child_remaining_nested_child_edges: int | None
    reason_codes: tuple[str, ...]
    classification: str = RECURSION_ROUTE_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != RECURSION_ROUTE_CANDIDATE_SCHEMA:
            raise RecursionRouterError("recursion route candidate schema mismatch")
        if self.classification != RECURSION_ROUTE_CLASSIFICATION:
            raise RecursionRouterError("recursion route candidate classification mismatch")
        _identifier("candidate_id", self.candidate_id)
        _identifier("need_id", self.need_id)
        _sha256("need_sha256", self.need_sha256)
        _identifier("route_candidate_id", self.route_candidate_id)
        _sha256("route_candidate_sha256", self.route_candidate_sha256)
        if (self.child_request_id is None) != (self.child_request_sha256 is None):
            raise RecursionRouterError("candidate child request identity/digest must be both present or both absent")
        if self.child_request_id is not None:
            _identifier("child_request_id", self.child_request_id)
            _sha256("child_request_sha256", self.child_request_sha256)
        _identifier("policy_id", self.policy_id)
        _generation("policy_generation", self.policy_generation)
        _sha256("policy_sha256", self.policy_sha256)
        _mode("requested_mode", self.requested_mode)
        _mode("selected_mechanism", self.selected_mechanism, allow_r3=False)
        _remaining_edges("remaining_nested_child_edges", self.remaining_nested_child_edges)
        if self.requested_mode != R3 and self.selected_mechanism != self.requested_mode:
            raise RecursionRouterError("non-adaptive requested mode must equal selected mechanism")
        if self.selected_mechanism == R2:
            if self.child_request_id is None:
                raise RecursionRouterError("R2 selected mechanism requires child request evidence")
            if self.child_remaining_nested_child_edges is None:
                raise RecursionRouterError("R2 selected mechanism requires child remaining-depth evidence")
            _remaining_edges(
                "child_remaining_nested_child_edges",
                self.child_remaining_nested_child_edges,
            )
            if self.child_remaining_nested_child_edges != self.remaining_nested_child_edges:
                raise RecursionRouterError("selected child remaining-depth evidence mismatch")
        elif self.child_remaining_nested_child_edges is not None:
            raise RecursionRouterError("non-R2 selected mechanism cannot expose child remaining-depth evidence")
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
            "requested_mode": self.requested_mode,
            "selected_mechanism": self.selected_mechanism,
            "remaining_nested_child_edges": self.remaining_nested_child_edges,
            "child_remaining_nested_child_edges": self.child_remaining_nested_child_edges,
            "reason_codes": self.reason_codes,
        }
        if self.candidate_id != _candidate_id(**identity):
            raise RecursionRouterError("candidate_id does not bind exact recursion route content")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RecursionRouteCandidate":
        if not isinstance(value, Mapping):
            raise RecursionRouterError("recursion route candidate input must be a mapping")
        expected = {field.name for field in cls.__dataclass_fields__.values()}
        if set(value.keys()) != expected:
            raise RecursionRouterError("recursion route candidate fields are not exact")
        reason_codes = value["reason_codes"]
        if type(reason_codes) is list:
            reason_codes = tuple(reason_codes)
        return cls(**{**dict(value), "reason_codes": reason_codes})

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RecursionNeed:
    """Caller-supplied mechanism need plus orthogonal nested-child budget evidence."""

    schema: str
    need_id: str
    generation: int
    route_candidate_id: str
    route_candidate_sha256: str
    requested_mode: str
    r3_available_modes: tuple[str, ...]
    remaining_nested_child_edges: int
    child_request_id: str | None
    child_request_generation: int | None
    child_request_sha256: str | None
    parent_candidate_id: str | None
    parent_candidate_sha256: str | None
    parent_child_remaining_nested_edges: int | None
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != RECURSION_NEED_SCHEMA:
            raise RecursionRouterError("recursion need schema mismatch")
        _identifier("need_id", self.need_id)
        _generation("need generation", self.generation)
        _identifier("route_candidate_id", self.route_candidate_id)
        _sha256("route_candidate_sha256", self.route_candidate_sha256)
        _mode("requested_mode", self.requested_mode)
        _remaining_edges("remaining_nested_child_edges", self.remaining_nested_child_edges)
        refs = _canonical_refs("provenance_refs", self.provenance_refs, require_nonempty=True)
        object.__setattr__(self, "provenance_refs", refs)

        if self.requested_mode == R3:
            modes = _canonical_modes(
                "r3_available_modes",
                self.r3_available_modes,
                require_nonempty=True,
            )
            object.__setattr__(self, "r3_available_modes", modes)
        elif self.r3_available_modes:
            raise RecursionRouterError("r3_available_modes is only valid for R3 adaptive selection")

        child_fields = (
            self.child_request_id,
            self.child_request_generation,
            self.child_request_sha256,
        )
        if all(value is None for value in child_fields):
            pass
        elif any(value is None for value in child_fields):
            raise RecursionRouterError("child request identity fields must be all present or all absent")
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
            raise RecursionRouterError("parent recursion candidate fields must be all present or all absent")
        else:
            _identifier("parent_candidate_id", self.parent_candidate_id)
            _sha256("parent_candidate_sha256", self.parent_candidate_sha256)
            _remaining_edges(
                "parent_child_remaining_nested_edges",
                self.parent_child_remaining_nested_edges,
            )

        enables_r2 = self.requested_mode == R2 or (
            self.requested_mode == R3 and R2 in self.r3_available_modes
        )
        if enables_r2:
            if self.child_request_id is None:
                raise RecursionRouterError("R2-capable need requires exact child request identity")
        else:
            if self.child_request_id is not None:
                raise RecursionRouterError("non-R2-capable need must not carry child request identity")
            if self.remaining_nested_child_edges != 0:
                raise RecursionRouterError("non-R2-capable need must use zero nested-child edges")

        if self.parent_candidate_id is not None and enables_r2:
            if self.parent_child_remaining_nested_edges == 0:
                raise RecursionRouterError("parent recursion candidate has no remaining nested-child edge")
            if self.remaining_nested_child_edges != self.parent_child_remaining_nested_edges - 1:
                raise RecursionRouterError("nested R2 reroute must consume exactly one remaining child edge")
        elif self.parent_candidate_id is not None and self.remaining_nested_child_edges != 0:
            raise RecursionRouterError("non-R2 nested reroute must expose zero child-edge budget")

        identity = {
            "generation": self.generation,
            "route_candidate_id": self.route_candidate_id,
            "route_candidate_sha256": self.route_candidate_sha256,
            "requested_mode": self.requested_mode,
            "r3_available_modes": self.r3_available_modes,
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
            raise RecursionRouterError("need_id does not bind exact recursion need content")

    @classmethod
    def create(
        cls,
        *,
        route_candidate: RouteCandidate,
        requested_mode: str,
        generation: int,
        provenance_refs: Iterable[str],
        r3_available_modes: Iterable[str] = (),
        remaining_nested_child_edges: int = 0,
        child_request: NativeChildRequest | None = None,
        parent_candidate: RecursionRouteCandidate | None = None,
    ) -> "RecursionNeed":
        route_sha = _verify_route_candidate(route_candidate)
        _mode("requested_mode", requested_mode)
        _generation("need generation", generation)
        remaining_nested_child_edges = _remaining_edges(
            "remaining_nested_child_edges",
            remaining_nested_child_edges,
        )
        refs = _canonical_refs("provenance_refs", tuple(provenance_refs), require_nonempty=True)
        r3_modes = tuple(r3_available_modes)

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
            if type(parent_candidate) is not RecursionRouteCandidate:
                raise RecursionRouterError("parent_candidate must be exact RecursionRouteCandidate")
            if parent_candidate.selected_mechanism != R2:
                raise RecursionRouterError("parent_candidate must have selected R2 child harness")
            if parent_candidate.child_remaining_nested_child_edges is None:
                raise RecursionRouterError("parent_candidate lacks child remaining-depth evidence")
            parent_candidate_id = parent_candidate.candidate_id
            parent_candidate_sha256 = parent_candidate.sha256()
            parent_child_remaining_nested_edges = parent_candidate.child_remaining_nested_child_edges

        identity = {
            "generation": generation,
            "route_candidate_id": route_candidate.candidate_id,
            "route_candidate_sha256": route_sha,
            "requested_mode": requested_mode,
            "r3_available_modes": r3_modes,
            "remaining_nested_child_edges": remaining_nested_child_edges,
            "child_request_id": child_request_id,
            "child_request_generation": child_request_generation,
            "child_request_sha256": child_request_sha256,
            "parent_candidate_id": parent_candidate_id,
            "parent_candidate_sha256": parent_candidate_sha256,
            "parent_child_remaining_nested_edges": parent_child_remaining_nested_edges,
            "provenance_refs": refs,
        }
        return cls(schema=RECURSION_NEED_SCHEMA, need_id=_need_id(**identity), **identity)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RecursionNeed":
        if not isinstance(value, Mapping):
            raise RecursionRouterError("recursion need input must be a mapping")
        expected = {field.name for field in cls.__dataclass_fields__.values()}
        if set(value.keys()) != expected:
            raise RecursionRouterError("recursion need fields are not exact")
        r3_available_modes = value["r3_available_modes"]
        provenance_refs = value["provenance_refs"]
        if type(r3_available_modes) is list:
            r3_available_modes = tuple(r3_available_modes)
        if type(provenance_refs) is list:
            provenance_refs = tuple(provenance_refs)
        try:
            return cls(**{**dict(value), "r3_available_modes": r3_available_modes, "provenance_refs": provenance_refs})
        except (TypeError, ValueError) as exc:
            raise RecursionRouterError(f"invalid recursion need: {exc}") from exc

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["r3_available_modes"] = list(self.r3_available_modes)
        value["provenance_refs"] = list(self.provenance_refs)
        return value

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _verify_parent_binding(
    need: RecursionNeed,
    parent_candidate: RecursionRouteCandidate | None,
) -> None:
    if need.parent_candidate_id is None:
        if parent_candidate is not None:
            raise RecursionRouterError("unexpected parent recursion candidate")
        return
    if type(parent_candidate) is not RecursionRouteCandidate:
        raise RecursionRouterError("exact parent recursion candidate is required")
    if parent_candidate.candidate_id != need.parent_candidate_id:
        raise RecursionRouterError("parent recursion candidate id mismatch")
    if parent_candidate.sha256() != need.parent_candidate_sha256:
        raise RecursionRouterError("parent recursion candidate digest mismatch")
    if parent_candidate.selected_mechanism != R2:
        raise RecursionRouterError("parent recursion candidate must have selected R2")
    if parent_candidate.child_remaining_nested_child_edges != need.parent_child_remaining_nested_edges:
        raise RecursionRouterError("parent remaining nested-child evidence mismatch")


def _verify_child_binding(
    *,
    route_candidate: RouteCandidate,
    need: RecursionNeed,
    child_request: NativeChildRequest | None,
) -> tuple[str | None, str | None]:
    if need.child_request_id is None:
        if child_request is not None:
            raise RecursionRouterError("unexpected child request for non-R2-capable need")
        return None, None
    if child_request is None:
        raise RecursionRouterError("exact NativeChildRequest is required for R2-capable need")
    child_sha = _verify_child_request(child_request)
    if child_request.request_id != need.child_request_id:
        raise RecursionRouterError("recursion need child request id mismatch")
    if child_request.request_generation != need.child_request_generation:
        raise RecursionRouterError("recursion need child request generation mismatch")
    if child_sha != need.child_request_sha256:
        raise RecursionRouterError("recursion need child request digest mismatch")
    _verify_route_child_relation(route_candidate, child_request)
    if need.remaining_nested_child_edges > child_request.resource_budget.max_nested_depth:
        raise RecursionRouterError(
            "remaining nested-child edges exceed NativeChildRequest max_nested_depth"
        )
    return child_request.request_id, child_sha


def _route_compatible_modes(route_candidate: RouteCandidate) -> frozenset[str]:
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
    """Emit one deterministic evidence-only R0/R1/R2/R3 mechanism candidate."""

    route_sha = _verify_route_candidate(route_candidate)
    if type(need) is not RecursionNeed:
        raise RecursionRouterError("need must be exact concrete RecursionNeed")
    if type(policy) is not RecursionPolicy:
        raise RecursionRouterError("policy must be exact concrete RecursionPolicy")
    # Reconstruct at the consumer boundary before any need/policy field is read.
    # Frozen dataclasses are still mutable via object.__setattr__; canonical
    # reconstruction re-runs identity and policy invariants fail-closed.
    need = RecursionNeed.from_mapping(need.as_dict())
    policy = RecursionPolicy.from_mapping(policy.as_dict())
    if need.route_candidate_id != route_candidate.candidate_id:
        raise RecursionRouterError("recursion need route candidate id mismatch")
    if need.route_candidate_sha256 != route_sha:
        raise RecursionRouterError("recursion need route candidate digest mismatch")
    _verify_parent_binding(need, parent_candidate)

    if need.remaining_nested_child_edges > policy.max_nested_child_edges:
        raise RecursionRouterError("remaining nested-child edges exceed policy ceiling")

    compatible = _route_compatible_modes(route_candidate)
    requested = need.requested_mode

    if requested != R3:
        if requested not in policy.admitted_modes:
            raise RecursionRouterError("requested mechanism is not policy-admitted")
        if requested not in compatible:
            raise RecursionRouterError("requested mechanism contradicts upstream route")
        selected = requested
    else:
        if R3 not in policy.admitted_modes:
            raise RecursionRouterError("R3 adaptive selection is not policy-admitted")
        declared = set(need.r3_available_modes)
        incompatible = declared - compatible
        if incompatible:
            raise RecursionRouterError("R3 availability contains mechanism incompatible with upstream route")
        selected = ""
        for mechanism in policy.r3_preference_order:
            if mechanism in declared and mechanism in policy.admitted_modes:
                selected = mechanism
                break
        if not selected:
            raise RecursionRouterError("R3 has no route-compatible policy-admitted lower mechanism")

    child_request_id, child_request_sha = _verify_child_binding(
        route_candidate=route_candidate,
        need=need,
        child_request=child_request,
    )

    if selected == R0:
        if child_request_id is not None or need.remaining_nested_child_edges != 0:
            raise RecursionRouterError("R0 deterministic path cannot carry child/depth evidence")
        reason_codes = (
            "R3_ADAPTIVE_SELECTED_R0" if requested == R3 else "R0_DETERMINISTIC_ADMITTED",
        )
        child_remaining = None
    elif selected == R1:
        if child_request_id is not None and requested != R3:
            raise RecursionRouterError("R1 model-recursion path does not require NativeChildRequest")
        if need.remaining_nested_child_edges != 0 and R2 not in need.r3_available_modes:
            raise RecursionRouterError("R1 model-recursion path cannot carry nested-child depth")
        reason_codes = (
            "R3_ADAPTIVE_SELECTED_R1" if requested == R3 else "R1_MODEL_RECURSION_CANDIDATE_ADMITTED",
        )
        child_remaining = None
    elif selected == R2:
        if child_request_id is None:
            raise RecursionRouterError("R2 child harness requires exact child request evidence")
        reason_codes = (
            "R3_ADAPTIVE_SELECTED_R2" if requested == R3 else "R2_NATIVE_CHILD_HARNESS_ADMITTED",
        )
        child_remaining = need.remaining_nested_child_edges
    else:
        raise RecursionRouterError("adaptive selection produced unsupported lower mechanism")

    need_sha = need.sha256()
    policy_sha = policy.sha256()
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
        "requested_mode": requested,
        "selected_mechanism": selected,
        "remaining_nested_child_edges": need.remaining_nested_child_edges,
        "child_remaining_nested_child_edges": child_remaining,
        "reason_codes": reason_codes,
    }
    return RecursionRouteCandidate(
        schema=RECURSION_ROUTE_CANDIDATE_SCHEMA,
        candidate_id=_candidate_id(**identity),
        **identity,
    )
