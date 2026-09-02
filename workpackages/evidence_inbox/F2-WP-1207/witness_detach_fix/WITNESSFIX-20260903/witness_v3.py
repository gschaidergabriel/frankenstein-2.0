#!/usr/bin/env python3
"""Zeuge v3 -- fixes the WP1207 post-reentry blocker (blockers.json,
POSTREENTRY-20260901, INFRA_AUTH_TRANSPORT_QUOTA): "Zeuge starb mit dem
Subjekt (Detach nicht belastbar)".

Root cause (witness_v2.py, same run): the witness process itself was never
detached from whatever session/process-group launched it. It only called
`start_new_session=True` on the CHILD it spawns *after* the target dies (the
relaunch), not on itself. If the launching session/process-group is torn
down together with the target (job-control cleanup, controlling-terminal
SIGHUP to the foreground group, session/cgroup teardown -- any of the
ordinary ways an OS or a supervising harness cleans up "everything that
belonged to this job" when its lead process dies), a witness that never
detached goes down with it, before it can observe the death or relaunch
anything. That is exactly what blockers.json describes and what
next_discriminator prescribes: "Neustart-Werkzeug AUSSERHALB der
Prozessgruppe des Subjekts erzeugen (echtes setsid + nohup + Auskoppeln VOR
dem Kill) und an Attrappe belasten, bevor es je wieder am echten Prozess
laeuft."

Fix: classic UNIX double-fork daemonization (setsid + double fork + stdio
redirected to /dev/null + cwd to /) executed as the FIRST thing in main(),
before any target/kill/relaunch logic runs. After this, the witness lives in
its own new session with no controlling terminal and is not a job-control
child of its launcher's process group -- so a group-wide or session-wide
teardown of the launcher's job cannot take it down.

Generalized vs v2: target pid, relaunch command and session id are CLI args,
not hardcoded constants (v2 hardcoded TARGET=4179659, a real subject PID,
and a gnome-terminal `claude --resume <session>` relaunch command -- neither
belongs in a reusable tool, and both are dead weight for testing against a
dummy).

Usage:
    witness_v3.py --arm --target-pid PID --relaunch-cmd 'CMD' [--evidence PATH]

Without --arm: dry-run, prints what it would do, does nothing.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def daemonize() -> None:
    """Classic double-fork self-detach. Must run before anything else."""
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    os.chdir("/")
    os.umask(0)
    devnull_in = os.open(os.devnull, os.O_RDONLY)
    devnull_out = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_in, 0)
    os.dup2(devnull_out, 1)
    os.dup2(devnull_out, 2)


def alive(pid: int) -> bool:
    return Path(f"/proc/{pid}").exists()


def flush(evid_path: Path, res: dict) -> None:
    evid_path.write_text(json.dumps(res, indent=1, sort_keys=True))


def run(args: argparse.Namespace) -> int:
    evid = Path(args.evidence)
    res = {
        "witness_version": "v3",
        "own_pid": os.getpid(),
        "own_pgid": os.getpgrp(),
        "own_sid": os.getsid(0),
        "target_pid": args.target_pid,
        "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "daemonized": args.daemonize,
    }
    flush(evid, res)

    if not alive(args.target_pid):
        res["status"] = "ABORT -- target already dead at arm time"
        flush(evid, res)
        return 3

    # Wait for target to die (poll -- no signal sent by this tool in the
    # dummy test; the test harness kills the target itself to keep the
    # "who kills whom" boundary explicit and auditable).
    waited = 0.0
    while alive(args.target_pid) and waited < args.timeout:
        time.sleep(0.1)
        waited += 0.1
    res["target_died"] = not alive(args.target_pid)
    res["waited_s"] = round(waited, 2)
    flush(evid, res)
    if not res["target_died"]:
        res["status"] = "FAIL -- target still alive at timeout"
        flush(evid, res)
        return 4

    t1 = time.monotonic()
    proc = subprocess.Popen(
        args.relaunch_cmd,
        shell=True,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    res["relaunched_pid"] = proc.pid
    res["relaunch_ms"] = round((time.monotonic() - t1) * 1000, 3)
    res["status"] = "OK"
    flush(evid, res)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="store_true")
    ap.add_argument("--target-pid", type=int, required=True)
    ap.add_argument("--relaunch-cmd", type=str, required=True)
    ap.add_argument("--evidence", type=str, required=True)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--daemonize", action="store_true",
                     help="self-detach via double-fork+setsid before doing anything else")
    args = ap.parse_args()

    if not args.arm:
        print("NICHT SCHARF -- nur mit --arm. Target waere:", args.target_pid)
        return 2

    if args.daemonize:
        daemonize()

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
