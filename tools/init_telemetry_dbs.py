#!/usr/bin/env python3
"""Initialize the canonical Frankenstein 2.0 telemetry SQLite databases.

Phase-0 evidence-spine component only. This module creates storage contracts and
does not claim that all Frankenstein 2.0 components are already instrumented.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence

SCHEMA_VERSION = "1"
INITIALIZER_ID = "F2-WP-005/init_telemetry_dbs.py"

DATABASE_SCHEMAS: Mapping[str, Sequence[str]] = {
    "system_telemetry.sqlite": (
        """
        CREATE TABLE IF NOT EXISTS component_events (
            event_id TEXT PRIMARY KEY,
            observed_at_utc TEXT NOT NULL,
            monotonic_ns INTEGER,
            component TEXT NOT NULL,
            operation TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'INFO',
            run_id TEXT,
            workpackage_id TEXT,
            generation INTEGER,
            trace_id TEXT,
            span_id TEXT,
            parent_span_id TEXT,
            session_id TEXT,
            agent_id TEXT,
            task_id TEXT,
            turn_id TEXT,
            causal_id TEXT,
            invocation_id TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS system_state_intervals (
            interval_id TEXT PRIMARY KEY,
            state_name TEXT NOT NULL,
            started_at_utc TEXT NOT NULL,
            ended_at_utc TEXT,
            start_monotonic_ns INTEGER,
            end_monotonic_ns INTEGER,
            run_id TEXT,
            trace_id TEXT,
            causal_id TEXT,
            attributes_json TEXT NOT NULL DEFAULT '{}'
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_component_events_run_trace ON component_events(run_id, trace_id)",
        "CREATE INDEX IF NOT EXISTS idx_component_events_causal ON component_events(causal_id)",
        "CREATE INDEX IF NOT EXISTS idx_state_intervals_run ON system_state_intervals(run_id, state_name)",
    ),
    "communications.sqlite": (
        """
        CREATE TABLE IF NOT EXISTS communication_events (
            event_id TEXT PRIMARY KEY,
            observed_at_utc TEXT NOT NULL,
            monotonic_ns INTEGER,
            direction TEXT NOT NULL CHECK(direction IN ('INTERNAL','OUTBOUND','INBOUND')),
            channel TEXT NOT NULL,
            sender_id TEXT,
            recipient_id TEXT,
            message_kind TEXT NOT NULL,
            run_id TEXT,
            workpackage_id TEXT,
            generation INTEGER,
            trace_id TEXT,
            session_id TEXT,
            agent_id TEXT,
            task_id TEXT,
            turn_id TEXT,
            causal_id TEXT,
            invocation_id TEXT,
            tool_use_id TEXT,
            child_agent_id TEXT,
            payload_digest TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}'
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_communication_causal ON communication_events(causal_id, event_id)",
        "CREATE INDEX IF NOT EXISTS idx_communication_agent_task ON communication_events(agent_id, task_id)",
        "CREATE INDEX IF NOT EXISTS idx_communication_run ON communication_events(run_id, observed_at_utc)",
    ),
    "hypotheses.sqlite": (
        """
        CREATE TABLE IF NOT EXISTS hypotheses (
            hypothesis_id TEXT PRIMARY KEY,
            created_at_utc TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('HYPOTHESIS','COUNTERHYPOTHESIS')),
            statement TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('OPEN','SUPPORTED','WEAKENED','FALSIFIED','UNRESOLVED')),
            confidence REAL,
            run_id TEXT,
            workpackage_id TEXT,
            generation INTEGER,
            causal_id TEXT,
            parent_hypothesis_id TEXT,
            FOREIGN KEY(parent_hypothesis_id) REFERENCES hypotheses(hypothesis_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hypothesis_evidence (
            evidence_id TEXT PRIMARY KEY,
            hypothesis_id TEXT NOT NULL,
            observed_at_utc TEXT NOT NULL,
            relation TEXT NOT NULL CHECK(relation IN ('SUPPORTS','CONTRADICTS','CONTEXT')),
            evidence_ref TEXT NOT NULL,
            source_class TEXT NOT NULL,
            notes TEXT,
            FOREIGN KEY(hypothesis_id) REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS targeted_tests (
            test_id TEXT PRIMARY KEY,
            hypothesis_id TEXT NOT NULL,
            proposed_at_utc TEXT NOT NULL,
            discriminator TEXT NOT NULL,
            expected_information_gain REAL,
            status TEXT NOT NULL CHECK(status IN ('PROPOSED','RUNNING','PASS','FAIL','BLOCKED')),
            run_id TEXT,
            result_ref TEXT,
            FOREIGN KEY(hypothesis_id) REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_hypotheses_workpackage ON hypotheses(workpackage_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_hypothesis_evidence_h ON hypothesis_evidence(hypothesis_id, relation)",
    ),
    "bugs.sqlite": (
        """
        CREATE TABLE IF NOT EXISTS bugs (
            bug_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            first_seen_at_utc TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('OPEN','ROOT_CAUSE_CANDIDATE','ROOT_CAUSE_CONFIRMED','FIX_CANDIDATE','REGRESSION_PENDING','FIXED')),
            symptom TEXT NOT NULL,
            root_cause TEXT,
            root_cause_evidence_ref TEXT,
            fix_commit TEXT,
            regression_test_ref TEXT,
            regression_receipt_ref TEXT,
            run_id TEXT,
            workpackage_id TEXT,
            causal_id TEXT,
            CHECK(
                status != 'FIXED'
                OR (
                    root_cause IS NOT NULL
                    AND root_cause_evidence_ref IS NOT NULL
                    AND fix_commit IS NOT NULL
                    AND regression_test_ref IS NOT NULL
                    AND regression_receipt_ref IS NOT NULL
                )
            )
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bug_evidence (
            evidence_id TEXT PRIMARY KEY,
            bug_id TEXT NOT NULL,
            observed_at_utc TEXT NOT NULL,
            evidence_kind TEXT NOT NULL,
            evidence_ref TEXT NOT NULL,
            notes TEXT,
            FOREIGN KEY(bug_id) REFERENCES bugs(bug_id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_bugs_status ON bugs(status, workpackage_id)",
        "CREATE INDEX IF NOT EXISTS idx_bug_evidence_bug ON bug_evidence(bug_id)",
    ),
    "grid10_telemetry.sqlite": (
        """
        CREATE TABLE IF NOT EXISTS grid_cycles (
            cycle_id TEXT PRIMARY KEY,
            started_at_utc TEXT NOT NULL,
            ended_at_utc TEXT,
            run_id TEXT,
            workpackage_id TEXT,
            generation INTEGER,
            trace_id TEXT,
            causal_id TEXT,
            situation_digest TEXT,
            control_snapshot_digest TEXT,
            outcome_kind TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS grid_cell_events (
            cell_event_id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL,
            cell_id TEXT NOT NULL,
            event_kind TEXT NOT NULL,
            observed_at_utc TEXT NOT NULL,
            monotonic_ns INTEGER,
            proposal_id TEXT,
            branch_id TEXT,
            budget_json TEXT NOT NULL DEFAULT '{}',
            payload_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(cycle_id) REFERENCES grid_cycles(cycle_id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS gwt_events (
            gwt_event_id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL,
            observed_at_utc TEXT NOT NULL,
            event_kind TEXT NOT NULL CHECK(event_kind IN ('SELECT','BROADCAST','UPTAKE','REENTRY','ABSTAIN')),
            candidate_id TEXT,
            recipient_id TEXT,
            causal_influence_ref TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(cycle_id) REFERENCES grid_cycles(cycle_id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_grid_cell_cycle ON grid_cell_events(cycle_id, cell_id)",
        "CREATE INDEX IF NOT EXISTS idx_gwt_cycle_kind ON gwt_events(cycle_id, event_kind)",
        "CREATE INDEX IF NOT EXISTS idx_grid_cycles_run ON grid_cycles(run_id, started_at_utc)",
    ),
    "performance.sqlite": (
        """
        CREATE TABLE IF NOT EXISTS spans (
            span_id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            parent_span_id TEXT,
            component TEXT NOT NULL,
            subsystem TEXT,
            operation TEXT NOT NULL,
            state_name TEXT,
            run_id TEXT,
            workpackage_id TEXT,
            generation INTEGER,
            agent_id TEXT,
            task_id TEXT,
            invocation_id TEXT,
            started_at_utc TEXT NOT NULL,
            ended_at_utc TEXT,
            start_monotonic_ns INTEGER,
            end_monotonic_ns INTEGER,
            queue_wait_ns INTEGER NOT NULL DEFAULT 0,
            compute_ns INTEGER NOT NULL DEFAULT 0,
            io_wait_ns INTEGER NOT NULL DEFAULT 0,
            network_wait_ns INTEGER NOT NULL DEFAULT 0,
            model_wait_ns INTEGER NOT NULL DEFAULT 0,
            db_wait_ns INTEGER NOT NULL DEFAULT 0,
            child_wait_ns INTEGER NOT NULL DEFAULT 0,
            unattributed_ns INTEGER NOT NULL DEFAULT 0,
            attributes_json TEXT NOT NULL DEFAULT '{}'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resource_samples (
            sample_id TEXT PRIMARY KEY,
            observed_at_utc TEXT NOT NULL,
            monotonic_ns INTEGER,
            run_id TEXT,
            component TEXT NOT NULL,
            state_name TEXT,
            cpu_percent REAL,
            rss_bytes INTEGER,
            pss_bytes INTEGER,
            disk_read_bytes INTEGER,
            disk_write_bytes INTEGER,
            network_rx_bytes INTEGER,
            network_tx_bytes INTEGER,
            gpu_util_percent REAL,
            vram_bytes INTEGER,
            model_calls INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER,
            attributes_json TEXT NOT NULL DEFAULT '{}'
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id, start_monotonic_ns)",
        "CREATE INDEX IF NOT EXISTS idx_spans_run_component ON spans(run_id, component)",
        "CREATE INDEX IF NOT EXISTS idx_resource_run_state ON resource_samples(run_id, state_name, observed_at_utc)",
    ),
}

EXPECTED_TABLES: Mapping[str, frozenset[str]] = {
    "system_telemetry.sqlite": frozenset({"schema_meta", "component_events", "system_state_intervals"}),
    "communications.sqlite": frozenset({"schema_meta", "communication_events"}),
    "hypotheses.sqlite": frozenset({"schema_meta", "hypotheses", "hypothesis_evidence", "targeted_tests"}),
    "bugs.sqlite": frozenset({"schema_meta", "bugs", "bug_evidence"}),
    "grid10_telemetry.sqlite": frozenset({"schema_meta", "grid_cycles", "grid_cell_events", "gwt_events"}),
    "performance.sqlite": frozenset({"schema_meta", "spans", "resource_samples"}),
}


def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def _initialize_database(path: Path, statements: Iterable[str]) -> None:
    with _connect(path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        con.executemany(
            "INSERT OR IGNORE INTO schema_meta(key, value) VALUES (?, ?)",
            (
                ("schema_name", path.name),
                ("schema_version", SCHEMA_VERSION),
                ("initializer_id", INITIALIZER_ID),
            ),
        )
        for statement in statements:
            con.execute(statement)

        metadata = dict(con.execute("SELECT key, value FROM schema_meta"))
        expected = {
            "schema_name": path.name,
            "schema_version": SCHEMA_VERSION,
            "initializer_id": INITIALIZER_ID,
        }
        if metadata != expected:
            raise RuntimeError(
                f"schema metadata mismatch for {path.name}: expected {expected}, got {metadata}"
            )


def initialize_all(root: Path) -> Dict[str, str]:
    root = Path(root)
    db_dir = root / "databases"
    db_dir.mkdir(parents=True, exist_ok=True)
    for name, statements in DATABASE_SCHEMAS.items():
        _initialize_database(db_dir / name, statements)
    verify_all(root)
    return {name: str(db_dir / name) for name in DATABASE_SCHEMAS}


def verify_all(root: Path) -> None:
    root = Path(root)
    db_dir = root / "databases"
    errors = []
    for name, expected_tables in EXPECTED_TABLES.items():
        path = db_dir / name
        if not path.exists():
            errors.append(f"{name}: missing")
            continue
        with _connect(path) as con:
            if con.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                errors.append(f"{name}: foreign_keys disabled")
            actual_tables = {
                row[0]
                for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            missing = expected_tables - actual_tables
            if missing:
                errors.append(f"{name}: missing tables {sorted(missing)}")
            metadata = dict(con.execute("SELECT key, value FROM schema_meta"))
            expected_meta = {
                "schema_name": name,
                "schema_version": SCHEMA_VERSION,
                "initializer_id": INITIALIZER_ID,
            }
            if metadata != expected_meta:
                errors.append(f"{name}: metadata mismatch {metadata!r}")
    if errors:
        raise RuntimeError("; ".join(errors))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Databases are created under <root>/databases/.",
    )
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.verify_only:
        verify_all(args.root)
        result = {"ok": True, "mode": "verify", "root": str(args.root)}
    else:
        paths = initialize_all(args.root)
        result = {"ok": True, "mode": "initialize", "root": str(args.root), "databases": paths}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
