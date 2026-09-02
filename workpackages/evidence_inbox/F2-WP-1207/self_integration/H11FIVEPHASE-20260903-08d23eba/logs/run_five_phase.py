#!/usr/bin/env python3
"""H11 five-phase continuous recovery-latency run, F2-WP-1207.

RUN_ID = H11FIVEPHASE-20260903-08d23eba

Purpose (H11 in INTEGRATION_HYPOTHESES.md): "Recovery latency can be decomposed
into detection -> rollback begin -> rollback end -> process re-entry -> healthy
readback." Every prior run (SELFINT-20260901-a1c9e2f4, PHASE13-20260901) only
ever reported 2 phases as real, distinct timings, and even those two
(`failure_detection_ms` / `rollback_duration_ms` in
`self_update_transaction.apply_transaction`'s injected `post_mutation` path)
are NOT independent: `failure_detection_ms` there is measured from the same
`detection_start` timer all the way through the rollback restore AND the
post-restore digest verify AND the `record_attempt` receipt call, so it
STRUCTURALLY CONTAINS `rollback_duration_ms` rather than being a sibling of it.
No run ever separated "the mismatch was noticed" from "the bytes were
restored" from "a fresh process saw the healthy state" from "the fresh
readback itself completed", all inside one continuous timed sequence.

This script closes the gap the document itself named as the safe next step
(INTEGRATION_HYPOTHESES.md, "H6 (further) / H11 (closing) on the real,
current v1 harness specifically"): "a continuous 5-phase timing run entirely
inside the existing disposable self_update_transaction.py sandbox, no live
process contact at all". It does NOT touch any live v1 harness / Claude Code
process. It only imports the two already-ACCEPTED, already-used primitives
(`frankenstein2.portable_release_transaction`,
`frankenstein2.self_update_transaction`) and never forks or edits either
module -- exactly the same non-modification discipline the original
SELFINT-20260901-a1c9e2f4 run and its `run_gates.py` driver used.

Design of the 5 phases (all measured with `time.monotonic()`, all real work,
none fabricated):

  1. detection_ms       -- compute_state_digest() over the managed_dir after a
                            genuinely corrupted on-disk mutation, compared
                            against the expected manifest digest for the
                            update that was supposed to have landed. This is
                            the SAME comparison self_update_transaction's own
                            (non-injected-flag) verify branch performs
                            ("observed_state != _manifest_digest(manifest)")
                            -- real hashing work over real files, not a
                            synthetic near-zero flag check.
  2. rollback_duration_ms -- store._restore_snapshot(healthy_generation), i.e.
                            the exact same private method self_update_
                            transaction.py itself calls for its own recovery
                            paths. Timed strictly from immediately before the
                            call ("rollback begin") to immediately after it
                            returns ("rollback end") -- nothing else inside
                            that window.
  3. reentry_ms          -- wall time from the parent issuing
                            subprocess.Popen(...) for a genuinely fresh
                            `python3` process to the parent reading that
                            child's first stdout line (an "ALIVE" marker
                            flushed as the very first statement the child
                            executes, before it even imports frankenstein2).
                            This is a real OS process-spawn/exec/interpreter-
                            startup cost, not a synthetic value.
  4. readback_ms         -- timed INSIDE the child, strictly around the
                            `independent_readback(managed_dir, control_dir)`
                            call itself (the same function P7 used in the
                            original run, invoked from a genuinely separate
                            process exactly as its own docstring requires).

  A ROLLED_BACK receipt is still minted via the accepted primitive's own
  `record_attempt` (using the same request/plan construction
  self_update_transaction.py uses), so the run's recovery event is provable
  against the same accepted receipt schema as every other run -- but the
  receipt-mint call itself is measured OUTSIDE phases 1-2 (reported
  separately as `receipt_mint_ms`, disclosed, not hidden inside detection or
  rollback) so it cannot inflate either of those two numbers the way the old
  combined `failure_detection_ms` silently did.

Sandbox contract: managed_dir/control_dir live under a disposable
/tmp/h11fivephase-<run_id>/ directory this script creates and never anything
under ~/.claude. No live process (v1 harness, real Claude Code CLI) is
touched, signalled, or spawned -- the only subprocess spawned is this
script's own throwaway `python3 -c "..."` reader for phase 3/4.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/ai-core-node/frankenstein-2.0/src")

from frankenstein2.portable_release_transaction import (  # noqa: E402
    build_transaction_plan,
    record_attempt,
)
from frankenstein2.self_update_transaction import (  # noqa: E402
    SelfUpdateStore,
    apply_transaction,
    compute_state_digest,
    independent_readback,
    release_identity_for_payload,
)

RUN_ID = "H11FIVEPHASE-20260903-08d23eba"
RUN_DIR = Path(f"/tmp/h11fivephase-{RUN_ID}")
MANAGED_DIR = RUN_DIR / "sandbox-claude"
CONTROL_DIR = RUN_DIR / "control-claude"
EVIDENCE_DIR = Path(
    "/home/ai-core-node/frankenstein-2.0/workpackages/evidence_inbox/"
    "F2-WP-1207/self_integration/H11FIVEPHASE-20260903-08d23eba"
)
MEASUREMENTS_PATH = EVIDENCE_DIR / "measurements.jsonl"
REPO_DIR = Path("/home/ai-core-node/frankenstein-2.0")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_DIR, capture_output=True, text=True, timeout=30,
    ).stdout.strip()


REPO_HEAD_SHA = _git("rev-parse", "HEAD")
REPO_DIRTY = bool(_git("status", "--porcelain"))

if RUN_DIR.exists():
    shutil.rmtree(RUN_DIR)
RUN_DIR.mkdir(parents=True)

store = SelfUpdateStore(managed_dir=MANAGED_DIR, control_dir=CONTROL_DIR)

phases: dict[str, float] = {}
timeline: list[dict] = []


def _mark(label: str, ts: float) -> None:
    timeline.append({"label": label, "monotonic": ts})


# --------------------------------------------------------------- setup (not a phase)
# INSTALL gen1 (baseline) then UPDATE gen2 (the "healthy" state this run will
# corrupt-and-recover to). Neither is timed as one of the 5 named phases --
# this is ordinary setup identical in spirit to SELFINT's P5.
payload_v0 = {"settings.json": b'{"schema":"h11fivephase-v0"}\n', "commands/noop.md": b"# noop\n"}
apply_transaction(
    store, operation="INSTALL", payload=payload_v0,
    release_id="h11fivephase-sandbox", version="r0-baseline",
    attempt_id=f"{RUN_ID}-install-1",
)

payload_healthy = dict(payload_v0)
payload_healthy["settings.json"] = b'{"schema":"h11fivephase-v1-healthy"}\n'
payload_healthy["watchdog/marker.txt"] = f"healthy generation for {RUN_ID}".encode("utf-8")
r_update = apply_transaction(
    store, operation="UPDATE", payload=payload_healthy,
    release_id="h11fivephase-sandbox", version="r1-healthy",
    attempt_id=f"{RUN_ID}-update-healthy-1",
)
healthy_lineage = store.load_lineage()
healthy_generation = healthy_lineage.generation
healthy_state_sha256 = healthy_lineage.state_sha256
assert healthy_state_sha256 == compute_state_digest(MANAGED_DIR)

# Build (pure validation, no mutation) the plan for the UPDATE that is about
# to be attempted and corrupted -- exactly what apply_transaction itself does
# before mutating. Used below to build the same ROLLED_BACK receipt the
# accepted primitive would mint.
target_release, manifest = release_identity_for_payload(
    payload_healthy, release_id="h11fivephase-sandbox", version="r2-attempted-bad"
)
# distinct payload for the doomed attempt (different bytes -> different manifest)
payload_bad = dict(payload_healthy)
payload_bad["settings.json"] = b'{"schema":"h11fivephase-v2-attempted"}\n'
target_release, manifest = release_identity_for_payload(
    payload_bad, release_id="h11fivephase-sandbox", version="r2-attempted-bad"
)
request = {
    "schema": "FRANKENSTEIN2_PORTABLE_RELEASE_TRANSACTION_REQUEST/v1",
    "attempt_id": f"{RUN_ID}-p6-bad-update-1",
    "operation": "UPDATE",
    "target_release": target_release.as_dict(),
    "current_lineage": healthy_lineage.as_dict(),
    "expected_generation": healthy_lineage.generation,
    "expected_state_sha256": healthy_lineage.state_sha256,
    "rollback_release": None,
    "injected_failure_stage": None,
}
plan = build_transaction_plan(request)

# --------------------------------------------------------------- fault injection (not a phase)
# Write the (structurally valid, plan-accepted) bad payload to disk, THEN
# corrupt one on-disk file directly (outside the payload dict) so the
# resulting bytes genuinely disagree with the manifest digest the plan
# validated against. This reproduces self_update_transaction.py's own
# non-injected-flag verify-mismatch branch ("observed_state !=
# _manifest_digest(manifest)") for real, rather than relying on the
# synthetic injected_failure_stage flag (whose "detection" is a no-op branch
# check, not real comparison work).
from frankenstein2.self_update_transaction import _write_payload  # noqa: E402

t_mutate_start = time.monotonic()
_write_payload(MANAGED_DIR, payload_bad)
(MANAGED_DIR / "watchdog" / "marker.txt").write_bytes(b"CORRUPTED-IN-FLIGHT-BYTES\x00\x01\x02")
t_mutate_end = time.monotonic()
mutation_ms = (t_mutate_end - t_mutate_start) * 1000.0

expected_manifest_digest = None  # computed lazily below via helper import
from frankenstein2.self_update_transaction import _manifest_digest  # noqa: E402
expected_manifest_digest = _manifest_digest(manifest)

# --------------------------------------------------------------- PHASE 1: detection
t0 = time.monotonic()
_mark("detection_start", t0)
observed_after_mutation = compute_state_digest(MANAGED_DIR)
mismatch_found = observed_after_mutation != expected_manifest_digest
t1 = time.monotonic()
_mark("detection_end", t1)
detection_ms = (t1 - t0) * 1000.0
assert mismatch_found, "fault injection did not actually produce a detectable digest mismatch"

# --------------------------------------------------------------- PHASE 2/3: rollback begin -> rollback end
t2 = time.monotonic()
_mark("rollback_begin", t2)
store._restore_snapshot(healthy_generation)
t3 = time.monotonic()
_mark("rollback_end", t3)
rollback_duration_ms = (t3 - t2) * 1000.0

restored_state_sha256 = compute_state_digest(MANAGED_DIR)
restore_matches_healthy = restored_state_sha256 == healthy_state_sha256

# Receipt mint (accepted primitive), measured but OUTSIDE phases 1/2 so it
# cannot silently inflate either of them the way the old combined
# failure_detection_ms did.
t_receipt_start = time.monotonic()
receipt = record_attempt(
    plan,
    outcome="ROLLED_BACK",
    observed_generation=plan.source_generation,
    observed_state_sha256=restored_state_sha256,
    failure_code="OBSERVED_DIGEST_MISMATCH",
)
t_receipt_end = time.monotonic()
receipt_mint_ms = (t_receipt_end - t_receipt_start) * 1000.0

# Lineage was never advanced for the doomed attempt (matches
# self_update_transaction.py's own semantics: a ROLLED_BACK receipt on an
# INSTALL/UPDATE plan does not call _save_lineage). Confirm that directly.
lineage_after_rollback = store.load_lineage()
lineage_unchanged_at_healthy_generation = (
    lineage_after_rollback.generation == healthy_generation
    and lineage_after_rollback.state_sha256 == healthy_state_sha256
)

# --------------------------------------------------------------- PHASE 4: process re-entry
child_code = f"""
import sys, time
print("ALIVE " + repr(time.monotonic()), flush=True)
sys.path.insert(0, "/home/ai-core-node/frankenstein-2.0/src")
from frankenstein2.self_update_transaction import independent_readback
import time as _time, json as _json
t_rb0 = _time.monotonic()
result = independent_readback({str(MANAGED_DIR)!r}, {str(CONTROL_DIR)!r})
t_rb1 = _time.monotonic()
print(_json.dumps({{
    "readback_start_monotonic": t_rb0,
    "readback_end_monotonic": t_rb1,
    "readback_ms": (t_rb1 - t_rb0) * 1000.0,
    "result": result,
}}), flush=True)
"""

t4_spawn = time.monotonic()
_mark("reentry_spawn", t4_spawn)
proc = subprocess.Popen(
    [sys.executable, "-c", child_code],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
)
first_line = proc.stdout.readline()
t5_alive = time.monotonic()
_mark("reentry_alive", t5_alive)
reentry_ms = (t5_alive - t4_spawn) * 1000.0

second_line = proc.stdout.readline()
stderr_tail = ""
returncode = proc.wait(timeout=30)
if proc.stderr:
    stderr_tail = proc.stderr.read()[-2000:]

child_ok = returncode == 0 and first_line.startswith("ALIVE") and bool(second_line.strip())
child_payload = json.loads(second_line) if child_ok else None

# --------------------------------------------------------------- PHASE 5: healthy readback
readback_ms = child_payload["readback_ms"] if child_payload else None
readback_result = child_payload["result"] if child_payload else None
lineage_matches_observed = (
    readback_result.get("lineage_matches_observed") if readback_result else None
)
readback_generation = (
    (readback_result.get("lineage") or {}).get("generation") if readback_result else None
)
readback_state_sha256 = (
    (readback_result.get("lineage") or {}).get("state_sha256") if readback_result else None
)
healthy_confirmed = (
    child_ok
    and lineage_matches_observed is True
    and readback_generation == healthy_generation
    and readback_state_sha256 == healthy_state_sha256
)

# --------------------------------------------------------------- write outputs
five_phase_record = {
    "schema": "F2_WP1207_H11_FIVE_PHASE_MEASUREMENT/v1",
    "run_id": RUN_ID,
    "repo_head_sha": REPO_HEAD_SHA,
    "repo_dirty": REPO_DIRTY,
    "continuous_single_run": True,
    "note": (
        "All 5 phases below were measured back-to-back inside one Python "
        "process execution of this script (plus one fresh child process for "
        "phases 4/5), never against a live v1 harness or real Claude Code "
        "process -- purely inside the disposable self_update_transaction.py "
        "sandbox, per INTEGRATION_HYPOTHESES.md's own proposed safe next step."
    ),
    "setup": {
        "healthy_generation": healthy_generation,
        "healthy_state_sha256": healthy_state_sha256,
        "mutation_ms_not_a_named_phase": round(mutation_ms, 4),
        "mismatch_genuinely_detected": mismatch_found,
    },
    "phases": {
        "1_detection_ms": round(detection_ms, 4),
        "2_3_rollback_begin_to_rollback_end_ms": round(rollback_duration_ms, 4),
        "4_process_reentry_ms": round(reentry_ms, 4),
        "5_healthy_readback_ms": round(readback_ms, 4) if readback_ms is not None else None,
    },
    "disclosed_but_not_one_of_the_5_named_phases": {
        "receipt_mint_ms": round(receipt_mint_ms, 4),
        "reason": (
            "record_attempt's ROLLED_BACK receipt mint is real accepted-primitive "
            "work, but H11 names exactly 5 phases (detection, rollback begin, "
            "rollback end, re-entry, readback) and receipt-minting is not one of "
            "them; the OLD combined failure_detection_ms silently absorbed an "
            "equivalent cost into 'detection' -- this run keeps it visible and "
            "separate instead of hiding it inside phase 1."
        ),
    },
    "correctness_checks": {
        "restore_matches_healthy_state": restore_matches_healthy,
        "lineage_unchanged_at_healthy_generation_after_rollback": lineage_unchanged_at_healthy_generation,
        "receipt_outcome": receipt.outcome,
        "child_subprocess_ok": child_ok,
        "child_subprocess_returncode": returncode,
        "child_stderr_tail_or_empty": stderr_tail,
        "lineage_matches_observed_in_fresh_process": lineage_matches_observed,
        "readback_generation_matches_healthy": readback_generation == healthy_generation,
        "readback_state_matches_healthy": readback_state_sha256 == healthy_state_sha256,
        "healthy_readback_confirmed": healthy_confirmed,
    },
    "raw_timeline_monotonic": timeline,
}

EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
MEASUREMENTS_PATH.write_text(
    json.dumps(five_phase_record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)

print(json.dumps(five_phase_record, ensure_ascii=False, sort_keys=True, indent=2))

if not (
    restore_matches_healthy
    and lineage_unchanged_at_healthy_generation
    and healthy_confirmed
):
    sys.exit(1)
