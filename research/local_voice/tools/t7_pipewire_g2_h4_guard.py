#!/usr/bin/env python3
"""Fail-closed H4 guard for Trigger-7 PipeWire G2 cancellation evidence.

This is an evidence-validity wrapper around t7_pipewire_monitor_cancel_analyze.py.
It prevents a false green where the post-cancel observation interval exists but
the exact local-TTS source itself is silent there. Before delegating to the
v2 analyzer, the guard requires a predeclared post-bound observation interval
and a minimum fraction of that interval to contain source-active *and*
control-monitor-correlated old-source audio.

Research/evidence tool only. It cannot mint runtime or product credit.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any

SCHEMA = "T7_PIPEWIRE_G2_H4_DISCRIMINATIVE_GUARD/v1"
DEFAULT_MIN_POST_BOUND_OBSERVATION_MS = 500.0
DEFAULT_MIN_POST_BOUND_ACTIVE_RATIO = 0.40


def _load_analyzer():
    path = Path(__file__).with_name("t7_pipewire_monitor_cancel_analyze.py")
    name = "t7_pipewire_monitor_cancel_analyze_h4_delegate"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"ANALYZER_IMPORT_SPEC_FAILED:{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _terminal(output: Path, receipt: dict[str, Any], classification: str, reason: str) -> int:
    receipt["pass"] = False
    receipt["classification"] = classification
    receipt["reason"] = reason
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--control", type=Path, required=True)
    p.add_argument("--cancel", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cancel-offset-ms", type=float, required=True)
    p.add_argument("--max-inflight-ms", type=float, required=True)
    p.add_argument("--required-postroll-ms", type=float, default=500.0)
    p.add_argument("--window-ms", type=float, default=20.0)
    p.add_argument("--correlation-threshold", type=float, default=0.80)
    p.add_argument("--source-rms-floor", type=float, default=0.003)
    p.add_argument("--capture-rms-ratio-floor", type=float, default=0.10)
    p.add_argument(
        "--min-post-bound-observation-ms",
        type=float,
        default=DEFAULT_MIN_POST_BOUND_OBSERVATION_MS,
    )
    p.add_argument(
        "--min-post-bound-active-ratio",
        type=float,
        default=DEFAULT_MIN_POST_BOUND_ACTIVE_RATIO,
    )
    args, _unknown = p.parse_known_args(argv)

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "trigger": "7",
        "research_id": "T7-20260902-PIPEWIRE-MONITOR-CANCEL-G2",
        "semantic_key": "0d83f7d13c1d8f91686cf94070f73d901a49018b40a9c058d1949af094655bff",
        "scope": "EVIDENCE_VALIDITY_GUARD_ONLY__ZERO_RUNTIME_OR_ACCEPTANCE_CREDIT",
        "pass": False,
    }

    try:
        if args.cancel_offset_ms <= 0:
            raise ValueError("--cancel-offset-ms must be > 0")
        if args.max_inflight_ms < 0:
            raise ValueError("--max-inflight-ms must be >= 0")
        if args.required_postroll_ms <= 0:
            raise ValueError("--required-postroll-ms must be > 0")
        if args.min_post_bound_observation_ms < 500.0:
            raise ValueError("--min-post-bound-observation-ms must be >= 500 for G2 promotion")
        if not 0 < args.min_post_bound_active_ratio <= 1:
            raise ValueError("--min-post-bound-active-ratio must be in (0,1]")
        if args.window_ms <= 0:
            raise ValueError("--window-ms must be > 0")

        analyzer = _load_analyzer()
        source = analyzer.load_pcm16_wav(args.source)
        control = analyzer.load_pcm16_wav(args.control)
        if source.rate != control.rate or source.channels != control.channels:
            return _terminal(
                args.output,
                receipt,
                "EVIDENCE_INVALID_H4_SOURCE_CONTROL_FORMAT_MISMATCH",
                "H4 guard refuses resampling or channel reinterpretation",
            )

        rate = source.rate
        cancel_frame = int(round(args.cancel_offset_ms * rate / 1000.0))
        requested_probe = int(round(400.0 * rate / 1000.0))
        cancel_probe_limit = max(128, int(cancel_frame * 0.80))
        probe_frames = min(requested_probe, cancel_probe_limit, source.frames)
        if probe_frames < 128:
            return _terminal(
                args.output,
                receipt,
                "EVIDENCE_INVALID_H4_ALIGNMENT_PROBE_TOO_SHORT",
                "cancel occurs too early to bind an independent pre-cancel source/control alignment",
            )

        control_offset, control_corr = analyzer.fft_alignment_offset(
            source.mono, control.mono, probe_frames
        )
        if control_corr < args.correlation_threshold:
            return _terminal(
                args.output,
                receipt,
                "EVIDENCE_INVALID_H4_CONTROL_ALIGNMENT",
                "source->control alignment correlation is below the predeclared threshold",
            )

        bound_end_ms = args.cancel_offset_ms + args.max_inflight_ms
        observation_end_ms = bound_end_ms + args.min_post_bound_observation_ms
        start_frame = int(math.ceil(bound_end_ms * rate / 1000.0))
        end_frame = int(math.ceil(observation_end_ms * rate / 1000.0))
        if end_frame > source.frames:
            return _terminal(
                args.output,
                receipt,
                "EVIDENCE_INVALID_H4_SOURCE_TOO_SHORT_FOR_DISCRIMINATIVE_POST_BOUND_INTERVAL",
                "source does not extend through the predeclared H4 post-bound observation interval",
            )
        if control_offset + end_frame > control.frames:
            return _terminal(
                args.output,
                receipt,
                "EVIDENCE_INVALID_H4_CONTROL_TOO_SHORT_FOR_DISCRIMINATIVE_POST_BOUND_INTERVAL",
                "control monitor capture does not cover the H4 post-bound observation interval",
            )

        rows = analyzer.scan_correlated_windows(
            source=source.mono,
            capture=control.mono,
            capture_offset=control_offset,
            sample_rate=rate,
            start_source_frame=start_frame,
            end_source_frame=end_frame,
            window_ms=args.window_ms,
            corr_threshold=args.correlation_threshold,
            source_rms_floor=args.source_rms_floor,
            capture_rms_ratio_floor=args.capture_rms_ratio_floor,
        )
        complete_rows = [
            row
            for row in rows
            if (row["source_end_ms"] - row["source_start_ms"]) >= args.window_ms * 0.99
        ]
        active_rows = [row for row in complete_rows if row["source_active"]]
        correlated_active_rows = [row for row in active_rows if row["old_audio_present"]]
        eligible_ms = sum(row["source_end_ms"] - row["source_start_ms"] for row in complete_rows)
        active_ms = sum(row["source_end_ms"] - row["source_start_ms"] for row in active_rows)
        correlated_active_ms = sum(
            row["source_end_ms"] - row["source_start_ms"] for row in correlated_active_rows
        )
        required_active_ms = args.min_post_bound_observation_ms * args.min_post_bound_active_ratio

        receipt["h4_guard"] = {
            "control_alignment_offset_frames": control_offset,
            "control_alignment_correlation": control_corr,
            "declared_bound_end_ms": bound_end_ms,
            "min_post_bound_observation_ms_predeclared": args.min_post_bound_observation_ms,
            "min_post_bound_active_ratio_predeclared": args.min_post_bound_active_ratio,
            "required_correlated_active_ms": required_active_ms,
            "eligible_complete_window_ms": eligible_ms,
            "source_active_ms": active_ms,
            "control_correlated_active_ms": correlated_active_ms,
            "complete_window_count": len(complete_rows),
            "source_active_window_count": len(active_rows),
            "control_correlated_active_window_count": len(correlated_active_rows),
        }
        if eligible_ms + 1e-6 < args.min_post_bound_observation_ms:
            return _terminal(
                args.output,
                receipt,
                "EVIDENCE_INVALID_H4_INSUFFICIENT_COMPLETE_POST_BOUND_WINDOWS",
                "H4 interval exists nominally but lacks the predeclared amount of complete analyzable windows",
            )
        if correlated_active_ms + 1e-6 < required_active_ms:
            return _terminal(
                args.output,
                receipt,
                "EVIDENCE_INVALID_H4_INSUFFICIENT_POST_BOUND_DISCRIMINATIVE_AUDIO",
                "full-playback control does not demonstrate enough source-active, source-correlated old-TTS audio after the cancel bound",
            )

        # Delegate to the canonical v2 analyzer only after H4 evidence validity passes.
        delegate_argv = list(argv or [])
        strip_names = {"--min-post-bound-observation-ms", "--min-post-bound-active-ratio"}
        filtered: list[str] = []
        i = 0
        while i < len(delegate_argv):
            token = delegate_argv[i]
            if token in strip_names:
                i += 2
                continue
            filtered.append(token)
            i += 1
        rc = analyzer.main(filtered)
        if not args.output.exists():
            return _terminal(
                args.output,
                receipt,
                "EVIDENCE_INVALID_H4_DELEGATE_NO_RECEIPT",
                "canonical analyzer returned without a receipt",
            )
        delegated = json.loads(args.output.read_text(encoding="utf-8"))
        delegated["h4_discriminative_guard"] = receipt["h4_guard"]
        delegated["h4_discriminative_guard"]["pass"] = True
        delegated["h4_discriminative_guard"]["schema"] = SCHEMA
        delegated.setdefault("explicit_zero_credit", {})["runtime_credit_from_h4_guard"] = 0
        args.output.write_text(json.dumps(delegated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return rc
    except Exception as exc:
        return _terminal(
            args.output,
            receipt,
            "EVIDENCE_INVALID_H4_GUARD_INPUT_OR_ENVIRONMENT",
            f"{type(exc).__name__}: {exc}",
        )


if __name__ == "__main__":
    raise SystemExit(main())
