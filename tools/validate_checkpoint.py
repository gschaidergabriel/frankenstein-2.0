#!/usr/bin/env python3
"""Fail-closed validator for Frankenstein 2.0 continuation checkpoints.

This validates continuity metadata only. A valid checkpoint is not runtime
execution evidence and cannot by itself promote a workpackage to accepted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

CHECKPOINT_SCHEMA = "FRANKENSTEIN2_CURRENT_CHECKPOINT/v1"
CLAIM_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_CLAIM/v1"
ACTIVE_SCHEMA = "FRANKENSTEIN2_ACTIVE_WORKPACKAGE/v1"
STATE_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_STATE/v1"
CANONICAL_REPOSITORY = "gschaidergabriel/frankenstein-2.0"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class CheckpointValidationError(ValueError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CheckpointValidationError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CheckpointValidationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CheckpointValidationError(f"expected JSON object: {path}")
    return value


def _require_nonempty_string(obj: dict[str, Any], key: str, errors: list[str]) -> str | None:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key}: required non-empty string")
        return None
    return value


def _find_claim(repo_root: Path, claim_id: str) -> tuple[Path | None, dict[str, Any] | None]:
    claim_dir = repo_root / "workpackages" / "claims"
    if not claim_dir.is_dir():
        return None, None
    for path in sorted(claim_dir.glob("*.json")):
        try:
            claim = _load_json(path)
        except CheckpointValidationError:
            continue
        if claim.get("claim_id") == claim_id:
            return path, claim
    return None, None


def validate_checkpoint(repo_root: Path, checkpoint_path: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    checkpoint_path = (checkpoint_path or repo_root / "checkpoints" / "CURRENT.json").resolve()
    cp = _load_json(checkpoint_path)
    errors: list[str] = []

    if cp.get("schema") != CHECKPOINT_SCHEMA:
        errors.append(f"schema: expected {CHECKPOINT_SCHEMA!r}, got {cp.get('schema')!r}")
    if cp.get("canonical_repository") != CANONICAL_REPOSITORY:
        errors.append(
            f"canonical_repository: expected {CANONICAL_REPOSITORY!r}, got {cp.get('canonical_repository')!r}"
        )

    trigger = _require_nonempty_string(cp, "trigger", errors)
    worker_id = _require_nonempty_string(cp, "worker_id", errors)
    workpackage_id = _require_nonempty_string(cp, "current_workpackage", errors)
    claim_id = _require_nonempty_string(cp, "claim_id", errors)
    next_action = _require_nonempty_string(cp, "next_exact_action", errors)

    generation = cp.get("generation")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        errors.append("generation: required positive integer")

    for key in ("checkpoint_parent_main", "worker_claim_commit"):
        value = cp.get(key)
        if not isinstance(value, str) or not SHA40.fullmatch(value):
            errors.append(f"{key}: required lowercase 40-hex commit SHA")

    strongest = cp.get("strongest_current_evidence")
    if not isinstance(strongest, list) or not strongest:
        errors.append("strongest_current_evidence: required non-empty list")
    else:
        for i, item in enumerate(strongest):
            if not isinstance(item, dict):
                errors.append(f"strongest_current_evidence[{i}]: expected object")
                continue
            _require_nonempty_string(item, "type", errors)
            _require_nonempty_string(item, "claim", errors)

    unresolved = cp.get("unresolved")
    if not isinstance(unresolved, list):
        errors.append("unresolved: required list")
    elif any(not isinstance(x, str) or not x.strip() for x in unresolved):
        errors.append("unresolved: every item must be a non-empty string")

    _require_nonempty_string(cp, "evidence_scope", errors)

    runtime_observed = cp.get("runtime_execution_observed")
    runtime_credit = cp.get("runtime_credit")
    whole_acceptance = cp.get("whole_system_acceptance")
    if not isinstance(runtime_observed, bool):
        errors.append("runtime_execution_observed: required boolean")
    if not isinstance(runtime_credit, (int, float)) or isinstance(runtime_credit, bool) or runtime_credit < 0:
        errors.append("runtime_credit: required non-negative number")
    if not isinstance(whole_acceptance, bool):
        errors.append("whole_system_acceptance: required boolean")
    if runtime_observed is False and runtime_credit not in (0, 0.0):
        errors.append("runtime_credit: must be 0 when runtime_execution_observed is false")
    if runtime_observed is False and whole_acceptance is True:
        errors.append("whole_system_acceptance: cannot be true when runtime_execution_observed is false")

    state = _load_json(repo_root / "workpackages" / "STATE.json")
    if state.get("schema") != STATE_SCHEMA:
        errors.append(f"STATE.json schema mismatch: {state.get('schema')!r}")
    state_wps = state.get("workpackages")
    if not isinstance(state_wps, dict) or workpackage_id not in state_wps:
        errors.append(f"current_workpackage: {workpackage_id!r} not present in workpackages/STATE.json")

    claim_path: Path | None = None
    claim: dict[str, Any] | None = None
    if claim_id:
        claim_path, claim = _find_claim(repo_root, claim_id)
        if claim is None:
            errors.append(f"claim_id: no matching claim object found for {claim_id!r}")
        else:
            if claim.get("schema") != CLAIM_SCHEMA:
                errors.append(f"claim schema mismatch: {claim.get('schema')!r}")
            bindings = {
                "workpackage_id": (claim.get("workpackage_id"), workpackage_id),
                "generation": (claim.get("generation"), generation),
                "worker_id": (claim.get("worker_id"), worker_id),
                "trigger": (claim.get("trigger"), trigger),
                "claim_id": (claim.get("claim_id"), claim_id),
            }
            for key, (actual, expected) in bindings.items():
                if actual != expected:
                    errors.append(f"claim binding mismatch {key}: claim={actual!r} checkpoint={expected!r}")

    # CURRENT is a continuation authority surface, not merely a historical claim pointer.
    # Bind it to the single mechanical active-workpackage pointer so an old, internally
    # self-consistent claim cannot masquerade as the current mutation generation.
    if workpackage_id:
        active_path = repo_root / "workpackages" / "active" / f"{workpackage_id}.json"
        try:
            active = _load_json(active_path)
        except CheckpointValidationError as exc:
            errors.append(f"active pointer: {exc}")
        else:
            if active.get("schema") != ACTIVE_SCHEMA:
                errors.append(f"active pointer schema mismatch: {active.get('schema')!r}")
            active_bindings = {
                "workpackage_id": (active.get("workpackage_id"), workpackage_id),
                "generation": (active.get("generation"), generation),
                "claim_id": (active.get("claim_id"), claim_id),
                "worker_id": (active.get("worker_id"), worker_id),
            }
            for key, (actual, expected) in active_bindings.items():
                if actual != expected:
                    errors.append(
                        f"active pointer binding mismatch {key}: active={actual!r} checkpoint={expected!r}"
                    )
            if active.get("state") != "ACTIVE":
                errors.append(f"active pointer state: expected 'ACTIVE', got {active.get('state')!r}")

    if next_action and next_action.strip().lower() in {"none", "n/a", "done"}:
        errors.append("next_exact_action: must encode an executable continuation, not a terminal placeholder")

    if errors:
        raise CheckpointValidationError("\n".join(errors))

    return {
        "schema": "FRANKENSTEIN2_CHECKPOINT_VALIDATION_RESULT/v1",
        "pass": True,
        "checkpoint": str(checkpoint_path.relative_to(repo_root)),
        "claim_path": str(claim_path.relative_to(repo_root)) if claim_path else None,
        "active_path": f"workpackages/active/{workpackage_id}.json",
        "workpackage_id": workpackage_id,
        "generation": generation,
        "claim_id": claim_id,
        "worker_id": worker_id,
        "runtime_execution_observed": runtime_observed,
        "runtime_credit": runtime_credit,
        "whole_system_acceptance": whole_acceptance,
        "next_exact_action": next_action,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate_checkpoint(args.repo_root, args.checkpoint)
    except CheckpointValidationError as exc:
        if args.json:
            print(json.dumps({"schema": "FRANKENSTEIN2_CHECKPOINT_VALIDATION_RESULT/v1", "pass": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"PASS: {result['workpackage_id']} generation={result['generation']} claim={result['claim_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
