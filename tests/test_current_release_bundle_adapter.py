#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from frankenstein2.current_release_bundle_adapter import from_current_release_bundle
from frankenstein2.hostile_twin_release_executor import HostileTwinExecutionError, ScratchHostileTwin, request_for_install
from frankenstein2.release_archive import ReleaseArchivePolicy, build_release_archive


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def build_current_bundle(root: Path) -> Path:
    package = root / "package"
    package.mkdir()
    (package / "app.txt").write_text("current-release\n")
    source_commit = "a" * 40
    source_tree = "b" * 40
    source_epoch = 1788102773
    policy = ReleaseArchivePolicy(
        policy_id="f2-release-zip-stored-posix-v1",
        source_date_epoch=source_epoch,
        executable_paths=(),
    )
    build = build_release_archive(
        package,
        release_id=f"frankenstein-2.0-{source_commit[:12]}",
        source_commit=source_commit,
        source_tree=source_tree,
        build_id=f"trigger4-release-{source_commit[:12]}",
        policy=policy,
    )
    archive_name = "frankenstein-2.0.zip"
    receipt_name = "frankenstein-2.0-archive-receipt.json"
    prehandoff_name = "frankenstein-2.0-prehandoff.json"
    content_name = "frankenstein-2.0-content-bound-prehandoff.json"
    static_name = "frankenstein-2.0-artifact-bound-static-completeness.json"
    receipt_bytes = build.receipt.canonical_bytes()
    prehandoff_bytes = canonical({"schema": "TEST_PREHANDOFF/v1", "status": "READY_FOR_REAL_HOST_HANDOFF"})
    content_bytes = canonical({"schema": "TEST_CONTENT_BOUND/v1", "status": "READY_FOR_REAL_HOST_HANDOFF"})
    subject_sha = sha(canonical({"archive": build.receipt.archive_sha256, "pre": sha(prehandoff_bytes)}))
    static_bytes = canonical({"schema": "TEST_STATIC/v1", "status": "STATIC_COMPLETE_FOR_REAL_HOST_ACCEPTANCE"})
    file_bytes = {
        archive_name: build.archive_bytes,
        receipt_name: receipt_bytes,
        prehandoff_name: prehandoff_bytes,
        content_name: content_bytes,
        static_name: static_bytes,
    }
    index = {
        "schema": "FRANKENSTEIN2_RELEASE_CANDIDATE_BUNDLE/v1",
        "classification": "EXACT_GIT_TREE_DETERMINISTIC_RELEASE_CANDIDATE_REPOSITORY_BUILD_ONLY",
        "source_commit": source_commit,
        "source_tree": source_tree,
        "source_date_epoch": source_epoch,
        "release_id": build.receipt.release_id,
        "build_id": build.receipt.build_id,
        "archive": {
            "filename": archive_name,
            "sha256": build.receipt.archive_sha256,
            "size_bytes": build.receipt.archive_size,
            "member_count": build.receipt.member_count,
            "manifest_sha256": build.receipt.manifest_sha256,
            "policy_id": policy.policy_id,
            "policy_sha256": policy.digest(),
            "receipt_sha256": build.receipt.digest(),
        },
        "artifact_subject": {
            "sha256": subject_sha,
            "artifact_bound_prehandoff_sha256": sha(prehandoff_bytes),
            "status": "READY_FOR_REAL_HOST_HANDOFF",
            "static_status": "READY_FOR_REAL_HOST_HANDOFF",
            "static_violations": [],
        },
        "prehandoff_receipt": {
            "declared_ref": "release-receipts/frankenstein-2.0-prehandoff.json",
            "filename": prehandoff_name,
            "sha256": sha(prehandoff_bytes),
            "size_bytes": len(prehandoff_bytes),
            "content_subject_sha256": "c" * 64,
            "content_bound_sha256": sha(content_bytes),
            "content_bound_status": "READY_FOR_REAL_HOST_HANDOFF",
        },
        "artifact_bound_static_completeness": {
            "filename": static_name,
            "sha256": sha(static_bytes),
            "receipt_sha256": sha(static_bytes),
            "status": "STATIC_COMPLETE_FOR_REAL_HOST_ACCEPTANCE",
            "static_status": "STATIC_COMPLETE_FOR_REAL_HOST_ACCEPTANCE",
            "static_violations": [],
            "artifact_subject_sha256": subject_sha,
            "artifact_sha256": build.receipt.archive_sha256,
            "release_manifest_sha256": build.receipt.manifest_sha256,
        },
        "files": {
            name: {"sha256": sha(data), "size_bytes": len(data)}
            for name, data in file_bytes.items()
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
    out = root / "current-release-bundle.zip"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, data in file_bytes.items():
            zf.writestr(name, data)
        zf.writestr("release-bundle-index.json", canonical(index))
    return out


def rewrite_bundle(path: Path, mutate) -> Path:
    with zipfile.ZipFile(path, "r") as src:
        members = {name: src.read(name) for name in src.namelist()}
    mutate(members)
    out = path.with_name("mutated-" + path.name)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as dst:
        for name, data in members.items():
            dst.writestr(name, data)
    return out


class CurrentReleaseBundleAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.bundle = build_current_bundle(self.root)

    def tearDown(self) -> None:
        self.td.cleanup()

    def test_current_bundle_reaches_existing_hostile_twin_loader_and_execution(self) -> None:
        candidate = from_current_release_bundle(self.bundle)
        self.assertEqual(candidate.release_identity.version, "git-aaaaaaaaaaaa")
        self.assertEqual(candidate.release_identity.artifact_sha256, candidate.archive_receipt.archive_sha256)
        twin = ScratchHostileTwin(self.root / "twin")
        receipt = twin.execute(
            request_for_install(attempt_id="current-install", release=candidate.release_identity),
            candidate=candidate,
            canonical_state_bytes=b'{"state":"preserved"}\n',
        )
        self.assertEqual(receipt.outcome, "SUCCEEDED")
        self.assertEqual(receipt.target_runtime_credit, 0)
        self.assertFalse(receipt.whole_system_acceptance)

    def test_missing_current_bundle_index_fails_closed(self) -> None:
        bad = rewrite_bundle(self.bundle, lambda members: members.pop("release-bundle-index.json"))
        with self.assertRaisesRegex(HostileTwinExecutionError, "index missing"):
            from_current_release_bundle(bad)

    def test_renamed_declared_member_fails_closed(self) -> None:
        def mutate(members):
            members["renamed.zip"] = members.pop("frankenstein-2.0.zip")
        bad = rewrite_bundle(self.bundle, mutate)
        with self.assertRaises(HostileTwinExecutionError):
            from_current_release_bundle(bad)

    def test_tampered_declared_member_fails_closed(self) -> None:
        def mutate(members):
            members["frankenstein-2.0-prehandoff.json"] += b"tamper"
        bad = rewrite_bundle(self.bundle, mutate)
        with self.assertRaisesRegex(HostileTwinExecutionError, "member mismatch"):
            from_current_release_bundle(bad)

    def test_subject_disagreement_fails_closed_even_when_outer_file_hashes_are_rebound(self) -> None:
        def mutate(members):
            index = json.loads(members["release-bundle-index.json"])
            index["artifact_subject"]["artifact_bound_prehandoff_sha256"] = "0" * 64
            members["release-bundle-index.json"] = canonical(index)
        bad = rewrite_bundle(self.bundle, mutate)
        with self.assertRaisesRegex(HostileTwinExecutionError, "artifact subject and pre-handoff receipt disagree"):
            from_current_release_bundle(bad)

    def test_preminted_runtime_credit_fails_closed(self) -> None:
        def mutate(members):
            index = json.loads(members["release-bundle-index.json"])
            index["credits"]["clean_machine_runtime_credit"] = 1
            members["release-bundle-index.json"] = canonical(index)
        bad = rewrite_bundle(self.bundle, mutate)
        with self.assertRaisesRegex(HostileTwinExecutionError, "illegally pre-mints"):
            from_current_release_bundle(bad)


if __name__ == "__main__":
    unittest.main()
