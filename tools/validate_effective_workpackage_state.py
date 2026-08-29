#!/usr/bin/env python3
"""Fail-closed repository validator for workpackage state-view v2.

STATE.json is a compatibility/materialized snapshot. For workpackages with a
validated append-only state-event chain, the latest event is authoritative.
This validator resolves the effective state with active-pointer and terminal
reconciliation blob bindings enabled, then checks the minimum view invariants
needed for safe re-entry.

It deliberately mints no runtime, provider, GRID10, GWT, J-Space, effect,
completion, or whole-system credit.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from resolve_workpackage_state_v2 import ValidationError, resolve_effective_state

EXPECTED_SCHEMA = "FRANKENSTEIN2_EFFECTIVE_WORKPACKAGE_STATE/v2"
REQUIRED_ROW_KEYS = {"status", "phase", "title", "evidence"}


def validate(root: Path) -> dict[str, object]:
    resolved = resolve_effective_state(root, check_active=True)

    if resolved.get("schema") != EXPECTED_SCHEMA:
        raise ValidationError(
            f"effective-state schema mismatch: {resolved.get('schema')!r}"
        )

    workpackages = resolved.get("workpackages")
    if not isinstance(workpackages, dict) or not workpackages:
        raise ValidationError("effective state must contain non-empty workpackages")

    migrated = resolved.get("migrated_event_heads")
    if not isinstance(migrated, dict):
        raise ValidationError("migrated_event_heads must be an object")

    for workpackage_id, event_head in migrated.items():
        row = workpackages.get(workpackage_id)
        if not isinstance(row, dict):
            raise ValidationError(
                f"migrated workpackage missing effective row: {workpackage_id}"
            )
        missing = REQUIRED_ROW_KEYS.difference(row)
        if missing:
            raise ValidationError(
                f"effective row missing keys for {workpackage_id}: {sorted(missing)}"
            )
        if not isinstance(event_head, str) or not event_head:
            raise ValidationError(
                f"migrated workpackage missing canonical event head: {workpackage_id}"
            )

    return {
        "schema": "FRANKENSTEIN2_EFFECTIVE_WORKPACKAGE_STATE_VALIDATION/v1",
        "result": "PASS",
        "snapshot_generation": resolved.get("snapshot_generation"),
        "effective_workpackage_count": len(workpackages),
        "migrated_workpackage_count": len(migrated),
        "credit_boundary": (
            "STATE_VIEW_ONLY_NO_PROVIDER_VPS_PERCEPTION_GRID10_GWT_JSPACE_"
            "TRAINING_EFFECT_COMPLETION_OR_WHOLE_SYSTEM_RUNTIME_CREDIT"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate(args.root.resolve())
    except ValidationError as exc:
        print(f"FAIL_CLOSED: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("PASS effective workpackage state validation")
        print(f"snapshot_generation={result['snapshot_generation']}")
        print(f"effective_workpackages={result['effective_workpackage_count']}")
        print(f"migrated_workpackages={result['migrated_workpackage_count']}")
        print(f"credit_boundary={result['credit_boundary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
