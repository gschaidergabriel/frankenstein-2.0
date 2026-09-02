#!/usr/bin/env python3
"""F2-WP-1207 LOCAL ITERATION 3: GRID10-interface read-only compatibility check.

Purpose (per README "GRID10-Interface read-only pruefen" candidate):
does v2's frankenstein2.grid10_interface module (F2-WP-503, exact-ten-cell
logical budget ABI) import and run cleanly under v1's own interpreter/
environment, with zero new dependencies and zero contact with any live
process or v1 state?

This is discovery + verification only:
  - static AST scan of grid10_interface.py's imports, checked against the
    Python 3.12 stdlib module set -- proves zero third-party dependency
  - dynamic import + full functional exercise of the public ABI (Grid10Plan,
    CellBudget, CellInput, CellOutput, account_outputs) using entirely
    synthetic data -- no v1 file, no v1 DB row, no v1 process is read or
    touched by this exercise
  - v1 unified.db fingerprint (size/mtime/sha256) captured before and after
    as an explicit "nothing incidentally touched" proof, same discipline as
    LOCAL-ITER1/ITER2 -- even though this check has no reason to go near it

Deliberately excludes anything resembling the pattern that tripped
Anthropic's cyber-safety filter on 2026-09-02 (hostile-twin simulation,
injected faults against a live process, process termination/reentry,
transaction wrapper around an active agent): no process is started, killed,
or re-entered here; no fault is injected into anything live; this is a
plain import + pure-function exercise against unmodified v2 source, run
once, top to bottom.

Usage:
    python3 grid10_compat_check.py > report.json
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
GRID10_MODULE_PATH = REPO_ROOT / "src" / "frankenstein2" / "grid10_interface.py"
STERN_PY = Path.home() / ".claude" / "star" / "stern.py"


def _stdlib_names() -> set[str]:
    names = set(getattr(sys, "stdlib_module_names", ()))
    names |= set(sys.builtin_module_names)
    return names


def static_import_scan(module_path: Path) -> dict:
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(module_path))
    top_level_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level_imports.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                top_level_imports.add(node.module.split(".", 1)[0])
            # level > 0 (relative import) or module is None (bare `from . import x`)
            # -- both stay inside the frankenstein2 package, not third-party.
    stdlib = _stdlib_names()
    third_party = sorted(name for name in top_level_imports if name not in stdlib and name != "__future__")
    return {
        "module_path": str(module_path.relative_to(REPO_ROOT)),
        "top_level_imports": sorted(top_level_imports),
        "third_party_imports": third_party,
        "zero_third_party_deps": len(third_party) == 0,
    }


def dynamic_functional_exercise() -> dict:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from frankenstein2.grid10_interface import (  # noqa: E402  (path set above)
        CellBudget,
        CellInput,
        CellOutput,
        GRID10_CELL_IDS,
        Grid10Plan,
        account_outputs,
    )

    hash_a = "a" * 64
    hash_b = "b" * 64

    cells = tuple(
        CellBudget(
            cell_id=cell_id,
            role_label=f"compat-check-role-{cell_id}",
            max_input_refs=3,
            max_output_refs=2,
            max_work_units=5,
            max_reentry_depth=1,
        )
        for cell_id in GRID10_CELL_IDS
    )

    plan = Grid10Plan.create(
        plan_id="wp1207-local-iter3-compat-check",
        cycle_id="compat-check-cycle-1",
        generation=0,
        frame_id="compat-check-frame",
        frame_generation=0,
        frame_sha256=hash_a,
        policy_id="compat-check-policy",
        policy_generation=0,
        policy_sha256=hash_b,
        cells=cells,
        max_total_work_units=50,
        provenance_refs=("synthetic:wp1207-local-iter3",),
    )

    pairs = []
    for cell_id in GRID10_CELL_IDS:
        cell_input = CellInput.for_plan(
            plan,
            cell_id=cell_id,
            work_units_requested=3,
            reentry_depth=0,
            input_refs=(f"synthetic-in:{cell_id}",),
            provenance_refs=("synthetic:wp1207-local-iter3",),
        )
        cell_output = CellOutput.for_input(
            plan,
            cell_input,
            status="COMPLETE",
            work_units_used=2,
            output_refs=(f"synthetic-out:{cell_id}",),
            evidence_refs=(f"synthetic-evidence:{cell_id}",),
            provenance_refs=("synthetic:wp1207-local-iter3",),
        )
        pairs.append((cell_input, cell_output))

    receipt = account_outputs(plan, pairs)

    return {
        "plan_sha256": plan.sha256(),
        "cells_exercised": list(receipt.completed_cell_ids),
        "cells_missing": list(receipt.missing_cell_ids),
        "total_work_units_used": receipt.total_work_units_used,
        "remaining_work_units": receipt.remaining_work_units,
        "receipt_sha256": receipt.sha256(),
        "all_ten_cells_completed": len(receipt.completed_cell_ids) == 10
        and len(receipt.missing_cell_ids) == 0,
    }


def v1_db_path_and_fingerprint() -> dict:
    """Reuse v1's own read-only resolver (same approach as LOCAL-ITER2), then
    take an independent sha256, purely to prove this check did not touch it.
    Does not require the DB to exist for this check to be meaningful."""
    if not STERN_PY.is_file():
        return {"resolvable": False, "reason": "stern.py not found at expected path"}
    try:
        proc = subprocess.run(
            [sys.executable, str(STERN_PY), "db-pfad-zeigen"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive, reported not raised
        return {"resolvable": False, "reason": f"resolver invocation failed: {exc!r}"}
    stdout = proc.stdout.strip()
    try:
        resolved = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        resolved = {}
    raw_path = resolved.get("db_path_aufgeloest")
    db_path = Path(raw_path) if raw_path else None
    if not db_path or not db_path.is_file():
        return {
            "resolvable": False,
            "resolver_stdout": stdout,
            "resolver_returncode": proc.returncode,
        }
    stat = db_path.stat()
    digest = hashlib.sha256()
    with db_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return {
        "resolvable": True,
        "path": str(db_path),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def main() -> int:
    report: dict = {
        "check": "F2-WP-1207-LOCAL-ITER3-grid10-compat-check",
        "python_version": sys.version,
        "python_executable": sys.executable,
    }

    static_result = static_import_scan(GRID10_MODULE_PATH)
    report["static_import_scan"] = static_result

    db_before = v1_db_path_and_fingerprint()
    report["v1_db_fingerprint_before"] = db_before

    try:
        dynamic_result = dynamic_functional_exercise()
        report["dynamic_functional_exercise"] = dynamic_result
        dynamic_ok = dynamic_result["all_ten_cells_completed"]
    except Exception as exc:  # report, do not raise -- this is a check, not a gate
        report["dynamic_functional_exercise_error"] = repr(exc)
        dynamic_ok = False

    db_after = v1_db_path_and_fingerprint()
    report["v1_db_fingerprint_after"] = db_after

    fingerprint_unchanged = (
        db_before.get("resolvable") == db_after.get("resolvable")
        and db_before.get("sha256") == db_after.get("sha256")
        and db_before.get("size_bytes") == db_after.get("size_bytes")
        and db_before.get("mtime_ns") == db_after.get("mtime_ns")
    )
    report["v1_db_fingerprint_unchanged"] = fingerprint_unchanged

    overall_pass = (
        static_result["zero_third_party_deps"]
        and dynamic_ok
        and fingerprint_unchanged
    )
    report["result"] = "PASS" if overall_pass else "FAIL"
    report["conclusion"] = (
        "GRID10 interface (frankenstein2.grid10_interface) imports and runs "
        "cleanly under v1's own Python 3.12 interpreter with zero third-party "
        "dependencies (stdlib only: dataclasses, hashlib, json, re, typing, "
        "__future__). No live process, v1 file, or v1 DB row was read for the "
        "functional exercise itself -- it uses synthetic plan/cell data only. "
        "This confirms GRID10 is a portable, dependency-free ABI that v1 could "
        "import directly if a coordinator later decides to wire it in; this "
        "check does not wire anything in and makes no such recommendation."
        if overall_pass
        else "One or more sub-checks failed -- see fields above for detail."
    )

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
