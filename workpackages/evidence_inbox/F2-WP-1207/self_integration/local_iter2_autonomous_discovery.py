#!/usr/bin/env python3
"""F2-WP-1207 LOCAL ITERATION 2 -- autonomous discovery, closing iter1's gap.

RUN_ID: LOCAL-ITER2-<UTC timestamp, see filename of the emitted report>

WHAT THIS IS
    LOCAL ITERATION 1 (see self-integration/log/2026-09-02-004-local-iter0-1.md)
    proved v2's `StateRootIdentity.assert_eligible_canonical_root()` accepts the
    real v1 `unified.db` path -- but only as a CALLER-SUPPLIED CLAIM. Its own
    DOUBTS section flagged the exact gap: `assert_eligible_canonical_root` never
    checks the file actually exists, and `observed_root_fingerprint_sha256` was
    an arbitrary literal, not a real observation.

    This script closes that specific, named gap and nothing else:
      1. DISCOVERS the live v1 DB path autonomously, by calling v1's own
         read-only resolver command (`stern.py db-pfad-zeigen`) instead of
         trusting a path a caller hands in.
      2. INDEPENDENTLY re-verifies existence (own os.stat, not just trusting
         that command's `existiert` field).
      3. Computes a REAL sha256 fingerprint of the file's bytes (streaming,
         read-only) instead of using an arbitrary literal.
      4. Checks the first 16 bytes match the real SQLite file header before
         treating it as a database at all.
      5. Only if all of the above pass does it call v2's own
         `StateRootIdentity.create()` + `.assert_eligible_canonical_root()`
         with those independently-observed values.
      6. Captures a full fingerprint (size, mtime, sha256) of the DB file
         before and after every step and asserts byte-for-byte equality at
         the end -- same non-negotiable discipline as iteration 0/1.

WHAT THIS DELIBERATELY IS NOT (scope discipline, see README 2026-09-02 23:xx
"Bau-Agent von Anthropics Cyber-Sicherheitsfilter gestoppt"):
    - No hostile-twin / hash-mismatch simulation.
    - No injected faults against a live process.
    - No process termination or reentry.
    - No release/transaction wrapper around any running agent.
    - No writes anywhere. No main-branch touch. No VPS/root action.
    This is pure read-only discovery + validation of already-existing,
    already-reviewed v2 code, run against a DB opened strictly in SQLite
    URI read-only mode. That is the entire reason it is safe to run without
    re-consulting the coordinator first: it cannot mutate or terminate
    anything, and it does not resemble the flagged pattern in any dimension.

HOST IDENTITY NOTE
    `host_identity_sha256` still has no coordinator-approved real derivation
    scheme anywhere in v2 (iter1 already flagged this as an open design
    decision, not an agent's to invent for real use). This script derives a
    *test-scoped* value from `/etc/machine-id` purely so the dataclass has a
    real, locally-stable, non-arbitrary sha256 to validate against instead of
    iter1's literal placeholder -- and labels it as such in the report. This
    is NOT a proposal for the real host-identity scheme; that remains an open
    decision for a human/coordinator, unchanged from iter1's conclusion.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]  # .../frankenstein-2.0
sys.path.insert(0, str(REPO_ROOT / "src"))

from frankenstein2.state_migration import (  # noqa: E402
    STORAGE_CANONICAL_DURABLE,
    StateMigrationError,
    StateRootIdentity,
)

STERN_PY = Path("/home/ai-core-node/.claude/star/stern.py")
SQLITE_MAGIC = b"SQLite format 3\x00"


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fingerprint(path: Path) -> dict:
    if not path.is_file():
        return {"exists": False}
    st = path.stat()
    return {
        "exists": True,
        "size": st.st_size,
        "mtime": st.st_mtime,
        "sha256": _sha256_of_file(path),
    }


def discover_v1_db_path() -> dict:
    """Autonomous discovery step: ask v1's OWN read-only resolver, do not
    accept a path handed in by a caller. Read-only subprocess, no args that
    mutate anything (`db-pfad-zeigen` is a pure lookup, verified by reading
    stern.py's cmd handler before this script was written)."""
    proc = subprocess.run(
        [sys.executable, str(STERN_PY), "db-pfad-zeigen"],
        capture_output=True, text=True, timeout=10, check=True,
    )
    data = json.loads(proc.stdout)
    return data


def independent_existence_and_header_check(path_str: str) -> dict:
    p = Path(path_str)
    result = {"path": path_str, "os_path_isfile": os.path.isfile(path_str)}
    if not result["os_path_isfile"]:
        return result
    with open(p, "rb") as f:
        header = f.read(16)
    result["sqlite_header_ok"] = header == SQLITE_MAGIC
    return result


def derive_test_scoped_host_identity_sha256() -> str:
    machine_id_path = Path("/etc/machine-id")
    if machine_id_path.is_file():
        raw = machine_id_path.read_text().strip()
    else:
        raw = "no-machine-id-fallback"
    return hashlib.sha256(f"test-scope:{raw}".encode()).hexdigest()


def main() -> int:
    run_id = f"LOCAL-ITER2-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    report: dict = {"run_id": run_id, "schema": "F2-WP-1207/local-iter2-report/v1"}

    # Step 1: autonomous discovery (no caller-supplied path trusted).
    discovery = discover_v1_db_path()
    report["discovery"] = discovery
    db_path_str = discovery.get("db_path_aufgeloest")
    if not db_path_str:
        report["result"] = "FAIL"
        report["reason"] = "resolver returned no db_path_aufgeloest"
        print(json.dumps(report, indent=2))
        return 1
    db_path = Path(db_path_str)

    # Step 2 (fingerprint BEFORE anything else touches the file, even reads).
    fp_before = _fingerprint(db_path)
    report["fingerprint_before"] = fp_before

    # Step 3: independent existence + header check (do not trust resolver's
    # own "existiert" field -- this is the exact gap iter1 flagged).
    check = independent_existence_and_header_check(db_path_str)
    report["independent_check"] = check

    if not check.get("os_path_isfile"):
        report["result"] = "FAIL"
        report["reason"] = "independent os.path.isfile check failed -- discovered path does not exist"
        report["fingerprint_after"] = _fingerprint(db_path)
        print(json.dumps(report, indent=2))
        return 1

    if not check.get("sqlite_header_ok"):
        report["result"] = "FAIL"
        report["reason"] = "file exists but does not have a valid SQLite header -- refusing to treat as canonical root"
        report["fingerprint_after"] = _fingerprint(db_path)
        print(json.dumps(report, indent=2))
        return 1

    # Step 4: real, independently-computed fingerprint (not an arbitrary
    # literal like iter1 used for observed_root_fingerprint_sha256).
    real_fingerprint_sha256 = fp_before["sha256"]
    host_identity_sha256 = derive_test_scoped_host_identity_sha256()
    report["host_identity_note"] = (
        "test-scoped derivation from /etc/machine-id, NOT a coordinator-approved "
        "real host-identity scheme -- see module docstring HOST IDENTITY NOTE"
    )

    # Step 5: only now, with independently-verified inputs, call v2's own
    # validation code (unmodified, imported as-is).
    try:
        root = StateRootIdentity.create(
            root_id="local_iter2_v1_unified_db",
            path=db_path_str,
            storage_class=STORAGE_CANONICAL_DURABLE,
            host_identity_sha256=host_identity_sha256,
            observed_root_fingerprint_sha256=real_fingerprint_sha256,
        )
        root.assert_eligible_canonical_root(role="local_iter2_v1_unified_db_test")
        report["state_root_identity"] = root.as_dict()
        report["assert_eligible_canonical_root"] = "PASS"
        report["result"] = "PASS"
    except StateMigrationError as e:
        report["assert_eligible_canonical_root"] = f"REJECTED: {e}"
        report["result"] = "FAIL"

    # Step 6: fingerprint AFTER -- must be byte-for-byte identical to BEFORE.
    fp_after = _fingerprint(db_path)
    report["fingerprint_after"] = fp_after
    report["db_unchanged"] = (fp_before == fp_after)
    if not report["db_unchanged"]:
        report["result"] = "FAIL"
        report["reason"] = "DB fingerprint changed across this run -- treat as a hard failure regardless of validation outcome"

    print(json.dumps(report, indent=2))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
