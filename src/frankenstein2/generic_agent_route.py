#!/usr/bin/env python3
"""Deterministic generic coding-agent install-route planner.

F2-WP-1104 generation 2.

The route planner consumes a semantic host capability report plus a WP1104-owned
producer-bound assessment envelope. Positive generic-host routing is permitted only
when the report can be deterministically recomputed by the canonical WP1101
``assess_host_adapter`` producer from explicit environment/lifecycle/capability inputs.
A report digest or internally self-consistent report fields are not producer lineage.

This module does not probe a host, install a package, touch the filesystem, call a
provider, or grant physical-host / completion credit. Generic product-name recognition
is not compatibility evidence: NATIVE is available only when the exact release and
exact host-environment have independently VERIFIED native-support evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import re
from typing import Iterable

from .host_adapter_abi import (
    AdapterClass,
    CAPABILITY_REPORT_SCHEMA,
    DEFAULT_REQUIRED_CAPABILITIES,
    DEFAULT_REQUIRED_ROLES,
    CapabilityObservation,
    HostCapabilityReport,
    LifecycleBinding,
    TargetEnvironmentBinding,
    assess_host_adapter,
)


ROUTE_SCHEMA = "FRANKENSTEIN2_GENERIC_AGENT_ROUTE/v2"
RELEASE_SCHEMA = "FRANKENSTEIN2_GENERIC_AGENT_RELEASE_BINDING/v1"
NATIVE_SUPPORT_SCHEMA = "FRANKENSTEIN2_GENERIC_AGENT_NATIVE_SUPPORT/v1"
ASSESSMENT_EVIDENCE_SCHEMA = "FRANKENSTEIN2_GENERIC_AGENT_ASSESSMENT_EVIDENCE/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_ASSESSMENT_ORIGIN = object()


class GenericAgentRouteError(ValueError):
    """Fail-closed validation error for generic host route inputs."""


class StateRootClass(str, Enum):
    DURABLE_USER_DATA = "DURABLE_USER_DATA"
    HOST_PLUGIN_CACHE = "HOST_PLUGIN_CACHE"
    HOST_CACHE = "HOST_CACHE"
    TEMPORARY = "TEMPORARY"
    UNKNOWN = "UNKNOWN"


class SupportEvidenceState(str, Enum):
    VERIFIED = "VERIFIED"
    DECLARED_ONLY = "DECLARED_ONLY"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_nonempty(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GenericAgentRouteError(f"{label}_EMPTY")
    return value.strip()


def _require_sha256(value: str, label: str) -> str:
    value = _require_nonempty(value, label)
    if not SHA256_RE.fullmatch(value):
        raise GenericAgentRouteError(f"{label}_INVALID_SHA256")
    return value


def _require_git_object(value: str, label: str) -> str:
    value = _require_nonempty(value, label)
    if not GIT_OBJECT_RE.fullmatch(value):
        raise GenericAgentRouteError(f"{label}_INVALID_GIT_OBJECT")
    return value


def _validate_capability_report_consistency(report: HostCapabilityReport) -> None:
    """Reject impossible caller-supplied report states before field consumption."""
    if type(report) is not HostCapabilityReport:
        raise GenericAgentRouteError("CAPABILITY_REPORT_EXACT_TYPE_REQUIRED")
    if report.schema != CAPABILITY_REPORT_SCHEMA:
        raise GenericAgentRouteError("CAPABILITY_REPORT_SCHEMA_MISMATCH")
    if not isinstance(report.classification, AdapterClass):
        raise GenericAgentRouteError("CAPABILITY_REPORT_CLASSIFICATION_INVALID")

    required_blocked = bool(
        report.conflicts
        or report.missing_required_roles
        or report.unverified_required_roles
        or report.missing_required_capabilities
        or report.unverified_required_capabilities
    )
    optional_degraded = bool(
        report.missing_optional_roles or report.missing_optional_capabilities
    )

    if required_blocked:
        if report.classification is not AdapterClass.BLOCKED:
            raise GenericAgentRouteError(
                "CAPABILITY_REPORT_REQUIRED_DEFICIT_CLASSIFICATION_MISMATCH"
            )
        if report.native_surface_complete:
            raise GenericAgentRouteError(
                "CAPABILITY_REPORT_BLOCKED_CANNOT_BE_NATIVE_COMPLETE"
            )
        return

    if optional_degraded:
        if report.classification is not AdapterClass.DEGRADED:
            raise GenericAgentRouteError(
                "CAPABILITY_REPORT_OPTIONAL_DEFICIT_CLASSIFICATION_MISMATCH"
            )
        if report.native_surface_complete:
            raise GenericAgentRouteError(
                "CAPABILITY_REPORT_DEGRADED_CANNOT_BE_NATIVE_COMPLETE"
            )
        return

    if report.classification not in (AdapterClass.ADAPTED, AdapterClass.NATIVE):
        raise GenericAgentRouteError(
            "CAPABILITY_REPORT_CLEAR_SURFACE_CLASSIFICATION_MISMATCH"
        )
    if report.classification is AdapterClass.NATIVE and not report.native_surface_complete:
        raise GenericAgentRouteError("CAPABILITY_REPORT_NATIVE_WITHOUT_COMPLETE_NATIVE_SURFACE")
    if report.classification is AdapterClass.ADAPTED and report.native_surface_complete:
        raise GenericAgentRouteError("CAPABILITY_REPORT_ADAPTED_WITH_NATIVE_COMPLETE_SURFACE")


@dataclass(frozen=True)
class AssessedHostCapabilityEvidence:
    """WP1104 producer-bound envelope around canonical WP1101 assessment inputs.

    The public ``HostCapabilityReport`` remains directly constructible by design in its
    owning WP1101 ABI. WP1104 therefore does not treat that object or its digest as proof
    that assessment occurred. This envelope is created only by ``from_observations`` and
    stores the exact inputs required to recompute the canonical report at consumption.

    Runtime authenticity of ``evidence_ref`` values remains a later host/clean-machine
    acceptance question; this component only closes the deterministic producer boundary.
    """

    schema: str
    environment: TargetEnvironmentBinding
    lifecycle_bindings: tuple[LifecycleBinding, ...]
    capabilities: tuple[CapabilityObservation, ...]
    declared_mode: AdapterClass
    optional_roles: tuple[str, ...]
    optional_capabilities: tuple[str, ...]
    report: HostCapabilityReport
    _origin: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.schema != ASSESSMENT_EVIDENCE_SCHEMA:
            raise GenericAgentRouteError("ASSESSMENT_EVIDENCE_SCHEMA_MISMATCH")
        if self._origin is not _ASSESSMENT_ORIGIN:
            raise GenericAgentRouteError("ASSESSMENT_EVIDENCE_PRODUCER_ORIGIN_REQUIRED")
        if type(self.environment) is not TargetEnvironmentBinding:
            raise GenericAgentRouteError("ASSESSMENT_ENVIRONMENT_EXACT_TYPE_REQUIRED")
        if type(self.report) is not HostCapabilityReport:
            raise GenericAgentRouteError("ASSESSMENT_REPORT_EXACT_TYPE_REQUIRED")

    @classmethod
    def from_observations(
        cls,
        *,
        environment: TargetEnvironmentBinding,
        lifecycle_bindings: Iterable[LifecycleBinding],
        capabilities: Iterable[CapabilityObservation],
        declared_mode: AdapterClass,
        optional_roles: Iterable[str] = ("BACKGROUND_WAKE",),
        optional_capabilities: Iterable[str] = (),
    ) -> "AssessedHostCapabilityEvidence":
        lifecycle_tuple = tuple(lifecycle_bindings)
        capability_tuple = tuple(capabilities)
        optional_role_tuple = tuple(optional_roles)
        optional_capability_tuple = tuple(optional_capabilities)
        report = assess_host_adapter(
            environment=environment,
            lifecycle_bindings=lifecycle_tuple,
            capabilities=capability_tuple,
            declared_mode=declared_mode,
            required_roles=DEFAULT_REQUIRED_ROLES,
            required_capabilities=DEFAULT_REQUIRED_CAPABILITIES,
            optional_roles=optional_role_tuple,
            optional_capabilities=optional_capability_tuple,
        )
        return cls(
            schema=ASSESSMENT_EVIDENCE_SCHEMA,
            environment=environment,
            lifecycle_bindings=lifecycle_tuple,
            capabilities=capability_tuple,
            declared_mode=declared_mode,
            optional_roles=optional_role_tuple,
            optional_capabilities=optional_capability_tuple,
            report=report,
            _origin=_ASSESSMENT_ORIGIN,
        )

    def recompute_report(self) -> HostCapabilityReport:
        """Re-run the canonical producer and require exact report equality."""
        if self._origin is not _ASSESSMENT_ORIGIN:
            raise GenericAgentRouteError("ASSESSMENT_EVIDENCE_PRODUCER_ORIGIN_REQUIRED")
        recomputed = assess_host_adapter(
            environment=self.environment,
            lifecycle_bindings=self.lifecycle_bindings,
            capabilities=self.capabilities,
            declared_mode=self.declared_mode,
            required_roles=DEFAULT_REQUIRED_ROLES,
            required_capabilities=DEFAULT_REQUIRED_CAPABILITIES,
            optional_roles=self.optional_roles,
            optional_capabilities=self.optional_capabilities,
        )
        if recomputed.canonical_json() != self.report.canonical_json():
            raise GenericAgentRouteError("ASSESSMENT_EVIDENCE_REPORT_RECOMPUTE_MISMATCH")
        return recomputed


@dataclass(frozen=True)
class ReleaseBinding:
    """Exact release candidate identity consumed by the generic host route."""

    schema: str
    release_id: str
    release_manifest_digest: str
    source_commit: str
    state_migration_version: str

    @classmethod
    def create(
        cls,
        *,
        release_id: str,
        release_manifest_digest: str,
        source_commit: str,
        state_migration_version: str,
    ) -> "ReleaseBinding":
        return cls(
            schema=RELEASE_SCHEMA,
            release_id=_require_nonempty(release_id, "RELEASE_ID"),
            release_manifest_digest=_require_sha256(
                release_manifest_digest, "RELEASE_MANIFEST_DIGEST"
            ),
            source_commit=_require_git_object(source_commit, "SOURCE_COMMIT"),
            state_migration_version=_require_nonempty(
                state_migration_version, "STATE_MIGRATION_VERSION"
            ),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def binding_digest(self) -> str:
        return _sha256_json(self.to_dict())


@dataclass(frozen=True)
class NativeSupportEvidence:
    """Release-specific native-support evidence for one exact host environment."""

    schema: str
    state: SupportEvidenceState
    release_binding_digest: str
    environment_binding_digest: str
    host_family: str
    evidence_ref: str | None

    @classmethod
    def create(
        cls,
        *,
        state: SupportEvidenceState,
        release_binding_digest: str,
        environment_binding_digest: str,
        host_family: str,
        evidence_ref: str | None = None,
    ) -> "NativeSupportEvidence":
        release_binding_digest = _require_sha256(
            release_binding_digest, "NATIVE_SUPPORT_RELEASE_DIGEST"
        )
        environment_binding_digest = _require_sha256(
            environment_binding_digest, "NATIVE_SUPPORT_ENVIRONMENT_DIGEST"
        )
        host_family = _require_nonempty(host_family, "NATIVE_SUPPORT_HOST_FAMILY")
        if state is SupportEvidenceState.VERIFIED:
            if evidence_ref is None or not evidence_ref.strip():
                raise GenericAgentRouteError("VERIFIED_NATIVE_SUPPORT_WITHOUT_EVIDENCE")
        return cls(
            schema=NATIVE_SUPPORT_SCHEMA,
            state=state,
            release_binding_digest=release_binding_digest,
            environment_binding_digest=environment_binding_digest,
            host_family=host_family,
            evidence_ref=evidence_ref.strip() if evidence_ref and evidence_ref.strip() else None,
        )

    def verifies(
        self,
        *,
        release_binding_digest: str,
        environment_binding_digest: str,
        host_family: str,
    ) -> bool:
        return (
            self.state is SupportEvidenceState.VERIFIED
            and self.release_binding_digest == release_binding_digest
            and self.environment_binding_digest == environment_binding_digest
            and self.host_family == host_family
            and bool(self.evidence_ref)
        )


@dataclass(frozen=True)
class GenericAgentRouteCandidate:
    schema: str
    host_family: str
    host_version: str
    release_binding_digest: str
    environment_binding_digest: str
    capability_report_digest: str
    state_lineage_id: str
    durable_state_root: str
    state_root_class: StateRootClass
    classification: AdapterClass
    limitations: tuple[str, ...]
    native_support_evidence_ref: str | None
    baseline_local_boot_requires_vps: bool = False
    mutation_authority: bool = False
    completion_authority: bool = False
    physical_host_credit: bool = False
    installer_runtime_credit: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["classification"] = self.classification.value
        data["state_root_class"] = self.state_root_class.value
        return data

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    def route_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _verify_positive_report_producer_lineage(
    *,
    report: HostCapabilityReport,
    evidence: AssessedHostCapabilityEvidence | None,
    environment_binding_digest: str,
    state_lineage_id: str,
) -> None:
    """Require exact canonical producer re-entry for any non-BLOCKED route."""
    if report.classification is AdapterClass.BLOCKED:
        return
    if evidence is None:
        raise GenericAgentRouteError("CAPABILITY_REPORT_PRODUCER_LINEAGE_REQUIRED")
    if type(evidence) is not AssessedHostCapabilityEvidence:
        raise GenericAgentRouteError("ASSESSMENT_EVIDENCE_EXACT_TYPE_REQUIRED")

    recomputed = evidence.recompute_report()
    if recomputed.canonical_json() != report.canonical_json():
        raise GenericAgentRouteError("CAPABILITY_REPORT_PRODUCER_LINEAGE_MISMATCH")
    if evidence.environment.binding_digest() != environment_binding_digest:
        raise GenericAgentRouteError("ASSESSMENT_EVIDENCE_ENVIRONMENT_MISMATCH")
    if evidence.environment.state_lineage_id != state_lineage_id:
        raise GenericAgentRouteError("ASSESSMENT_EVIDENCE_STATE_LINEAGE_MISMATCH")


def plan_generic_agent_route(
    *,
    host_family: str,
    host_version: str,
    release: ReleaseBinding,
    capability_report: HostCapabilityReport,
    environment_binding_digest: str,
    state_lineage_id: str,
    durable_state_root: str,
    state_root_class: StateRootClass,
    capability_evidence: AssessedHostCapabilityEvidence | None = None,
    native_support: NativeSupportEvidence | None = None,
) -> GenericAgentRouteCandidate:
    """Plan one generic coding-agent route from explicit evidence only.

    Positive ADAPTED/DEGRADED/NATIVE routing requires a producer-bound assessment
    envelope whose stored report is recomputed at this consumer boundary. BLOCKED is
    allowed without producer proof because it grants no positive compatibility route.
    """

    host_family = _require_nonempty(host_family, "HOST_FAMILY")
    host_version = _require_nonempty(host_version, "HOST_VERSION")
    environment_binding_digest = _require_sha256(
        environment_binding_digest, "ENVIRONMENT_BINDING_DIGEST"
    )
    state_lineage_id = _require_nonempty(state_lineage_id, "STATE_LINEAGE_ID")
    durable_state_root = _require_nonempty(durable_state_root, "DURABLE_STATE_ROOT")

    _validate_capability_report_consistency(capability_report)

    if state_root_class is not StateRootClass.DURABLE_USER_DATA:
        raise GenericAgentRouteError(
            f"CANONICAL_STATE_ROOT_NOT_DURABLE_USER_DATA:{state_root_class.value}"
        )
    if capability_report.environment_binding_digest != environment_binding_digest:
        raise GenericAgentRouteError("CAPABILITY_REPORT_ENVIRONMENT_MISMATCH")
    if capability_report.state_lineage_id != state_lineage_id:
        raise GenericAgentRouteError("CAPABILITY_REPORT_STATE_LINEAGE_MISMATCH")
    if capability_report.completion_authority:
        raise GenericAgentRouteError("CAPABILITY_REPORT_MUST_NOT_HAVE_COMPLETION_AUTHORITY")
    if capability_report.physical_host_credit:
        raise GenericAgentRouteError("CAPABILITY_REPORT_MUST_NOT_HAVE_PHYSICAL_HOST_CREDIT")

    _verify_positive_report_producer_lineage(
        report=capability_report,
        evidence=capability_evidence,
        environment_binding_digest=environment_binding_digest,
        state_lineage_id=state_lineage_id,
    )

    release_digest = release.binding_digest()
    limitations = list(capability_report.limitations)
    classification = capability_report.classification
    native_evidence_ref: str | None = None

    if classification is AdapterClass.NATIVE:
        native_is_verified = native_support is not None and native_support.verifies(
            release_binding_digest=release_digest,
            environment_binding_digest=environment_binding_digest,
            host_family=host_family,
        )
        if native_is_verified:
            native_evidence_ref = native_support.evidence_ref
        else:
            classification = AdapterClass.ADAPTED
            limitations.append("GENERIC_NATIVE_SUPPORT_NOT_RELEASE_VERIFIED")

    limitations = list(dict.fromkeys(limitations))

    return GenericAgentRouteCandidate(
        schema=ROUTE_SCHEMA,
        host_family=host_family,
        host_version=host_version,
        release_binding_digest=release_digest,
        environment_binding_digest=environment_binding_digest,
        capability_report_digest=capability_report.report_digest(),
        state_lineage_id=state_lineage_id,
        durable_state_root=durable_state_root,
        state_root_class=state_root_class,
        classification=classification,
        limitations=tuple(limitations),
        native_support_evidence_ref=native_evidence_ref,
    )
