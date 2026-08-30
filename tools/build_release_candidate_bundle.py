#!/usr/bin/env python3
"""Build one exact Frankenstein 2.0 release-candidate evidence bundle from a Git commit.

F2-WP-1207 generation 3.

This is repository-hosted release-candidate materialization only. It composes the
already accepted WP1107/WP1110 identities and WP1207 transaction identity; it does
not install the release, mutate a target, grant runtime/effect/completion credit, or
replace any existing verifier.

The package payload is reconstructed from the exact Git tree rather than the ambient
checkout so untracked/dirty files cannot silently enter the release artifact.
"""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
from typing import Any

from frankenstein2.portable_release_transaction import ReleaseIdentity
from frankenstein2.receipt_content_binding import (
    ContentBoundPreHandoffReceipt,
    bind_prehandoff_receipt_content,
)
from frankenstein2.release_archive import (
    ReleaseArchiveBuild,
    ReleaseArchivePolicy,
    verify_release_archive,
    build_release_archive,
)
from frankenstein2.release_artifact_subject import (
    ArtifactBoundPreHandoffReceipt,
    bind_release_artifact_subject,
)

BUNDLE_SCHEMA = "FRANKENSTEIN2_RELEASE_CANDIDATE_EVIDENCE_BUNDLE/v1"
BUNDLE_SCOPE = (
    "EXACT_GIT_TREE_RELEASE_CANDIDATE_PLUS_EXTERNAL_PREHANDOFF_RECEIPT_"
    "MATERIALIZATION_REPOSITORY_HOSTED_ONLY_NO_TARGET_RUNTIME_EFFECT_OR_COMPLETION_CREDIT"
)


class ReleaseCandidateBundleError(RuntimeError):
    """Exact release-candidate bundle cannot be produced safely."""


def _run_git(repo_root: Path, *args: str, text: bool = True) -> str | bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr if text else proc.stderr.decode("utf-8", "replace")
        raise ReleaseCandidateBundleError(
            f"git {' '.join(args)} failed: {stderr.strip()}"
        )
    return proc.stdout


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_new_or_identical(
    output_root: Path,
    relative_path: str | PurePosixPath,
    data: bytes,
) -> Path:
    """Materialize immutable evidence without following output-tree symlinks."""

    rel = _safe_relpath(str(relative_path))
    root = output_root.absolute()
    if root.is_symlink() or not root.is_dir():
        raise ReleaseCandidateBundleError("output root must be a real directory")

    parent = root
    for part in rel.parts[:-1]:
        parent = parent / part
        try:
            parent.mkdir()
        except FileExistsError:
            pass
        if parent.is_symlink() or not parent.is_dir():
            raise ReleaseCandidateBundleError(
                f"output path contains a symlink or non-directory: {rel.as_posix()!r}"
            )

    destination = parent / rel.name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(destination, flags, 0o600)
    except FileExistsError:
        if destination.is_symlink() or not destination.is_file():
            raise ReleaseCandidateBundleError(
                f"output evidence path is a symlink or non-file: {rel.as_posix()!r}"
            )
        if destination.read_bytes() != data:
            raise ReleaseCandidateBundleError(
                f"output evidence already exists with different bytes: {rel.as_posix()!r}"
            )
        return destination
    except OSError as exc:
        raise ReleaseCandidateBundleError(
            f"cannot create output evidence safely: {rel.as_posix()!r}"
        ) from exc

    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            destination.unlink()
        except OSError:
            pass
        raise
    return destination


def _safe_relpath(name: str) -> PurePosixPath:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise ReleaseCandidateBundleError(f"unsafe Git archive path: {name!r}")
    try:
        name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ReleaseCandidateBundleError(
            f"generation-2 release policy requires ASCII paths: {name!r}"
        ) from exc
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseCandidateBundleError(f"unsafe Git archive path: {name!r}")
    if path.as_posix() != name.rstrip("/"):
        raise ReleaseCandidateBundleError(f"non-canonical Git archive path: {name!r}")
    return path


@dataclass(frozen=True, slots=True)
class MaterializedGitTree:
    root: Path
    commit_sha: str
    tree_sha: str
    source_date_epoch: int
    executable_paths: tuple[str, ...]
    regular_file_count: int


