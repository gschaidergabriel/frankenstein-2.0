#!/usr/bin/env python3
"""Fail-closed WP-002 aggregate projection gate for State View v2.

The v2 resolver may intentionally let legacy workpackages/STATE.json lag behind
validated append-only state events. This gate checks the *effective* v2 view
against every current active workpackage pointer so active/accepted work cannot
silently disappear or regress to NOT_STARTED.

This is metadata/projection validation only. It mints no runtime, provider,
GRID10, GWT, J-Space, training, effect, completion, or whole-system credit.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import resolve_workpackage_state_v2 as resolver  # noqa: E402

ACTIVE_ROOT_REL = Path("workpackages/active")
ACTIVE_SCHEMA = "FRANKENSTEIN2_ACTIVE_WORKPACKAGE_CLAIM/v1"


class ProjectionValidationError(Exception):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectionValidationError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectionValidationError(f"expected JSON object: {path}")
    return value


def validate_projection(root: Path) -> dict[str, Any]:
    root = root.resolve()
    effective = resolver.resolve_effective_state(root, check_active=True)
    rows = effective.get("workpackages")
    if not isinstance(rows, dict):
        raise ProjectionValidationError("effective workpackages view must be an object")

    active_root = root / ACTIVE_ROOT_REL
    if not active_root.is_dir():
        raise ProjectionValidationError(f"missing active pointer directory: {ACTIVE_ROOT_REL}")

    checked: list[str] = []
    for path in sorted(active_root.glob("F2-WP-*.json")):
        pointer = _load_json(path)
        if pointer.get("schema") != ACTIVE_SCHEMA:
            continue
        wp = pointer.get("workpackage_id")
        state = pointer.get("state")
        if not isinstance(wp, str) or not wp:
            raise ProjectionValidationError(f"{path}: missing workpackage_id")
        if not isinstance(state, str) or not state:
            raise ProjectionValidationError(f"{path}: missing state")

        row = rows.get(wp)
        if not isinstance(row, dict):
            raise ProjectionValidationError(
                f"{wp}: active pointer is absent from effective State View v2"
            )
        broad = row.get("status")
        if state == "ACTIVE" and broad == "NOT_STARTED":
            raise ProjectionValidationError(
                f"{wp}: ACTIVE pointer cannot project as NOT_STARTED"
            )
        if state == "ACCEPTED" and broad != "ACCEPTED_AT_SCOPE":
            raise ProjectionValidationError(
                f"{wp}: ACCEPTED pointer requires broad ACCEPTED_AT_SCOPE, got {broad!r}"
            )
        checked.append(wp)

    return {
        "schema": "F2_WP002_EFFECTIVE_PROJECTION_VALIDATION/v2",
        "checked_active_pointers": checked,
        "checked_count": len(checked),
        "migrated_event_heads": effective.get("migrated_event_heads", {}),
        "runtime_credit": 0,
        "whole_system_acceptance": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate_projection(args.root)
    except (ProjectionValidationError, resolver.ValidationError) as exc:
        print(f"WP002_PROJECTION_INVALID: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"WP002_PROJECTION_VALID checked={result['checked_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
