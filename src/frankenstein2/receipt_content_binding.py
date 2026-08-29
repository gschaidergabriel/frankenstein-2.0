"""WP1110 generation-3 immutable pre-handoff receipt content binding.

This successor composes the accepted generation-2 exact release-artifact subject path.
It does not change the historical generation-1 clean-machine ABI and does not mint a
second ZIP, manifest, or runtime authority.

A textual ``prehandoff_receipt_ref`` is insufficient when the referenced object could
be replaced. This module therefore binds the exact canonical bytes of the generation-2
``ArtifactBoundPreHandoffReceipt`` and requires every successor clean-machine
observation to carry that same immutable receipt-content subject.

RECEIPT_CONTENT_BOUND_READY_FOR_REVIEW != RUNTIME_ACCEPTED != WHOLE_SYSTEM_COMPLETE
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Sequence

from .artifact_bound_clean_machine import (
    ArtifactBoundAcceptanceObservation,
    ArtifactBoundCleanMachineMatrixResult,
    evaluate_artifact_bound_clean_machine_acceptance,
)
from .pre_handoff_release import BLOCKED_STATUS, READY_STATUS
from .release_artifact_subject import ArtifactBoundPreHandoffReceipt

RECEIPT_CONTENT_SUBJECT_SCHEMA = "FRANKENSTEIN2_PREHANDOFF_RECEIPT_CONTENT_SUBJECT/v1"
CONTENT_BOUND_PREHANDOFF_SCHEMA = "FRANKENSTEIN2_CONTENT_BOUND_PREHANDOFF_RECEIPT/v1"
CONTENT_BOUND_OBSERVATION_SCHEMA = (
    "FRANKENSTEIN2_RECEIPT_CONTENT_BOUND_CLEAN_MACHINE_OBSERVATION/v1"
)
CONTENT_BOUND_MATRIX_SCHEMA = (
    "FRANKENSTEIN2_RECEIPT_CONTENT_BOUND_CLEAN_MACHINE_MATRIX/v1"
)
CONTENT_BOUND_SCOPE = (
    "EXACT_PREHANDOFF_RECEIPT_CONTENT_PLUS_ARTIFACT_BOUND_HANDOFF_ONLY_"
    "NO_RUNTIME_EFFECT_OR_COMPLETION_CREDIT"
)
CONTENT_BOUND_MATRIX_SCOPE = (
    "CALLER_SUPPLIED_REAL_HOST_EVIDENCE_BOUND_TO_EXACT_ARTIFACT_AND_"
    "PREHANDOFF_RECEIPT_CONTENT_VALIDATION_ONLY"
)


class ReceiptContentBindingError(ValueError):
    """Pre-handoff receipt content or successor observation is not exactly bound."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReceiptContentBindingError(
            f"{name} must be a non-empty already-trimmed string"
        )
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ReceiptContentBindingError(f"{name} contains control characters")
    return value


def _sha256(value: Any, name: str) -> str:
    text = _text(value, name)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ReceiptContentBindingError(f"{name} must be lowercase 64-hex SHA-256")
    return text


