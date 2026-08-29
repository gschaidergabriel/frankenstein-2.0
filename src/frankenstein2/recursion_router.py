"""F2-WP-603 deterministic bounded recursion-route candidate layer.

This component composes the already-landed F2-WP-600 route candidate and the
F2-WP-601 Native Child request/budget contract.  It does not inspect task payload
text or infer task semantics/complexity.  The caller explicitly supplies the desired
recursion depth (R0/R1/R2/R3), while an explicit policy supplies the admitted depth
set and ceiling.

Outputs are immutable evidence/provenance candidates only.  Nothing here spawns a
child, transports a payload, executes a tool/model/provider, grants capabilities,
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

RECURSION_NEED_SCHEMA = "FRANKENSTEIN2_RECURSION_NEED/v1"
RECURSION_POLICY_SCHEMA = "FRANKENSTEIN2_RECURSION_POLICY/v1"
RECURSION_ROUTE_CANDIDATE_SCHEMA = "FRANKENSTEIN2_RECURSION_ROUTE_CANDIDATE/v1"
RECURSION_ROUTE_CLASSIFICATION = (
    "EVIDENCE_ONLY_NOT_CHILD_SPAWN_TRANSPORT_EXECUTION_EFFECT_OR_COMPLETION_AUTHORITY"
)

R0 = "R0"
R1 = "R1"
R2 = "R2"
R3 = "R3"
_DEPTH_TO_LEVEL = {0: R0, 1: R1, 2: R2, 3: R3}
_LEVEL_TO_DEPTH = {value: key for key, value in _DEPTH_TO_LEVEL.items()}
_ALLOWED_DEPTHS = frozenset(_DEPTH_TO_LEVEL)
_MAX_IDENTIFIER_LENGTH = 512
_MAX_REF_COUNT = 4096
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RecursionRouterError(ValueError):
    """Fail-closed WP603 recursion admission/routing error."""


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


def _depth(name: str, value: Any) -> int:
    if type(value) is not int or value not in _ALLOWED_DEPTHS:
        raise RecursionRouterError(f"{name} must be an exact integer in [0, 3]")
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


def _need_identity_payload(
    *,
    generation: int,
    route_candidate_id: str,
    route_candidate_sha256: str,
    requested_depth: int,
    child_request_id: str | None,
    child_request_generation: int | None,
    child_request_sha256: str | None,
    provenance_refs: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "generation": generation,
        "route_candidate_id": route_candidate_id,
        "route_candidate_sha256": route_candidate_sha256,
        "requested_depth": requested_depth,
        "child_request_id": child_request_id,
        "child_request_generation": child_request_generation,
        "child_request_sha256": child_request_sha256,
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
    selected_depth: int,
    selected_level: str,
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
        "selected_depth": selected_depth,
        "selected_level": selected_level,
        "reason_codes": list(reason_codes),
    }


def _candidate_id(**identity_fields: Any) -> str:
    return "recursion-route:" + _digest(_candidate_identity_payload(**identity_fields))


@dataclass(frozen=True, slots=True)
class RecursionNeed:
    """Caller-supplied recursion intent bound to exact upstream identities/digests."""

    schema: str
    need_id: str
    generation: int
    route_candidate_id: str
    route_candidate_sha256: str
    requested_depth: int
    child_request_id: str | None
    child_request_generation: int | None
    child_request_sha256: str | None
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != RECURSION_NEED_SCHEMA:
            raise RecursionRouterError("recursion need schema mismatch")
        _identifier("need_id", self.need_id)
        _generation("need generation", self.generation)
        _identifier("route_candidate_id", self.route_candidate_id)
        _sha256("route_candidate_sha256", self.route_candidate_sha256)
        _depth("requested_depth", self.requested_depth)
        refs = _canonical_refs("provenance_refs", self.provenance_refs, require_nonempty=True)
        object.__setattr__(self, "provenance_refs", refs)

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

        expected_id = _need_id(
            generation=self.generation,
            route_candidate_id=self.route_candidate_id,
            route_candidate_sha256=self.route_candidate_sha256,
            requested_depth=self.requested_depth,
            child_request_id=self.child_request_id,
            child_request_generation=self.child_request_generation,
            child_request_sha256=self.child_request_sha256,
            provenance_refs=self.provenance_refs,
        )
        if self.need_id != expected_id:
            raise RecursionRouterError("need_id does not bind exact recursion need content")

    @classmethod
    def create(
        cls,
        *,
        route_candidate: RouteCandidate,
        requested_depth: int,
        generation: int,
        provenance_refs: Iterable[str],
        child_request: NativeChildRequest | None = None,
    ) -> "RecursionNeed":
        route_sha = _verify_route_candidate(route_candidate)
        _depth("requested_depth", requested_depth)
        _generation("need generation", generation)
        refs = _canonical_refs("provenance_refs", tuple(provenance_refs), require_nonempty=True)
        if child_request is None:
            child_request_id = None
            child_request_generation = None
            child_request_sha256 = None
        else:
            child_request_sha256 = _verify_child_request(child_request)
            child_request_id = child_request.request_id
            child_request_generation = child_request.request_generation
        identity = {
            "generation": generation,
            "route_candidate_id": route_candidate.candidate_id,
            "route_candidate_sha256": route_sha,
            "requested_depth": requested_depth,
            "child_request_id": child_request_id,
            "child_request_generation": child_request_generation,
            "child_request_sha256": child_request_sha256,
            "provenance_refs": refs,
        }
        return cls(
            schema=RECURSION_NEED_SCHEMA,
            need_id=_need_id(**identity),
            **identity,
        )

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["provenance_refs"] = list(self.provenance_refs)
        return value

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RecursionPolicy:
    """Explicit depth admission policy; never an execution/capability authority."""

    schema: str
    policy_id: str
    generation: int
    max_recursion_depth: int
    admitted_depths: tuple[int, ...]
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != RECURSION_POLICY_SCHEMA:
            raise RecursionRouterError("recursion policy schema mismatch")
        _identifier("policy_id", self.policy_id)
        _generation("policy generation", self.generation)
        _depth("max_recursion_depth", self.max_recursion_depth)
        if type(self.admitted_depths) is not tuple or not self.admitted_depths:
            raise RecursionRouterError("admitted_depths must be a non-empty immutable tuple")
        for value in self.admitted_depths:
            _depth("admitted depth", value)
        if self.admitted_depths != tuple(sorted(set(self.admitted_depths))):
            raise RecursionRouterError("admitted_depths must be unique canonical ascending depths")
        if any(value > self.max_recursion_depth for value in self.admitted_depths):
            raise RecursionRouterError("admitted depth exceeds max_recursion_depth")
        refs = _canonical_refs("provenance_refs", self.provenance_refs, require_nonempty=True)
        object.__setattr__(self, "provenance_refs", refs)

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        generation: int,
        max_recursion_depth: int,
        admitted_depths: Iterable[int],
        provenance_refs: Iterable[str],
    ) -> "RecursionPolicy":
        return cls(
            schema=RECURSION_POLICY_SCHEMA,
            policy_id=policy_id,
            generation=generation,
            max_recursion_depth=max_recursion_depth,
            admitted_depths=tuple(admitted_depths),
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "max_recursion_depth": self.max_recursion_depth,
            "admitted_depths": list(self.admitted_depths),
            "provenance_refs": list(self.provenance_refs),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RecursionRouteCandidate:
    """Evidence-only R0/R1/R2/R3 routing result bound to exact inputs."""

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
    selected_depth: int
    selected_level: str
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
        _depth("selected_depth", self.selected_depth)
        if self.selected_level not in _LEVEL_TO_DEPTH:
            raise RecursionRouterError("selected_level must be one of R0/R1/R2/R3")
        if _LEVEL_TO_DEPTH[self.selected_level] != self.selected_depth:
            raise RecursionRouterError("selected_level does not match selected_depth")
        reasons = _canonical_refs("reason_codes", self.reason_codes, require_nonempty=True)
        object.__setattr__(self, "reason_codes", reasons)
        expected_id = _candidate_id(
            need_id=self.need_id,
            need_sha256=self.need_sha256,
            route_candidate_id=self.route_candidate_id,
            route_candidate_sha256=self.route_candidate_sha256,
            child_request_id=self.child_request_id,
            child_request_sha256=self.child_request_sha256,
            policy_id=self.policy_id,
            policy_generation=self.policy_generation,
            policy_sha256=self.policy_sha256,
            selected_depth=self.selected_depth,
            selected_level=self.selected_level,
            reason_codes=self.reason_codes,
        )
        if self.candidate_id != expected_id:
            raise RecursionRouterError("candidate_id does not bind exact recursion route content")

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def route_recursion(
    *,
    route_candidate: RouteCandidate,
    need: RecursionNeed,
    policy: RecursionPolicy,
    child_request: NativeChildRequest | None = None,
) -> RecursionRouteCandidate:
    """Emit one deterministic evidence-only R0/R1/R2/R3 route candidate.

    No task semantics are inferred.  ``need.requested_depth`` is the sole desired-depth
    input; upstream route kind, explicit policy and child budget only constrain whether
    that caller-supplied request is admissible.
    """

    route_sha = _verify_route_candidate(route_candidate)
    if type(need) is not RecursionNeed:
        raise RecursionRouterError("need must be exact concrete RecursionNeed")
    if type(policy) is not RecursionPolicy:
        raise RecursionRouterError("policy must be exact concrete RecursionPolicy")

    if need.route_candidate_id != route_candidate.candidate_id:
        raise RecursionRouterError("recursion need route candidate id mismatch")
    if need.route_candidate_sha256 != route_sha:
        raise RecursionRouterError("recursion need route candidate digest mismatch")

    requested_depth = need.requested_depth
    if requested_depth > policy.max_recursion_depth:
        raise RecursionRouterError("requested recursion depth exceeds policy ceiling")
    if requested_depth not in policy.admitted_depths:
        raise RecursionRouterError("requested recursion depth is not policy-admitted")

    child_request_id: str | None = None
    child_request_sha: str | None = None

    if route_candidate.selected_route == DIRECT_SMALL:
        if requested_depth != 0:
            raise RecursionRouterError("DIRECT_SMALL cannot be paired with nonzero recursion")
        if child_request is not None:
            raise RecursionRouterError("DIRECT_SMALL R0 cannot be paired with a NativeChildRequest")
        if any(
            value is not None
            for value in (
                need.child_request_id,
                need.child_request_generation,
                need.child_request_sha256,
            )
        ):
            raise RecursionRouterError("DIRECT_SMALL R0 recursion need must not claim child request identity")
        reason_codes = ("DIRECT_SMALL_REQUIRES_R0",)

    elif route_candidate.selected_route == DELEGATE_BUILD:
        if requested_depth == 0:
            raise RecursionRouterError("DELEGATE_BUILD requires an admitted nonzero child recursion depth")
        if child_request is None:
            raise RecursionRouterError("DELEGATE_BUILD requires an exact NativeChildRequest")
        child_request_sha = _verify_child_request(child_request)
        child_request_id = child_request.request_id
        if need.child_request_id != child_request.request_id:
            raise RecursionRouterError("recursion need child request id mismatch")
        if need.child_request_generation != child_request.request_generation:
            raise RecursionRouterError("recursion need child request generation mismatch")
        if need.child_request_sha256 != child_request_sha:
            raise RecursionRouterError("recursion need child request digest mismatch")

        # Bind only explicit common identity/content fields.  Never infer equivalence
        # from payload text or model output.
        if route_candidate.task_id != child_request.binding.parent.task_id:
            raise RecursionRouterError("routed task_id does not match child binding parent task_id")
        if route_candidate.task_sha256 != child_request.payload_sha256:
            raise RecursionRouterError("routed task digest does not match child payload digest")
        if child_request.resource_budget.max_nested_depth < requested_depth:
            raise RecursionRouterError("NativeChildRequest max_nested_depth cannot cover selected recursion depth")
        reason_codes = ("DELEGATE_BUILD_EXPLICIT_DEPTH_ADMITTED",)

    else:
        # RouteCandidate itself should already reject this, but keep the boundary explicit.
        raise RecursionRouterError("unsupported upstream route candidate")

    need_sha = need.sha256()
    policy_sha = policy.sha256()
    selected_level = _DEPTH_TO_LEVEL[requested_depth]
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
        "selected_depth": requested_depth,
        "selected_level": selected_level,
        "reason_codes": reason_codes,
    }
    return RecursionRouteCandidate(
        schema=RECURSION_ROUTE_CANDIDATE_SCHEMA,
        candidate_id=_candidate_id(**identity),
        **identity,
    )
