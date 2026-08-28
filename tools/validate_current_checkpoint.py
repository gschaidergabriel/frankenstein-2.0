#!/usr/bin/env python3
"""Fail-closed validator for Frankenstein 2.0 checkpoints/CURRENT.json.

This validates continuity/source-evidence invariants only. It never grants runtime
or whole-system acceptance. Active workpackage identity and machine-readable state
are bound to the checkpoint. A terminal active pointer is accepted only when an
exact matching reconciliation record is present.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SHA40 = re.compile(r"^[0-9a-f]{40}$")
WP = re.compile(r"^F2-WP-[0-9]+$")
TERMINAL_ACTIVE_STATES = {"ACCEPTED", "FAILED_TERMINAL", "RETIRED_STALE", "SUPERSEDED"}

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


def _validate_checkpoint_core(checkpoint: dict[str, Any]) -> None:
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
        if "commit" in item:
            commit = item["commit"]
            _require(isinstance(commit, str) and bool(SHA40.fullmatch(commit)),
                     f"strongest_current_evidence[{idx}].commit malformed")

    for field in ("completed_this_checkpoint", "unresolved"):
        values = checkpoint[field]
        _require(isinstance(values, list) and all(isinstance(x, str) and x.strip() for x in values),
                 f"{field} must be a string list")
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


def _bind_legacy_claim(checkpoint: dict[str, Any], claim: dict[str, Any]) -> None:
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


def _bind_reconciliation(checkpoint: dict[str, Any], active: dict[str, Any], reconciliation: dict[str, Any]) -> None:
    _require(reconciliation.get("schema") == "FRANKENSTEIN2_WORKPACKAGE_RECONCILIATION/v1",
             "reconciliation schema mismatch")
    for field, checkpoint_field in (
        ("workpackage_id", "current_workpackage"),
        ("generation", "generation"),
        ("claim_id", "claim_id"),
        ("worker_id", "worker_id"),
    ):
        _require(reconciliation.get(field) == checkpoint.get(checkpoint_field),
                 f"reconciliation/checkpoint identity mismatch: {field}")
    _require(reconciliation.get("terminal_state") == active.get("state"),
             "reconciliation terminal_state does not match active pointer")
    _require(reconciliation.get("whole_system_acceptance") is False,
             "component reconciliation must not assert whole-system acceptance")


def _bind_active_pointer(
    checkpoint: dict[str, Any],
    active: dict[str, Any],
    reconciliation: dict[str, Any] | None,
) -> None:
    _require(active.get("schema") == "FRANKENSTEIN2_ACTIVE_WORKPACKAGE/v1", "active schema mismatch")
    for active_field, checkpoint_field in (
        ("workpackage_id", "current_workpackage"),
        ("generation", "generation"),
        ("claim_id", "claim_id"),
        ("worker_id", "worker_id"),
    ):
        _require(active.get(active_field) == checkpoint.get(checkpoint_field),
                 f"active/checkpoint identity mismatch: {active_field}")
    base_commit = active.get("base_commit")
    _require(isinstance(base_commit, str) and bool(SHA40.fullmatch(base_commit)),
             "active base_commit malformed")

    active_state = active.get("state")
    if active_state == "ACTIVE":
        _require(reconciliation is None,
                 "terminal reconciliation supplied while active pointer is still ACTIVE")
        return
    _require(active_state in TERMINAL_ACTIVE_STATES, "active pointer has invalid state")
    _require(reconciliation is not None, "terminal active pointer requires reconciliation")
    _bind_reconciliation(checkpoint, active, reconciliation)


def _bind_workpackage_state(checkpoint: dict[str, Any], state: dict[str, Any]) -> None:
    _require(state.get("schema") == "FRANKENSTEIN2_WORKPACKAGE_STATE/v1", "state schema mismatch")
    _require(state.get("canonical_repository") == checkpoint["canonical_repository"],
             "state canonical_repository mismatch")
    workpackages = state.get("workpackages")
    _require(isinstance(workpackages, dict), "state workpackages object required")
    entry = workpackages.get(checkpoint["current_workpackage"])
    _require(isinstance(entry, dict), "checkpoint workpackage absent from state")
    _require(entry.get("status") in {"IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"},
             "checkpoint points to NOT_STARTED or invalid workpackage state")


def validate_checkpoint(
    checkpoint: dict[str, Any],
    claim: dict[str, Any] | None = None,
    active: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    reconciliation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_checkpoint_core(checkpoint)
    if claim is not None:
        _bind_legacy_claim(checkpoint, claim)
    if active is not None:
        _bind_active_pointer(checkpoint, active, reconciliation)
    elif reconciliation is not None:
        raise ValidationError("reconciliation supplied without active pointer")
    if state is not None:
        _bind_workpackage_state(checkpoint, state)

    return {
        "pass": True,
        "scope": "SOURCE_AND_CONTINUITY_METADATA_ONLY",
        "runtime_credit_granted": 0,
        "workpackage": checkpoint["current_workpackage"],
        "generation": checkpoint["generation"],
        "claim_id": checkpoint["claim_id"],
        "legacy_claim_bound": claim is not None,
        "active_pointer_bound": active is not None,
        "workpackage_state_bound": state is not None,
        "reconciliation_bound": reconciliation is not None,
        "active_state": active.get("state") if active is not None else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--claim", type=Path)
    parser.add_argument("--active", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--reconciliation", type=Path)
    args = parser.parse_args(argv)
    try:
        checkpoint = load_json(args.checkpoint)
        claim = load_json(args.claim) if args.claim else None
        active = load_json(args.active) if args.active else None
        state = load_json(args.state) if args.state else None
        reconciliation = load_json(args.reconciliation) if args.reconciliation else None

        # Terminal pointers carry a canonical reconciliation reference. During
        # protocol migration both names are admitted, with the explicit terminal
        # name preferred. The referenced reconciliation is still fully identity-bound.
        if active is not None and active.get("state") in TERMINAL_ACTIVE_STATES and reconciliation is None:
            ref_value = active.get("terminal_reconciliation_ref") or active.get("reconciliation_ref")
            ref = _nonempty_string(ref_value, "active.terminal_reconciliation_ref")
            repo_root = args.checkpoint.resolve().parents[1]
            reconciliation = load_json(repo_root / ref)

        result = validate_checkpoint(checkpoint, claim, active, state, reconciliation)
    except ValidationError as exc:
        print(json.dumps({"pass": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
