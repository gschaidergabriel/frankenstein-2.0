"""Generation-2 clean-machine admission binds every observation to the exact release ZIP.

This module composes the accepted generation-1 clean-machine matrix with the generation-2
external artifact-bound pre-handoff receipt. The old validator remains available for its
historical declared scope; this successor is the path that can satisfy WP1110's exact final
artifact evidence requirement.

ARTIFACT_BOUND_READY_FOR_REVIEW != RUNTIME_ACCEPTED != WHOLE_SYSTEM_COMPLETE
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Sequence

from .clean_machine_acceptance import (
    AcceptanceObservation,
    CleanMachineMatrixResult,
    evaluate_clean_machine_acceptance,
)
from .pre_handoff_release import READY_STATUS
from .release_artifact_subject import ArtifactBoundPreHandoffReceipt

ARTIFACT_BOUND_MATRIX_SCHEMA = "FRANKENSTEIN2_ARTIFACT_BOUND_CLEAN_MACHINE_MATRIX/v1"
ARTIFACT_BOUND_OBSERVATION_SCHEMA = "FRANKENSTEIN2_ARTIFACT_BOUND_CLEAN_MACHINE_OBSERVATION/v1"
ARTIFACT_BOUND_MATRIX_SCOPE = (
    "CALLER_SUPPLIED_REAL_HOST_EVIDENCE_BOUND_TO_EXACT_RELEASE_ARTIFACT_VALIDATION_ONLY"
)


class ArtifactBoundCleanMachineError(ValueError):
    """Artifact-bound clean-machine evidence violates a fail-closed invariant."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ArtifactBoundCleanMachineError(f"{name} must be a non-empty already-trimmed string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ArtifactBoundCleanMachineError(f"{name} contains control characters")
    return value


def _sha256(value: Any, name: str) -> str:
    text = _text(value, name)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ArtifactBoundCleanMachineError(f"{name} must be lowercase 64-hex SHA-256")
    return text


