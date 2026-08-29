"""F2-WP-1103 deterministic Codex CLI host-route planning contract.

The module consumes caller-supplied observations. It never probes an installed Codex
instance and never converts matching event names into firing evidence. The result is a
route candidate only: NATIVE / ADAPTED / DEGRADED / BLOCKED is not installer-runtime,
physical-host, effect, or whole-system completion credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

REPORT_SCHEMA = "FRANKENSTEIN2_CODEX_HOST_CAPABILITY_REPORT/v1"
SURFACE_SCHEMA = "FRANKENSTEIN2_CODEX_SURFACE_OBSERVATION/v1"
ROUTE_SCHEMA = "FRANKENSTEIN2_CODEX_ROUTE_CANDIDATE/v1"

NATIVE = "NATIVE"
ADAPTED = "ADAPTED"
DEGRADED = "DEGRADED"
BLOCKED = "BLOCKED"

REQUIRED_ROLES = (
    "SESSION_START",
    "USER_TURN",
    "PRE_EFFECT",
    "POST_EFFECT",
    "SESSION_STOP",
    "PRE_COMPACT_OR_CHECKPOINT",
    "TOOL_RESULT_RETURN",
)
OPTIONAL_ROLES = ("BACKGROUND_WAKE",)
ALLOWED_ROLES = frozenset(REQUIRED_ROLES + OPTIONAL_ROLES)

DECLARED = "DECLARED"
OBSERVED = "OBSERVED"
FIRING_VERIFIED = "FIRING_VERIFIED"
ALLOWED_EVIDENCE_LEVELS = frozenset({DECLARED, OBSERVED, FIRING_VERIFIED})

NATIVE_SURFACE = "NATIVE"
ADAPTER_SURFACE = "ADAPTER"
ALLOWED_SURFACE_MODES = frozenset({NATIVE_SURFACE, ADAPTER_SURFACE})

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512

# Conservative reject-list only. It is intentionally not presented as a filesystem oracle.
# The caller must still verify the selected durable state root on the real target host.
_DISPOSABLE_ROOT_MARKERS = (
    "/.codex/",
    "\\.codex\\",
    "/tmp/",
    "\\temp\\",
    "/cache/",
    "\\cache\\",
    "/plugin-cache/",
    "\\plugin-cache\\",
)


class CodexRouteError(ValueError):
    """Fail-closed WP1103 contract error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise CodexRouteError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_TEXT:
        raise CodexRouteError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CodexRouteError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise CodexRouteError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _safe_state_root(value: str) -> bool:
    lowered = value.replace("//", "/").lower()
    wrapped = f"/{lowered.strip('/')}/"
    return not any(marker in wrapped for marker in _DISPOSABLE_ROOT_MARKERS)


@dataclass(frozen=True, slots=True)
class CodexSurfaceObservation:
    """One caller-observed Codex host surface mapped to one semantic lifecycle role."""

    schema: str
    surface_id: str
    semantic_role: str
    concrete_event: str
    evidence_level: str
    surface_mode: str
    timing_verified: bool
    payload_identity_verified: bool
    matcher_coverage_verified: bool
    firing_multiplicity_verified: bool

    def __post_init__(self) -> None:
        if self.schema != SURFACE_SCHEMA:
            raise CodexRouteError("surface schema mismatch")
        _text("surface_id", self.surface_id)
        if self.semantic_role not in ALLOWED_ROLES:
            raise CodexRouteError(f"unsupported semantic_role {self.semantic_role!r}")
        _text("concrete_event", self.concrete_event)
        if self.evidence_level not in ALLOWED_EVIDENCE_LEVELS:
            raise CodexRouteError("unsupported evidence_level")
        if self.surface_mode not in ALLOWED_SURFACE_MODES:
            raise CodexRouteError("unsupported surface_mode")
        for name in (
            "timing_verified",
            "payload_identity_verified",
            "matcher_coverage_verified",
            "firing_multiplicity_verified",
        ):
            if type(getattr(self, name)) is not bool:
                raise CodexRouteError(f"{name} must be bool")

    @property
    def firing_contract_verified(self) -> bool:
        """True only when the full event semantics, not merely its name, were verified."""
        return (
            self.evidence_level == FIRING_VERIFIED
            and self.timing_verified
            and self.payload_identity_verified
            and self.matcher_coverage_verified
            and self.firing_multiplicity_verified
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "surface_id": self.surface_id,
            "semantic_role": self.semantic_role,
            "concrete_event": self.concrete_event,
            "evidence_level": self.evidence_level,
            "surface_mode": self.surface_mode,
            "timing_verified": self.timing_verified,
            "payload_identity_verified": self.payload_identity_verified,
            "matcher_coverage_verified": self.matcher_coverage_verified,
            "firing_multiplicity_verified": self.firing_multiplicity_verified,
        }


