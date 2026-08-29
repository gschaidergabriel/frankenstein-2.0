from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence

CLEAN_MACHINE_MATRIX_SCHEMA = "FRANKENSTEIN2_CLEAN_MACHINE_ACCEPTANCE_MATRIX/v1"
REAL_HOST_EVIDENCE_SCOPE = "REAL_CLEAN_MACHINE_OBSERVATION"

BASE_CASE_IDS = (
    "claude_code",
    "codex_cli",
    "other_agent",
    "no_vps_baseline",
    "vps_bridge",
)
PERCEPTION_CASE_ID = "perception_enabled"

ROUTE_RESULTS = frozenset({"NATIVE", "ADAPTED", "DEGRADED", "BLOCKED", "ACCEPTED"})


class CleanMachineAcceptanceError(ValueError):
    """Typed clean-machine acceptance evidence violates a fail-closed invariant."""


def _require_nonempty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CleanMachineAcceptanceError(f"{field_name} must be a non-empty string")
    return value


def _require_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise CleanMachineAcceptanceError(
            f"{field_name} must be a 64-character SHA-256 hex digest"
        )
    try:
        int(value, 16)
    except ValueError as exc:
        raise CleanMachineAcceptanceError(f"{field_name} must be hexadecimal") from exc
    return value.lower()


def _require_bool(value: bool, field_name: str) -> bool:
    if type(value) is not bool:
        raise CleanMachineAcceptanceError(f"{field_name} must be boolean")
    return value


