"""Bind WP1111 portable static completeness to one exact unopened release ZIP.

F2-WP-1112 generation 1.

This is a composition layer only. The accepted WP1107 ``verify_release_archive`` remains
archive/container authority and the accepted WP1111
``evaluate_portable_release_static_completeness`` remains static-delivery authority.
The composer verifies the exact ZIP before materialization, runs WP1111 on the resulting
exact release root, and binds both subjects into one deterministic receipt. The original
artifact locator is re-verified after WP1111 returns so mutation or path retargeting during
the composition window fails closed.

ARTIFACT_BOUND_STATIC_COMPLETE != INSTALLATION != TARGET_RUNTIME != COMPLETION
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

from .portable_release_static_completeness import (
    BLOCKED,
    STATIC_COMPLETE,
    PortableReleaseStaticCompletenessReceipt,
    evaluate_portable_release_static_completeness,
)
from .release_archive import (
    ReleaseArchivePolicy,
    ReleaseArchiveReceipt,
    verify_release_archive,
)
from .release_artifact_subject import ReleaseArtifactSubject

SCHEMA = "FRANKENSTEIN2_ARTIFACT_BOUND_STATIC_COMPLETENESS/v1"
EVIDENCE_SCOPE = (
    "EXACT_RELEASE_ARTIFACT_TO_WP1111_STATIC_COMPLETENESS_BINDING_ONLY_"
    "NO_INSTALL_RUNTIME_EFFECT_OR_COMPLETION_CREDIT"
)


class ArtifactBoundStaticCompletenessError(ValueError):
    """Exact release artifact cannot be bound safely to WP1111 completeness."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ArtifactBoundStaticCompletenessError(
            f"{name} must be a non-empty already-trimmed string"
        )
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ArtifactBoundStaticCompletenessError(f"{name} contains control characters")
    return value


def _digest(value: Any, name: str) -> str:
    text = _text(value, name)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ArtifactBoundStaticCompletenessError(
            f"{name} must be lowercase 64-hex SHA-256"
        )
    return text


def _subject_from_archive(
    artifact_path: Path, archive_receipt: ReleaseArchiveReceipt
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
    """Materialize only bytes already accepted by WP1107 archive verification."""

    with zipfile.ZipFile(io.BytesIO(archive_bytes), mode="r", allowZip64=False) as archive:
        for info in archive.infolist():
            relative = PurePosixPath(info.filename)
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info.filename))


def _assert_artifact_locator_still_exact(
    locator: Path, resolved_path: Path, expected_bytes: bytes
) -> None:
    """Close the read/evaluate/return TOCTOU window on the handoff artifact locator."""

    if locator.is_symlink() or locator.is_junction():
        raise ArtifactBoundStaticCompletenessError(
            "artifact locator changed to a symlink or junction during static evaluation"
        )
    try:
        rebound = locator.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ArtifactBoundStaticCompletenessError(
            "artifact locator stopped resolving during static evaluation"
        ) from exc
    if rebound != resolved_path or not rebound.is_file():
        raise ArtifactBoundStaticCompletenessError(
            "artifact locator target changed during static evaluation"
        )
    try:
        final_bytes = rebound.read_bytes()
    except OSError as exc:
        raise ArtifactBoundStaticCompletenessError(
            "artifact could not be re-read after static evaluation"
        ) from exc
    if final_bytes != expected_bytes:
        raise ArtifactBoundStaticCompletenessError(
            "artifact mutated during static completeness evaluation"
        )


