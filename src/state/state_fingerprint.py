from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


PROFILE = "FRANKENSTEIN2_STATE_FINGERPRINT/v1"


class StateFingerprintError(ValueError):
    """Raised when a supplied state projection is not deterministic under v1."""


def _validate_projection(value: Any, path: str = "$") -> None:
    """Accept only the deliberately small cross-run deterministic v1 value domain.

    Floats are rejected rather than silently inheriting implementation-specific numeric
    canonicalization. Tuples/sets/bytes/custom objects are rejected rather than coerced,
    because coercion could erase caller-significant type or ordering information.
    """

    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_projection(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise StateFingerprintError(f"{path}: mapping keys must be strings")
            _validate_projection(item, f"{path}.{key}")
        return
    raise StateFingerprintError(
        f"{path}: unsupported projection type {type(value).__name__}; "
        "v1 accepts null/bool/int/string/list/string-keyed-dict only"
    )


def canonical_projection_bytes(projection: Any) -> bytes:
    """Return deterministic UTF-8 bytes for the accepted v1 projection domain.

    This is an F2-local profile, not a claim of RFC 8785/JCS compliance.
    """

    _validate_projection(projection)
    return json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class StateFingerprint:
    profile: str
    projection_schema: str
    generation: int
    sha256: str
    canonical_bytes: int

    def __post_init__(self) -> None:
        if self.profile != PROFILE:
            raise StateFingerprintError(f"unsupported profile: {self.profile}")
        if not isinstance(self.projection_schema, str) or not self.projection_schema.strip():
            raise StateFingerprintError("projection_schema must be a non-empty string")
        if not isinstance(self.generation, int) or isinstance(self.generation, bool) or self.generation < 0:
            raise StateFingerprintError("generation must be a non-negative integer")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise StateFingerprintError("sha256 must be lowercase 64-hex")
        if not isinstance(self.canonical_bytes, int) or isinstance(self.canonical_bytes, bool) or self.canonical_bytes < 0:
            raise StateFingerprintError("canonical_bytes must be a non-negative integer")

    @property
    def identity_tuple(self) -> tuple[str, str, int, str]:
        return self.profile, self.projection_schema, self.generation, self.sha256


def fingerprint_state_projection(
    *,
    projection_schema: str,
    generation: int,
    projection: Any,
) -> StateFingerprint:
    """Fingerprint one explicit state projection without reading or inferring state.

    The caller owns projection semantics. This function does not drop timestamps, infer
    salience, read UnifiedDB, or decide whether a change matters to Pulse/agency policy.
    """

    if not isinstance(projection_schema, str) or not projection_schema.strip():
        raise StateFingerprintError("projection_schema must be a non-empty string")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
        raise StateFingerprintError("generation must be a non-negative integer")

    payload = canonical_projection_bytes(projection)
    envelope = b"\x00".join(
        (
            PROFILE.encode("utf-8"),
            projection_schema.encode("utf-8"),
            str(generation).encode("ascii"),
            payload,
        )
    )
    return StateFingerprint(
        profile=PROFILE,
        projection_schema=projection_schema,
        generation=generation,
        sha256=hashlib.sha256(envelope).hexdigest(),
        canonical_bytes=len(payload),
    )


def fingerprint_changed(previous: StateFingerprint, current: StateFingerprint) -> bool:
    """Return exact fingerprint-identity change, not semantic/world-state inequality."""

    return previous.identity_tuple != current.identity_tuple
