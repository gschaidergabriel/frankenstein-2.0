#!/usr/bin/env python3
"""REVIEW_ONLY falsifier for F2-WP-1107 generation 2.

This file does not own or modify the WP1107 implementation. It tests the active G2
invariant that unexpected/mutated archive contents fail closed.
"""
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


class WP1107TrailingDataReview(unittest.TestCase):
    def test_unbound_trailing_bytes_after_eocd_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wp1107-tail-review-") as tmp:
            root = Path(tmp)
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
                release_id="frankenstein-2.0-review",
                source_commit="c" * 40,
                source_tree="t" * 40,
                build_id="wp1107-g2-trailing-data-review",
                policy=policy,
                prehandoff_receipt_refs=("receipt/review",),
            )

            # Python's zipfile reader accepts bytes after the end-of-central-directory
            # record. Those bytes are not represented by a ZIP member or the embedded
            # release manifest, so the active G2 contract requires the verifier to reject
            # them as unexpected/unbound archive contents even without an external receipt.
            mutated = build.archive_bytes + b"UNBOUND_TRAILING_DATA"

            with self.assertRaises(ReleaseArchiveError):
                verify_release_archive(mutated, policy=policy)


if __name__ == "__main__":
    unittest.main()