@dataclass(frozen=True, slots=True)
class ArtifactBoundStaticCompletenessReceipt:
    artifact_subject: ReleaseArtifactSubject
    prehandoff_receipt_ref: str
    static_completeness_sha256: str
    static_status: str
    static_violations: tuple[str, ...]
    status: str
    schema: str = SCHEMA
    evidence_scope: str = EVIDENCE_SCOPE
    runtime_credit: int = 0
    physical_host_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_subject, ReleaseArtifactSubject):
            raise ArtifactBoundStaticCompletenessError(
                "artifact_subject must be ReleaseArtifactSubject"
            )
        _text(self.prehandoff_receipt_ref, "prehandoff_receipt_ref")
        _digest(self.static_completeness_sha256, "static_completeness_sha256")
        if self.static_status not in {STATIC_COMPLETE, BLOCKED}:
            raise ArtifactBoundStaticCompletenessError("unexpected static status")
        if tuple(sorted(set(self.static_violations))) != self.static_violations:
            raise ArtifactBoundStaticCompletenessError(
                "static_violations must be unique and sorted"
            )
        expected = (
            STATIC_COMPLETE
            if self.static_status == STATIC_COMPLETE and not self.static_violations
            else BLOCKED
        )
        if self.status != expected:
            raise ArtifactBoundStaticCompletenessError(
                "artifact-bound status is inconsistent with WP1111 static result"
            )
        if self.schema != SCHEMA:
            raise ArtifactBoundStaticCompletenessError("receipt schema mismatch")
        if self.evidence_scope != EVIDENCE_SCOPE:
            raise ArtifactBoundStaticCompletenessError("evidence scope mismatch")
        if any(
            value != 0
            for value in (
                self.runtime_credit,
                self.physical_host_credit,
                self.effect_credit,
                self.completion_credit,
            )
        ) or self.whole_system_acceptance:
            raise ArtifactBoundStaticCompletenessError(
                "artifact-bound static receipt cannot mint higher-scope credit"
            )

    @property
    def artifact_sha256(self) -> str:
        return self.artifact_subject.artifact_sha256

    @property
    def release_manifest_sha256(self) -> str:
        return self.artifact_subject.release_manifest_sha256

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["artifact_subject"] = self.artifact_subject.as_dict()
        value["static_violations"] = list(self.static_violations)
        return value

    def canonical_bytes(self) -> bytes:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256(self.canonical_bytes())


def _static_digest(receipt: PortableReleaseStaticCompletenessReceipt) -> str:
    return _sha256(_canonical_json(receipt.as_dict()))


def bind_release_artifact_static_completeness(
    artifact_path: str | Path,
    *,
    policy: ReleaseArchivePolicy,
    prehandoff_receipt_ref: str,
    expected_archive_receipt: ReleaseArchiveReceipt | None = None,
) -> ArtifactBoundStaticCompletenessReceipt:
    """Verify exact ZIP bytes, materialize them, then execute accepted WP1111 on that root."""

    receipt_ref = _text(prehandoff_receipt_ref, "prehandoff_receipt_ref")
    artifact_locator = Path(artifact_path)
    if artifact_locator.is_symlink() or artifact_locator.is_junction():
        raise ArtifactBoundStaticCompletenessError(
            "artifact_path must not be a symlink or junction"
        )
    try:
        path = artifact_locator.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ArtifactBoundStaticCompletenessError("artifact_path does not resolve") from exc
    if not path.is_file():
        raise ArtifactBoundStaticCompletenessError(
            "artifact_path must resolve to a regular file"
        )
    if Path(path.name).name != path.name:
        raise ArtifactBoundStaticCompletenessError("artifact filename is not canonical")

    archive_bytes = path.read_bytes()
    archive_receipt = verify_release_archive(
        archive_bytes,
        policy=policy,
        expected_receipt=expected_archive_receipt,
    )
    if archive_receipt.archive_sha256 != _sha256(archive_bytes):
        raise ArtifactBoundStaticCompletenessError(
            "archive verifier digest disagrees with exact artifact bytes"
        )
    if archive_receipt.archive_size != len(archive_bytes):
        raise ArtifactBoundStaticCompletenessError(
            "archive verifier size disagrees with exact artifact bytes"
        )

    subject = _subject_from_archive(path, archive_receipt)
    with tempfile.TemporaryDirectory(prefix="f2-wp1112-static-") as tmp:
        root = Path(tmp)
        _materialize_verified_archive(archive_bytes, root)
        static = evaluate_portable_release_static_completeness(
            root,
            prehandoff_receipt_ref=receipt_ref,
        )

    if static.release_manifest_sha256 != subject.release_manifest_sha256:
        raise ArtifactBoundStaticCompletenessError(
            "WP1111 manifest digest differs from exact archive subject"
        )
    if static.release_id != subject.release_id:
        raise ArtifactBoundStaticCompletenessError(
            "WP1111 release id differs from exact archive subject"
        )
    if static.source_commit != subject.source_commit:
        raise ArtifactBoundStaticCompletenessError(
            "WP1111 source commit differs from exact archive subject"
        )

    _assert_artifact_locator_still_exact(artifact_locator, path, archive_bytes)

    violations = tuple(sorted(set(static.violations)))
    status = STATIC_COMPLETE if static.status == STATIC_COMPLETE and not violations else BLOCKED
    return ArtifactBoundStaticCompletenessReceipt(
        artifact_subject=subject,
        prehandoff_receipt_ref=receipt_ref,
        static_completeness_sha256=_static_digest(static),
        static_status=static.status,
        static_violations=violations,
        status=status,
    )
