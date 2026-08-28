#!/usr/bin/env python3
"""Fail-closed validator for Frankenstein 2.0 workpackage state/claim generations."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ACTIVE_RE = re.compile(r"^F2-WP-(\d+)$")
CLAIM_FILE_RE = re.compile(r"^(F2-WP-\d+)_G(\d+)_([^/]+)\.json$")
ALLOWED_STATES = {"NOT_STARTED", "IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"}


class ValidationError(Exception):
    pass


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"expected object: {path}")
    return value


def require(obj: dict, key: str, path: Path):
    if key not in obj:
        raise ValidationError(f"missing {key!r}: {path}")
    return obj[key]


def validate(root: Path, workpackage: str) -> list[str]:
    m = ACTIVE_RE.fullmatch(workpackage)
    if not m:
        raise ValidationError(f"invalid workpackage id: {workpackage}")

    state_path = root / "workpackages" / "STATE.json"
    active_path = root / "workpackages" / "active" / f"{workpackage}.json"
    state = load_json(state_path)
    active = load_json(active_path)

    states = require(state, "workpackages", state_path)
    if not isinstance(states, dict) or workpackage not in states:
        raise ValidationError(f"workpackage absent from STATE.json: {workpackage}")
    state_row = states[workpackage]
    if not isinstance(state_row, dict):
        raise ValidationError(f"invalid STATE row: {workpackage}")

    if require(active, "workpackage_id", active_path) != workpackage:
        raise ValidationError("active filename/workpackage_id mismatch")
    generation = require(active, "generation", active_path)
    claim_id = require(active, "claim_id", active_path)
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise ValidationError("generation must be a positive integer")
    if not isinstance(claim_id, str) or not claim_id:
        raise ValidationError("claim_id must be a non-empty string")

    claim_dir = root / "workpackages" / "claims"
    candidates = []
    for path in claim_dir.glob(f"{workpackage}_G{generation}_*.json"):
        match = CLAIM_FILE_RE.fullmatch(path.name)
        if match:
            candidates.append(path)
    if not candidates:
        raise ValidationError(f"no claim file for {workpackage} generation {generation}")

    matching = None
    claim = None
    for path in sorted(candidates):
        candidate = load_json(path)
        if candidate.get("claim_id") == claim_id:
            matching = path
            claim = candidate
            break
    if matching is None or claim is None:
        raise ValidationError(f"active claim_id has no matching claim file: {claim_id}")

    filename_match = CLAIM_FILE_RE.fullmatch(matching.name)
    assert filename_match
    if filename_match.group(1) != workpackage:
        raise ValidationError("claim filename/workpackage mismatch")
    if int(filename_match.group(2)) != generation:
        raise ValidationError("claim filename/generation mismatch")

    for field in ("workpackage_id", "generation", "claim_id", "worker_id", "base_commit"):
        if require(active, field, active_path) != require(claim, field, matching):
            raise ValidationError(f"active/claim mismatch: {field}")

    state_status = require(state_row, "status", state_path)
    claim_status = require(claim, "status", matching)
    if state_status not in ALLOWED_STATES:
        raise ValidationError(f"unsupported STATE status: {state_status}")

    terminal = state_status == "ACCEPTED_AT_SCOPE"
    if terminal:
        if not str(claim_status).startswith("ACCEPTED"):
            raise ValidationError("terminal STATE requires terminal claim status")
        reconciliation = active.get("reconciliation_ref") or claim.get("reconciliation_ref")
        if not isinstance(reconciliation, str) or not reconciliation:
            raise ValidationError("terminal STATE requires reconciliation_ref")
        recon_path = root / reconciliation
        if not recon_path.is_file():
            raise ValidationError(f"terminal reconciliation file missing: {reconciliation}")
        evidence = state_row.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(isinstance(x, str) and x for x in evidence):
            raise ValidationError("ACCEPTED_AT_SCOPE requires non-empty evidence list")
    else:
        if state_status == "IN_PROGRESS" and str(claim_status).startswith("ACCEPTED"):
            raise ValidationError("IN_PROGRESS STATE cannot point at terminal claim")
        if active.get("reconciliation_ref"):
            raise ValidationError("non-terminal ACTIVE pointer must not carry reconciliation_ref")

    return [
        f"PASS workpackage={workpackage}",
        f"generation={generation}",
        f"claim={claim_id}",
        f"state={state_status}",
        f"claim_file={matching.relative_to(root)}",
        "runtime_credit=0",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("workpackage")
    args = parser.parse_args()
    try:
        for line in validate(args.root.resolve(), args.workpackage):
            print(line)
        return 0
    except ValidationError as exc:
        print(f"FAIL_CLOSED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
