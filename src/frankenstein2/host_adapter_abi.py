#!/usr/bin/env python3
"""Deterministic semantic host-adapter ABI and capability assessment.

F2-WP-1101 generation 1.

This module does not probe a host and does not install anything. It receives observed
host/profile evidence from a collector/adapter, binds it to one target-environment
identity and one durable state lineage, validates semantic lifecycle mappings, and
classifies the route fail-closed as NATIVE, ADAPTED, DEGRADED or BLOCKED.

Important boundaries:
- matching hook/event names are not proof that a lifecycle role fires correctly;
- UNKNOWN, DECLARED_ONLY and CONFLICT never satisfy a required capability;
- host-specific evidence is valid only for the exact target-environment digest;
- a host adapter is not a cognitive-state or completion authority;
- repository/source success is not physical-host acceptance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Iterable, Mapping, Sequence


ABI_SCHEMA = "FRANKENSTEIN2_SEMANTIC_HOST_ABI/v1"
TARGET_BINDING_SCHEMA = "FRANKENSTEIN2_TARGET_ENVIRONMENT_BINDING/v1"
CAPABILITY_REPORT_SCHEMA = "FRANKENSTEIN2_HOST_CAPABILITY_REPORT/v1"
SEMANTIC_EVENT_SCHEMA = "FRANKENSTEIN2_SEMANTIC_LIFECYCLE_EVENT/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class HostABIError(ValueError):
    """Fail-closed validation error for host ABI inputs."""


class AdapterClass(str, Enum):
    NATIVE = "NATIVE"
    ADAPTED = "ADAPTED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


class EvidenceState(str, Enum):
    VERIFIED_NATIVE = "VERIFIED_NATIVE"
    VERIFIED_ADAPTED = "VERIFIED_ADAPTED"
    DECLARED_ONLY = "DECLARED_ONLY"
    UNKNOWN = "UNKNOWN"
    MISSING = "MISSING"
    CONFLICT = "CONFLICT"


class LifecycleVerification(str, Enum):
    VERIFIED = "VERIFIED"
    DECLARED_ONLY = "DECLARED_ONLY"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"
    CONFLICT = "CONFLICT"


SEMANTIC_LIFECYCLE_ROLES: tuple[str, ...] = (
    "SESSION_START",
    "USER_TURN",
    "PRE_EFFECT",
    "POST_EFFECT",
    "SESSION_STOP",
    "PRE_COMPACT_OR_CHECKPOINT",
    "TOOL_RESULT_RETURN",
    "BACKGROUND_WAKE",
)
DEFAULT_REQUIRED_ROLES: tuple[str, ...] = tuple(
    role for role in SEMANTIC_LIFECYCLE_ROLES if role != "BACKGROUND_WAKE"
)
DEFAULT_REQUIRED_CAPABILITIES: tuple[str, ...] = (
    "DURABLE_STATE_PATH",
    "STATE_READBACK",
    "LIFECYCLE_EVENT_BINDING",
    "TOOL_RESULT_BINDING",
)
EFFECT_ROLES = frozenset({"PRE_EFFECT", "POST_EFFECT", "TOOL_RESULT_RETURN"})

# v1 verified lifecycle contracts are deliberately closed. Free-form strings may remain
# on non-verified observations, but a VERIFIED binding must use a contract whose semantics
# the ABI actually knows how to interpret and whose evidence_ref can therefore attest.
VERIFIED_OCCURRENCE_CONTRACTS = frozenset({"MEASURED_MULTIPLICITY", "ONCE"})
VERIFIED_TIMING_CONTRACTS = frozenset({"MEASURED_ORDERING", "BEFORE"})

# Fields a LifecycleBinding may require to be present on a SemanticLifecycleEvent.
# Environment/adapter/concrete-event identity is verified separately below.
SEMANTIC_EVENT_IDENTITY_FIELDS = frozenset(
    {
        "session_id",
        "agent_id",
        "task_id",
        "turn_id",
        "causal_id",
        "generation",
        "effect_id",
        "tool_use_id",
    }
)


def _canonical_json(value: Mapping | Sequence | str | int | bool | None) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_json(value: Mapping | Sequence) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_nonempty(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HostABIError(f"{label}_EMPTY")
    return value.strip()


def _require_sha256(value: str, label: str) -> str:
    value = _require_nonempty(value, label)
    if not SHA256_RE.fullmatch(value):
        raise HostABIError(f"{label}_INVALID_SHA256")
    return value


def _require_generation(value: int, label: str = "GENERATION") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostABIError(f"{label}_INVALID")
    return value


@dataclass(frozen=True)
class TargetEnvironmentBinding:
    """Opaque binding to a separately observed target-host profile."""

    schema: str
    profile_generation: int
    profile_digest: str
    host_identity: str
    state_lineage_id: str
    adapter_id: str
    adapter_version: str

    @classmethod
    def create(
        cls,
        *,
        profile_generation: int,
        profile_digest: str,
        host_identity: str,
        state_lineage_id: str,
        adapter_id: str,
        adapter_version: str,
    ) -> "TargetEnvironmentBinding":
        return cls(
            schema=TARGET_BINDING_SCHEMA,
            profile_generation=_require_generation(profile_generation, "PROFILE_GENERATION"),
            profile_digest=_require_sha256(profile_digest, "PROFILE_DIGEST"),
            host_identity=_require_nonempty(host_identity, "HOST_IDENTITY"),
            state_lineage_id=_require_nonempty(state_lineage_id, "STATE_LINEAGE_ID"),
            adapter_id=_require_nonempty(adapter_id, "ADAPTER_ID"),
            adapter_version=_require_nonempty(adapter_version, "ADAPTER_VERSION"),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def binding_digest(self) -> str:
        return _sha256_json(self.to_dict())


@dataclass(frozen=True)
class CapabilityObservation:
    name: str
    state: EvidenceState
    concrete_surface: str | None = None
    evidence_ref: str | None = None
    environment_digest: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.name, "CAPABILITY_NAME")
        if self.environment_digest is not None:
            _require_sha256(self.environment_digest, "CAPABILITY_ENVIRONMENT_DIGEST")
        if self.state in (EvidenceState.VERIFIED_NATIVE, EvidenceState.VERIFIED_ADAPTED):
            if self.concrete_surface is None or not self.concrete_surface.strip():
                raise HostABIError(f"CAPABILITY_{self.name}_VERIFIED_WITHOUT_SURFACE")
            if self.evidence_ref is None or not self.evidence_ref.strip():
                raise HostABIError(f"CAPABILITY_{self.name}_VERIFIED_WITHOUT_EVIDENCE")
            if self.environment_digest is None:
                raise HostABIError(f"CAPABILITY_{self.name}_VERIFIED_WITHOUT_ENVIRONMENT")

    @property
    def is_verified(self) -> bool:
        return self.state in (EvidenceState.VERIFIED_NATIVE, EvidenceState.VERIFIED_ADAPTED)

    @property
    def is_native(self) -> bool:
        return self.state is EvidenceState.VERIFIED_NATIVE


@dataclass(frozen=True)
class LifecycleBinding:
    semantic_role: str
    concrete_event: str | None
    source_surface: str | None
    verification: LifecycleVerification
    evidence_ref: str | None
    environment_digest: str | None
    occurrence_contract: str
    timing_contract: str
    payload_identity_fields: tuple[str, ...]
    native_surface: bool

    def __post_init__(self) -> None:
        if self.semantic_role not in SEMANTIC_LIFECYCLE_ROLES:
            raise HostABIError(f"UNKNOWN_SEMANTIC_ROLE:{self.semantic_role}")
        occurrence_contract = _require_nonempty(self.occurrence_contract, "OCCURRENCE_CONTRACT")
        timing_contract = _require_nonempty(self.timing_contract, "TIMING_CONTRACT")
        if len(set(self.payload_identity_fields)) != len(self.payload_identity_fields):
            raise HostABIError(f"DUPLICATE_PAYLOAD_IDENTITY_FIELD:{self.semantic_role}")
        for field in self.payload_identity_fields:
            field = _require_nonempty(field, "PAYLOAD_IDENTITY_FIELD")
            if field not in SEMANTIC_EVENT_IDENTITY_FIELDS:
                raise HostABIError(f"UNKNOWN_PAYLOAD_IDENTITY_FIELD:{self.semantic_role}:{field}")
        if self.environment_digest is not None:
            _require_sha256(self.environment_digest, "LIFECYCLE_ENVIRONMENT_DIGEST")
        if self.verification is LifecycleVerification.VERIFIED:
            if occurrence_contract not in VERIFIED_OCCURRENCE_CONTRACTS:
                raise HostABIError(f"{self.semantic_role}_UNVERIFIED_OCCURRENCE_CONTRACT:{occurrence_contract}")
            if timing_contract not in VERIFIED_TIMING_CONTRACTS:
                raise HostABIError(f"{self.semantic_role}_UNVERIFIED_TIMING_CONTRACT:{timing_contract}")
            if self.concrete_event is None or not self.concrete_event.strip():
                raise HostABIError(f"{self.semantic_role}_VERIFIED_WITHOUT_EVENT")
            if self.source_surface is None or not self.source_surface.strip():
                raise HostABIError(f"{self.semantic_role}_VERIFIED_WITHOUT_SOURCE")
            if self.evidence_ref is None or not self.evidence_ref.strip():
                raise HostABIError(f"{self.semantic_role}_VERIFIED_WITHOUT_EVIDENCE")
            if self.environment_digest is None:
                raise HostABIError(f"{self.semantic_role}_VERIFIED_WITHOUT_ENVIRONMENT")
        if self.semantic_role in EFFECT_ROLES and self.verification is LifecycleVerification.VERIFIED:
            fields = set(self.payload_identity_fields)
            if not ({"effect_id", "tool_use_id"} & fields):
                raise HostABIError(f"{self.semantic_role}_MISSING_EFFECT_OR_TOOL_IDENTITY")
            if "causal_id" not in fields:
                raise HostABIError(f"{self.semantic_role}_MISSING_CAUSAL_IDENTITY")

    @property
    def is_verified(self) -> bool:
        return self.verification is LifecycleVerification.VERIFIED


@dataclass(frozen=True)
class SemanticLifecycleEvent:
    schema: str
    role: str
    environment_digest: str
    state_lineage_id: str
    adapter_id: str
    session_id: str
    agent_id: str
    task_id: str
    turn_id: str
    causal_id: str
    generation: int
    concrete_event: str
    occurrence_index: int
    payload_digest: str
    effect_id: str | None = None
    tool_use_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        role: str,
        environment_digest: str,
        state_lineage_id: str,
        adapter_id: str,
        session_id: str,
        agent_id: str,
        task_id: str,
        turn_id: str,
        causal_id: str,
        generation: int,
        concrete_event: str,
        occurrence_index: int,
        payload_digest: str,
        effect_id: str | None = None,
        tool_use_id: str | None = None,
    ) -> "SemanticLifecycleEvent":
        if role not in SEMANTIC_LIFECYCLE_ROLES:
            raise HostABIError(f"UNKNOWN_SEMANTIC_ROLE:{role}")
        if isinstance(occurrence_index, bool) or not isinstance(occurrence_index, int) or occurrence_index < 0:
            raise HostABIError("OCCURRENCE_INDEX_INVALID")
        if role in EFFECT_ROLES and not ((effect_id and effect_id.strip()) or (tool_use_id and tool_use_id.strip())):
            raise HostABIError(f"{role}_EVENT_MISSING_EFFECT_OR_TOOL_ID")
        return cls(
            schema=SEMANTIC_EVENT_SCHEMA,
            role=role,
            environment_digest=_require_sha256(environment_digest, "EVENT_ENVIRONMENT_DIGEST"),
            state_lineage_id=_require_nonempty(state_lineage_id, "STATE_LINEAGE_ID"),
            adapter_id=_require_nonempty(adapter_id, "ADAPTER_ID"),
            session_id=_require_nonempty(session_id, "SESSION_ID"),
            agent_id=_require_nonempty(agent_id, "AGENT_ID"),
            task_id=_require_nonempty(task_id, "TASK_ID"),
            turn_id=_require_nonempty(turn_id, "TURN_ID"),
            causal_id=_require_nonempty(causal_id, "CAUSAL_ID"),
            generation=_require_generation(generation),
            concrete_event=_require_nonempty(concrete_event, "CONCRETE_EVENT"),
            occurrence_index=occurrence_index,
            payload_digest=_require_sha256(payload_digest, "PAYLOAD_DIGEST"),
            effect_id=effect_id.strip() if effect_id and effect_id.strip() else None,
            tool_use_id=tool_use_id.strip() if tool_use_id and tool_use_id.strip() else None,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def event_digest(self) -> str:
        return _sha256_json(self.to_dict())


@dataclass(frozen=True)
class HostCapabilityReport:
    schema: str
    classification: AdapterClass
    environment_binding_digest: str
    state_lineage_id: str
    required_roles: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    optional_roles: tuple[str, ...]
    optional_capabilities: tuple[str, ...]
    missing_required_roles: tuple[str, ...]
    unverified_required_roles: tuple[str, ...]
    missing_optional_roles: tuple[str, ...]
    missing_required_capabilities: tuple[str, ...]
    unverified_required_capabilities: tuple[str, ...]
    missing_optional_capabilities: tuple[str, ...]
    conflicts: tuple[str, ...]
    limitations: tuple[str, ...]
    native_surface_complete: bool
    completion_authority: bool = False
    physical_host_credit: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["classification"] = self.classification.value
        return data

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    def report_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _validated_lifecycle_binding(binding: LifecycleBinding) -> LifecycleBinding:
    """Revalidate current binding content at the consumer boundary."""
    if type(binding) is not LifecycleBinding:
        raise HostABIError("LIFECYCLE_BINDING_EXACT_TYPE_REQUIRED")
    return LifecycleBinding(
        semantic_role=binding.semantic_role,
        concrete_event=binding.concrete_event,
        source_surface=binding.source_surface,
        verification=binding.verification,
        evidence_ref=binding.evidence_ref,
        environment_digest=binding.environment_digest,
        occurrence_contract=binding.occurrence_contract,
        timing_contract=binding.timing_contract,
        payload_identity_fields=binding.payload_identity_fields,
        native_surface=binding.native_surface,
    )


def _semantic_event_has_identity(event: SemanticLifecycleEvent, field: str) -> bool:
    if field == "generation":
        value = event.generation
        return not isinstance(value, bool) and isinstance(value, int) and value >= 0
    value = getattr(event, field, None)
    return isinstance(value, str) and bool(value.strip())


def _index_unique_lifecycle(bindings: Iterable[LifecycleBinding]) -> dict[str, LifecycleBinding]:
    result: dict[str, LifecycleBinding] = {}
    for raw_binding in bindings:
        binding = _validated_lifecycle_binding(raw_binding)
        if binding.semantic_role in result:
            raise HostABIError(f"DUPLICATE_SEMANTIC_ROLE_BINDING:{binding.semantic_role}")
        result[binding.semantic_role] = binding
    return result


def _index_unique_capabilities(observations: Iterable[CapabilityObservation]) -> dict[str, CapabilityObservation]:
    result: dict[str, CapabilityObservation] = {}
    for observation in observations:
        if observation.name in result:
            raise HostABIError(f"DUPLICATE_CAPABILITY_OBSERVATION:{observation.name}")
        result[observation.name] = observation
    return result


def _validate_role_set(roles: Iterable[str], label: str) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(roles))
    for role in normalized:
        if role not in SEMANTIC_LIFECYCLE_ROLES:
            raise HostABIError(f"{label}_UNKNOWN_ROLE:{role}")
    return normalized


def _validate_capability_names(names: Iterable[str], label: str) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(names))
    for name in normalized:
        _require_nonempty(name, label)
    return normalized


def assess_host_adapter(
    *,
    environment: TargetEnvironmentBinding,
    lifecycle_bindings: Iterable[LifecycleBinding],
    capabilities: Iterable[CapabilityObservation],
    declared_mode: AdapterClass,
    required_roles: Iterable[str] = DEFAULT_REQUIRED_ROLES,
    required_capabilities: Iterable[str] = DEFAULT_REQUIRED_CAPABILITIES,
    optional_roles: Iterable[str] = ("BACKGROUND_WAKE",),
    optional_capabilities: Iterable[str] = (),
) -> HostCapabilityReport:
    """Assess one concrete host route without granting completion or physical credit."""
    if declared_mode not in (AdapterClass.NATIVE, AdapterClass.ADAPTED):
        raise HostABIError("DECLARED_MODE_MUST_BE_NATIVE_OR_ADAPTED")

    env_digest = environment.binding_digest()
    roles = _index_unique_lifecycle(lifecycle_bindings)
    caps = _index_unique_capabilities(capabilities)
    req_roles = _validate_role_set(required_roles, "REQUIRED_ROLES")
    opt_roles = _validate_role_set(optional_roles, "OPTIONAL_ROLES")
    req_caps = _validate_capability_names(required_capabilities, "REQUIRED_CAPABILITY")
    opt_caps = _validate_capability_names(optional_capabilities, "OPTIONAL_CAPABILITY")

    overlap_roles = set(req_roles) & set(opt_roles)
    overlap_caps = set(req_caps) & set(opt_caps)
    if overlap_roles:
        raise HostABIError("ROLE_REQUIRED_OPTIONAL_OVERLAP:" + ",".join(sorted(overlap_roles)))
    if overlap_caps:
        raise HostABIError("CAPABILITY_REQUIRED_OPTIONAL_OVERLAP:" + ",".join(sorted(overlap_caps)))

    conflicts: list[str] = []
    missing_required_roles: list[str] = []
    unverified_required_roles: list[str] = []
    missing_optional_roles: list[str] = []
    limitations: list[str] = []

    for role in req_roles:
        binding = roles.get(role)
        if binding is None:
            missing_required_roles.append(role)
            continue
        if binding.verification is LifecycleVerification.CONFLICT:
            conflicts.append(f"ROLE:{role}")
        elif not binding.is_verified:
            unverified_required_roles.append(role)
        elif binding.environment_digest != env_digest:
            conflicts.append(f"ROLE_ENVIRONMENT_MISMATCH:{role}")

    for role in opt_roles:
        binding = roles.get(role)
        if binding is None or not binding.is_verified:
            missing_optional_roles.append(role)
            limitations.append(f"OPTIONAL_ROLE_UNAVAILABLE:{role}")
        elif binding.environment_digest != env_digest:
            conflicts.append(f"OPTIONAL_ROLE_ENVIRONMENT_MISMATCH:{role}")

    missing_required_capabilities: list[str] = []
    unverified_required_capabilities: list[str] = []
    missing_optional_capabilities: list[str] = []

    for name in req_caps:
        observation = caps.get(name)
        if observation is None or observation.state is EvidenceState.MISSING:
            missing_required_capabilities.append(name)
            continue
        if observation.state is EvidenceState.CONFLICT:
            conflicts.append(f"CAPABILITY:{name}")
        elif not observation.is_verified:
            unverified_required_capabilities.append(name)
        elif observation.environment_digest != env_digest:
            conflicts.append(f"CAPABILITY_ENVIRONMENT_MISMATCH:{name}")

    for name in opt_caps:
        observation = caps.get(name)
        if observation is None or not observation.is_verified:
            missing_optional_capabilities.append(name)
            limitations.append(f"OPTIONAL_CAPABILITY_UNAVAILABLE:{name}")
        elif observation.environment_digest != env_digest:
            conflicts.append(f"OPTIONAL_CAPABILITY_ENVIRONMENT_MISMATCH:{name}")

    required_blocked = bool(
        conflicts
        or missing_required_roles
        or unverified_required_roles
        or missing_required_capabilities
        or unverified_required_capabilities
    )
    verified_role_bindings = [roles[r] for r in req_roles if r in roles and roles[r].is_verified]
    verified_required_caps = [caps[n] for n in req_caps if n in caps and caps[n].is_verified]
    native_surface_complete = (
        not required_blocked
        and declared_mode is AdapterClass.NATIVE
        and all(binding.native_surface for binding in verified_role_bindings)
        and all(observation.is_native for observation in verified_required_caps)
    )

    if required_blocked:
        classification = AdapterClass.BLOCKED
    elif missing_optional_roles or missing_optional_capabilities:
        classification = AdapterClass.DEGRADED
    elif native_surface_complete:
        classification = AdapterClass.NATIVE
    else:
        classification = AdapterClass.ADAPTED

    if classification is AdapterClass.BLOCKED:
        limitations.append("REQUIRED_HOST_SURFACE_NOT_VERIFIED")
    if declared_mode is AdapterClass.NATIVE and classification is AdapterClass.ADAPTED:
        limitations.append("DECLARED_NATIVE_BUT_ADAPTED_SURFACE_OBSERVED")

    return HostCapabilityReport(
        schema=CAPABILITY_REPORT_SCHEMA,
        classification=classification,
        environment_binding_digest=env_digest,
        state_lineage_id=environment.state_lineage_id,
        required_roles=req_roles,
        required_capabilities=req_caps,
        optional_roles=opt_roles,
        optional_capabilities=opt_caps,
        missing_required_roles=tuple(sorted(missing_required_roles)),
        unverified_required_roles=tuple(sorted(unverified_required_roles)),
        missing_optional_roles=tuple(sorted(missing_optional_roles)),
        missing_required_capabilities=tuple(sorted(missing_required_capabilities)),
        unverified_required_capabilities=tuple(sorted(unverified_required_capabilities)),
        missing_optional_capabilities=tuple(sorted(missing_optional_capabilities)),
        conflicts=tuple(sorted(conflicts)),
        limitations=tuple(sorted(set(limitations))),
        native_surface_complete=native_surface_complete,
    )


def verify_semantic_event_binding(
    event: SemanticLifecycleEvent,
    *,
    environment: TargetEnvironmentBinding,
    binding: LifecycleBinding,
) -> bool:
    """Verify that a normalized event belongs to the exact adapter/environment contract."""
    try:
        binding = _validated_lifecycle_binding(binding)
    except (AttributeError, HostABIError):
        return False
    if type(event) is not SemanticLifecycleEvent or type(environment) is not TargetEnvironmentBinding:
        return False
    env_digest = environment.binding_digest()
    if event.role != binding.semantic_role or not binding.is_verified:
        return False
    if event.environment_digest != env_digest or binding.environment_digest != env_digest:
        return False
    if event.state_lineage_id != environment.state_lineage_id:
        return False
    if event.adapter_id != environment.adapter_id:
        return False
    if event.concrete_event != binding.concrete_event:
        return False
    if any(not _semantic_event_has_identity(event, field) for field in binding.payload_identity_fields):
        return False
    return True
