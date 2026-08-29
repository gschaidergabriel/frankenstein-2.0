from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from frankenstein2.release_integrity import (
    DEFAULT_MANIFEST_PATH,
    RELEASE_MANIFEST_SCHEMA,
    ReleaseIntegrityError,
    ReleaseManifest,
    build_release_manifest,
    load_and_verify_release_manifest,
    verify_release_manifest,
    write_release_manifest,
)


class ReleaseIntegrityTests(unittest.TestCase):
    def package(self, root: Path, order=("b.txt", "a.txt")) -> Path:
        package = root / "package"
        package.mkdir()
        for name in order:
            path = package / name
            path.write_text(f"payload:{name}\n", encoding="utf-8")
        nested = package / "payload"
        nested.mkdir()
        (nested / "core.bin").write_bytes(b"\x00\x01core")
        return package

    def manifest(self, package: Path) -> ReleaseManifest:
        return build_release_manifest(
            package,
            release_id="f2-test-1",
            source_commit="commit-abc",
            source_tree="tree-def",
            build_id="build-001",
            prehandoff_receipt_refs=("receipt:a", "receipt:b"),
        )

    def test_manifest_is_deterministic_across_creation_order(self):
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            first = self.package(Path(td1), order=("b.txt", "a.txt"))
            second = self.package(Path(td2), order=("a.txt", "b.txt"))
            a = self.manifest(first)
            b = self.manifest(second)
            self.assertEqual(a.canonical_bytes(), b.canonical_bytes())
            self.assertEqual(a.sha256(), b.sha256())
            self.assertEqual(
                [entry.path for entry in a.files],
                ["a.txt", "b.txt", "payload/core.bin"],
            )

    def test_write_load_verify_exact_payload(self):
        with tempfile.TemporaryDirectory() as td:
            package = self.package(Path(td))
            manifest = self.manifest(package)
            path = write_release_manifest(package, manifest)
            self.assertEqual(path.relative_to(package).as_posix(), DEFAULT_MANIFEST_PATH)
            loaded = load_and_verify_release_manifest(package)
            self.assertEqual(loaded.sha256(), manifest.sha256())

    def test_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            package = self.package(Path(td))
            manifest = self.manifest(package)
            (package / "a.txt").write_text("mutated\n", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseIntegrityError, "mismatched"):
                verify_release_manifest(package, manifest)

    def test_extra_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            package = self.package(Path(td))
            manifest = self.manifest(package)
            (package / "extra.txt").write_text("unexpected\n", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseIntegrityError, "extra"):
                verify_release_manifest(package, manifest)

    def test_missing_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            package = self.package(Path(td))
            manifest = self.manifest(package)
            (package / "b.txt").unlink()
            with self.assertRaisesRegex(ReleaseIntegrityError, "missing"):
                verify_release_manifest(package, manifest)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_symlink_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            package = self.package(Path(td))
            os.symlink(package / "a.txt", package / "alias.txt")
            with self.assertRaisesRegex(ReleaseIntegrityError, "symlink file forbidden"):
                self.manifest(package)

    def test_traversal_entry_is_rejected_on_load(self):
        raw = {
            "schema": RELEASE_MANIFEST_SCHEMA,
            "release_id": "r",
            "source_commit": "c",
            "source_tree": "t",
            "build_id": "b",
            "prehandoff_receipt_refs": [],
            "files": [{"path": "../escape", "sha256": "0" * 64, "size": 0}],
        }
        with self.assertRaisesRegex(ReleaseIntegrityError, "traversal"):
            ReleaseManifest.from_bytes((json.dumps(raw) + "\n").encode())

    def test_noncanonical_manifest_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            package = self.package(Path(td))
            manifest = self.manifest(package)
            path = write_release_manifest(package, manifest)
            raw = json.loads(path.read_text(encoding="utf-8"))
            path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseIntegrityError, "canonical byte form"):
                load_and_verify_release_manifest(package)

    def test_duplicate_receipt_ref_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            package = self.package(Path(td))
            with self.assertRaisesRegex(ReleaseIntegrityError, "duplicate pre-handoff"):
                build_release_manifest(
                    package,
                    release_id="r",
                    source_commit="c",
                    source_tree="t",
                    build_id="b",
                    prehandoff_receipt_refs=("receipt:a", "receipt:a"),
                )


if __name__ == "__main__":
    unittest.main()
