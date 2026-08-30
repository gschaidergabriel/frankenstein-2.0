"""Compatibility adapter from the accepted WP1113 release bundle to WP1207.

F2-WP-1207 generation 6 repository/component scope only.

The accepted Stage-11 release artifact is an Actions artifact ZIP containing
``release-bundle-index.json`` plus the exact release archive and bound receipts.  The
existing hostile-twin executor predates that container and accepts a legacy evidence ZIP.
This module does not create a second release, transaction, or execution authority: it
validates the current bundle fail-closed, reconstructs the already-defined WP1107 archive
policy from exact archive metadata, and returns the existing ``BoundReleaseCandidate``.

CURRENT_BUNDLE_ADAPTATION != TARGET_RUNTIME != PHYSICAL_HOST != EFFECT != COMPLETION
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping
import zipfile

from .hostile_twin_release_executor import BoundReleaseCandidate, HostileTwinExecutionError
from .portable_release_transaction import RELEASE_SCHEMA, ReleaseIdentity
from .release_archive import ReleaseArchivePolicy, ReleaseArchiveReceipt, verify_release_archive

CURRENT_BUNDLE_SCHEMA = "FRANKENSTEIN2_RELEASE_CANDIDATE_BUNDLE/v1"
CURRENT_INDEX_NAME = "release-bundle-index.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_object(data: bytes, *, name: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HostileTwinExecutionError(f"invalid {name} JSON") from exc
    if not isinstance(value, dict):
        raise HostileTwinExecutionError(f"{name} JSON must contain an object")
    return value


def _simple_member(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HostileTwinExecutionError(f"{field} must be a non-empty trimmed string")
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1 or path.parts[0] in {".", ".."}:
        raise HostileTwinExecutionError(f"{field} must be one safe bundle member")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise HostileTwinExecutionError(f"{field} contains control characters")
    return value


def _hex40(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise HostileTwinExecutionError(f"{field} must be lowercase 40-hex")
    return value


def _file_meta(files: Mapping[str, Any], name: str) -> tuple[str, int]:
    raw = files.get(name)
    if not isinstance(raw, Mapping):
        raise HostileTwinExecutionError(f"declared file metadata missing: {name}")
    digest = raw.get("sha256")
    size = raw.get("size_bytes")
    if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise HostileTwinExecutionError(f"invalid declared file digest: {name}")
    if type(size) is not int or size < 0:
        raise HostileTwinExecutionError(f"invalid declared file size: {name}")
    return digest, size


def _receipt_from_mapping(raw: Mapping[str, Any]) -> ReleaseArchiveReceipt:
    try:
        return ReleaseArchiveReceipt(
            release_id=raw["release_id"],
            source_commit=raw["source_commit"],
            source_tree=raw["source_tree"],
            build_id=raw["build_id"],
            archive_policy_id=raw["archive_policy_id"],
            archive_policy_sha256=raw["archive_policy_sha256"],
            manifest_path=raw["manifest_path"],
            manifest_sha256=raw["manifest_sha256"],
            archive_sha256=raw["archive_sha256"],
            archive_size=raw["archive_size"],
            member_count=raw["member_count"],
            evidence_scope=raw.get("evidence_scope", "DETERMINISTIC_RELEASE_ZIP_REPOSITORY_COMPONENT_ONLY_NO_INSTALL_RUNTIME_OR_COMPLETION_CREDIT"),
            schema=raw.get("schema", "FRANKENSTEIN2_RELEASE_ARCHIVE_RECEIPT/v1"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HostileTwinExecutionError("invalid current bundle archive receipt") from exc


def _policy_from_archive(index: Mapping[str, Any], archive_bytes: bytes) -> ReleaseArchivePolicy:
    source_epoch = index.get("source_date_epoch")
    if type(source_epoch) is not int:
        raise HostileTwinExecutionError("current bundle source_date_epoch missing")
    archive_meta = index.get("archive")
    if not isinstance(archive_meta, Mapping):
        raise HostileTwinExecutionError("current bundle archive metadata missing")
    policy_id = archive_meta.get("policy_id")
    if not isinstance(policy_id, str):
        raise HostileTwinExecutionError("current bundle archive policy id missing")

    executable: list[str] = []
    try:
        with zipfile.ZipFile(Path("unused"), "r"):
            pass
    except (FileNotFoundError, zipfile.BadZipFile):
        pass
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            for info in archive.infolist():
                mode = stat.S_IMODE(info.external_attr >> 16)
                if mode == 0o755:
                    executable.append(info.filename)
                elif mode != 0o644:
                    raise HostileTwinExecutionError(
                        f"current release member has unsupported mode {mode:o}: {info.filename}"
                    )
    except zipfile.BadZipFile as exc:
        raise HostileTwinExecutionError("current bundle release archive is not a ZIP") from exc

    try:
        policy = ReleaseArchivePolicy(
            policy_id=policy_id,
            source_date_epoch=source_epoch,
            executable_paths=tuple(sorted(executable)),
        )
    except (TypeError, ValueError) as exc:
        raise HostileTwinExecutionError("cannot reconstruct current bundle archive policy") from exc
    if policy.digest() != archive_meta.get("policy_sha256"):
        raise HostileTwinExecutionError("reconstructed archive policy digest mismatch")
    return policy


def from_current_release_bundle(bundle_path: str | Path) -> BoundReleaseCandidate:
    """Validate one WP1113 Actions-artifact ZIP and return the existing WP1207 candidate type."""

    path = Path(bundle_path)
    if path.is_symlink() or not path.is_file():
        raise HostileTwinExecutionError("current release bundle must be a regular non-symlink file")
    outer = path.read_bytes()
    outer_sha = _sha256(outer)
    try:
        archive = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile as exc:
        raise HostileTwinExecutionError("invalid current release bundle ZIP") from exc

    with archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise HostileTwinExecutionError("duplicate current bundle member")
        if CURRENT_INDEX_NAME not in names:
            raise HostileTwinExecutionError("current release bundle index missing")
        index = _json_object(archive.read(CURRENT_INDEX_NAME), name="current release bundle index")
        if index.get("schema") != CURRENT_BUNDLE_SCHEMA:
            raise HostileTwinExecutionError("current release bundle schema mismatch")

        source_commit = _hex40(index.get("source_commit"), field="source_commit")
        _hex40(index.get("source_tree"), field="source_tree")
        release_id = index.get("release_id")
        if release_id != f"frankenstein-2.0-{source_commit[:12]}":
            raise HostileTwinExecutionError("current release id disagrees with exact source commit")

        files = index.get("files")
        if not isinstance(files, Mapping) or not files:
            raise HostileTwinExecutionError("current release bundle declared files missing")
        declared_names = {_simple_member(name, field="declared bundle filename") for name in files}
        if set(names) != declared_names | {CURRENT_INDEX_NAME}:
            raise HostileTwinExecutionError("current release bundle contains missing or undeclared members")
        for name in sorted(declared_names):
            data = archive.read(name)
            expected_sha, expected_size = _file_meta(files, name)
            if _sha256(data) != expected_sha or len(data) != expected_size:
                raise HostileTwinExecutionError(f"current release bundle member mismatch: {name}")

        archive_meta = index.get("archive")
        if not isinstance(archive_meta, Mapping):
            raise HostileTwinExecutionError("current release archive metadata missing")
        artifact_filename = _simple_member(archive_meta.get("filename"), field="archive filename")
        archive_bytes = archive.read(artifact_filename)
        if _sha256(archive_bytes) != archive_meta.get("sha256") or len(archive_bytes) != archive_meta.get("size_bytes"):
            raise HostileTwinExecutionError("current release archive bytes mismatch")

        receipt_name = "frankenstein-2.0-archive-receipt.json"
        receipt_raw = _json_object(archive.read(receipt_name), name="archive receipt")
        expected_receipt = _receipt_from_mapping(receipt_raw)
        if expected_receipt.digest() != archive_meta.get("receipt_sha256"):
            raise HostileTwinExecutionError("current release archive receipt digest mismatch")
        if expected_receipt.source_commit != source_commit or expected_receipt.source_tree != index.get("source_tree"):
            raise HostileTwinExecutionError("current release archive receipt source identity mismatch")
        if expected_receipt.release_id != release_id or expected_receipt.build_id != index.get("build_id"):
            raise HostileTwinExecutionError("current release archive receipt release identity mismatch")

        policy = _policy_from_archive(index, archive_bytes)
        observed_receipt = verify_release_archive(
            archive_bytes,
            policy=policy,
            expected_receipt=expected_receipt,
            manifest_path=expected_receipt.manifest_path,
        )
        if observed_receipt.as_dict() != expected_receipt.as_dict():
            raise HostileTwinExecutionError("current release archive receipt mapping mismatch")
        if observed_receipt.archive_sha256 != archive_meta.get("sha256"):
            raise HostileTwinExecutionError("current release archive digest disagrees with index")
        if observed_receipt.manifest_sha256 != archive_meta.get("manifest_sha256"):
            raise HostileTwinExecutionError("current release manifest digest disagrees with index")
        if observed_receipt.member_count != archive_meta.get("member_count"):
            raise HostileTwinExecutionError("current release archive member count disagrees with index")

        prehandoff = index.get("prehandoff_receipt")
        subject = index.get("artifact_subject")
        static = index.get("artifact_bound_static_completeness")
        if not isinstance(prehandoff, Mapping) or not isinstance(subject, Mapping) or not isinstance(static, Mapping):
            raise HostileTwinExecutionError("current release bound receipt metadata missing")
        prehandoff_name = _simple_member(prehandoff.get("filename"), field="pre-handoff filename")
        prehandoff_bytes = archive.read(prehandoff_name)
        if _sha256(prehandoff_bytes) != prehandoff.get("sha256"):
            raise HostileTwinExecutionError("current pre-handoff receipt digest mismatch")
        if subject.get("artifact_bound_prehandoff_sha256") != prehandoff.get("sha256"):
            raise HostileTwinExecutionError("artifact subject and pre-handoff receipt disagree")

        content_name = "frankenstein-2.0-content-bound-prehandoff.json"
        content_bytes = archive.read(content_name)
        if _sha256(content_bytes) != prehandoff.get("content_bound_sha256"):
            raise HostileTwinExecutionError("current content-bound receipt digest mismatch")

        static_name = _simple_member(static.get("filename"), field="static completeness filename")
        static_bytes = archive.read(static_name)
        if _sha256(static_bytes) != static.get("sha256"):
            raise HostileTwinExecutionError("current static-completeness receipt digest mismatch")
        if static.get("artifact_sha256") != observed_receipt.archive_sha256:
            raise HostileTwinExecutionError("static completeness artifact digest disagrees with archive")
        if static.get("release_manifest_sha256") != observed_receipt.manifest_sha256:
            raise HostileTwinExecutionError("static completeness manifest digest disagrees with archive")
        if static.get("artifact_subject_sha256") != subject.get("sha256"):
            raise HostileTwinExecutionError("static completeness artifact subject disagrees with index")

        credits = index.get("credits")
        if not isinstance(credits, Mapping) or credits.get("repository_release_build_credit") != 1:
            raise HostileTwinExecutionError("current release bundle repository-build credit missing")
        for key in (
            "clean_machine_runtime_credit", "physical_host_credit", "vps_runtime_credit",
            "provider_model_credit", "effect_credit", "completion_credit",
        ):
            if credits.get(key) != 0:
                raise HostileTwinExecutionError(f"current release bundle illegally pre-mints {key}")
        if credits.get("whole_system_acceptance") is not False:
            raise HostileTwinExecutionError("current release bundle illegally pre-mints whole-system acceptance")

    release = ReleaseIdentity(
        schema=RELEASE_SCHEMA,
        release_id=release_id,
        version=f"git-{source_commit[:12]}",
        artifact_sha256=observed_receipt.archive_sha256,
        manifest_sha256=observed_receipt.manifest_sha256,
    )
    return BoundReleaseCandidate(
        outer_sha256=outer_sha,
        artifact_filename=artifact_filename,
        archive_bytes=archive_bytes,
        archive_policy=policy,
        archive_receipt=observed_receipt,
        release_identity=release,
        portable_release_digest=release.digest(),
        artifact_bound_receipt_sha256=_sha256(prehandoff_bytes),
        content_bound_receipt_sha256=_sha256(content_bytes),
    )