@dataclass(frozen=True, slots=True)
class CodexHostCapabilityReport:
    """Explicit observations supplied by a separate host-inspection boundary."""

    schema: str
    report_id: str
    target_environment_identity_sha256: str
    codex_version: str
    surfaces: tuple[CodexSurfaceObservation, ...]

    def __post_init__(self) -> None:
        if self.schema != REPORT_SCHEMA:
            raise CodexRouteError("report schema mismatch")
        _text("report_id", self.report_id)
        _sha256(
            "target_environment_identity_sha256",
            self.target_environment_identity_sha256,
        )
        _text("codex_version", self.codex_version)
        if type(self.surfaces) is not tuple:
            raise CodexRouteError("surfaces must be a tuple")
        if any(type(surface) is not CodexSurfaceObservation for surface in self.surfaces):
            raise CodexRouteError(
                "surfaces must contain exact CodexSurfaceObservation values"
            )
        ids = [surface.surface_id for surface in self.surfaces]
        if len(ids) != len(set(ids)):
            raise CodexRouteError("surface_id values must be unique")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "report_id": self.report_id,
            "target_environment_identity_sha256": self.target_environment_identity_sha256,
            "codex_version": self.codex_version,
            "surfaces": [
                surface.as_dict()
                for surface in sorted(self.surfaces, key=lambda item: item.surface_id)
            ],
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class CodexRouteCandidate:
    """Deterministic planning output; never effect or completion authority."""

    schema: str
    route_id: str
    capability_report_sha256: str
    target_environment_identity_sha256: str
    release_manifest_sha256: str
    state_lineage_id: str
    durable_state_root: str
    classification: str
    role_bindings: tuple[tuple[str, str], ...]
    missing_roles: tuple[str, ...]
    unverified_roles: tuple[str, ...]
    ambiguous_roles: tuple[str, ...]
    adapter_roles: tuple[str, ...]
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != ROUTE_SCHEMA:
            raise CodexRouteError("route schema mismatch")
        _text("route_id", self.route_id)
        _sha256("capability_report_sha256", self.capability_report_sha256)
        _sha256(
            "target_environment_identity_sha256",
            self.target_environment_identity_sha256,
        )
        _sha256("release_manifest_sha256", self.release_manifest_sha256)
        _text("state_lineage_id", self.state_lineage_id)
        _text("durable_state_root", self.durable_state_root)
        if self.classification not in {NATIVE, ADAPTED, DEGRADED, BLOCKED}:
            raise CodexRouteError("unsupported route classification")
        for name in (
            "role_bindings",
            "missing_roles",
            "unverified_roles",
            "ambiguous_roles",
            "adapter_roles",
            "notes",
        ):
            if type(getattr(self, name)) is not tuple:
                raise CodexRouteError(f"{name} must be tuple")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "route_id": self.route_id,
            "capability_report_sha256": self.capability_report_sha256,
            "target_environment_identity_sha256": self.target_environment_identity_sha256,
            "release_manifest_sha256": self.release_manifest_sha256,
            "state_lineage_id": self.state_lineage_id,
            "durable_state_root": self.durable_state_root,
            "classification": self.classification,
            "role_bindings": [list(item) for item in self.role_bindings],
            "missing_roles": list(self.missing_roles),
            "unverified_roles": list(self.unverified_roles),
            "ambiguous_roles": list(self.ambiguous_roles),
            "adapter_roles": list(self.adapter_roles),
            "notes": list(self.notes),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def plan_codex_route(
    *,
    report: CodexHostCapabilityReport,
    release_manifest_sha256: str,
    state_lineage_id: str,
    durable_state_root: str,
    route_id: str,
) -> CodexRouteCandidate:
    """Build a route candidate from explicit observations only.

    A concrete event is bindable only after timing, payload identity, matcher coverage,
    and firing multiplicity are all verified. Multiple fully verified bindings for one
    required semantic role are treated as ambiguous rather than guessed between.
    """
    if type(report) is not CodexHostCapabilityReport:
        raise CodexRouteError("report must be exact CodexHostCapabilityReport")
    _sha256("release_manifest_sha256", release_manifest_sha256)
    _text("state_lineage_id", state_lineage_id)
    _text("durable_state_root", durable_state_root)
    _text("route_id", route_id)

    by_role: dict[str, list[CodexSurfaceObservation]] = {
        role: [] for role in ALLOWED_ROLES
    }
    for surface in report.surfaces:
        by_role[surface.semantic_role].append(surface)

    bindings: list[tuple[str, str]] = []
    missing: list[str] = []
    unverified: list[str] = []
    ambiguous: list[str] = []
    adapter_roles: list[str] = []
    notes: list[str] = []

    for role in REQUIRED_ROLES:
        candidates = sorted(by_role[role], key=lambda item: item.surface_id)
        if not candidates:
            missing.append(role)
            continue
        verified = [item for item in candidates if item.firing_contract_verified]
        if not verified:
            unverified.append(role)
            continue
        if len(verified) > 1:
            ambiguous.append(role)
            continue
        selected = verified[0]
        bindings.append((role, selected.surface_id))
        if selected.surface_mode == ADAPTER_SURFACE:
            adapter_roles.append(role)

    unsafe_state_root = not _safe_state_root(durable_state_root)
    if unsafe_state_root:
        notes.append("DURABLE_STATE_ROOT_MATCHES_DISPOSABLE_HOST_OR_CACHE_LOCATION")

    optional_verified = [
        item
        for item in sorted(by_role["BACKGROUND_WAKE"], key=lambda item: item.surface_id)
        if item.firing_contract_verified
    ]
    if len(optional_verified) == 1:
        bindings.append(("BACKGROUND_WAKE", optional_verified[0].surface_id))
        if optional_verified[0].surface_mode == ADAPTER_SURFACE:
            adapter_roles.append("BACKGROUND_WAKE")
    elif len(optional_verified) > 1:
        notes.append("OPTIONAL_BACKGROUND_WAKE_AMBIGUOUS_NOT_BOUND")

    if unsafe_state_root or missing or ambiguous:
        classification = BLOCKED
    elif unverified:
        classification = DEGRADED
    elif adapter_roles:
        classification = ADAPTED
    else:
        classification = NATIVE

    if missing:
        notes.append("REQUIRED_ROLE_MISSING")
    if unverified:
        notes.append("MATCHING_SURFACE_WITHOUT_FULL_FIRING_EVIDENCE")
    if ambiguous:
        notes.append("MULTIPLE_FULLY_VERIFIED_SURFACES_FOR_REQUIRED_ROLE")

    return CodexRouteCandidate(
        schema=ROUTE_SCHEMA,
        route_id=route_id,
        capability_report_sha256=report.sha256(),
        target_environment_identity_sha256=report.target_environment_identity_sha256,
        release_manifest_sha256=release_manifest_sha256,
        state_lineage_id=state_lineage_id,
        durable_state_root=durable_state_root,
        classification=classification,
        role_bindings=tuple(sorted(bindings)),
        missing_roles=tuple(sorted(missing)),
        unverified_roles=tuple(sorted(unverified)),
        ambiguous_roles=tuple(sorted(ambiguous)),
        adapter_roles=tuple(sorted(adapter_roles)),
        notes=tuple(sorted(notes)),
    )
