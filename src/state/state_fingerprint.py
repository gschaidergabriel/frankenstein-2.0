from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


PROFILE = "FRANKENSTEIN2_STATE_FINGERPRINT/v1"


class StateFingerprintError(ValueError):
    """Raised when a supplied state projection is not deterministic under v1."""


def _validate_projection(value: Any, path: str = "$") -> None:
    """Accept only the deliberately small cross-run deterministic v1 value domain."""
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


def _projection_schema(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateFingerprintError("projection_schema must be a non-empty string")
    if value != value.strip():
        raise StateFingerprintError("projection_schema must already be trimmed")
    return value


def _generation(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StateFingerprintError("generation must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise StateFingerprintError(f"{name} must be lowercase 64-hex")
    return value


def canonical_projection_bytes(projection: Any) -> bytes:
    """Return deterministic UTF-8 bytes without normalizing caller-significant values."""
    _validate_projection(projection)
    return json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _hash_parts(*parts: bytes) -> str:
    return hashlib.sha256(b"\x00".join(parts)).hexdigest()


@dataclass(frozen=True, slots=True)
class StateFingerprint:
    """Deterministic projection fingerprint with separate content and lineage identity.

    ``content_sha256`` answers whether the explicit projection/schema content changed.
    ``identity_sha256`` additionally binds the caller-supplied generation. Equality of
    either digest is only equality at this projection contract; it is never world-truth
    equality and grants no Pulse, wake, persistence, effect, or completion authority.
    """

    profile: str
    projection_schema: str
    generation: int
    content_sha256: str
    identity_sha256: str
    canonical_bytes: int

    def __post_init__(self) -> None:
        if self.profile != PROFILE:
            raise StateFingerprintError(f"unsupported profile: {self.profile}")
        object.__setattr__(
            self,
            "projection_schema",
            _projection_schema(self.projection_schema),
        )
        object.__setattr__(self, "generation", _generation(self.generation))
        object.__setattr__(
            self,
            "content_sha256",
            _sha256("content_sha256", self.content_sha256),
        )
        object.__setattr__(
            self,
            "identity_sha256",
            _sha256("identity_sha256", self.identity_sha256),
        )
        if (
            not isinstance(self.canonical_bytes, int)
            or isinstance(self.canonical_bytes, bool)
            or self.canonical_bytes < 0
        ):
            raise StateFingerprintError("canonical_bytes must be a non-negative integer")

    @property
    def content_identity_tuple(self) -> tuple[str, str, str]:
        return self.profile, self.projection_schema, self.content_sha256

    @property
    def lineage_identity_tuple(self) -> tuple[str, str, int, str]:
        return (
            self.profile,
            self.projection_schema,
            self.generation,
            self.identity_sha256,
        )

    @property
    def sha256(self) -> str:
        """Compatibility view of the full lineage identity digest."""
        return self.identity_sha256

    @property
    def identity_tuple(self) -> tuple[str, str, int, str]:
        """Compatibility view of the full lineage identity tuple."""
        return self.lineage_identity_tuple


def fingerprint_state_projection(
    *,
    projection_schema: str,
    generation: int,
    projection: Any,
) -> StateFingerprint:
    """Fingerprint one explicit state projection without reading or inferring state."""
    projection_schema = _projection_schema(projection_schema)
    generation = _generation(generation)
    payload = canonical_projection_bytes(projection)

    content_sha256 = _hash_parts(
        PROFILE.encode("utf-8"),
        projection_schema.encode("utf-8"),
        payload,
    )
    identity_sha256 = _hash_parts(
        PROFILE.encode("utf-8"),
        projection_schema.encode("utf-8"),
        str(generation).encode("ascii"),
        content_sha256.encode("ascii"),
    )
    return StateFingerprint(
        profile=PROFILE,
        projection_schema=projection_schema,
        generation=generation,
        content_sha256=content_sha256,
        identity_sha256=identity_sha256,
        canonical_bytes=len(payload),
    )


def content_changed(previous: StateFingerprint, current: StateFingerprint) -> bool:
    """Return projection/schema content change only; generation-only drift is false."""
    return previous.content_identity_tuple != current.content_identity_tuple


def lineage_changed(previous: StateFingerprint, current: StateFingerprint) -> bool:
    """Return full fingerprint identity change, including generation-only drift."""
    return previous.lineage_identity_tuple != current.lineage_identity_tuple


def fingerprint_changed(previous: StateFingerprint, current: StateFingerprint) -> bool:
    """Compatibility alias for full lineage change; Pulse must choose a change class."""
    return lineage_changed(previous, current)


__all__ = [
    "PROFILE",
    "StateFingerprint",
    "StateFingerprintError",
    "canonical_projection_bytes",
    "content_changed",
    "fingerprint_changed",
    "fingerprint_state_projection",
    "lineage_changed",
]
