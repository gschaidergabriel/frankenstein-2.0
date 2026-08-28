"""Immutable semantic effect-request identity for Frankenstein 2.0 WP105.

The Stage-1 effect path already binds causal/call identity.  This module binds the
semantic request that the canonical EntityOS EffectGate actually evaluates so an
ALLOW for request B cannot be replayed against call A merely because the call ids
match.

This is not policy and is not an EffectGate.  It mirrors only the currently admitted
``EffectRequest`` input shape and produces a deterministic digest that can be echoed by
canonical authority evidence and checked again at the executor boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


class EffectRequestIdentityError(ValueError):
    """Raised when semantic effect-request identity is malformed."""


def _token(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EffectRequestIdentityError(f"INVALID_{name.upper()}")
    if len(value) > 4096 or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise EffectRequestIdentityError(f"INVALID_{name.upper()}")
    return value


def _argv(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = tuple(value)
    if not isinstance(value, tuple):
        raise EffectRequestIdentityError("INVALID_ARGV")
    return tuple(_token("argv_item", item) for item in value)


@dataclass(frozen=True, slots=True)
class EffectRequestIdentity:
    """Immutable typed projection of EntityOS ``EffectRequest`` policy inputs."""

    user_id: str
    session_id: str
    capability: str
    target: str
    argv: tuple[str, ...] | None = None
    expected_generation: int | None = None

    def __post_init__(self) -> None:
        for name in ("user_id", "session_id", "capability", "target"):
            _token(name, getattr(self, name))
        object.__setattr__(self, "argv", _argv(self.argv))
        if self.expected_generation is not None:
            if type(self.expected_generation) is not int or self.expected_generation < 0:
                raise EffectRequestIdentityError("INVALID_EXPECTED_GENERATION")

    def canonical_payload(self) -> dict[str, object]:
        """Return the exact deterministic payload used for semantic identity."""
        return {
            "argv": list(self.argv) if self.argv is not None else None,
            "capability": self.capability,
            "expected_generation": self.expected_generation,
            "session_id": self.session_id,
            "target": self.target,
            "user_id": self.user_id,
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


__all__ = ["EffectRequestIdentity", "EffectRequestIdentityError"]
