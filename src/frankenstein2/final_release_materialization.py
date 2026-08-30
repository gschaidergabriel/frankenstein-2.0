"""Compose the accepted Stage-11 release primitives into one exact handoff materialization.

F2-WP-1110 generation-4 REVIEW_ONLY candidate.

This module does not create a new ZIP verifier, pre-handoff authority, or receipt-content
authority. It composes the accepted WP1107/WP1110 primitives and adds only a fail-closed
filesystem materialization boundary:

    package root
      -> build_release_archive
      -> exact unopened ZIP write/readback
      -> bind_release_artifact_subject
      -> exact canonical ArtifactBoundPreHandoffReceipt write/readback
      -> bind_prehandoff_receipt_content

The output is still release-handoff evidence only. It grants no installer, clean-machine,
physical-host, provider, effect, completion, or whole-system credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .pre_handoff_release import READY_STATUS
from .receipt_content_binding import bind_prehandoff_receipt_content
from .release_archive import ReleaseArchivePolicy, build_release_archive, verify_release_archive
from .release_artifact_subject import bind_release_artifact_subject

FINAL_MATERIALIZATION_SCHEMA = "FRANKENSTEIN2_FINAL_RELEASE_MATERIALIZATION/v1"
FINAL_MATERIALIZATION_SCOPE = (
    "EXACT_RELEASE_ZIP_PLUS_CANONICAL_PREHANDOFF_RECEIPT_MATERIALIZATION_ONLY_"
    "NO_INSTALL_RUNTIME_CLEAN_MACHINE_EFFECT_OR_COMPLETION_CREDIT"
)


class FinalReleaseMaterializationError(ValueError):
    """The exact final release handoff could not be materialized safely."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FinalReleaseMaterializationError(
            f"{name} must be a non-empty already-trimmed string"
        )
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise FinalReleaseMaterializationError(f"{name} contains control characters")
    return value


def _sha256_hex(value: Any, name: str) -> str:
    value = _text(value, name)
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise FinalReleaseMaterializationError(
            f"{name} must be lowercase 64-hex SHA-256"
        )
    return value


