#!/usr/bin/env python3
"""Repository-level falsifiers for F2-WP-1107 generation 3."""
from __future__ import annotations

from dataclasses import replace
import io
import locale
import os
from pathlib import Path
import tempfile
import time
import unittest
import zipfile

from frankenstein2.release_archive import (
    ARCHIVE_COMPONENT_SCOPE,
    ReleaseArchiveError,
    ReleaseArchivePolicy,
    build_release_archive,
    verify_release_archive,
)

SOURCE_COMMIT = "c" * 40
SOURCE_TREE = "t" * 40
EPOCH = 1_700_000_000


def populate(root: Path, *, reverse: bool, mtime: int, bin_mode: int, data_mode: int) -> None:
    entries = [
        ("bin/run.sh", b"#!/bin/sh\nprintf 'frankenstein-2.0\\n'\n"),
        ("data/config.txt", b"alpha=1\nbeta=2\n"),
        ("share/readme.txt", b"portable release fixture\n"),
    ]
    if reverse:
        entries.reverse()
    for rel, data in entries:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.utime(path, (mtime, mtime))
        os.chmod(path, bin_mode if rel == "bin/run.sh" else data_mode)


def build(root: Path, policy: ReleaseArchivePolicy):
    return build_release_archive(
        root,
        release_id="frankenstein-2.0-test",
        source_commit=SOURCE_COMMIT,
        source_tree=SOURCE_TREE,
        build_id="wp1107-g2-fixture",
        policy=policy,
        prehandoff_receipt_refs=("receipt/a", "receipt/b"),
    )


def rewrite_member(archive_bytes: bytes, member: str, replacement: bytes) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(archive_bytes), "r")
    output = io.BytesIO()
    with source, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as target:
        target.comment = source.comment
        for info in source.infolist():
            data = replacement if info.filename == member else source.read(info.filename)
            target.writestr(info, data)
    return output.getvalue()


