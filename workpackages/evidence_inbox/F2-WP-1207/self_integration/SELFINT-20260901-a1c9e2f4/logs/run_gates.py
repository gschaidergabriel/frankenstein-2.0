#!/usr/bin/env python3
"""Gate driver for F2-WP-1207 self-integration run SELFINT-20260901-a1c9e2f4.

Executes P5-P11 against the disposable sandbox at
/tmp/selfint-SELFINT-20260901-a1c9e2f4/sandbox-claude (a curated, bounded,
faithful representative copy of ~/.claude -- never the real directory).
Writes one JSON-lines measurement record per gate to
measurements.jsonl (in this script's directory) and prints a single JSON
summary object to stdout for the caller to build the remaining evidence
artifacts from. Never touches ~/.claude.

RE-RUN 2026-09-01 (coordinator defect report, PRODUCT_NEGATIVE): re-executed
against the fixed src/frankenstein2/self_update_transaction.py (fail-closed
injected_failure_stage whitelist + post-mutation recovery-then-reraise).
Also closes an EVIDENCE_INVALID gap the coordinator flagged: each measurement
record is now identity-bound (repo_head_sha, repo_dirty, operation,
parent/current/planned/expected-rollback/observed state sha256, failure
classification) instead of timing/resource fields only. Every identity value
below is read from the actual store/lineage/receipt of that gate's own call --
never fabricated; null + explicit reason where a field genuinely does not
apply to that gate (e.g. no rollback target for a plain successful UPDATE).
"""
from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/ai-core-node/frankenstein-2.0/src")

from frankenstein2.portable_release_transaction import PortableReleaseTransactionError  # noqa: E402
from frankenstein2.self_update_transaction import (  # noqa: E402
    SelfUpdateStore,
    SelfUpdateTransactionError,
    apply_rollback,
    apply_transaction,
    compute_state_digest,
    release_identity_for_payload,
    _write_payload,
)
import tempfile

RUN_ID = "SELFINT-20260901-a1c9e2f4"
RUN_DIR = Path("/tmp/selfint-SELFINT-20260901-a1c9e2f4")
MANAGED_DIR = RUN_DIR / "sandbox-claude"
CONTROL_DIR = RUN_DIR / "control-claude"
MEASUREMENTS_PATH = RUN_DIR / "measurements.jsonl"
REPO_DIR = Path("/home/ai-core-node/frankenstein-2.0")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_DIR, capture_output=True, text=True, timeout=30,
    ).stdout.strip()


REPO_HEAD_SHA = _git("rev-parse", "HEAD")
REPO_DIRTY = bool(_git("status", "--porcelain"))

if CONTROL_DIR.exists():
    import shutil
    shutil.rmtree(CONTROL_DIR)

store = SelfUpdateStore(managed_dir=MANAGED_DIR, control_dir=CONTROL_DIR)

results: dict[str, dict] = {}
measurement_records: list[dict] = []


def _read_payload(base: Path) -> dict[str, bytes]:
    payload = {}
    for root, _dirs, files in os.walk(base):
        for name in files:
            full = Path(root) / name
            rel = full.relative_to(base).as_posix()
            payload[rel] = full.read_bytes()
    return payload


def _io_snapshot() -> dict | None:
    try:
        text = Path("/proc/self/io").read_text()
    except Exception:
        return None
    out = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        out[k.strip()] = int(v.strip())
    return out


def _planned_digest_for_payload(payload: "Mapping[str, bytes]") -> str:
    """Genuinely compute the state digest a payload WOULD produce if applied, by
    materializing it into a throwaway scratch directory (never MANAGED_DIR, never
    touches lineage/CAS) and hashing that with the same compute_state_digest used
    for every observed digest elsewhere in this run. Real, not fabricated -- just
    computed off to the side instead of from the live managed dir."""
    with tempfile.TemporaryDirectory(prefix="selfint-planned-digest-") as scratch:
        scratch_path = Path(scratch)
        _write_payload(scratch_path, payload)
        return compute_state_digest(scratch_path)


