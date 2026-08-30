#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from frankenstein2.artifact_bound_static_completeness import (
    ArtifactBoundStaticCompletenessReceipt,
)
from frankenstein2.hostile_twin_release_executor import HostileTwinExecutionError
from frankenstein2.portable_release_static_completeness import STATIC_COMPLETE
from frankenstein2.pre_handoff_release import READY_STATUS
from frankenstein2.receipt_content_binding import (
    ContentBoundPreHandoffReceipt,
    PreHandoffReceiptContentSubject,
)
from frankenstein2.release_archive import ReleaseArchivePolicy, build_release_archive
from frankenstein2.release_artifact_subject import (
    ArtifactBoundPreHandoffReceipt,
    ReleaseArtifactSubject,
)
from frankenstein2.wp1113_release_bundle_adapter import (
    CURRENT_BUNDLE_SCHEMA,
    CURRENT_INDEX_NAME,
    load_bound_release_candidate,
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def build_current_bundle(root: Path) -> tuple[Path, dict[str, object]]:
    package = root / "package"
    package.mkdir()
    (package / "app.txt").write_text("current-wp1113\n", encoding="utf-8")
    executable = package / "run.sh"
    executable.write_text("#!/bin/sh\necho current\n", encoding="utf-8")

    source_commit = "a" * 40
    source_tree = "b" * 40
    source_epoch = 1788065582
    release_id = f"frankenstein-2.0-{source_commit[:12]}"
    build_id = f"trigger4-release-{source_commit[:12]}"
    prehandoff_ref = "release-receipts/frankenstein-2.0-prehandoff.json"
    policy = ReleaseArchivePolicy(
        policy_id="f2-release-zip-stored-posix-v1",
        source_date_epoch=source_epoch,
        executable_paths=("run.sh",),
    )
    build = build_release_archive(
        package,
        release_id=release_id,
        source_commit=source_commit,
        source_tree=source_tree,
        build_id=build_id,
        policy=policy,
        prehandoff_receipt_refs=(prehandoff_ref,),
    )

    artifact_name = "frankenstein-2.0.zip"
    subject = ReleaseArtifactSubject(
        artifact_filename=artifact_name,
        artifact_sha256=build.receipt.archive_sha256,
        artifact_size_bytes=build.receipt.archive_size,
        release_manifest_sha256=build.receipt.manifest_sha256,
        source_commit=build.receipt.source_commit,
        source_tree=build.receipt.source_tree,
        release_id=build.receipt.release_id,
        build_id=build.receipt.build_id,
        archive_policy_id=build.receipt.archive_policy_id,
        archive_policy_sha256=build.receipt.archive_policy_sha256,
        member_count=build.receipt.member_count,
    )
    prehandoff = ArtifactBoundPreHandoffReceipt(
        subject=subject,
        prehandoff_receipt_ref=prehandoff_ref,
        static_prehandoff_sha256="1" * 64,
        static_status=READY_STATUS,
        static_violations=(),
        status=READY_STATUS,
    )
    prehandoff_bytes = prehandoff.canonical_bytes()
    content_subject = PreHandoffReceiptContentSubject(
        prehandoff_receipt_ref=prehandoff_ref,
        prehandoff_receipt_sha256=sha(prehandoff_bytes),
        prehandoff_receipt_size_bytes=len(prehandoff_bytes),
    )
    content_bound = ContentBoundPreHandoffReceipt(
        artifact_bound_prehandoff=prehandoff,
        receipt_content_subject=content_subject,
        status=READY_STATUS,
    )
    content_bytes = content_bound.canonical_bytes()
    static_bound = ArtifactBoundStaticCompletenessReceipt(
        artifact_subject=subject,
        prehandoff_receipt_ref=prehandoff_ref,
        static_completeness_sha256="2" * 64,
        static_status=STATIC_COMPLETE,
        static_violations=(),
        status=STATIC_COMPLETE,
    )
    static_bytes = static_bound.canonical_bytes()
    archive_receipt_bytes = build.receipt.canonical_bytes()

    files = {
        artifact_name: build.archive_bytes,
        "frankenstein-2.0-archive-receipt.json": archive_receipt_bytes,
        "frankenstein-2.0-prehandoff.json": prehandoff_bytes,
        "frankenstein-2.0-content-bound-prehandoff.json": content_bytes,
        "frankenstein-2.0-artifact-bound-static-completeness.json": static_bytes,
    }
    index = {
        "schema": CURRENT_BUNDLE_SCHEMA,
        "classification": "EXACT_GIT_TREE_DETERMINISTIC_RELEASE_CANDIDATE_REPOSITORY_BUILD_ONLY",
        "source_commit": source_commit,
        "source_tree": source_tree,
        "source_date_epoch": source_epoch,
        "release_id": release_id,
        "build_id": build_id,
        "tracked_regular_file_count": build.receipt.member_count - 1,
        "tracked_executable_file_count": 1,
        "archive": {
            "filename": artifact_name,
            "sha256": build.receipt.archive_sha256,
            "size_bytes": build.receipt.archive_size,
            "member_count": build.receipt.member_count,
            "manifest_sha256": build.receipt.manifest_sha256,
            "policy_id": policy.policy_id,
            "policy_sha256": policy.digest(),
            "receipt_sha256": build.receipt.digest(),
        },
        "artifact_subject": {
            "sha256": subject.sha256(),
            "artifact_bound_prehandoff_sha256": prehandoff.sha256(),
            "status": prehandoff.status,
            "static_status": prehandoff.static_status,
            "static_violations": list(prehandoff.static_violations),
        },
        "prehandoff_receipt": {
            "declared_ref": prehandoff_ref,
            "filename": "frankenstein-2.0-prehandoff.json",
            "sha256": sha(prehandoff_bytes),
            "size_bytes": len(prehandoff_bytes),
            "content_subject_sha256": content_subject.sha256(),
            "content_bound_sha256": content_bound.sha256(),
            "content_bound_status": content_bound.status,
        },
        "artifact_bound_static_completeness": {
            "filename": "frankenstein-2.0-artifact-bound-static-completeness.json",
            "sha256": sha(static_bytes),
            "receipt_sha256": static_bound.sha256(),
            "status": static_bound.status,
            "static_status": static_bound.static_status,
            "static_violations": list(static_bound.static_violations),
            "artifact_subject_sha256": static_bound.artifact_subject.sha256(),
            "artifact_sha256": static_bound.artifact_sha256,
            "release_manifest_sha256": static_bound.release_manifest_sha256,
        },
        "files": {
            name: {"sha256": sha(data), "size_bytes": len(data)}
            for name, data in files.items()
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
    }
    bundle = root / "wp1113-current.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_STORED) as outer:
        outer.writestr(CURRENT_INDEX_NAME, canonical(index))
        for name, data in files.items():
            outer.writestr(name, data)
    return bundle, {
        "index": index,
        "files": files,
        "receipt": build.receipt,
        "subject": subject,
    }


def rewrite_bundle(
    source: Path,
    destination: Path,
    *,
    mutate_index=None,
    mutate_member=None,
    rename_member: tuple[str, str] | None = None,
    add_legacy_index: bool = False,
) -> Path:
    with zipfile.ZipFile(source, "r") as zf:
        members = {name: zf.read(name) for name in zf.namelist()}
    index = json.loads(members[CURRENT_INDEX_NAME])
    if mutate_index is not None:
        mutate_index(index)
    members[CURRENT_INDEX_NAME] = canonical(index)
    if mutate_member is not None:
        name, transform = mutate_member
        members[name] = transform(members[name])
    if rename_member is not None:
        old, new = rename_member
        members[new] = members.pop(old)
    if add_legacy_index:
        members["RELEASE_CANDIDATE_BUNDLE.json"] = canonical({"schema": "legacy"})
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return destination


class WP1113ReleaseBundleAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.bundle, self.fixture = build_current_bundle(self.root)

    def tearDown(self) -> None:
        self.td.cleanup()

    def test_current_wp1113_bundle_reaches_existing_bound_candidate(self) -> None:
        outer_sha = sha(self.bundle.read_bytes())
        candidate = load_bound_release_candidate(
            self.bundle, expected_outer_sha256=f"sha256:{outer_sha}"
        )
        receipt = self.fixture["receipt"]
        self.assertEqual(candidate.outer_sha256, outer_sha)
        self.assertEqual(candidate.archive_receipt, receipt)
        self.assertEqual(candidate.release_identity.release_id, receipt.release_id)
        self.assertEqual(candidate.release_identity.version, f"git-{receipt.source_commit}")
        self.assertEqual(candidate.release_identity.artifact_sha256, receipt.archive_sha256)
        self.assertEqual(candidate.release_identity.manifest_sha256, receipt.manifest_sha256)
        self.assertEqual(candidate.artifact_bound_receipt_sha256, sha(self.fixture["files"]["frankenstein-2.0-prehandoff.json"]))
        self.assertEqual(candidate.content_bound_receipt_sha256, sha(self.fixture["files"]["frankenstein-2.0-content-bound-prehandoff.json"]))

    def test_wrong_admitted_outer_digest_fails_before_parsing_credit(self) -> None:
        with self.assertRaisesRegex(HostileTwinExecutionError, "admitted artifact identity"):
            load_bound_release_candidate(self.bundle, expected_outer_sha256="0" * 64)

    def test_tampered_declared_member_fails_closed(self) -> None:
        bad = rewrite_bundle(
            self.bundle,
            self.root / "tampered-member.zip",
            mutate_member=(
                "frankenstein-2.0-content-bound-prehandoff.json",
                lambda data: data + b" ",
            ),
        )
        with self.assertRaisesRegex(HostileTwinExecutionError, "declared current bundle member bytes mismatch"):
            load_bound_release_candidate(bad)

    def test_missing_or_renamed_declared_member_fails_closed(self) -> None:
        bad = rewrite_bundle(
            self.bundle,
            self.root / "renamed-member.zip",
            rename_member=(
                "frankenstein-2.0-content-bound-prehandoff.json",
                "renamed-content-bound.json",
            ),
        )
        with self.assertRaisesRegex(HostileTwinExecutionError, "declared current bundle member missing"):
            load_bound_release_candidate(bad)

    def test_artifact_subject_digest_disagreement_fails_closed(self) -> None:
        def mutate(index: dict) -> None:
            index["artifact_subject"]["sha256"] = "0" * 64

        bad = rewrite_bundle(
            self.bundle,
            self.root / "subject-mismatch.zip",
            mutate_index=mutate,
        )
        with self.assertRaisesRegex(HostileTwinExecutionError, "artifact subject digest"):
            load_bound_release_candidate(bad)

    def test_archive_policy_digest_disagreement_fails_closed(self) -> None:
        def mutate(index: dict) -> None:
            index["archive"]["policy_sha256"] = "0" * 64

        bad = rewrite_bundle(
            self.bundle,
            self.root / "policy-mismatch.zip",
            mutate_index=mutate,
        )
        with self.assertRaisesRegex(HostileTwinExecutionError, "archive policy digest"):
            load_bound_release_candidate(bad)

    def test_both_bundle_indexes_are_rejected_as_ambiguous(self) -> None:
        bad = rewrite_bundle(
            self.bundle,
            self.root / "ambiguous.zip",
            add_legacy_index=True,
        )
        with self.assertRaisesRegex(HostileTwinExecutionError, "ambiguous release bundle"):
            load_bound_release_candidate(bad)


if __name__ == "__main__":
    unittest.main()
