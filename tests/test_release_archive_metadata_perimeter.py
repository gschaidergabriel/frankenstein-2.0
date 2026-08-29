#!/usr/bin/env python3
"""Post-research metadata-perimeter falsifiers for F2-WP-1107 generation 2."""
from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from frankenstein2.release_archive import (
    ReleaseArchiveError,
    ReleaseArchivePolicy,
    build_release_archive,
    verify_release_archive,
)


def fixture(root: Path, *, unicode_name: bool = False) -> None:
    (root / "bin").mkdir(parents=True, exist_ok=True)
    (root / "bin/run.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
    name = "caf\u00e9.txt" if unicode_name else "cafe.txt"
    (root / name).write_bytes(b"payload\n")


def policy(**changes) -> ReleaseArchivePolicy:
    values = {
        "policy_id": "f2-release-zip-stored-posix-v1",
        "source_date_epoch": 1_700_000_000,
        "executable_paths": ("bin/run.sh",),
    }
    values.update(changes)
    return ReleaseArchivePolicy(**values)


def build(root: Path, p: ReleaseArchivePolicy):
    return build_release_archive(
        root,
        release_id="f2-metadata-perimeter",
        source_commit="c" * 40,
        source_tree="t" * 40,
        build_id="wp1107-g2-metadata",
        policy=p,
    )


class ReleaseArchiveMetadataPerimeterTests(unittest.TestCase):
    def test_serialized_zip_versions_and_flags_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            result = build(root, policy())
            with zipfile.ZipFile(io.BytesIO(result.archive_bytes), "r", allowZip64=False) as archive:
                for info in archive.infolist():
                    self.assertEqual(info.create_system, 3)
                    self.assertEqual(info.create_version, 20)
                    self.assertEqual(info.extract_version, 20)
                    self.assertEqual(info.flag_bits, 0)
                    self.assertEqual(info.extra, b"")
            verify_release_archive(result.archive_bytes, policy=policy(), expected_receipt=result.receipt)

    def test_non_ascii_member_name_is_rejected_before_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root, unicode_name=True)
            with self.assertRaisesRegex(ReleaseArchiveError, "ASCII"):
                build(root, policy())

    def test_non_classic_zip_version_policy_is_rejected(self) -> None:
        with self.assertRaisesRegex(ReleaseArchiveError, "ZIP version 2.0"):
            policy(create_version=45)
        with self.assertRaisesRegex(ReleaseArchiveError, "ZIP version 2.0"):
            policy(extract_version=45)

    def test_builder_translates_zip64_requirement_into_fail_closed_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            with patch("zipfile.ZipFile.writestr", side_effect=zipfile.LargeZipFile("requires ZIP64")):
                with self.assertRaisesRegex(ReleaseArchiveError, "forbidden ZIP64"):
                    build(root, policy())

    def test_verifier_rejects_modified_serialized_version_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            result = build(root, policy())
            source = zipfile.ZipFile(io.BytesIO(result.archive_bytes), "r", allowZip64=False)
            output = io.BytesIO()
            with source, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as target:
                for index, info in enumerate(source.infolist()):
                    data = source.read(info.filename)
                    if index == 0:
                        info.create_version = 45
                    target.writestr(info, data)
            with self.assertRaisesRegex(ReleaseArchiveError, "system/version"):
                verify_release_archive(output.getvalue(), policy=policy())


if __name__ == "__main__":
    unittest.main()
