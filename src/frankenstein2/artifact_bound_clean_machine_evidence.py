"""Fail-closed ingestion for externally observed clean-machine evidence.

This module does not observe a host, execute an effect, or mint runtime credit. It only
turns caller-supplied JSON-shaped evidence into the already accepted artifact-bound
clean-machine validator *after* independently re-hashing the exact unopened release ZIP.

The intended handoff is:

    exact release ZIP + artifact-bound prehandoff receipt + real-host observations
      -> exact byte/size/name check
      -> typed observation reconstruction
      -> existing artifact-bound clean-machine matrix validator
      -> bounded review result (all higher-scope credits remain zero)

This closes a transport/ingestion gap without creating a second runtime, state, release,
or effect authority.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path
from typing import Any

from .artifact_bound_clean_machine import (
    ArtifactBoundAcceptanceObservation,
    ArtifactBoundCleanMachineMatrixResult,
    evaluate_artifact_bound_clean_machine_acceptance,
)
from .clean_machine_acceptance import AcceptanceObservation
from .release_artifact_subject import (
    ArtifactBoundPreHandoffReceipt,
    ReleaseArtifactSubject,
)


class ArtifactBoundEvidenceIngestError(ValueError):
    """External evidence cannot be safely bound to the exact release artifact."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ArtifactBoundEvidenceIngestError(f"{name} must be an object")
    return value


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ArtifactBoundEvidenceIngestError(f"{name} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ArtifactBoundEvidenceIngestError(
            f"{name} keys mismatch: missing={missing} extra={extra}"
        )


def artifact_bound_prehandoff_from_dict(value: Mapping[str, Any]) -> ArtifactBoundPreHandoffReceipt:
    """Reconstruct the canonical typed prehandoff receipt without weakening its checks."""
    record = _mapping(value, "prehandoff")
    expected = {
        "schema",
        "artifact_subject",
        "prehandoff_receipt_ref",
        "static_prehandoff_sha256",
        "static_status",
        "static_violations",
        "status",
        "evidence_scope",
        "runtime_credit",
        "physical_host_credit",
        "effect_credit",
        "completion_credit",
        "whole_system_acceptance",
    }
    _exact_keys(record, expected, "prehandoff")

    subject_record = _mapping(record["artifact_subject"], "artifact_subject")
    subject_expected = {
        "schema",
        "artifact_filename",
        "artifact_sha256",
        "artifact_size_bytes",
        "release_manifest_sha256",
        "source_commit",
        "source_tree",
        "release_id",
        "build_id",
        "archive_policy_id",
        "archive_policy_sha256",
        "member_count",
    }
    _exact_keys(subject_record, subject_expected, "artifact_subject")
    try:
        subject = ReleaseArtifactSubject(**dict(subject_record))
        static_violations = tuple(_sequence(record["static_violations"], "static_violations"))
        return ArtifactBoundPreHandoffReceipt(
            subject=subject,
            prehandoff_receipt_ref=record["prehandoff_receipt_ref"],
            static_prehandoff_sha256=record["static_prehandoff_sha256"],
            static_status=record["static_status"],
            static_violations=static_violations,
            status=record["status"],
            evidence_scope=record["evidence_scope"],
            runtime_credit=record["runtime_credit"],
            physical_host_credit=record["physical_host_credit"],
            effect_credit=record["effect_credit"],
            completion_credit=record["completion_credit"],
            whole_system_acceptance=record["whole_system_acceptance"],
            schema=record["schema"],
        )
    except (TypeError, ValueError) as exc:
        raise ArtifactBoundEvidenceIngestError("invalid artifact-bound prehandoff receipt") from exc


