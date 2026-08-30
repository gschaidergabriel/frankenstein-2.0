#!/usr/bin/env python3
"""REVIEW_ONLY leading-data falsifier for F2-WP-1107 generation 3.

This file does not own or modify the WP1107 implementation. It tests whether the
release verifier closes the complete archive byte boundary, including bytes before
the first canonical ZIP structure.
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


class WP1107LeadingDataReview(unittest.TestCase):
    def test_unbound_leading_bytes_before_zip_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wp1107-leading-review-") as tmp:
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
                build_id="wp1107-g3-leading-data-review",
                policy=policy,
                prehandoff_receipt_refs=("receipt/review",),
            )

            # Python zipfile intentionally supports concatenated/self-extracting ZIPs and
            # adjusts member offsets for bytes before the ZIP structures. Those bytes are
            # outside the canonical F2 archive produced by build_release_archive(), so a
            # byte-closed verifier must reject them even without expected_receipt.
            mutated = b"UNBOUND_LEADING_DATA" + build.archive_bytes

            with self.assertRaises(ReleaseArchiveError):
                verify_release_archive(mutated, policy=policy)


if __name__ == "__main__":
    unittest.main()
