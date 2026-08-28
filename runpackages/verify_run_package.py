#!/usr/bin/env python3
"""Fail-closed verifier for canonical Frankenstein 2.0 immutable run packages."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import hashlib
import json
import re
import sys

MANIFEST_SCHEMA = "FRANKENSTEIN2_RUN_PACKAGE_MANIFEST/v1"
ARTIFACT_SCHEMA = "FRANKENSTEIN2_RUN_ARTIFACT_INDEX/v1"
CLOSED_SCHEMA = "FRANKENSTEIN2_RUN_CLOSED_RECEIPT/v1"

MANIFEST_NAME = "manifest.json"
ARTIFACTS_NAME = "ARTIFACTS.json"
SUMS_NAME = "SHA256SUMS"
CLOSED_NAME = "CLOSED.json"
CLOSURE_FILES = {ARTIFACTS_NAME, SUMS_NAME, CLOSED_NAME}

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
WP_ID = re.compile(r"^F2-WP-[0-9]+$")
EVIDENCE_CLASSES = {
    "SOURCE_ONLY",
    "UNIT_RUNTIME",
    "COMPONENT_RUNTIME",
    "INTEGRATION_RUNTIME",
    "WHOLE_SYSTEM_RUNTIME",
    "NEGATIVE_RESULT",
    "BLOCKED",
}
CLOSURE_STATUSES = {
    "CLOSED_PASS_AT_SCOPE",
    "CLOSED_FAIL",
    "CLOSED_BLOCKED",
    "CLOSED_SOURCE_ONLY",
}


class RunPackageError(RuntimeError):
    pass


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_relpath(text: str) -> PurePosixPath:
    if not isinstance(text, str) or not text or "\\" in text:
        raise RunPackageError(f"UNSAFE_PACKAGE_PATH:{text!r}")
    p = PurePosixPath(text)
    if p.is_absolute() or any(part in {"", ".", ".."} for part in p.parts):
        raise RunPackageError(f"UNSAFE_PACKAGE_PATH:{text!r}")
    return p


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink():
        raise RunPackageError(f"{label}_SYMLINK_FORBIDDEN")
    if not path.is_file():
        raise RunPackageError(f"{label}_MISSING")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RunPackageError(f"{label}_NOT_OBJECT")
    return value


def _require_string(obj: dict[str, Any], key: str, label: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise RunPackageError(f"INVALID_{label}_{key.upper()}")
    return value


def _require_nonnegative_int(obj: dict[str, Any], key: str, label: str) -> int:
    value = obj.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RunPackageError(f"INVALID_{label}_{key.upper()}")
    return value


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise RunPackageError("MANIFEST_SCHEMA_MISMATCH")
    _require_string(manifest, "run_id", "MANIFEST")
    _require_string(manifest, "series", "MANIFEST")
    workpackage_id = _require_string(manifest, "workpackage_id", "MANIFEST")
    if not WP_ID.fullmatch(workpackage_id):
        raise RunPackageError("INVALID_MANIFEST_WORKPACKAGE_ID")
    generation = _require_nonnegative_int(manifest, "generation", "MANIFEST")
    if generation < 1:
        raise RunPackageError("INVALID_MANIFEST_GENERATION")
    _require_string(manifest, "claim_id", "MANIFEST")
    _require_string(manifest, "worker_id", "MANIFEST")
    source_before = _require_string(manifest, "source_commit_before", "MANIFEST")
    if not SHA40.fullmatch(source_before):
        raise RunPackageError("INVALID_MANIFEST_SOURCE_COMMIT_BEFORE")
    source_after = manifest.get("source_commit_after")
    if source_after is not None and (not isinstance(source_after, str) or not SHA40.fullmatch(source_after)):
        raise RunPackageError("INVALID_MANIFEST_SOURCE_COMMIT_AFTER")
    _require_string(manifest, "started_at_utc", "MANIFEST")

    evidence = manifest.get("evidence_scope")
    if not isinstance(evidence, dict):
        raise RunPackageError("INVALID_MANIFEST_EVIDENCE_SCOPE")
    classification = evidence.get("classification")
    if classification not in EVIDENCE_CLASSES:
        raise RunPackageError("INVALID_MANIFEST_EVIDENCE_CLASSIFICATION")
    runtime_observed = evidence.get("runtime_execution_observed")
    if not isinstance(runtime_observed, bool):
        raise RunPackageError("INVALID_MANIFEST_RUNTIME_EXECUTION_OBSERVED")
    runtime_credit = _require_nonnegative_int(evidence, "runtime_credit", "MANIFEST_EVIDENCE")
    if not runtime_observed and runtime_credit != 0:
        raise RunPackageError("UNOBSERVED_RUNTIME_CANNOT_HAVE_CREDIT")
    if classification == "SOURCE_ONLY" and (runtime_observed or runtime_credit != 0):
        raise RunPackageError("SOURCE_ONLY_CANNOT_HAVE_RUNTIME_CREDIT")

    participants = manifest.get("participants")
    if not isinstance(participants, list) or not participants:
        raise RunPackageError("INVALID_MANIFEST_PARTICIPANTS")
    seen_ids: set[str] = set()
    for idx, participant in enumerate(participants):
        if not isinstance(participant, dict):
            raise RunPackageError(f"INVALID_PARTICIPANT:{idx}")
        pid = _require_string(participant, "participant_id", f"PARTICIPANT_{idx}")
        if pid in seen_ids:
            raise RunPackageError(f"DUPLICATE_PARTICIPANT_ID:{pid}")
        seen_ids.add(pid)
        _require_string(participant, "component", f"PARTICIPANT_{idx}")
        observability = participant.get("observability")
        if observability not in {"OBSERVABLE", "NOT_OBSERVABLE"}:
            raise RunPackageError(f"INVALID_PARTICIPANT_OBSERVABILITY:{pid}")
        if observability == "NOT_OBSERVABLE":
            _require_string(participant, "not_observable_reason", f"PARTICIPANT_{idx}")

    if manifest.get("artifacts_index") != ARTIFACTS_NAME:
        raise RunPackageError("MANIFEST_ARTIFACT_INDEX_BINDING_MISMATCH")
    if manifest.get("closure_receipt") != CLOSED_NAME:
        raise RunPackageError("MANIFEST_CLOSURE_BINDING_MISMATCH")


def _validate_artifacts(index: dict[str, Any], run_id: str) -> list[dict[str, Any]]:
    if index.get("schema") != ARTIFACT_SCHEMA:
        raise RunPackageError("ARTIFACT_INDEX_SCHEMA_MISMATCH")
    if index.get("run_id") != run_id:
        raise RunPackageError("ARTIFACT_INDEX_RUN_ID_MISMATCH")
    _require_string(index, "generated_at_utc", "ARTIFACT_INDEX")
    artifacts = index.get("artifacts")
    if not isinstance(artifacts, list):
        raise RunPackageError("INVALID_ARTIFACT_LIST")

    seen: set[str] = set()
    for idx, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise RunPackageError(f"INVALID_ARTIFACT:{idx}")
        rel = _require_string(artifact, "path", f"ARTIFACT_{idx}")
        _safe_relpath(rel)
        if rel in CLOSURE_FILES:
            raise RunPackageError(f"ARTIFACT_INDEX_SELF_OR_CLOSURE_FILE_FORBIDDEN:{rel}")
        if rel in seen:
            raise RunPackageError(f"DUPLICATE_ARTIFACT_PATH:{rel}")
        seen.add(rel)
        digest = _require_string(artifact, "sha256", f"ARTIFACT_{idx}")
        if not SHA64.fullmatch(digest):
            raise RunPackageError(f"INVALID_ARTIFACT_DIGEST:{rel}")
        _require_nonnegative_int(artifact, "size_bytes", f"ARTIFACT_{idx}")
        _require_string(artifact, "role", f"ARTIFACT_{idx}")
        provenance = artifact.get("provenance")
        if not isinstance(provenance, dict):
            raise RunPackageError(f"INVALID_ARTIFACT_PROVENANCE:{rel}")
        _require_string(provenance, "producer", f"ARTIFACT_{idx}_PROVENANCE")
        _require_string(provenance, "source_kind", f"ARTIFACT_{idx}_PROVENANCE")
    return artifacts


def _parse_sha256sums(path: Path) -> dict[str, str]:
    if path.is_symlink():
        raise RunPackageError("SHA256SUMS_SYMLINK_FORBIDDEN")
    if not path.is_file():
        raise RunPackageError("SHA256SUMS_MISSING")
    parsed: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw:
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", raw)
        if not match:
            raise RunPackageError(f"INVALID_SHA256SUMS_LINE:{line_number}")
        digest, rel = match.groups()
        _safe_relpath(rel)
        if rel in {SUMS_NAME, CLOSED_NAME}:
            raise RunPackageError(f"SHA256SUMS_SELF_OR_CLOSED_FORBIDDEN:{rel}")
        if rel in parsed:
            raise RunPackageError(f"DUPLICATE_SHA256SUMS_PATH:{rel}")
        parsed[rel] = digest
    if not parsed:
        raise RunPackageError("EMPTY_SHA256SUMS")
    return parsed


def _validate_closed(closed: dict[str, Any], manifest: dict[str, Any], digests: dict[str, str]) -> None:
    if closed.get("schema") != CLOSED_SCHEMA:
        raise RunPackageError("CLOSED_SCHEMA_MISMATCH")
    if closed.get("run_id") != manifest["run_id"]:
        raise RunPackageError("CLOSED_RUN_ID_MISMATCH")
    _require_string(closed, "closed_at_utc", "CLOSED")
    expected = {
        "manifest_sha256": digests[MANIFEST_NAME],
        "artifact_index_sha256": digests[ARTIFACTS_NAME],
        "sha256sums_sha256": digests[SUMS_NAME],
    }
    for key, value in expected.items():
        if closed.get(key) != value:
            raise RunPackageError(f"CLOSED_DIGEST_MISMATCH:{key}")

    status = closed.get("closure_status")
    if status not in CLOSURE_STATUSES:
        raise RunPackageError("INVALID_CLOSURE_STATUS")
    classification = closed.get("evidence_classification")
    if classification not in EVIDENCE_CLASSES:
        raise RunPackageError("INVALID_CLOSED_EVIDENCE_CLASSIFICATION")
    if classification != manifest["evidence_scope"]["classification"]:
        raise RunPackageError("CLOSED_MANIFEST_CLASSIFICATION_MISMATCH")
    runtime_observed = closed.get("runtime_execution_observed")
    if not isinstance(runtime_observed, bool):
        raise RunPackageError("INVALID_CLOSED_RUNTIME_EXECUTION_OBSERVED")
    if runtime_observed != manifest["evidence_scope"]["runtime_execution_observed"]:
        raise RunPackageError("CLOSED_MANIFEST_RUNTIME_OBSERVED_MISMATCH")
    runtime_credit = _require_nonnegative_int(closed, "runtime_credit", "CLOSED")
    if runtime_credit != manifest["evidence_scope"]["runtime_credit"]:
        raise RunPackageError("CLOSED_MANIFEST_RUNTIME_CREDIT_MISMATCH")
    _require_string(closed, "acceptance_scope", "CLOSED")
    completion_deficit = closed.get("completion_deficit")
    if not isinstance(completion_deficit, str):
        raise RunPackageError("INVALID_CLOSED_COMPLETION_DEFICIT")

    if not runtime_observed and runtime_credit != 0:
        raise RunPackageError("CLOSED_UNOBSERVED_RUNTIME_CANNOT_HAVE_CREDIT")
    if classification == "SOURCE_ONLY":
        if runtime_observed or runtime_credit != 0 or status != "CLOSED_SOURCE_ONLY":
            raise RunPackageError("INVALID_SOURCE_ONLY_CLOSURE")
    if status == "CLOSED_PASS_AT_SCOPE" and not runtime_observed:
        raise RunPackageError("PASS_AT_SCOPE_REQUIRES_RUNTIME_EXECUTION")


def verify_package(package_dir: Path) -> dict[str, Any]:
    package_dir = Path(package_dir)
    if package_dir.is_symlink():
        raise RunPackageError("PACKAGE_DIRECTORY_SYMLINK_FORBIDDEN")
    if not package_dir.is_dir():
        raise RunPackageError("PACKAGE_DIRECTORY_MISSING")

    manifest_path = package_dir / MANIFEST_NAME
    artifacts_path = package_dir / ARTIFACTS_NAME
    sums_path = package_dir / SUMS_NAME
    closed_path = package_dir / CLOSED_NAME

    manifest = _load_json_object(manifest_path, "MANIFEST")
    _validate_manifest(manifest)
    artifact_index = _load_json_object(artifacts_path, "ARTIFACT_INDEX")
    artifacts = _validate_artifacts(artifact_index, manifest["run_id"])
    closed = _load_json_object(closed_path, "CLOSED")

    observed_payload: dict[str, Path] = {}
    for path in sorted(package_dir.rglob("*")):
        if path.is_symlink():
            raise RunPackageError(f"PACKAGE_SYMLINK_FORBIDDEN:{path.relative_to(package_dir).as_posix()}")
        if path.is_dir():
            continue
        rel = path.relative_to(package_dir).as_posix()
        _safe_relpath(rel)
        observed_payload[rel] = path

    artifact_paths = {artifact["path"] for artifact in artifacts}
    expected_artifact_paths = set(observed_payload) - CLOSURE_FILES
    if artifact_paths != expected_artifact_paths:
        missing = sorted(expected_artifact_paths - artifact_paths)
        extra = sorted(artifact_paths - expected_artifact_paths)
        raise RunPackageError(f"ARTIFACT_SET_MISMATCH:missing={missing}:extra={extra}")
    if MANIFEST_NAME not in artifact_paths:
        raise RunPackageError("MANIFEST_MISSING_FROM_ARTIFACT_INDEX")

    artifact_by_path = {artifact["path"]: artifact for artifact in artifacts}
    for rel in sorted(artifact_paths):
        path = observed_payload[rel]
        expected_digest = artifact_by_path[rel]["sha256"]
        if _file_digest(path) != expected_digest:
            raise RunPackageError(f"ARTIFACT_DIGEST_MISMATCH:{rel}")
        if path.stat().st_size != artifact_by_path[rel]["size_bytes"]:
            raise RunPackageError(f"ARTIFACT_SIZE_MISMATCH:{rel}")

    sums = _parse_sha256sums(sums_path)
    expected_sum_paths = set(observed_payload) - {SUMS_NAME, CLOSED_NAME}
    if set(sums) != expected_sum_paths:
        missing = sorted(expected_sum_paths - set(sums))
        extra = sorted(set(sums) - expected_sum_paths)
        raise RunPackageError(f"SHA256SUMS_SET_MISMATCH:missing={missing}:extra={extra}")
    for rel, expected_digest in sums.items():
        if _file_digest(observed_payload[rel]) != expected_digest:
            raise RunPackageError(f"SHA256SUMS_DIGEST_MISMATCH:{rel}")

    digests = {
        MANIFEST_NAME: _file_digest(manifest_path),
        ARTIFACTS_NAME: _file_digest(artifacts_path),
        SUMS_NAME: _file_digest(sums_path),
    }
    _validate_closed(closed, manifest, digests)

    return {
        "schema": "FRANKENSTEIN2_RUN_PACKAGE_VERIFICATION/v1",
        "status": "VERIFIED_CLOSED",
        "run_id": manifest["run_id"],
        "workpackage_id": manifest["workpackage_id"],
        "generation": manifest["generation"],
        "claim_id": manifest["claim_id"],
        "evidence_classification": closed["evidence_classification"],
        "runtime_execution_observed": closed["runtime_execution_observed"],
        "runtime_credit": closed["runtime_credit"],
        "acceptance_scope": closed["acceptance_scope"],
        "artifact_count": len(artifacts),
        "closure_status": closed["closure_status"],
        "closed_digest": _file_digest(closed_path),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: verify_run_package.py <run-package-dir>", file=sys.stderr)
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
