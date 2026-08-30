#!/usr/bin/env python3
"""F2-WP-1107 G3 exact archive-byte-envelope regressions."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from frankenstein2.release_archive import (
    ReleaseArchiveError,
    ReleaseArchivePolicy,
    build_release_archive,
    verify_release_archive,
)


class ExactArchiveEnvelopeTests(unittest.TestCase):
    def build(self):
        tmp = tempfile.TemporaryDirectory(prefix="wp1107-g3-")
        root = Path(tmp.name)
        (root / "bin").mkdir(parents=True)
        (root / "bin" / "run.sh").write_bytes(b"#!/bin/sh\nprintf 'ok\\n'\n")
        policy = ReleaseArchivePolicy(
            policy_id="f2-release-zip-stored-posix-v1",
            source_date_epoch=1_700_000_000,
            executable_paths=("bin/run.sh",),
        )
        build = build_release_archive(
            root,
            release_id="frankenstein-2.0-wp1107-g3",
            source_commit="c" * 40,
            source_tree="t" * 40,
            build_id="wp1107-g3-byte-envelope",
            policy=policy,
        )
        return tmp, policy, build

    def test_trailing_bytes_fail_without_expected_receipt(self) -> None:
        tmp, policy, build = self.build()
        try:
            mutated = build.archive_bytes + b"UNBOUND_TRAILING_DATA"
            with self.assertRaisesRegex(ReleaseArchiveError, "byte envelope is not canonical"):
                verify_release_archive(mutated, policy=policy)
        finally:
            tmp.cleanup()

    def test_prefixed_bytes_fail_without_expected_receipt(self) -> None:
        tmp, policy, build = self.build()
        try:
            mutated = b"UNBOUND_PREFIX" + build.archive_bytes
            with self.assertRaisesRegex(ReleaseArchiveError, "byte envelope is not canonical"):
                verify_release_archive(mutated, policy=policy)
        finally:
            tmp.cleanup()

    def test_canonical_archive_still_verifies_exactly(self) -> None:
        tmp, policy, build = self.build()
        try:
            observed = verify_release_archive(
                build.archive_bytes,
                policy=policy,
                expected_receipt=build.receipt,
            )
            self.assertEqual(observed, build.receipt)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
