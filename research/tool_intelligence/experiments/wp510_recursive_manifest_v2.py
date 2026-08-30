#!/usr/bin/env python3
"""Trigger-6 successor instrument for WP510 recursive manifest identity.

v2 preserves the v1 dependency analysis but repairs interpreter identity:
- executable_path_sha256 hashes only the resolved path string;
- executable_file_sha256 hashes the actual interpreter executable bytes;
- unreadable executable bytes fail closed.

Research-only. No architecture/runtime/whole-system credit is granted.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any

BASE = Path(__file__).with_name("wp510_recursive_manifest.py")
_spec = importlib.util.spec_from_file_location("wp510_recursive_manifest_v1", BASE)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load base instrument: {BASE}")
_v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_v1)

_v1_interpreter_manifest = _v1.interpreter_manifest
_v1_build_manifest = _v1.build_manifest


def interpreter_manifest_v2() -> dict[str, Any]:
    out = _v1_interpreter_manifest()
    resolved = Path(sys.executable).resolve()
    # v1 called this executable_sha256, but it was the digest of the path text.
    out.pop("executable_sha256", None)
    out["executable_path"] = str(resolved)
    out["executable_path_sha256"] = _v1.sha256_text(str(resolved))
    try:
        payload = resolved.read_bytes()
    except OSError as exc:
        out["executable_file_read_status"] = "UNREADABLE_FAIL_CLOSED"
        out["executable_file_sha256"] = None
        out["executable_file_size"] = None
        out["executable_file_error_type"] = type(exc).__name__
    else:
        out["executable_file_read_status"] = "OK"
        out["executable_file_sha256"] = _v1.sha256_bytes(payload)
        out["executable_file_size"] = len(payload)
        out["executable_file_error_type"] = None
    return out


def build_manifest_v2(repo_root: Path, root_rel: str, *, observe_runtime: bool) -> dict[str, Any]:
    # Monkeypatch only for the duration of the inherited builder invocation.
    _v1.interpreter_manifest = interpreter_manifest_v2
    try:
        out = _v1_build_manifest(repo_root, root_rel, observe_runtime=observe_runtime)
    finally:
        _v1.interpreter_manifest = _v1_interpreter_manifest

    out["schema"] = "FRANKENSTEIN2_TRIGGER6_RECURSIVE_PYTHON_MANIFEST/v2"
    out["instrument_successor"] = {
        "supersedes_schema": "FRANKENSTEIN2_TRIGGER6_RECURSIVE_PYTHON_MANIFEST/v1",
        "repair": "INTERPRETER_EXECUTABLE_FILE_BYTES_IDENTITY",
        "v1_defect": "v1 executable_sha256 hashed resolved executable path text, not executable bytes",
    }
    if out["interpreter"].get("executable_file_read_status") != "OK":
        blockers = list(out.get("blockers", []))
        if "INTERPRETER_EXECUTABLE_UNREADABLE" not in blockers:
            blockers.append("INTERPRETER_EXECUTABLE_UNREADABLE")
        out["blockers"] = sorted(blockers)
        out["completeness_class"] = "HYBRID_BOUNDED_UNPROVEN"

    # Recompute the manifest identity after all successor fields and repaired identity exist.
    out.pop("manifest_sha256", None)
    out["manifest_sha256"] = _v1.sha256_text(_v1.canonical_json(out))
    return out


# Patch inherited CLI so --self-test remains the same adversarial closure test while
# normal manifest construction uses the repaired v2 identity.
_v1.build_manifest = build_manifest_v2

if __name__ == "__main__":
    raise SystemExit(_v1.main())
