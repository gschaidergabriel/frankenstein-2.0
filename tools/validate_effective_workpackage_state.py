#!/usr/bin/env python3
"""Validate current Frankenstein 2.0 workpackage state through the v2 effective view.

`workpackages/STATE.json` is a compatibility snapshot. Once a workpackage has an
admitted append-only state-event chain, STATE_CONCURRENCY_PROTOCOL_V2 makes that
validated event head authoritative for the effective row. This bridge preserves
all legacy claim/reconciliation checks while refusing to require migrated rows to
be synchronously copied back into the global snapshot.

Scope: continuity/projection metadata only. This script grants no runtime, VPS,
GRID10, GWT/J-Space, provider/model, training, effect, completion, or whole-system
credit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import validate_workpackage_state as legacy
from resolve_workpackage_state_v2 import (
    TERMINAL_STATES,
    ValidationError as StateV2ValidationError,
    load_event_chain,
    resolve_effective_state,
)


class ValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _terminal_reconciliation_for_migrated(
    root: Path, workpackage_id: str
) -> dict[str, Any]:
    chain = load_event_chain(root, workpackage_id)
    _require(bool(chain), f"migrated workpackage has no event chain: {workpackage_id}")
    head = chain[-1].data
    reconciliation_ref = head.get("reconciliation_ref")
    _require(
        isinstance(reconciliation_ref, str) and bool(reconciliation_ref),
        f"terminal migrated workpackage lacks reconciliation_ref: {workpackage_id}",
    )
    return legacy.load_json(root / reconciliation_ref)


def validate_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    contract = legacy.load_contract(root)

    # The snapshot remains structurally validated, but it is not current-state authority
    # for rows that have migrated to append-only state events.
    snapshot = legacy.load_json(root / "workpackages" / "STATE.json")
    legacy.validate_state(snapshot, contract)

    try:
        resolved = resolve_effective_state(root, check_active=True)
    except StateV2ValidationError as exc:
        raise ValidationError(f"effective state v2 failed closed: {exc}") from exc

    effective_state = dict(snapshot)
    effective_state["workpackages"] = resolved["workpackages"]
    workpackages = legacy.validate_state(effective_state, contract)
    migrated = set(resolved["migrated_event_heads"])

    active_dir = root / "workpackages" / "active"
    _require(active_dir.is_dir(), "workpackages/active directory missing")
    claims = legacy._claims_by_id(root)

    # ACCEPTED_AT_SCOPE still requires at least one concrete repository-local evidence ref.
    for workpackage_id, entry in workpackages.items():
        if entry.get("status") == "ACCEPTED_AT_SCOPE":
            evidence = entry["evidence"]
            _require(
                any((root / item).exists() for item in evidence),
                f"ACCEPTED_AT_SCOPE has no existing repository-local evidence: {workpackage_id}",
            )

    validated: list[dict[str, Any]] = []
    for path in sorted(active_dir.glob("*.json")):
        pointer = legacy.load_json(path)
        claim_id = legacy._string(pointer.get("claim_id"), f"{path}.claim_id")
        claim = claims.get(claim_id)
        _require(claim is not None, f"{path}: no matching claim object for {claim_id}")

        workpackage_id = pointer.get("workpackage_id")
        reconciliation = None
        if pointer.get("state") in set(contract["terminal_states"]):
            if workpackage_id in migrated:
                # The v2 resolver already bound the event head to the exact active-pointer
                # and reconciliation Git blobs. Re-use that one causal reconciliation rather
                # than treating append-only historical reconciliations as parallel authorities.
                reconciliation = _terminal_reconciliation_for_migrated(root, workpackage_id)
            else:
                matches = legacy._matching_reconciliations(root, pointer)
                _require(
                    len(matches) == 1,
                    f"{path}: non-migrated terminal pointer requires exactly one matching reconciliation; found {len(matches)}",
                )
                reconciliation = matches[0][1]

        validated.append(
            legacy.validate_pointer(
                filename_stem=path.stem,
                pointer=pointer,
                claim=claim,
                state_entry=workpackages.get(workpackage_id),
                contract=contract,
                reconciliation=reconciliation,
            )
        )

    return {
        "pass": True,
        "scope": "EFFECTIVE_STATE_V2_PLUS_LEGACY_CLAIM_RECONCILIATION_VALIDATION_ONLY",
        "snapshot_generation": snapshot["generation"],
        "migrated_workpackages": len(migrated),
        "active_pointers_validated": len(validated),
        "runtime_credit_granted": 0,
        "whole_system_acceptance": False,
        "validated": validated,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        result = validate_repository(args.root)
    except (ValidationError, legacy.ValidationError) as exc:
        print(
            json.dumps(
                {"pass": False, "error": str(exc), "runtime_credit_granted": 0},
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