def _size(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ArtifactBoundCleanMachineError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class ArtifactBoundAcceptanceObservation:
    observation: AcceptanceObservation
    artifact_filename: str
    artifact_sha256: str
    artifact_size_bytes: int
    artifact_subject_sha256: str
    schema: str = ARTIFACT_BOUND_OBSERVATION_SCHEMA

    def __post_init__(self) -> None:
        if not isinstance(self.observation, AcceptanceObservation):
            raise ArtifactBoundCleanMachineError("observation must be AcceptanceObservation")
        _text(self.artifact_filename, "artifact_filename")
        _sha256(self.artifact_sha256, "artifact_sha256")
        _size(self.artifact_size_bytes, "artifact_size_bytes")
        _sha256(self.artifact_subject_sha256, "artifact_subject_sha256")
        if self.schema != ARTIFACT_BOUND_OBSERVATION_SCHEMA:
            raise ArtifactBoundCleanMachineError("artifact-bound observation schema mismatch")

    @property
    def case_id(self) -> str:
        return self.observation.case_id

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "artifact_filename": self.artifact_filename,
            "artifact_sha256": self.artifact_sha256,
            "artifact_size_bytes": self.artifact_size_bytes,
            "artifact_subject_sha256": self.artifact_subject_sha256,
            "observation": self.observation.as_dict(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class ArtifactBoundCleanMachineMatrixResult:
    artifact_filename: str
    artifact_sha256: str
    artifact_size_bytes: int
    artifact_subject_sha256: str
    release_manifest_sha256: str
    prehandoff_receipt_ref: str
    artifact_bound_prehandoff_sha256: str
    base_matrix_sha256: str
    required_case_ids: tuple[str, ...]
    observed_case_ids: tuple[str, ...]
    violations: tuple[str, ...]
    status: str
    evidence_scope: str = ARTIFACT_BOUND_MATRIX_SCOPE
    runtime_credit: int = 0
    physical_host_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False
    schema: str = ARTIFACT_BOUND_MATRIX_SCHEMA

    def __post_init__(self) -> None:
        _text(self.artifact_filename, "artifact_filename")
        _sha256(self.artifact_sha256, "artifact_sha256")
        _size(self.artifact_size_bytes, "artifact_size_bytes")
        _sha256(self.artifact_subject_sha256, "artifact_subject_sha256")
        _sha256(self.release_manifest_sha256, "release_manifest_sha256")
        _text(self.prehandoff_receipt_ref, "prehandoff_receipt_ref")
        _sha256(self.artifact_bound_prehandoff_sha256, "artifact_bound_prehandoff_sha256")
        _sha256(self.base_matrix_sha256, "base_matrix_sha256")
        if tuple(sorted(set(self.violations))) != self.violations:
            raise ArtifactBoundCleanMachineError("violations must be unique and sorted")
        if self.schema != ARTIFACT_BOUND_MATRIX_SCHEMA:
            raise ArtifactBoundCleanMachineError("artifact-bound matrix schema mismatch")
        if self.evidence_scope != ARTIFACT_BOUND_MATRIX_SCOPE:
            raise ArtifactBoundCleanMachineError("artifact-bound matrix evidence scope mismatch")
        if any(
            value != 0
            for value in (
                self.runtime_credit,
                self.physical_host_credit,
                self.completion_credit,
            )
        ) or self.whole_system_acceptance:
            raise ArtifactBoundCleanMachineError("artifact-bound matrix cannot mint higher-scope credit")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "artifact_filename": self.artifact_filename,
            "artifact_sha256": self.artifact_sha256,
            "artifact_size_bytes": self.artifact_size_bytes,
            "artifact_subject_sha256": self.artifact_subject_sha256,
            "release_manifest_sha256": self.release_manifest_sha256,
            "prehandoff_receipt_ref": self.prehandoff_receipt_ref,
            "artifact_bound_prehandoff_sha256": self.artifact_bound_prehandoff_sha256,
            "base_matrix_sha256": self.base_matrix_sha256,
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
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def evaluate_artifact_bound_clean_machine_acceptance(
    observations: Sequence[ArtifactBoundAcceptanceObservation],
    *,
    artifact_bound_prehandoff: ArtifactBoundPreHandoffReceipt,
    perception_required: bool = False,
) -> ArtifactBoundCleanMachineMatrixResult:
    """Validate real-host rows only when every row names the same exact unopened ZIP."""

    if not isinstance(artifact_bound_prehandoff, ArtifactBoundPreHandoffReceipt):
        raise ArtifactBoundCleanMachineError(
            "artifact_bound_prehandoff must be ArtifactBoundPreHandoffReceipt"
        )

    subject = artifact_bound_prehandoff.subject
    subject_sha = subject.sha256()
    violations: list[str] = []
    if artifact_bound_prehandoff.status != READY_STATUS:
        violations.append("artifact_bound_prehandoff:not_ready")

    inner: list[AcceptanceObservation] = []
    seen_cases: set[str] = set()
    for wrapped in observations:
        if not isinstance(wrapped, ArtifactBoundAcceptanceObservation):
            raise ArtifactBoundCleanMachineError(
                "observations must contain ArtifactBoundAcceptanceObservation values"
            )
        if wrapped.case_id in seen_cases:
            raise ArtifactBoundCleanMachineError(
                f"duplicate artifact-bound clean-machine case: {wrapped.case_id}"
            )
        seen_cases.add(wrapped.case_id)
        if wrapped.artifact_filename != subject.artifact_filename:
            violations.append(f"{wrapped.case_id}:artifact_filename mismatch")
        if wrapped.artifact_sha256 != subject.artifact_sha256:
            violations.append(f"{wrapped.case_id}:artifact_sha256 mismatch")
        if wrapped.artifact_size_bytes != subject.artifact_size_bytes:
            violations.append(f"{wrapped.case_id}:artifact_size_bytes mismatch")
        if wrapped.artifact_subject_sha256 != subject_sha:
            violations.append(f"{wrapped.case_id}:artifact_subject_sha256 mismatch")
        inner.append(wrapped.observation)

    base: CleanMachineMatrixResult = evaluate_clean_machine_acceptance(
        inner,
        release_manifest_sha256=subject.release_manifest_sha256,
        prehandoff_receipt_ref=artifact_bound_prehandoff.prehandoff_receipt_ref,
        perception_required=perception_required,
    )
    violations.extend(base.violations)
    ordered = tuple(sorted(set(violations)))
    status = "READY_FOR_ADMISSION_REVIEW" if not ordered else "BLOCKED"

    return ArtifactBoundCleanMachineMatrixResult(
        artifact_filename=subject.artifact_filename,
        artifact_sha256=subject.artifact_sha256,
        artifact_size_bytes=subject.artifact_size_bytes,
        artifact_subject_sha256=subject_sha,
        release_manifest_sha256=subject.release_manifest_sha256,
        prehandoff_receipt_ref=artifact_bound_prehandoff.prehandoff_receipt_ref,
        artifact_bound_prehandoff_sha256=artifact_bound_prehandoff.sha256(),
        base_matrix_sha256=base.sha256(),
        required_case_ids=base.required_case_ids,
        observed_case_ids=base.observed_case_ids,
        violations=ordered,
        status=status,
    )
