"""Bind the exact unopened Frankenstein 2.0 release ZIP into pre-handoff evidence.

F2-WP-1110 generation 2.

This module is deliberately a composition layer. It reuses the accepted WP1107
``verify_release_archive`` implementation as the ZIP/container authority and the accepted
WP1110 generation-1 ``evaluate_pre_handoff_release`` implementation as the extracted
payload/route authority. It does not create a second payload-integrity authority.

The resulting external receipt binds both evidence subjects:

    exact unopened ZIP bytes
        -> archive SHA-256 + size + filename
        -> verified embedded release manifest SHA-256
        -> exact prehandoff receipt reference
        -> accepted static route/invariant gate

It grants no runtime, physical-host, effect, completion, or whole-system credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any
import zipfile

from .pre_handoff_release import (
    BLOCKED_STATUS,
    READY_STATUS,
    PreHandoffReleaseReceipt,
    evaluate_pre_handoff_release,
)
from .release_archive import (
    ReleaseArchivePolicy,
    ReleaseArchiveReceipt,
    verify_release_archive,
)

ARTIFACT_SUBJECT_SCHEMA = "FRANKENSTEIN2_RELEASE_ARTIFACT_SUBJECT/v1"
ARTIFACT_BOUND_PREHANDOFF_SCHEMA = "FRANKENSTEIN2_ARTIFACT_BOUND_PREHANDOFF_RECEIPT/v1"
ARTIFACT_BOUND_SCOPE = (
    "EXACT_UNOPENED_RELEASE_ARTIFACT_PLUS_STATIC_PREHANDOFF_BINDING_ONLY_"
    "NO_INSTALL_RUNTIME_EFFECT_OR_COMPLETION_CREDIT"
)


class ReleaseArtifactSubjectError(ValueError):
    """Exact release-artifact subject cannot be bound safely."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReleaseArtifactSubjectError(f"{name} must be a non-empty already-trimmed string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ReleaseArtifactSubjectError(f"{name} contains control characters")
    return value


def _require_sha256(value: Any, name: str) -> str:
    text = _require_text(value, name)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ReleaseArtifactSubjectError(f"{name} must be lowercase 64-hex SHA-256")
    return text


@dataclass(frozen=True, slots=True)
class ReleaseArtifactSubject:
    artifact_filename: str
    artifact_sha256: str
    artifact_size_bytes: int
    release_manifest_sha256: str
    source_commit: str
    source_tree: str
    release_id: str
    build_id: str
    archive_policy_id: str
    archive_policy_sha256: str
    member_count: int
    schema: str = ARTIFACT_SUBJECT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != ARTIFACT_SUBJECT_SCHEMA:
            raise ReleaseArtifactSubjectError("artifact subject schema mismatch")
        filename = _require_text(self.artifact_filename, "artifact_filename")
        if Path(filename).name != filename or filename in {".", ".."}:
            raise ReleaseArtifactSubjectError("artifact_filename must be a basename")
        _require_sha256(self.artifact_sha256, "artifact_sha256")
        _require_sha256(self.release_manifest_sha256, "release_manifest_sha256")
        _require_sha256(self.archive_policy_sha256, "archive_policy_sha256")
        for name in (
            "source_commit",
            "source_tree",
            "release_id",
            "build_id",
            "archive_policy_id",
        ):
            _require_text(getattr(self, name), name)
        if (
            isinstance(self.artifact_size_bytes, bool)
            or not isinstance(self.artifact_size_bytes, int)
            or self.artifact_size_bytes <= 0
        ):
            raise ReleaseArtifactSubjectError("artifact_size_bytes must be a positive integer")
        if (
            isinstance(self.member_count, bool)
            or not isinstance(self.member_count, int)
            or self.member_count < 1
        ):
            raise ReleaseArtifactSubjectError("member_count must be a positive integer")

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def canonical_bytes(self) -> bytes:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256(self.canonical_bytes())


@dataclass(frozen=True, slots=True)
class ArtifactBoundPreHandoffReceipt:
    subject: ReleaseArtifactSubject
    prehandoff_receipt_ref: str
    static_prehandoff_sha256: str
    static_status: str
    static_violations: tuple[str, ...]
    status: str
    evidence_scope: str = ARTIFACT_BOUND_SCOPE
    runtime_credit: int = 0
    physical_host_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False
    schema: str = ARTIFACT_BOUND_PREHANDOFF_SCHEMA

    def __post_init__(self) -> None:
        if not isinstance(self.subject, ReleaseArtifactSubject):
            raise ReleaseArtifactSubjectError("subject must be ReleaseArtifactSubject")
        _require_text(self.prehandoff_receipt_ref, "prehandoff_receipt_ref")
        _require_sha256(self.static_prehandoff_sha256, "static_prehandoff_sha256")
        if self.static_status not in {READY_STATUS, BLOCKED_STATUS}:
            raise ReleaseArtifactSubjectError("unexpected static prehandoff status")
        if tuple(sorted(set(self.static_violations))) != self.static_violations:
            raise ReleaseArtifactSubjectError("static_violations must be unique and sorted")
        expected = READY_STATUS if self.static_status == READY_STATUS and not self.static_violations else BLOCKED_STATUS
        if self.status != expected:
            raise ReleaseArtifactSubjectError("artifact-bound status is inconsistent with static gate")
        if self.schema != ARTIFACT_BOUND_PREHANDOFF_SCHEMA:
            raise ReleaseArtifactSubjectError("artifact-bound receipt schema mismatch")
        if self.evidence_scope != ARTIFACT_BOUND_SCOPE:
            raise ReleaseArtifactSubjectError("artifact-bound evidence scope mismatch")
        if any(
            value != 0
            for value in (
                self.runtime_credit,
                self.physical_host_credit,
                self.effect_credit,
                self.completion_credit,
            )
        ) or self.whole_system_acceptance:
            raise ReleaseArtifactSubjectError("artifact-bound receipt cannot mint higher-scope credit")

    @property
    def release_manifest_sha256(self) -> str:
        return self.subject.release_manifest_sha256

    @property
    def artifact_sha256(self) -> str:
        return self.subject.artifact_sha256

    @property
    def artifact_size_bytes(self) -> int:
        return self.subject.artifact_size_bytes

    @property
    def artifact_filename(self) -> str:
        return self.subject.artifact_filename

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "artifact_subject": self.subject.as_dict(),
            "prehandoff_receipt_ref": self.prehandoff_receipt_ref,
            "static_prehandoff_sha256": self.static_prehandoff_sha256,
            "static_status": self.static_status,
            "static_violations": list(self.static_violations),
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
        return _sha256(self.canonical_bytes())


