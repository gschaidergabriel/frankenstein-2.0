"""Typed causal identity spine for Frankenstein 2.0.

This module defines identifiers only. It does not resolve durable-state paths,
write UnifiedDB, execute effects, or infer identity from time/process context.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Any, Mapping

_REQUIRED_FIELDS = (
    "session_id",
    "agent_id",
    "task_id",
    "turn_id",
    "causal_id",
    "generation",
)
_OPTIONAL_FIELDS = ("parent_causal_id",)
_ALLOWED_FIELDS = frozenset((*_REQUIRED_FIELDS, *_OPTIONAL_FIELDS))
_MAX_IDENTIFIER_LENGTH = 512


class CausalIdentityError(ValueError):
    """Raised when a causal identity violates the F2 identity contract."""


def _validate_identifier(name: str, value: Any, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise CausalIdentityError(f"{name} must be a string")
    if not value or value != value.strip():
        raise CausalIdentityError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise CausalIdentityError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CausalIdentityError(f"{name} contains control characters")
    return value


def _validate_generation(value: Any) -> int:
    # bool is a subclass of int in Python; accepting it would silently turn
    # True/False into generations 1/0.
    if type(value) is not int:
        raise CausalIdentityError("generation must be an integer, not bool/coerced input")
    if value < 0:
        raise CausalIdentityError("generation must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class CausalIdentity:
    """Stable identity envelope for one F2 causal step.

    ``causal_id`` identifies this causal step. ``parent_causal_id`` records
    lineage explicitly when a derived step is created. No method in this
    class invents an identifier or generation from wall-clock/process state.
    """

    session_id: str
    agent_id: str
    task_id: str
    turn_id: str
    causal_id: str
    generation: int
    parent_causal_id: str | None = None

    def __post_init__(self) -> None:
        for name in _REQUIRED_FIELDS[:-1]:
            _validate_identifier(name, getattr(self, name))
        _validate_generation(self.generation)
        _validate_identifier("parent_causal_id", self.parent_causal_id, optional=True)
        if self.parent_causal_id == self.causal_id:
            raise CausalIdentityError("parent_causal_id must not equal causal_id")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CausalIdentity":
        if not isinstance(value, Mapping):
            raise CausalIdentityError("identity input must be a mapping")
        keys = set(value.keys())
        unexpected = keys - _ALLOWED_FIELDS
        missing = set(_REQUIRED_FIELDS) - keys
        if unexpected:
            raise CausalIdentityError(
                "unexpected identity field(s): " + ", ".join(sorted(map(str, unexpected)))
            )
        if missing:
            raise CausalIdentityError(
                "missing identity field(s): " + ", ".join(sorted(missing))
            )
        return cls(
            session_id=value["session_id"],
            agent_id=value["agent_id"],
            task_id=value["task_id"],
            turn_id=value["turn_id"],
            causal_id=value["causal_id"],
            generation=value["generation"],
            parent_causal_id=value.get("parent_causal_id"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "turn_id": self.turn_id,
            "causal_id": self.causal_id,
            "generation": self.generation,
            "parent_causal_id": self.parent_causal_id,
        }

    def canonical_json(self) -> str:
        """Return deterministic UTF-8 JSON independent of mapping insertion order."""
        return json.dumps(
            self.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def derive(
        self,
        *,
        causal_id: str,
        generation: int | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
        turn_id: str | None = None,
    ) -> "CausalIdentity":
        """Create an explicit child/derived identity.

        The caller must supply the new causal id. The current ``causal_id`` is
        copied into ``parent_causal_id``; no root/parent lineage is inferred.
        """
        return replace(
            self,
            session_id=self.session_id if session_id is None else session_id,
            agent_id=self.agent_id if agent_id is None else agent_id,
            task_id=self.task_id if task_id is None else task_id,
            turn_id=self.turn_id if turn_id is None else turn_id,
            causal_id=causal_id,
            generation=self.generation if generation is None else generation,
            parent_causal_id=self.causal_id,
        )
