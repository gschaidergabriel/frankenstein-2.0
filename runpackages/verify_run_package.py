#!/usr/bin/env python3
"""Fail-closed verifier for Frankenstein 2.0 immutable run packages."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any
import hashlib
import json
import re
import sys

SCHEMA = "FRANKENSTEIN2_IMMUTABLE_RUN_PACKAGE/v1"
MANIFEST_NAME = "MANIFEST.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
WP_ID = re.compile(r"^F2-WP-[0-9]{3,4}$")
OUTCOMES = {"PASS", "FAIL", "BLOCKED", "INFRA_FAILURE", "NOT_RUN"}


class RunPackageError(RuntimeError):
    pass


def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _manifest_digest(manifest: dict[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("package_digest", None)
    return hashlib.sha256(_canon(unsigned)).hexdigest()


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_relpath(text: str) -> PurePosixPath:
    if not isinstance(text, str) or not text or "\\" in text:
        raise RunPackageError(f"UNSAFE_PAYLOAD_PATH:{text!r}")
    p = PurePosixPath(text)
    if p.is_absolute() or any(part in {"", ".", ".."} for part in p.parts):
        raise RunPackageError(f"UNSAFE_PAYLOAD_PATH:{text!r}")
    if p.name == MANIFEST_NAME:
        raise RunPackageError("MANIFEST_MUST_NOT_SELF_HASH")
    return p


def _require_string(manifest: dict[str, Any], key: str, *, max_len: int | None = None) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or not value:
        raise RunPackageError(f"INVALID_{key.upper()}")
    if max_len is not None and len(value) > max_len:
        raise RunPackageError(f"INVALID_{key.upper()}_LENGTH")
    return value


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != SCHEMA:
        raise RunPackageError("SCHEMA_MISMATCH")
    _require_string(manifest, "package_id", max_len=200)
    workpackage_id = _require_string(manifest, "workpackage_id")
    if not WP_ID.fullmatch(workpackage_id):
        raise RunPackageError("INVALID_WORKPACKAGE_ID")
    generation = manifest.get("generation")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
        raise RunPackageError("INVALID_GENERATION")

    source = manifest.get("source_identity")
    if not isinstance(source, dict):
        raise RunPackageError("INVALID_SOURCE_IDENTITY")
    for key in ("repository", "ref"):
        if not isinstance(source.get(key), str) or not source[key]:
            raise RunPackageError(f"INVALID_SOURCE_IDENTITY_{key.upper()}")
    if not isinstance(source.get("commit_sha"), str) or not SHA40.fullmatch(source["commit_sha"]):
        raise RunPackageError("INVALID_SOURCE_COMMIT_SHA")
    if not isinstance(source.get("tree_sha"), str) or not SHA40.fullmatch(source["tree_sha"]):
        raise RunPackageError("INVALID_SOURCE_TREE_SHA")

    _require_string(manifest, "claim_scope", max_len=240)
    _require_string(manifest, "runtime_credit_ceiling", max_len=240)

    command = manifest.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x for x in command):
        raise RunPackageError("INVALID_COMMAND_VECTOR")

    outcome = manifest.get("outcome")
    if outcome not in OUTCOMES:
        raise RunPackageError("INVALID_OUTCOME")

    provider_calls = manifest.get("provider_calls")
    if not isinstance(provider_calls, int) or isinstance(provider_calls, bool) or provider_calls < 0:
        raise RunPackageError("INVALID_PROVIDER_CALL_COUNT")

    try:
        spend = Decimal(str(manifest.get("paid_spend_usd")))
    except (InvalidOperation, ValueError):
        raise RunPackageError("INVALID_PAID_SPEND") from None
    if not spend.is_finite() or spend < 0:
        raise RunPackageError("INVALID_PAID_SPEND")

    if not isinstance(manifest.get("external_effects_executed"), bool):
        raise RunPackageError("INVALID_EXTERNAL_EFFECT_FLAG")

    started_at = manifest.get("started_at")
    completed_at = manifest.get("completed_at")
    exit_code = manifest.get("exit_code")
    if started_at is not None and not isinstance(started_at, str):
        raise RunPackageError("INVALID_STARTED_AT")
    if completed_at is not None and not isinstance(completed_at, str):
        raise RunPackageError("INVALID_COMPLETED_AT")
    if exit_code is not None and (not isinstance(exit_code, int) or isinstance(exit_code, bool)):
        raise RunPackageError("INVALID_EXIT_CODE")
    if outcome == "PASS" and (started_at is None or completed_at is None or exit_code != 0):
        raise RunPackageError("PASS_REQUIRES_OBSERVED_ZERO_EXIT_EXECUTION")
    if outcome == "NOT_RUN" and (started_at is not None or completed_at is not None or exit_code is not None):
        raise RunPackageError("NOT_RUN_MUST_NOT_CONTAIN_EXECUTION_RESULT")

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RunPackageError("EMPTY_OR_INVALID_PAYLOAD_INDEX")
    for rel, digest in files.items():
        _safe_relpath(rel)
        if not isinstance(digest, str) or not SHA64.fullmatch(digest):
            raise RunPackageError(f"INVALID_PAYLOAD_DIGEST:{rel}")

    digest = manifest.get("package_digest")
    if not isinstance(digest, str) or not SHA64.fullmatch(digest):
        raise RunPackageError("INVALID_PACKAGE_DIGEST")


def verify_package(package_dir: Path) -> dict[str, Any]:
    package_dir = Path(package_dir)
    if package_dir.is_symlink():
        raise RunPackageError("PACKAGE_DIRECTORY_SYMLINK_FORBIDDEN")
    manifest_path = package_dir / MANIFEST_NAME
    if not package_dir.is_dir() or not manifest_path.is_file():
        raise RunPackageError("PACKAGE_OR_MANIFEST_MISSING")
    if manifest_path.is_symlink():
        raise RunPackageError("MANIFEST_SYMLINK_FORBIDDEN")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise RunPackageError("MANIFEST_NOT_OBJECT")
    _validate_manifest(manifest)

    indexed: dict[str, str] = manifest["files"]
    observed: dict[str, str] = {}
    for path in sorted(package_dir.rglob("*")):
        if path == manifest_path:
            continue
        if path.is_symlink():
            raise RunPackageError(f"PAYLOAD_SYMLINK_FORBIDDEN:{path.relative_to(package_dir).as_posix()}")
        if path.is_dir():
            continue
        rel = path.relative_to(package_dir).as_posix()
        _safe_relpath(rel)
        observed[rel] = _file_digest(path)

    if set(observed) != set(indexed):
        missing = sorted(set(indexed) - set(observed))
        extra = sorted(set(observed) - set(indexed))
        raise RunPackageError(f"PAYLOAD_SET_MISMATCH:missing={missing}:extra={extra}")
    for rel, digest in indexed.items():
        if observed[rel] != digest:
            raise RunPackageError(f"PAYLOAD_DIGEST_MISMATCH:{rel}")

    expected_package_digest = _manifest_digest(manifest)
    if manifest["package_digest"] != expected_package_digest:
        raise RunPackageError("PACKAGE_DIGEST_MISMATCH")

    return {
        "schema": SCHEMA,
        "status": "VERIFIED",
        "package_id": manifest["package_id"],
        "workpackage_id": manifest["workpackage_id"],
        "generation": manifest["generation"],
        "claim_scope": manifest["claim_scope"],
        "runtime_credit_ceiling": manifest["runtime_credit_ceiling"],
        "outcome": manifest["outcome"],
        "source_identity": manifest["source_identity"],
        "provider_calls": manifest["provider_calls"],
        "paid_spend_usd": manifest["paid_spend_usd"],
        "external_effects_executed": manifest["external_effects_executed"],
        "payload_count": len(indexed),
        "package_digest": manifest["package_digest"],
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: verify_run_package.py <package-dir>", file=sys.stderr)
        return 2
    try:
        result = verify_package(Path(argv[1]))
    except (RunPackageError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
