"""Target-host Ubuntu userspace twin planning for Frankenstein 2.0.

F2-WP-1202 generation 1.

This module consumes the canonical F2-WP-1201 TargetHostProfile/v1 boundary and derives
a deterministic T1 userspace projection. It never accepts a second caller-defined profile
shape under the canonical schema name, never trusts a detached profile digest, and never
invents target facts that WP1201 did not observe.

    SIMULATION_PASS != PHYSICAL_PASS
    REPOSITORY_PASS != TARGET_PASS

No device emulation, physical-host probing, effect execution, installer execution, or
completion authority lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from .target_host_profile import (
    OBSERVED as PROFILE_OBSERVED,
    TARGET_HOST_PROFILE_SCHEMA,
    UNKNOWN as PROFILE_UNKNOWN,
    TargetHostProfile,
    TargetHostProfileError,
)

PROFILE_SCHEMA = TARGET_HOST_PROFILE_SCHEMA
PROJECTION_SCHEMA = "FRANKENSTEIN2_TARGET_HOST_PROFILE_T1_PROJECTION/v1"
PLAN_SCHEMA = "FRANKENSTEIN2_T1_USERSPACE_TWIN_PLAN/v1"
FIDELITY = "T1_UBUNTU_USERSPACE"
UNKNOWN = "UNKNOWN"
ONE_HANDOFF_ENTRY = "AI_START_HERE_DO_NOT_SCAN_REPO"
_UNAVAILABLE = "NOT_COLLECTED_BY_CANONICAL_WP1201_G1"

_T1_FACT_BINDINGS: tuple[tuple[str, str | None], ...] = (
    ("os_release", "os_release"),
    ("kernel_release", "kernel_release"),
    ("architecture", "architecture"),
    ("uid", "collector_uid"),
    ("session_type", "session_type"),
    ("xdg_runtime_dir", None),
    ("session_dbus", None),
    ("systemd_user", "systemd_user_state"),
    ("pipewire_version", "pipewire_version"),
    ("wireplumber_version", "wireplumber_version"),
    ("portal_backend", None),
    ("browser_package_form", None),
)


class TargetUserspaceTwinError(ValueError):
    """Fail-closed profile/plan validation error."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _string(name: str, value: Any) -> str:
    if type(value) is not str:
        raise TargetUserspaceTwinError(f"{name} must be a string")
    if value != value.strip() or not value:
        raise TargetUserspaceTwinError(f"{name} must be non-empty and already trimmed")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TargetUserspaceTwinError(f"{name} contains control characters")
    return value


def _projection_scalar(name: str, value: Any) -> str:
    if type(value) is str:
        return _string(name, value)
    if type(value) is int:
        return str(value)
    if type(value) is bool:
        return "true" if value else "false"
    raise TargetUserspaceTwinError(
        f"{name} canonical observed value is not a supported T1 scalar"
    )


def _canonical_profile(raw: Mapping[str, Any] | TargetHostProfile) -> TargetHostProfile:
    """Reconstruct the exact canonical WP1201 profile before consuming any fact."""

    if type(raw) is TargetHostProfile:
        raw_dict = raw.as_dict()
    elif type(raw) is dict:
        raw_dict = raw
    else:
        raise TargetUserspaceTwinError(
            "target profile must be exact TargetHostProfile or canonical dict"
        )

    expected_top_level = {
        "schema",
        "collector_version",
        "generation",
        "facts",
        "profile_digest_sha256",
        "observed_field_count",
        "unknown_field_count",
        "unknown_fields",
        "epistemic_scope",
    }
    if set(raw_dict) != expected_top_level:
        raise TargetUserspaceTwinError(
            "target profile must use the exact canonical WP1201 wire shape"
        )
    if type(raw_dict.get("facts")) is not dict:
        raise TargetUserspaceTwinError("target profile facts must be an exact dict")
    if any(type(record) is not dict for record in raw_dict["facts"].values()):
        raise TargetUserspaceTwinError("target profile fact records must be exact dicts")

    try:
        rebuilt = TargetHostProfile(
            schema=raw_dict["schema"],
            collector_version=raw_dict["collector_version"],
            generation=raw_dict["generation"],
            facts={
                key: dict(raw_dict["facts"][key])
                for key in sorted(raw_dict["facts"])
            },
            profile_digest_sha256=raw_dict["profile_digest_sha256"],
        )
    except (KeyError, TypeError, ValueError, TargetHostProfileError) as exc:
        raise TargetUserspaceTwinError(
            f"invalid canonical WP1201 target profile: {exc}"
        ) from exc

    if rebuilt.as_dict() != raw_dict:
        raise TargetUserspaceTwinError(
            "target profile derived metadata does not match canonical WP1201 reconstruction"
        )
    return rebuilt


def _fact_to_projection_value(
    profile: TargetHostProfile, *, output_field: str, source_fact: str | None
) -> str:
    if source_fact is None:
        return UNKNOWN
    record = profile.facts[source_fact]
    if record["status"] == PROFILE_UNKNOWN:
        return UNKNOWN
    if record["status"] != PROFILE_OBSERVED:
        raise TargetUserspaceTwinError(
            f"{source_fact} has noncanonical epistemic status"
        )
    return _projection_scalar(output_field, record["value"])


