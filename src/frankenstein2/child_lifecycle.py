"""F2-WP-604 deterministic child lifecycle/generation candidate contract.

This component controls evidence/provenance for resume, replacement and nested-spawn
requests.  It does not perform any of those operations.  It consumes the already-
accepted WP601 NativeChildRequest boundary, requires exact caller-supplied lifecycle
state and generation, and emits an immutable content-bound candidate only.

No provider/model/tool is invoked here.  No UnifiedDB/DeliveryStore state is mutated and
no execution, effect, completion, runtime, GRID/GWT/J-Space or whole-system credit is
minted by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .native_child_abi import NativeChildRequest, verify_native_child_request

LIFECYCLE_VERSION = "F2_CHILD_LIFECYCLE/v1"
RESUME = "RESUME"
REPLACE = "REPLACE"
NESTED_SPAWN = "NESTED_SPAWN"
WAITING = "WAITING"
RUNNING = "RUNNING"
TERMINAL = "TERMINAL"
_OPERATIONS = frozenset({RESUME, REPLACE, NESTED_SPAWN})
_STATES = frozenset({WAITING, RUNNING, TERMINAL})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_IDENTIFIER_LENGTH = 512


class ChildLifecycleError(ValueError):
    """Raised when a WP604 lifecycle candidate violates the fail-closed contract."""


def _identifier(name: str, value: Any) -> str:
    if type(value) is not str:
        raise ChildLifecycleError(f"{name} must be a string")
    if not value or value != value.strip():
        raise ChildLifecycleError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise ChildLifecycleError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ChildLifecycleError(f"{name} contains control characters")
    return value


def _digest(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ChildLifecycleError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _json_int(name: str, value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        qualifier = "positive" if minimum == 1 else "non-negative"
        raise ChildLifecycleError(f"{name} must be a {qualifier} integer")
    try:
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ChildLifecycleError(f"{name} is outside the canonical JSON integer domain") from exc
    return value


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ChildLifecycleError("lifecycle value is not canonically JSON serializable") from exc


@dataclass(frozen=True, slots=True)
class ChildLifecyclePolicy:
    """Deterministic declaration-only lifecycle bounds."""

    max_generation: int
    max_nested_depth: int

    def __post_init__(self) -> None:
        _json_int("max_generation", self.max_generation, minimum=1)
        _json_int("max_nested_depth", self.max_nested_depth)

    def as_dict(self) -> dict[str, int]:
        return {
            "max_generation": self.max_generation,
            "max_nested_depth": self.max_nested_depth,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ChildLifecyclePolicy":
        if not isinstance(value, Mapping) or set(value.keys()) != {"max_generation", "max_nested_depth"}:
            raise ChildLifecycleError("invalid lifecycle policy fields")
        return cls(
            max_generation=value["max_generation"],
            max_nested_depth=value["max_nested_depth"],
        )


@dataclass(frozen=True, slots=True)
class ChildLifecycleCandidate:
    """Immutable non-executing child lifecycle transition candidate."""

    lifecycle_version: str
    operation: str
    current_state: str
    request: NativeChildRequest
    request_id: str
    request_generation: int
    request_sha256: str
    binding_id: str
    binding_sha256: str
    expected_current_generation: int
    next_generation: int
    requested_nested_depth: int
    replacement_binding_id: str | None
    policy: ChildLifecyclePolicy

    def __post_init__(self) -> None:
        if self.lifecycle_version != LIFECYCLE_VERSION:
            raise ChildLifecycleError(f"lifecycle_version must equal {LIFECYCLE_VERSION}")
        if self.operation not in _OPERATIONS:
            raise ChildLifecycleError("operation is not admitted")
        if self.current_state not in _STATES:
            raise ChildLifecycleError("current_state is not admitted")
        if type(self.request) is not NativeChildRequest:
            raise ChildLifecycleError("request must be exact concrete NativeChildRequest")
        _identifier("request_id", self.request_id)
        _json_int("request_generation", self.request_generation, minimum=1)
        _digest("request_sha256", self.request_sha256)
        _identifier("binding_id", self.binding_id)
        _digest("binding_sha256", self.binding_sha256)
        _json_int("expected_current_generation", self.expected_current_generation, minimum=1)
        _json_int("next_generation", self.next_generation, minimum=1)
        _json_int("requested_nested_depth", self.requested_nested_depth)
        if self.replacement_binding_id is not None:
            _identifier("replacement_binding_id", self.replacement_binding_id)
        if type(self.policy) is not ChildLifecyclePolicy:
            raise ChildLifecycleError("policy must be exact concrete ChildLifecyclePolicy")

        try:
            verify_native_child_request(
                self.request,
                expected_request_id=self.request_id,
                expected_request_generation=self.request_generation,
                expected_binding_id=self.binding_id,
                expected_binding_sha256=self.binding_sha256,
                expected_request_sha256=self.request_sha256,
            )
        except (TypeError, ValueError) as exc:
            raise ChildLifecycleError(f"invalid predecessor NativeChildRequest: {exc}") from exc

        if self.expected_current_generation != self.request_generation:
            raise ChildLifecycleError("stale or mismatched current generation")
        if self.next_generation != self.expected_current_generation + 1:
            raise ChildLifecycleError("next_generation must be exactly current generation + 1")
        if self.next_generation > self.policy.max_generation:
            raise ChildLifecycleError("next_generation exceeds lifecycle policy ceiling")

        if self.operation == RESUME:
            if self.current_state != WAITING:
                raise ChildLifecycleError("RESUME requires exact WAITING state")
            if self.requested_nested_depth != 0:
                raise ChildLifecycleError("RESUME cannot request nested depth")
            if self.replacement_binding_id is not None:
                raise ChildLifecycleError("RESUME cannot carry replacement binding identity")

        elif self.operation == REPLACE:
            if self.current_state not in {WAITING, RUNNING, TERMINAL}:
                raise ChildLifecycleError("REPLACE requires an admitted current state")
            if self.requested_nested_depth != 0:
                raise ChildLifecycleError("REPLACE cannot request nested depth")
            if self.replacement_binding_id is None:
                raise ChildLifecycleError("REPLACE requires explicit new binding identity")
            if self.replacement_binding_id == self.binding_id:
                raise ChildLifecycleError("replacement must use a new binding identity")

        elif self.operation == NESTED_SPAWN:
            if self.current_state == TERMINAL:
                raise ChildLifecycleError("TERMINAL child cannot request nested spawn")
            if self.requested_nested_depth < 1:
                raise ChildLifecycleError("NESTED_SPAWN requires depth >= 1")
            if self.replacement_binding_id is not None:
                raise ChildLifecycleError("NESTED_SPAWN cannot carry replacement binding identity")
            if self.requested_nested_depth > self.policy.max_nested_depth:
                raise ChildLifecycleError("requested nested depth exceeds lifecycle policy")
            if self.requested_nested_depth > self.request.resource_budget.max_nested_depth:
                raise ChildLifecycleError("requested nested depth exceeds NativeChildRequest budget")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ChildLifecycleCandidate":
        if not isinstance(value, Mapping):
            raise ChildLifecycleError("candidate input must be a mapping")
        expected = {
            "lifecycle_version",
            "operation",
            "current_state",
            "request",
            "request_id",
            "request_generation",
            "request_sha256",
            "binding_id",
            "binding_sha256",
            "expected_current_generation",
            "next_generation",
            "requested_nested_depth",
            "replacement_binding_id",
            "policy",
        }
        if set(value.keys()) != expected:
            raise ChildLifecycleError("invalid lifecycle candidate fields")
        try:
            request = NativeChildRequest.from_mapping(value["request"])
        except (TypeError, ValueError) as exc:
            raise ChildLifecycleError(f"invalid predecessor request mapping: {exc}") from exc
        return cls(
            lifecycle_version=value["lifecycle_version"],
            operation=value["operation"],
            current_state=value["current_state"],
            request=request,
            request_id=value["request_id"],
            request_generation=value["request_generation"],
            request_sha256=value["request_sha256"],
            binding_id=value["binding_id"],
            binding_sha256=value["binding_sha256"],
            expected_current_generation=value["expected_current_generation"],
            next_generation=value["next_generation"],
            requested_nested_depth=value["requested_nested_depth"],
            replacement_binding_id=value["replacement_binding_id"],
            policy=ChildLifecyclePolicy.from_mapping(value["policy"]),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "lifecycle_version": self.lifecycle_version,
            "operation": self.operation,
            "current_state": self.current_state,
            "request": self.request.as_dict(),
            "request_id": self.request_id,
            "request_generation": self.request_generation,
            "request_sha256": self.request_sha256,
            "binding_id": self.binding_id,
            "binding_sha256": self.binding_sha256,
            "expected_current_generation": self.expected_current_generation,
            "next_generation": self.next_generation,
            "requested_nested_depth": self.requested_nested_depth,
            "replacement_binding_id": self.replacement_binding_id,
            "policy": self.policy.as_dict(),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def lifecycle_id(self) -> str:
        return "wlc:" + self.sha256()


def build_child_lifecycle_candidate(
    *,
    operation: str,
    current_state: str,
    request: NativeChildRequest,
    expected_current_generation: int,
    requested_nested_depth: int,
    replacement_binding_id: str | None,
    policy: ChildLifecyclePolicy,
) -> ChildLifecycleCandidate:
    """Build one lifecycle candidate from exact caller-supplied state only."""

    if type(request) is not NativeChildRequest:
        raise ChildLifecycleError("request must be exact concrete NativeChildRequest")
    if type(policy) is not ChildLifecyclePolicy:
        raise ChildLifecycleError("policy must be exact concrete ChildLifecyclePolicy")
    # Validate all arithmetic inputs before computing derived values.  This keeps malformed
    # booleans/strings/objects inside the WP604 fail-closed error surface rather than leaking
    # a raw Python TypeError before the dataclass boundary can validate them.
    current_generation = _json_int(
        "expected_current_generation", expected_current_generation, minimum=1
    )
    nested_depth = _json_int("requested_nested_depth", requested_nested_depth)
    return ChildLifecycleCandidate(
        lifecycle_version=LIFECYCLE_VERSION,
        operation=operation,
        current_state=current_state,
        request=request,
        request_id=request.request_id,
        request_generation=request.request_generation,
        request_sha256=request.sha256(),
        binding_id=request.binding_id,
        binding_sha256=request.binding_sha256,
        expected_current_generation=current_generation,
        next_generation=current_generation + 1,
        requested_nested_depth=nested_depth,
        replacement_binding_id=replacement_binding_id,
        policy=policy,
    )


def verify_child_lifecycle_candidate(
    candidate: ChildLifecycleCandidate,
    *,
    expected_lifecycle_id: str,
    expected_sha256: str,
    expected_operation: str,
    expected_current_generation: int,
) -> ChildLifecycleCandidate:
    """Revalidate exact canonical lifecycle evidence at a consumer boundary."""

    if type(candidate) is not ChildLifecycleCandidate:
        raise ChildLifecycleError("candidate must be exact concrete ChildLifecycleCandidate")
    _identifier("expected_lifecycle_id", expected_lifecycle_id)
    _digest("expected_sha256", expected_sha256)
    if expected_operation not in _OPERATIONS:
        raise ChildLifecycleError("expected_operation is not admitted")
    _json_int("expected_current_generation", expected_current_generation, minimum=1)
    reconstructed = ChildLifecycleCandidate.from_mapping(candidate.as_dict())
    if reconstructed != candidate:
        raise ChildLifecycleError("candidate canonical reconstruction mismatch")
    if candidate.lifecycle_id() != expected_lifecycle_id:
        raise ChildLifecycleError("lifecycle identity mismatch")
    if candidate.sha256() != expected_sha256:
        raise ChildLifecycleError("lifecycle digest mismatch")
    if candidate.operation != expected_operation:
        raise ChildLifecycleError("lifecycle operation mismatch")
    if candidate.expected_current_generation != expected_current_generation:
        raise ChildLifecycleError("lifecycle generation mismatch")
    return candidate
