#!/usr/bin/env python3
"""Fail-closed validator for Frankenstein 2.0 checkpoints/CURRENT.json.

This validates continuity/source-evidence invariants only. It never grants runtime
or whole-system acceptance.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SHA40 = re.compile(r"^[0-9a-f]{40}$")
WP = re.compile(r"^F2-WP-[0-9]+$")

REQUIRED = {
    "schema", "canonical_repository", "trigger", "worker_id",
    "current_workpackage", "generation", "claim_id",
    "checkpoint_parent_main", "worker_claim_commit",
    "observed_parallel_frontier", "strongest_current_evidence",
    "completed_this_checkpoint", "unresolved", "evidence_scope",
    "runtime_execution_observed", "runtime_credit",
    "whole_system_acceptance", "next_exact_action",
}


class ValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _nonempty_string(value: Any, field: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{field}: non-empty string required")
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{path}: unreadable JSON: {exc}") from exc
    _require(isinstance(value, dict), f"{path}: top-level object required")
    return value


def validate_checkpoint(checkpoint: dict[str, Any], claim: dict[str, Any] | None = None) -> None:
    missing = sorted(REQUIRED - checkpoint.keys())
    _require(not missing, f"missing required fields: {', '.join(missing)}")

    _require(checkpoint["schema"] == "FRANKENSTEIN2_CURRENT_CHECKPOINT/v1", "schema mismatch")
    _require(checkpoint["canonical_repository"] == "gschaidergabriel/frankenstein-2.0",
             "canonical_repository mismatch")
    _require(checkpoint["trigger"] == "4", "trigger must be '4'")

    wp = _nonempty_string(checkpoint["current_workpackage"], "current_workpackage")
    _require(bool(WP.fullmatch(wp)), "current_workpackage malformed")

    generation = checkpoint["generation"]
    _require(type(generation) is int and generation >= 1, "generation must be integer >= 1")
    _nonempty_string(checkpoint["claim_id"], "claim_id")
    _nonempty_string(checkpoint["worker_id"], "worker_id")

    for field in ("checkpoint_parent_main", "worker_claim_commit"):
        value = checkpoint[field]
        _require(isinstance(value, str) and bool(SHA40.fullmatch(value)),
                 f"{field}: lowercase 40-hex commit required")

    frontier = checkpoint["observed_parallel_frontier"]
    _require(isinstance(frontier, dict), "observed_parallel_frontier must be an object")
    for key, value in frontier.items():
        _require(bool(WP.fullmatch(str(key))), f"observed_parallel_frontier key malformed: {key}")
        _nonempty_string(value, f"observed_parallel_frontier[{key}]")

    evidence = checkpoint["strongest_current_evidence"]
    _require(isinstance(evidence, list) and len(evidence) > 0,
             "strongest_current_evidence must be non-empty")
    for idx, item in enumerate(evidence):
        _require(isinstance(item, dict), f"strongest_current_evidence[{idx}] must be object")
        _nonempty_string(item.get("type"), f"strongest_current_evidence[{idx}].type")
        _nonempty_string(item.get("path"), f"strongest_current_evidence[{idx}].path")

    completed = checkpoint["completed_this_checkpoint"]
    unresolved = checkpoint["unresolved"]
    _require(isinstance(completed, list) and all(isinstance(x, str) and x.strip() for x in completed),
             "completed_this_checkpoint must be a string list")
    _require(isinstance(unresolved, list) and all(isinstance(x, str) and x.strip() for x in unresolved),
             "unresolved must be a string list")
    _nonempty_string(checkpoint["evidence_scope"], "evidence_scope")
    _nonempty_string(checkpoint["next_exact_action"], "next_exact_action")

    observed = checkpoint["runtime_execution_observed"]
    credit = checkpoint["runtime_credit"]
    accepted = checkpoint["whole_system_acceptance"]
    _require(type(observed) is bool, "runtime_execution_observed must be boolean")
    _require(type(credit) in (int, float) and not isinstance(credit, bool) and credit >= 0,
             "runtime_credit must be numeric >= 0")
    _require(type(accepted) is bool, "whole_system_acceptance must be boolean")
    _require(observed or credit == 0, "runtime_credit must be 0 without observed runtime execution")
    _require(observed or accepted is False,
             "whole_system_acceptance cannot be true without observed runtime execution")

    if claim is not None:
        _require(claim.get("schema") == "FRANKENSTEIN2_WORKPACKAGE_CLAIM/v1", "claim schema mismatch")
        for claim_field, checkpoint_field in (
            ("workpackage_id", "current_workpackage"),
            ("generation", "generation"),
            ("claim_id", "claim_id"),
            ("worker_id", "worker_id"),
            ("trigger", "trigger"),
        ):
            _require(claim.get(claim_field) == checkpoint.get(checkpoint_field),
                     f"claim/checkpoint identity mismatch: {claim_field}")
        _require(claim.get("runtime_credit") in (0, 0.0),
                 "claim itself carries non-zero runtime credit")
        _require(claim.get("runtime_execution_observed") is False,
                 "source/continuity claim unexpectedly asserts runtime execution")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--claim", type=Path)
    args = parser.parse_args(argv)
    try:
        checkpoint = load_json(args.checkpoint)
        claim = load_json(args.claim) if args.claim else None
        validate_checkpoint(checkpoint, claim)
    except ValidationError as exc:
        print(json.dumps({"pass": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({
        "pass": True,
        "scope": "SOURCE_AND_CONTINUITY_METADATA_ONLY",
        "runtime_credit_granted": 0,
        "workpackage": checkpoint["current_workpackage"],
        "generation": checkpoint["generation"],
        "claim_id": checkpoint["claim_id"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
