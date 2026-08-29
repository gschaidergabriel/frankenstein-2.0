#!/usr/bin/env python3
"""Deterministically rebuild the broad workpackage projection from granular pointers.

This is a metadata projection tool, not an acceptance authority. It never modifies active
pointers, claims or reconciliations and never mints runtime/physical/model/effect credit.
Accepted pointers become ACCEPTED_AT_SCOPE only when their selected reconciliation
explicitly declares broader_workpackage_status=ACCEPTED_AT_SCOPE. Otherwise the tool
fails conservative to IN_PROGRESS. Non-success terminal pointers project to HOLD unless
an existing non-NOT_STARTED broad state is already present.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

try:
    from tools import validate_workpackage_state as validator
except ModuleNotFoundError:
    # Direct script execution sets sys.path[0] to tools/ rather than repository root.
    # Import the sibling module without changing repository semantics.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import validate_workpackage_state as validator

ACTIVE = "ACTIVE"
ACCEPTED = "ACCEPTED"
NON_SUCCESS_TERMINALS = {"FAILED_TERMINAL", "RETIRED_STALE", "SUPERSEDED"}


def _phase_from_workpackage_id(workpackage_id: str) -> int:
    return int(workpackage_id.rsplit("-", 1)[1]) // 100


def _fallback_title(pointer: dict[str, Any]) -> str:
    for field in ("title", "intent", "claimed_scope"):
        value = pointer.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Current granular workpackage projection"


def _project_status(root: Path, pointer: dict[str, Any], existing_status: str | None) -> tuple[str, str]:
    pointer_state = pointer.get("state")
    if pointer_state == ACTIVE:
        return "IN_PROGRESS", "ACTIVE_POINTER"
    if pointer_state == ACCEPTED:
        matches = validator._matching_reconciliations(root, pointer)
        reconciliation = validator._select_terminal_reconciliation(
            root, matches, context=f"projection:{pointer.get('workpackage_id')}"
        )
        broader = reconciliation.get("broader_workpackage_status")
        if broader == "ACCEPTED_AT_SCOPE":
            return "ACCEPTED_AT_SCOPE", "EXPLICIT_RECONCILIATION_BROAD_ACCEPTANCE"
        if broader in {"IN_PROGRESS", "HOLD", "BLOCKED"}:
            return broader, "EXPLICIT_RECONCILIATION_BROAD_STATUS"
        return "IN_PROGRESS", "CONSERVATIVE_ACCEPTED_POINTER_FALLBACK"
    if pointer_state in NON_SUCCESS_TERMINALS:
        if existing_status in {"IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"}:
            return existing_status, "PRESERVE_EXISTING_NON_NOT_STARTED_TERMINAL_PROJECTION"
        return "HOLD", "CONSERVATIVE_NON_SUCCESS_TERMINAL_FALLBACK"
    raise validator.ValidationError(
        f"projection:{pointer.get('workpackage_id')}: unsupported pointer state {pointer_state!r}"
    )


def rebuild(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    state_path = root / "workpackages" / "STATE.json"
    original = validator.load_json(state_path)
    contract = validator.load_contract(root)
    validator.validate_state(original, contract)

    rebuilt = copy.deepcopy(original)
    workpackages = rebuilt["workpackages"]
    changes: list[dict[str, Any]] = []

    for pointer_path in sorted((root / "workpackages" / "active").glob("*.json")):
        pointer = validator.load_json(pointer_path)
        workpackage_id = pointer.get("workpackage_id")
        if not isinstance(workpackage_id, str):
            raise validator.ValidationError(f"{pointer_path}: missing workpackage_id")
        existing = workpackages.get(workpackage_id)
        existing_status = existing.get("status") if isinstance(existing, dict) else None
        projected_status, basis = _project_status(root, pointer, existing_status)

        if existing is None:
            existing = {
                "status": projected_status,
                "phase": _phase_from_workpackage_id(workpackage_id),
                "title": _fallback_title(pointer),
                "evidence": [],
            }
            workpackages[workpackage_id] = existing
        before = copy.deepcopy(existing)
        existing["status"] = projected_status
        evidence = existing.setdefault("evidence", [])
        if not isinstance(evidence, list):
            raise validator.ValidationError(f"{workpackage_id}: evidence must be a list")
        pointer_ref = pointer_path.relative_to(root).as_posix()
        if pointer_ref not in evidence:
            evidence.append(pointer_ref)
        existing["evidence"] = sorted(set(evidence))

        if before != existing:
            changes.append({
                "workpackage_id": workpackage_id,
                "pointer_state": pointer.get("state"),
                "from_status": before.get("status") if isinstance(before, dict) else None,
                "to_status": projected_status,
                "basis": basis,
                "pointer_ref": pointer_ref,
            })

    if changes:
        rebuilt["generation"] = int(original["generation"]) + 1
        rebuilt["recorded_date"] = "2026-08-29"

    report = {
        "schema": "FRANKENSTEIN2_AGGREGATE_PROJECTION_REBUILD_REPORT/v1",
        "source_state_generation": original["generation"],
        "generated_state_generation": rebuilt["generation"],
        "changed": bool(changes),
        "change_count": len(changes),
        "changes": changes,
        "runtime_credit": 0,
        "physical_grid10_credit": 0,
        "whole_system_acceptance": False,
    }
    return rebuilt, report


def _dump(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    rebuilt, report = rebuild(root)
    if args.output:
        args.output.write_text(_dump(rebuilt), encoding="utf-8")
    else:
        print(_dump(rebuilt), end="")
    if args.report:
        args.report.write_text(_dump(report), encoding="utf-8")
    if args.check and report["changed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