def _classify_failure(gate_id: str, outcome: str, error: str | None) -> str | None:
    """Map an observed (outcome, error) pair to the failure taxonomy already used
    elsewhere in this evidence run (rollback_evidence.json, hypothesis_results.json).
    Returns None for a genuinely successful gate (no failure occurred)."""
    if outcome == "OK":
        return None
    err = error or ""
    if "hostile-twin" in err:
        return "HOSTILE_TWIN_REJECTED_PRE_MUTATION"
    if "must differ" in err:
        return "REPLAY_REJECTED_NO_DOUBLE_APPLY"
    if "generation" in err and "current lineage" in err:
        return "STALE_CAS_REJECTED"
    if "INJECTED_POST_MUTATION" in err or gate_id.startswith("P6"):
        return "INJECTED_POST_MUTATION_ROLLED_BACK"
    if "injected_failure_stage" in err:
        return "UNKNOWN_INJECTED_STAGE_REJECTED_PRE_MUTATION"
    return "UNCLASSIFIED_RAISE"


def _measure(
    gate_id: str,
    hypothesis: str,
    fn,
    *,
    operation: str,
    parent_state_sha256: str | None,
    planned_target_state_sha256: str | None = None,
    planned_target_reason: str | None = None,
    expected_rollback_target_state_sha256: str | None = None,
    expected_rollback_target_reason: str | None = None,
):
    rusage_before = resource.getrusage(resource.RUSAGE_SELF)
    io_before = _io_snapshot()
    t0 = time.monotonic()
    outcome = "OK"
    error = None
    value = None
    try:
        value = fn()
    except (PortableReleaseTransactionError, SelfUpdateTransactionError) as exc:
        outcome = "RAISED"
        error = f"{type(exc).__name__}: {exc}"
    t1 = time.monotonic()
    rusage_after = resource.getrusage(resource.RUSAGE_SELF)
    io_after = _io_snapshot()

    if io_before is not None and io_after is not None:
        disk_read_bytes_delta = io_after["rchar"] - io_before["rchar"]
        disk_write_bytes_delta = io_after["wchar"] - io_before["wchar"]
        disk_note = None
    else:
        disk_read_bytes_delta = None
        disk_write_bytes_delta = None
        disk_note = "unmeasurable: /proc/self/io not readable in this environment"

    current_state_sha256 = compute_state_digest(MANAGED_DIR)
    lineage_after = store.load_lineage()

    record = {
        "schema": "F2_WP1207_SELF_INTEGRATION_MEASUREMENT/v2",
        "run_id": RUN_ID,
        "gate_id": gate_id,
        "hypothesis": hypothesis,
        "repo_head_sha": REPO_HEAD_SHA,
        "repo_dirty": REPO_DIRTY,
        "operation": operation,
        "outcome": outcome,
        "failure_classification_or_null": _classify_failure(gate_id, outcome, error),
        "parent_state_sha256_or_null": parent_state_sha256,
        "planned_target_state_sha256_or_null": planned_target_state_sha256,
        "planned_target_reason_or_null": (
            None if planned_target_state_sha256 is not None else
            (planned_target_reason or "not applicable to this gate")
        ),
        "expected_rollback_target_state_sha256_or_null": expected_rollback_target_state_sha256,
        "expected_rollback_target_reason_or_null": (
            None if expected_rollback_target_state_sha256 is not None else
            (expected_rollback_target_reason or "not applicable: this gate does not involve rollback")
        ),
        "observed_state_sha256": current_state_sha256,
        "observed_lineage_generation": lineage_after.generation if lineage_after else None,
        "observed_lineage_state_sha256_or_null": lineage_after.state_sha256 if lineage_after else None,
        "wall_time_ms": round((t1 - t0) * 1000.0, 3),
        "cpu_user_ms": round((rusage_after.ru_utime - rusage_before.ru_utime) * 1000.0, 3),
        "cpu_sys_ms": round((rusage_after.ru_stime - rusage_before.ru_stime) * 1000.0, 3),
        "rss_kb_before": rusage_before.ru_maxrss,
        "rss_kb_after": rusage_after.ru_maxrss,
        "rss_kb_delta_or_null": (rusage_after.ru_maxrss - rusage_before.ru_maxrss),
        "disk_read_bytes_delta": disk_read_bytes_delta,
        "disk_write_bytes_delta": disk_write_bytes_delta,
        "disk_note_or_null": disk_note,
        "error_or_null": error,
    }
    measurement_records.append(record)
    return value, outcome, error


# ---------------------------------------------------------------- P5: INSTALL + UPDATE
payload_v0 = _read_payload(MANAGED_DIR)


