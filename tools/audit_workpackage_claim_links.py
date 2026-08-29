#!/usr/bin/env python3
"""Read-only audit of active workpackage pointer -> archived claim links.

This is a diagnostic accelerator for F2-WP-002. It never repairs state and never
grants runtime, GRID10, provider, effect, training or whole-system credit.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def audit(root: Path) -> dict:
    claims: dict[str, str] = {}
    for path in sorted((root / "workpackages" / "claims").glob("*.json")):
        value = load(path)
        claim_id = value.get("claim_id")
        if isinstance(claim_id, str) and claim_id:
            claims[claim_id] = str(path.relative_to(root))

    missing: list[dict[str, object]] = []
    for path in sorted((root / "workpackages" / "active").glob("*.json")):
        pointer = load(path)
        claim_id = pointer.get("claim_id")
        if isinstance(claim_id, str) and claim_id and claim_id not in claims:
            missing.append({
                "workpackage_id": pointer.get("workpackage_id"),
                "generation": pointer.get("generation"),
                "pointer_state": pointer.get("state"),
                "claim_id": claim_id,
                "pointer_path": str(path.relative_to(root)),
                "reconciliation_ref": pointer.get("reconciliation_ref"),
            })

    return {
        "schema": "FRANKENSTEIN2_WORKPACKAGE_CLAIM_LINK_AUDIT/v1",
        "pass": not missing,
        "missing_count": len(missing),
        "missing": missing,
        "runtime_credit_granted": 0,
        "whole_system_acceptance": False,
    }


def main(argv: list[str] | None = None) -> int:
    root = Path((argv or sys.argv[1:])[0] if (argv or sys.argv[1:]) else ".").resolve()
    result = audit(root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
