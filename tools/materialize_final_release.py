#!/usr/bin/env python3
"""Materialize one deterministic Frankenstein 2.0 release handoff candidate.

This is a build/handoff utility. Success means exact ZIP + exact pre-handoff receipt bytes
were produced and re-verified. It does not mean installation, clean-machine, physical-host,
effect, completion, or whole-system acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from frankenstein2.final_release_materialization import materialize_final_release
from frankenstein2.release_archive import ReleaseArchivePolicy


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--source-date-epoch", required=True, type=int)
    parser.add_argument(
        "--receipt-ref",
        required=True,
        help="Relative external pre-handoff receipt path, e.g. receipts/f2-prehandoff.json",
    )
    parser.add_argument(
        "--artifact-filename",
        default="frankenstein-2.0.zip",
    )
    parser.add_argument(
        "--executable-path",
        action="append",
        default=[],
        help="Canonical archive-relative executable path; repeat as needed",
    )
    parser.add_argument(
        "--result-file",
        default=None,
        help="Optional output path for the canonical materialization summary JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    policy = ReleaseArchivePolicy(
        policy_id="f2-release-zip-stored-posix-v1",
        source_date_epoch=args.source_date_epoch,
        executable_paths=tuple(sorted(set(args.executable_path))),
    )
    result = materialize_final_release(
        args.package_root,
        args.output_dir,
        release_id=args.release_id,
        source_commit=args.source_commit,
        source_tree=args.source_tree,
        build_id=args.build_id,
        policy=policy,
        prehandoff_receipt_ref=args.receipt_ref,
        artifact_filename=args.artifact_filename,
    )
    payload = result.canonical_bytes()
    if args.result_file:
        result_path = Path(args.result_file)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        if result_path.exists() and result_path.read_bytes() != payload:
            raise SystemExit("result-file exists with different bytes")
        if not result_path.exists():
            result_path.write_bytes(payload)
    sys.stdout.write(json.dumps(result.as_dict(), sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
