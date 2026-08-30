#!/usr/bin/env python3
"""Frozen-copy E4 mutation ablation for the Trigger-6 WP510 manifest predicate.

Runs only against temporary copies of repository source. It does not mutate product
source and grants no architecture/runtime/effect/completion credit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

ROOT_REL = "src/frankenstein2/gwt_causal_path.py"
TARGET_REL = "src/frankenstein2/hyperposition.py"


def run_manifest(tool: Path, repo: Path, *, runtime: bool) -> dict[str, Any]:
    cmd = [sys.executable, str(tool), "--repo-root", str(repo), "--root-source", ROOT_REL]
    if runtime:
        cmd.append("--runtime-observe")
    proc = subprocess.run(cmd, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"manifest tool failed rc={proc.returncode} stderr={proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def make_frozen_copy(repo_root: Path, parent: Path, name: str) -> Path:
    dst = parent / name
    (dst / "src").mkdir(parents=True)
    shutil.copytree(repo_root / "src" / "frankenstein2", dst / "src" / "frankenstein2")
    return dst


def append(repo: Path, rel: str, text: str) -> None:
    with (repo / rel).open("a", encoding="utf-8") as handle:
        handle.write(text)


def root_sha(manifest: dict[str, Any]) -> str:
    for row in manifest["closure"]["files"]:
        if row["path"] == ROOT_REL:
            return row["sha256"]
    raise AssertionError("root source absent from manifest")


def closure_paths(manifest: dict[str, Any]) -> set[str]:
    return {row["path"] for row in manifest["closure"]["files"]}


def result_row(*, name: str, baseline: dict[str, Any], mutated: dict[str, Any], expect_blocker: str | None = None, expect_surface: str | None = None, expect_runtime_extra: str | None = None, expect_closure_change: bool | None = None, expect_root_same: bool = True) -> dict[str, Any]:
    blockers = set(mutated["blockers"])
    surfaces = set(mutated["closure"]["dynamic_surfaces"])
    runtime_extra = set(mutated.get("runtime_extra_local_modules", []))
    checks: dict[str, bool] = {"root_identity_expectation": (root_sha(mutated) == root_sha(baseline)) == expect_root_same}
    if expect_blocker is not None:
        checks["expected_blocker"] = expect_blocker in blockers
    if expect_surface is not None:
        checks["expected_surface"] = expect_surface in surfaces
    if expect_runtime_extra is not None:
        checks["expected_runtime_extra"] = expect_runtime_extra in runtime_extra
    if expect_closure_change is not None:
        checks["closure_change_expectation"] = (mutated["closure"]["local_closure_sha256"] != baseline["closure"]["local_closure_sha256"]) == expect_closure_change
    return {
        "case": name,
        "passed": all(checks.values()),
        "checks": checks,
        "blockers": sorted(blockers),
        "dynamic_surfaces": sorted(surfaces),
        "runtime_extra_local_modules": sorted(runtime_extra),
        "local_files": len(mutated["closure"]["files"]),
        "root_sha256": root_sha(mutated),
        "local_closure_sha256": mutated["closure"]["local_closure_sha256"],
        "manifest_sha256": mutated["manifest_sha256"],
        "completeness_class": mutated["completeness_class"],
    }


def run(repo_root: Path, tool: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        parent = Path(td)
        baseline_repo = make_frozen_copy(repo_root, parent, "baseline")
        baseline = run_manifest(tool, baseline_repo, runtime=True)
        baseline_root = root_sha(baseline)
        baseline_closure = baseline["closure"]["local_closure_sha256"]
        rows: list[dict[str, Any]] = []

        case = make_frozen_copy(repo_root, parent, "unrelated")
        (case / "src/frankenstein2/r6_unrelated_not_imported.py").write_text("VALUE = 'unrelated'\n", encoding="utf-8")
        m = run_manifest(tool, case, runtime=True)
        row = result_row(name="UNRELATED_REPO_CHURN", baseline=baseline, mutated=m, expect_closure_change=False)
        row["checks"]["semantic_closure_preserved"] = m["closure"]["local_closure_sha256"] == baseline_closure and root_sha(m) == baseline_root and m["runtime_extra_local_modules"] == []
        row["passed"] = all(row["checks"].values())
        rows.append(row)

        case = make_frozen_copy(repo_root, parent, "transitive_byte")
        append(case, TARGET_REL, "\n# trigger6 E4 transitive-byte mutation\n")
        m = run_manifest(tool, case, runtime=True)
        rows.append(result_row(name="TRANSITIVE_SOURCE_BYTE_MUTATION", baseline=baseline, mutated=m, expect_closure_change=True, expect_root_same=True))

        case = make_frozen_copy(repo_root, parent, "static_new_dep")
        (case / "src/frankenstein2/r6_new_dep.py").write_text("VALUE = 1\n", encoding="utf-8")
        append(case, TARGET_REL, "\nimport frankenstein2.r6_new_dep\n")
        m = run_manifest(tool, case, runtime=True)
        row = result_row(name="STATIC_NEW_LOCAL_DEPENDENCY", baseline=baseline, mutated=m, expect_closure_change=True, expect_root_same=True)
        row["checks"]["new_dep_entered_closure"] = "src/frankenstein2/r6_new_dep.py" in closure_paths(m)
        row["passed"] = all(row["checks"].values())
        rows.append(row)

        case = make_frozen_copy(repo_root, parent, "dynamic_import")
        (case / "src/frankenstein2/r6_dynamic_extra.py").write_text("VALUE = 2\n", encoding="utf-8")
        append(case, TARGET_REL, "\nimport importlib\n_R6_DYNAMIC_EXTRA = importlib.import_module('frankenstein2.r6_dynamic_extra')\n")
        m = run_manifest(tool, case, runtime=True)
        rows.append(result_row(name="DYNAMIC_IMPORT_RUNTIME_EXTRA", baseline=baseline, mutated=m, expect_blocker="DYNAMIC_IMPORT_OR_RUNTIME_SURFACE", expect_surface="DYNAMIC_IMPORT_CALL", expect_runtime_extra="frankenstein2.r6_dynamic_extra", expect_closure_change=True, expect_root_same=True))

        case_specs = [
            ("SYS_PATH_MUTATION", "\nimport sys\nsys.path.append('/tmp/r6_wp510_e4')\n", "SYS_PATH_MUTATION"),
            ("ENTRY_POINT_DISCOVERY", "\nfrom importlib import metadata\n_R6_ENTRY_POINTS = metadata.entry_points()\n", "ENTRY_POINT_DISCOVERY"),
            ("ENVIRONMENT_DEPENDENCY", "\nimport os\n_R6_ENVIRONMENT = os.getenv('R6_WP510_E4')\n", "ENVIRONMENT_DEPENDENCY"),
            ("NATIVE_LIBRARY_LOAD", "\nimport ctypes\n_R6_NATIVE = ctypes.CDLL(None)\n", "NATIVE_LIBRARY_LOAD"),
        ]
        for name, mutation, surface in case_specs:
            case = make_frozen_copy(repo_root, parent, name.lower())
            append(case, TARGET_REL, mutation)
            m = run_manifest(tool, case, runtime=True)
            rows.append(result_row(name=name, baseline=baseline, mutated=m, expect_blocker="DYNAMIC_IMPORT_OR_RUNTIME_SURFACE", expect_surface=surface, expect_closure_change=True, expect_root_same=True))

        passed = all(row["passed"] for row in rows)
        return {
            "schema": "FRANKENSTEIN2_TRIGGER6_WP510_FROZEN_HAZARD_ABLATION/v1",
            "classification": "E4_RESEARCH_ONLY_FROZEN_COPY_NO_PRODUCT_MUTATION",
            "passed": passed,
            "baseline": {
                "root_sha256": baseline_root,
                "local_files": len(baseline["closure"]["files"]),
                "local_closure_sha256": baseline_closure,
                "manifest_sha256": baseline["manifest_sha256"],
                "blockers": baseline["blockers"],
                "runtime_extra_local_modules": baseline["runtime_extra_local_modules"],
            },
            "cases": rows,
            "credit": {"architecture_credit": 0, "runtime_credit": 0, "whole_system_credit": 0},
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--manifest-tool", default="research/tool_intelligence/experiments/wp510_recursive_manifest.py")
    parser.add_argument("--output")
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    result = run(repo, (repo / args.manifest_tool).resolve())
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