@dataclass(frozen=True, slots=True)
class TargetProfileProjection:
    """Reduced T1 view derived only from one validated canonical WP1201 profile."""

    schema: str
    profile_generation: int
    profile_sha256: str
    fields: tuple[tuple[str, str], ...]
    source_fact_bindings: tuple[tuple[str, str], ...]

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any] | TargetHostProfile
    ) -> "TargetProfileProjection":
        profile = _canonical_profile(raw)
        normalized = tuple(
            (
                output_field,
                _fact_to_projection_value(
                    profile,
                    output_field=output_field,
                    source_fact=source_fact,
                ),
            )
            for output_field, source_fact in _T1_FACT_BINDINGS
        )
        bindings = tuple(
            (output_field, source_fact if source_fact is not None else _UNAVAILABLE)
            for output_field, source_fact in _T1_FACT_BINDINGS
        )
        return cls(
            schema=PROJECTION_SCHEMA,
            profile_generation=profile.generation,
            profile_sha256=profile.profile_digest_sha256,
            fields=normalized,
            source_fact_bindings=bindings,
        )

    def field_map(self) -> dict[str, str]:
        return dict(self.fields)


@dataclass(frozen=True, slots=True)
class FidelityGap:
    field: str
    observed_value: str
    required_for: str
    status: str = UNKNOWN

    def as_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "observed_value": self.observed_value,
            "required_for": self.required_for,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class TwinBootstrapPlan:
    schema: str
    fidelity: str
    projection_schema: str
    source_profile_generation: int
    source_profile_sha256: str
    observed_shape: tuple[tuple[str, str], ...]
    source_fact_bindings: tuple[tuple[str, str], ...]
    fidelity_gaps: tuple[FidelityGap, ...]
    required_runtime_checks: tuple[str, ...]
    one_handoff_installer_entry: str
    classification: str = "T1_PREHANDOFF_PLAN_NO_PHYSICAL_OR_COMPLETION_CREDIT"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "fidelity": self.fidelity,
            "projection_schema": self.projection_schema,
            "source_profile_generation": self.source_profile_generation,
            "source_profile_sha256": self.source_profile_sha256,
            "observed_shape": dict(self.observed_shape),
            "source_fact_bindings": dict(self.source_fact_bindings),
            "fidelity_gaps": [gap.as_dict() for gap in self.fidelity_gaps],
            "required_runtime_checks": list(self.required_runtime_checks),
            "one_handoff_installer_entry": self.one_handoff_installer_entry,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _sha256(self.as_dict())


_GAP_PURPOSE = {
    "os_release": "distro userspace selection",
    "kernel_release": "kernel-fidelity declaration",
    "architecture": "runtime architecture match",
    "uid": "target-like non-root user identity",
    "session_type": "Wayland/X11/session topology",
    "xdg_runtime_dir": "XDG runtime ownership and lifetime",
    "session_dbus": "session D-Bus reachability",
    "systemd_user": "systemd user-manager reachability",
    "pipewire_version": "audio/video graph userspace fidelity",
    "wireplumber_version": "multimedia policy-manager fidelity",
    "portal_backend": "desktop permission/session boundary",
    "browser_package_form": "browser lifecycle/package-form fidelity",
}

_RUNTIME_CHECKS = (
    "systemd-system-manager-is-live",
    "non-root-target-user-exists",
    "systemd-user-manager-is-live-for-target-user",
    "xdg-runtime-dir-exists-and-owned-by-target-user",
    "session-dbus-is-reachable-from-target-user-context",
    "declared-session-type-is-observed-or-gap-recorded",
    "pipewire-and-wireplumber-state-is-observed-or-gap-recorded",
    "portal-backend-state-is-observed-or-gap-recorded",
    "one-handoff-installer-entry-is-used",
    "twin-target-differences-are-recorded-not-masked",
)


def build_t1_userspace_plan(
    profile: Mapping[str, Any] | TargetHostProfile,
) -> TwinBootstrapPlan:
    """Create a deterministic T1 plan from exact WP1201 evidence only."""

    projection = TargetProfileProjection.from_mapping(profile)
    gaps = tuple(
        FidelityGap(
            field=name,
            observed_value=value,
            required_for=_GAP_PURPOSE[name],
        )
        for name, value in projection.fields
        if value == UNKNOWN
    )
    return TwinBootstrapPlan(
        schema=PLAN_SCHEMA,
        fidelity=FIDELITY,
        projection_schema=projection.schema,
        source_profile_generation=projection.profile_generation,
        source_profile_sha256=projection.profile_sha256,
        observed_shape=tuple(sorted(projection.fields)),
        source_fact_bindings=projection.source_fact_bindings,
        fidelity_gaps=gaps,
        required_runtime_checks=_RUNTIME_CHECKS,
        one_handoff_installer_entry=ONE_HANDOFF_ENTRY,
    )


def plan_from_json(text: str) -> str:
    """Pure canonical WP1201 JSON-in / T1-plan JSON-out adapter."""

    if type(text) is not str:
        raise TargetUserspaceTwinError("profile JSON must be text")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TargetUserspaceTwinError("invalid target profile JSON") from exc
    if type(raw) is not dict:
        raise TargetUserspaceTwinError("target profile JSON must contain an object")
    return _canonical_json(build_t1_userspace_plan(raw).as_dict()) + "\n"
