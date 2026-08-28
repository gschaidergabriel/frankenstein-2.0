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
            assert version == (2,), (name, version)
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

    print(
        "PASS: telemetry v2 schema, canonical data/ default, idempotence, "
        "mandatory hypothesis/bug lifecycles, FIXED fail-closed gate"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
