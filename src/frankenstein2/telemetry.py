"""Fail-closed telemetry writes for Frankenstein 2.0.

This module is intentionally narrow: it writes explicitly supplied, causally bound
system events into the canonical telemetry spine. It does not invent identifiers,
wall-clock timestamps, causal lineage, or runtime completion claims.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from .causal_identity import CausalIdentity

_SYSTEM_DB = "system_telemetry.sqlite"
_EXPECTED_SYSTEM_COLUMNS = frozenset(
    {
        "event_id",
        "run_id",
        "workpackage_id",
        "generation",
        "recorded_at_utc",
        "monotonic_ns",
        "trace_id",
        "span_id",
        "parent_span_id",
        "session_id",
        "agent_id",
        "task_id",
        "turn_id",
        "causal_id",
        "invocation_id",
        "tool_use_id",
        "child_agent_id",
        "component",
        "severity",
        "event_type",
        "payload_json",
    }
)
_ALLOWED_SEVERITIES = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_MAX_TEXT = 1024
_MAX_PAYLOAD_BYTES = 1_048_576


class TelemetryWriteError(RuntimeError):
    """Raised when a telemetry write cannot be admitted exactly and safely."""


def _strict_text(name: str, value: Any, *, max_len: int = _MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise TelemetryWriteError(f"{name} must be a string")
    if not value or value != value.strip():
        raise TelemetryWriteError(f"{name} must be non-empty and already trimmed")
    if len(value) > max_len:
        raise TelemetryWriteError(f"{name} exceeds {max_len} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TelemetryWriteError(f"{name} contains control characters")
    return value


def _optional_text(name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _strict_text(name, value)


def _utc_timestamp(value: Any) -> str:
    text = _strict_text("recorded_at_utc", value)
    if not text.endswith("Z"):
        raise TelemetryWriteError("recorded_at_utc must be explicit UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise TelemetryWriteError("recorded_at_utc must be valid RFC3339/ISO-8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise TelemetryWriteError("recorded_at_utc must resolve to UTC")
    return text


def _monotonic_ns(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise TelemetryWriteError("monotonic_ns must be a non-negative integer or null")
    return value


def _canonical_payload(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        raise TelemetryWriteError("payload must be a mapping")
    try:
        encoded = json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TelemetryWriteError("payload must be finite deterministic JSON") from exc
    if len(encoded.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise TelemetryWriteError(f"payload exceeds {_MAX_PAYLOAD_BYTES} UTF-8 bytes")
    return encoded


class TelemetryWriter:
    """Write exact causal system events to an initialized telemetry root.

    The writer refuses to create databases or silently migrate schemas. Initialization
    belongs to ``tools/init_telemetry_dbs.py`` so a missing/stale telemetry substrate is
    observable as a failure rather than being papered over during event emission.
    """

    def __init__(self, root: str | Path, *, busy_timeout_ms: int = 5000) -> None:
        self.root = Path(root)
        if type(busy_timeout_ms) is not int or busy_timeout_ms < 0:
            raise TelemetryWriteError("busy_timeout_ms must be a non-negative integer")
        self.busy_timeout_ms = busy_timeout_ms

    @property
    def system_db_path(self) -> Path:
        return self.root / _SYSTEM_DB

    def _open_system_db(self) -> sqlite3.Connection:
        path = self.system_db_path
        if not path.is_file():
            raise TelemetryWriteError(f"telemetry database missing: {path}")
        conn = sqlite3.connect(path)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            observed = {
                row[1] for row in conn.execute("PRAGMA table_info(system_events)").fetchall()
            }
            missing = sorted(_EXPECTED_SYSTEM_COLUMNS - observed)
            if missing:
                raise TelemetryWriteError(
                    "system_events schema missing required column(s): " + ", ".join(missing)
                )
        except Exception:
            conn.close()
            raise
        return conn

    def emit_system_event(
        self,
        *,
        event_id: str,
        run_id: str,
        identity: CausalIdentity,
        recorded_at_utc: str,
        component: str,
        severity: str,
        event_type: str,
        payload: Mapping[str, Any],
        workpackage_id: str | None = None,
        monotonic_ns: int | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        invocation_id: str | None = None,
        tool_use_id: str | None = None,
        child_agent_id: str | None = None,
    ) -> None:
        if not isinstance(identity, CausalIdentity):
            raise TelemetryWriteError("identity must be an explicit CausalIdentity")
        # The current system_events schema has causal_id but no parent_causal_id.
        # Silently dropping derived lineage would turn correlation into false causal
        # closure, so derived events remain blocked until the typed schema migrates.
        if identity.parent_causal_id is not None:
            raise TelemetryWriteError(
                "system_events schema cannot preserve parent_causal_id; derived causal event rejected"
            )
        event_id = _strict_text("event_id", event_id)
        run_id = _strict_text("run_id", run_id)
        workpackage_id = _optional_text("workpackage_id", workpackage_id)
        recorded_at_utc = _utc_timestamp(recorded_at_utc)
        component = _strict_text("component", component)
        severity = _strict_text("severity", severity)
        if severity not in _ALLOWED_SEVERITIES:
            raise TelemetryWriteError(
                "severity must be one of " + ", ".join(sorted(_ALLOWED_SEVERITIES))
            )
        event_type = _strict_text("event_type", event_type)
        monotonic_ns = _monotonic_ns(monotonic_ns)
        trace_id = _optional_text("trace_id", trace_id)
        span_id = _optional_text("span_id", span_id)
        parent_span_id = _optional_text("parent_span_id", parent_span_id)
        invocation_id = _optional_text("invocation_id", invocation_id)
        tool_use_id = _optional_text("tool_use_id", tool_use_id)
        child_agent_id = _optional_text("child_agent_id", child_agent_id)
        payload_json = _canonical_payload(payload)

        values = (
            event_id,
            run_id,
            workpackage_id,
            identity.generation,
            recorded_at_utc,
            monotonic_ns,
            trace_id,
            span_id,
            parent_span_id,
            identity.session_id,
            identity.agent_id,
            identity.task_id,
            identity.turn_id,
            identity.causal_id,
            invocation_id,
            tool_use_id,
            child_agent_id,
            component,
            severity,
            event_type,
            payload_json,
        )
        conn = self._open_system_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO system_events (
                    event_id, run_id, workpackage_id, generation, recorded_at_utc,
                    monotonic_ns, trace_id, span_id, parent_span_id, session_id,
                    agent_id, task_id, turn_id, causal_id, invocation_id,
                    tool_use_id, child_agent_id, component, severity, event_type,
                    payload_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                values,
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise TelemetryWriteError(
                f"telemetry event rejected by canonical database: {exc}"
            ) from exc
        except sqlite3.DatabaseError as exc:
            conn.rollback()
            raise TelemetryWriteError(f"telemetry database write failed: {exc}") from exc
        finally:
            conn.close()
