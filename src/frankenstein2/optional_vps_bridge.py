#!/usr/bin/env python3
"""Deterministic optional VPS/HCU bridge planning and validation.

F2-WP-1106 generation 1.

This module is deliberately non-executing. It receives caller-supplied evidence about
one local runtime and (optionally) one remote bridge endpoint, then validates whether
ATTACH or DETACH is admissible without making the VPS a prerequisite for baseline
local boot or creating a second state/truth/effect authority.

Repository/source success is not physical bridge or target-runtime acceptance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Mapping, Sequence


LOCAL_RUNTIME_SCHEMA = "FRANKENSTEIN2_LOCAL_RUNTIME_IDENTITY/v1"
REMOTE_ENDPOINT_SCHEMA = "FRANKENSTEIN2_OPTIONAL_REMOTE_ENDPOINT/v1"
BRIDGE_PLAN_SCHEMA = "FRANKENSTEIN2_OPTIONAL_VPS_BRIDGE_PLAN/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BridgeValidationError(ValueError):
    """Fail-closed bridge planning error."""


class EvidenceState(str, Enum):
    VERIFIED = "VERIFIED"
    DECLARED_ONLY = "DECLARED_ONLY"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


class BridgeAction(str, Enum):
    ATTACH = "ATTACH"
    DETACH = "DETACH"


class BridgeDisposition(str, Enum):
    ATTACHED = "ATTACHED"
    DETACHED = "DETACHED"
    BLOCKED = "BLOCKED"


def _canonical_json(value: Mapping | Sequence) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_json(value: Mapping | Sequence) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_nonempty(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BridgeValidationError(f"{label}_EMPTY")
    return value.strip()


def _require_sha256(value: str, label: str) -> str:
    value = _require_nonempty(value, label)
    if not SHA256_RE.fullmatch(value):
        raise BridgeValidationError(f"{label}_INVALID_SHA256")
    return value


def _require_generation(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BridgeValidationError(f"{label}_INVALID")
    return value


@dataclass(frozen=True)
class LocalRuntimeIdentity:
    schema: str
    runtime_id: str
    release_digest: str
    state_lineage_id: str
    state_generation: int
    baseline_boot_state: EvidenceState
    baseline_boot_evidence_ref: str | None

    @classmethod
    def create(
        cls,
        *,
        runtime_id: str,
        release_digest: str,
        state_lineage_id: str,
        state_generation: int,
        baseline_boot_state: EvidenceState,
        baseline_boot_evidence_ref: str | None,
    ) -> "LocalRuntimeIdentity":
        runtime_id = _require_nonempty(runtime_id, "RUNTIME_ID")
        state_lineage_id = _require_nonempty(state_lineage_id, "STATE_LINEAGE_ID")
        release_digest = _require_sha256(release_digest, "RELEASE_DIGEST")
        state_generation = _require_generation(state_generation, "STATE_GENERATION")
        if baseline_boot_state is EvidenceState.VERIFIED:
            if baseline_boot_evidence_ref is None or not baseline_boot_evidence_ref.strip():
                raise BridgeValidationError("VERIFIED_BASELINE_BOOT_WITHOUT_EVIDENCE")
        return cls(
            schema=LOCAL_RUNTIME_SCHEMA,
            runtime_id=runtime_id,
            release_digest=release_digest,
            state_lineage_id=state_lineage_id,
            state_generation=state_generation,
            baseline_boot_state=baseline_boot_state,
            baseline_boot_evidence_ref=(
                baseline_boot_evidence_ref.strip()
                if baseline_boot_evidence_ref and baseline_boot_evidence_ref.strip()
                else None
            ),
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["baseline_boot_state"] = self.baseline_boot_state.value
        return data

    def identity_digest(self) -> str:
        return _sha256_json(self.to_dict())


@dataclass(frozen=True)
class RemoteEndpointEvidence:
    schema: str
    endpoint_id: str
    transport: str
    environment_digest: str
    capability_report_digest: str
    bound_local_state_lineage_id: str
    availability_state: EvidenceState
    availability_evidence_ref: str | None
    typed_request_result_transport: bool
    canonical_state_authority: bool = False
    truth_authority: bool = False
    effect_authority: bool = False

    @classmethod
    def create(
        cls,
        *,
        endpoint_id: str,
        transport: str,
        environment_digest: str,
        capability_report_digest: str,
        bound_local_state_lineage_id: str,
        availability_state: EvidenceState,
        availability_evidence_ref: str | None,
        typed_request_result_transport: bool,
        canonical_state_authority: bool = False,
        truth_authority: bool = False,
        effect_authority: bool = False,
    ) -> "RemoteEndpointEvidence":
        endpoint_id = _require_nonempty(endpoint_id, "ENDPOINT_ID")
        transport = _require_nonempty(transport, "TRANSPORT")
        environment_digest = _require_sha256(environment_digest, "ENVIRONMENT_DIGEST")
        capability_report_digest = _require_sha256(
            capability_report_digest, "CAPABILITY_REPORT_DIGEST"
        )
        bound_local_state_lineage_id = _require_nonempty(
            bound_local_state_lineage_id, "BOUND_LOCAL_STATE_LINEAGE_ID"
        )
        if availability_state is EvidenceState.VERIFIED:
            if availability_evidence_ref is None or not availability_evidence_ref.strip():
                raise BridgeValidationError("VERIFIED_REMOTE_AVAILABILITY_WITHOUT_EVIDENCE")
        if canonical_state_authority or truth_authority or effect_authority:
            raise BridgeValidationError("REMOTE_ENDPOINT_ATTEMPTS_SECOND_AUTHORITY")
        return cls(
            schema=REMOTE_ENDPOINT_SCHEMA,
            endpoint_id=endpoint_id,
            transport=transport,
            environment_digest=environment_digest,
            capability_report_digest=capability_report_digest,
            bound_local_state_lineage_id=bound_local_state_lineage_id,
            availability_state=availability_state,
            availability_evidence_ref=(
                availability_evidence_ref.strip()
                if availability_evidence_ref and availability_evidence_ref.strip()
                else None
            ),
            typed_request_result_transport=bool(typed_request_result_transport),
            canonical_state_authority=False,
            truth_authority=False,
            effect_authority=False,
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["availability_state"] = self.availability_state.value
        return data

    def identity_digest(self) -> str:
        return _sha256_json(self.to_dict())


@dataclass(frozen=True)
class OptionalBridgePlan:
    schema: str
    action: BridgeAction
    disposition: BridgeDisposition
    local_runtime_digest: str
    remote_endpoint_digest: str | None
    state_lineage_id: str
    state_generation: int
    baseline_local_boot_independent: bool
    remote_optional: bool
    typed_request_result_transport: bool
    blockers: tuple[str, ...]
    limitations: tuple[str, ...]
    canonical_state_authority: str
    truth_authority: str
    effect_authority: str
    target_runtime_credit: int = 0
    whole_system_acceptance: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["action"] = self.action.value
        data["disposition"] = self.disposition.value
        return data

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    def plan_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def plan_optional_bridge(
    *,
    local: LocalRuntimeIdentity,
    action: BridgeAction,
    remote: RemoteEndpointEvidence | None = None,
) -> OptionalBridgePlan:
    """Produce a deterministic non-executing attach/detach plan.

    ATTACH requires verified baseline-local boot *without* the remote bridge, verified
    endpoint availability, typed request/result transport, and exact local-state-lineage
    binding. DETACH never requires remote availability and always preserves the local
    state lineage; it therefore remains admissible even when a previously known remote
    endpoint is unavailable or absent.
    """

    local_digest = local.identity_digest()
    blockers: list[str] = []
    limitations: list[str] = []

    baseline_independent = local.baseline_boot_state is EvidenceState.VERIFIED
    if not baseline_independent:
        blockers.append("BASELINE_LOCAL_BOOT_NOT_VERIFIED_INDEPENDENTLY")

    remote_digest: str | None = None
    typed_transport = False

    if action is BridgeAction.ATTACH:
        if remote is None:
            blockers.append("REMOTE_ENDPOINT_EVIDENCE_MISSING")
        else:
            remote_digest = remote.identity_digest()
            typed_transport = remote.typed_request_result_transport
            if remote.bound_local_state_lineage_id != local.state_lineage_id:
                blockers.append("REMOTE_STATE_LINEAGE_BINDING_MISMATCH")
            if remote.availability_state is not EvidenceState.VERIFIED:
                blockers.append("REMOTE_AVAILABILITY_NOT_VERIFIED")
            if not remote.typed_request_result_transport:
                blockers.append("REMOTE_TRANSPORT_NOT_TYPED_REQUEST_RESULT")
        disposition = BridgeDisposition.BLOCKED if blockers else BridgeDisposition.ATTACHED
    elif action is BridgeAction.DETACH:
        if remote is not None:
            remote_digest = remote.identity_digest()
            typed_transport = remote.typed_request_result_transport
            if remote.bound_local_state_lineage_id != local.state_lineage_id:
                limitations.append("DETACH_IGNORES_MISMATCHED_REMOTE_LINEAGE_AND_PRESERVES_LOCAL")
        disposition = BridgeDisposition.BLOCKED if blockers else BridgeDisposition.DETACHED
    else:  # defensive for non-enum callers
        raise BridgeValidationError("UNKNOWN_BRIDGE_ACTION")

    limitations.extend(
        [
            "REMOTE_OUTPUT_IS_CANDIDATE_OR_PROJECTION_ONLY",
            "NO_REMOTE_TRUTH_OR_EFFECT_COMPLETION_AUTHORITY",
            "REPOSITORY_PLAN_IS_NOT_PHYSICAL_BRIDGE_RUNTIME_EVIDENCE",
        ]
    )

    return OptionalBridgePlan(
        schema=BRIDGE_PLAN_SCHEMA,
        action=action,
        disposition=disposition,
        local_runtime_digest=local_digest,
        remote_endpoint_digest=remote_digest,
        state_lineage_id=local.state_lineage_id,
        state_generation=local.state_generation,
        baseline_local_boot_independent=baseline_independent,
        remote_optional=True,
        typed_request_result_transport=typed_transport,
        blockers=tuple(sorted(set(blockers))),
        limitations=tuple(sorted(set(limitations))),
        canonical_state_authority="LOCAL_CANONICAL_STATE_LINEAGE_ONLY",
        truth_authority="LOCAL_DETERMINISTIC_ADMISSION_ONLY",
        effect_authority="LOCAL_EFFECT_GATE_AND_JOURNAL_ONLY",
        target_runtime_credit=0,
        whole_system_acceptance=False,
    )


def validate_remote_return(
    *,
    plan: OptionalBridgePlan,
    returned_state_lineage_id: str,
    request_digest: str,
    result_digest: str,
) -> dict:
    """Validate identity binding of a remote return without minting world/effect truth."""
    if plan.disposition is not BridgeDisposition.ATTACHED:
        raise BridgeValidationError("REMOTE_RETURN_WITHOUT_ATTACHED_PLAN")
    returned_state_lineage_id = _require_nonempty(
        returned_state_lineage_id, "RETURNED_STATE_LINEAGE_ID"
    )
    if returned_state_lineage_id != plan.state_lineage_id:
        raise BridgeValidationError("REMOTE_RETURN_STATE_LINEAGE_MISMATCH")
    request_digest = _require_sha256(request_digest, "REQUEST_DIGEST")
    result_digest = _require_sha256(result_digest, "RESULT_DIGEST")
    return {
        "schema": "FRANKENSTEIN2_OPTIONAL_REMOTE_RETURN_VALIDATION/v1",
        "bridge_plan_digest": plan.plan_digest(),
        "state_lineage_id": plan.state_lineage_id,
        "request_digest": request_digest,
        "result_digest": result_digest,
        "identity_binding_valid": True,
        "candidate_or_projection_only": True,
        "canonical_truth_credit": 0,
        "effect_completion_credit": 0,
        "target_runtime_credit": 0,
        "whole_system_acceptance": False,
    }
