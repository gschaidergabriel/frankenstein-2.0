"""Static completeness gate for the portable Frankenstein 2.0 release contract.

F2-WP-1111 generation 1.

This composes the accepted WP1110 static pre-handoff result with explicit delivery
metadata required by the portable-host distribution contract. It is static evidence
only: no installer, host, device, provider, VPS, effect, or completion credit is minted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any

from .pre_handoff_release import READY_STATUS, evaluate_pre_handoff_release

SCHEMA = "FRANKENSTEIN2_RELEASE_STATIC_COMPLETENESS/v1"
METADATA_SCHEMA = "FRANKENSTEIN2_RELEASE_DELIVERY_CONTRACT/v1"
METADATA_PATH = "AI_START_HERE_DO_NOT_SCAN_REPO/02_RELEASE_CONTRACT.json"
STATE_MIGRATION_VERSION = "FRANKENSTEIN2_STATE_MIGRATION_PLAN/v1"
EVIDENCE_SCOPE = "PORTABLE_RELEASE_STATIC_CONTRACT_COMPLETENESS_ONLY_NO_RUNTIME_EFFECT_OR_COMPLETION_CREDIT"
BLOCKED = "BLOCKED"
STATIC_COMPLETE = "STATIC_COMPLETE_FOR_REAL_HOST_ACCEPTANCE"
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+$")
_REQUIRED_HOST_KEYS = ("claude_code", "codex_cli", "other_agent")


class PortableReleaseStaticCompletenessError(ValueError):
    pass


def _safe_file(root: Path, raw: Any, label: str, violations: list[str]) -> str | None:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        violations.append(f"{label}:invalid_ref")
        return None
    candidate = (root / raw).resolve()
    try:
        rel = candidate.relative_to(root)
    except ValueError:
        violations.append(f"{label}:escapes_release_root")
        return None
    if candidate.is_symlink() or not candidate.is_file():
        violations.append(f"{label}:missing_or_nonregular")
        return None
    return rel.as_posix()


def _load_json_file(root: Path, rel: str, label: str, violations: list[str]) -> dict[str, Any] | None:
    path = root / rel
    if path.is_symlink() or not path.is_file():
        violations.append(f"{label}:missing_or_nonregular")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        violations.append(f"{label}:invalid_utf8_json")
        return None
    if not isinstance(value, dict):
        violations.append(f"{label}:root_not_object")
        return None
    return value


@dataclass(frozen=True, slots=True)
class PortableReleaseStaticCompletenessReceipt:
    release_id: str
    source_commit: str
    release_manifest_sha256: str
    prehandoff_status: str
    metadata_path: str
    baseline_python_minimum: str | None
    state_migration_version: str | None
    verified_refs: tuple[str, ...]
    violations: tuple[str, ...]
    status: str
    schema: str = SCHEMA
    evidence_scope: str = EVIDENCE_SCOPE
    runtime_credit: int = 0
    physical_host_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["verified_refs"] = list(self.verified_refs)
        value["violations"] = list(self.violations)
        return value


def evaluate_portable_release_static_completeness(
    package_root: str | Path, *, prehandoff_receipt_ref: str
) -> PortableReleaseStaticCompletenessReceipt:
    root = Path(package_root).resolve(strict=True)
    if not root.is_dir():
        raise PortableReleaseStaticCompletenessError("package_root must be a directory")

    pre = evaluate_pre_handoff_release(root, prehandoff_receipt_ref=prehandoff_receipt_ref)
    violations: list[str] = []
    verified: list[str] = []
    if pre.status != READY_STATUS:
        violations.append("prehandoff:not_ready")

    metadata = _load_json_file(root, METADATA_PATH, "release_contract", violations)
    python_min: str | None = None
    migration_version: str | None = None

    if metadata is not None:
        if metadata.get("schema") != METADATA_SCHEMA:
            violations.append("release_contract:schema_mismatch")

        runtime = metadata.get("baseline_runtime")
        if not isinstance(runtime, dict):
            violations.append("baseline_runtime:missing_or_invalid")
        else:
            if runtime.get("implementation") != "CPython":
                violations.append("baseline_runtime:implementation_mismatch")
            python_min = runtime.get("minimum_version") if isinstance(runtime.get("minimum_version"), str) else None
            if python_min is None or not _VERSION_RE.fullmatch(python_min):
                violations.append("baseline_runtime:minimum_version_invalid")
            if runtime.get("dependency_class") != "PYTHON_STDLIB_BASELINE":
                violations.append("baseline_runtime:dependency_class_mismatch")
            refs = runtime.get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                violations.append("baseline_runtime:evidence_refs_missing")
            else:
                for i, ref in enumerate(refs):
                    resolved = _safe_file(root, ref, f"baseline_runtime:evidence_ref:{i}", violations)
                    if resolved:
                        verified.append(resolved)

        migration = metadata.get("state_migration")
        if not isinstance(migration, dict):
            violations.append("state_migration:missing_or_invalid")
        else:
            migration_version = migration.get("version") if isinstance(migration.get("version"), str) else None
            if migration_version != STATE_MIGRATION_VERSION:
                violations.append("state_migration:version_mismatch")
            for key in ("source_ref", "acceptance_ref"):
                resolved = _safe_file(root, migration.get(key), f"state_migration:{key}", violations)
                if resolved:
                    verified.append(resolved)

        supported = metadata.get("supported_hosts")
        if not isinstance(supported, dict):
            violations.append("supported_hosts:missing_or_invalid")
        else:
            route_ref = _safe_file(root, supported.get("route_map_ref"), "supported_hosts:route_map_ref", violations)
            if route_ref:
                verified.append(route_ref)
            keys = supported.get("required_route_keys")
            if not isinstance(keys, list) or tuple(keys) != _REQUIRED_HOST_KEYS:
                violations.append("supported_hosts:required_route_keys_mismatch")
            resolved_route_names = {name for name, _ in pre.resolved_routes}
            for key in _REQUIRED_HOST_KEYS:
                if key not in resolved_route_names:
                    violations.append(f"supported_hosts:{key}:not_resolved_by_prehandoff")

        optional = metadata.get("optional_feature_capabilities")
        if not isinstance(optional, dict):
            violations.append("optional_feature_capabilities:missing_or_invalid")
        else:
            host_abi = _safe_file(root, optional.get("host_abi_ref"), "optional_feature_capabilities:host_abi_ref", violations)
            if host_abi:
                verified.append(host_abi)
            refs = optional.get("perception_policy_refs")
            if not isinstance(refs, list) or not refs:
                violations.append("optional_feature_capabilities:perception_policy_refs_missing")
            else:
                for i, ref in enumerate(refs):
                    resolved = _safe_file(root, ref, f"optional_feature_capabilities:perception_policy_ref:{i}", violations)
                    if resolved:
                        verified.append(resolved)

        defaults = metadata.get("perception_defaults")
        if not isinstance(defaults, dict):
            violations.append("perception_defaults:missing_or_invalid")
        else:
            if defaults.get("raw_frame_persistence") is not False:
                violations.append("perception_defaults:raw_frame_persistence_must_be_false")
            if defaults.get("vlm_escalation") != "EXPLICIT_PERMISSION_REQUIRED":
                violations.append("perception_defaults:vlm_escalation_mismatch")

        verifier = metadata.get("verifier_self_test")
        if not isinstance(verifier, dict):
            violations.append("verifier_self_test:missing_or_invalid")
        else:
            if verifier.get("kind") != "AGENT_PROCEDURE":
                violations.append("verifier_self_test:kind_mismatch")
            entry = _safe_file(root, verifier.get("entry_ref"), "verifier_self_test:entry_ref", violations)
            if entry:
                verified.append(entry)
                route_verify_paths = {path for name, path in pre.resolved_routes if name == "verify_install"}
                if entry not in route_verify_paths:
                    violations.append("verifier_self_test:not_same_as_prehandoff_verify_route")

    ordered = tuple(sorted(set(violations)))
    return PortableReleaseStaticCompletenessReceipt(
        release_id=pre.release_id,
        source_commit=pre.source_commit,
        release_manifest_sha256=pre.release_manifest_sha256,
        prehandoff_status=pre.status,
        metadata_path=METADATA_PATH,
        baseline_python_minimum=python_min,
        state_migration_version=migration_version,
        verified_refs=tuple(sorted(set(verified))),
        violations=ordered,
        status=STATIC_COMPLETE if not ordered else BLOCKED,
    )
