#!/usr/bin/env python3
"""Emit the exact WP1107 G2 deterministic archive vector for runtime comparison."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

from frankenstein2.release_archive import ReleaseArchivePolicy, build_release_archive


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="wp1107-golden-") as tmp:
        root = Path(tmp)
        for rel, data in (
            ("bin/run.sh", b"#!/bin/sh\nprintf 'frankenstein-2.0\\n'\n"),
            ("data/config.txt", b"alpha=1\nbeta=2\n"),
            ("share/readme.txt", b"portable release fixture\n"),
        ):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        result = build_release_archive(
            root,
            release_id="frankenstein-2.0-golden",
            source_commit="c" * 40,
            source_tree="t" * 40,
            build_id="wp1107-g2-golden-v1",
            policy=ReleaseArchivePolicy(
                policy_id="f2-release-zip-stored-posix-v1",
                source_date_epoch=1_700_000_000,
                executable_paths=("bin/run.sh",),
            ),
            prehandoff_receipt_refs=("receipt/a", "receipt/b"),
        )
        print(json.dumps({
            "archive_sha256": result.receipt.archive_sha256,
            "manifest_sha256": result.receipt.manifest_sha256,
            "policy_sha256": result.receipt.archive_policy_sha256,
            "receipt_digest": result.receipt.digest(),
            "archive_size": result.receipt.archive_size,
            "member_count": result.receipt.member_count,
        }, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