def artifact_bound_observation_from_dict(value: Mapping[str, Any]) -> ArtifactBoundAcceptanceObservation:
    """Reconstruct one real-host observation while preserving its declared artifact identity."""
    record = _mapping(value, "artifact_bound_observation")
    expected = {
        "schema",
        "artifact_filename",
        "artifact_sha256",
        "artifact_size_bytes",
        "artifact_subject_sha256",
        "observation",
    }
    _exact_keys(record, expected, "artifact_bound_observation")

    observation_record = _mapping(record["observation"], "observation")
    observation_expected = {
        "case_id",
        "environment_id",
        "release_manifest_sha256",
        "prehandoff_receipt_ref",
        "route_result",
        "evidence_scope",
        "observed_at",
        "evidence_refs",
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
        "limitations",
        "adapted_route_evidence_ref",
    }
    _exact_keys(observation_record, observation_expected, "observation")
    typed_observation = dict(observation_record)
    typed_observation["evidence_refs"] = tuple(
        _sequence(observation_record["evidence_refs"], "evidence_refs")
    )
    typed_observation["limitations"] = tuple(
        _sequence(observation_record["limitations"], "limitations")
    )
    try:
        observation = AcceptanceObservation(**typed_observation)
        return ArtifactBoundAcceptanceObservation(
            observation=observation,
            artifact_filename=record["artifact_filename"],
            artifact_sha256=record["artifact_sha256"],
            artifact_size_bytes=record["artifact_size_bytes"],
            artifact_subject_sha256=record["artifact_subject_sha256"],
            schema=record["schema"],
        )
    except (TypeError, ValueError) as exc:
        raise ArtifactBoundEvidenceIngestError("invalid artifact-bound clean-machine observation") from exc


def _verify_exact_unopened_artifact(
    artifact_path: str | Path,
    prehandoff: ArtifactBoundPreHandoffReceipt,
) -> Path:
    path = Path(artifact_path)
    if path.is_symlink():
        raise ArtifactBoundEvidenceIngestError("artifact_path must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ArtifactBoundEvidenceIngestError("artifact_path does not resolve") from exc
    if not resolved.is_file():
        raise ArtifactBoundEvidenceIngestError("artifact_path must resolve to a regular file")

    data = resolved.read_bytes()
    subject = prehandoff.subject
    observed_sha256 = hashlib.sha256(data).hexdigest()
    if resolved.name != subject.artifact_filename:
        raise ArtifactBoundEvidenceIngestError("artifact filename does not match prehandoff subject")
    if len(data) != subject.artifact_size_bytes:
        raise ArtifactBoundEvidenceIngestError("artifact size does not match prehandoff subject")
    if observed_sha256 != subject.artifact_sha256:
        raise ArtifactBoundEvidenceIngestError("artifact SHA-256 does not match prehandoff subject")
    return resolved


def evaluate_artifact_bound_clean_machine_evidence(
    *,
    artifact_path: str | Path,
    prehandoff_record: Mapping[str, Any],
    observation_records: Sequence[Mapping[str, Any]],
    perception_required: bool = False,
) -> ArtifactBoundCleanMachineMatrixResult:
    """Validate external observations against the exact unopened release artifact.

    No observation fields are synthesized from the prehandoff subject. Each external row
    must carry its own artifact binding, and the existing matrix validator compares those
    values to the independently reconstructed receipt after this function re-hashes the
    actual ZIP bytes.
    """
    prehandoff = artifact_bound_prehandoff_from_dict(prehandoff_record)
    _verify_exact_unopened_artifact(artifact_path, prehandoff)
    records = _sequence(observation_records, "observations")
    observations = tuple(
        artifact_bound_observation_from_dict(_mapping(item, "observation item"))
        for item in records
    )
    return evaluate_artifact_bound_clean_machine_acceptance(
        observations,
        artifact_bound_prehandoff=prehandoff,
        perception_required=perception_required,
    )


__all__ = [
    "ArtifactBoundEvidenceIngestError",
    "artifact_bound_observation_from_dict",
    "artifact_bound_prehandoff_from_dict",
    "evaluate_artifact_bound_clean_machine_evidence",
]
