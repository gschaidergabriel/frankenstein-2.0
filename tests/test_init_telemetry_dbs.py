#!/usr/bin/env python3
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "init_telemetry_dbs.py"

EXPECTED = {
    "system_telemetry.sqlite": {"sources", "system_events", "schema_meta"},
    "communications.sqlite": {"communications", "schema_meta"},
    "hypotheses.sqlite": {"hypotheses", "hypothesis_evidence", "schema_meta"},
    "bugs.sqlite": {"bugs", "schema_meta"},
    "grid10_telemetry.sqlite": {
        "grid_cycles",
        "grid_cells",
        "hyperposition_branches",
        "world_projections",
        "microlab_calls",
        "gwt_events",
        "schema_meta",
    },
    "performance.sqlite": {"spans", "resource_samples", "schema_meta"},
}

HYPOTHESIS_STATES = (
    "OPEN",
    "TEST_PLANNED",
    "TESTING",
    "SUPPORTED",
    "REFUTED",
    "INCONCLUSIVE",
    "SUPERSEDED",
    "RETIRED",
)

BUG_STATES = (
    "OPEN",
    "REPRODUCED",
    "ROOT_CAUSE_HYPOTHESIZED",
    "ROOT_CAUSE_CONFIRMED",
    "FIX_CANDIDATE",
    "REGRESSION_PENDING",
    "REOPENED",
    "WONT_FIX",
)

GRID_CHILD_INSERTS = {
    "grid_cells": (
        "INSERT INTO grid_cells(cell_event_id,run_id,cycle_id,cell_id,status) VALUES (?,?,?,?,?)",
        lambda prefix, run_id, cycle_id: (f"{prefix}-cell", run_id, cycle_id, "G1", "COMPLETE"),
    ),
    "hyperposition_branches": (
        "INSERT INTO hyperposition_branches(branch_id,run_id,cycle_id) VALUES (?,?,?)",
        lambda prefix, run_id, cycle_id: (f"{prefix}-branch", run_id, cycle_id),
    ),
    "world_projections": (
        """INSERT INTO world_projections(
            projection_id,run_id,cycle_id,projection_type,payload_digest,recorded_at_utc
        ) VALUES (?,?,?,?,?,?)""",
        lambda prefix, run_id, cycle_id: (
            f"{prefix}-projection",
            run_id,
            cycle_id,
            "OBSERVATION",
            "digest",
            "2026-08-28T00:00:00Z",
        ),
    ),
    "microlab_calls": (
        """INSERT INTO microlab_calls(
            call_id,run_id,cycle_id,simulator_type,input_digest,recorded_at_utc
        ) VALUES (?,?,?,?,?,?)""",
        lambda prefix, run_id, cycle_id: (
            f"{prefix}-microlab",
            run_id,
            cycle_id,
            "test",
            "digest",
            "2026-08-28T00:00:00Z",
        ),
    ),
    "gwt_events": (
        """INSERT INTO gwt_events(
            gwt_event_id,run_id,cycle_id,phase,payload_digest,recorded_at_utc
        ) VALUES (?,?,?,?,?,?)""",
        lambda prefix, run_id, cycle_id: (
            f"{prefix}-gwt",
            run_id,
            cycle_id,
            "BROADCAST",
            "digest",
            "2026-08-28T00:00:00Z",
        ),
    ),
}


def tables(path: Path) -> set[str]:
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def assert_expected_schema(dbroot: Path) -> None:
    for name, required in EXPECTED.items():
        path = dbroot / name
        assert path.is_file(), path
        got = tables(path)
        assert required <= got, (name, required - got)
        con = sqlite3.connect(path)
        try:
            version = con.execute(
                "SELECT schema_version FROM schema_meta WHERE schema_name=?", (name,)
            ).fetchone()
            assert version == (3,), (name, version)
            assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            con.close()


