#!/usr/bin/env python3
"""Initialize Frankenstein 2.0 telemetry SQLite databases.

Standard-library only. This creates schema, not runtime evidence.
Existing databases are migrated idempotently by CREATE IF NOT EXISTS.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DB_NAMES = (
    "system_telemetry.sqlite",
    "communications.sqlite",
    "hypotheses.sqlite",
    "bugs.sqlite",
    "grid10_telemetry.sqlite",
    "performance.sqlite",
)

COMMON_EVENT_COLUMNS = """
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    workpackage_id TEXT,
    generation INTEGER,
    recorded_at_utc TEXT NOT NULL,
    monotonic_ns INTEGER,
    trace_id TEXT,
    span_id TEXT,
    parent_span_id TEXT,
    session_id TEXT,
    agent_id TEXT,
    task_id TEXT,
    turn_id TEXT,
    causal_id TEXT,
    invocation_id TEXT,
    tool_use_id TEXT,
    child_agent_id TEXT
"""

SCHEMAS = {
    "system_telemetry.sqlite": f"""
        CREATE TABLE IF NOT EXISTS system_events (
            {COMMON_EVENT_COLUMNS},
            component TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('DEBUG','INFO','WARNING','ERROR','CRITICAL')),
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
        );
        CREATE INDEX IF NOT EXISTS idx_system_events_run_time
            ON system_events(run_id, recorded_at_utc);
        CREATE INDEX IF NOT EXISTS idx_system_events_causal
            ON system_events(causal_id);
    """,
    "communications.sqlite": f"""
        CREATE TABLE IF NOT EXISTS communications (
            {COMMON_EVENT_COLUMNS},
            sender_id TEXT NOT NULL,
            recipient_id TEXT,
            channel TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('IN','OUT','INTERNAL')),
            lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('PENDING','OFFERED','ACKED','FAILED','DROPPED')),
            message_digest TEXT NOT NULL,
            payload_ref TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_communications_delivery_identity
            ON communications(event_id, COALESCE(recipient_id, ''));
        CREATE INDEX IF NOT EXISTS idx_communications_delivery
            ON communications(run_id, recipient_id, lifecycle_state);
    """,
    "hypotheses.sqlite": """
        CREATE TABLE IF NOT EXISTS hypotheses (
            hypothesis_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            workpackage_id TEXT,
            generation INTEGER,
            kind TEXT NOT NULL CHECK (kind IN ('HYPOTHESIS','COUNTERHYPOTHESIS')),
            statement TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('OPEN','SUPPORTED','WEAKENED','FALSIFIED','UNRESOLVED')),
            confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
            falsifier TEXT,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            source_refs_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(source_refs_json))
        );
        CREATE TABLE IF NOT EXISTS hypothesis_evidence (
            evidence_id TEXT PRIMARY KEY,
            hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE RESTRICT,
            polarity TEXT NOT NULL CHECK (polarity IN ('FOR','AGAINST','NEUTRAL')),
            evidence_type TEXT NOT NULL,
            evidence_ref TEXT NOT NULL,
            recorded_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hypothesis_evidence_h
            ON hypothesis_evidence(hypothesis_id, polarity);
    """,
    "bugs.sqlite": """
        CREATE TABLE IF NOT EXISTS bugs (
            bug_id TEXT PRIMARY KEY,
            workpackage_id TEXT,
            generation INTEGER,
            status TEXT NOT NULL CHECK (status IN ('OPEN','ROOT_CAUSE_CANDIDATE','FIX_CANDIDATE','REGRESSION_PENDING','FIXED','WONT_FIX')),
            symptom TEXT NOT NULL,
            reproduction TEXT,
            root_cause TEXT,
            root_cause_evidence_ref TEXT,
            fix_commit TEXT,
            regression_test_ref TEXT,
            regression_receipt_ref TEXT,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS bugs_fixed_requires_evidence_insert
        BEFORE INSERT ON bugs
        WHEN NEW.status = 'FIXED'
        AND (
            NULLIF(TRIM(COALESCE(NEW.root_cause,'')), '') IS NULL OR
            NULLIF(TRIM(COALESCE(NEW.root_cause_evidence_ref,'')), '') IS NULL OR
            NULLIF(TRIM(COALESCE(NEW.fix_commit,'')), '') IS NULL OR
            NULLIF(TRIM(COALESCE(NEW.regression_test_ref,'')), '') IS NULL OR
            NULLIF(TRIM(COALESCE(NEW.regression_receipt_ref,'')), '') IS NULL
        )
        BEGIN
            SELECT RAISE(ABORT, 'FIXED requires root cause, evidence, fix commit, regression test and receipt');
        END;
        CREATE TRIGGER IF NOT EXISTS bugs_fixed_requires_evidence_update
        BEFORE UPDATE OF status, root_cause, root_cause_evidence_ref, fix_commit, regression_test_ref, regression_receipt_ref
        ON bugs
        WHEN NEW.status = 'FIXED'
        AND (
            NULLIF(TRIM(COALESCE(NEW.root_cause,'')), '') IS NULL OR
            NULLIF(TRIM(COALESCE(NEW.root_cause_evidence_ref,'')), '') IS NULL OR
            NULLIF(TRIM(COALESCE(NEW.fix_commit,'')), '') IS NULL OR
            NULLIF(TRIM(COALESCE(NEW.regression_test_ref,'')), '') IS NULL OR
            NULLIF(TRIM(COALESCE(NEW.regression_receipt_ref,'')), '') IS NULL
        )
        BEGIN
            SELECT RAISE(ABORT, 'FIXED requires root cause, evidence, fix commit, regression test and receipt');
        END;
    """,
    "grid10_telemetry.sqlite": f"""
        CREATE TABLE IF NOT EXISTS grid_cycles (
            {COMMON_EVENT_COLUMNS},
            cycle_id TEXT NOT NULL UNIQUE,
            situation_frame_digest TEXT NOT NULL,
            control_snapshot_digest TEXT,
            hyperposition_digest TEXT,
            completion_deficit_json TEXT NOT NULL DEFAULT '{{}}' CHECK (json_valid(completion_deficit_json))
        );
        CREATE TABLE IF NOT EXISTS grid_cells (
            cell_event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            cycle_id TEXT NOT NULL,
            cell_id TEXT NOT NULL,
            model_or_engine TEXT,
            started_monotonic_ns INTEGER,
            finished_monotonic_ns INTEGER,
            input_digest TEXT,
            output_digest TEXT,
            status TEXT NOT NULL CHECK (status IN ('NOT_STARTED','RUNNING','COMPLETE','FAILED','SKIPPED'))
        );
        CREATE TABLE IF NOT EXISTS gwt_events (
            gwt_event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            cycle_id TEXT NOT NULL,
            phase TEXT NOT NULL CHECK (phase IN ('CANDIDATE','SELECT','BROADCAST','UPTAKE','REENTRY')),
            subject_id TEXT,
            payload_digest TEXT NOT NULL,
            provenance_json TEXT NOT NULL DEFAULT '{{}}' CHECK (json_valid(provenance_json)),
            recorded_at_utc TEXT NOT NULL,
            monotonic_ns INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_grid_cells_cycle ON grid_cells(run_id, cycle_id, cell_id);
        CREATE INDEX IF NOT EXISTS idx_gwt_cycle_phase ON gwt_events(run_id, cycle_id, phase);
    """,
    "performance.sqlite": """
        CREATE TABLE IF NOT EXISTS spans (
            span_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            trace_id TEXT NOT NULL,
            parent_span_id TEXT,
            workpackage_id TEXT,
            component TEXT NOT NULL,
            operation TEXT NOT NULL,
            start_utc TEXT NOT NULL,
            end_utc TEXT,
            start_monotonic_ns INTEGER NOT NULL,
            end_monotonic_ns INTEGER,
            status TEXT NOT NULL CHECK (status IN ('RUNNING','OK','ERROR','CANCELLED')),
            attributes_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(attributes_json))
        );
        CREATE TABLE IF NOT EXISTS resource_samples (
            sample_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            component TEXT NOT NULL,
            recorded_at_utc TEXT NOT NULL,
            monotonic_ns INTEGER,
            rss_bytes INTEGER,
            pss_bytes INTEGER,
            cpu_seconds REAL,
            cpu_percent REAL,
            gpu_memory_bytes INTEGER,
            io_read_bytes INTEGER,
            io_write_bytes INTEGER,
            attributes_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(attributes_json))
        );
        CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(run_id, trace_id, start_monotonic_ns);
        CREATE INDEX IF NOT EXISTS idx_resources_run_time ON resource_samples(run_id, monotonic_ns);
    """,
}


def configure(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")


def init_db(path: Path, schema: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        configure(conn)
        conn.executescript(schema)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta (schema_name TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
        )
        conn.execute(
            "INSERT INTO schema_meta(schema_name, schema_version) VALUES (?, 1) "
            "ON CONFLICT(schema_name) DO UPDATE SET schema_version=excluded.schema_version",
            (path.name,),
        )
        conn.commit()
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"{path}: integrity_check={result!r}")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="databases", help="directory for telemetry SQLite files")
    args = parser.parse_args()
    root = Path(args.root)
    for name in DB_NAMES:
        init_db(root / name, SCHEMAS[name])
    print(f"initialized {len(DB_NAMES)} telemetry databases under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
