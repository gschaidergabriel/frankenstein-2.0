#!/usr/bin/env python3
"""Reusable Frankenstein 2.0 telemetry emitters and run finalizer.

This module sits above ``init_telemetry_dbs.py``. It provides deterministic,
standard-library-only writers for the canonical project telemetry stores and a
fail-closed run finalizer that snapshots the stores only after all declared
participating sources have an explicit instrumentation disposition.

It does not grant runtime, effect, completion, or truth authority.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.init_telemetry_dbs import DB_NAMES, SCHEMAS, init_db

SOURCE_STATES = {"INSTRUMENTED", "NOT_INSTRUMENTABLE", "NOT_OBSERVABLE"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class CausalContext:
    run_id: str
    workpackage_id: str | None = None
    generation: int | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    turn_id: str | None = None
    causal_id: str | None = None
    invocation_id: str | None = None
    tool_use_id: str | None = None
    child_agent_id: str | None = None

    def common(self, event_id: str) -> dict[str, Any]:
        return {
            "event_id": event_id,
            "run_id": self.run_id,
            "workpackage_id": self.workpackage_id,
            "generation": self.generation,
            "recorded_at_utc": utc_now(),
            "monotonic_ns": time.monotonic_ns(),
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "turn_id": self.turn_id,
            "causal_id": self.causal_id,
            "invocation_id": self.invocation_id,
            "tool_use_id": self.tool_use_id,
            "child_agent_id": self.child_agent_id,
        }


class TelemetryRuntime:
    def __init__(self, data_root: str | Path, context: CausalContext) -> None:
        self.data_root = Path(data_root)
        self.context = context
        for name in DB_NAMES:
            init_db(self.data_root / name, SCHEMAS[name])

    def _connect(self, name: str) -> sqlite3.Connection:
        conn = sqlite3.connect(self.data_root / name)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def register_source(
        self,
        source_id: str,
        component: str,
        status: str = "INSTRUMENTED",
        *,
        reason: str | None = None,
        source_commit: str | None = None,
    ) -> None:
        if status not in SOURCE_STATES:
            raise ValueError(f"invalid source status: {status}")
        if status != "INSTRUMENTED" and not (reason and reason.strip()):
            raise ValueError(f"{status} requires a non-empty reason")
        with self._connect("system_telemetry.sqlite") as conn:
            conn.execute(
                """INSERT INTO sources(
                    source_id,run_id,component,instrumentation_status,reason,source_commit,registered_at_utc
                ) VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(source_id) DO UPDATE SET
                    run_id=excluded.run_id,
                    component=excluded.component,
                    instrumentation_status=excluded.instrumentation_status,
                    reason=excluded.reason,
                    source_commit=excluded.source_commit,
                    registered_at_utc=excluded.registered_at_utc""",
                (source_id, self.context.run_id, component, status, reason, source_commit, utc_now()),
            )

    def emit_system_event(
        self,
        component: str,
        event_type: str,
        payload: Any,
        *,
        severity: str = "INFO",
        event_id: str | None = None,
    ) -> str:
        event_id = event_id or new_id("evt")
        row = self.context.common(event_id)
        row.update(
            component=component,
            severity=severity,
            event_type=event_type,
            payload_json=canonical_json(payload),
        )
        columns = list(row)
        with self._connect("system_telemetry.sqlite") as conn:
            conn.execute(
                f"INSERT INTO system_events({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                [row[c] for c in columns],
            )
        return event_id

    def emit_communication(
        self,
        sender_id: str,
        channel: str,
        direction: str,
        lifecycle_state: str,
        message_digest: str,
        *,
        recipient_id: str | None = None,
        payload_ref: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        latency_ms: float | None = None,
        interrupted: bool = False,
        cancelled: bool = False,
        completion_ref: str | None = None,
        metadata: Any | None = None,
        event_id: str | None = None,
    ) -> str:
        event_id = event_id or new_id("comm")
        row = self.context.common(event_id)
        row.update(
            sender_id=sender_id,
            recipient_id=recipient_id,
            channel=channel,
            direction=direction,
            lifecycle_state=lifecycle_state,
            message_digest=message_digest,
            payload_ref=payload_ref,
            model=model,
            provider=provider,
            latency_ms=latency_ms,
            interrupted=int(interrupted),
            cancelled=int(cancelled),
            completion_ref=completion_ref,
            metadata_json=canonical_json(metadata or {}),
        )
        columns = list(row)
        with self._connect("communications.sqlite") as conn:
            conn.execute(
                f"INSERT INTO communications({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                [row[c] for c in columns],
            )
        return event_id

    def record_hypothesis(
        self,
        statement: str,
        falsification_criterion: str,
        *,
        kind: str = "HYPOTHESIS",
        status: str = "OPEN",
        hypothesis_id: str | None = None,
        parent_id: str | None = None,
        opponent_id: str | None = None,
        rationale: str | None = None,
        confidence: float | None = None,
        priority: int | None = None,
        discriminator: str | None = None,
        component: str | None = None,
        source_refs: Iterable[str] = (),
    ) -> str:
        hypothesis_id = hypothesis_id or new_id("hyp")
        now = utc_now()
        with self._connect("hypotheses.sqlite") as conn:
            conn.execute(
                """INSERT INTO hypotheses(
                    hypothesis_id,run_id,workpackage_id,generation,kind,parent_id,opponent_id,
                    statement,rationale,status,confidence,priority,falsification_criterion,
                    discriminator,component,created_at_utc,updated_at_utc,source_refs_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    hypothesis_id,
                    self.context.run_id,
                    self.context.workpackage_id,
                    self.context.generation,
                    kind,
                    parent_id,
                    opponent_id,
                    statement,
                    rationale,
                    status,
                    confidence,
                    priority,
                    falsification_criterion,
                    discriminator,
                    component,
                    now,
                    now,
                    canonical_json(list(source_refs)),
                ),
            )
        return hypothesis_id

    def record_bug(
        self,
        symptom: str,
        *,
        status: str = "OPEN",
        bug_id: str | None = None,
        reproduction: str | None = None,
        root_cause_hypothesis: str | None = None,
        root_cause: str | None = None,
        root_cause_evidence_ref: str | None = None,
        fix_commit: str | None = None,
        regression_test_ref: str | None = None,
        regression_receipt_ref: str | None = None,
    ) -> str:
        bug_id = bug_id or new_id("bug")
        now = utc_now()
        with self._connect("bugs.sqlite") as conn:
            conn.execute(
                """INSERT INTO bugs(
                    bug_id,workpackage_id,generation,status,symptom,reproduction,
                    root_cause_hypothesis,root_cause,root_cause_evidence_ref,fix_commit,
                    regression_test_ref,regression_receipt_ref,created_at_utc,updated_at_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    bug_id,
                    self.context.workpackage_id,
                    self.context.generation,
                    status,
                    symptom,
                    reproduction,
                    root_cause_hypothesis,
                    root_cause,
                    root_cause_evidence_ref,
                    fix_commit,
                    regression_test_ref,
                    regression_receipt_ref,
                    now,
                    now,
                ),
            )
        return bug_id

    def emit_grid_cycle(
        self,
        cycle_id: str,
        situation_frame_digest: str,
        *,
        control_snapshot_digest: str | None = None,
        hyperposition_digest: str | None = None,
        completion_deficit: Any | None = None,
        token_budget: int | None = None,
        time_budget_ms: float | None = None,
        branch_budget: int | None = None,
        recursion_route: str | None = None,
        decision: str | None = None,
        hold_reason: str | None = None,
    ) -> str:
        event_id = new_id("cycle-event")
        row = self.context.common(event_id)
        row.update(
            cycle_id=cycle_id,
            situation_frame_digest=situation_frame_digest,
            control_snapshot_digest=control_snapshot_digest,
            hyperposition_digest=hyperposition_digest,
            completion_deficit_json=canonical_json(completion_deficit or {}),
            token_budget=token_budget,
            time_budget_ms=time_budget_ms,
            branch_budget=branch_budget,
            recursion_route=recursion_route,
            decision=decision,
            hold_reason=hold_reason,
        )
        columns = list(row)
        with self._connect("grid10_telemetry.sqlite") as conn:
            conn.execute(
                f"INSERT INTO grid_cycles({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                [row[c] for c in columns],
            )
        return event_id

    def emit_grid_cell(
        self,
        cycle_id: str,
        cell_id: str,
        *,
        status: str,
        model_or_engine: str | None = None,
        input_digest: str | None = None,
        output_digest: str | None = None,
        salience: float | None = None,
        confidence: float | None = None,
        utility: float | None = None,
        expected_information_gain: float | None = None,
        cost_estimate: float | None = None,
        started_monotonic_ns: int | None = None,
        finished_monotonic_ns: int | None = None,
    ) -> str:
        cell_event_id = new_id("cell")
        with self._connect("grid10_telemetry.sqlite") as conn:
            conn.execute(
                """INSERT INTO grid_cells(
                    cell_event_id,run_id,cycle_id,cell_id,model_or_engine,started_monotonic_ns,
                    finished_monotonic_ns,input_digest,output_digest,salience,confidence,utility,
                    expected_information_gain,cost_estimate,status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    cell_event_id,
                    self.context.run_id,
                    cycle_id,
                    cell_id,
                    model_or_engine,
                    started_monotonic_ns,
                    finished_monotonic_ns,
                    input_digest,
                    output_digest,
                    salience,
                    confidence,
                    utility,
                    expected_information_gain,
                    cost_estimate,
                    status,
                ),
            )
        return cell_event_id

    def emit_hyperposition_branch(
        self,
        cycle_id: str,
        *,
        hypothesis_ref: str | None = None,
        branch_weight: float | None = None,
        status: str | None = None,
        discriminator_ref: str | None = None,
        provenance: Any | None = None,
    ) -> str:
        branch_id = new_id("branch")
        with self._connect("grid10_telemetry.sqlite") as conn:
            conn.execute(
                """INSERT INTO hyperposition_branches(
                    branch_id,run_id,cycle_id,hypothesis_ref,branch_weight,status,discriminator_ref,provenance_json
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    branch_id,
                    self.context.run_id,
                    cycle_id,
                    hypothesis_ref,
                    branch_weight,
                    status,
                    discriminator_ref,
                    canonical_json(provenance or {}),
                ),
            )
        return branch_id

    def emit_world_projection(
        self,
        cycle_id: str,
        projection_type: str,
        payload_digest: str,
        *,
        disagreement: float | None = None,
        provenance: Any | None = None,
    ) -> str:
        projection_id = new_id("projection")
        with self._connect("grid10_telemetry.sqlite") as conn:
            conn.execute(
                """INSERT INTO world_projections(
                    projection_id,run_id,cycle_id,projection_type,payload_digest,disagreement,
                    provenance_json,recorded_at_utc
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    projection_id,
                    self.context.run_id,
                    cycle_id,
                    projection_type,
                    payload_digest,
                    disagreement,
                    canonical_json(provenance or {}),
                    utc_now(),
                ),
            )
        return projection_id

    def emit_microlab_call(
        self,
        cycle_id: str,
        simulator_type: str,
        input_digest: str,
        *,
        result_digest: str | None = None,
        cost: Any | None = None,
    ) -> str:
        call_id = new_id("microlab")
        with self._connect("grid10_telemetry.sqlite") as conn:
            conn.execute(
                """INSERT INTO microlab_calls(
                    call_id,run_id,cycle_id,simulator_type,input_digest,result_digest,cost_json,recorded_at_utc
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    call_id,
                    self.context.run_id,
                    cycle_id,
                    simulator_type,
                    input_digest,
                    result_digest,
                    canonical_json(cost or {}),
                    utc_now(),
                ),
            )
        return call_id

    def emit_gwt_event(
        self,
        cycle_id: str,
        phase: str,
        payload_digest: str,
        *,
        subject_id: str | None = None,
        provenance: Any | None = None,
        influenced_later_decision: bool | None = None,
        downstream_ref: str | None = None,
    ) -> str:
        gwt_event_id = new_id("gwt")
        with self._connect("grid10_telemetry.sqlite") as conn:
            conn.execute(
                """INSERT INTO gwt_events(
                    gwt_event_id,run_id,cycle_id,phase,subject_id,payload_digest,provenance_json,
                    influenced_later_decision,downstream_ref,recorded_at_utc,monotonic_ns
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    gwt_event_id,
                    self.context.run_id,
                    cycle_id,
                    phase,
                    subject_id,
                    payload_digest,
                    canonical_json(provenance or {}),
                    None if influenced_later_decision is None else int(influenced_later_decision),
                    downstream_ref,
                    utc_now(),
                    time.monotonic_ns(),
                ),
            )
        return gwt_event_id

    def emit_span(
        self,
        component: str,
        operation: str,
        start_monotonic_ns: int,
        *,
        end_monotonic_ns: int | None = None,
        status: str = "OK",
        trace_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        system_state: str | None = None,
        start_utc: str | None = None,
        end_utc: str | None = None,
        queue_ns: int | None = None,
        compute_ns: int | None = None,
        io_ns: int | None = None,
        network_ns: int | None = None,
        model_ns: int | None = None,
        db_ns: int | None = None,
        child_wait_ns: int | None = None,
        attributes: Any | None = None,
    ) -> str:
        span_id = span_id or new_id("span")
        trace_id = trace_id or self.context.trace_id or new_id("trace")
        with self._connect("performance.sqlite") as conn:
            conn.execute(
                """INSERT INTO spans(
                    span_id,run_id,trace_id,parent_span_id,workpackage_id,component,operation,
                    system_state,start_utc,end_utc,start_monotonic_ns,end_monotonic_ns,
                    queue_ns,compute_ns,io_ns,network_ns,model_ns,db_ns,child_wait_ns,status,attributes_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    span_id,
                    self.context.run_id,
                    trace_id,
                    parent_span_id or self.context.parent_span_id,
                    self.context.workpackage_id,
                    component,
                    operation,
                    system_state,
                    start_utc or utc_now(),
                    end_utc or (utc_now() if end_monotonic_ns is not None else None),
                    start_monotonic_ns,
                    end_monotonic_ns,
                    queue_ns,
                    compute_ns,
                    io_ns,
                    network_ns,
                    model_ns,
                    db_ns,
                    child_wait_ns,
                    status,
                    canonical_json(attributes or {}),
                ),
            )
        return span_id

    def emit_resource_sample(
        self,
        component: str,
        *,
        system_state: str | None = None,
        rss_bytes: int | None = None,
        pss_bytes: int | None = None,
        vms_bytes: int | None = None,
        peak_rss_bytes: int | None = None,
        cpu_user_seconds: float | None = None,
        cpu_system_seconds: float | None = None,
        cpu_percent: float | None = None,
        gpu_percent: float | None = None,
        gpu_memory_bytes: int | None = None,
        io_read_bytes: int | None = None,
        io_write_bytes: int | None = None,
        network_rx_bytes: int | None = None,
        network_tx_bytes: int | None = None,
        fd_count: int | None = None,
        thread_count: int | None = None,
        queue_depth: int | None = None,
        sqlite_lock_wait_ns: int | None = None,
        power_watts: float | None = None,
        temperature_c: float | None = None,
        work_units: Any | None = None,
        attributes: Any | None = None,
    ) -> str:
        sample_id = new_id("resource")
        with self._connect("performance.sqlite") as conn:
            conn.execute(
                """INSERT INTO resource_samples(
                    sample_id,run_id,component,system_state,recorded_at_utc,monotonic_ns,
                    rss_bytes,pss_bytes,vms_bytes,peak_rss_bytes,cpu_user_seconds,cpu_system_seconds,
                    cpu_percent,gpu_percent,gpu_memory_bytes,io_read_bytes,io_write_bytes,
                    network_rx_bytes,network_tx_bytes,fd_count,thread_count,queue_depth,
                    sqlite_lock_wait_ns,power_watts,temperature_c,work_units_json,attributes_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sample_id,
                    self.context.run_id,
                    component,
                    system_state,
                    utc_now(),
                    time.monotonic_ns(),
                    rss_bytes,
                    pss_bytes,
                    vms_bytes,
                    peak_rss_bytes,
                    cpu_user_seconds,
                    cpu_system_seconds,
                    cpu_percent,
                    gpu_percent,
                    gpu_memory_bytes,
                    io_read_bytes,
                    io_write_bytes,
                    network_rx_bytes,
                    network_tx_bytes,
                    fd_count,
                    thread_count,
                    queue_depth,
                    sqlite_lock_wait_ns,
                    power_watts,
                    temperature_c,
                    canonical_json(work_units or {}),
                    canonical_json(attributes or {}),
                ),
            )
        return sample_id


