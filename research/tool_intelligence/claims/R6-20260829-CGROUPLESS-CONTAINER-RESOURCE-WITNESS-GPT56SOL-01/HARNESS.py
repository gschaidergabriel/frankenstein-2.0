#!/usr/bin/env python3
"""Read-only Linux procfs resource witness for one already-resolved host PID.

This intentionally provides INIT_PROCESS_ONLY evidence. It must never be used to
mint container-total or cgroup-total resource credit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

SCHEMA = "FRANKENSTEIN2_PROCFS_PROCESS_RESOURCE_WITNESS/v1"
SCOPE = "INIT_PROCESS_ONLY"


class WitnessError(RuntimeError):
    pass


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise WitnessError(f"PID_NOT_AVAILABLE:{path}") from exc
    except PermissionError as exc:
        raise WitnessError(f"PERMISSION_DENIED:{path}") from exc


def _parse_stat(text: str) -> dict[str, int | str]:
    lparen = text.find("(")
    rparen = text.rfind(")")
    if lparen <= 0 or rparen <= lparen:
        raise WitnessError("MALFORMED_PROC_STAT")
    pid = int(text[:lparen].strip())
    comm = text[lparen + 1 : rparen]
    rest = text[rparen + 1 :].strip().split()
    if len(rest) < 22:
        raise WitnessError("TRUNCATED_PROC_STAT")
    return {
        "pid": pid,
        "comm": comm,
        "state": rest[0],
        "utime_ticks": int(rest[11]),
        "stime_ticks": int(rest[12]),
        "starttime_ticks": int(rest[19]),
        "vsize_bytes": int(rest[20]),
        "rss_pages": int(rest[21]),
    }


def _parse_colon_file(text: str) -> dict[str, int | str]:
    out: dict[str, int | str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        raw = raw.strip()
        if raw.endswith(" kB"):
            try:
                out[key] = int(raw[:-3].strip()) * 1024
                continue
            except ValueError:
                pass
        try:
            out[key] = int(raw)
        except ValueError:
            out[key] = raw
    return out


def _snapshot(pid: int) -> dict[str, Any]:
    root = Path("/proc") / str(pid)
    stat_before = _parse_stat(_read_text(root / "stat"))
    status = _parse_colon_file(_read_text(root / "status"))
    io = _parse_colon_file(_read_text(root / "io"))
    stat_after = _parse_stat(_read_text(root / "stat"))
    if stat_before["starttime_ticks"] != stat_after["starttime_ticks"]:
        raise WitnessError("PID_IDENTITY_CHANGED_DURING_SNAPSHOT")
    if stat_before["pid"] != pid or stat_after["pid"] != pid:
        raise WitnessError("PID_IDENTITY_MISMATCH")
    return {
        "monotonic_ns": time.monotonic_ns(),
        "wall_time_ns": time.time_ns(),
        "stat": stat_after,
        "status": {k: status[k] for k in (
            "VmRSS", "VmHWM", "Threads",
            "voluntary_ctxt_switches", "nonvoluntary_ctxt_switches",
        ) if k in status},
        "io": {k: io[k] for k in (
            "rchar", "wchar", "syscr", "syscw",
            "read_bytes", "write_bytes", "cancelled_write_bytes",
        ) if k in io},
    }


def _numeric_delta(a: dict[str, Any], b: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for key in sorted(set(a) & set(b)):
        av, bv = a[key], b[key]
        if isinstance(av, int) and isinstance(bv, int):
            result[key] = bv - av
    return result


def witness(pid: int, interval_seconds: float) -> dict[str, Any]:
    if pid <= 0:
        raise WitnessError("INVALID_PID")
    if interval_seconds < 0:
        raise WitnessError("NEGATIVE_INTERVAL")
    pidfd = None
    pidfd_state = "UNAVAILABLE"
    if hasattr(os, "pidfd_open"):
        try:
            pidfd = os.pidfd_open(pid, 0)
            pidfd_state = "OPENED"
        except OSError as exc:
            pidfd_state = f"OPEN_FAILED:{exc.errno}"
    try:
        start = _snapshot(pid)
        identity = start["stat"]["starttime_ticks"]
        if interval_seconds:
            time.sleep(interval_seconds)
        end = _snapshot(pid)
        if end["stat"]["starttime_ticks"] != identity:
            raise WitnessError("PID_IDENTITY_CHANGED_BETWEEN_SAMPLES")
        ticks = int(os.sysconf("SC_CLK_TCK"))
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        cpu_ticks = (
            end["stat"]["utime_ticks"] + end["stat"]["stime_ticks"]
            - start["stat"]["utime_ticks"] - start["stat"]["stime_ticks"]
        )
        result: dict[str, Any] = {
            "schema": SCHEMA,
            "scope": SCOPE,
            "container_total_credit": False,
            "cgroup_total_credit": False,
            "pid": pid,
            "process_identity": {"starttime_ticks": identity, "pidfd_state": pidfd_state},
            "clock_ticks_per_second": ticks,
            "page_size_bytes": page_size,
            "interval_seconds_requested": interval_seconds,
            "interval_seconds_observed": (end["monotonic_ns"] - start["monotonic_ns"]) / 1e9,
            "start": start,
            "end": end,
            "delta": {
                "cpu_ticks": cpu_ticks,
                "cpu_seconds": cpu_ticks / ticks,
                "io": _numeric_delta(start["io"], end["io"]),
                "status_counters": _numeric_delta(start["status"], end["status"]),
            },
            "limitations": [
                "INIT_PROCESS_ONLY_NOT_CONTAINER_TOTAL",
                "CHILD_OR_SIBLING_PROCESSES_NOT_ACCOUNTED",
                "STATUS_VMRSS_AND_VMHWM_ARE_APPROXIMATE_KERNEL_PROCFS_FIELDS",
                "PROC_IO_COUNTERS_HAVE_KERNEL_DOCUMENTED_CAVEATS",
            ],
            "promotion_rule": "CONTAINER_TOTAL_REQUIRES_INDEPENDENT_EXACT_CONTAINER_CGROUP_OR_COMPLETE_PROCESS_SET_BINDING",
        }
        canonical = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        result["witness_sha256"] = hashlib.sha256(canonical).hexdigest()
        return result
    finally:
        if pidfd is not None:
            os.close(pidfd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--interval-seconds", type=float, default=0.25)
    args = parser.parse_args()
    try:
        result = witness(args.pid, args.interval_seconds)
    except WitnessError as exc:
        print(json.dumps({
            "schema": SCHEMA,
            "scope": SCOPE,
            "status": "FAIL_CLOSED",
            "error": str(exc),
            "container_total_credit": False,
            "cgroup_total_credit": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
