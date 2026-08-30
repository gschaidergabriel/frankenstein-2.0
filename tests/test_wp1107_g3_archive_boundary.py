#!/usr/bin/env python3
"""F2-WP-1107 generation-3 exact outer archive-byte boundary regressions."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from frankenstein2.release_archive import (
    ReleaseArchiveError,
    ReleaseArchivePolicy,
    build_release_archive,
    verify_release_archive,
)


class WP1107ArchiveBoundaryTests(unittest.TestCase):
    def _build(self):
        tmp = tempfile.TemporaryDirectory(prefix="wp1107-g3-boundary-")
        root = Path(tmp.name)
        payload = root / "bin" / "run.sh"
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_bytes(b"#!/bin/sh\nprintf 'frankenstein-2.0\\n'\n")
        os.chmod(payload, 0o755)
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
            build_id="wp1107-g3-archive-boundary",
            policy=policy,
            prehandoff_receipt_refs=("receipt/wp1107-g3",),
        )
        return tmp, policy, build

    def test_canonical_builder_output_still_verifies_exactly(self) -> None:
        tmp, policy, build = self._build()
        try:
            observed = verify_release_archive(
                build.archive_bytes,
                policy=policy,
                expected_receipt=build.receipt,
            )
            self.assertEqual(observed, build.receipt)
        finally:
            tmp.cleanup()

    def test_unbound_trailing_bytes_after_eocd_fail_closed_without_receipt(self) -> None:
        tmp, policy, build = self._build()
        try:
            with self.assertRaisesRegex(
                ReleaseArchiveError,
                "canonical zero-comment EOCD",
            ):
                verify_release_archive(
                    build.archive_bytes + b"UNBOUND_TRAILING_DATA",
                    policy=policy,
                )
        finally:
            tmp.cleanup()

    def test_unbound_leading_bytes_before_first_local_header_fail_closed(self) -> None:
        tmp, policy, build = self._build()
        try:
            with self.assertRaisesRegex(
                ReleaseArchiveError,
                "unbound bytes before first local file header",
            ):
                verify_release_archive(
                    b"UNBOUND_PREFIX" + build.archive_bytes,
                    policy=policy,
                )
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
