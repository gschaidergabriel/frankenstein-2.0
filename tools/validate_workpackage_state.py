#!/usr/bin/env python3
"""Fail-closed validator for Frankenstein 2.0 machine-readable workpackage state.

Scope is source/continuity metadata only. This validator never grants cognitive-runtime,
GRID10, provider, VPS, effect, or whole-system acceptance.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO = "gschaidergabriel/frankenstein-2.0"
STATE_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_STATE/v1"
ACTIVE_SCHEMA = "FRANKENSTEIN2_ACTIVE_WORKPACKAGE/v1"
CLAIM_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_CLAIM/v1"
RECON_SCHEMA = "FRANKENSTEIN2_WORKPACKAGE_RECONCILIATION/v1"
WP = re.compile(r"^F2-WP-[0-9]+$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
STATE_VALUES = {"NOT_STARTED", "IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"}
ACTIVE_VALUES = {"ACTIVE", "ACCEPTED", "FAILED_TERMINAL", "RETIRED_STALE", "SUPERSEDED"}
TERMINAL_ACTIVE_VALUES = ACTIVE_VALUES - {"ACTIVE"}
OPEN_STATE_VALUES = {"IN_PROGRESS", "HOLD", "BLOCKED"}


class ValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _string(value: Any, field: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{field}: non-empty string required")
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{path}: unreadable JSON: {exc}") from exc
    _require(isinstance(value, dict), f"{path}: top-level object required")
    return value


def validate_state(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    _require(state.get("schema") == STATE_SCHEMA, "state schema mismatch")
    _require(state.get("canonical_repository") == REPO, "state canonical_repository mismatch")
    generation = state.get("generation")
    _require(type(generation) is int and generation >= 1, "state generation must be integer >= 1")
    workpackages = state.get("workpackages")
    _require(isinstance(workpackages, dict), "state workpackages object required")
    for workpackage_id, entry in workpackages.items():
        _require(isinstance(workpackage_id, str) and bool(WP.fullmatch(workpackage_id)),
                 f"malformed state workpackage id: {workpackage_id}")
        _require(isinstance(entry, dict), f"state entry must be object: {workpackage_id}")
        status = entry.get("status")
        _require(status in STATE_VALUES, f"invalid state status for {workpackage_id}: {status}")
        evidence = entry.get("evidence")
        _require(isinstance(evidence, list) and all(isinstance(x, str) and x.strip() for x in evidence),
                 f"state evidence must be string list: {workpackage_id}")
        if status == "ACCEPTED_AT_SCOPE":
            _require(bool(evidence), f"ACCEPTED_AT_SCOPE requires evidence: {workpackage_id}")
    return workpackages


def _bind_claim(pointer: dict[str, Any], claim: dict[str, Any]) -> None:
    _require(claim.get("schema") == CLAIM_SCHEMA, "claim schema mismatch")
    for field in ("workpackage_id", "generation", "claim_id", "worker_id"):
        _require(claim.get(field) == pointer.get(field), f"claim/pointer identity mismatch: {field}")
    _require(claim.get("trigger") == "4", "claim trigger must be '4'")


def _bind_reconciliation(pointer: dict[str, Any], reconciliation: dict[str, Any]) -> None:
    _require(reconciliation.get("schema") == RECON_SCHEMA, "reconciliation schema mismatch")
    for field in ("workpackage_id", "generation", "claim_id", "worker_id"):
        _require(reconciliation.get(field) == pointer.get(field),
                 f"reconciliation/pointer identity mismatch: {field}")
    _require(reconciliation.get("terminal_state") == pointer.get("state"),
             "reconciliation terminal_state mismatch")
    _require(reconciliation.get("whole_system_acceptance") is False,
             "component reconciliation must not assert whole-system acceptance")


def validate_pointer(
    *,
    filename_stem: str,
    pointer: dict[str, Any],
    claim: dict[str, Any],
    state_entry: dict[str, Any] | None,
    reconciliation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require(pointer.get("schema") == ACTIVE_SCHEMA, "active pointer schema mismatch")
    workpackage_id = _string(pointer.get("workpackage_id"), "pointer.workpackage_id")
    _require(bool(WP.fullmatch(workpackage_id)), "pointer workpackage_id malformed")
    _require(filename_stem == workpackage_id, "active filename/workpackage mismatch")
    _require(isinstance(state_entry, dict), "active pointer workpackage absent from STATE")

    generation = pointer.get("generation")
    _require(type(generation) is int and generation >= 1, "pointer generation must be integer >= 1")
    _string(pointer.get("claim_id"), "pointer.claim_id")
    _string(pointer.get("worker_id"), "pointer.worker_id")
    base_commit = pointer.get("base_commit")
    _require(isinstance(base_commit, str) and bool(SHA40.fullmatch(base_commit)),
             "pointer base_commit malformed")
    _string(pointer.get("legacy_claim_ref"), "pointer.legacy_claim_ref")
    _bind_claim(pointer, claim)

    pointer_state = pointer.get("state")
    _require(pointer_state in ACTIVE_VALUES, f"invalid active pointer state: {pointer_state}")
    broad_status = state_entry.get("status")
    _require(broad_status in STATE_VALUES, f"invalid broad workpackage status: {broad_status}")

    if pointer_state == "ACTIVE":
        _require(broad_status in OPEN_STATE_VALUES,
                 f"ACTIVE pointer requires open broad state, got {broad_status}")
        _require(reconciliation is None, "ACTIVE pointer must not bind terminal reconciliation")
    else:
        _require(reconciliation is not None, "terminal active pointer requires reconciliation")
        _bind_reconciliation(pointer, reconciliation)
        if pointer_state == "ACCEPTED":
            broader = reconciliation.get("broader_workpackage_status")
            if broader == "IN_PROGRESS":
                _require(broad_status == "IN_PROGRESS",
                         "scoped ACCEPTED reconciliation requires broad IN_PROGRESS")
            else:
                _require(broad_status == "ACCEPTED_AT_SCOPE",
                         "terminal ACCEPTED requires broad ACCEPTED_AT_SCOPE unless explicitly scoped IN_PROGRESS")

    return {
        "workpackage_id": workpackage_id,
        "generation": generation,
        "claim_id": pointer["claim_id"],
        "pointer_state": pointer_state,
        "broad_status": broad_status,
        "reconciliation_bound": reconciliation is not None,
    }


def validate_repository(root: Path) -> dict[str, Any]:
    state_path = root / "workpackages" / "STATE.json"
    state = load_json(state_path)
    workpackages = validate_state(state)
    active_dir = root / "workpackages" / "active"
    _require(active_dir.is_dir(), "workpackages/active directory missing")

    validated: list[dict[str, Any]] = []
    for path in sorted(active_dir.glob("*.json")):
        pointer = load_json(path)
        workpackage_id = pointer.get("workpackage_id")
        legacy_ref = _string(pointer.get("legacy_claim_ref"), f"{path}.legacy_claim_ref")
        claim = load_json(root / legacy_ref)
        reconciliation = None
        if pointer.get("state") in TERMINAL_ACTIVE_VALUES:
            reconciliation_ref = _string(
                pointer.get("terminal_reconciliation_ref"),
                f"{path}.terminal_reconciliation_ref",
            )
            reconciliation = load_json(root / reconciliation_ref)
        validated.append(validate_pointer(
            filename_stem=path.stem,
            pointer=pointer,
            claim=claim,
            state_entry=workpackages.get(workpackage_id),
            reconciliation=reconciliation,
        ))

    return {
        "pass": True,
        "scope": "SOURCE_AND_CONTINUITY_METADATA_ONLY",
        "runtime_credit_granted": 0,
        "state_generation": state["generation"],
        "active_pointers_validated": len(validated),
        "validated": validated,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        result = validate_repository(args.root.resolve())
    except ValidationError as exc:
        print(json.dumps({"pass": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
