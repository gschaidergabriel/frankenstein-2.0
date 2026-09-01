#!/usr/bin/env python3
"""Fail-closed evidence helpers for Trigger-4 PipeWire G2 terminal closure.

This module is evidence plumbing only.  It does not create a second voice,
playback, state, turn, effect, or acceptance authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

BOUND_SCHEMA = "T4_G2_PIPEWIRE_PREFLIGHT_BOUND/v1"
OBJECT_SCHEMA = "T4_G2_PIPEWIRE_OBJECT_BINDING/v1"
BOUND_POLICY_QUANTA = 16


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def _metadata_int(settings_text: str, key: str) -> int:
    patterns = (
        rf"key:\s*['\"]{re.escape(key)}['\"].*?value:\s*['\"]?([0-9]+)",
        rf"\b{re.escape(key)}\b\s*[=:]\s*['\"]?([0-9]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, settings_text)
        if match:
            value = int(match.group(1))
            if value > 0:
                return value
    raise ValueError(f"PIPEWIRE_SETTING_NOT_OBSERVED:{key}")


def derive_bound_receipt(settings_text: str) -> dict[str, Any]:
    """Derive a cancel-tail bound from pre-execution PipeWire clock settings.

    The 16-quantum policy is fixed in repository source before runtime.  Runtime
    may choose the observed rate/quantum but cannot tune the policy after seeing
    cancellation output.
    """
    rate = _metadata_int(settings_text, "clock.rate")
    quantum = _metadata_int(settings_text, "clock.quantum")
    bound_ms = float(math.ceil((BOUND_POLICY_QUANTA * quantum * 1000.0 / rate) * 1000.0) / 1000.0)
    return {
        "schema": BOUND_SCHEMA,
        "policy": "PREEXECUTION_OBSERVED_CLOCK_QUANTUM_X_FIXED_16",
        "policy_quanta": BOUND_POLICY_QUANTA,
        "clock_rate_hz": rate,
        "clock_quantum_frames": quantum,
        "derived_max_inflight_ms": bound_ms,
        "settings_sha256": sha256_text(settings_text),
    }


def validate_bound_receipt(receipt: dict[str, Any], current_settings_text: str, supplied_bound_ms: float) -> None:
    if receipt.get("schema") != BOUND_SCHEMA:
        raise ValueError("BOUND_PREFLIGHT_SCHEMA_MISMATCH")
    fresh = derive_bound_receipt(current_settings_text)
    for key in ("policy", "policy_quanta", "clock_rate_hz", "clock_quantum_frames", "derived_max_inflight_ms"):
        if receipt.get(key) != fresh.get(key):
            raise ValueError(f"BOUND_PREFLIGHT_CURRENT_GRAPH_MISMATCH:{key}")
    expected = float(receipt["derived_max_inflight_ms"])
    if not math.isclose(float(supplied_bound_ms), expected, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("BOUND_PREFLIGHT_SUPPLIED_VALUE_MISMATCH")


def _normalise_serial(value: Any) -> str:
    if value is None:
        raise ValueError("PIPEWIRE_OBJECT_SERIAL_MISSING")
    result = str(value).strip()
    if not result:
        raise ValueError("PIPEWIRE_OBJECT_SERIAL_EMPTY")
    return result


def _identity(obj: dict[str, Any]) -> dict[str, Any]:
    info = obj.get("info") if isinstance(obj.get("info"), dict) else {}
    props = info.get("props") if isinstance(info.get("props"), dict) else {}
    object_id = obj.get("id")
    if not isinstance(object_id, int):
        raise ValueError("PIPEWIRE_OBJECT_ID_MISSING")
    return {
        "schema": OBJECT_SCHEMA,
        "object_id": object_id,
        "object_serial": _normalise_serial(props.get("object.serial")),
        "node_name": props.get("node.name"),
        "node_description": props.get("node.description"),
        "node_nick": props.get("node.nick"),
        "media_class": props.get("media.class"),
        "device_id": props.get("device.id"),
    }


def _exact_named_candidates(objects: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        info = obj.get("info") if isinstance(obj.get("info"), dict) else {}
        props = info.get("props") if isinstance(info.get("props"), dict) else {}
        exact_values = {
            props.get("node.name"),
            props.get("node.description"),
            props.get("node.nick"),
            props.get("pulse.name"),
            props.get("pulse.monitor_name"),
        }
        if name in exact_values:
            candidates.append(obj)
    return candidates


def resolve_pipewire_objects(pw_dump_text: str, sink_name: str, monitor_name: str) -> dict[str, Any]:
    try:
        objects = json.loads(pw_dump_text)
    except json.JSONDecodeError as exc:
        raise ValueError("PIPEWIRE_DUMP_NOT_JSON") from exc
    if not isinstance(objects, list):
        raise ValueError("PIPEWIRE_DUMP_NOT_OBJECT_LIST")
    sink_candidates = _exact_named_candidates(objects, sink_name)
    monitor_candidates = _exact_named_candidates(objects, monitor_name)
    if len(sink_candidates) != 1:
        raise ValueError(f"PIPEWIRE_SINK_IDENTITY_AMBIGUOUS:{len(sink_candidates)}")
    if len(monitor_candidates) != 1:
        raise ValueError(f"PIPEWIRE_MONITOR_IDENTITY_AMBIGUOUS:{len(monitor_candidates)}")
    sink = _identity(sink_candidates[0])
    monitor = _identity(monitor_candidates[0])
    if sink["object_id"] == monitor["object_id"] or sink["object_serial"] == monitor["object_serial"]:
        raise ValueError("PIPEWIRE_SINK_MONITOR_IDENTITY_COLLISION")
    return {"sink": sink, "monitor": monitor}


def identities_absent(pw_dump_text: str, binding: dict[str, Any]) -> bool:
    try:
        objects = json.loads(pw_dump_text)
    except json.JSONDecodeError:
        return False
    if not isinstance(objects, list):
        return False
    forbidden_serials = {
        str(binding["sink"]["object_serial"]),
        str(binding["monitor"]["object_serial"]),
    }
    forbidden_names = {
        binding["sink"].get("node_name"),
        binding["monitor"].get("node_name"),
    } - {None}
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        info = obj.get("info") if isinstance(obj.get("info"), dict) else {}
        props = info.get("props") if isinstance(info.get("props"), dict) else {}
        if str(props.get("object.serial")) in forbidden_serials:
            return False
        if props.get("node.name") in forbidden_names:
            return False
    return True


def write_bound_receipt(settings_path: Path, output_path: Path) -> dict[str, Any]:
    text = settings_path.read_text(encoding="utf-8", errors="replace")
    receipt = derive_bound_receipt(text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    bound = sub.add_parser("derive-bound")
    bound.add_argument("--settings", type=Path, required=True)
    bound.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "derive-bound":
        receipt = write_bound_receipt(args.settings, args.output)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(main())