@dataclass(frozen=True, slots=True)
class ReleaseCandidateBundle:
    artifact_path: Path
    artifact_bound_receipt_path: Path
    content_bound_receipt_path: Path
    bundle_index_path: Path
    archive_build: ReleaseArchiveBuild
    artifact_bound_prehandoff: ArtifactBoundPreHandoffReceipt
    content_bound_prehandoff: ContentBoundPreHandoffReceipt
    bundle_index: dict[str, Any]


def materialize_exact_git_tree(repo_root: str | Path, staging_root: str | Path) -> MaterializedGitTree:
    """Materialize only regular tracked bytes from exact HEAD into a clean staging root."""

    repo = Path(repo_root).resolve(strict=True)
    if not (repo / ".git").exists():
        raise ReleaseCandidateBundleError("repo_root must be a Git working tree")

    commit_sha = str(_run_git(repo, "rev-parse", "HEAD")).strip()
    tree_sha = str(_run_git(repo, "show", "-s", "--format=%T", commit_sha)).strip()
    epoch_raw = str(_run_git(repo, "show", "-s", "--format=%ct", commit_sha)).strip()
    try:
        source_date_epoch = int(epoch_raw)
    except ValueError as exc:
        raise ReleaseCandidateBundleError("commit timestamp is not an integer epoch") from exc

    archive_bytes = _run_git(repo, "archive", "--format=tar", commit_sha, text=False)
    assert isinstance(archive_bytes, bytes)

    stage = Path(staging_root)
    stage.mkdir(parents=True, exist_ok=False)
    executables: list[str] = []
    regular_count = 0

    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        for member in archive.getmembers():
            raw_name = member.name.rstrip("/") if member.isdir() else member.name
            rel = _safe_relpath(raw_name)
            if member.isdir():
                stage.joinpath(*rel.parts).mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ReleaseCandidateBundleError(
                    f"non-regular tracked entry forbidden in release tree: {member.name!r}"
                )
            fileobj = archive.extractfile(member)
            if fileobj is None:
                raise ReleaseCandidateBundleError(
                    f"cannot read tracked release member: {member.name!r}"
                )
            data = fileobj.read()
            target = stage.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            regular_count += 1
            if member.mode & 0o111:
                executables.append(rel.as_posix())

    if regular_count < 1:
        raise ReleaseCandidateBundleError("exact Git tree contains no regular files")

    return MaterializedGitTree(
        root=stage,
        commit_sha=commit_sha,
        tree_sha=tree_sha,
        source_date_epoch=source_date_epoch,
        executable_paths=tuple(sorted(executables)),
        regular_file_count=regular_count,
    )


