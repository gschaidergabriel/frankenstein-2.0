"""Deterministic StateFingerprint candidate for F2-WP-201 generation 1.

REVIEW_ONLY candidate patch. This module fingerprints only an explicitly caller-supplied
projection. It has no persistence, Pulse/action-selection, world-fact, provider/tool,
effect, completion, or scheduler authority.

The important v1 distinction is explicit:

- ``content_sha256`` changes when the projection schema or canonical projection bytes change.
- ``identity_sha256`` also binds the caller-supplied generation.

Therefore generation-only movement is observable as identity change without being silently
reported as projection-content change. Equality of either digest is only equality under this
fingerprint profile; it is never proof of world-state truth or semantic equivalence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

PROFILE = "FRANKENSTEIN2_STATE_FINGERPRINT/v1"
CLASSIFICATION = "EXPLICIT_STATE_PROJECTION_FINGERPRINT_NOT_WORLD_TRUTH"
_MAX_SCHEMA_LEN = 512


class StateFingerprintError(ValueError):
    """Fail-closed validation error for the deterministic fingerprint profile."""


def _schema(value: Any) -> str:
    if not isinstance(value, str):
        raise StateFingerprintError("projection_schema must be a string")
    if not value or value != value.strip():
        raise StateFingerprintError("projection_schema must be non-empty and already trimmed")
    if len(value) > _MAX_SCHEMA_LEN:
        raise StateFingerprintError(f"projection_schema exceeds {_MAX_SCHEMA_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise StateFingerprintError("projection_schema contains control characters")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise StateFingerprintError("generation must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise StateFingerprintError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _validate_projection(value: Any, path: str = "$") -> None:
    """Accept only a deliberately small cross-run deterministic value domain.

    Floats, bytes, tuples, sets and custom objects are rejected rather than coerced because
    coercion could erase caller-significant type, ordering, or representation information.
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
    """Return deterministic UTF-8 bytes without semantic normalization."""
    _validate_projection(projection)
    return json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(parts: tuple[bytes, ...]) -> str:
    return hashlib.sha256(b"\x00".join(parts)).hexdigest()


@dataclass(frozen=True, slots=True)
class StateFingerprint:
    profile: str
    projection_schema: str
    generation: int
    content_sha256: str
    identity_sha256: str
    canonical_bytes: int
    classification: str = CLASSIFICATION

    def __post_init__(self) -> None:
        if self.profile != PROFILE:
            raise StateFingerprintError(f"unsupported profile: {self.profile!r}")
        object.__setattr__(self, "projection_schema", _schema(self.projection_schema))
        object.__setattr__(self, "generation", _generation(self.generation))
        object.__setattr__(self, "content_sha256", _sha256("content_sha256", self.content_sha256))
        object.__setattr__(self, "identity_sha256", _sha256("identity_sha256", self.identity_sha256))
        if type(self.canonical_bytes) is not int or self.canonical_bytes < 0:
            raise StateFingerprintError("canonical_bytes must be a non-negative integer")
        if self.classification != CLASSIFICATION:
            raise StateFingerprintError("classification mismatch")

    @property
    def sha256(self) -> str:
        """Compatibility alias for the generation-sensitive identity digest."""
        return self.identity_sha256

    @property
    def identity_tuple(self) -> tuple[str, str, int, str]:
        return self.profile, self.projection_schema, self.generation, self.identity_sha256

    @property
    def content_tuple(self) -> tuple[str, str, str]:
        return self.profile, self.projection_schema, self.content_sha256

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def fingerprint_state_projection(
    *,
    projection_schema: str,
    generation: int,
    projection: Any,
) -> StateFingerprint:
    """Fingerprint one explicit projection with separate content and identity digests."""
    projection_schema = _schema(projection_schema)
    generation = _generation(generation)
    payload = canonical_projection_bytes(projection)

    content_sha256 = _digest(
        (
            PROFILE.encode("utf-8"),
            projection_schema.encode("utf-8"),
            payload,
        )
    )
    identity_sha256 = _digest(
        (
            PROFILE.encode("utf-8"),
            projection_schema.encode("utf-8"),
            str(generation).encode("ascii"),
            content_sha256.encode("ascii"),
        )
    )
    return StateFingerprint(
        profile=PROFILE,
        projection_schema=projection_schema,
        generation=generation,
        content_sha256=content_sha256,
        identity_sha256=identity_sha256,
        canonical_bytes=len(payload),
    )


def _pair(previous: StateFingerprint, current: StateFingerprint) -> tuple[StateFingerprint, StateFingerprint]:
    if not isinstance(previous, StateFingerprint) or not isinstance(current, StateFingerprint):
        raise StateFingerprintError("comparison requires StateFingerprint values")
    return previous, current


def fingerprint_changed(previous: StateFingerprint, current: StateFingerprint) -> bool:
    """Return fingerprint identity change, including generation movement."""
    previous, current = _pair(previous, current)
    return previous.identity_tuple != current.identity_tuple


def projection_changed(previous: StateFingerprint, current: StateFingerprint) -> bool:
    """Return explicit projection/schema content change, excluding generation-only movement."""
    previous, current = _pair(previous, current)
    return previous.content_tuple != current.content_tuple
