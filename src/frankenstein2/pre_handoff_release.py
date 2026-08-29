"""Deterministic static one-handoff release gate for Frankenstein 2.0.

F2-WP-1110 generation 1.

This module binds the already-admitted deterministic release-manifest implementation to
Frankenstein 2.0's machine-readable installer route graph before any real clean-machine
execution.  It deliberately does *not* execute an installer, mutate a host, perform
network/provider/VPS work, or grant runtime/physical/effect/completion credit.

The receipt is intended to live outside the release payload.  The release manifest binds
its stable receipt reference; this receipt then binds the final manifest digest.  That
avoids a self-hash cycle while giving the later clean-machine validator one exact pair:

    release_manifest_sha256 + prehandoff_receipt_ref

Laws:

    STATIC_READY != REAL_HOST_ACCEPTED
    MANIFEST_VALID != INSTALL_RUNTIME_OBSERVED
    RECEIPT_REF_BOUND != RECEIPT_EFFECT_AUTHORITY
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from frankenstein2.release_integrity import load_and_verify_release_manifest

PREHANDOFF_SCHEMA = "FRANKENSTEIN2_PREHANDOFF_RELEASE_RECEIPT/v1"
ROUTES_SCHEMA = "FRANKENSTEIN2_AI_INSTALL_ROUTE/v1"
ROUTES_PATH = "AI_START_HERE_DO_NOT_SCAN_REPO/01_ROUTES.json"
EVIDENCE_SCOPE = "STATIC_RELEASE_PREHANDOFF_ONLY_NO_INSTALL_RUNTIME_EFFECT_OR_COMPLETION_CREDIT"
READY_STATUS = "READY_FOR_REAL_HOST_HANDOFF"
BLOCKED_STATUS = "BLOCKED"

EXPECTED_ROOT_RULE = "ROOT = parent(directory_containing_this_file)"
EXPECTED_STATE_RULE = "ONE_CANONICAL_DURABLE_LOCAL_F2_STATE_OUTSIDE_DISPOSABLE_HOST_CACHE"
EXPECTED_VPS_RULE = "OPTIONAL_EXTENSION_NOT_BASELINE_PRODUCT_LOCATION"
EXPECTED_PRODUCTION_READY_CONDITION = "PORTABLE_ONE_HANDOFF_RELEASE_GATE_ACCEPTED"

ROUTE_KEYS = (
    "claude_code",
    "codex_cli",
    "distribution_contract",
    "donor_installer_audit",
    "other_agent",
    "portable_delivery_phase",
    "product_completion_law",
    "verify_install",
)


class PreHandoffReleaseError(ValueError):
    """Static pre-handoff input cannot be interpreted safely."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _require_nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise PreHandoffReleaseError(f"{name} must be a non-empty already-trimmed string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PreHandoffReleaseError(f"{name} contains control characters")
    return value


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class PreHandoffReleaseReceipt:
    release_id: str
    source_commit: str
    source_tree: str
    build_id: str
    release_manifest_sha256: str
    prehandoff_receipt_ref: str
    routes_sha256: str | None
    resolved_routes: tuple[tuple[str, str], ...]
    violations: tuple[str, ...]
    status: str
    evidence_scope: str = EVIDENCE_SCOPE
    runtime_credit: int = 0
    physical_host_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False
    schema: str = PREHANDOFF_SCHEMA

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["resolved_routes"] = [
            {"route": route, "path": path} for route, path in self.resolved_routes
        ]
        value["violations"] = list(self.violations)
        return value

    def canonical_bytes(self) -> bytes:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_bytes(self.canonical_bytes())


def _load_routes(routes_file: Path, violations: list[str]) -> tuple[Mapping[str, Any] | None, str | None]:
    if routes_file.is_symlink() or not routes_file.is_file():
        violations.append("routes:missing_or_nonregular")
        return None, None
    raw = routes_file.read_bytes()
    digest = _sha256_bytes(raw)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        violations.append("routes:invalid_utf8_json")
        return None, digest
    if not isinstance(value, dict):
        violations.append("routes:root_not_object")
        return None, digest
    return value, digest


