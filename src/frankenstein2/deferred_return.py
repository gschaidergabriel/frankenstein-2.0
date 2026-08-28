"""Deferred causal return envelope for Frankenstein 2.0.

F2-WP-104 models one thing only: a result already bound to an explicitly
delegated child may become eligible for causal re-entry into its parent agent.
It does not model transport delivery/ACK, execute effects, decide task success,
or assert completion. Those authorities remain outside this component.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from .causal_identity import CausalIdentity
from .native_child_binding import NativeChildBinding, NativeChildBindingError

_MAX_IDENTIFIER_LENGTH = 512
_REQUIRED_FIELDS = ("return_id", "binding", "resume")
_ALLOWED_FIELDS = frozenset(_REQUIRED_FIELDS)


class DeferredReturnError(ValueError):
    """Raised when deferred-return provenance is incomplete or contradictory."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise DeferredReturnError(f"{name} must be a string")
    if not value or value != value.strip():
        raise DeferredReturnError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise DeferredReturnError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise DeferredReturnError(f"{name} contains control characters")
    return value


@dataclass(frozen=True, slots=True)
class DeferredReturnEnvelope:
    """Immutable eligibility envelope for one child result to re-enter a parent.

    ``binding`` must already contain an immutable result identity/digest.
    ``resume`` is a fresh causal step owned by the original parent agent/task,
    causally descending from the child and at a strictly later generation.

    Constructing this object proves only identity/provenance consistency. It
    does not prove that any transport delivered the result, that the parent
    consumed it, that an external effect occurred, or that the task completed.
    """

    return_id: str
    binding: NativeChildBinding
    resume: CausalIdentity

    def __post_init__(self) -> None:
        _identifier("return_id", self.return_id)
        if not isinstance(self.binding, NativeChildBinding):
            raise DeferredReturnError("binding must be a NativeChildBinding")
        if not self.binding.has_result:
            raise DeferredReturnError("binding must contain a bound child result")
        if not isinstance(self.resume, CausalIdentity):
            raise DeferredReturnError("resume must be a CausalIdentity")

        parent = self.binding.parent
        child = self.binding.child
        if self.resume.parent_causal_id != child.causal_id:
            raise DeferredReturnError(
                "resume.parent_causal_id must equal child.causal_id"
            )
        if self.resume.generation <= child.generation:
            raise DeferredReturnError(
                "resume generation must be greater than child generation"
            )
        if self.resume.session_id != parent.session_id:
            raise DeferredReturnError(
                "resume session_id must equal original parent session_id"
            )
        if self.resume.agent_id != parent.agent_id:
            raise DeferredReturnError(
                "resume agent_id must equal original parent agent_id"
            )
        if self.resume.task_id != parent.task_id:
            raise DeferredReturnError(
                "resume task_id must equal original parent task_id"
            )
        if self.resume.causal_id in {parent.causal_id, child.causal_id}:
            raise DeferredReturnError(
                "resume causal_id must be a fresh causal step"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DeferredReturnEnvelope":
        if not isinstance(value, Mapping):
            raise DeferredReturnError("deferred return input must be a mapping")
        keys = set(value.keys())
        unexpected = keys - _ALLOWED_FIELDS
        missing = set(_REQUIRED_FIELDS) - keys
        if unexpected:
            raise DeferredReturnError(
                "unexpected deferred-return field(s): "
                + ", ".join(sorted(map(str, unexpected)))
            )
        if missing:
            raise DeferredReturnError(
                "missing deferred-return field(s): "
                + ", ".join(sorted(missing))
            )
        try:
            binding = NativeChildBinding.from_mapping(value["binding"])
            resume = CausalIdentity.from_mapping(value["resume"])
        except (TypeError, ValueError, NativeChildBindingError) as exc:
            raise DeferredReturnError(f"invalid nested identity/binding: {exc}") from exc
        return cls(
            return_id=value["return_id"],
            binding=binding,
            resume=resume,
        )

    @property
    def result_id(self) -> str:
        assert self.binding.result_id is not None
        return self.binding.result_id

    @property
    def result_sha256(self) -> str:
        assert self.binding.result_sha256 is not None
        return self.binding.result_sha256

    def as_dict(self) -> dict[str, Any]:
        return {
            "return_id": self.return_id,
            "binding": self.binding.as_dict(),
            "resume": self.resume.as_dict(),
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
