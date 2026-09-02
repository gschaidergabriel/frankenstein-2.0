#!/usr/bin/env python3
"""Fail-closed canonical-required-observables guard for Trigger-4 G2.

Consumes the existing G2 harness receipt plus a read-only PipeWire observer trace.
It may narrow/reject evidence; it cannot create playback, cancellation, state,
effect, physical-device, whole-voice, or whole-product credit.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

SCHEMA = "T4_G2_PIPEWIRE_S2_PLAYBACK_CANCEL_MONITOR/v2"
SEMANTIC_KEY = "0d83f7d13c1d8f91686cf94070f73d901a49018b40a9c058d1949af094655bff"
REQUIRED_NAMES = (
    "f2_subject_sha",
    "tts_runtime_binary_sha256",
    "tts_model_sha256",
    "source_waveform_sha256",
    "voice_output_packet_id",
    "pipewire_version",
    "pipewire_sink_node_identity",
    "pipewire_monitor_node_identity",
    "playback_stream_identity",
    "capture_stream_identity",
    "source_sample_rate_channels_frames",
    "monitor_sample_rate_channels_frames",
    "pipewire_quantum_and_reported_latency",
    "control_alignment_offset_ms",
    "cancel_request_monotonic_ns",
    "packet_terminal_monotonic_ns",
    "playback_terminal_monotonic_ns",
    "last_old_packet_correlated_sample_monotonic_or_sample_index",
    "cancel_to_last_old_sample_ms",
    "post_bound_old_packet_correlation_or_sample_count",
    "commit_eligible_after_cancel",
    "run_owned_node_cleanup",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def distribution_manifest_sha256(name: str) -> str | None:
    try:
        dist = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return None
    h = hashlib.sha256()
    observed = 0
    for entry in sorted(dist.files or [], key=lambda item: str(item)):
        path = Path(dist.locate_file(entry))
        if not path.is_file():
            continue
        h.update(str(entry).encode("utf-8"))
        h.update(b"\0")
        h.update(bytes.fromhex(sha256_file(path)))
        h.update(b"\n")
        observed += 1
    return h.hexdigest() if observed else None


def parse_harness_stdout(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    markers = re.findall(r"^T4_G2_PIPEWIRE_RECEIPT_B64=([A-Za-z0-9+/=]+)$", text, re.MULTILINE)
    if not markers:
        raise ValueError("HARNESS_RECEIPT_MARKER_MISSING")
    try:
        payload = json.loads(base64.b64decode(markers[-1]).decode("utf-8"))
    except Exception as exc:
        raise ValueError("HARNESS_RECEIPT_MARKER_INVALID") from exc
    if not isinstance(payload, dict):
        raise ValueError("HARNESS_RECEIPT_NOT_OBJECT")
    return payload


def _process_label(node: dict[str, Any]) -> str:
    return " ".join(
        str(node.get(key) or "")
        for key in (
            "application_process_binary",
            "application_name",
            "node_name",
            "media_name",
        )
    ).lower()


def _overlaps(node: dict[str, Any], start_ns: int, end_ns: int, pad_ms: float = 600.0) -> bool:
    pad_ns = int(pad_ms * 1_000_000)
    first = int(node.get("first_seen_monotonic_ns") or 0)
    last = int(node.get("last_seen_monotonic_ns") or first)
    return first <= end_ns + pad_ns and last >= start_ns - pad_ns


def _stream_identity(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "object_id": node.get("object_id"),
        "object_serial": node.get("object_serial"),
        "node_name": node.get("node_name"),
        "media_class": node.get("media_class"),
        "media_name": node.get("media_name"),
        "application_name": node.get("application_name"),
        "application_process_binary": node.get("application_process_binary"),
        "application_process_id": node.get("application_process_id"),
        "target_object": node.get("target_object"),
        "node_target": node.get("node_target"),
        "first_seen_monotonic_ns": node.get("first_seen_monotonic_ns"),
        "last_seen_monotonic_ns": node.get("last_seen_monotonic_ns"),
        "latency_props": node.get("latency_props") or {},
    }


def resolve_phase_stream(
    observer: dict[str, Any],
    process_binary: str,
    start_ns: int,
    end_ns: int,
) -> dict[str, Any]:
    candidates = []
    for node in observer.get("nodes", []):
        if not isinstance(node, dict):
            continue
        media_class = str(node.get("media_class") or "")
        if not media_class.startswith("Stream/"):
            continue
        if process_binary.lower() not in _process_label(node):
            continue
        if _overlaps(node, start_ns, end_ns):
            candidates.append(node)
    exact_serials = {str(node.get("object_serial")) for node in candidates if node.get("object_serial") is not None}
    if len(exact_serials) != 1 or len(candidates) != 1:
        raise ValueError(
            f"STREAM_IDENTITY_AMBIGUOUS:{process_binary}:candidates={len(candidates)}:serials={len(exact_serials)}"
        )
    return _stream_identity(candidates[0])


def resolve_streams(harness: dict[str, Any], observer: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    control = harness.get("control") or {}
    cancel = harness.get("cancel") or {}
    replacement = harness.get("replacement") or {}
    phases = {
        "control": (control.get("playback_started_ns"), control.get("playback_terminal_ns")),
        "cancel": (cancel.get("playback_started_ns"), cancel.get("playback_terminal_ns")),
        "replacement": (replacement.get("playback_started_ns"), replacement.get("playback_terminal_ns")),
    }
    playback: dict[str, Any] = {}
    capture: dict[str, Any] = {}
    for phase, pair in phases.items():
        if pair[0] is None or pair[1] is None:
            if phase == "replacement":
                continue
            raise ValueError(f"STREAM_PHASE_TIMESTAMPS_MISSING:{phase}")
        start_ns, end_ns = int(pair[0]), int(pair[1])
        playback[phase] = resolve_phase_stream(observer, "paplay", start_ns, end_ns)
        capture[phase] = resolve_phase_stream(observer, "parec", start_ns, end_ns)
    for required_phase in ("control", "cancel"):
        if required_phase not in playback or required_phase not in capture:
            raise ValueError(f"REQUIRED_STREAM_PHASE_MISSING:{required_phase}")
    return playback, capture


def reported_latency(observer: dict[str, Any]) -> dict[str, Any]:
    samples = []
    for sample in observer.get("latency_samples", []):
        if not isinstance(sample, dict):
            continue
        compact: dict[str, Any] = {"monotonic_ns": sample.get("monotonic_ns")}
        reported = False
        for kind in ("sink", "monitor"):
            item = sample.get(kind)
            if not isinstance(item, dict):
                continue
            compact[kind] = item
            if item.get("latency_usec") is not None or item.get("configured_latency_usec") is not None:
                reported = True
        if reported:
            samples.append(compact)
    node_latency = []
    for node in observer.get("nodes", []):
        if not isinstance(node, dict):
            continue
        props = node.get("latency_props") or {}
        if props:
            node_latency.append(
                {
                    "object_serial": node.get("object_serial"),
                    "node_name": node.get("node_name"),
                    "media_class": node.get("media_class"),
                    "reported_properties": props,
                }
            )
    if not samples and not node_latency:
        raise ValueError("PIPEWIRE_REPORTED_LATENCY_NOT_OBSERVED")
    return {"pactl_reported_latency_samples": samples, "node_reported_latency_properties": node_latency}


def _required_value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (list, dict, tuple)) and len(value) == 0:
        return False
    return True


def build_required_observables(
    harness: dict[str, Any],
    observer: dict[str, Any],
    bound: dict[str, Any],
) -> dict[str, Any]:
    analysis = harness.get("analysis") or {}
    alignment = analysis.get("alignment") or {}
    measurement = analysis.get("measurement") or {}
    files = analysis.get("files") or {}
    source = harness.get("source") or {}
    cancel = harness.get("cancel") or {}
    pipewire = harness.get("pipewire") or {}
    graph = (pipewire.get("graph_preflight") or {}).get("pipewire_objects") or {}
    cleanup = harness.get("cleanup") or {}

    playback_streams, capture_streams = resolve_streams(harness, observer)
    latency = reported_latency(observer)
    python_executable = Path(sys.executable).resolve()
    tts_binary_sha = sha256_file(python_executable) if python_executable.is_file() else None
    tts_package_manifest_sha = distribution_manifest_sha256("piper-tts")

    source_meta = source.get("wav_meta") or {}
    control_file = files.get("control") or {}
    cancel_file = files.get("cancel") or {}
    rate = source_meta.get("rate")
    last_old_ms = measurement.get("last_old_audio_source_timeline_end_ms")
    last_old_sample_index = None
    if rate is not None and last_old_ms is not None:
        last_old_sample_index = int(round(float(last_old_ms) * float(rate) / 1000.0))

    return {
        "f2_subject_sha": harness.get("f2_subject_sha"),
        "tts_runtime_binary_sha256": tts_binary_sha,
        "tts_runtime_binary_path": str(python_executable),
        "tts_runtime_package_manifest_sha256": tts_package_manifest_sha,
        "tts_model_sha256": source.get("tts_model_sha256"),
        "source_waveform_sha256": source.get("wav_sha256"),
        "voice_output_packet_id": cancel.get("voice_output_packet_id"),
        "pipewire_version": pipewire.get("pipewire_version"),
        "pipewire_sink_node_identity": graph.get("sink"),
        "pipewire_monitor_node_identity": graph.get("monitor"),
        "playback_stream_identity": playback_streams,
        "capture_stream_identity": capture_streams,
        "source_sample_rate_channels_frames": {
            "rate": source_meta.get("rate"),
            "channels": source_meta.get("channels"),
            "frames": source_meta.get("frames"),
        },
        "monitor_sample_rate_channels_frames": {
            "control": {
                "rate": control_file.get("rate"),
                "channels": control_file.get("channels"),
                "frames": control_file.get("frames"),
            },
            "cancel": {
                "rate": cancel_file.get("rate"),
                "channels": cancel_file.get("channels"),
                "frames": cancel_file.get("frames"),
            },
        },
        "pipewire_quantum_and_reported_latency": {
            "clock_rate_hz": bound.get("clock_rate_hz"),
            "clock_quantum_frames": bound.get("clock_quantum_frames"),
            "bound_policy_quanta": bound.get("policy_quanta"),
            "derived_max_inflight_ms": bound.get("derived_max_inflight_ms"),
            **latency,
        },
        "control_alignment_offset_ms": alignment.get("control_capture_offset_ms"),
        "cancel_request_monotonic_ns": cancel.get("cancel_request_ns"),
        "packet_terminal_monotonic_ns": cancel.get("packet_terminal_ns"),
        "playback_terminal_monotonic_ns": cancel.get("playback_terminal_ns"),
        "last_old_packet_correlated_sample_monotonic_or_sample_index": {
            "source_sample_index": last_old_sample_index,
            "source_timeline_end_ms": last_old_ms,
        },
        "cancel_to_last_old_sample_ms": measurement.get("observed_cancel_to_last_old_audio_tail_ms"),
        "post_bound_old_packet_correlation_or_sample_count": {
            "post_bound_old_audio_window_count": measurement.get("post_bound_old_audio_window_count"),
            "post_bound_observation_window_count": measurement.get("post_bound_observation_window_count"),
            "max_post_bound_correlation": measurement.get("max_post_bound_correlation"),
        },
        "commit_eligible_after_cancel": cancel.get("commit_eligible"),
        "run_owned_node_cleanup": {
            "run_owned_sink_removed": cleanup.get("run_owned_sink_removed"),
            "bound_pipewire_object_identities_absent_after": cleanup.get("bound_pipewire_object_identities_absent_after"),
        },
    }


def validate_required(observables: dict[str, Any]) -> list[str]:
    missing = [name for name in REQUIRED_NAMES if not _required_value_present(observables.get(name))]
    source_meta = observables.get("source_sample_rate_channels_frames") or {}
    if any(source_meta.get(key) in (None, 0) for key in ("rate", "channels", "frames")):
        missing.append("source_sample_rate_channels_frames")
    monitor = observables.get("monitor_sample_rate_channels_frames") or {}
    for phase in ("control", "cancel"):
        meta = monitor.get(phase) or {}
        if any(meta.get(key) in (None, 0) for key in ("rate", "channels", "frames")):
            missing.append("monitor_sample_rate_channels_frames")
            break
    quantum = observables.get("pipewire_quantum_and_reported_latency") or {}
    if any(quantum.get(key) in (None, 0) for key in ("clock_rate_hz", "clock_quantum_frames", "derived_max_inflight_ms")):
        missing.append("pipewire_quantum_and_reported_latency")
    cleanup = observables.get("run_owned_node_cleanup") or {}
    if cleanup.get("run_owned_sink_removed") is not True or cleanup.get("bound_pipewire_object_identities_absent_after") is not True:
        missing.append("run_owned_node_cleanup")
    if observables.get("commit_eligible_after_cancel") is not False:
        missing.append("commit_eligible_after_cancel")
    last_old = observables.get("last_old_packet_correlated_sample_monotonic_or_sample_index") or {}
    if last_old.get("source_sample_index") is None:
        missing.append("last_old_packet_correlated_sample_monotonic_or_sample_index")
    return sorted(set(missing))


def guarded_receipt(
    harness: dict[str, Any],
    observer: dict[str, Any],
    bound: dict[str, Any],
) -> dict[str, Any]:
    receipt = dict(harness)
    receipt.setdefault("schema", SCHEMA)
    receipt.setdefault("semantic_key", SEMANTIC_KEY)
    receipt["canonical_required_observables_guard"] = {
        "benchmark": "research/local_voice/benchmarks/2026-09-02_TRIGGER7_COMPLETION_DEPTH_G2.json",
        "mode": "FAIL_CLOSED_EVIDENCE_ONLY",
    }
    try:
        observables = build_required_observables(receipt, observer, bound)
        missing = validate_required(observables)
    except Exception as exc:
        observables = {}
        missing = [f"guard_exception:{type(exc).__name__}:{exc}"]
    receipt["required_observables"] = observables
    receipt["canonical_required_observables_guard"]["missing"] = missing
    receipt["canonical_required_observables_guard"]["complete"] = not missing

    harness_pass = receipt.get("result") == "NO_COUNTEREXAMPLE"
    if harness_pass and not missing:
        receipt["classification"] = (
            "ACCEPT_AT_BOUNDED_S2_OWNER_VPS_PIPEWIRE_TEST_DRIVER_TRANSLATION_SCOPE_ONLY"
            "__CANONICAL_REQUIRED_OBSERVABLES_BOUND"
        )
        receipt["failure_class"] = None
        return receipt

    if harness_pass and missing:
        receipt["result"] = "BLOCKED"
        receipt["failure_class"] = "EVIDENCE_INVALID"
        receipt["classification"] = "EVIDENCE_INVALID_MISSING_CANONICAL_G2_REQUIRED_OBSERVABLES"
    for key in list((receipt.get("measured_credit") or {}).keys()):
        receipt["measured_credit"][key] = 0
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness-stdout", type=Path, required=True)
    parser.add_argument("--observer", type=Path, required=True)
    parser.add_argument("--bound-preflight", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        harness = parse_harness_stdout(args.harness_stdout)
        observer = json.loads(args.observer.read_text(encoding="utf-8"))
        bound = json.loads(args.bound_preflight.read_text(encoding="utf-8"))
        if not isinstance(observer, dict) or not isinstance(bound, dict):
            raise ValueError("OBSERVER_OR_BOUND_NOT_OBJECT")
        receipt = guarded_receipt(harness, observer, bound)
    except Exception as exc:
        receipt = {
            "schema": SCHEMA,
            "semantic_key": SEMANTIC_KEY,
            "trigger": "4",
            "work_class": "RUNTIME_CREDIT_CLOSURE",
            "result": "BLOCKED",
            "failure_class": "EVIDENCE_INVALID",
            "classification": f"EVIDENCE_INVALID_REQUIRED_OBSERVABLE_GUARD:{type(exc).__name__}:{exc}",
            "measured_credit": {},
            "explicit_zero_credit": {
                "physical_microphone": 0,
                "physical_speaker": 0,
                "human_heard_output": 0,
                "gwt_jspace": 0,
                "effect": 0,
                "training": 0,
                "whole_voice_e2e": 0,
                "whole_product": 0,
            },
            "required_observables": {},
            "canonical_required_observables_guard": {
                "complete": False,
                "missing": [f"guard_exception:{type(exc).__name__}:{exc}"],
                "mode": "FAIL_CLOSED_EVIDENCE_ONLY",
            },
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    encoded = base64.b64encode(json.dumps(receipt, sort_keys=True).encode("utf-8")).decode("ascii")
    print("T4_G2_PIPEWIRE_RECEIPT_B64=" + encoded)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt.get("result") == "NO_COUNTEREXAMPLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
