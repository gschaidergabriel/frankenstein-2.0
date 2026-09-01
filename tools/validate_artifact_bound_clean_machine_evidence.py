#!/usr/bin/env python3
"""Validate caller-supplied real-host observations against one exact release ZIP.

This command is an ingestion/validation tool only. It performs no host observation and
mints no runtime, physical-host, effect, completion, or whole-system credit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from frankenstein2.artifact_bound_clean_machine_evidence import (
    ArtifactBoundEvidenceIngestError,
    evaluate_artifact_bound_clean_machine_evidence,
)


def _load_json(path: Path, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactBoundEvidenceIngestError(f"cannot load {label}: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--prehandoff", required=True, type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--perception-required", action="store_true")
    args = parser.parse_args(argv)

    prehandoff = _load_json(args.prehandoff, "artifact-bound prehandoff receipt")
    observations = _load_json(args.observations, "clean-machine observations")
    result = evaluate_artifact_bound_clean_machine_evidence(
        artifact_path=args.artifact,
        prehandoff_record=prehandoff,
        observation_records=observations,
        perception_required=args.perception_required,
    )
    payload = result.canonical_bytes()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    sys.stdout.buffer.write(payload)
    return 0 if result.status == "READY_FOR_ADMISSION_REVIEW" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ArtifactBoundEvidenceIngestError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
