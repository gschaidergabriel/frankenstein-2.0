#!/usr/bin/env python3
"""Deterministic generic coding-agent install-route planner.

F2-WP-1104 generation 1.

This module is deliberately thin. It consumes the generic semantic host capability
report produced by :mod:`frankenstein2.host_adapter_abi` and turns that evidence into
a route candidate for an otherwise-unrecognized local coding-agent host.

It does not probe a host, install a package, touch the filesystem, call a provider,
or grant physical-host / completion credit. Generic product-name recognition is not
compatibility evidence: NATIVE is available only when the exact release and exact
host-environment have an independently VERIFIED native-support record.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import re

from .host_adapter_abi import AdapterClass, HostCapabilityReport


ROUTE_SCHEMA = "FRANKENSTEIN2_GENERIC_AGENT_ROUTE/v1"
RELEASE_SCHEMA = "FRANKENSTEIN2_GENERIC_AGENT_RELEASE_BINDING/v1"
NATIVE_SUPPORT_SCHEMA = "FRANKENSTEIN2_GENERIC_AGENT_NATIVE_SUPPORT/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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
            source_commit=_require_sha256(source_commit, "SOURCE_COMMIT"),
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
    native_support: NativeSupportEvidence | None = None,
) -> GenericAgentRouteCandidate:
    """Plan one generic coding-agent route from explicit evidence only.

    The capability report remains the authority for lifecycle/capability readiness.
    This function cannot upgrade a BLOCKED or DEGRADED report. A report that says
    NATIVE is deliberately reduced to ADAPTED unless exact release-specific native
    support is independently VERIFIED for the same environment and host family.
    """

    host_family = _require_nonempty(host_family, "HOST_FAMILY")
    host_version = _require_nonempty(host_version, "HOST_VERSION")
    environment_binding_digest = _require_sha256(
        environment_binding_digest, "ENVIRONMENT_BINDING_DIGEST"
    )
    state_lineage_id = _require_nonempty(state_lineage_id, "STATE_LINEAGE_ID")
    durable_state_root = _require_nonempty(durable_state_root, "DURABLE_STATE_ROOT")

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
            # Generic capability equivalence is useful, but it cannot mint release-level
            # native support. Preserve the stronger factual host evidence while reporting
            # the portable route truthfully as ADAPTED.
            classification = AdapterClass.ADAPTED
            limitations.append("GENERIC_NATIVE_SUPPORT_NOT_RELEASE_VERIFIED")

    # Preserve deterministic order while removing duplicates from upstream limitations.
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