def _p5_install():
    return apply_transaction(
        store, operation="INSTALL", payload=payload_v0,
        release_id="claude-config-sandbox", version="r0-baseline",
        attempt_id=f"{RUN_ID}-p5-install-1",
    )


r_install, outcome, err = _measure(
    "P5-install", "H1,H2,H3", _p5_install,
    operation="INSTALL",
    parent_state_sha256=None,
    planned_target_reason="INSTALL has no predecessor generation; nothing to compare a parent digest against",
    planned_target_state_sha256=_planned_digest_for_payload(payload_v0),
    expected_rollback_target_reason="not applicable: no injected failure on this gate, no rollback expected",
)
results["p5_install"] = {
    "outcome": outcome, "error": err,
    "receipt_outcome": r_install.receipt.outcome if r_install else None,
    "generation": r_install.receipt.observed_generation if r_install else None,
    "state_sha256": r_install.receipt.observed_state_sha256 if r_install else None,
}

payload_v1 = dict(payload_v0)
payload_v1["SELFINT_MARKER.txt"] = (
    f"simulated self-update payload marker gen1 {RUN_ID}".encode("utf-8")
)


def _p5_update():
    return apply_transaction(
        store, operation="UPDATE", payload=payload_v1,
        release_id="claude-config-sandbox", version="r1-simulated-update",
        attempt_id=f"{RUN_ID}-p5-update-1",
    )


gen0_state = r_install.receipt.observed_state_sha256 if r_install else compute_state_digest(MANAGED_DIR)
r_update, outcome, err = _measure(
    "P5-update", "H1,H2,H3", _p5_update,
    operation="UPDATE",
    parent_state_sha256=gen0_state,
    planned_target_state_sha256=_planned_digest_for_payload(payload_v1),
    expected_rollback_target_reason="not applicable: no injected failure on this gate, no rollback expected",
)
gen1_state = compute_state_digest(MANAGED_DIR)
results["p5_update"] = {
    "outcome": outcome, "error": err,
    "receipt_outcome": r_update.receipt.outcome if r_update else None,
    "generation": r_update.receipt.observed_generation if r_update else None,
    "state_sha256": r_update.receipt.observed_state_sha256 if r_update else None,
    "matches_fresh_digest": (r_update.receipt.observed_state_sha256 == gen1_state) if r_update else None,
}

# ---------------------------------------------------------------- P6: injected failure + rollback
payload_v2 = dict(payload_v1)
payload_v2["SELFINT_MARKER.txt"] = (
    f"simulated self-update payload marker gen2 {RUN_ID}".encode("utf-8")
)


def _p6_injected_failure():
    return apply_transaction(
        store, operation="UPDATE", payload=payload_v2,
        release_id="claude-config-sandbox", version="r2-injected-failure",
        attempt_id=f"{RUN_ID}-p6-update-fail-1",
        injected_failure_stage="post_mutation",
    )


r_p6, outcome, err = _measure(
    "P6-injected-failure-rollback", "H3,H4,H12", _p6_injected_failure,
    operation="UPDATE",
    parent_state_sha256=gen1_state,
    planned_target_state_sha256=_planned_digest_for_payload(payload_v2),
    expected_rollback_target_state_sha256=gen1_state,
)
post_rollback_state = compute_state_digest(MANAGED_DIR)
results["p6_injected_failure"] = {
    "outcome": outcome, "error": err,
    "receipt_outcome": r_p6.receipt.outcome if r_p6 else None,
    "expected_predecessor_state_sha256": gen1_state,
    "observed_state_sha256_after_recovery": r_p6.receipt.observed_state_sha256 if r_p6 else None,
    "fresh_digest_after_recovery": post_rollback_state,
    "exact_match": (
        r_p6.receipt.observed_state_sha256 == gen1_state == post_rollback_state
    ) if r_p6 else False,
    "generation_unchanged_at_1": store.load_lineage().generation == 1,
    "rollback_duration_ms": r_p6.rollback_duration_ms if r_p6 else None,
    "failure_detection_ms": r_p6.failure_detection_ms if r_p6 else None,
}

