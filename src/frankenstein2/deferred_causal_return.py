"""Deferred causal return envelope for Frankenstein 2.0.

F2-WP-104 carries an already bound child result back into an explicit causal
re-entry step for the semantic parent agent/task. It is not a delivery/ACK
protocol, execution-outcome classifier, scheduler, persistence layer, or child
runtime. Those remain separate workpackages and authorities.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from .causal_identity import CausalIdentity
from .native_child_binding import NativeChildBinding

_REQUIRED_FIELDS = ("return_id", "binding", "resume")
_ALLOWED_FIELDS = frozenset(_REQUIRED_FIELDS)
_MAX_IDENTIFIER_LENGTH = 512


class DeferredCausalReturnError(ValueError):
    """Raised when a deferred return has ambiguous or contradictory lineage."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise DeferredCausalReturnError(f"{name} must be a string")
    if not value or value != value.strip():
        raise DeferredCausalReturnError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise DeferredCausalReturnError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise DeferredCausalReturnError(f"{name} contains control characters")
    return value


@dataclass(frozen=True, slots=True)
class DeferredCausalReturn:
    """Immutable child-result -> parent-reentry causal envelope.

    The return is intentionally independent of transport. ``binding`` must
    already contain an immutable result identity/digest. ``resume`` is a new
    causal step owned by the semantic parent agent/task and explicitly caused
    by the child step through ``parent_causal_id``.
    """

    return_id: str
    binding: NativeChildBinding
    resume: CausalIdentity

    def __post_init__(self) -> None:
        _identifier("return_id", self.return_id)
        if not isinstance(self.binding, NativeChildBinding):
            raise DeferredCausalReturnError("binding must be a NativeChildBinding")
        if not isinstance(self.resume, CausalIdentity):
            raise DeferredCausalReturnError("resume must be a CausalIdentity")
        if not self.binding.has_result:
            raise DeferredCausalReturnError(
                "deferred return requires an already result-bound NativeChildBinding"
            )
        parent = self.binding.parent
        child = self.binding.child
        if self.resume.parent_causal_id != child.causal_id:
            raise DeferredCausalReturnError(
                "resume.parent_causal_id must equal child.causal_id"
            )
        if self.resume.generation <= child.generation:
            raise DeferredCausalReturnError(
                "resume generation must be greater than child generation"
            )
        if self.resume.session_id != parent.session_id:
            raise DeferredCausalReturnError(
                "resume session_id must equal semantic parent session_id"
            )
        if self.resume.agent_id != parent.agent_id:
            raise DeferredCausalReturnError(
                "resume agent_id must equal semantic parent agent_id"
            )
        if self.resume.task_id != parent.task_id:
            raise DeferredCausalReturnError(
                "resume task_id must equal semantic parent task_id"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DeferredCausalReturn":
        if not isinstance(value, Mapping):
            raise DeferredCausalReturnError("deferred return input must be a mapping")
        keys = set(value.keys())
        unexpected = keys - _ALLOWED_FIELDS
        missing = set(_REQUIRED_FIELDS) - keys
        if unexpected:
            raise DeferredCausalReturnError(
                "unexpected deferred-return field(s): "
                + ", ".join(sorted(map(str, unexpected)))
            )
        if missing:
            raise DeferredCausalReturnError(
                "missing deferred-return field(s): " + ", ".join(sorted(missing))
            )
        try:
            binding = NativeChildBinding.from_mapping(value["binding"])
            resume = CausalIdentity.from_mapping(value["resume"])
        except (TypeError, ValueError) as exc:
            raise DeferredCausalReturnError(f"invalid nested identity: {exc}") from exc
        return cls(return_id=value["return_id"], binding=binding, resume=resume)

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