def assert_hypothesis_lifecycle(dbroot: Path) -> None:
    con = sqlite3.connect(dbroot / "hypotheses.sqlite")
    try:
        for idx, status in enumerate(HYPOTHESIS_STATES):
            con.execute(
                """INSERT INTO hypotheses(
                    hypothesis_id,run_id,kind,statement,status,falsification_criterion,
                    created_at_utc,updated_at_utc
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    f"H{idx}",
                    "RUN",
                    "HYPOTHESIS",
                    "contract-state-test",
                    status,
                    "contradicting evidence",
                    "2026-08-28T00:00:00Z",
                    "2026-08-28T00:00:00Z",
                ),
            )
        try:
            con.execute(
                """INSERT INTO hypotheses(
                    hypothesis_id,run_id,kind,statement,status,falsification_criterion,
                    created_at_utc,updated_at_utc
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    "BAD",
                    "RUN",
                    "HYPOTHESIS",
                    "bad-state",
                    "FALSIFIED",
                    "criterion",
                    "2026-08-28T00:00:00Z",
                    "2026-08-28T00:00:00Z",
                ),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("non-contract hypothesis lifecycle state was accepted")
        con.rollback()
    finally:
        con.close()


def assert_bug_lifecycle_and_fixed_gate(dbroot: Path) -> None:
    con = sqlite3.connect(dbroot / "bugs.sqlite")
    try:
        for idx, status in enumerate(BUG_STATES):
            con.execute(
                "INSERT INTO bugs(bug_id,status,symptom,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?)",
                (f"B{idx}", status, "symptom", "2026-08-28T00:00:00Z", "2026-08-28T00:00:00Z"),
            )
        try:
            con.execute(
                "INSERT INTO bugs(bug_id,status,symptom,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?)",
                ("BF", "FIXED", "symptom", "2026-08-28T00:00:00Z", "2026-08-28T00:00:00Z"),
            )
        except sqlite3.IntegrityError as exc:
            assert "FIXED requires" in str(exc)
        else:
            raise AssertionError("FIXED without closure evidence was accepted")

        con.execute(
            """INSERT INTO bugs(
                bug_id,status,symptom,root_cause,root_cause_evidence_ref,fix_commit,
                regression_test_ref,regression_receipt_ref,created_at_utc,updated_at_utc
            ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                "BF2",
                "FIXED",
                "symptom",
                "cause",
                "evidence",
                "abc123",
                "test",
                "receipt",
                "2026-08-28T00:00:00Z",
                "2026-08-28T00:00:00Z",
            ),
        )
        con.rollback()
    finally:
        con.close()


def expect_integrity_error(con: sqlite3.Connection, sql: str, params: tuple, needle: str) -> None:
    try:
        con.execute(sql, params)
    except sqlite3.IntegrityError as exc:
        assert needle in str(exc), (needle, str(exc))
    else:
        raise AssertionError(f"expected sqlite3.IntegrityError containing {needle!r}")


def assert_grid_causal_integrity(dbroot: Path) -> None:
    con = sqlite3.connect(dbroot / "grid10_telemetry.sqlite")
    try:
        con.execute(
            """INSERT INTO grid_cycles(
                event_id,run_id,recorded_at_utc,cycle_id,situation_frame_digest
            ) VALUES (?,?,?,?,?)""",
            ("cycle-event", "run-A", "2026-08-28T00:00:00Z", "cycle-A", "situation"),
        )

        for table, (sql, make_params) in GRID_CHILD_INSERTS.items():
            expect_integrity_error(
                con,
                sql,
                make_params(f"orphan-{table}", "run-A", "missing-cycle"),
                "existing same-run GRID cycle",
            )
            expect_integrity_error(
                con,
                sql,
                make_params(f"wrong-run-{table}", "run-B", "cycle-A"),
                "existing same-run GRID cycle",
            )
            con.execute(sql, make_params(f"valid-{table}", "run-A", "cycle-A"))

        expect_integrity_error(
            con,
            "DELETE FROM grid_cycles WHERE run_id=? AND cycle_id=?",
            ("run-A", "cycle-A"),
            "has child telemetry",
        )
        expect_integrity_error(
            con,
            "UPDATE grid_cycles SET cycle_id=? WHERE run_id=? AND cycle_id=?",
            ("cycle-renamed", "run-A", "cycle-A"),
            "identity is referenced",
        )
        con.rollback()
    finally:
        con.close()


def assert_v2_reentry_fails_closed_on_existing_orphan(dbroot: Path) -> None:
    path = dbroot / "grid10_telemetry.sqlite"
    con = sqlite3.connect(path)
    try:
        trigger_names = [
            row[0]
            for row in con.execute(
                """SELECT name FROM sqlite_master
                WHERE type='trigger'
                  AND (name LIKE 'enforce_%_grid_cycle_%' OR name LIKE 'protect_grid_cycle_%')"""
            )
        ]
        assert len(trigger_names) == 12, trigger_names
        for name in trigger_names:
            con.execute(f'DROP TRIGGER "{name}"')
        con.execute(
            "UPDATE schema_meta SET schema_version=2 WHERE schema_name='grid10_telemetry.sqlite'"
        )
        con.execute(
            "INSERT INTO grid_cells(cell_event_id,run_id,cycle_id,cell_id,status) VALUES (?,?,?,?,?)",
            ("legacy-orphan", "legacy-run", "missing-cycle", "G1", "COMPLETE"),
        )
        con.commit()
    finally:
        con.close()

    failed = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(dbroot)],
        text=True,
        capture_output=True,
    )
    assert failed.returncode != 0, failed.stdout
    assert "causal integrity failure" in failed.stderr, failed.stderr

    con = sqlite3.connect(path)
    try:
        con.execute("DELETE FROM grid_cells WHERE cell_event_id='legacy-orphan'")
        con.commit()
    finally:
        con.close()

    subprocess.run([sys.executable, str(SCRIPT), "--root", str(dbroot)], check=True)
    con = sqlite3.connect(path)
    try:
        version = con.execute(
            "SELECT schema_version FROM schema_meta WHERE schema_name='grid10_telemetry.sqlite'"
        ).fetchone()[0]
        assert version == 3, version
        restored = con.execute(
            """SELECT COUNT(*) FROM sqlite_master
            WHERE type='trigger'
              AND (name LIKE 'enforce_%_grid_cycle_%' OR name LIKE 'protect_grid_cycle_%')"""
        ).fetchone()[0]
        assert restored == 12, restored
    finally:
        con.close()


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        dbroot = td_path / "dbs"

        for _ in range(2):
            subprocess.run([sys.executable, str(SCRIPT), "--root", str(dbroot)], check=True)
        assert_expected_schema(dbroot)

        subprocess.run([sys.executable, str(SCRIPT)], cwd=td_path, check=True)
        canonical_root = td_path / "data"
        assert_expected_schema(canonical_root)
        assert not (td_path / "databases").exists(), "superseded databases/ default reappeared"

        assert_hypothesis_lifecycle(dbroot)
        assert_bug_lifecycle_and_fixed_gate(dbroot)
        assert_grid_causal_integrity(dbroot)
        assert_v2_reentry_fails_closed_on_existing_orphan(dbroot)

    print(
        "PASS: telemetry v3 schema, canonical data/ default, idempotence, mandatory "
        "hypothesis/bug lifecycles, FIXED fail-closed gate, GRID child/cycle causal "
        "integrity, schema-v2 reentry orphan rejection"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