def _subject_from_archive(
    *,
    artifact_path: Path,
    archive_receipt: ReleaseArchiveReceipt,
) -> ReleaseArtifactSubject:
    return ReleaseArtifactSubject(
        artifact_filename=artifact_path.name,
        artifact_sha256=archive_receipt.archive_sha256,
        artifact_size_bytes=archive_receipt.archive_size,
        release_manifest_sha256=archive_receipt.manifest_sha256,
        source_commit=archive_receipt.source_commit,
        source_tree=archive_receipt.source_tree,
        release_id=archive_receipt.release_id,
        build_id=archive_receipt.build_id,
        archive_policy_id=archive_receipt.archive_policy_id,
        archive_policy_sha256=archive_receipt.archive_policy_sha256,
        member_count=archive_receipt.member_count,
    )


def _materialize_verified_archive(archive_bytes: bytes, destination: Path) -> None:
    """Materialize only after WP1107 verifier has accepted exact archive topology."""

    with zipfile.ZipFile(io.BytesIO(archive_bytes), mode="r", allowZip64=False) as archive:
        for info in archive.infolist():
            relative = PurePosixPath(info.filename)
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info.filename))


def bind_release_artifact_subject(
    artifact_path: str | Path,
    *,
    policy: ReleaseArchivePolicy,
    prehandoff_receipt_ref: str,
    expected_archive_receipt: ReleaseArchiveReceipt | None = None,
) -> ArtifactBoundPreHandoffReceipt:
    """Verify exact unopened ZIP first, then bind it to the existing static handoff gate.

    ``verify_release_archive`` performs the fail-closed container/member verification before
    this function writes any extracted member. Only after that verifier accepts the exact
    bytes are they materialized into a temporary root and evaluated by the generation-1
    pre-handoff route/payload gate.
    """

    receipt_ref = _require_text(prehandoff_receipt_ref, "prehandoff_receipt_ref")
    path = Path(artifact_path)
    if path.is_symlink():
        raise ReleaseArtifactSubjectError("artifact_path must not be a symlink")
    try:
        path = path.resolve(strict=True)
    except OSError as exc:
        raise ReleaseArtifactSubjectError("artifact_path does not resolve") from exc
    if not path.is_file():
        raise ReleaseArtifactSubjectError("artifact_path must resolve to a regular file")
    _require_text(path.name, "artifact_filename")

    archive_bytes = path.read_bytes()
    archive_receipt = verify_release_archive(
        archive_bytes,
        policy=policy,
        expected_receipt=expected_archive_receipt,
    )
    if archive_receipt.archive_sha256 != _sha256(archive_bytes):
        raise ReleaseArtifactSubjectError("archive verifier digest disagrees with exact artifact bytes")
    if archive_receipt.archive_size != len(archive_bytes):
        raise ReleaseArtifactSubjectError("archive verifier size disagrees with exact artifact bytes")

    subject = _subject_from_archive(artifact_path=path, archive_receipt=archive_receipt)

    with tempfile.TemporaryDirectory(prefix="f2-artifact-handoff-") as tmp:
        root = Path(tmp)
        _materialize_verified_archive(archive_bytes, root)
        static_receipt: PreHandoffReleaseReceipt = evaluate_pre_handoff_release(
            root,
            prehandoff_receipt_ref=receipt_ref,
        )

    if static_receipt.release_manifest_sha256 != subject.release_manifest_sha256:
        raise ReleaseArtifactSubjectError("extracted static gate manifest digest differs from archive subject")
    for field_name in ("release_id", "source_commit", "source_tree", "build_id"):
        if getattr(static_receipt, field_name) != getattr(subject, field_name):
            raise ReleaseArtifactSubjectError(f"archive/static identity mismatch: {field_name}")

    violations = tuple(sorted(set(static_receipt.violations)))
    status = READY_STATUS if static_receipt.status == READY_STATUS and not violations else BLOCKED_STATUS
    return ArtifactBoundPreHandoffReceipt(
        subject=subject,
        prehandoff_receipt_ref=receipt_ref,
        static_prehandoff_sha256=static_receipt.sha256(),
        static_status=static_receipt.status,
        static_violations=violations,
        status=status,
    )
