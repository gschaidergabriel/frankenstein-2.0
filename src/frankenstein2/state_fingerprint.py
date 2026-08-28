"""Deterministic StateFingerprint primitive for Frankenstein 2.0.

F2-WP-201 generation 1 reentry.

The primitive fingerprints only an explicitly supplied typed projection. It separates
projection-content change from generation/identity change so consumers cannot mistake a
new generation for changed projection bytes. It reads no database, infers no world fact,
and makes no Persistent Pulse, wake, model, tool, effect, or completion decision.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any

PROFILE = "FRANKENSTEIN2_STATE_FINGERPRINT/v2"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_SCHEMA_LEN = 512


class StateFingerprintError(ValueError):
    """Fail-closed fingerprint-contract error."""


def _projection_schema(value: Any) -> str:
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
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise StateFingerprintError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _validate_projection(value: Any, path: str = "$") -> None:
    """Validate the deliberately small deterministic v2 projection domain.

    Floats, tuples, sets, bytes and custom objects fail closed instead of being coerced,
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
        "v2 accepts null/bool/int/string/list/string-keyed-dict only"
    )


def canonical_projection_bytes(projection: Any) -> bytes:
    """Return deterministic UTF-8 bytes without dropping caller-supplied fields."""

    _validate_projection(projection)
    return json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest_parts(*parts: bytes) -> str:
    return hashlib.sha256(b"\x00".join(parts)).hexdigest()


@dataclass(frozen=True, slots=True)
class StateFingerprint:
    profile: str
    projection_schema: str
    generation: int
    projection_sha256: str
    identity_sha256: str
    canonical_bytes: int
    classification: str = "EXPLICIT_TYPED_PROJECTION_FINGERPRINT_NOT_WORLD_TRUTH"

    def __post_init__(self) -> None:
        if self.profile != PROFILE:
            raise StateFingerprintError(f"unsupported profile: {self.profile}")
        object.__setattr__(self, "projection_schema", _projection_schema(self.projection_schema))
        object.__setattr__(self, "generation", _generation(self.generation))
        object.__setattr__(self, "projection_sha256", _sha256("projection_sha256", self.projection_sha256))
        object.__setattr__(self, "identity_sha256", _sha256("identity_sha256", self.identity_sha256))
        if type(self.canonical_bytes) is not int or self.canonical_bytes < 0:
            raise StateFingerprintError("canonical_bytes must be a non-negative integer")

    @property
    def projection_identity(self) -> tuple[str, str]:
        """Identity of typed projection content, intentionally excluding generation."""

        return self.projection_schema, self.projection_sha256

    @property
    def state_identity(self) -> tuple[str, str, int, str]:
        """Exact state-generation identity, intentionally including generation."""

        return self.profile, self.projection_schema, self.generation, self.identity_sha256

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def fingerprint_state_projection(
    *,
    projection_schema: str,
    generation: int,
    projection: Any,
) -> StateFingerprint:
    """Fingerprint one explicit typed state projection without reading or inferring state."""

    schema = _projection_schema(projection_schema)
    gen = _generation(generation)
    payload = canonical_projection_bytes(projection)

    projection_sha = _digest_parts(
        PROFILE.encode("utf-8"),
        b"projection",
        schema.encode("utf-8"),
        payload,
    )
    identity_sha = _digest_parts(
        PROFILE.encode("utf-8"),
        b"identity",
        schema.encode("utf-8"),
        str(gen).encode("ascii"),
        projection_sha.encode("ascii"),
    )
    return StateFingerprint(
        profile=PROFILE,
        projection_schema=schema,
        generation=gen,
        projection_sha256=projection_sha,
        identity_sha256=identity_sha,
        canonical_bytes=len(payload),
    )


def projection_changed(previous: StateFingerprint, current: StateFingerprint) -> bool:
    """Return typed projection-content change, not generation/identity movement."""

    if not isinstance(previous, StateFingerprint) or not isinstance(current, StateFingerprint):
        raise StateFingerprintError("projection_changed requires StateFingerprint values")
    return previous.projection_identity != current.projection_identity


def identity_changed(previous: StateFingerprint, current: StateFingerprint) -> bool:
    """Return exact fingerprint identity change, including generation movement."""

    if not isinstance(previous, StateFingerprint) or not isinstance(current, StateFingerprint):
        raise StateFingerprintError("identity_changed requires StateFingerprint values")
    return previous.state_identity != current.state_identity


__all__ = [
    "PROFILE",
    "StateFingerprint",
    "StateFingerprintError",
    "canonical_projection_bytes",
    "fingerprint_state_projection",
    "identity_changed",
    "projection_changed",
]
