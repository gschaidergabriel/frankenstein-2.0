#!/usr/bin/env python3
"""Fail-closed WP-002 aggregate projection gate for State View v2.

The v2 resolver may intentionally let legacy workpackages/STATE.json lag behind
validated append-only state events. This gate checks the *effective* v2 view
against every current active workpackage pointer so active/scoped-terminal work
cannot silently disappear or regress.

A terminal ACCEPTED claim does not always mean the broader workpackage is done.
When its canonical reconciliation explicitly carries ``broader_workpackage_status``,
that status is authoritative for the aggregate projection. Otherwise ACCEPTED
falls back to ACCEPTED_AT_SCOPE.

All pointer/projection mismatches are aggregated in deterministic path order so
one CI run exposes the complete current repair set instead of hiding later drift
behind the first failure.

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
BROAD_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "HOLD", "BLOCKED", "ACCEPTED_AT_SCOPE"}


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


def _accepted_broad_status(root: Path, pointer_path: Path, pointer: dict[str, Any]) -> str:
    reconciliation_ref = pointer.get("reconciliation_ref") or pointer.get("terminal_reconciliation_ref")
    if reconciliation_ref is None:
        return "ACCEPTED_AT_SCOPE"
    if not isinstance(reconciliation_ref, str) or not reconciliation_ref:
        raise ProjectionValidationError(f"{pointer_path}: invalid reconciliation_ref")
    reconciliation_path = root / reconciliation_ref
    if not reconciliation_path.is_file():
        raise ProjectionValidationError(
            f"{pointer_path}: reconciliation_ref does not exist: {reconciliation_ref}"
        )
    reconciliation = _load_json(reconciliation_path)
    wp = pointer.get("workpackage_id")
    if reconciliation.get("workpackage_id") != wp:
        raise ProjectionValidationError(f"{wp}: pointer/reconciliation workpackage mismatch")
    if reconciliation.get("generation") != pointer.get("generation"):
        raise ProjectionValidationError(f"{wp}: pointer/reconciliation generation mismatch")
    if reconciliation.get("claim_id") != pointer.get("claim_id"):
        raise ProjectionValidationError(f"{wp}: pointer/reconciliation claim mismatch")
    explicit = reconciliation.get("broader_workpackage_status")
    if explicit is None:
        return "ACCEPTED_AT_SCOPE"
    if explicit not in BROAD_STATUSES:
        raise ProjectionValidationError(
            f"{wp}: unsupported reconciliation broader_workpackage_status {explicit!r}"
        )
    return explicit


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
    errors: list[str] = []
    for path in sorted(active_root.glob("F2-WP-*.json")):
        try:
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
            if state == "ACCEPTED":
                expected_broad = _accepted_broad_status(root, path, pointer)
                if broad != expected_broad:
                    raise ProjectionValidationError(
                        f"{wp}: ACCEPTED pointer requires broad {expected_broad}, got {broad!r}"
                    )
            checked.append(wp)
        except ProjectionValidationError as exc:
            errors.append(str(exc))

    if errors:
        raise ProjectionValidationError("\n".join(errors))

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