def _resolve_declared_route(
    *,
    root: Path,
    routes_dir: Path,
    route_name: str,
    raw_value: Any,
    violations: list[str],
) -> str | None:
    if not isinstance(raw_value, str) or not raw_value or raw_value != raw_value.strip():
        violations.append(f"routes:{route_name}:invalid_path")
        return None
    try:
        candidate = (routes_dir / raw_value).resolve(strict=True)
    except (OSError, RuntimeError):
        violations.append(f"routes:{route_name}:missing")
        return None
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        violations.append(f"routes:{route_name}:escapes_release_root")
        return None
    if candidate.is_symlink() or not candidate.is_file():
        violations.append(f"routes:{route_name}:not_regular_file")
        return None
    return relative.as_posix()


def evaluate_pre_handoff_release(
    package_root: str | Path,
    *,
    prehandoff_receipt_ref: str,
) -> PreHandoffReleaseReceipt:
    """Evaluate static release readiness without manufacturing host evidence.

    Release payload integrity is delegated to ``load_and_verify_release_manifest`` so this
    component cannot become a second release-manifest authority.  Route problems produce a
    deterministic BLOCKED receipt.  Manifest-integrity failures remain exceptions from the
    existing fail-closed integrity layer.
    """

    receipt_ref = _require_nonempty(prehandoff_receipt_ref, "prehandoff_receipt_ref")
    root = Path(package_root).resolve(strict=True)
    if not root.is_dir():
        raise PreHandoffReleaseError("package_root must resolve to a directory")

    manifest = load_and_verify_release_manifest(root)
    manifest_sha = manifest.sha256()
    violations: list[str] = []

    if receipt_ref not in manifest.prehandoff_receipt_refs:
        violations.append("prehandoff_receipt_ref:not_bound_in_release_manifest")

    routes_file = root / ROUTES_PATH
    routes, routes_sha = _load_routes(routes_file, violations)
    resolved_routes: list[tuple[str, str]] = []

    if routes is not None:
        if routes.get("schema") != ROUTES_SCHEMA:
            violations.append("routes:schema_mismatch")
        if routes.get("root_rule") != EXPECTED_ROOT_RULE:
            violations.append("routes:root_rule_mismatch")
        if routes.get("state_rule") != EXPECTED_STATE_RULE:
            violations.append("routes:state_rule_mismatch")
        if routes.get("vps_rule") != EXPECTED_VPS_RULE:
            violations.append("routes:vps_rule_mismatch")
        if routes.get("production_ready_condition") != EXPECTED_PRODUCTION_READY_CONDITION:
            violations.append("routes:production_ready_condition_mismatch")

        routes_dir = routes_file.parent.resolve(strict=True)
        for route_name in ROUTE_KEYS:
            if route_name not in routes:
                violations.append(f"routes:{route_name}:missing_key")
                continue
            resolved = _resolve_declared_route(
                root=root,
                routes_dir=routes_dir,
                route_name=route_name,
                raw_value=routes.get(route_name),
                violations=violations,
            )
            if resolved is not None:
                resolved_routes.append((route_name, resolved))

    ordered_violations = tuple(sorted(set(violations)))
    status = READY_STATUS if not ordered_violations else BLOCKED_STATUS

    return PreHandoffReleaseReceipt(
        release_id=manifest.release_id,
        source_commit=manifest.source_commit,
        source_tree=manifest.source_tree,
        build_id=manifest.build_id,
        release_manifest_sha256=manifest_sha,
        prehandoff_receipt_ref=receipt_ref,
        routes_sha256=routes_sha,
        resolved_routes=tuple(sorted(resolved_routes)),
        violations=ordered_violations,
        status=status,
    )
