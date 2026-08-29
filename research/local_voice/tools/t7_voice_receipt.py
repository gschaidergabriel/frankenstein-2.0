#!/usr/bin/env python3
"""Validate and summarize Trigger-7 realtime voice benchmark receipts.

Input is newline-delimited JSON. Exactly one `run` record is required and one or
more `turn` records. This tool intentionally knows nothing about a particular
ASR, LLM, or TTS implementation; it only converts causal timestamps and safety
counters into comparable evidence.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
REQUIRED_TS = ("user_speech_end", "first_audio_played")
OPTIONAL_DELTAS = {
    "speech_end_to_first_audio_ms": ("user_speech_end", "first_audio_played"),
    "endpoint_to_asr_final_ms": ("user_speech_end", "asr_final"),
    "inference_ttft_ms": ("inference_request", "inference_first_token"),
    "inference_to_speakable_clause_ms": ("inference_request", "first_speakable_clause"),
    "tts_ttfa_ms": ("tts_request", "tts_first_audio_ready"),
    "audio_queue_ms": ("tts_first_audio_ready", "first_audio_played"),
    "barge_in_to_stop_ms": ("barge_in_detected", "playback_stopped"),
}
NETWORK_COUNTERS = (
    "outbound_model_api_calls",
    "outbound_asr_api_calls",
    "outbound_tts_api_calls",
)


class ReceiptError(ValueError):
    pass


def _finite_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReceiptError(f"{field} must be an integer nanosecond timestamp")
    if value < 0:
        raise ReceiptError(f"{field} must be non-negative")
    return value


def _delta_ms(ts: dict[str, Any], start: str, end: str) -> float | None:
    if start not in ts or end not in ts:
        return None
    a = _finite_int(ts[start], f"timestamps_ns.{start}")
    b = _finite_int(ts[end], f"timestamps_ns.{end}")
    if b < a:
        raise ReceiptError(f"causal timestamp inversion: {end} < {start}")
    return (b - a) / 1_000_000.0


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReceiptError(f"line {lineno}: invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise ReceiptError(f"line {lineno}: record must be an object")
        records.append(obj)
    if not records:
        raise ReceiptError("receipt is empty")
    return records


def summarize(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records = list(records)
    runs = [r for r in records if r.get("kind") == "run"]
    turns = [r for r in records if r.get("kind") == "turn"]
    unknown = [r for r in records if r.get("kind") not in {"run", "turn"}]
    if len(runs) != 1:
        raise ReceiptError(f"expected exactly one run record, got {len(runs)}")
    if not turns:
        raise ReceiptError("expected at least one turn record")
    if unknown:
        raise ReceiptError("unknown record kind present")

    run = runs[0]
    if run.get("schema_version") != SCHEMA_VERSION:
        raise ReceiptError("unsupported schema_version")
    if run.get("language") != "de":
        raise ReceiptError("Trigger-7 v1 benchmark receipt requires language='de'")
    mode = run.get("runtime_mode")
    if mode not in {"LOCAL_SOLO", "CLAUDE_AUGMENTED"}:
        raise ReceiptError("runtime_mode must be LOCAL_SOLO or CLAUDE_AUGMENTED")

    run_network = run.get("network_counters", {})
    if not isinstance(run_network, dict):
        raise ReceiptError("network_counters must be an object")
    network_totals: dict[str, int] = {}
    for key in NETWORK_COUNTERS:
        value = run_network.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ReceiptError(f"network_counters.{key} must be a non-negative integer")
        network_totals[key] = value

    metric_values: dict[str, list[float]] = {name: [] for name in OPTIONAL_DELTAS}
    scenario_counts: Counter[str] = Counter()
    cancellation_violations = 0
    unheard_commit_violations = 0
    duplicate_audio_violations = 0
    replay_audio_violations = 0
    incomplete_required = 0

    for turn in turns:
        if turn.get("schema_version") != SCHEMA_VERSION:
            raise ReceiptError("turn has unsupported schema_version")
        ts = turn.get("timestamps_ns")
        if not isinstance(ts, dict):
            raise ReceiptError("turn.timestamps_ns must be an object")
        if any(k not in ts for k in REQUIRED_TS):
            incomplete_required += 1
        scenario = str(turn.get("scenario", "UNSPECIFIED"))
        scenario_counts[scenario] += 1
        for name, (start, end) in OPTIONAL_DELTAS.items():
            value = _delta_ms(ts, start, end)
            if value is not None:
                metric_values[name].append(value)

        flags = turn.get("flags", {})
        if not isinstance(flags, dict):
            raise ReceiptError("turn.flags must be an object")
        if flags.get("barge_in_expected") and not flags.get("generation_cancelled", False):
            cancellation_violations += 1
        if flags.get("unheard_output_committed", False):
            unheard_commit_violations += 1
        if flags.get("duplicate_audio_detected", False):
            duplicate_audio_violations += 1
        if flags.get("replayed_audio_detected", False):
            replay_audio_violations += 1

    metrics: dict[str, Any] = {}
    for name, values in metric_values.items():
        metrics[name] = {
            "n": len(values),
            "p50": _percentile(values, 0.50),
            "p95": _percentile(values, 0.95),
            "p99": _percentile(values, 0.99),
            "max": max(values) if values else None,
        }

    local_solo_network_ok = all(network_totals[k] == 0 for k in NETWORK_COUNTERS)
    causal_commit_ok = (
        cancellation_violations == 0
        and unheard_commit_violations == 0
        and duplicate_audio_violations == 0
        and replay_audio_violations == 0
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run.get("run_id"),
        "runtime_mode": mode,
        "language": "de",
        "turn_count": len(turns),
        "scenario_counts": dict(sorted(scenario_counts.items())),
        "metrics_ms": metrics,
        "network_counters": network_totals,
        "local_solo_zero_external_inference": local_solo_network_ok if mode == "LOCAL_SOLO" else None,
        "violations": {
            "incomplete_required_turn_timestamps": incomplete_required,
            "barge_in_without_generation_cancel": cancellation_violations,
            "unheard_output_committed": unheard_commit_violations,
            "duplicate_audio_detected": duplicate_audio_violations,
            "replayed_audio_detected": replay_audio_violations,
        },
        "causal_voice_commit_ok": causal_commit_ok,
        "evidence_note": "This receipt summarizes observed timestamps/counters only. It does not self-award V4/V5/V6 or quality parity.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path, help="input JSONL receipt")
    parser.add_argument("--out", type=Path, help="optional JSON summary output path")
    args = parser.parse_args()
    try:
        result = summarize(load_jsonl(args.receipt))
    except ReceiptError as exc:
        parser.error(str(exc))
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