def build_release_candidate_bundle(
    repo_root: str | Path,
    output_dir: str | Path,
) -> ReleaseCandidateBundle:
    """Build and reverify exact ZIP + external receipt-content evidence."""

    repo = Path(repo_root).resolve(strict=True)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    staging = output / ".staging"
    if staging.exists():
        raise ReleaseCandidateBundleError("staging path already exists")

    materialized = materialize_exact_git_tree(repo, staging)
    short = materialized.commit_sha[:12]
    release_id = f"frankenstein-2.0-{short}"
    build_id = f"git-tree-{short}"
    artifact_filename = f"{release_id}.zip"
    receipt_ref = (
        f"external-receipts/{artifact_filename}.artifact-bound-prehandoff.json"
    )

    policy = ReleaseArchivePolicy(
        policy_id=f"f2-git-tree-{short}-stored-posix-v1",
        source_date_epoch=materialized.source_date_epoch,
        executable_paths=materialized.executable_paths,
    )
    archive_build = build_release_archive(
        materialized.root,
        release_id=release_id,
        source_commit=materialized.commit_sha,
        source_tree=materialized.tree_sha,
        build_id=build_id,
        policy=policy,
        prehandoff_receipt_refs=(receipt_ref,),
    )
    artifact_path = _write_new_or_identical(
        output,
        artifact_filename,
        archive_build.archive_bytes,
    )

    # Re-open exact artifact bytes through the already accepted WP1107 verifier before
    # constructing any higher composition receipt.
    observed_archive = verify_release_archive(
        artifact_path.read_bytes(),
        policy=policy,
        expected_receipt=archive_build.receipt,
    )
    if observed_archive != archive_build.receipt:
        raise ReleaseCandidateBundleError("post-write archive receipt differs from build receipt")

    artifact_bound = bind_release_artifact_subject(
        artifact_path,
        policy=policy,
        prehandoff_receipt_ref=receipt_ref,
        expected_archive_receipt=archive_build.receipt,
    )
    if artifact_bound.status != "READY_FOR_REAL_HOST_HANDOFF":
        raise ReleaseCandidateBundleError(
            f"artifact-bound prehandoff is not ready: {artifact_bound.static_violations}"
        )

    artifact_bound_bytes = artifact_bound.canonical_bytes()
    artifact_bound_path = _write_new_or_identical(
        output,
        receipt_ref,
        artifact_bound_bytes,
    )

    content_bound = bind_prehandoff_receipt_content(
        artifact_bound,
        prehandoff_receipt_ref=receipt_ref,
        prehandoff_receipt_bytes=artifact_bound_path.read_bytes(),
    )
    if content_bound.status != "READY_FOR_REAL_HOST_HANDOFF":
        raise ReleaseCandidateBundleError("receipt-content binding is not ready")

    content_bound_ref = PurePosixPath(receipt_ref).with_name(
        PurePosixPath(receipt_ref).name.replace(
            ".artifact-bound-prehandoff.json",
            ".content-bound-prehandoff.json",
        )
    )
    content_bound_path = _write_new_or_identical(
        output,
        content_bound_ref,
        content_bound.canonical_bytes(),
    )

    portable_identity = ReleaseIdentity(
        schema="FRANKENSTEIN2_PORTABLE_RELEASE_IDENTITY/v1",
        release_id=release_id,
        version=f"git-{short}",
        artifact_sha256=archive_build.receipt.archive_sha256,
        manifest_sha256=archive_build.receipt.manifest_sha256,
    )

    index: dict[str, Any] = {
        "schema": BUNDLE_SCHEMA,
        "evidence_scope": BUNDLE_SCOPE,
        "source": {
            "commit_sha": materialized.commit_sha,
            "tree_sha": materialized.tree_sha,
            "source_date_epoch": materialized.source_date_epoch,
            "regular_file_count": materialized.regular_file_count,
        },
        "archive_policy": policy.as_dict(),
        "release_archive_receipt": archive_build.receipt.as_dict(),
        "artifact": {
            "filename": artifact_path.name,
            "sha256": _sha256(artifact_path.read_bytes()),
            "size_bytes": artifact_path.stat().st_size,
        },
        "artifact_bound_prehandoff": {
            "ref": receipt_ref,
            "sha256": _sha256(artifact_bound_path.read_bytes()),
            "size_bytes": artifact_bound_path.stat().st_size,
            "subject_sha256": artifact_bound.subject.sha256(),
            "status": artifact_bound.status,
        },
        "receipt_content_binding": {
            "content_bound_receipt_filename": content_bound_path.name,
            "content_bound_receipt_sha256": _sha256(content_bound_path.read_bytes()),
            "content_bound_receipt_size_bytes": content_bound_path.stat().st_size,
            "receipt_content_subject_sha256": (
                content_bound.receipt_content_subject.sha256()
            ),
            "status": content_bound.status,
        },
        "portable_release_identity": portable_identity.as_dict(),
        "portable_release_digest": portable_identity.digest(),
        "credits": {
            "target_runtime": 0,
            "physical_host": 0,
            "effect": 0,
            "completion": 0,
            "grid10_runtime": 0,
            "gwt_runtime": 0,
            "jspace_runtime": 0,
            "training": 0,
            "whole_system_acceptance": False,
        },
        "next_gate": (
            "ADMITTED_WP1207_HOSTILE_TWIN_INSTALL_UPDATE_FAILURE_ROLLBACK_AND_"
            "RELEASE_READBACK_USING_THIS_EXACT_ARTIFACT_AND_RECEIPT_SUBJECT"
        ),
    }
    index_path = output / "RELEASE_CANDIDATE_BUNDLE.json"
    index_path = _write_new_or_identical(
        output,
        index_path.name,
        _canonical_json(index),
    )

    # The staging directory is not evidence and must not enter the uploaded artifact.
    import shutil
    shutil.rmtree(staging)

    return ReleaseCandidateBundle(
        artifact_path=artifact_path,
        artifact_bound_receipt_path=artifact_bound_path,
        content_bound_receipt_path=content_bound_path,
        bundle_index_path=index_path,
        archive_build=archive_build,
        artifact_bound_prehandoff=artifact_bound,
        content_bound_prehandoff=content_bound,
        bundle_index=index,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    bundle = build_release_candidate_bundle(args.repo_root, args.output_dir)
    print(bundle.bundle_index_path.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