def source_dispositions(data_root: Path, run_id: str) -> dict[str, tuple[str, str | None]]:
    path = data_root / "system_telemetry.sqlite"
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT source_id,instrumentation_status,reason FROM sources WHERE run_id=?",
            (run_id,),
        ).fetchall()
    return {source_id: (status, reason) for source_id, status, reason in rows}


def assert_source_completeness(data_root: Path, run_id: str, expected_sources: Iterable[str]) -> dict[str, tuple[str, str | None]]:
    expected = set(expected_sources)
    dispositions = source_dispositions(data_root, run_id)
    missing = sorted(expected - set(dispositions))
    if missing:
        raise RuntimeError(f"missing telemetry source dispositions: {missing}")
    invalid = sorted(source for source in expected if dispositions[source][0] not in SOURCE_STATES)
    if invalid:
        raise RuntimeError(f"invalid telemetry source dispositions: {invalid}")
    return {source: dispositions[source] for source in sorted(expected)}


def sqlite_snapshot(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    src = sqlite3.connect(source)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
        dst.commit()
        result = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"snapshot integrity failure {destination}: {result}")
    finally:
        dst.close()
        src.close()


def count_run_rows(path: Path, run_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    with sqlite3.connect(path) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if "run_id" in columns:
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE run_id=?", (run_id,)).fetchone()[0]
    return counts


def finalize_run(
    data_root: str | Path,
    run_root: str | Path,
    run_id: str,
    expected_sources: Iterable[str],
    *,
    grid_participated: bool,
) -> dict[str, Any]:
    data_root = Path(data_root)
    run_root = Path(run_root)
    if (run_root / "CLOSED.json").exists():
        raise FileExistsError(f"run already closed: {run_root}")

    dispositions = assert_source_completeness(data_root, run_id, expected_sources)
    missing_databases = [name for name in DB_NAMES if not (data_root / name).is_file()]
    if missing_databases:
        raise RuntimeError(f"missing project telemetry databases: {missing_databases}")

    run_root.mkdir(parents=True, exist_ok=True)
    metrics: dict[str, Any] = {"schema": "FRANKENSTEIN2_RUN_METRICS/v1", "run_id": run_id, "databases": {}}
    hashes: dict[str, str] = {}

    for name in DB_NAMES:
        destination = run_root / name
        sqlite_snapshot(data_root / name, destination)
        hashes[name] = sha256_file(destination)
        metrics["databases"][name] = count_run_rows(destination, run_id)

    metrics_path = run_root / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hashes["metrics.json"] = sha256_file(metrics_path)

    sums_path = run_root / "SHA256SUMS"
    sums_path.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items())),
        encoding="utf-8",
    )

    closed = {
        "schema": "FRANKENSTEIN2_RUN_CLOSED/v1",
        "run_id": run_id,
        "closed_at_utc": utc_now(),
        "telemetry_completeness": "COMPLETE_FOR_DECLARED_SOURCES",
        "declared_sources": {
            source: {"status": status, "reason": reason}
            for source, (status, reason) in dispositions.items()
        },
        "grid_participated": grid_participated,
        "grid_database_present": (run_root / "grid10_telemetry.sqlite").is_file(),
        "snapshot_mode": "CONSISTENT_SQLITE_BACKUP_OF_PROJECT_STORES",
        "artifact_hash_index": "SHA256SUMS",
        "whole_system_runtime_credit": False,
    }
    if grid_participated and not (run_root / "grid10_telemetry.sqlite").is_file():
        raise RuntimeError("GRID participated but grid10_telemetry.sqlite snapshot is absent")
    (run_root / "CLOSED.json").write_text(json.dumps(closed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return closed
