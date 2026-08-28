"""Bind causal identity to UnifiedDB authority and telemetry lineage.

This adapter is deliberately non-mutating. It does not open SQLite, write telemetry,
execute effects, or grant runtime authority. It verifies that separately produced
identity envelopes agree before a later writer/integrator is allowed to persist them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from frankenstein2.causal_identity import CausalIdentity, CausalIdentityError


class CausalAuthorityBindingError(ValueError):
    """Raised when cross-plane causal lineage cannot be bound exactly."""


@dataclass(frozen=True, slots=True)
class UnifiedDBAuthorityRef:
    """Reference to an accepted UnifiedDB identity component receipt."""

    receipt_ref: str
    canonical_source: str
    fingerprint_schema: str

    def __post_init__(self) -> None:
        for name, value in (
            ("receipt_ref", self.receipt_ref),
            ("canonical_source", self.canonical_source),
            ("fingerprint_schema", self.fingerprint_schema),
        ):
            if not isinstance(value, str) or not value.strip():
                raise CausalAuthorityBindingError(f"{name} must be a non-empty string")
        if self.fingerprint_schema != "FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2":
            raise CausalAuthorityBindingError("unsupported UnifiedDB fingerprint schema")


@dataclass(frozen=True, slots=True)
class CausalTelemetryBinding:
    """Non-mutating cross-plane binding for one telemetry event."""

    identity: CausalIdentity
    telemetry_event_id: str
    telemetry_run_id: str
    unifieddb: UnifiedDBAuthorityRef

    def as_dict(self) -> dict[str, Any]:
        return {
            "telemetry_event_id": self.telemetry_event_id,
            "telemetry_run_id": self.telemetry_run_id,
            "causal_identity": self.identity.as_dict(),
            "unifieddb": {
                "receipt_ref": self.unifieddb.receipt_ref,
                "canonical_source": self.unifieddb.canonical_source,
                "fingerprint_schema": self.unifieddb.fingerprint_schema,
            },
        }


def bind_causal_authority(
    identity: CausalIdentity,
    *,
    unifieddb: UnifiedDBAuthorityRef,
    telemetry: Mapping[str, Any],
) -> CausalTelemetryBinding:
    """Validate one exact causal identity against telemetry and UnifiedDB authority.

    Telemetry must already expose the core causal fields. Missing, null, or mismatched
    fields are rejected rather than inferred from session/process time. An optional
    ``parent_causal_id`` may be carried by a richer telemetry adapter; when present it
    must match the identity exactly.
    """
    if not isinstance(identity, CausalIdentity):
        raise CausalAuthorityBindingError("identity must be a CausalIdentity")
    if not isinstance(unifieddb, UnifiedDBAuthorityRef):
        raise CausalAuthorityBindingError("unifieddb must be a UnifiedDBAuthorityRef")
    if not isinstance(telemetry, Mapping):
        raise CausalAuthorityBindingError("telemetry must be a mapping")

    event_id = telemetry.get("event_id")
    run_id = telemetry.get("run_id")
    if not isinstance(event_id, str) or not event_id.strip():
        raise CausalAuthorityBindingError("telemetry.event_id is required")
    if not isinstance(run_id, str) or not run_id.strip():
        raise CausalAuthorityBindingError("telemetry.run_id is required")

    for field in ("session_id", "agent_id", "task_id", "turn_id", "causal_id", "generation"):
        value = telemetry.get(field)
        expected = getattr(identity, field)
        if value != expected:
            raise CausalAuthorityBindingError(
                f"telemetry/{field} mismatch: expected {expected!r}, got {value!r}"
            )

    if "parent_causal_id" in telemetry and telemetry["parent_causal_id"] != identity.parent_causal_id:
        raise CausalAuthorityBindingError("telemetry/parent_causal_id mismatch")

    try:
        identity_copy = CausalIdentity.from_mapping(identity.as_dict())
    except CausalIdentityError as exc:  # defensive guard for future dataclass changes
        raise CausalAuthorityBindingError("identity round-trip failed") from exc

    return CausalTelemetryBinding(
        identity=identity_copy,
        telemetry_event_id=event_id,
        telemetry_run_id=run_id,
        unifieddb=unifieddb,
    )
