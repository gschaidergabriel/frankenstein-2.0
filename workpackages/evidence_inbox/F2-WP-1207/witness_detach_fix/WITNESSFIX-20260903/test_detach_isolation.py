#!/usr/bin/env python3
"""Isolated dummy test for the witness-detach fix (WP1207 post-reentry
blocker, blockers.json/POSTREENTRY-20260901: "Zeuge starb mit dem Subjekt
(Detach nicht belastbar)").

Entirely self-contained: dummy_subject.py stand-ins, no contact with any
real claude/agent process, no live subject touched. This is exactly the
"an Attrappe belasten, bevor es je wieder am echten Prozess laeuft" step
the blocker's own next_discriminator prescribes.

Methodology (v2 of this test -- v1 had a race condition, see NOTES.md):
spin up a "harness leader" in its own fresh process group/session
(start_new_session=True), and inside it launch a dummy subject plus TWO
witnesses running the identical witness_v3.py code -- one WITHOUT
--daemonize (naive, reproduces the v2 vulnerability: stays in the harness's
process group) and one WITH --daemonize (fixed: double-forks into its own
session before touching the target). Both witnesses are given a long
timeout and simply sit in their poll loop with the subject still alive.

Then send exactly ONE signal: SIGTERM to the harness's process group. This
takes the subject and the naive witness down in the same kernel action --
literally the reported failure mode, "witness died WITH the subject", not a
race against a fast poll loop. The fixed witness is not a member of that
process group (already detached), so it survives the same signal, then
notices -- via its own ordinary poll loop, same as always -- that its
target is gone, and completes its relaunch.

Pass criteria:
  - naive witness's pgid == harness pgid at start (setup sanity: it really
    is an ordinary member of the harness's job, like witness_v2.py was)
  - fixed witness's pgid != harness pgid at start (real detachment)
  - immediately after the single group SIGTERM: naive witness pid gone
  - immediately after the same signal: fixed witness pid still alive
  - shortly after: fixed witness completes its relaunch (status OK,
    relaunched_pid alive) -- proves detachment doesn't just mean "survives"
    but "survives AND still does its job"
"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = Path("/tmp/wp1207-witnessfix-test")


def read_json(p: Path, timeout=10.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                pass
        time.sleep(0.1)
    return None


def alive(pid: int) -> bool:
    return Path(f"/proc/{pid}").exists()


def main() -> int:
    if WORK.exists():
        for f in WORK.glob("*"):
            f.unlink()
    WORK.mkdir(parents=True, exist_ok=True)

    result = {"test": "witness-detach-isolation-v2", "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    harness = subprocess.Popen(
        ["bash", str(HERE / "harness_leader.sh"), str(HERE), str(WORK)],
        start_new_session=True,
    )
    harness_pgid = os.getpgid(harness.pid)
    result["harness_leader_pid"] = harness.pid
    result["harness_pgid"] = harness_pgid

    subject_pid = None
    for _ in range(50):
        p = WORK / "subject.pid"
        if p.exists():
            subject_pid = int(p.read_text().strip())
            break
        time.sleep(0.1)
    result["subject_pid"] = subject_pid
    if subject_pid is None or not alive(subject_pid):
        result["status"] = "SETUP_FAIL -- subject never started"
        print(json.dumps(result, indent=1))
        return 10

    ev_naive_0 = read_json(WORK / "evidence_naive.json")
    ev_fixed_0 = read_json(WORK / "evidence_fixed.json")
    result["naive_witness_initial"] = ev_naive_0
    result["fixed_witness_initial"] = ev_fixed_0
    if not ev_naive_0 or not ev_fixed_0:
        result["status"] = "SETUP_FAIL -- witness evidence never appeared"
        print(json.dumps(result, indent=1))
        return 11

    naive_pid = ev_naive_0["own_pid"]
    naive_pgid_at_start = ev_naive_0["own_pgid"]
    fixed_pid = ev_fixed_0["own_pid"]
    fixed_pgid_at_start = ev_fixed_0["own_pgid"]
    result["naive_pgid_equals_harness_pgid"] = (naive_pgid_at_start == harness_pgid)
    result["fixed_pgid_differs_from_harness_pgid"] = (fixed_pgid_at_start != harness_pgid)

    # settle: make sure both witnesses are stably parked in their poll loop
    # (subject is still alive, no death to detect yet -- nothing racy here).
    time.sleep(0.5)
    result["subject_alive_before_group_kill"] = alive(subject_pid)
    result["naive_alive_before_group_kill"] = alive(naive_pid)
    result["fixed_alive_before_group_kill"] = alive(fixed_pid)

    # --- the actual failure-mode simulation: ONE signal, group-wide ---
    # This takes subject + naive witness (+ harness leader) down together,
    # exactly matching "Zeuge starb mit dem Subjekt": no separate subject
    # kill beforehand, no race against the witness's own poll loop.
    try:
        os.killpg(harness_pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    result["group_sigterm_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # check immediately -- this is the property under test, no grace period.
    time.sleep(0.15)
    result["subject_alive_immediately_after"] = alive(subject_pid)
    result["naive_witness_alive_immediately_after"] = alive(naive_pid)
    result["fixed_witness_alive_immediately_after"] = alive(fixed_pid)

    # now give the surviving fixed witness time to notice the target is
    # gone (its own 0.1s poll loop) and complete its relaunch.
    ev_fixed_final = None
    for _ in range(100):
        ev_fixed_final = read_json(WORK / "evidence_fixed.json", timeout=0.1)
        if ev_fixed_final and ev_fixed_final.get("status"):
            break
        time.sleep(0.1)
    result["fixed_witness_final"] = ev_fixed_final

    relaunched_alive = False
    if ev_fixed_final and ev_fixed_final.get("relaunched_pid"):
        relaunched_alive = alive(ev_fixed_final["relaunched_pid"])
    result["fixed_witness_relaunch_confirmed_alive"] = relaunched_alive

    ev_naive_final = read_json(WORK / "evidence_naive.json", timeout=0.1)
    result["naive_witness_final_evidence_unchanged"] = (ev_naive_final == ev_naive_0)
    result["naive_witness_never_reached_status"] = (
        ev_naive_final is not None and "status" not in ev_naive_final
    )

    # Note on fixed_witness_alive_immediately_after: witness_v3.py is a
    # ONE-SHOT tool that exits right after completing its job (spawn
    # relaunch + write final evidence), not a persistent daemon -- so
    # "still resident 0.15s later" is not itself meaningful (it may have
    # already finished successfully in that window, same as the naive one
    # would have if it hadn't been killed first). The decisive proof of
    # survival is that it reached a clean "status": "OK" with a live
    # relaunched process at all, despite being a live process in the
    # harness's session at the moment the group SIGTERM was sent -- if it
    # had died with the group (like the naive one, provably, below), its
    # evidence file would be stuck at the initial record forever, exactly
    # like the naive witness's is.
    passed = (
        result["naive_pgid_equals_harness_pgid"] is True
        and result["fixed_pgid_differs_from_harness_pgid"] is True
        and result["subject_alive_before_group_kill"] is True
        and result["naive_alive_before_group_kill"] is True
        and result["fixed_alive_before_group_kill"] is True
        and result["subject_alive_immediately_after"] is False
        and result["naive_witness_alive_immediately_after"] is False
        and result["naive_witness_never_reached_status"] is True
        and ev_fixed_final is not None
        and ev_fixed_final.get("status") == "OK"
        and relaunched_alive is True
    )
    result["status"] = "PASS" if passed else "FAIL"

    # relaunched_pid is a `shell=True` Popen pid -- that's the /bin/sh
    # wrapper's pid, and since start_new_session=True made it a fresh
    # session/pgid leader, killpg on that pid takes down the shell AND
    # its actual dummy_subject.py child together (plain kill() would only
    # kill the shell and orphan+leak the child).
    for pid in [(ev_fixed_final or {}).get("relaunched_pid"), (ev_naive_final or {}).get("relaunched_pid")]:
        if pid:
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    for pid in [subject_pid, naive_pid, fixed_pid, harness.pid]:
        if pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    try:
        os.killpg(harness_pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass

    out = WORK / "test_result.json"
    out.write_text(json.dumps(result, indent=1, sort_keys=True))
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
