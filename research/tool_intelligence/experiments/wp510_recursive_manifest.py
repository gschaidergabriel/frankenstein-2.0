#!/usr/bin/env python3
"""Research-only recursive Python dependency manifest extractor for F2 WP510.

This tool is a Trigger-6 E3 falsifier. It does not grant product, runtime,
architecture, effect, completion, GRID/GWT, J-Space, or training credit.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
from typing import Any

SCHEMA = "FRANKENSTEIN2_TRIGGER6_RECURSIVE_PYTHON_MANIFEST/v1"
F2_PACKAGE = "frankenstein2"
ENV_KEYS = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSAFEPATH",
    "PYTHONNOUSERSITE",
    "PYTHONUSERBASE",
    "VIRTUAL_ENV",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted(node.value)
        return None if left is None else f"{left}.{node.attr}"
    return None


class SurfaceVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.surfaces: set[str] = set()

    def visit_Call(self, node: ast.Call) -> Any:
        name = dotted(node.func) or ""
        tail = name.rsplit(".", 1)[-1]
        if name == "__import__" or tail in {"import_module", "spec_from_file_location", "module_from_spec"}:
            self.surfaces.add("DYNAMIC_IMPORT_CALL")
        if name.startswith("sys.path.") and tail in {"append", "extend", "insert", "remove", "pop", "clear"}:
            self.surfaces.add("SYS_PATH_MUTATION")
        if name.startswith("sys.meta_path.") or name.startswith("sys.path_hooks."):
            self.surfaces.add("IMPORT_HOOK_MUTATION")
        if tail == "entry_points":
            self.surfaces.add("ENTRY_POINT_DISCOVERY")
        if name in {"os.getenv", "os.putenv", "os.unsetenv"}:
            self.surfaces.add("ENVIRONMENT_DEPENDENCY")
        if tail in {"CDLL", "PyDLL", "WinDLL", "OleDLL", "dlopen"}:
            self.surfaces.add("NATIVE_LIBRARY_LOAD")
        if name in {"eval", "exec", "compile"}:
            self.surfaces.add("DYNAMIC_CODE_EXECUTION")
        return self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> Any:
        for target in node.targets:
            target_name = dotted(target) or ""
            if target_name in {"sys.path", "sys.meta_path", "sys.path_hooks"}:
                self.surfaces.add("IMPORT_ENVIRONMENT_REBIND")
        return self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> Any:
        target_name = dotted(node.target) or ""
        if target_name == "sys.path":
            self.surfaces.add("SYS_PATH_MUTATION")
        return self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        name = dotted(node.value) or ""
        if name == "os.environ":
            self.surfaces.add("ENVIRONMENT_DEPENDENCY")
        return self.generic_visit(node)


class ImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.modules: set[str] = set()

    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            self.modules.add(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        if node.module:
            self.modules.add(node.module)


def resolve_local_module(src_root: Path, module: str) -> Path | None:
    parts = module.split(".")
    py = src_root.joinpath(*parts).with_suffix(".py")
    if py.is_file():
        return py
    pkg = src_root.joinpath(*parts, "__init__.py")
    if pkg.is_file():
        return pkg
    return None


def module_name_for(src_root: Path, path: Path) -> str:
    rel = path.relative_to(src_root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = Path(parts[-1]).stem
    return ".".join(parts)


def package_init_paths(src_root: Path, module: str) -> list[Path]:
    parts = module.split(".")[:-1]
    result: list[Path] = []
    for index in range(1, len(parts) + 1):
        path = src_root.joinpath(*parts[:index], "__init__.py")
        if path.is_file():
            result.append(path)
    return result


def classify_import(name: str, src_root: Path) -> str:
    if name == F2_PACKAGE or name.startswith(F2_PACKAGE + "."):
        return "LOCAL_F2" if resolve_local_module(src_root, name) else "UNRESOLVED_LOCAL_F2"
    top = name.split(".", 1)[0]
    if top in getattr(sys, "stdlib_module_names", frozenset()):
        return "STDLIB"
    spec = importlib.util.find_spec(top)
    if spec is None:
        return "UNRESOLVED_EXTERNAL"
    return "EXTERNAL_DISTRIBUTION_OR_SITE_PATH"


def inspect_file(path: Path, src_root: Path) -> dict[str, Any]:
    data = path.read_bytes()
    text = data.decode("utf-8")
    tree = ast.parse(text, filename=str(path))
    imports = ImportVisitor()
    imports.visit(tree)
    surfaces = SurfaceVisitor()
    surfaces.visit(tree)
    import_rows = [
        {"module": name, "class": classify_import(name, src_root)}
        for name in sorted(imports.modules)
    ]
    return {
        "path": path.relative_to(src_root.parent).as_posix(),
        "module": module_name_for(src_root, path),
        "sha256": sha256_bytes(data),
        "imports": import_rows,
        "dynamic_surfaces": sorted(surfaces.surfaces),
    }


def recursive_local_closure(repo_root: Path, root_rel: str) -> dict[str, Any]:
    src_root = repo_root / "src"
    root = repo_root / root_rel
    if not root.is_file():
        raise SystemExit(f"root source missing: {root_rel}")
    queue: list[Path] = [root]
    seen: set[Path] = set()
    records: list[dict[str, Any]] = []
    unresolved_local: set[str] = set()
    external: set[str] = set()
    stdlib: set[str] = set()
    dynamic_surfaces: set[str] = set()

    while queue:
        path = queue.pop(0).resolve()
        if path in seen:
            continue
        seen.add(path)
        record = inspect_file(path, src_root)
        records.append(record)
        dynamic_surfaces.update(record["dynamic_surfaces"])
        for row in record["imports"]:
            name = row["module"]
            kind = row["class"]
            if kind == "LOCAL_F2":
                dep = resolve_local_module(src_root, name)
                if dep is not None:
                    queue.append(dep)
                    queue.extend(package_init_paths(src_root, name))
            elif kind == "UNRESOLVED_LOCAL_F2":
                unresolved_local.add(name)
            elif kind == "STDLIB":
                stdlib.add(name)
            else:
                external.add(name)

    records.sort(key=lambda row: row["path"])
    local_digest = sha256_text(canonical_json([(r["path"], r["sha256"]) for r in records]))
    return {
        "root_source": root_rel,
        "files": records,
        "local_closure_sha256": local_digest,
        "unresolved_local_imports": sorted(unresolved_local),
        "stdlib_imports": sorted(stdlib),
        "external_or_unresolved_imports": sorted(external),
        "dynamic_surfaces": sorted(dynamic_surfaces),
    }


def interpreter_manifest() -> dict[str, Any]:
    env = {}
    for key in ENV_KEYS:
        value = os.environ.get(key)
        env[key] = {
            "present": value is not None,
            "sha256": None if value is None else sha256_text(value),
        }
    path_rows = [
        {"index": i, "sha256": sha256_text(value), "empty": value == ""}
        for i, value in enumerate(sys.path)
    ]
    return {
        "implementation": sys.implementation.name,
        "version": sys.version,
        "cache_tag": sys.implementation.cache_tag,
        "executable_sha256": sha256_text(str(Path(sys.executable).resolve())),
        "soabi": sysconfig.get_config_var("SOABI"),
        "platform": sys.platform,
        "sys_path": path_rows,
        "environment": env,
    }


def runtime_observe(repo_root: Path, module: str) -> dict[str, Any]:
    src = (repo_root / "src").resolve()
    code = r'''
import json, pathlib, sys
mod = sys.argv[1]
src = pathlib.Path(sys.argv[2]).resolve()
__import__(mod)
rows=[]
for name, obj in sorted(sys.modules.items()):
    path=getattr(obj,"__file__",None)
    if not path:
        continue
    try:
        resolved=pathlib.Path(path).resolve()
        rel=resolved.relative_to(src)
    except Exception:
        continue
    rows.append({"module":name,"path":rel.as_posix()})
print(json.dumps(rows, sort_keys=True, separators=(",",":")))
'''
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src)
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code, module, str(src)],
        cwd=repo_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        code2 = "import sys; sys.path.insert(0, sys.argv[2]); " + code
        proc = subprocess.run(
            [sys.executable, "-P", "-c", code2, module, str(src)],
            cwd=repo_root,
            env={k: v for k, v in env.items() if k != "PYTHONPATH"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    if proc.returncode != 0:
        return {
            "status": "RUNTIME_OBSERVATION_FAILED",
            "returncode": proc.returncode,
            "stderr_sha256": sha256_text(proc.stderr),
        }
    rows = json.loads(proc.stdout.strip() or "[]")
    return {"status": "OBSERVED_RESEARCH_ONLY", "loaded_local_modules": rows}


def build_manifest(repo_root: Path, root_rel: str, *, observe_runtime: bool) -> dict[str, Any]:
    closure = recursive_local_closure(repo_root, root_rel)
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "classification": "TRIGGER6_E3_RESEARCH_ONLY_NOT_PRODUCT_OR_RUNTIME_CREDIT",
        "closure": closure,
        "interpreter": interpreter_manifest(),
        "runtime_observation": None,
        "credit": {
            "architecture_credit": 0,
            "runtime_credit": 0,
            "whole_system_credit": 0,
        },
    }
    if observe_runtime:
        module = module_name_for(repo_root / "src", repo_root / root_rel)
        manifest["runtime_observation"] = runtime_observe(repo_root, module)

    local_static = {row["module"] for row in closure["files"]}
    runtime = manifest["runtime_observation"]
    runtime_extra: list[str] = []
    if isinstance(runtime, dict) and runtime.get("status") == "OBSERVED_RESEARCH_ONLY":
        runtime_local = {row["module"] for row in runtime["loaded_local_modules"]}
        runtime_extra = sorted(runtime_local - local_static)
    manifest["runtime_extra_local_modules"] = runtime_extra

    blockers = []
    if closure["unresolved_local_imports"]:
        blockers.append("UNRESOLVED_LOCAL_IMPORT")
    if closure["external_or_unresolved_imports"]:
        blockers.append("EXTERNAL_OR_UNRESOLVED_IMPORT")
    if closure["dynamic_surfaces"]:
        blockers.append("DYNAMIC_IMPORT_OR_RUNTIME_SURFACE")
    if runtime_extra:
        blockers.append("RUNTIME_STATIC_CLOSURE_MISMATCH")
    if observe_runtime and isinstance(runtime, dict) and runtime.get("status") != "OBSERVED_RESEARCH_ONLY":
        blockers.append("RUNTIME_OBSERVATION_FAILED")

    manifest["blockers"] = blockers
    manifest["completeness_class"] = (
        "CLOSED_BY_CONSTRUCTION_CANDIDATE_RESEARCH_ONLY"
        if not blockers
        else "HYBRID_BOUNDED_UNPROVEN"
    )
    manifest["manifest_sha256"] = sha256_text(canonical_json(manifest))
    return manifest


def _write_fixture(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def self_test() -> dict[str, Any]:
    outcomes: dict[str, bool] = {}
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        _write_fixture(repo, "src/frankenstein2/__init__.py", "")
        _write_fixture(repo, "src/frankenstein2/dep.py", "VALUE=1\n")
        base = "from frankenstein2.dep import VALUE\n"

        cases = {
            "baseline": base,
            "dynamic_import": base + "import importlib\ndef f(): return importlib.import_module('x')\n",
            "sys_path": base + "import sys\nsys.path.append('/tmp/x')\n",
            "entry_point": base + "from importlib import metadata\ndef f(): return metadata.entry_points()\n",
            "environment": base + "import os\nFLAG=os.getenv('F2_FLAG')\n",
            "native": base + "import ctypes\ndef f(): return ctypes.CDLL('libx.so')\n",
        }
        expected = {
            "dynamic_import": "DYNAMIC_IMPORT_CALL",
            "sys_path": "SYS_PATH_MUTATION",
            "entry_point": "ENTRY_POINT_DISCOVERY",
            "environment": "ENVIRONMENT_DEPENDENCY",
            "native": "NATIVE_LIBRARY_LOAD",
        }
        for name, text in cases.items():
            _write_fixture(repo, "src/frankenstein2/root.py", text)
            result = recursive_local_closure(repo, "src/frankenstein2/root.py")
            outcomes[f"{name}_closure_has_dep"] = any(
                row["module"] == "frankenstein2.dep" for row in result["files"]
            )
            if name == "baseline":
                outcomes["baseline_no_dynamic_surface"] = result["dynamic_surfaces"] == []
            else:
                outcomes[f"{name}_surface_detected"] = expected[name] in result["dynamic_surfaces"]

        _write_fixture(repo, "src/frankenstein2/root.py", "from frankenstein2.missing import X\n")
        result = recursive_local_closure(repo, "src/frankenstein2/root.py")
        outcomes["missing_local_import_fails_closed"] = (
            "frankenstein2.missing" in result["unresolved_local_imports"]
        )

    passed = all(outcomes.values())
    return {
        "schema": "FRANKENSTEIN2_TRIGGER6_RECURSIVE_MANIFEST_SELFTEST/v1",
        "passed": passed,
        "checks": outcomes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--root-source", default="src/frankenstein2/gwt_causal_path.py")
    parser.add_argument("--runtime-observe", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["passed"] else 1

    repo_root = Path(args.repo_root).resolve()
    manifest = build_manifest(repo_root, args.root_source, observe_runtime=args.runtime_observe)
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
