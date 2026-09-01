from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.build_release_candidate_bundle import (
    ReleaseCandidateBundleError,
    build_release_candidate_bundle,
)


def _load_existing_fixture_module():
    path = Path(__file__).with_name("test_release_candidate_bundle.py")
    spec = importlib.util.spec_from_file_location("wp1207_existing_fixture", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load existing WP1207 G3 fixture module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FIXTURE = _load_existing_fixture_module()


def _head(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


class WP1207G3OutputBoundaryReviewTests(unittest.TestCase):
    """REVIEW_ONLY falsifiers for the post-merge G3 output boundary.

    These tests intentionally ask for fail-closed behavior that the current G3 source
    must demonstrate before its exact receipt materialization can be treated as robust
    against a pre-existing hostile output directory. They do not mint runtime credit.
    """

    def test_declared_receipt_is_materialized_at_declared_reference(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = _FIXTURE._make_repo(root)
            output = root / "out"

            bundle = build_release_candidate_bundle(repo, output)

            declared = bundle.bundle_index["artifact_bound_prehandoff"]["ref"]
            materialized = bundle.artifact_bound_receipt_path.relative_to(output).as_posix()
            self.assertEqual(materialized, declared)
            self.assertTrue(output.joinpath(*declared.split("/")).is_file())

    def test_preexisting_receipt_parent_symlink_escape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = _FIXTURE._make_repo(root)
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
                "symlink|escape|output",
            ):
                build_release_candidate_bundle(repo, output)

            self.assertEqual(list(outside.iterdir()), [])

    def test_preexisting_declared_receipt_different_bytes_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = _FIXTURE._make_repo(root)
            output = root / "out"
            short = _head(repo)[:12]
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
                "exists|different|immutable|receipt",
            ):
                build_release_candidate_bundle(repo, output)

            self.assertEqual(receipt.read_bytes(), sentinel)


if __name__ == "__main__":
    unittest.main()