def _safe_relpath(value: Any, name: str) -> str:
    value = _text(value, name)
    if "\\" in value or "\x00" in value:
        raise FinalReleaseMaterializationError(f"{name} is not canonical POSIX")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise FinalReleaseMaterializationError(f"{name} must be ASCII") from exc
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise FinalReleaseMaterializationError(f"{name} is not a safe relative path")
    return value


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _write_once_or_match(path: Path, data: bytes, *, output_root: Path, label: str) -> None:
    if type(data) is not bytes or not data:
        raise FinalReleaseMaterializationError(f"{label} bytes must be non-empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise FinalReleaseMaterializationError(f"{label} path must not be a symlink")
    resolved_parent = path.parent.resolve(strict=True)
    if not _is_within(resolved_parent, output_root):
        raise FinalReleaseMaterializationError(f"{label} escaped output root")
    if path.exists():
        if not path.is_file():
            raise FinalReleaseMaterializationError(
                f"{label} path exists but is not a regular file"
            )
        if path.read_bytes() != data:
            raise FinalReleaseMaterializationError(
                f"{label} already exists with different bytes"
            )
        return
    try:
        with path.open("xb") as handle:
            handle.write(data)
    except FileExistsError as exc:
        raise FinalReleaseMaterializationError(
            f"{label} appeared concurrently; retry after exact readback"
        ) from exc
    if path.read_bytes() != data:
        raise FinalReleaseMaterializationError(f"{label} readback mismatch")


@dataclass(frozen=True, slots=True)
class FinalReleaseMaterialization:
    release_id: str
    source_commit: str
    source_tree: str
    build_id: str
    archive_policy_id: str
    archive_policy_sha256: str
    artifact_filename: str
    artifact_sha256: str
    artifact_size_bytes: int
    release_manifest_sha256: str
    archive_receipt_sha256: str
    artifact_subject_sha256: str
    artifact_bound_prehandoff_sha256: str
    prehandoff_receipt_ref: str
    prehandoff_receipt_sha256: str
    prehandoff_receipt_size_bytes: int
    receipt_content_subject_sha256: str
    content_bound_prehandoff_sha256: str
    status: str
    evidence_scope: str = FINAL_MATERIALIZATION_SCOPE
    runtime_credit: int = 0
    physical_host_credit: int = 0
    clean_machine_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False
    schema: str = FINAL_MATERIALIZATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != FINAL_MATERIALIZATION_SCHEMA:
            raise FinalReleaseMaterializationError("materialization schema mismatch")
        if self.evidence_scope != FINAL_MATERIALIZATION_SCOPE:
            raise FinalReleaseMaterializationError("materialization evidence scope mismatch")
        for name in (
            "release_id",
            "source_commit",
            "source_tree",
            "build_id",
            "archive_policy_id",
        ):
            _text(getattr(self, name), name)
        filename = _safe_relpath(self.artifact_filename, "artifact_filename")
        if "/" in filename or not filename.endswith(".zip"):
            raise FinalReleaseMaterializationError(
                "artifact_filename must be a .zip basename"
            )
        _safe_relpath(self.prehandoff_receipt_ref, "prehandoff_receipt_ref")
        for name in (
            "archive_policy_sha256",
            "artifact_sha256",
            "release_manifest_sha256",
            "archive_receipt_sha256",
            "artifact_subject_sha256",
            "artifact_bound_prehandoff_sha256",
            "prehandoff_receipt_sha256",
            "receipt_content_subject_sha256",
            "content_bound_prehandoff_sha256",
        ):
            _sha256_hex(getattr(self, name), name)
        for name in ("artifact_size_bytes", "prehandoff_receipt_size_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise FinalReleaseMaterializationError(f"{name} must be positive integer")
        if self.status != READY_STATUS:
            raise FinalReleaseMaterializationError(
                "final materialization can exist only after READY pre-handoff"
            )
        if any(
            value != 0
            for value in (
                self.runtime_credit,
                self.physical_host_credit,
                self.clean_machine_credit,
                self.effect_credit,
                self.completion_credit,
            )
        ) or self.whole_system_acceptance:
            raise FinalReleaseMaterializationError(
                "release materialization cannot mint higher-scope credit"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "release_id": self.release_id,
            "source_commit": self.source_commit,
            "source_tree": self.source_tree,
            "build_id": self.build_id,
            "archive_policy_id": self.archive_policy_id,
            "archive_policy_sha256": self.archive_policy_sha256,
            "artifact_filename": self.artifact_filename,
            "artifact_sha256": self.artifact_sha256,
            "artifact_size_bytes": self.artifact_size_bytes,
            "release_manifest_sha256": self.release_manifest_sha256,
            "archive_receipt_sha256": self.archive_receipt_sha256,
            "artifact_subject_sha256": self.artifact_subject_sha256,
            "artifact_bound_prehandoff_sha256": self.artifact_bound_prehandoff_sha256,
            "prehandoff_receipt_ref": self.prehandoff_receipt_ref,
            "prehandoff_receipt_sha256": self.prehandoff_receipt_sha256,
            "prehandoff_receipt_size_bytes": self.prehandoff_receipt_size_bytes,
            "receipt_content_subject_sha256": self.receipt_content_subject_sha256,
            "content_bound_prehandoff_sha256": self.content_bound_prehandoff_sha256,
            "status": self.status,
            "evidence_scope": self.evidence_scope,
            "runtime_credit": self.runtime_credit,
            "physical_host_credit": self.physical_host_credit,
            "clean_machine_credit": self.clean_machine_credit,
            "effect_credit": self.effect_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def materialize_final_release(
    package_root: str | Path,
    output_dir: str | Path,
    *,
    release_id: str,
    source_commit: str,
    source_tree: str,
    build_id: str,
    policy: ReleaseArchivePolicy,
    prehandoff_receipt_ref: str,
    artifact_filename: str = "frankenstein-2.0.zip",
) -> FinalReleaseMaterialization:
    """Materialize one deterministic ZIP and its exact canonical external handoff receipt.

    The output directory must be outside ``package_root`` so generated artifacts cannot feed
    back into the release manifest on a repeated build.
    """

    if not isinstance(policy, ReleaseArchivePolicy):
        raise FinalReleaseMaterializationError(
            "policy must be the accepted ReleaseArchivePolicy"
        )
    package_input = Path(package_root)
    if package_input.is_symlink():
        raise FinalReleaseMaterializationError("package_root must not be a symlink")
    try:
        package = package_input.resolve(strict=True)
    except OSError as exc:
        raise FinalReleaseMaterializationError("package_root does not resolve") from exc
    if not package.is_dir():
        raise FinalReleaseMaterializationError("package_root must be a directory")

    output_input = Path(output_dir)
    if output_input.is_symlink():
        raise FinalReleaseMaterializationError("output_dir must not be a symlink")
    output_candidate = output_input.resolve(strict=False)
    if _is_within(output_candidate, package):
        raise FinalReleaseMaterializationError(
            "output_dir must be outside package_root to prevent self-inclusion"
        )
    output_input.mkdir(parents=True, exist_ok=True)
    output = output_input.resolve(strict=True)
    if _is_within(output, package):
        raise FinalReleaseMaterializationError(
            "output_dir resolved inside package_root"
        )

    artifact_filename = _safe_relpath(artifact_filename, "artifact_filename")
    if "/" in artifact_filename or not artifact_filename.endswith(".zip"):
        raise FinalReleaseMaterializationError(
            "artifact_filename must be a .zip basename"
        )
    receipt_ref = _safe_relpath(
        prehandoff_receipt_ref, "prehandoff_receipt_ref"
    )
    if receipt_ref == artifact_filename:
        raise FinalReleaseMaterializationError(
            "artifact and pre-handoff receipt paths must differ"
        )

    build = build_release_archive(
        package,
        release_id=_text(release_id, "release_id"),
        source_commit=_text(source_commit, "source_commit"),
        source_tree=_text(source_tree, "source_tree"),
        build_id=_text(build_id, "build_id"),
        policy=policy,
        prehandoff_receipt_refs=(receipt_ref,),
    )

    artifact_path = output / artifact_filename
    _write_once_or_match(
        artifact_path,
        build.archive_bytes,
        output_root=output,
        label="release artifact",
    )
    artifact_bytes = artifact_path.read_bytes()
    observed_archive = verify_release_archive(
        artifact_bytes,
        policy=policy,
        expected_receipt=build.receipt,
    )

    artifact_bound = bind_release_artifact_subject(
        artifact_path,
        policy=policy,
        prehandoff_receipt_ref=receipt_ref,
        expected_archive_receipt=observed_archive,
    )
    if artifact_bound.status != READY_STATUS or artifact_bound.static_violations:
        raise FinalReleaseMaterializationError(
            "static pre-handoff gate blocked; external receipt was not materialized"
        )

    receipt_bytes = artifact_bound.canonical_bytes()
    receipt_path = output.joinpath(*PurePosixPath(receipt_ref).parts)
    _write_once_or_match(
        receipt_path,
        receipt_bytes,
        output_root=output,
        label="pre-handoff receipt",
    )
    receipt_readback = receipt_path.read_bytes()
    content_bound = bind_prehandoff_receipt_content(
        artifact_bound,
        prehandoff_receipt_ref=receipt_ref,
        prehandoff_receipt_bytes=receipt_readback,
    )
    if content_bound.status != READY_STATUS:
        raise FinalReleaseMaterializationError(
            "receipt-content binding did not remain READY"
        )

    return FinalReleaseMaterialization(
        release_id=observed_archive.release_id,
        source_commit=observed_archive.source_commit,
        source_tree=observed_archive.source_tree,
        build_id=observed_archive.build_id,
        archive_policy_id=observed_archive.archive_policy_id,
        archive_policy_sha256=observed_archive.archive_policy_sha256,
        artifact_filename=artifact_filename,
        artifact_sha256=observed_archive.archive_sha256,
        artifact_size_bytes=observed_archive.archive_size,
        release_manifest_sha256=observed_archive.manifest_sha256,
        archive_receipt_sha256=observed_archive.digest(),
        artifact_subject_sha256=artifact_bound.subject.sha256(),
        artifact_bound_prehandoff_sha256=artifact_bound.sha256(),
        prehandoff_receipt_ref=receipt_ref,
        prehandoff_receipt_sha256=content_bound.prehandoff_receipt_sha256,
        prehandoff_receipt_size_bytes=content_bound.prehandoff_receipt_size_bytes,
        receipt_content_subject_sha256=content_bound.receipt_content_subject.sha256(),
        content_bound_prehandoff_sha256=content_bound.sha256(),
        status=content_bound.status,
    )
