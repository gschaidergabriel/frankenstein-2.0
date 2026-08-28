#!/usr/bin/env python3
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "init_telemetry_dbs.py"

EXPECTED = {
    "system_telemetry.sqlite": {"system_events", "schema_meta"},
    "communications.sqlite": {"communications", "schema_meta"},
    "hypotheses.sqlite": {"hypotheses", "hypothesis_evidence", "schema_meta"},
    "bugs.sqlite": {"bugs", "schema_meta"},
    "grid10_telemetry.sqlite": {"grid_cycles", "grid_cells", "gwt_events", "schema_meta"},
    "performance.sqlite": {"spans", "resource_samples", "schema_meta"},
}


def tables(path: Path) -> set[str]:
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        dbroot = Path(td) / "dbs"
        # Idempotence is required because setup may be re-entered after restart.
        for _ in range(2):
            subprocess.run([sys.executable, str(SCRIPT), "--root", str(dbroot)], check=True)

        for name, required in EXPECTED.items():
            got = tables(dbroot / name)
            assert required <= got, (name, required - got)

        bugdb = sqlite3.connect(dbroot / "bugs.sqlite")
        try:
            try:
                bugdb.execute(
                    "INSERT INTO bugs(bug_id,status,symptom,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?)",
                    ("B1", "FIXED", "symptom", "2026-08-28T00:00:00Z", "2026-08-28T00:00:00Z"),
                )
            except sqlite3.IntegrityError as exc:
                assert "FIXED requires" in str(exc)
            else:
                raise AssertionError("FIXED without evidence was accepted")

            bugdb.execute(
                """INSERT INTO bugs(
                    bug_id,status,symptom,root_cause,root_cause_evidence_ref,fix_commit,
                    regression_test_ref,regression_receipt_ref,created_at_utc,updated_at_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    "B2", "FIXED", "symptom", "cause", "evidence", "abc123", "test", "receipt",
                    "2026-08-28T00:00:00Z", "2026-08-28T00:00:00Z",
                ),
            )
            bugdb.commit()
        finally:
            bugdb.close()

    print("PASS: telemetry initializer idempotence, schema presence, FIXED fail-closed gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
