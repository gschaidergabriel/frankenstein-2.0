#!/usr/bin/env python3
"""Read-only PipeWire evidence sidecar for the Trigger-4 G2 discriminator.

The observer never creates, routes, starts, stops, or mutates audio. It samples
run-local PipeWire node/stream identities and reported latency while the existing
G2 harness remains the sole test-driver playback/cancellation path.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import signal
import subprocess
import time
from typing import Any

SCHEMA = "T4_G2_PIPEWIRE_READONLY_OBSERVER/v1"
_STOP = False


def _stop(_signum: int, _frame: object) -> None:
    global _STOP
    _STOP = True


def run_text(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        return ""
    return proc.stdout


def node_snapshot(obj: dict[str, Any], now_ns: int) -> dict[str, Any] | None:
    if not str(obj.get("type", "")).endswith(":Node"):
        return None
    info = obj.get("info") if isinstance(obj.get("info"), dict) else {}
    props = info.get("props") if isinstance(info.get("props"), dict) else {}
    serial = props.get("object.serial")
    if serial is None:
        return None
    latency_props = {
        str(key): value
        for key, value in props.items()
        if "latency" in str(key).lower() or str(key) in {"node.rate", "audio.rate"}
    }
    return {
        "object_id": obj.get("id"),
        "object_serial": str(serial),
        "node_name": props.get("node.name"),
        "node_description": props.get("node.description"),
        "media_class": props.get("media.class"),
        "media_name": props.get("media.name"),
        "application_name": props.get("application.name"),
        "application_process_binary": props.get("application.process.binary"),
        "application_process_id": props.get("application.process.id"),
        "pipewire_sec_pid": props.get("pipewire.sec.pid"),
        "target_object": props.get("target.object"),
        "node_target": props.get("node.target"),
        "latency_props": latency_props,
        "first_seen_monotonic_ns": now_ns,
        "last_seen_monotonic_ns": now_ns,
    }


def collect_nodes(state: dict[str, dict[str, Any]]) -> None:
    text = run_text(["pw-dump"])
    if not text:
        return
    try:
        objects = json.loads(text)
    except json.JSONDecodeError:
        return
    if not isinstance(objects, list):
        return
    now_ns = time.monotonic_ns()
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        snap = node_snapshot(obj, now_ns)
        if snap is None:
            continue
        key = f"{snap['object_serial']}:{snap['object_id']}"
        existing = state.get(key)
        if existing is None:
            state[key] = snap
        else:
            existing["last_seen_monotonic_ns"] = now_ns
            for field in (
                "node_name",
                "node_description",
                "media_class",
                "media_name",
                "application_name",
                "application_process_binary",
                "application_process_id",
                "pipewire_sec_pid",
                "target_object",
                "node_target",
            ):
                if snap.get(field) is not None:
                    existing[field] = snap[field]
            if snap.get("latency_props"):
                existing["latency_props"] = snap["latency_props"]


def parse_pactl_latency(text: str, object_name: str, prefix: str) -> dict[str, Any] | None:
    sections = re.split(rf"(?m)^(?={re.escape(prefix)} #)", text)
    for section in sections:
        if not re.search(rf"(?m)^\s*Name:\s*{re.escape(object_name)}\s*$", section):
            continue
        match = re.search(
            r"(?m)^\s*Latency:\s*([0-9]+)\s*usec(?:,\s*configured\s*([0-9]+)\s*usec)?",
            section,
        )
        if not match:
            return {"name": object_name, "latency_usec": None, "configured_latency_usec": None}
        return {
            "name": object_name,
            "latency_usec": int(match.group(1)),
            "configured_latency_usec": int(match.group(2)) if match.group(2) is not None else None,
        }
    return None


def collect_latency(samples: list[dict[str, Any]], sink_name: str, monitor_name: str) -> None:
    now_ns = time.monotonic_ns()
    sink = parse_pactl_latency(run_text(["pactl", "list", "sinks"]), sink_name, "Sink")
    monitor = parse_pactl_latency(run_text(["pactl", "list", "sources"]), monitor_name, "Source")
    if sink is None and monitor is None:
        return
    sample: dict[str, Any] = {"monotonic_ns": now_ns}
    if sink is not None:
        sample["sink"] = sink
    if monitor is not None:
        sample["monitor"] = monitor
    samples.append(sample)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sink-name", default="f2_voice_g2_sink")
    parser.add_argument("--monitor-name", default="f2_voice_g2_sink.monitor")
    parser.add_argument("--interval-ms", type=float, default=100.0)
    args = parser.parse_args()
    if args.interval_ms < 20:
        raise SystemExit("interval must be >=20ms")

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    started_ns = time.monotonic_ns()
    nodes: dict[str, dict[str, Any]] = {}
    latency_samples: list[dict[str, Any]] = []
    iterations = 0
    while not _STOP:
        collect_nodes(nodes)
        if iterations % 4 == 0:
            collect_latency(latency_samples, args.sink_name, args.monitor_name)
        iterations += 1
        time.sleep(args.interval_ms / 1000.0)

    collect_nodes(nodes)
    collect_latency(latency_samples, args.sink_name, args.monitor_name)
    report = {
        "schema": SCHEMA,
        "mode": "READ_ONLY_EVIDENCE_SIDECAR",
        "started_monotonic_ns": started_ns,
        "stopped_monotonic_ns": time.monotonic_ns(),
        "poll_interval_ms": args.interval_ms,
        "sink_name": args.sink_name,
        "monitor_name": args.monitor_name,
        "nodes": sorted(nodes.values(), key=lambda row: (row["first_seen_monotonic_ns"], row["object_serial"])),
        "latency_samples": latency_samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
