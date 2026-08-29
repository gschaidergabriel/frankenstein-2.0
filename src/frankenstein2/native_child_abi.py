"""F2-WP-601 deterministic Native Child request ABI.

This component is a request/identity contract only.  It deliberately reuses the
accepted F2-WP-102 ``NativeChildBinding`` as the child causal/provenance identity
instead of creating a second identity authority.

Requested capabilities are untrusted input claims.  A request created here does not
spawn a child, grant a capability, execute a tool/model/provider, persist state,
reconcile a child result, authorize an effect, or mint completion/runtime credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .causal_identity import CausalIdentity
from .native_child_binding import NativeChildBinding

ABI_VERSION = "F2_NATIVE_CHILD_ABI/v1"
_MAX_IDENTIFIER_LENGTH = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class NativeChildABIError(ValueError):
    """Raised when a Native Child request violates the WP601 contract."""


def _identifier(name: str, value: Any) -> str:
    if type(value) is not str:
        raise NativeChildABIError(f"{name} must be a string")
    if not value or value != value.strip():
        raise NativeChildABIError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise NativeChildABIError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise NativeChildABIError(f"{name} contains control characters")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 1:
        raise NativeChildABIError(f"{name} must be a positive integer")
    return value


def _nonnegative_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise NativeChildABIError(f"{name} must be a non-negative integer")
    return value


def _digest(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise NativeChildABIError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _canonical_refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise NativeChildABIError(f"{name} must be an immutable tuple")
    for item in value:
        _identifier(f"{name} item", item)
    if len(set(value)) != len(value):
        raise NativeChildABIError(f"{name} must not contain duplicates")
    if value != tuple(sorted(value)):
        raise NativeChildABIError(f"{name} must be in canonical lexical order")
    return value


@dataclass(frozen=True, slots=True)
class ChildResourceBudget:
    """Declarative upper bounds; this object does not enforce or spend resources."""

    max_work_units: int
    max_duration_ms: int
    max_output_bytes: int
    max_nested_depth: int
    max_tool_calls: int

    def __post_init__(self) -> None:
        _positive_int("max_work_units", self.max_work_units)
        _positive_int("max_duration_ms", self.max_duration_ms)
        _nonnegative_int("max_output_bytes", self.max_output_bytes)
        _nonnegative_int("max_nested_depth", self.max_nested_depth)
        _nonnegative_int("max_tool_calls", self.max_tool_calls)

    def as_dict(self) -> dict[str, int]:
        return {
            "max_work_units": self.max_work_units,
            "max_duration_ms": self.max_duration_ms,
            "max_output_bytes": self.max_output_bytes,
            "max_nested_depth": self.max_nested_depth,
            "max_tool_calls": self.max_tool_calls,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ChildResourceBudget":
        if not isinstance(value, Mapping):
            raise NativeChildABIError("resource_budget must be a mapping")
        expected = {
            "max_work_units",
            "max_duration_ms",
            "max_output_bytes",
            "max_nested_depth",
            "max_tool_calls",
        }
        keys = set(value.keys())
        if keys != expected:
            missing = expected - keys
            extra = keys - expected
            details: list[str] = []
            if missing:
                details.append("missing=" + ",".join(sorted(map(str, missing))))
            if extra:
                details.append("unexpected=" + ",".join(sorted(map(str, extra))))
            raise NativeChildABIError("invalid resource_budget fields: " + "; ".join(details))
        return cls(
            max_work_units=value["max_work_units"],
            max_duration_ms=value["max_duration_ms"],
            max_output_bytes=value["max_output_bytes"],
            max_nested_depth=value["max_nested_depth"],
            max_tool_calls=value["max_tool_calls"],
        )


@dataclass(frozen=True, slots=True)
class NativeChildRequest:
    """Immutable Native Child execution request candidate.

    ``requested_capability_refs`` are requests, not grants.  The actual executor must
    resolve them against a separate canonical capability authority before execution.
    """

    request_id: str
    request_generation: int
    abi_version: str
    binding: NativeChildBinding
    binding_id: str
    binding_sha256: str
    child_runtime_class: str
    payload_ref: str
    payload_sha256: str
    input_refs: tuple[str, ...]
    requested_capability_refs: tuple[str, ...]
    resource_budget: ChildResourceBudget

    def __post_init__(self) -> None:
        _identifier("request_id", self.request_id)
        _positive_int("request_generation", self.request_generation)
        if self.abi_version != ABI_VERSION:
            raise NativeChildABIError(f"abi_version must equal {ABI_VERSION}")

        # Exact concrete types are deliberate trust boundaries.  Recent F2 falsifiers
        # showed that isinstance + polymorphic serialization can self-attest one value
        # while downstream direct attribute consumption observes another.
        if type(self.binding) is not NativeChildBinding:
            raise NativeChildABIError("binding must be exact concrete NativeChildBinding")
        if type(self.binding.parent) is not CausalIdentity or type(self.binding.child) is not CausalIdentity:
            raise NativeChildABIError("binding parent/child must be exact concrete CausalIdentity")
        if self.binding.has_result:
            raise NativeChildABIError("binding must be pending; WP601 does not admit already-bound results")

        _identifier("binding_id", self.binding_id)
        _digest("binding_sha256", self.binding_sha256)
        if self.binding_id != self.binding.binding_id():
            raise NativeChildABIError("binding_id does not match exact NativeChildBinding")
        if self.binding_sha256 != self.binding.sha256():
            raise NativeChildABIError("binding_sha256 does not match exact NativeChildBinding")

        _identifier("child_runtime_class", self.child_runtime_class)
        _identifier("payload_ref", self.payload_ref)
        _digest("payload_sha256", self.payload_sha256)
        _canonical_refs("input_refs", self.input_refs)
        _canonical_refs("requested_capability_refs", self.requested_capability_refs)
        if type(self.resource_budget) is not ChildResourceBudget:
            raise NativeChildABIError("resource_budget must be exact concrete ChildResourceBudget")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "NativeChildRequest":
        if not isinstance(value, Mapping):
            raise NativeChildABIError("request input must be a mapping")
        expected = {
            "request_id",
            "request_generation",
            "abi_version",
            "binding",
            "binding_id",
            "binding_sha256",
            "child_runtime_class",
            "payload_ref",
            "payload_sha256",
            "input_refs",
            "requested_capability_refs",
            "resource_budget",
        }
        keys = set(value.keys())
        if keys != expected:
            missing = expected - keys
            extra = keys - expected
            details: list[str] = []
            if missing:
                details.append("missing=" + ",".join(sorted(map(str, missing))))
            if extra:
                details.append("unexpected=" + ",".join(sorted(map(str, extra))))
            raise NativeChildABIError("invalid request fields: " + "; ".join(details))
        try:
            binding = NativeChildBinding.from_mapping(value["binding"])
        except (TypeError, ValueError) as exc:
            raise NativeChildABIError(f"invalid native-child binding: {exc}") from exc
        return cls(
            request_id=value["request_id"],
            request_generation=value["request_generation"],
            abi_version=value["abi_version"],
            binding=binding,
            binding_id=value["binding_id"],
            binding_sha256=value["binding_sha256"],
            child_runtime_class=value["child_runtime_class"],
            payload_ref=value["payload_ref"],
            payload_sha256=value["payload_sha256"],
            input_refs=tuple(value["input_refs"]) if type(value["input_refs"]) is list else value["input_refs"],
            requested_capability_refs=(
                tuple(value["requested_capability_refs"])
                if type(value["requested_capability_refs"]) is list
                else value["requested_capability_refs"]
            ),
            resource_budget=ChildResourceBudget.from_mapping(value["resource_budget"]),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_generation": self.request_generation,
            "abi_version": self.abi_version,
            "binding": self.binding.as_dict(),
            "binding_id": self.binding_id,
            "binding_sha256": self.binding_sha256,
            "child_runtime_class": self.child_runtime_class,
            "payload_ref": self.payload_ref,
            "payload_sha256": self.payload_sha256,
            "input_refs": list(self.input_refs),
            "requested_capability_refs": list(self.requested_capability_refs),
            "resource_budget": self.resource_budget.as_dict(),
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def verify_native_child_request(
    request: NativeChildRequest,
    *,
    expected_request_id: str,
    expected_request_generation: int,
    expected_binding_id: str,
    expected_binding_sha256: str,
    expected_request_sha256: str,
) -> NativeChildRequest:
    """Revalidate an exact request at a consumer boundary and return it unchanged."""

    if type(request) is not NativeChildRequest:
        raise NativeChildABIError("request must be exact concrete NativeChildRequest")
    _identifier("expected_request_id", expected_request_id)
    _positive_int("expected_request_generation", expected_request_generation)
    _identifier("expected_binding_id", expected_binding_id)
    _digest("expected_binding_sha256", expected_binding_sha256)
    _digest("expected_request_sha256", expected_request_sha256)

    # Reconstruct from canonical fields so every nested validation is repeated before
    # any downstream direct attribute consumption.
    reconstructed = NativeChildRequest.from_mapping(request.as_dict())
    if reconstructed != request:
        raise NativeChildABIError("request canonical reconstruction mismatch")
    if request.request_id != expected_request_id:
        raise NativeChildABIError("request_id does not match expected identity")
    if request.request_generation != expected_request_generation:
        raise NativeChildABIError("request_generation does not match expected generation")
    if request.binding_id != expected_binding_id:
        raise NativeChildABIError("binding_id does not match expected identity")
    if request.binding_sha256 != expected_binding_sha256:
        raise NativeChildABIError("binding_sha256 does not match expected digest")
    if request.sha256() != expected_request_sha256:
        raise NativeChildABIError("request SHA-256 does not match expected digest")
    return request
