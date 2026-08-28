"""Trigger-6 E3 fixture adapter for a pinned AgentSight snapshot.

Research-only. This module cannot authorize effects, establish completion, or
become canonical state. It reduces a pinned AgentSight schema-v1 export into
minimized, provenance-preserving witness rows for falsification.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Iterable

PINNED_AGENTSIGHT_COMMIT = "934f441eff8ca210807333633f47b2efcb8cd020"
SUPPORTED_SCHEMA_VERSION = 1
AUTHORITY_SCOPE = "NONCANONICAL_OBSERVABILITY_WITNESS_ONLY"

_SENSITIVE_KEYS = {
    "argv", "command", "cwd", "details", "input", "output", "path",
    "subject", "summary", "target", "attributes",
}
_VIEW_CLASSES = {
    "view": "DIRECT_CAPTURE_WITNESS",
    "sqlite": "RECONSTRUCTED_PERSISTED_WITNESS",
    "agent_native_session": "AGENT_NATIVE_FALLBACK_WITNESS",
    "unknown": "UNKNOWN_PROVENANCE_WITNESS",
}


class SnapshotSchemaError(ValueError):
    pass


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def _as_list(snapshot: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = snapshot.get(key, [])
    if not isinstance(value, list):
        raise SnapshotSchemaError(f"{key} must be an array")
    if any(not isinstance(item, dict) for item in value):
        raise SnapshotSchemaError(f"{key} entries must be objects")
    return value


def _provenance(view_source: Any) -> tuple[str, str]:
    if not isinstance(view_source, str):
        return "unknown", _VIEW_CLASSES["unknown"]
    normalized = view_source if view_source in _VIEW_CLASSES else "unknown"
    return normalized, _VIEW_CLASSES[normalized]


def _clean_metadata(row: dict[str, Any], allow: Iterable[str]) -> dict[str, Any]:
    allowed = set(allow)
    out: dict[str, Any] = {}
    for key in allowed:
        if key in row and key not in _SENSITIVE_KEYS:
            value = row[key]
            if isinstance(value, (str, int, float, bool)) or value is None:
                out[key] = value
    return out


def _witness(kind: str, row: dict[str, Any], *, timestamp_key: str) -> dict[str, Any]:
    view_source, evidence_class = _provenance(row.get("view_source"))
    confidence = row.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        confidence = None

    foreign_ids = {
        key: row.get(key)
        for key in ("id", "session_id", "conversation_id", "tool_call_id",
                    "related_event_id", "related_pid", "pid", "ppid", "root_pid")
        if row.get(key) is not None
    }
    return {
        "witness_kind": kind,
        "foreign_ids": foreign_ids,
        "observed_timestamp_ms": row.get(timestamp_key),
        "view_source": view_source,
        "evidence_class": evidence_class,
        "source_confidence": confidence,
        "causal_binding_status": "UNBOUND_FOREIGN_ID",
        "canonical_truth_credit": False,
        "effect_authority_credit": False,
        "completion_authority_credit": False,
        "metadata": _clean_metadata(
            row,
            {
                "audit_type", "action", "status", "comm", "tool_name",
                "duration_ms", "start_timestamp_ms", "end_timestamp_ms",
                "exit_code",
            },
        ),
    }


def adapt_agentsight_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Adapt a pinned AgentSight schema-v1 snapshot into read-only witness rows."""
    if not isinstance(snapshot, dict):
        raise SnapshotSchemaError("snapshot must be an object")
    if snapshot.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise SnapshotSchemaError(
            f"unsupported AgentSight schema_version={snapshot.get('schema_version')!r}"
        )

    records: list[dict[str, Any]] = []
    for row in _as_list(snapshot, "process_nodes"):
        records.append(_witness("process_node", row, timestamp_key="start_timestamp_ms"))
    for row in _as_list(snapshot, "audit_events"):
        records.append(_witness("audit_event", row, timestamp_key="timestamp_ms"))
    for row in _as_list(snapshot, "tool_calls"):
        records.append(_witness("tool_call", row, timestamp_key="timestamp_ms"))

    # Sessions are useful for provenance but must not import arbitrary attributes.
    for row in _as_list(snapshot, "sessions"):
        records.append(_witness("session", row, timestamp_key="start_timestamp_ms"))

    return {
        "schema": "F2_TRIGGER6_AGENTSIGHT_WITNESS_FIXTURE/v1",
        "research_id": "R6-SEED-005",
        "evidence_level": "E3_FIXTURE_REPRODUCED_ONLY",
        "agent_sight_source_commit": PINNED_AGENTSIGHT_COMMIT,
        "agent_sight_schema_version": SUPPORTED_SCHEMA_VERSION,
        "source_snapshot_sha256": _canonical_digest(snapshot),
        "authority_scope": AUTHORITY_SCOPE,
        "canonical_state_writer": False,
        "effect_gate_authority": False,
        "effect_journal_authority": False,
        "completion_authority": False,
        "records": records,
    }


def compare_fixture_coverage(
    adapted: dict[str, Any], native_baseline: dict[str, Any]
) -> dict[str, Any]:
    """Compare fixture event-kind coverage only; this is not a runtime benchmark."""
    native_events = native_baseline.get("events", [])
    if not isinstance(native_events, list):
        raise ValueError("native baseline events must be an array")
    native_kinds = {
        e.get("witness_kind")
        for e in native_events
        if isinstance(e, dict) and isinstance(e.get("witness_kind"), str)
    }
    external_kinds = {
        e["witness_kind"] for e in adapted.get("records", []) if "witness_kind" in e
    }
    return {
        "measurement_scope": "FIXTURE_EVENT_KIND_COVERAGE_ONLY",
        "native_kinds": sorted(native_kinds),
        "agentsight_witness_kinds": sorted(external_kinds),
        "incremental_kinds": sorted(external_kinds - native_kinds),
        "shared_kinds": sorted(external_kinds & native_kinds),
        "capture_overhead_measured": False,
        "cpu_overhead_measured": False,
        "rss_overhead_measured": False,
        "io_overhead_measured": False,
        "latency_overhead_measured": False,
        "privilege_requirement_runtime_tested": False,
    }