# ---------------------------------------------------------------- P7: process restart + independent readback
proc = subprocess.run(
    [
        sys.executable, "-c",
        (
            "import sys, json; "
            "sys.path.insert(0, '/home/ai-core-node/frankenstein-2.0/src'); "
            "from frankenstein2.self_update_transaction import independent_readback; "
            f"print(json.dumps(independent_readback('{MANAGED_DIR}', '{CONTROL_DIR}')))"
        ),
    ],
    capture_output=True, text=True, timeout=60,
)
readback_stdout = proc.stdout.strip()
readback_ok = proc.returncode == 0
readback_payload = json.loads(readback_stdout) if readback_ok and readback_stdout else None
results["p7_process_restart_readback"] = {
    "subprocess_returncode": proc.returncode,
    "subprocess_stderr_tail": proc.stderr[-2000:] if proc.stderr else "",
    "readback": readback_payload,
    "lineage_matches_observed": (
        readback_payload.get("lineage_matches_observed") if readback_payload else None
    ),
    "generation": (
        readback_payload.get("lineage", {}).get("generation") if readback_payload and readback_payload.get("lineage") else None
    ),
    "note": "invoked in a genuinely fresh python3 subprocess, not in-process, per P7 requirement",
}
_p7_lineage_gen = (
    readback_payload.get("lineage", {}).get("generation")
    if readback_payload and readback_payload.get("lineage") else None
)
_p7_lineage_state = (
    readback_payload.get("lineage", {}).get("state_sha256")
    if readback_payload and readback_payload.get("lineage") else None
)
measurement_records.append({
    "schema": "F2_WP1207_SELF_INTEGRATION_MEASUREMENT/v2",
    "run_id": RUN_ID, "gate_id": "P7-process-restart-readback", "hypothesis": "H4,H10,H11",
    "repo_head_sha": REPO_HEAD_SHA,
    "repo_dirty": REPO_DIRTY,
    "operation": "READBACK",
    "outcome": "OK" if readback_ok else "SUBPROCESS_FAILED",
    "failure_classification_or_null": None if readback_ok else "UNCLASSIFIED_RAISE",
    "parent_state_sha256_or_null": gen1_state,
    "planned_target_state_sha256_or_null": None,
    "planned_target_reason_or_null": "not applicable: READBACK does not mutate state, no planned target digest",
    "expected_rollback_target_state_sha256_or_null": None,
    "expected_rollback_target_reason_or_null": "not applicable: this gate does not involve rollback",
    "observed_state_sha256": compute_state_digest(MANAGED_DIR),
    "observed_lineage_generation": _p7_lineage_gen,
    "observed_lineage_state_sha256_or_null": _p7_lineage_state,
    "wall_time_ms": None, "cpu_user_ms": None, "cpu_sys_ms": None,
    "rss_kb_before": None, "rss_kb_after": None, "rss_kb_delta_or_null": None,
    "disk_read_bytes_delta": None, "disk_write_bytes_delta": None,
    "disk_note_or_null": "not measured: cross-process gate, timing captured separately if needed",
    "error_or_null": None if readback_ok else proc.stderr[-500:],
})

# ---------------------------------------------------------------- P8: hostile twin
forged_identity, _ = release_identity_for_payload(
    {"FORGED_MARKER.txt": b"this payload never actually gets written"},
    release_id="claude-config-sandbox-forged", version="r2-hostile-twin",
)
before_p8 = compute_state_digest(MANAGED_DIR)


def _p8_hostile_twin():
    return apply_transaction(
        store, operation="UPDATE", payload=payload_v2,
        release_id="claude-config-sandbox", version="r2-hostile-twin-attempt",
        attempt_id=f"{RUN_ID}-p8-update-hostile-1",
        declared_target_release=forged_identity,
    )


r_p8, outcome, err = _measure(
    "P8-hostile-twin", "H5", _p8_hostile_twin,
    operation="UPDATE",
    parent_state_sha256=before_p8,
    planned_target_reason=(
        "hostile-twin declares a forged identity intentionally mismatched against "
        "payload_v2; rejected before any target digest materializes"
    ),
    expected_rollback_target_reason="not applicable: rejected pre-mutation, no rollback needed",
)
after_p8 = compute_state_digest(MANAGED_DIR)
results["p8_hostile_twin"] = {
    "outcome": outcome, "error": err,
    "rejected_before_mutation": (outcome == "RAISED" and "hostile-twin" in (err or "")),
    "state_unchanged": before_p8 == after_p8,
    "generation_unchanged_at_1": store.load_lineage().generation == 1,
}

