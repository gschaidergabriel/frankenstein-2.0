#!/usr/bin/env python3
"""Post-build WP1111 gate for one exact deterministic F2 release candidate.

This verifier composes the existing release-candidate builder with the accepted
F2-WP-1111 portable static-completeness gate. It does not create a second release
integrity authority and does not mint clean-machine, target-host, VPS, effect,
completion, or whole-system credit.

The existing builder remains authoritative for deterministic archive construction.
This verifier binds the produced archive bytes back to release-bundle-index.json,
materializes only canonical regular ZIP members into a temporary directory, and runs
the existing WP1111 gate against that exact archive payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile
from typing import Any

from frankenstein2.portable_release_static_completeness import (
    STATIC_COMPLETE,
    evaluate_portable_release_static_completeness,
)

SCHEMA = "FRANKENSTEIN2_RELEASE_CANDIDATE_STATIC_COMPLETENESS/v1"
DEFAULT_INDEX = "release-bundle-index.json"
DEFAULT_RECEIPT = "frankenstein-2.0-static-completeness.json"
EVIDENCE_SCOPE = (
    "EXACT_RELEASE_ARCHIVE_POST_BUILD_STATIC_COMPLETENESS_REPOSITORY_CI_ONLY_"
    "NO_RUNTIME_EFFECT_OR_COMPLETION_CREDIT"
)


class ReleaseCandidateStaticCompletenessError(RuntimeError):
    """The exact built release candidate cannot pass the WP1111 post-build gate."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_index(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseCandidateStaticCompletenessError(
            f"release bundle index is unreadable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise ReleaseCandidateStaticCompletenessError("release bundle index root must be an object")
    return value


def _canonical_member(raw: str) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise ReleaseCandidateStaticCompletenessError(f"non-canonical archive member: {raw!r}")
    try:
        raw.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ReleaseCandidateStaticCompletenessError(
            f"non-ASCII archive member is outside the accepted release ABI: {raw!r}"
        ) from exc
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != raw
    ):
        raise ReleaseCandidateStaticCompletenessError(f"unsafe archive member: {raw!r}")
    return path


def _materialize_exact_archive(archive_path: Path, destination: Path, *, expected_members: int) -> None:
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(archive_path, "r", allowZip64=False) as archive:
            infos = archive.infolist()
            if len(infos) != expected_members:
                raise ReleaseCandidateStaticCompletenessError(
                    f"archive member count mismatch: index={expected_members} zip={len(infos)}"
                )
            for info in infos:
                path = _canonical_member(info.filename)
                if info.filename in seen:
                    raise ReleaseCandidateStaticCompletenessError(
                        f"duplicate archive member: {info.filename!r}"
                    )
                seen.add(info.filename)
                mode = (info.external_attr >> 16) & 0xFFFF
                if info.is_dir() or stat.S_IFMT(mode) != stat.S_IFREG:
                    raise ReleaseCandidateStaticCompletenessError(
                        f"archive member is not a regular file: {info.filename!r}"
                    )
                data = archive.read(info)
                target = destination.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ReleaseCandidateStaticCompletenessError(
            f"release archive cannot be materialized safely: {archive_path}"
        ) from exc


def verify_bundle(bundle_dir: Path) -> dict[str, Any]:
    index_path = bundle_dir / DEFAULT_INDEX
    index = _load_index(index_path)

    archive = index.get("archive")
    prehandoff = index.get("prehandoff_receipt")
    if not isinstance(archive, dict) or not isinstance(prehandoff, dict):
        raise ReleaseCandidateStaticCompletenessError(
            "release bundle index is missing archive/prehandoff objects"
        )

    filename = archive.get("filename")
    expected_sha = archive.get("sha256")
    expected_members = archive.get("member_count")
    declared_ref = prehandoff.get("declared_ref")
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or not isinstance(expected_sha, str)
        or len(expected_sha) != 64
        or any(ch not in "0123456789abcdef" for ch in expected_sha)
        or isinstance(expected_members, bool)
        or not isinstance(expected_members, int)
        or expected_members < 1
        or not isinstance(declared_ref, str)
        or not declared_ref
    ):
        raise ReleaseCandidateStaticCompletenessError("release bundle index identity fields are invalid")

    archive_path = bundle_dir / filename
    try:
        archive_bytes = archive_path.read_bytes()
    except OSError as exc:
        raise ReleaseCandidateStaticCompletenessError(
            f"release archive is missing: {archive_path}"
        ) from exc
    observed_sha = _sha256(archive_bytes)
    if observed_sha != expected_sha:
        raise ReleaseCandidateStaticCompletenessError(
            f"archive SHA-256 mismatch: index={expected_sha} observed={observed_sha}"
        )

    with tempfile.TemporaryDirectory(prefix="f2-release-static-") as temporary:
        extracted = Path(temporary)
        _materialize_exact_archive(
            archive_path,
            extracted,
            expected_members=expected_members,
        )
        static = evaluate_portable_release_static_completeness(
            extracted,
            prehandoff_receipt_ref=declared_ref,
        )

    if static.status != STATIC_COMPLETE or static.violations:
        raise ReleaseCandidateStaticCompletenessError(
            f"WP1111 exact-archive gate blocked: status={static.status} "
            f"violations={list(static.violations)}"
        )

    if static.release_id != index.get("release_id"):
        raise ReleaseCandidateStaticCompletenessError("WP1111 release_id does not match bundle index")
    if static.source_commit != index.get("source_commit"):
        raise ReleaseCandidateStaticCompletenessError("WP1111 source_commit does not match bundle index")
    if static.release_manifest_sha256 != archive.get("manifest_sha256"):
        raise ReleaseCandidateStaticCompletenessError(
            "WP1111 release-manifest digest does not match archive index"
        )

    receipt = {
        "schema": SCHEMA,
        "classification": "POST_BUILD_EXACT_ARCHIVE_WP1111_GATE_REPOSITORY_CI_ONLY",
        "evidence_scope": EVIDENCE_SCOPE,
        "release_id": static.release_id,
        "source_commit": static.source_commit,
        "archive_filename": filename,
        "archive_sha256": observed_sha,
        "release_manifest_sha256": static.release_manifest_sha256,
        "prehandoff_receipt_ref": declared_ref,
        "wp1111_status": static.status,
        "wp1111_violations": list(static.violations),
        "wp1111_receipt": static.as_dict(),
        "credits": {
            "repository_release_static_completeness_credit": 1,
            "clean_machine_runtime_credit": 0,
            "physical_host_credit": 0,
            "vps_runtime_credit": 0,
            "effect_credit": 0,
            "completion_credit": 0,
            "whole_system_acceptance": False,
        },
        "next_exact_action": (
            "Use this exact archive plus the exact external pre-handoff receipt bytes on admitted "
            "real host cases; bind runtime observations to the same archive SHA-256 and receipt "
            "subject before any runtime or completion promotion."
        ),
    }
    output_path = bundle_dir / DEFAULT_RECEIPT
    output_path.write_bytes(_canonical_json(receipt))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", type=Path, required=True)
    args = parser.parse_args()
    receipt = verify_bundle(args.bundle_dir)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
