from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from frankenstein2.receipt_content_binding import (
    ReceiptContentBindingError,
    bind_prehandoff_receipt_content,
)
from tools.build_release_candidate_bundle import (
    ReleaseCandidateBundleError,
    build_release_candidate_bundle,
)


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return proc.stdout.strip()


def _write(repo: Path, rel: str, content: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "F2 Test")
    _git(repo, "config", "user.email", "f2-test@example.invalid")

    routes = {
        "schema": "FRANKENSTEIN2_AI_INSTALL_ROUTE/v1",
        "root_rule": "ROOT = parent(directory_containing_this_file)",
        "product_completion_law": "../PRODUCT_COMPLETION_LAW.md",
        "distribution_contract": "../architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md",
        "portable_delivery_phase": "../workpackages/PORTABLE_DELIVERY_PHASE.json",
        "donor_installer_audit": "../provenance/frankenstein1-portable-installer-audit-20260829.json",
        "verify_install": "03_VERIFY_INSTALL.md",
        "claude_code": "CLAUDE_CODE/00_DO_THIS.md",
        "codex_cli": "CODEX_CLI/00_DO_THIS.md",
        "other_agent": "OTHER_AGENT/00_DO_THIS.md",
        "state_rule": "ONE_CANONICAL_DURABLE_LOCAL_F2_STATE_OUTSIDE_DISPOSABLE_HOST_CACHE",
        "vps_rule": "OPTIONAL_EXTENSION_NOT_BASELINE_PRODUCT_LOCATION",
        "production_ready_condition": "PORTABLE_ONE_HANDOFF_RELEASE_GATE_ACCEPTED",
    }
    _write(
        repo,
        "AI_START_HERE_DO_NOT_SCAN_REPO/01_ROUTES.json",
        json.dumps(routes, indent=2, sort_keys=True) + "\n",
    )
    for rel in (
        "PRODUCT_COMPLETION_LAW.md",
        "architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md",
        "workpackages/PORTABLE_DELIVERY_PHASE.json",
        "provenance/frankenstein1-portable-installer-audit-20260829.json",
        "AI_START_HERE_DO_NOT_SCAN_REPO/03_VERIFY_INSTALL.md",
        "AI_START_HERE_DO_NOT_SCAN_REPO/CLAUDE_CODE/00_DO_THIS.md",
        "AI_START_HERE_DO_NOT_SCAN_REPO/CODEX_CLI/00_DO_THIS.md",
        "AI_START_HERE_DO_NOT_SCAN_REPO/OTHER_AGENT/00_DO_THIS.md",
    ):
        _write(repo, rel, f"fixture: {rel}\n")
    _write(repo, "bin/f2-fixture", "#!/bin/sh\nexit 0\n")
    os.chmod(repo / "bin/f2-fixture", 0o755)

    _git(repo, "add", ".")
    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = "2000-01-01T00:00:00Z"
    env["GIT_COMMITTER_DATE"] = "2000-01-01T00:00:00Z"
    _git(repo, "commit", "-q", "-m", "fixture", env=env)
    return repo


class ReleaseCandidateBundleTests(unittest.TestCase):
    def test_exact_git_tree_bundle_is_reproducible_and_ignores_untracked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = _make_repo(root)
            _write(repo, "UNTRACKED_SHOULD_NOT_ENTER.txt", "ambient\n")

            first = build_release_candidate_bundle(repo, root / "out-1")
            second = build_release_candidate_bundle(repo, root / "out-2")

            self.assertEqual(first.artifact_path.read_bytes(), second.artifact_path.read_bytes())
            self.assertEqual(
                first.artifact_bound_receipt_path.read_bytes(),
                second.artifact_bound_receipt_path.read_bytes(),
            )
            self.assertEqual(
                first.content_bound_receipt_path.read_bytes(),
                second.content_bound_receipt_path.read_bytes(),
            )
            self.assertEqual(first.bundle_index, second.bundle_index)
            self.assertEqual(first.bundle_index["credits"]["target_runtime"], 0)
            self.assertFalse(first.bundle_index["credits"]["whole_system_acceptance"])
            self.assertEqual(
                first.bundle_index["artifact_bound_prehandoff"]["status"],
                "READY_FOR_REAL_HOST_HANDOFF",
            )
            self.assertEqual(
                first.bundle_index["receipt_content_binding"]["status"],
                "READY_FOR_REAL_HOST_HANDOFF",
            )

            with zipfile.ZipFile(first.artifact_path, "r") as archive:
                self.assertNotIn("UNTRACKED_SHOULD_NOT_ENTER.txt", archive.namelist())
                fixture_info = archive.getinfo("bin/f2-fixture")
                self.assertEqual((fixture_info.external_attr >> 16) & 0o777, 0o755)

    def test_exact_external_receipt_bytes_are_immutable_subject(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = _make_repo(root)
            bundle = build_release_candidate_bundle(repo, root / "out")
            exact = bundle.artifact_bound_receipt_path.read_bytes()
            with self.assertRaises(ReceiptContentBindingError):
                bind_prehandoff_receipt_content(
                    bundle.artifact_bound_prehandoff,
                    prehandoff_receipt_ref=(
                        bundle.bundle_index["artifact_bound_prehandoff"]["ref"]
                    ),
                    prehandoff_receipt_bytes=exact + b" ",
                )

    def test_preexisting_receipt_parent_symlink_escape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = _make_repo(root)
            output = root / "out"
            outside = root / "outside"
            output.mkdir()
            outside.mkdir()
            link = output / "external-receipts"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")

            with self.assertRaisesRegex(
                ReleaseCandidateBundleError,
                "symlink|output",
            ):
                build_release_candidate_bundle(repo, output)

            self.assertEqual(list(outside.iterdir()), [])

    def test_preexisting_declared_receipt_different_bytes_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = _make_repo(root)
            output = root / "out"
            short = _git(repo, "rev-parse", "HEAD")[:12]
            receipt = (
                output
                / "external-receipts"
                / f"frankenstein-2.0-{short}.zip.artifact-bound-prehandoff.json"
            )
            receipt.parent.mkdir(parents=True)
            sentinel = b"hostile-preexisting-receipt\n"
            receipt.write_bytes(sentinel)

            with self.assertRaisesRegex(
                ReleaseCandidateBundleError,
                "exists with different bytes",
            ):
                build_release_candidate_bundle(repo, output)

            self.assertEqual(receipt.read_bytes(), sentinel)

    def test_repeated_same_output_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = _make_repo(root)
            output = root / "out"

            first = build_release_candidate_bundle(repo, output)
            second = build_release_candidate_bundle(repo, output)

            self.assertEqual(first.bundle_index, second.bundle_index)
            self.assertEqual(
                first.artifact_path.read_bytes(),
                second.artifact_path.read_bytes(),
            )

    def test_tracked_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = _make_repo(root)
            link = repo / "tracked-link"
            try:
                link.symlink_to("PRODUCT_COMPLETION_LAW.md")
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            _git(repo, "add", "tracked-link")
            env = dict(os.environ)
            env["GIT_AUTHOR_DATE"] = "2000-01-01T00:01:00Z"
            env["GIT_COMMITTER_DATE"] = "2000-01-01T00:01:00Z"
            _git(repo, "commit", "-q", "-m", "add tracked symlink", env=env)

            with self.assertRaisesRegex(
                ReleaseCandidateBundleError, "non-regular tracked entry"
            ):
                build_release_candidate_bundle(repo, root / "out")


if __name__ == "__main__":
    unittest.main()