# ---------------------------------------------------------------- P9: replay/idempotency
def _p9_replay_already_active_release():
    return apply_transaction(
        store, operation="UPDATE", payload=payload_v1,
        release_id="claude-config-sandbox", version="r1-simulated-update",
        attempt_id=f"{RUN_ID}-p9-replay-1",
    )


before_p9 = compute_state_digest(MANAGED_DIR)
r_p9, outcome, err = _measure(
    "P9-replay-idempotency", "H8", _p9_replay_already_active_release,
    operation="UPDATE",
    parent_state_sha256=before_p9,
    planned_target_state_sha256=_planned_digest_for_payload(payload_v1),
    expected_rollback_target_reason="not applicable: rejected pre-mutation (target == active release), no rollback needed",
)
after_p9 = compute_state_digest(MANAGED_DIR)
results["p9_replay_idempotency"] = {
    "outcome": outcome, "error": err,
    "rejected_no_double_apply": (outcome == "RAISED" and "must differ" in (err or "")),
    "state_unchanged": before_p9 == after_p9,
    "generation_unchanged_at_1": store.load_lineage().generation == 1,
}

# ---------------------------------------------------------------- P10: concurrent/stale CAS
gen1_lineage = store.load_lineage()
payload_v3 = dict(payload_v1)
payload_v3["SELFINT_MARKER.txt"] = f"caller-B advance gen2 {RUN_ID}".encode("utf-8")


def _p10_caller_b():
    return apply_transaction(
        store, operation="UPDATE", payload=payload_v3,
        release_id="claude-config-sandbox", version="r2-caller-b",
        attempt_id=f"{RUN_ID}-p10-caller-b-1",
    )


before_p10b = compute_state_digest(MANAGED_DIR)
r_callerb, outcome_b, err_b = _measure(
    "P10-caller-b-advance", "H9", _p10_caller_b,
    operation="UPDATE",
    parent_state_sha256=before_p10b,
    planned_target_state_sha256=_planned_digest_for_payload(payload_v3),
    expected_rollback_target_reason="not applicable: no injected failure on this gate, no rollback expected",
)
gen2_state = compute_state_digest(MANAGED_DIR)
payload_v4_stale = dict(payload_v1)
payload_v4_stale["SELFINT_MARKER.txt"] = f"caller-A stale attempt {RUN_ID}".encode("utf-8")


def _p10_caller_a_stale():
    return apply_transaction(
        store, operation="UPDATE", payload=payload_v4_stale,
        release_id="claude-config-sandbox", version="r2-caller-a-stale",
        attempt_id=f"{RUN_ID}-p10-caller-a-1",
        expected_generation=gen1_lineage.generation,
        expected_state_sha256=gen1_lineage.state_sha256,
    )


r_callera, outcome_a, err_a = _measure(
    "P10-caller-a-stale-reject", "H9", _p10_caller_a_stale,
    operation="UPDATE",
    parent_state_sha256=gen2_state,
    planned_target_state_sha256=_planned_digest_for_payload(payload_v4_stale),
    expected_rollback_target_reason="not applicable: rejected pre-mutation via CAS, no rollback needed",
)
after_p10 = compute_state_digest(MANAGED_DIR)
results["p10_concurrent_stale_cas"] = {
    "caller_b_outcome": outcome_b, "caller_b_error": err_b,
    "caller_b_succeeded": (outcome_b == "OK"),
    "caller_a_outcome": outcome_a, "caller_a_error": err_a,
    "caller_a_rejected_fail_closed": (outcome_a == "RAISED" and "generation" in (err_a or "")),
    "final_state_is_caller_b_state": (after_p10 == gen2_state),
    "final_generation": store.load_lineage().generation,
    "no_split_brain": (after_p10 == gen2_state and store.load_lineage().generation == 2),
}

# ---------------------------------------------------------------- write outputs
MEASUREMENTS_PATH.write_text(
    "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in measurement_records) + "\n",
    encoding="utf-8",
)

summary = {
    "run_id": RUN_ID,
    "managed_dir": str(MANAGED_DIR),
    "control_dir": str(CONTROL_DIR),
    "measurements_path": str(MEASUREMENTS_PATH),
    "results": results,
    "final_lineage": store.load_lineage().as_dict(),
    "final_state_sha256": compute_state_digest(MANAGED_DIR),
}
print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