def _size(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReceiptContentBindingError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class PreHandoffReceiptContentSubject:
    prehandoff_receipt_ref: str
    prehandoff_receipt_sha256: str
    prehandoff_receipt_size_bytes: int
    schema: str = RECEIPT_CONTENT_SUBJECT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != RECEIPT_CONTENT_SUBJECT_SCHEMA:
            raise ReceiptContentBindingError("receipt-content subject schema mismatch")
        _text(self.prehandoff_receipt_ref, "prehandoff_receipt_ref")
        _sha256(self.prehandoff_receipt_sha256, "prehandoff_receipt_sha256")
        _size(self.prehandoff_receipt_size_bytes, "prehandoff_receipt_size_bytes")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "prehandoff_receipt_ref": self.prehandoff_receipt_ref,
            "prehandoff_receipt_sha256": self.prehandoff_receipt_sha256,
            "prehandoff_receipt_size_bytes": self.prehandoff_receipt_size_bytes,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class ContentBoundPreHandoffReceipt:
    artifact_bound_prehandoff: ArtifactBoundPreHandoffReceipt
    receipt_content_subject: PreHandoffReceiptContentSubject
    status: str
    evidence_scope: str = CONTENT_BOUND_SCOPE
    runtime_credit: int = 0
    physical_host_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False
    schema: str = CONTENT_BOUND_PREHANDOFF_SCHEMA

    def __post_init__(self) -> None:
        if not isinstance(
            self.artifact_bound_prehandoff, ArtifactBoundPreHandoffReceipt
        ):
            raise ReceiptContentBindingError(
                "artifact_bound_prehandoff must be ArtifactBoundPreHandoffReceipt"
            )
        if not isinstance(
            self.receipt_content_subject, PreHandoffReceiptContentSubject
        ):
            raise ReceiptContentBindingError(
                "receipt_content_subject must be PreHandoffReceiptContentSubject"
            )
        if self.schema != CONTENT_BOUND_PREHANDOFF_SCHEMA:
            raise ReceiptContentBindingError("content-bound prehandoff schema mismatch")
        if self.evidence_scope != CONTENT_BOUND_SCOPE:
            raise ReceiptContentBindingError("content-bound evidence scope mismatch")
        if (
            self.receipt_content_subject.prehandoff_receipt_ref
            != self.artifact_bound_prehandoff.prehandoff_receipt_ref
        ):
            raise ReceiptContentBindingError(
                "receipt-content subject ref differs from artifact-bound prehandoff ref"
            )
        expected_status = (
            READY_STATUS
            if self.artifact_bound_prehandoff.status == READY_STATUS
            else BLOCKED_STATUS
        )
        if self.status != expected_status:
            raise ReceiptContentBindingError(
                "content-bound status is inconsistent with artifact-bound prehandoff"
            )
        if any(
            value != 0
            for value in (
                self.runtime_credit,
                self.physical_host_credit,
                self.effect_credit,
                self.completion_credit,
            )
        ) or self.whole_system_acceptance:
            raise ReceiptContentBindingError(
                "content-bound prehandoff cannot mint higher-scope credit"
            )

    @property
    def prehandoff_receipt_ref(self) -> str:
        return self.receipt_content_subject.prehandoff_receipt_ref

    @property
    def prehandoff_receipt_sha256(self) -> str:
        return self.receipt_content_subject.prehandoff_receipt_sha256

    @property
    def prehandoff_receipt_size_bytes(self) -> int:
        return self.receipt_content_subject.prehandoff_receipt_size_bytes

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "artifact_bound_prehandoff_sha256": self.artifact_bound_prehandoff.sha256(),
            "artifact_subject_sha256": self.artifact_bound_prehandoff.subject.sha256(),
            "release_manifest_sha256": (
                self.artifact_bound_prehandoff.release_manifest_sha256
            ),
            "receipt_content_subject": self.receipt_content_subject.as_dict(),
            "status": self.status,
            "evidence_scope": self.evidence_scope,
            "runtime_credit": self.runtime_credit,
            "physical_host_credit": self.physical_host_credit,
            "effect_credit": self.effect_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def bind_prehandoff_receipt_content(
    artifact_bound_prehandoff: ArtifactBoundPreHandoffReceipt,
    *,
    prehandoff_receipt_ref: str,
    prehandoff_receipt_bytes: bytes,
) -> ContentBoundPreHandoffReceipt:
    """Bind exact external receipt bytes to the accepted generation-2 handoff.

    The admitted external receipt representation is the exact canonical byte sequence
    emitted by ``ArtifactBoundPreHandoffReceipt.canonical_bytes()``. A same-ref object
    with any different byte content fails closed before clean-machine evidence can use it.
    """

    if not isinstance(artifact_bound_prehandoff, ArtifactBoundPreHandoffReceipt):
        raise ReceiptContentBindingError(
            "artifact_bound_prehandoff must be ArtifactBoundPreHandoffReceipt"
        )
    receipt_ref = _text(prehandoff_receipt_ref, "prehandoff_receipt_ref")
    if receipt_ref != artifact_bound_prehandoff.prehandoff_receipt_ref:
        raise ReceiptContentBindingError(
            "prehandoff_receipt_ref differs from artifact-bound prehandoff ref"
        )
    if type(prehandoff_receipt_bytes) is not bytes or not prehandoff_receipt_bytes:
        raise ReceiptContentBindingError(
            "prehandoff_receipt_bytes must be non-empty exact bytes"
        )
    expected_bytes = artifact_bound_prehandoff.canonical_bytes()
    if prehandoff_receipt_bytes != expected_bytes:
        raise ReceiptContentBindingError(
            "external prehandoff receipt bytes differ from canonical artifact-bound receipt"
        )

    subject = PreHandoffReceiptContentSubject(
        prehandoff_receipt_ref=receipt_ref,
        prehandoff_receipt_sha256=hashlib.sha256(
            prehandoff_receipt_bytes
        ).hexdigest(),
        prehandoff_receipt_size_bytes=len(prehandoff_receipt_bytes),
    )
    status = (
        READY_STATUS
        if artifact_bound_prehandoff.status == READY_STATUS
        else BLOCKED_STATUS
    )
    return ContentBoundPreHandoffReceipt(
        artifact_bound_prehandoff=artifact_bound_prehandoff,
        receipt_content_subject=subject,
        status=status,
    )


@dataclass(frozen=True, slots=True)
class ReceiptContentBoundAcceptanceObservation:
    artifact_observation: ArtifactBoundAcceptanceObservation
    prehandoff_receipt_ref: str
    prehandoff_receipt_sha256: str
    prehandoff_receipt_size_bytes: int
    receipt_content_subject_sha256: str
    schema: str = CONTENT_BOUND_OBSERVATION_SCHEMA

    def __post_init__(self) -> None:
        if not isinstance(
            self.artifact_observation, ArtifactBoundAcceptanceObservation
        ):
            raise ReceiptContentBindingError(
                "artifact_observation must be ArtifactBoundAcceptanceObservation"
            )
        _text(self.prehandoff_receipt_ref, "prehandoff_receipt_ref")
        _sha256(self.prehandoff_receipt_sha256, "prehandoff_receipt_sha256")
        _size(self.prehandoff_receipt_size_bytes, "prehandoff_receipt_size_bytes")
        _sha256(
            self.receipt_content_subject_sha256,
            "receipt_content_subject_sha256",
        )
        if self.schema != CONTENT_BOUND_OBSERVATION_SCHEMA:
            raise ReceiptContentBindingError(
                "receipt-content-bound observation schema mismatch"
            )

    @property
    def case_id(self) -> str:
        return self.artifact_observation.case_id

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "prehandoff_receipt_ref": self.prehandoff_receipt_ref,
            "prehandoff_receipt_sha256": self.prehandoff_receipt_sha256,
            "prehandoff_receipt_size_bytes": self.prehandoff_receipt_size_bytes,
            "receipt_content_subject_sha256": self.receipt_content_subject_sha256,
            "artifact_observation": self.artifact_observation.as_dict(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class ReceiptContentBoundCleanMachineMatrixResult:
    artifact_filename: str
    artifact_sha256: str
    artifact_size_bytes: int
    artifact_subject_sha256: str
    release_manifest_sha256: str
    prehandoff_receipt_ref: str
    prehandoff_receipt_sha256: str
    prehandoff_receipt_size_bytes: int
    receipt_content_subject_sha256: str
    content_bound_prehandoff_sha256: str
    artifact_bound_matrix_sha256: str
    required_case_ids: tuple[str, ...]
    observed_case_ids: tuple[str, ...]
    violations: tuple[str, ...]
    status: str
    evidence_scope: str = CONTENT_BOUND_MATRIX_SCOPE
    runtime_credit: int = 0
    physical_host_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False
    schema: str = CONTENT_BOUND_MATRIX_SCHEMA

    def __post_init__(self) -> None:
        _text(self.artifact_filename, "artifact_filename")
        _sha256(self.artifact_sha256, "artifact_sha256")
        _size(self.artifact_size_bytes, "artifact_size_bytes")
        _sha256(self.artifact_subject_sha256, "artifact_subject_sha256")
        _sha256(self.release_manifest_sha256, "release_manifest_sha256")
        _text(self.prehandoff_receipt_ref, "prehandoff_receipt_ref")
        _sha256(self.prehandoff_receipt_sha256, "prehandoff_receipt_sha256")
        _size(self.prehandoff_receipt_size_bytes, "prehandoff_receipt_size_bytes")
        _sha256(
            self.receipt_content_subject_sha256,
            "receipt_content_subject_sha256",
        )
        _sha256(
            self.content_bound_prehandoff_sha256,
            "content_bound_prehandoff_sha256",
        )
        _sha256(self.artifact_bound_matrix_sha256, "artifact_bound_matrix_sha256")
        if tuple(sorted(set(self.violations))) != self.violations:
            raise ReceiptContentBindingError("violations must be unique and sorted")
        if self.schema != CONTENT_BOUND_MATRIX_SCHEMA:
            raise ReceiptContentBindingError(
                "receipt-content-bound matrix schema mismatch"
            )
        if self.evidence_scope != CONTENT_BOUND_MATRIX_SCOPE:
            raise ReceiptContentBindingError(
                "receipt-content-bound matrix evidence scope mismatch"
            )
        if any(
            value != 0
            for value in (
                self.runtime_credit,
                self.physical_host_credit,
                self.completion_credit,
            )
        ) or self.whole_system_acceptance:
            raise ReceiptContentBindingError(
                "receipt-content-bound matrix cannot mint higher-scope credit"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "artifact_filename": self.artifact_filename,
            "artifact_sha256": self.artifact_sha256,
            "artifact_size_bytes": self.artifact_size_bytes,
            "artifact_subject_sha256": self.artifact_subject_sha256,
            "release_manifest_sha256": self.release_manifest_sha256,
            "prehandoff_receipt_ref": self.prehandoff_receipt_ref,
            "prehandoff_receipt_sha256": self.prehandoff_receipt_sha256,
            "prehandoff_receipt_size_bytes": self.prehandoff_receipt_size_bytes,
            "receipt_content_subject_sha256": self.receipt_content_subject_sha256,
            "content_bound_prehandoff_sha256": self.content_bound_prehandoff_sha256,
            "artifact_bound_matrix_sha256": self.artifact_bound_matrix_sha256,
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


def evaluate_receipt_content_bound_clean_machine_acceptance(
    observations: Sequence[ReceiptContentBoundAcceptanceObservation],
    *,
    content_bound_prehandoff: ContentBoundPreHandoffReceipt,
    perception_required: bool = False,
) -> ReceiptContentBoundCleanMachineMatrixResult:
    """Validate rows only when all bind the same exact receipt bytes and release ZIP."""

    if not isinstance(content_bound_prehandoff, ContentBoundPreHandoffReceipt):
        raise ReceiptContentBindingError(
            "content_bound_prehandoff must be ContentBoundPreHandoffReceipt"
        )

    expected = content_bound_prehandoff.receipt_content_subject
    expected_subject_sha = expected.sha256()
    violations: list[str] = []
    if content_bound_prehandoff.status != READY_STATUS:
        violations.append("content_bound_prehandoff:not_ready")

    inner: list[ArtifactBoundAcceptanceObservation] = []
    seen_cases: set[str] = set()
    for wrapped in observations:
        if not isinstance(wrapped, ReceiptContentBoundAcceptanceObservation):
            raise ReceiptContentBindingError(
                "observations must contain ReceiptContentBoundAcceptanceObservation values"
            )
        if wrapped.case_id in seen_cases:
            raise ReceiptContentBindingError(
                f"duplicate receipt-content-bound clean-machine case: {wrapped.case_id}"
            )
        seen_cases.add(wrapped.case_id)

        if wrapped.prehandoff_receipt_ref != expected.prehandoff_receipt_ref:
            violations.append(f"{wrapped.case_id}:prehandoff_receipt_ref mismatch")
        if wrapped.prehandoff_receipt_sha256 != expected.prehandoff_receipt_sha256:
            violations.append(
                f"{wrapped.case_id}:prehandoff_receipt_sha256 mismatch"
            )
        if (
            wrapped.prehandoff_receipt_size_bytes
            != expected.prehandoff_receipt_size_bytes
        ):
            violations.append(
                f"{wrapped.case_id}:prehandoff_receipt_size_bytes mismatch"
            )
        if wrapped.receipt_content_subject_sha256 != expected_subject_sha:
            violations.append(
                f"{wrapped.case_id}:receipt_content_subject_sha256 mismatch"
            )
        inner.append(wrapped.artifact_observation)

    base: ArtifactBoundCleanMachineMatrixResult = (
        evaluate_artifact_bound_clean_machine_acceptance(
            inner,
            artifact_bound_prehandoff=(
                content_bound_prehandoff.artifact_bound_prehandoff
            ),
            perception_required=perception_required,
        )
    )
    violations.extend(base.violations)
    ordered = tuple(sorted(set(violations)))
    status = "READY_FOR_ADMISSION_REVIEW" if not ordered else "BLOCKED"

    return ReceiptContentBoundCleanMachineMatrixResult(
        artifact_filename=base.artifact_filename,
        artifact_sha256=base.artifact_sha256,
        artifact_size_bytes=base.artifact_size_bytes,
        artifact_subject_sha256=base.artifact_subject_sha256,
        release_manifest_sha256=base.release_manifest_sha256,
        prehandoff_receipt_ref=expected.prehandoff_receipt_ref,
        prehandoff_receipt_sha256=expected.prehandoff_receipt_sha256,
        prehandoff_receipt_size_bytes=expected.prehandoff_receipt_size_bytes,
        receipt_content_subject_sha256=expected_subject_sha,
        content_bound_prehandoff_sha256=content_bound_prehandoff.sha256(),
        artifact_bound_matrix_sha256=base.sha256(),
        required_case_ids=base.required_case_ids,
        observed_case_ids=base.observed_case_ids,
        violations=ordered,
        status=status,
    )
