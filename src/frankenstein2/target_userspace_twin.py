"""Target-host Ubuntu userspace twin planning for Frankenstein 2.0.

F2-WP-1202 generation 1.

This module builds a deterministic *T1 userspace* bootstrap plan from an observed target
profile. It deliberately does not infer missing distro, kernel, package, session, device,
or permission facts. Unknown target facts remain UNKNOWN fidelity gaps.

The plan is a pre-handoff engineering artifact only:

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

PROFILE_SCHEMA = "FRANKENSTEIN2_TARGET_HOST_PROFILE/v1"
PLAN_SCHEMA = "FRANKENSTEIN2_T1_USERSPACE_TWIN_PLAN/v1"
FIDELITY = "T1_UBUNTU_USERSPACE"
UNKNOWN = "UNKNOWN"
ONE_HANDOFF_ENTRY = "AI_START_HERE_DO_NOT_SCAN_REPO"

_REQUIRED_PROFILE_FIELDS = (
    "os_release",
    "kernel_release",
    "architecture",
    "uid",
    "session_type",
    "xdg_runtime_dir",
    "session_dbus",
    "systemd_user",
    "pipewire_version",
    "wireplumber_version",
    "portal_backend",
    "browser_package_form",
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
    if not isinstance(value, str):
        raise TargetUserspaceTwinError(f"{name} must be a string")
    if value != value.strip() or not value:
        raise TargetUserspaceTwinError(f"{name} must be non-empty and already trimmed")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TargetUserspaceTwinError(f"{name} contains control characters")
    return value


def _digest(value: Any) -> str:
    text = _string("profile_sha256", value)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise TargetUserspaceTwinError("profile_sha256 must be lowercase 64-hex SHA-256")
    return text


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise TargetUserspaceTwinError("profile_generation must be a non-negative integer")
    return value


def _observed_or_unknown(name: str, value: Any) -> str:
    if value is None:
        return UNKNOWN
    text = _string(name, value)
    return text


@dataclass(frozen=True, slots=True)
class TargetProfileProjection:
    """Minimal non-secret profile projection required for a T1 userspace twin."""

    schema: str
    profile_generation: int
    profile_sha256: str
    fields: tuple[tuple[str, str], ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TargetProfileProjection":
        if not isinstance(raw, Mapping):
            raise TargetUserspaceTwinError("target profile must be a mapping")
        schema = raw.get("schema", PROFILE_SCHEMA)
        if schema != PROFILE_SCHEMA:
            raise TargetUserspaceTwinError("target profile schema mismatch")
        generation = _generation(raw.get("profile_generation"))
        digest = _digest(raw.get("profile_sha256"))
        fields_raw = raw.get("fields")
        if not isinstance(fields_raw, Mapping):
            raise TargetUserspaceTwinError("target profile fields must be a mapping")

        normalized = tuple(
            (name, _observed_or_unknown(name, fields_raw.get(name)))
            for name in _REQUIRED_PROFILE_FIELDS
        )
        return cls(
            schema=PROFILE_SCHEMA,
            profile_generation=generation,
            profile_sha256=digest,
            fields=normalized,
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
    source_profile_generation: int
    source_profile_sha256: str
    observed_shape: tuple[tuple[str, str], ...]
    fidelity_gaps: tuple[FidelityGap, ...]
    required_runtime_checks: tuple[str, ...]
    one_handoff_installer_entry: str
    classification: str = "T1_PREHANDOFF_PLAN_NO_PHYSICAL_OR_COMPLETION_CREDIT"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "fidelity": self.fidelity,
            "source_profile_generation": self.source_profile_generation,
            "source_profile_sha256": self.source_profile_sha256,
            "observed_shape": dict(self.observed_shape),
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


def build_t1_userspace_plan(profile: Mapping[str, Any]) -> TwinBootstrapPlan:
    """Create a deterministic T1 plan while preserving every unknown input as UNKNOWN.

    The function never substitutes a plausible Ubuntu/kernel/session default for missing
    target evidence. That would collapse target reality into builder assumptions.
    """

    projection = TargetProfileProjection.from_mapping(profile)
    observed = projection.field_map()
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
        source_profile_generation=projection.profile_generation,
        source_profile_sha256=projection.profile_sha256,
        observed_shape=tuple(sorted(observed.items())),
        fidelity_gaps=gaps,
        required_runtime_checks=_RUNTIME_CHECKS,
        one_handoff_installer_entry=ONE_HANDOFF_ENTRY,
    )


def plan_from_json(text: str) -> str:
    """Pure JSON-in/JSON-out adapter for deterministic CI and installer tooling."""

    if not isinstance(text, str):
        raise TargetUserspaceTwinError("profile JSON must be text")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TargetUserspaceTwinError("invalid target profile JSON") from exc
    if not isinstance(raw, dict):
        raise TargetUserspaceTwinError("target profile JSON must contain an object")
    return _canonical_json(build_t1_userspace_plan(raw).as_dict()) + "\n"