def _canonical_string_tuple(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    items = tuple(values)
    for item in items:
        _require_nonempty(item, field_name)
    if tuple(sorted(items)) != items or len(set(items)) != len(items):
        raise CleanMachineAcceptanceError(f"{field_name} must be unique and sorted")
    return items


@dataclass(frozen=True)
class AcceptanceObservation:
    case_id: str
    environment_id: str
    release_manifest_sha256: str
    prehandoff_receipt_ref: str
    route_result: str
    evidence_scope: str
    observed_at: str
    evidence_refs: tuple[str, ...]
    lifecycle_firing_observed: bool
    durable_state_readback_observed: bool
    restart_recovery_observed: bool
    reinstall_update_persistence_observed: bool
    uninstall_disable_observed: bool
    baseline_local_boot_observed: bool
    single_state_lineage_verified: bool
    vps_configured: bool
    vps_bridge_attach_observed: bool
    vps_bridge_detach_observed: bool
    remote_second_state_authority_observed: bool
    perception_enabled: bool
    perception_binding_observed: bool
    perception_permission_revocation_observed: bool
    limitations: tuple[str, ...] = ()
    adapted_route_evidence_ref: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.case_id, "case_id")
        _require_nonempty(self.environment_id, "environment_id")
        object.__setattr__(
            self,
            "release_manifest_sha256",
            _require_sha256(self.release_manifest_sha256, "release_manifest_sha256"),
        )
        _require_nonempty(self.prehandoff_receipt_ref, "prehandoff_receipt_ref")
        if self.route_result not in ROUTE_RESULTS:
            raise CleanMachineAcceptanceError(
                f"unsupported route_result: {self.route_result!r}"
            )
        _require_nonempty(self.evidence_scope, "evidence_scope")
        _require_nonempty(self.observed_at, "observed_at")
        object.__setattr__(
            self,
            "evidence_refs",
            _canonical_string_tuple(self.evidence_refs, "evidence_refs"),
        )
        if not self.evidence_refs:
            raise CleanMachineAcceptanceError("evidence_refs must not be empty")
        object.__setattr__(
            self,
            "limitations",
            _canonical_string_tuple(self.limitations, "limitations"),
        )
        if self.adapted_route_evidence_ref is not None:
            _require_nonempty(
                self.adapted_route_evidence_ref, "adapted_route_evidence_ref"
            )
        for field_name in (
            "lifecycle_firing_observed",
            "durable_state_readback_observed",
            "restart_recovery_observed",
            "reinstall_update_persistence_observed",
            "uninstall_disable_observed",
            "baseline_local_boot_observed",
            "single_state_lineage_verified",
            "vps_configured",
            "vps_bridge_attach_observed",
            "vps_bridge_detach_observed",
            "remote_second_state_authority_observed",
            "perception_enabled",
            "perception_binding_observed",
            "perception_permission_revocation_observed",
        ):
            _require_bool(getattr(self, field_name), field_name)

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "environment_id": self.environment_id,
            "release_manifest_sha256": self.release_manifest_sha256,
            "prehandoff_receipt_ref": self.prehandoff_receipt_ref,
            "route_result": self.route_result,
            "evidence_scope": self.evidence_scope,
            "observed_at": self.observed_at,
            "evidence_refs": list(self.evidence_refs),
            "lifecycle_firing_observed": self.lifecycle_firing_observed,
            "durable_state_readback_observed": self.durable_state_readback_observed,
            "restart_recovery_observed": self.restart_recovery_observed,
            "reinstall_update_persistence_observed": self.reinstall_update_persistence_observed,
            "uninstall_disable_observed": self.uninstall_disable_observed,
            "baseline_local_boot_observed": self.baseline_local_boot_observed,
            "single_state_lineage_verified": self.single_state_lineage_verified,
            "vps_configured": self.vps_configured,
            "vps_bridge_attach_observed": self.vps_bridge_attach_observed,
            "vps_bridge_detach_observed": self.vps_bridge_detach_observed,
            "remote_second_state_authority_observed": self.remote_second_state_authority_observed,
            "perception_enabled": self.perception_enabled,
            "perception_binding_observed": self.perception_binding_observed,
            "perception_permission_revocation_observed": self.perception_permission_revocation_observed,
            "limitations": list(self.limitations),
            "adapted_route_evidence_ref": self.adapted_route_evidence_ref,
        }

    def canonical_bytes(self) -> bytes:
        return (
            json.dumps(
                self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            + "\n"
        ).encode("utf-8")

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class CleanMachineMatrixResult:
    release_manifest_sha256: str
    prehandoff_receipt_ref: str
    perception_required: bool
    required_case_ids: tuple[str, ...]
    observed_case_ids: tuple[str, ...]
    violations: tuple[str, ...]
    status: str
    evidence_scope: str = "CALLER_SUPPLIED_REAL_HOST_EVIDENCE_VALIDATION_ONLY"
    runtime_credit: int = 0
    physical_host_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False
    schema: str = CLEAN_MACHINE_MATRIX_SCHEMA

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "release_manifest_sha256": self.release_manifest_sha256,
            "prehandoff_receipt_ref": self.prehandoff_receipt_ref,
            "perception_required": self.perception_required,
            "required_case_ids": list(self.required_case_ids),
            "observed_case_ids": list(self.observed_case_ids),
            "violations": list(self.violations),
            "status": self.status,
            "evidence_scope": self.evidence_scope,
            "runtime_credit": self.runtime_credit,
            "physical_host_credit": self.physical_host_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def canonical_bytes(self) -> bytes:
        return (
            json.dumps(
                self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            + "\n"
        ).encode("utf-8")

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def required_case_ids(*, perception_required: bool) -> tuple[str, ...]:
    _require_bool(perception_required, "perception_required")
    if perception_required:
        return BASE_CASE_IDS + (PERCEPTION_CASE_ID,)
    return BASE_CASE_IDS


def _require_observed(
    observation: AcceptanceObservation,
    attribute: str,
    violations: list[str],
) -> None:
    if not getattr(observation, attribute):
        violations.append(f"{observation.case_id}:{attribute}=false")


def _evaluate_host_route(
    observation: AcceptanceObservation,
    violations: list[str],
) -> None:
    for attribute in (
        "lifecycle_firing_observed",
        "durable_state_readback_observed",
        "restart_recovery_observed",
        "reinstall_update_persistence_observed",
        "uninstall_disable_observed",
        "baseline_local_boot_observed",
        "single_state_lineage_verified",
    ):
        _require_observed(observation, attribute, violations)

    if observation.case_id == "claude_code":
        if observation.route_result not in {"NATIVE", "ADAPTED"}:
            violations.append(
                "claude_code:route_result must be NATIVE or evidenced ADAPTED"
            )
        if (
            observation.route_result == "ADAPTED"
            and observation.adapted_route_evidence_ref is None
        ):
            violations.append("claude_code:ADAPTED requires adapted_route_evidence_ref")
    elif observation.case_id == "codex_cli":
        if observation.route_result not in {"NATIVE", "ADAPTED"}:
            violations.append("codex_cli:route_result must be NATIVE or ADAPTED")
        if (
            observation.route_result == "ADAPTED"
            and observation.adapted_route_evidence_ref is None
        ):
            violations.append("codex_cli:ADAPTED requires adapted_route_evidence_ref")
    elif observation.case_id == "other_agent":
        if observation.route_result not in {"ADAPTED", "DEGRADED", "BLOCKED"}:
            violations.append(
                "other_agent:route_result must be ADAPTED, DEGRADED or BLOCKED"
            )
        if observation.route_result in {"DEGRADED", "BLOCKED"} and not observation.limitations:
            violations.append("other_agent:DEGRADED/BLOCKED requires precise limitations")


def _evaluate_case(
    observation: AcceptanceObservation,
    violations: list[str],
) -> None:
    if observation.evidence_scope != REAL_HOST_EVIDENCE_SCOPE:
        violations.append(
            f"{observation.case_id}:evidence_scope must be {REAL_HOST_EVIDENCE_SCOPE}"
        )

    if observation.remote_second_state_authority_observed:
        violations.append(
            f"{observation.case_id}:remote_second_state_authority_observed=true"
        )

    if observation.case_id in {"claude_code", "codex_cli", "other_agent"}:
        _evaluate_host_route(observation, violations)
        return

    if observation.case_id == "no_vps_baseline":
        if observation.route_result != "ACCEPTED":
            violations.append("no_vps_baseline:route_result must be ACCEPTED")
        if observation.vps_configured:
            violations.append("no_vps_baseline:vps_configured must be false")
        if observation.vps_bridge_attach_observed:
            violations.append(
                "no_vps_baseline:vps_bridge_attach_observed must be false"
            )
        for attribute in (
            "baseline_local_boot_observed",
            "durable_state_readback_observed",
            "restart_recovery_observed",
            "reinstall_update_persistence_observed",
            "uninstall_disable_observed",
            "single_state_lineage_verified",
        ):
            _require_observed(observation, attribute, violations)
        return

    if observation.case_id == "vps_bridge":
        if observation.route_result != "ACCEPTED":
            violations.append("vps_bridge:route_result must be ACCEPTED")
        for attribute in (
            "vps_configured",
            "baseline_local_boot_observed",
            "durable_state_readback_observed",
            "single_state_lineage_verified",
            "vps_bridge_attach_observed",
            "vps_bridge_detach_observed",
        ):
            _require_observed(observation, attribute, violations)
        return

    if observation.case_id == PERCEPTION_CASE_ID:
        if observation.route_result != "ACCEPTED":
            violations.append("perception_enabled:route_result must be ACCEPTED")
        for attribute in (
            "perception_enabled",
            "perception_binding_observed",
            "perception_permission_revocation_observed",
            "single_state_lineage_verified",
        ):
            _require_observed(observation, attribute, violations)
        return

    raise CleanMachineAcceptanceError(
        f"unknown clean-machine acceptance case: {observation.case_id!r}"
    )


def evaluate_clean_machine_acceptance(
    observations: Sequence[AcceptanceObservation],
    *,
    release_manifest_sha256: str,
    prehandoff_receipt_ref: str,
    perception_required: bool = False,
) -> CleanMachineMatrixResult:
    manifest_sha = _require_sha256(release_manifest_sha256, "release_manifest_sha256")
    receipt_ref = _require_nonempty(prehandoff_receipt_ref, "prehandoff_receipt_ref")
    expected = required_case_ids(perception_required=perception_required)

    by_case: dict[str, AcceptanceObservation] = {}
    for observation in observations:
        if not isinstance(observation, AcceptanceObservation):
            raise CleanMachineAcceptanceError(
                "observations must contain AcceptanceObservation values"
            )
        if observation.case_id in by_case:
            raise CleanMachineAcceptanceError(
                f"duplicate clean-machine case: {observation.case_id}"
            )
        by_case[observation.case_id] = observation

    unknown = sorted(set(by_case) - set(expected))
    if unknown:
        raise CleanMachineAcceptanceError(f"unexpected clean-machine cases: {unknown}")

    violations: list[str] = []
    missing = sorted(set(expected) - set(by_case))
    for case_id in missing:
        violations.append(f"{case_id}:missing")

    environment_ids: set[str] = set()
    for case_id in sorted(by_case):
        observation = by_case[case_id]
        environment_ids.add(observation.environment_id)
        if observation.release_manifest_sha256 != manifest_sha:
            violations.append(f"{case_id}:release_manifest_sha256 mismatch")
        if observation.prehandoff_receipt_ref != receipt_ref:
            violations.append(f"{case_id}:prehandoff_receipt_ref mismatch")
        _evaluate_case(observation, violations)

    if len(environment_ids) != len(by_case):
        violations.append("environment_id must be unique per clean-machine case")

    ordered_violations = tuple(sorted(set(violations)))
    status = "READY_FOR_ADMISSION_REVIEW" if not ordered_violations else "BLOCKED"

    return CleanMachineMatrixResult(
        release_manifest_sha256=manifest_sha,
        prehandoff_receipt_ref=receipt_ref,
        perception_required=perception_required,
        required_case_ids=expected,
        observed_case_ids=tuple(sorted(by_case)),
        violations=ordered_violations,
        status=status,
    )
