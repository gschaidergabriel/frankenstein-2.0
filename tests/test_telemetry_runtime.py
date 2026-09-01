#!/usr/bin/env python3
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.telemetry_runtime import CausalContext, TelemetryRuntime, finalize_run


def count(path: Path, table: str) -> int:
    with sqlite3.connect(path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data_root = root / "data"
        run_root = root / "runs" / "RUN-1"
        ctx = CausalContext(
            run_id="RUN-1",
            workpackage_id="F2-WP-005",
            generation=1,
            trace_id="TRACE-1",
            session_id="SESSION-1",
            causal_id="CAUSE-1",
        )
        telemetry = TelemetryRuntime(data_root, ctx)

        telemetry.register_source("component-a", "component-a", source_commit="abc123")
        telemetry.register_source(
            "external-b",
            "external-b",
            "NOT_INSTRUMENTABLE",
            reason="synthetic fixture has no event stream",
        )
        telemetry.emit_system_event("component-a", "TEST_EVENT", {"value": 1})
        telemetry.emit_communication(
            "component-a",
            "internal",
            "INTERNAL",
            "ACKED",
            "digest-message",
            recipient_id="component-b",
            metadata={"test": True},
        )
        hypothesis_id = telemetry.record_hypothesis(
            "The finalizer closes only complete declared-source runs.",
            "A run closes despite a missing declared source disposition.",
            discriminator="negative completeness fixture",
            priority=1,
        )
        telemetry.record_bug("synthetic open bug", reproduction="fixture", status="OPEN")

        cycle_id = "CYCLE-1"
        telemetry.emit_grid_cycle(
            cycle_id,
            "situation-digest",
            hyperposition_digest="hyper-digest",
            completion_deficit={"open": 1},
            token_budget=100,
            branch_budget=2,
            decision="OBSERVE",
        )
        start = time.monotonic_ns()
        end = start + 1000
        telemetry.emit_grid_cell(
            cycle_id,
            "G3",
            status="COMPLETE",
            input_digest="in",
            output_digest="out",
            salience=0.5,
            confidence=0.6,
            utility=0.7,
            expected_information_gain=0.8,
            cost_estimate=0.1,
            started_monotonic_ns=start,
            finished_monotonic_ns=end,
        )
        branch_id = telemetry.emit_hyperposition_branch(
            cycle_id,
            hypothesis_ref=hypothesis_id,
            branch_weight=0.5,
            status="OPEN",
            discriminator_ref="disc-1",
        )
        telemetry.emit_world_projection(
            cycle_id,
            "QUBO",
            "projection-digest",
            disagreement=0.2,
            provenance={"branch": branch_id},
        )
        telemetry.emit_microlab_call(
            cycle_id,
            "constraint-check",
            "micro-input",
            result_digest="micro-output",
            cost={"steps": 3},
        )
        telemetry.emit_gwt_event(
            cycle_id,
            "BROADCAST",
            "broadcast-digest",
            subject_id="G3",
            influenced_later_decision=True,
            downstream_ref="decision-1",
        )
        telemetry.emit_span(
            "component-a",
            "fixture-operation",
            start,
            end_monotonic_ns=end,
            system_state="GRID_BURST",
            compute_ns=700,
            db_ns=300,
        )
        telemetry.emit_resource_sample(
            "component-a",
            system_state="GRID_BURST",
            rss_bytes=1024,
            cpu_percent=1.0,
            work_units={"grid_cycles": 1},
        )

        closed = finalize_run(
            data_root,
            run_root,
            "RUN-1",
            ["component-a", "external-b"],
            grid_participated=True,
        )
        assert closed["telemetry_completeness"] == "COMPLETE_FOR_DECLARED_SOURCES"
        assert closed["whole_system_runtime_credit"] is False
        for name in (
            "system_telemetry.sqlite",
            "communications.sqlite",
            "hypotheses.sqlite",
            "bugs.sqlite",
            "grid10_telemetry.sqlite",
            "performance.sqlite",
            "metrics.json",
            "SHA256SUMS",
            "CLOSED.json",
        ):
            assert (run_root / name).is_file(), name

        assert count(run_root / "system_telemetry.sqlite", "system_events") == 1
        assert count(run_root / "communications.sqlite", "communications") == 1
        assert count(run_root / "hypotheses.sqlite", "hypotheses") == 1
        assert count(run_root / "bugs.sqlite", "bugs") == 1
        assert count(run_root / "grid10_telemetry.sqlite", "grid_cycles") == 1
        assert count(run_root / "grid10_telemetry.sqlite", "hyperposition_branches") == 1
        assert count(run_root / "grid10_telemetry.sqlite", "world_projections") == 1
        assert count(run_root / "grid10_telemetry.sqlite", "microlab_calls") == 1
        assert count(run_root / "grid10_telemetry.sqlite", "gwt_events") == 1
        assert count(run_root / "performance.sqlite", "spans") == 1
        assert count(run_root / "performance.sqlite", "resource_samples") == 1
        metrics = json.loads((run_root / "metrics.json").read_text())
        assert metrics["run_id"] == "RUN-1"

        failed_root = root / "runs" / "RUN-MISSING"
        try:
            finalize_run(
                data_root,
                failed_root,
                "RUN-1",
                ["component-a", "missing-source"],
                grid_participated=False,
            )
        except RuntimeError as exc:
            assert "missing telemetry source dispositions" in str(exc)
        else:
            raise AssertionError("missing expected telemetry source did not fail closed")
        assert not (failed_root / "CLOSED.json").exists()

        try:
            telemetry.register_source("bad-source", "bad", "NOT_OBSERVABLE")
        except ValueError as exc:
            assert "requires a non-empty reason" in str(exc)
        else:
            raise AssertionError("NOT_OBSERVABLE without reason was accepted")

    # REVIEW_ONLY falsifier 1: source_id is currently a global primary key.
    # Registering the same logical source in a later run rewrites the older run's
    # provenance instead of preserving a distinct (run_id, source_id) identity.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data_root = root / "data"
        run_a = TelemetryRuntime(data_root, CausalContext(run_id="RUN-A", workpackage_id="F2-WP-005", generation=2))
        run_b = TelemetryRuntime(data_root, CausalContext(run_id="RUN-B", workpackage_id="F2-WP-005", generation=2))
        run_a.register_source("shared-source", "component-a", source_commit="commit-a")
        run_b.register_source("shared-source", "component-b", source_commit="commit-b")
        with sqlite3.connect(data_root / "system_telemetry.sqlite") as conn:
            rows = conn.execute(
                "SELECT run_id,source_id,component,source_commit FROM sources WHERE source_id=?",
                ("shared-source",),
            ).fetchall()
        assert rows == [("RUN-B", "shared-source", "component-b", "commit-b")], rows

    # REVIEW_ONLY falsifier 2: finalize_run() currently backs up the complete
    # longitudinal project DB. A RUN-A package therefore contains RUN-B rows.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data_root = root / "data"
        out = root / "runs" / "RUN-A"
        run_a = TelemetryRuntime(data_root, CausalContext(run_id="RUN-A", workpackage_id="F2-WP-005", generation=2))
        run_b = TelemetryRuntime(data_root, CausalContext(run_id="RUN-B", workpackage_id="F2-WP-005", generation=2))
        run_a.register_source("source-a", "component-a")
        run_b.register_source("source-b", "component-b")
        run_a.emit_system_event("component-a", "RUN_A_EVENT", {"marker": "RUN-A-ONLY"}, event_id="evt-run-a")
        run_b.emit_system_event("component-b", "RUN_B_EVENT", {"marker": "RUN-B-SHOULD-NOT-BE-IN-RUN-A"}, event_id="evt-run-b")
        finalize_run(data_root, out, "RUN-A", ["source-a"], grid_participated=False)
        with sqlite3.connect(out / "system_telemetry.sqlite") as conn:
            snapshot_runs = [row[0] for row in conn.execute("SELECT run_id FROM system_events ORDER BY run_id")]
        assert snapshot_runs == ["RUN-A", "RUN-B"], snapshot_runs

    print("PASS: telemetry baseline plus REVIEW_ONLY WP005-G2 run-isolation falsifiers reproduced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
