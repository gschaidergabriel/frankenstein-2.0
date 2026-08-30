#!/usr/bin/env python3
"""REVIEW_ONLY falsifier for active F2-WP-1107 generation 3.

This test asks a stricter question than the current EOCD-tail check: can a caller prepend
unbound bytes while rebasing every absolute classic-ZIP offset so the archive remains
structurally valid? Such a self-extracting-style prefix is part of the handed-off byte string
but is neither a manifest member nor a deterministic builder output.

Expected invariant: verify_release_archive() must fail closed even without expected_receipt.
A failing CI run is therefore intended negative evidence against the active repair, not
mutation authority for this review branch.
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

SOURCE_COMMIT = "c" * 40
SOURCE_TREE = "t" * 40
EPOCH = 1_700_000_000
EOCD_SIGNATURE = b"PK\x05\x06"
CENTRAL_DIRECTORY_SIGNATURE = b"PK\x01\x02"
EOCD_SIZE = 22
CENTRAL_DIRECTORY_FIXED_SIZE = 46


def _populate(root: Path) -> None:
    entries = (
        ("bin/run.sh", b"#!/bin/sh\nprintf 'frankenstein-2.0\\n'\n"),
        ("data/config.txt", b"alpha=1\nbeta=2\n"),
        ("share/readme.txt", b"portable release fixture\n"),
    )
    for rel, data in entries:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.chmod(path, 0o755 if rel == "bin/run.sh" else 0o644)


def _policy() -> ReleaseArchivePolicy:
    return ReleaseArchivePolicy(
        policy_id="f2-release-zip-stored-posix-v1",
        source_date_epoch=EPOCH,
        executable_paths=("bin/run.sh",),
    )


def _build(root: Path):
    return build_release_archive(
        root,
        release_id="frankenstein-2.0-review",
        source_commit=SOURCE_COMMIT,
        source_tree=SOURCE_TREE,
        build_id="wp1107-g3-rebased-prefix-review",
        policy=_policy(),
        prehandoff_receipt_refs=("receipt/a",),
    )


def _prepend_prefix_and_rebase_absolute_offsets(
    archive_bytes: bytes,
    prefix: bytes,
) -> bytes:
    """Create a valid classic ZIP whose unbound prefix is invisible to member validation."""
    if not prefix:
        raise AssertionError("review prefix must be non-empty")
    eocd_offset = len(archive_bytes) - EOCD_SIZE
    if archive_bytes[eocd_offset : eocd_offset + 4] != EOCD_SIGNATURE:
        raise AssertionError("fixture is not canonical no-comment classic ZIP")

    central_directory_size = int.from_bytes(
        archive_bytes[eocd_offset + 12 : eocd_offset + 16], "little"
    )
    central_directory_offset = int.from_bytes(
        archive_bytes[eocd_offset + 16 : eocd_offset + 20], "little"
    )
    delta = len(prefix)
    mutated = bytearray(prefix + archive_bytes)
    new_eocd_offset = eocd_offset + delta
    new_central_directory_offset = central_directory_offset + delta
    mutated[new_eocd_offset + 16 : new_eocd_offset + 20] = (
        new_central_directory_offset.to_bytes(4, "little")
    )

    cursor = new_central_directory_offset
    end = new_central_directory_offset + central_directory_size
    while cursor < end:
        if mutated[cursor : cursor + 4] != CENTRAL_DIRECTORY_SIGNATURE:
            raise AssertionError("unexpected central-directory layout in deterministic fixture")
        local_header_offset = int.from_bytes(mutated[cursor + 42 : cursor + 46], "little")
        mutated[cursor + 42 : cursor + 46] = (local_header_offset + delta).to_bytes(
            4, "little"
        )
        filename_length = int.from_bytes(mutated[cursor + 28 : cursor + 30], "little")
        extra_length = int.from_bytes(mutated[cursor + 30 : cursor + 32], "little")
        comment_length = int.from_bytes(mutated[cursor + 32 : cursor + 34], "little")
        cursor += (
            CENTRAL_DIRECTORY_FIXED_SIZE
            + filename_length
            + extra_length
            + comment_length
        )
    if cursor != end:
        raise AssertionError("central-directory traversal did not close exactly")
    return bytes(mutated)


class RebasedPrefixReviewTests(unittest.TestCase):
    def test_rebased_unbound_prefix_must_fail_closed_without_expected_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wp1107-prefix-review-") as tmp:
            root = Path(tmp)
            _populate(root)
            build = _build(root)
            mutated = _prepend_prefix_and_rebase_absolute_offsets(
                build.archive_bytes,
                b"UNBOUND_SELF_EXTRACTING_PREFIX",
            )

            self.assertNotEqual(mutated, build.archive_bytes)
            with self.assertRaises(ReleaseArchiveError):
                verify_release_archive(mutated, policy=_policy())


if __name__ == "__main__":
    unittest.main()
