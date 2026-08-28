"""Fail-closed workpackage -> tool-use -> native-child -> result identity binding.

F2-WP-102 is deliberately an identity/provenance component. It does not spawn a
child, deliver messages, decide execution success, write UnifiedDB, or perform an
effect. Those semantics belong to later workpackages. This module only makes it
hard to attach a returned result to the wrong delegation or causal child.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import re
from typing import Any, Mapping

from .causal_identity import CausalIdentity

_REQUIRED_FIELDS = (
    "workpackage_id",
    "parent",
    "tool_use_id",
    "delegation_id",
    "child",
)
_OPTIONAL_FIELDS = ("result_id", "result_sha256")
_ALLOWED_FIELDS = frozenset((*_REQUIRED_FIELDS, *_OPTIONAL_FIELDS))
_MAX_IDENTIFIER_LENGTH = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class NativeChildBindingError(ValueError):
    """Raised when native-child provenance is incomplete or contradictory."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise NativeChildBindingError(f"{name} must be a string")
    if not value or value != value.strip():
        raise NativeChildBindingError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise NativeChildBindingError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise NativeChildBindingError(f"{name} contains control characters")
    return value


def _digest(value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise NativeChildBindingError("result_sha256 must be lowercase 64-hex SHA-256")
    return value


@dataclass(frozen=True, slots=True)
class NativeChildBinding:
    """Immutable identity binding for one explicitly delegated child.

    ``parent`` is the Agent/tool caller's causal identity. ``child`` must be an
    explicit causal descendant in the same session and at a strictly later
    generation. A result is absent or fully bound as the pair
    ``result_id`` + ``result_sha256``; partial result identity fails closed.
    """

    workpackage_id: str
    parent: CausalIdentity
    tool_use_id: str
    delegation_id: str
    child: CausalIdentity
    result_id: str | None = None
    result_sha256: str | None = None

    def __post_init__(self) -> None:
        _identifier("workpackage_id", self.workpackage_id)
        _identifier("tool_use_id", self.tool_use_id)
        _identifier("delegation_id", self.delegation_id)
        if not isinstance(self.parent, CausalIdentity):
            raise NativeChildBindingError("parent must be a CausalIdentity")
        if not isinstance(self.child, CausalIdentity):
            raise NativeChildBindingError("child must be a CausalIdentity")
        if self.child.parent_causal_id != self.parent.causal_id:
            raise NativeChildBindingError(
                "child.parent_causal_id must equal parent.causal_id"
            )
        if self.child.generation <= self.parent.generation:
            raise NativeChildBindingError(
                "child generation must be greater than parent generation"
            )
        if self.child.session_id != self.parent.session_id:
            raise NativeChildBindingError(
                "child session_id must equal parent session_id in F2-WP-102"
            )
        if (self.result_id is None) != (self.result_sha256 is None):
            raise NativeChildBindingError(
                "result_id and result_sha256 must either both be absent or both be present"
            )
        if self.result_id is not None:
            _identifier("result_id", self.result_id)
            _digest(self.result_sha256)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "NativeChildBinding":
        if not isinstance(value, Mapping):
            raise NativeChildBindingError("binding input must be a mapping")
        keys = set(value.keys())
        unexpected = keys - _ALLOWED_FIELDS
        missing = set(_REQUIRED_FIELDS) - keys
        if unexpected:
            raise NativeChildBindingError(
                "unexpected binding field(s): " + ", ".join(sorted(map(str, unexpected)))
            )
        if missing:
            raise NativeChildBindingError(
                "missing binding field(s): " + ", ".join(sorted(missing))
            )
        try:
            parent = CausalIdentity.from_mapping(value["parent"])
            child = CausalIdentity.from_mapping(value["child"])
        except (TypeError, ValueError) as exc:
            raise NativeChildBindingError(f"invalid causal identity: {exc}") from exc
        return cls(
            workpackage_id=value["workpackage_id"],
            parent=parent,
            tool_use_id=value["tool_use_id"],
            delegation_id=value["delegation_id"],
            child=child,
            result_id=value.get("result_id"),
            result_sha256=value.get("result_sha256"),
        )

    @property
    def has_result(self) -> bool:
        return self.result_id is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "workpackage_id": self.workpackage_id,
            "parent": self.parent.as_dict(),
            "tool_use_id": self.tool_use_id,
            "delegation_id": self.delegation_id,
            "child": self.child.as_dict(),
            "result_id": self.result_id,
            "result_sha256": self.result_sha256,
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

    def bind_result(
        self,
        *,
        delegation_id: str,
        child_causal_id: str,
        result_id: str,
        result_sha256: str,
    ) -> "NativeChildBinding":
        """Bind an immutable returned-result identity to the expected child.

        The caller must repeat the delegation and child causal identities. This
        prevents a generic result object from being attached by positional or
        temporal coincidence. Replaying the exact same binding is idempotent;
        rebinding an already-bound result to different bytes or identity fails.
        """
        _identifier("delegation_id", delegation_id)
        _identifier("child_causal_id", child_causal_id)
        _identifier("result_id", result_id)
        _digest(result_sha256)
        if delegation_id != self.delegation_id:
            raise NativeChildBindingError("result delegation_id does not match binding")
        if child_causal_id != self.child.causal_id:
            raise NativeChildBindingError("result child_causal_id does not match binding")
        if self.has_result:
            if self.result_id == result_id and self.result_sha256 == result_sha256:
                return self
            raise NativeChildBindingError("result is already bound and cannot be replaced")
        return replace(self, result_id=result_id, result_sha256=result_sha256)