class ReleaseArchiveTests(unittest.TestCase):
    def policy(self, **changes) -> ReleaseArchivePolicy:
        values = {
            "policy_id": "f2-release-zip-stored-posix-v1",
            "source_date_epoch": EPOCH,
            "executable_paths": ("bin/run.sh",),
        }
        values.update(changes)
        return ReleaseArchivePolicy(**values)

    def test_archive_bytes_ignore_root_path_creation_order_mtime_modes_tz_and_locale(self) -> None:
        old_tz = os.environ.get("TZ")
        old_locale = locale.setlocale(locale.LC_ALL)
        try:
            with tempfile.TemporaryDirectory(prefix="wp1107-a-") as a, tempfile.TemporaryDirectory(prefix="wp1107-b-") as b:
                root_a, root_b = Path(a), Path(b)
                populate(root_a, reverse=False, mtime=1_600_000_000, bin_mode=0o700, data_mode=0o600)
                populate(root_b, reverse=True, mtime=1_800_000_000, bin_mode=0o777, data_mode=0o666)
                os.environ["TZ"] = "UTC0"
                if hasattr(time, "tzset"):
                    time.tzset()
                locale.setlocale(locale.LC_ALL, "C")
                left = build(root_a, self.policy())
                os.environ["TZ"] = "GMT-9"
                if hasattr(time, "tzset"):
                    time.tzset()
                right = build(root_b, self.policy())
                self.assertEqual(left.archive_bytes, right.archive_bytes)
                self.assertEqual(left.receipt.archive_sha256, right.receipt.archive_sha256)
                self.assertEqual(left.receipt.manifest_sha256, right.receipt.manifest_sha256)
        finally:
            if old_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old_tz
            if hasattr(time, "tzset"):
                time.tzset()
            locale.setlocale(locale.LC_ALL, old_locale)

    def test_archive_contains_only_sorted_files_and_canonical_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, reverse=False, mtime=0, bin_mode=0o755, data_mode=0o644)
            result = build(root, self.policy())
            with zipfile.ZipFile(io.BytesIO(result.archive_bytes), "r") as archive:
                names = archive.namelist()
                self.assertEqual(names, sorted(names))
                self.assertNotIn("bin/", names)
                self.assertIn("manifest/release-manifest.json", names)
                embedded = archive.read("manifest/release-manifest.json")
                self.assertEqual(embedded, result.manifest.canonical_bytes())
            observed = verify_release_archive(result.archive_bytes, policy=self.policy(), expected_receipt=result.receipt)
            self.assertEqual(observed, result.receipt)
            self.assertEqual(observed.evidence_scope, ARCHIVE_COMPONENT_SCOPE)

    def test_payload_mutation_changes_manifest_and_archive_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, reverse=False, mtime=0, bin_mode=0o755, data_mode=0o644)
            before = build(root, self.policy())
            (root / "data/config.txt").write_bytes(b"alpha=9\nbeta=2\n")
            after = build(root, self.policy())
            self.assertNotEqual(before.receipt.manifest_sha256, after.receipt.manifest_sha256)
            self.assertNotEqual(before.receipt.archive_sha256, after.receipt.archive_sha256)

    def test_tampered_member_fails_against_embedded_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, reverse=False, mtime=0, bin_mode=0o755, data_mode=0o644)
            result = build(root, self.policy())
            tampered = rewrite_member(result.archive_bytes, "data/config.txt", b"tampered\n")
            with self.assertRaisesRegex(ReleaseArchiveError, "payload mismatch"):
                verify_release_archive(tampered, policy=self.policy())

    def test_unexpected_extra_member_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, reverse=False, mtime=0, bin_mode=0o755, data_mode=0o644)
            result = build(root, self.policy())
            stream = io.BytesIO(result.archive_bytes)
            with zipfile.ZipFile(stream, "a", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("zzz-extra.txt", b"unexpected")
            with self.assertRaises(ReleaseArchiveError):
                verify_release_archive(stream.getvalue(), policy=self.policy())

    def test_unbound_container_prefix_or_trailing_bytes_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, reverse=False, mtime=0, bin_mode=0o755, data_mode=0o644)
            result = build(root, self.policy())
            mutations = (
                b"UNBOUND_PREFIX" + result.archive_bytes,
                result.archive_bytes + b"UNBOUND_TRAILING_DATA",
            )
            for mutated in mutations:
                with self.subTest(mutation_size=len(mutated) - len(result.archive_bytes)):
                    with self.assertRaisesRegex(ReleaseArchiveError, "canonical deterministic encoding"):
                        verify_release_archive(mutated, policy=self.policy())

    def test_wrong_expected_receipt_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, reverse=False, mtime=0, bin_mode=0o755, data_mode=0o644)
            result = build(root, self.policy())
            wrong = replace(result.receipt, archive_sha256="0" * 64)
            with self.assertRaisesRegex(ReleaseArchiveError, "receipt identity mismatch"):
                verify_release_archive(result.archive_bytes, policy=self.policy(), expected_receipt=wrong)

    def test_policy_identity_is_bound_even_when_member_bytes_can_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, reverse=False, mtime=0, bin_mode=0o755, data_mode=0o644)
            a = build(root, self.policy(policy_id="policy-a"))
            b = build(root, self.policy(policy_id="policy-b"))
            self.assertEqual(a.archive_bytes, b.archive_bytes)
            self.assertNotEqual(a.receipt.archive_policy_sha256, b.receipt.archive_policy_sha256)
            self.assertNotEqual(a.receipt.digest(), b.receipt.digest())

    def test_timestamp_clamp_is_explicit_and_archive_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, reverse=False, mtime=0, bin_mode=0o755, data_mode=0o644)
            below = build(root, self.policy(source_date_epoch=0))
            floor = build(root, self.policy(source_date_epoch=315532800))
            self.assertEqual(below.archive_bytes, floor.archive_bytes)
            with zipfile.ZipFile(io.BytesIO(below.archive_bytes), "r") as archive:
                self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()))

    def test_executable_policy_must_be_unique_sorted_and_reference_payload(self) -> None:
        with self.assertRaisesRegex(ReleaseArchiveError, "unique and sorted"):
            self.policy(executable_paths=("bin/run.sh", "bin/run.sh"))
        with self.assertRaisesRegex(ReleaseArchiveError, "unique and sorted"):
            self.policy(executable_paths=("data/config.txt", "bin/run.sh"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, reverse=False, mtime=0, bin_mode=0o755, data_mode=0o644)
            with self.assertRaisesRegex(ReleaseArchiveError, "absent payload"):
                build(root, self.policy(executable_paths=("bin/missing.sh",)))

    def test_manifest_cannot_be_marked_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, reverse=False, mtime=0, bin_mode=0o755, data_mode=0o644)
            with self.assertRaisesRegex(ReleaseArchiveError, "manifest cannot be executable"):
                build(root, self.policy(executable_paths=("manifest/release-manifest.json",)))

    def test_invalid_zip_and_wrong_policy_fail_closed(self) -> None:
        with self.assertRaisesRegex(ReleaseArchiveError, "invalid release ZIP"):
            verify_release_archive(b"not-a-zip", policy=self.policy())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, reverse=False, mtime=0, bin_mode=0o755, data_mode=0o644)
            result = build(root, self.policy())
            with self.assertRaises(ReleaseArchiveError):
                verify_release_archive(result.archive_bytes, policy=self.policy(source_date_epoch=EPOCH + 4))


if __name__ == "__main__":
    unittest.main()
