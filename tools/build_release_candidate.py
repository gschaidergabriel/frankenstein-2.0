#!/usr/bin/env python3
"""Build one deterministic Frankenstein 2.0 release candidate from exact Git tree bytes.

This is a Stage-11 production harness around the already accepted WP1107/WP1110
components. It does not create a new release-integrity authority and does not mint
clean-machine, target-host, effect, completion, or whole-system credit.

The payload source is the exact current Git tree, not the ambient checkout:

    HEAD tree -> canonical regular blobs/modes -> WP1107 deterministic ZIP
              -> WP1110 exact unopened-artifact subject
              -> WP1110 exact external pre-handoff receipt-content subject

Untracked files and checkout-local mutations cannot enter the payload. Git symlinks,
gitlinks/submodules, non-regular modes, non-UTF-8 paths, and non-ASCII paths fail closed.
The external pre-handoff receipt is materialized at the exact canonical relative path
declared in the release manifest; declared-reference/path divergence fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from frankenstein2.pre_handoff_release import READY_STATUS
from frankenstein2.receipt_content_binding import bind_prehandoff_receipt_content
from frankenstein2.release_archive import (
    ReleaseArchivePolicy,
    build_release_archive,
    verify_release_archive,
    write_release_archive,
)
from frankenstein2.release_artifact_subject import bind_release_artifact_subject

SCHEMA = "FRANKENSTEIN2_RELEASE_CANDIDATE_BUNDLE/v1"
DEFAULT_ARTIFACT = "frankenstein-2.0.zip"
DEFAULT_PREHANDOFF_REF = "release-receipts/frankenstein-2.0-prehandoff.json"
DEFAULT_POLICY_ID = "f2-release-zip-stored-posix-v1"
ALLOWED_GIT_MODES = {"100644", "100755"}


class ReleaseCandidateBuildError(RuntimeError):
    """Exact-source release candidate cannot be produced safely."""


def _git_bytes(*args: str) -> bytes:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT)
    except subprocess.CalledProcessError as exc:
        raise ReleaseCandidateBuildError(f"git {' '.join(args)} failed") from exc


def _git_text(*args: str) -> str:
    try:
        return _git_bytes(*args).decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ReleaseCandidateBuildError(f"git {' '.join(args)} returned non-UTF-8 text") from exc


def _canonical_path(raw: bytes) -> str:
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseCandidateBuildError("release tree contains a non-UTF-8 path") from exc
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ReleaseCandidateBuildError(f"release tree contains a non-ASCII path: {value!r}") from exc
    if "\\" in value or "\x00" in value:
        raise ReleaseCandidateBuildError(f"non-canonical release path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseCandidateBuildError(f"unsafe release path: {value!r}")
    if path.as_posix() != value:
        raise ReleaseCandidateBuildError(f"release path is not canonical POSIX: {value!r}")
    return value


def _canonical_output_ref(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReleaseCandidateBuildError(f"{name} must be a non-empty already-trimmed string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ReleaseCandidateBuildError(f"{name} contains control characters")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ReleaseCandidateBuildError(f"{name} must be ASCII") from exc
    if "\\" in value or "\x00" in value:
        raise ReleaseCandidateBuildError(f"{name} is not canonical POSIX")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseCandidateBuildError(f"{name} is not a safe relative path")
    if path.as_posix() != value:
        raise ReleaseCandidateBuildError(f"{name} is not canonical POSIX")
    return value


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _write_exact_declared_receipt(
    output_dir: Path,
    receipt_ref: str,
    exact_bytes: bytes,
) -> Path:
    """Write exact receipt bytes only at the declared relative reference.

    Parent symlink escapes and same-reference/different-bytes replacement fail closed.
    Existing byte-identical content is accepted as an idempotent rebuild.
    """

    if type(exact_bytes) is not bytes or not exact_bytes:
        raise ReleaseCandidateBuildError("external pre-handoff receipt bytes must be non-empty exact bytes")
    output_root = output_dir.resolve(strict=True)
    relative = PurePosixPath(receipt_ref)
    target = output_root.joinpath(*relative.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = target.parent.resolve(strict=True)
    if not _is_within(resolved_parent, output_root):
        raise ReleaseCandidateBuildError("pre-handoff receipt parent escapes output directory")
    if target.is_symlink():
        raise ReleaseCandidateBuildError("pre-handoff receipt path must not be a symlink")
    if target.exists():
        if not target.is_file():
            raise ReleaseCandidateBuildError("pre-handoff receipt path exists but is not a regular file")
        if target.read_bytes() != exact_bytes:
            raise ReleaseCandidateBuildError(
                "declared pre-handoff receipt already exists with different bytes"
            )
        return target
    try:
        with target.open("xb") as handle:
            handle.write(exact_bytes)
    except FileExistsError as exc:
        raise ReleaseCandidateBuildError(
            "pre-handoff receipt appeared concurrently; exact readback required"
        ) from exc
    if target.read_bytes() != exact_bytes:
        raise ReleaseCandidateBuildError("pre-handoff receipt readback mismatch")
    return target


def _tree_entries() -> tuple[tuple[str, str, str, str], ...]:
    raw = _git_bytes("ls-tree", "-r", "-z", "HEAD")
    entries: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for record in raw.split(b"\x00"):
        if not record:
            continue
        try:
            meta, raw_path = record.split(b"\t", 1)
            mode_b, type_b, object_b = meta.split(b" ", 2)
            mode = mode_b.decode("ascii")
            object_type = type_b.decode("ascii")
            object_id = object_b.decode("ascii")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ReleaseCandidateBuildError("malformed git ls-tree record") from exc
        path = _canonical_path(raw_path)
        if path in seen:
            raise ReleaseCandidateBuildError(f"duplicate Git tree path: {path}")
        seen.add(path)
        if mode not in ALLOWED_GIT_MODES or object_type != "blob":
            raise ReleaseCandidateBuildError(
                f"unsupported release tree entry {path!r}: mode={mode} type={object_type}; "
                "symlinks, gitlinks/submodules, and non-regular entries are forbidden"
            )
        if len(object_id) not in {40, 64} or any(ch not in "0123456789abcdef" for ch in object_id):
            raise ReleaseCandidateBuildError(f"invalid Git object id for {path}")
        entries.append((path, mode, object_type, object_id))
    if not entries:
        raise ReleaseCandidateBuildError("Git tree contains no release files")
    entries.sort(key=lambda item: item[0])
    return tuple(entries)


def _materialize_exact_tree(destination: Path, entries: Iterable[tuple[str, str, str, str]]) -> tuple[str, ...]:
    entries = tuple(entries)
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdin is None or process.stdout is None:
        process.kill()
        raise ReleaseCandidateBuildError("failed to open git cat-file batch pipes")
    executable_paths: list[str] = []
    try:
        for path, mode, _object_type, object_id in entries:
            process.stdin.write((object_id + "\n").encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline()
            parts = header.rstrip(b"\n").split(b" ")
            if len(parts) != 3 or parts[0].decode("ascii", "replace") != object_id or parts[1] != b"blob":
                raise ReleaseCandidateBuildError(f"unexpected git cat-file header for {path}: {header!r}")
            try:
                size = int(parts[2])
            except ValueError as exc:
                raise ReleaseCandidateBuildError(f"invalid Git blob size for {path}") from exc
            data = process.stdout.read(size)
            separator = process.stdout.read(1)
            if len(data) != size or separator != b"\n":
                raise ReleaseCandidateBuildError(f"truncated Git blob stream for {path}")
            target = destination.joinpath(*PurePosixPath(path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if mode == "100755":
                executable_paths.append(path)
        process.stdin.close()
        return_code = process.wait(timeout=30)
        if return_code != 0:
            stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
            raise ReleaseCandidateBuildError(f"git cat-file --batch failed: {stderr.strip()}")
    except Exception:
        process.kill()
        process.wait()
        raise
    return tuple(sorted(executable_paths))


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_bundle(output_dir: Path, *, artifact_filename: str, prehandoff_receipt_ref: str) -> dict[str, object]:
    source_commit = _git_text("rev-parse", "HEAD")
    source_tree = _git_text("rev-parse", "HEAD^{tree}")
    source_epoch_text = _git_text("show", "-s", "--format=%ct", "HEAD")
    try:
        source_epoch = int(source_epoch_text)
    except ValueError as exc:
        raise ReleaseCandidateBuildError("HEAD commit timestamp is not an integer") from exc

    expected_source = None
    import os
    expected_source = os.environ.get("EXPECTED_SOURCE_SHA")
    if expected_source and source_commit != expected_source:
        raise ReleaseCandidateBuildError(
            f"source identity mismatch: HEAD={source_commit} EXPECTED_SOURCE_SHA={expected_source}"
        )

    if Path(artifact_filename).name != artifact_filename or artifact_filename in {".", ".."}:
        raise ReleaseCandidateBuildError("artifact filename must be a simple basename")
    prehandoff_receipt_ref = _canonical_output_ref(
        prehandoff_receipt_ref, "prehandoff_receipt_ref"
    )
    if prehandoff_receipt_ref == artifact_filename:
        raise ReleaseCandidateBuildError(
            "pre-handoff receipt reference must not alias release artifact"
        )

    entries = _tree_entries()
    release_id = f"frankenstein-2.0-{source_commit[:12]}"
    build_id = f"trigger4-release-{source_commit[:12]}"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="f2-release-tree-") as temporary:
        staging = Path(temporary)
        executable_paths = _materialize_exact_tree(staging, entries)
        policy = ReleaseArchivePolicy(
            policy_id=DEFAULT_POLICY_ID,
            source_date_epoch=source_epoch,
            executable_paths=executable_paths,
        )
        build = build_release_archive(
            staging,
            release_id=release_id,
            source_commit=source_commit,
            source_tree=source_tree,
            build_id=build_id,
            policy=policy,
            prehandoff_receipt_refs=(prehandoff_receipt_ref,),
        )

    artifact_path = write_release_archive(output_dir / artifact_filename, build)
    observed_archive = verify_release_archive(
        artifact_path.read_bytes(),
        policy=policy,
        expected_receipt=build.receipt,
    )
    if observed_archive != build.receipt:
        raise ReleaseCandidateBuildError("post-write archive verification changed receipt identity")

    artifact_bound = bind_release_artifact_subject(
        artifact_path,
        policy=policy,
        prehandoff_receipt_ref=prehandoff_receipt_ref,
        expected_archive_receipt=build.receipt,
    )
    if artifact_bound.status != READY_STATUS or artifact_bound.static_violations:
        raise ReleaseCandidateBuildError(
            f"artifact-bound pre-handoff is not ready: status={artifact_bound.status} "
            f"violations={artifact_bound.static_violations}"
        )

    external_prehandoff_bytes = artifact_bound.canonical_bytes()
    external_prehandoff_path = _write_exact_declared_receipt(
        output_dir,
        prehandoff_receipt_ref,
        external_prehandoff_bytes,
    )
    materialized_ref = external_prehandoff_path.relative_to(output_dir).as_posix()
    if materialized_ref != prehandoff_receipt_ref:
        raise ReleaseCandidateBuildError(
            "materialized pre-handoff receipt path differs from declared reference"
        )
    external_prehandoff_readback = external_prehandoff_path.read_bytes()

    content_bound = bind_prehandoff_receipt_content(
        artifact_bound,
        prehandoff_receipt_ref=prehandoff_receipt_ref,
        prehandoff_receipt_bytes=external_prehandoff_readback,
    )
    if content_bound.status != READY_STATUS:
        raise ReleaseCandidateBuildError(f"receipt-content binding is not ready: {content_bound.status}")

    archive_receipt_path = output_dir / "frankenstein-2.0-archive-receipt.json"
    archive_receipt_path.write_bytes(build.receipt.canonical_bytes())
    content_bound_path = output_dir / "frankenstein-2.0-content-bound-prehandoff.json"
    content_bound_path.write_bytes(content_bound.canonical_bytes())

    bundle = {
        "schema": SCHEMA,
        "classification": "EXACT_GIT_TREE_DETERMINISTIC_RELEASE_CANDIDATE_REPOSITORY_BUILD_ONLY",
        "source_commit": source_commit,
        "source_tree": source_tree,
        "source_date_epoch": source_epoch,
        "release_id": release_id,
        "build_id": build_id,
        "tracked_regular_file_count": len(entries),
        "tracked_executable_file_count": len(executable_paths),
        "archive": {
            "filename": artifact_filename,
            "sha256": build.receipt.archive_sha256,
            "size_bytes": build.receipt.archive_size,
            "member_count": build.receipt.member_count,
            "manifest_sha256": build.receipt.manifest_sha256,
            "policy_id": policy.policy_id,
            "policy_sha256": policy.digest(),
            "receipt_sha256": build.receipt.digest(),
        },
        "artifact_subject": {
            "sha256": artifact_bound.subject.sha256(),
            "artifact_bound_prehandoff_sha256": artifact_bound.sha256(),
            "status": artifact_bound.status,
            "static_status": artifact_bound.static_status,
            "static_violations": list(artifact_bound.static_violations),
        },
        "prehandoff_receipt": {
            "declared_ref": prehandoff_receipt_ref,
            "materialized_ref": materialized_ref,
            "sha256": _sha256(external_prehandoff_readback),
            "size_bytes": len(external_prehandoff_readback),
            "content_subject_sha256": content_bound.receipt_content_subject.sha256(),
            "content_bound_sha256": content_bound.sha256(),
            "content_bound_status": content_bound.status,
        },
        "files": {
            artifact_path.name: {"sha256": _sha256(artifact_path.read_bytes()), "size_bytes": artifact_path.stat().st_size},
            archive_receipt_path.name: {"sha256": _sha256(archive_receipt_path.read_bytes()), "size_bytes": archive_receipt_path.stat().st_size},
            materialized_ref: {"sha256": _sha256(external_prehandoff_readback), "size_bytes": external_prehandoff_path.stat().st_size},
            content_bound_path.name: {"sha256": _sha256(content_bound_path.read_bytes()), "size_bytes": content_bound_path.stat().st_size},
        },
        "credits": {
            "repository_release_build_credit": 1,
            "clean_machine_runtime_credit": 0,
            "physical_host_credit": 0,
            "vps_runtime_credit": 0,
            "provider_model_credit": 0,
            "effect_credit": 0,
            "completion_credit": 0,
            "whole_system_acceptance": False,
        },
        "next_exact_action": (
            "Run the exact archive plus exact external pre-handoff receipt bytes on real clean-machine "
            "Claude Code, Codex CLI, other-agent, no-VPS baseline, and VPS-bridge cases; bind every "
            "observation to these same artifact and receipt-content subjects before any runtime promotion."
        ),
    }
    index_path = output_dir / "release-bundle-index.json"
    index_path.write_bytes(_json_bytes(bundle))
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("dist/release-candidate"))
    parser.add_argument("--artifact-filename", default=DEFAULT_ARTIFACT)
    parser.add_argument("--prehandoff-receipt-ref", default=DEFAULT_PREHANDOFF_REF)
    args = parser.parse_args()
    bundle = build_bundle(
        args.output_dir,
        artifact_filename=args.artifact_filename,
        prehandoff_receipt_ref=args.prehandoff_receipt_ref,
    )
    print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
