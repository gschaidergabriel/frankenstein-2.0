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


def assert_expected_schema(dbroot: Path) -> None:
    for name, required in EXPECTED.items():
        path = dbroot / name
        assert path.is_file(), path
        got = tables(path)
        assert required <= got, (name, required - got)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        dbroot = td_path / "dbs"

        # Explicit-root setup is idempotent because setup may be re-entered after restart.
        for _ in range(2):
            subprocess.run([sys.executable, str(SCRIPT), "--root", str(dbroot)], check=True)
        assert_expected_schema(dbroot)

        # The no-argument contract must materialize the owner-directed canonical data/ path,
        # not the superseded databases/ path.
        subprocess.run([sys.executable, str(SCRIPT)], cwd=td_path, check=True)
        canonical_root = td_path / "data"
        assert_expected_schema(canonical_root)
        assert not (td_path / "databases").exists(), "superseded databases/ default reappeared"

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

    print("PASS: telemetry initializer idempotence, canonical data/ default, schema presence, FIXED fail-closed gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
