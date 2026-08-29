from __future__ import annotations
import sqlite3, hashlib, json
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS operations(
    operation_retry_id TEXT PRIMARY KEY,
    operation_payload_sha256 TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('UNRESOLVED','VERIFIED_APPLIED','VERIFIED_NOT_APPLIED')),
    first_attempt_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts(
    attempt_id TEXT PRIMARY KEY,
    operation_retry_id TEXT NOT NULL,
    disposition TEXT NOT NULL,
    FOREIGN KEY(operation_retry_id) REFERENCES operations(operation_retry_id)
);
CREATE TABLE IF NOT EXISTS child_mutations(
    mutation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_retry_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL
);
"""

def payload_sha(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()

def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn

def attempt(conn, *, operation_retry_id: str, attempt_id: str, payload: dict) -> dict:
    psha = payload_sha(payload)
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT operation_payload_sha256,state,first_attempt_id FROM operations WHERE operation_retry_id=?",
            (operation_retry_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO operations(operation_retry_id,operation_payload_sha256,state,first_attempt_id) VALUES(?,?,?,?)",
                (operation_retry_id, psha, "UNRESOLVED", attempt_id),
            )
            conn.execute(
                "INSERT INTO attempts(attempt_id,operation_retry_id,disposition) VALUES(?,?,?)",
                (attempt_id, operation_retry_id, "DISPATCH_ALLOWED"),
            )
            # Deterministic zero-real-effect proxy for crossing the child-dispatch boundary.
            conn.execute(
                "INSERT INTO child_mutations(operation_retry_id,attempt_id) VALUES(?,?)",
                (operation_retry_id, attempt_id),
            )
            conn.commit()
            return {"disposition":"DISPATCH_ALLOWED","child_mutation":1,"payload_sha256":psha}
        existing_sha, state, _first_attempt_id = row
        if existing_sha != psha:
            conn.execute(
                "INSERT INTO attempts(attempt_id,operation_retry_id,disposition) VALUES(?,?,?)",
                (attempt_id, operation_retry_id, "REJECT_PAYLOAD_MISMATCH"),
            )
            conn.commit()
            return {"disposition":"REJECT_PAYLOAD_MISMATCH","child_mutation":0,"payload_sha256":psha}
        if state == "UNRESOLVED":
            conn.execute(
                "INSERT INTO attempts(attempt_id,operation_retry_id,disposition) VALUES(?,?,?)",
                (attempt_id, operation_retry_id, "DENY_DUPLICATE_UNRESOLVED"),
            )
            conn.commit()
            return {"disposition":"DENY_DUPLICATE_UNRESOLVED","child_mutation":0,"payload_sha256":psha}
        conn.execute(
            "INSERT INTO attempts(attempt_id,operation_retry_id,disposition) VALUES(?,?,?)",
            (attempt_id, operation_retry_id, "REJECT_VERIFIED_STATE_OUT_OF_SCOPE"),
        )
        conn.commit()
        return {"disposition":"REJECT_VERIFIED_STATE_OUT_OF_SCOPE","child_mutation":0,"payload_sha256":psha}
    except:
        conn.rollback()
        raise

def child_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM child_mutations").fetchone()[0]

def run(path: Path) -> dict:
    if path.exists():
        path.unlink()
    payload = {"capability":"exec","target":"noop-fixture","argv":["fixture","alpha"]}
    changed = {"capability":"exec","target":"noop-fixture","argv":["fixture","BETA"]}

    c1 = open_db(path)
    r1 = attempt(c1, operation_retry_id="op-A", attempt_id="attempt-A1", payload=payload)
    count_after_first = child_count(c1)
    c1.close()

    c2 = open_db(path)
    r2 = attempt(c2, operation_retry_id="op-A", attempt_id="attempt-A2", payload=payload)
    count_after_restart_duplicate = child_count(c2)
    r3 = attempt(c2, operation_retry_id="op-A", attempt_id="attempt-A3", payload=changed)
    count_after_payload_mismatch = child_count(c2)
    r4 = attempt(c2, operation_retry_id="op-B", attempt_id="attempt-B1", payload=payload)
    count_after_distinct_operation = child_count(c2)
    attempts = c2.execute("SELECT attempt_id,operation_retry_id,disposition FROM attempts ORDER BY rowid").fetchall()
    operations = c2.execute("SELECT operation_retry_id,operation_payload_sha256,state,first_attempt_id FROM operations ORDER BY operation_retry_id").fetchall()
    c2.close()

    checks = {
        "first_attempt_dispatches_once": r1["disposition"] == "DISPATCH_ALLOWED" and count_after_first == 1,
        "same_operation_after_reopen_dispatches_zero_children": r2["disposition"] == "DENY_DUPLICATE_UNRESOLVED" and count_after_restart_duplicate == 1,
        "same_operation_changed_payload_rejects_pre_dispatch": r3["disposition"] == "REJECT_PAYLOAD_MISMATCH" and count_after_payload_mismatch == 1,
        "intentional_identical_semantics_distinct_operation_is_admissible": r4["disposition"] == "DISPATCH_ALLOWED" and count_after_distinct_operation == 2,
    }
    return {
        "schema":"R6_WP105_E3_RETRY_FENCE_MINIATURE_RESULT/v1",
        "checks":checks,
        "pass":all(checks.values()),
        "results":{"first":r1,"restart_duplicate":r2,"payload_mismatch":r3,"distinct_operation":r4},
        "counts":{"after_first":count_after_first,"after_restart_duplicate":count_after_restart_duplicate,"after_payload_mismatch":count_after_payload_mismatch,"after_distinct_operation":count_after_distinct_operation},
        "attempt_rows":[list(x) for x in attempts],
        "operation_rows":[list(x) for x in operations],
    }

if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1] if len(sys.argv) > 1 else "r6_wp105_retry_fence.sqlite")
    print(json.dumps(run(p), indent=2, sort_keys=True))
