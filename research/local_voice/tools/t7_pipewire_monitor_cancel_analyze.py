#!/usr/bin/env python3
"""Analyze Trigger-7 Generation-2 PipeWire monitor cancellation evidence.

Research/evidence tool only. It does not control playback and cannot mint runtime
or product credit. It compares:
  1. the exact locally-generated source WAV,
  2. a full-playback PipeWire monitor capture (control), and
  3. a cancellation PipeWire monitor capture.

The caller must provide the causal cancellation offset from playback start and a
predeclared maximum in-flight tail derived from the PipeWire graph/latency
preflight. The tool aligns monitor captures to the source, verifies that the
control actually covers the source, requires an explicit post-bound observation
window for the cancellation capture, scans fixed windows for source-correlated
old-packet audio, and emits a JSON measurement receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = "T7_PIPEWIRE_MONITOR_CANCEL_ANALYSIS/v2"
DEFAULT_REQUIRED_POSTROLL_MS = 500.0
DEFAULT_MIN_CONTROL_CORRELATED_WINDOW_RATIO = 0.90


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _numpy():
    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "numpy is required for this research analyzer; install it only "
            "inside the disposable research/runtime sandbox"
        ) from exc
    return np


@dataclass(frozen=True)
class WavData:
    path: Path
    rate: int
    channels: int
    sample_width: int
    frames: int
    mono: Any
    sha256: str


def load_pcm16_wav(path: Path) -> WavData:
    np = _numpy()
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.getnframes()
        comptype = wf.getcomptype()
        raw = wf.readframes(frames)
    if comptype != "NONE":
        raise ValueError(f"{path}: compressed WAV is unsupported ({comptype})")
    if width != 2:
        raise ValueError(f"{path}: expected PCM16 WAV, sample width={width}")
    if channels < 1:
        raise ValueError(f"{path}: invalid channel count {channels}")
    arr = np.frombuffer(raw, dtype="<i2").astype(np.float64)
    if arr.size != frames * channels:
        raise ValueError(f"{path}: PCM frame count mismatch")
    arr = arr.reshape((-1, channels))
    mono = arr.mean(axis=1) / 32768.0
    return WavData(
        path=path,
        rate=rate,
        channels=channels,
        sample_width=width,
        frames=frames,
        mono=mono,
        sha256=sha256_file(path),
    )


def rms(x: Any) -> float:
    np = _numpy()
    if len(x) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x), dtype=np.float64)))


def normalized_corr(a: Any, b: Any) -> float | None:
    np = _numpy()
    n = min(len(a), len(b))
    if n < 8:
        return None
    a = np.asarray(a[:n], dtype=np.float64)
    b = np.asarray(b[:n], dtype=np.float64)
    a = a - float(a.mean())
    b = b - float(b.mean())
    denom = math.sqrt(float(np.dot(a, a)) * float(np.dot(b, b)))
    if denom <= 1e-15:
        return None
    return float(np.dot(a, b) / denom)


def fft_alignment_offset(reference: Any, captured: Any, probe_frames: int) -> tuple[int, float]:
    """Return capture index where reference[0] best aligns and a peak score proxy."""
    np = _numpy()
    probe_frames = min(probe_frames, len(reference))
    if probe_frames < 128:
        raise ValueError("alignment probe is too short")
    ref = np.asarray(reference[:probe_frames], dtype=np.float64)
    cap = np.asarray(captured, dtype=np.float64)
    if len(cap) < probe_frames:
        raise ValueError("capture is shorter than alignment probe")

    ref = ref - float(ref.mean())
    cap = cap - float(cap.mean())
    conv_len = len(cap) + len(ref) - 1
    nfft = 1 << (conv_len - 1).bit_length()
    c = np.fft.irfft(
        np.fft.rfft(cap, n=nfft) * np.fft.rfft(ref[::-1], n=nfft),
        n=nfft,
    )[:conv_len]
    valid_start = probe_frames - 1
    valid_end = len(cap)
    valid = c[valid_start:valid_end]
    if valid.size == 0:
        raise ValueError("no valid alignment positions")
    rel = int(np.argmax(np.abs(valid)))
    offset = rel
    seg = cap[offset : offset + probe_frames]
    score = normalized_corr(ref, seg)
    return offset, float(score if score is not None else 0.0)


def scan_correlated_windows(
    *,
    source: Any,
    capture: Any,
    capture_offset: int,
    sample_rate: int,
    start_source_frame: int,
    end_source_frame: int,
    window_ms: float,
    corr_threshold: float,
    source_rms_floor: float,
    capture_rms_ratio_floor: float,
) -> list[dict[str, Any]]:
    np = _numpy()
    window = max(64, int(round(sample_rate * window_ms / 1000.0)))
    rows: list[dict[str, Any]] = []
    pos = max(0, start_source_frame)
    end_source_frame = min(end_source_frame, len(source))
    while pos < end_source_frame:
        stop = min(pos + window, end_source_frame)
        cap_start = capture_offset + pos
        cap_stop = capture_offset + stop
        if cap_start < 0 or cap_stop > len(capture):
            break
        src = np.asarray(source[pos:stop], dtype=np.float64)
        obs = np.asarray(capture[cap_start:cap_stop], dtype=np.float64)
        src_rms = rms(src)
        obs_rms = rms(obs)
        corr = normalized_corr(src, obs)
        ratio = obs_rms / src_rms if src_rms > 1e-12 else None
        source_active = src_rms >= source_rms_floor
        old_audio_present = bool(
            source_active
            and corr is not None
            and corr >= corr_threshold
            and ratio is not None
            and ratio >= capture_rms_ratio_floor
        )
        rows.append(
            {
                "source_start_frame": int(pos),
                "source_end_frame": int(stop),
                "source_start_ms": pos * 1000.0 / sample_rate,
                "source_end_ms": stop * 1000.0 / sample_rate,
                "source_rms": src_rms,
                "capture_rms": obs_rms,
                "capture_to_source_rms_ratio": ratio,
                "correlation": corr,
                "source_active": source_active,
                "old_audio_present": old_audio_present,
            }
        )
        pos += window
    return rows


def _write_terminal(receipt: dict[str, Any], output: Path, classification: str, reason: str) -> int:
    receipt["pass"] = False
    receipt["classification"] = classification
    receipt["reason"] = reason
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--control", type=Path, required=True)
    p.add_argument("--cancel", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--cancel-offset-ms",
        type=float,
        required=True,
        help="Causal cancel request offset from playback start, from external monotonic trace.",
    )
    p.add_argument(
        "--max-inflight-ms",
        type=float,
        required=True,
        help="Predeclared maximum acceptable graph tail from PipeWire preflight.",
    )
    p.add_argument(
        "--required-postroll-ms",
        type=float,
        default=DEFAULT_REQUIRED_POSTROLL_MS,
        help="Predeclared observation window required after the in-flight bound.",
    )
    p.add_argument(
        "--min-control-correlated-window-ratio",
        type=float,
        default=DEFAULT_MIN_CONTROL_CORRELATED_WINDOW_RATIO,
        help="Minimum fraction of active full-control windows that must correlate to the source.",
    )
    p.add_argument("--alignment-probe-ms", type=float, default=400.0)
    p.add_argument("--window-ms", type=float, default=20.0)
    p.add_argument("--correlation-threshold", type=float, default=0.80)
    p.add_argument("--source-rms-floor", type=float, default=0.003)
    p.add_argument("--capture-rms-ratio-floor", type=float, default=0.10)
    p.add_argument("--voice-output-packet-id")
    p.add_argument("--f2-subject-sha")
    args = p.parse_args(argv)

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "semantic_key": "0d83f7d13c1d8f91686cf94070f73d901a49018b40a9c058d1949af094655bff",
        "research_id": "T7-20260902-PIPEWIRE-MONITOR-CANCEL-G2",
        "trigger": "7",
        "scope": "MEASUREMENT_ONLY__NO_RUNTIME_OR_ACCEPTANCE_CREDIT_BY_TOOL",
        "voice_output_packet_id": args.voice_output_packet_id,
        "f2_subject_sha": args.f2_subject_sha,
        "pass": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    try:
        if args.cancel_offset_ms <= 0:
            raise ValueError("--cancel-offset-ms must be > 0")
        if args.max_inflight_ms < 0:
            raise ValueError("--max-inflight-ms must be >= 0")
        if args.required_postroll_ms <= 0:
            raise ValueError("--required-postroll-ms must be > 0")
        if not 0 < args.min_control_correlated_window_ratio <= 1:
            raise ValueError("--min-control-correlated-window-ratio must be in (0,1]")
        if not 0 < args.correlation_threshold <= 1:
            raise ValueError("--correlation-threshold must be in (0,1]")
        if not 0 < args.capture_rms_ratio_floor:
            raise ValueError("--capture-rms-ratio-floor must be > 0")

        source = load_pcm16_wav(args.source)
        control = load_pcm16_wav(args.control)
        cancel = load_pcm16_wav(args.cancel)
        if not (source.rate == control.rate == cancel.rate):
            raise ValueError(
                f"sample-rate mismatch source/control/cancel="
                f"{source.rate}/{control.rate}/{cancel.rate}; fail closed instead of resampling"
            )
        if not (source.channels == control.channels == cancel.channels):
            raise ValueError(
                f"channel mismatch source/control/cancel="
                f"{source.channels}/{control.channels}/{cancel.channels}; fail closed"
            )
        rate = source.rate

        receipt["files"] = {
            "source": {"path": str(source.path), "sha256": source.sha256, "rate": source.rate, "channels": source.channels, "frames": source.frames},
            "control": {"path": str(control.path), "sha256": control.sha256, "rate": control.rate, "channels": control.channels, "frames": control.frames},
            "cancel": {"path": str(cancel.path), "sha256": cancel.sha256, "rate": cancel.rate, "channels": cancel.channels, "frames": cancel.frames},
        }

        cancel_frame = int(round(args.cancel_offset_ms * rate / 1000.0))
        if cancel_frame >= source.frames:
            raise ValueError("cancel offset lies at/after source end")
        requested_probe = int(round(args.alignment_probe_ms * rate / 1000.0))
        cancel_probe_limit = max(128, int(cancel_frame * 0.80))
        probe_frames = min(requested_probe, cancel_probe_limit, source.frames)
        if probe_frames < 128:
            raise ValueError("cancel occurs too early for an independent pre-cancel alignment")

        control_offset, control_corr = fft_alignment_offset(source.mono, control.mono, probe_frames)
        cancel_offset, cancel_corr = fft_alignment_offset(source.mono, cancel.mono, probe_frames)
        receipt["alignment"] = {
            "probe_frames": probe_frames,
            "probe_ms": probe_frames * 1000.0 / rate,
            "control_capture_offset_frames": control_offset,
            "control_capture_offset_ms": control_offset * 1000.0 / rate,
            "control_probe_correlation": control_corr,
            "cancel_capture_offset_frames": cancel_offset,
            "cancel_capture_offset_ms": cancel_offset * 1000.0 / rate,
            "cancel_probe_correlation": cancel_corr,
        }

        control_valid = control_corr >= args.correlation_threshold and cancel_corr >= args.correlation_threshold
        receipt["control_valid"] = control_valid
        if not control_valid:
            return _write_terminal(
                receipt,
                args.output,
                "EVIDENCE_INVALID_CONTROL_OR_PRECANCEL_ALIGNMENT",
                "source->control or source->cancel pre-cancel correlation did not meet the declared threshold",
            )

        required_source_end_ms = args.cancel_offset_ms + args.max_inflight_ms + args.required_postroll_ms
        required_source_end_frame = int(math.ceil(required_source_end_ms * rate / 1000.0))
        required_control_capture_end_frame = control_offset + source.frames
        required_cancel_capture_end_frame = cancel_offset + required_source_end_frame
        receipt["coverage"] = {
            "required_postroll_ms_predeclared": args.required_postroll_ms,
            "required_source_timeline_end_ms": required_source_end_ms,
            "required_source_timeline_end_frame": required_source_end_frame,
            "source_frames": source.frames,
            "control_capture_frames": control.frames,
            "required_control_capture_end_frame": required_control_capture_end_frame,
            "cancel_capture_frames": cancel.frames,
            "required_cancel_capture_end_frame": required_cancel_capture_end_frame,
        }
        if required_source_end_frame > source.frames:
            return _write_terminal(
                receipt,
                args.output,
                "EVIDENCE_INVALID_SOURCE_TOO_SHORT_FOR_POST_BOUND_OBSERVATION",
                "source does not extend through cancel + max-inflight + predeclared post-roll",
            )
        if required_control_capture_end_frame > control.frames:
            return _write_terminal(
                receipt,
                args.output,
                "EVIDENCE_INVALID_INSUFFICIENT_CONTROL_CAPTURE",
                "control capture does not cover the complete aligned source waveform",
            )
        if required_cancel_capture_end_frame > cancel.frames:
            return _write_terminal(
                receipt,
                args.output,
                "EVIDENCE_INVALID_INSUFFICIENT_POST_BOUND_CAPTURE",
                "cancel capture does not cover cancel + max-inflight + predeclared post-roll",
            )

        control_windows = scan_correlated_windows(
            source=source.mono,
            capture=control.mono,
            capture_offset=control_offset,
            sample_rate=rate,
            start_source_frame=0,
            end_source_frame=source.frames,
            window_ms=args.window_ms,
            corr_threshold=args.correlation_threshold,
            source_rms_floor=args.source_rms_floor,
            capture_rms_ratio_floor=args.capture_rms_ratio_floor,
        )
        active_control_windows = [row for row in control_windows if row["source_active"]]
        correlated_control_windows = [row for row in active_control_windows if row["old_audio_present"]]
        control_window_ratio = (
            len(correlated_control_windows) / len(active_control_windows)
            if active_control_windows
            else 0.0
        )
        receipt["control_full_readback"] = {
            "active_source_window_count": len(active_control_windows),
            "correlated_window_count": len(correlated_control_windows),
            "correlated_window_ratio": control_window_ratio,
            "minimum_correlated_window_ratio_predeclared": args.min_control_correlated_window_ratio,
        }
        if not active_control_windows or control_window_ratio < args.min_control_correlated_window_ratio:
            return _write_terminal(
                receipt,
                args.output,
                "EVIDENCE_INVALID_CONTROL_FULL_PLAYBACK_READBACK",
                "full control monitor capture does not sufficiently correlate with the complete active source waveform",
            )

        bound_end_ms = args.cancel_offset_ms + args.max_inflight_ms
        windows = scan_correlated_windows(
            source=source.mono,
            capture=cancel.mono,
            capture_offset=cancel_offset,
            sample_rate=rate,
            start_source_frame=cancel_frame,
            end_source_frame=required_source_end_frame,
            window_ms=args.window_ms,
            corr_threshold=args.correlation_threshold,
            source_rms_floor=args.source_rms_floor,
            capture_rms_ratio_floor=args.capture_rms_ratio_floor,
        )
        present = [row for row in windows if row["old_audio_present"]]
        last_old_end_ms = max((row["source_end_ms"] for row in present), default=args.cancel_offset_ms)
        observed_tail_ms = max(0.0, last_old_end_ms - args.cancel_offset_ms)
        post_bound_observed = [row for row in windows if row["source_start_ms"] >= bound_end_ms]
        post_bound = [row for row in post_bound_observed if row["old_audio_present"]]
        max_post_bound_corr = max(
            (row["correlation"] for row in post_bound_observed if row["correlation"] is not None),
            default=None,
        )

        receipt["parameters"] = {
            "cancel_offset_ms": args.cancel_offset_ms,
            "max_inflight_ms_predeclared": args.max_inflight_ms,
            "required_postroll_ms_predeclared": args.required_postroll_ms,
            "window_ms": args.window_ms,
            "correlation_threshold_predeclared": args.correlation_threshold,
            "source_rms_floor_predeclared": args.source_rms_floor,
            "capture_rms_ratio_floor_predeclared": args.capture_rms_ratio_floor,
            "min_control_correlated_window_ratio_predeclared": args.min_control_correlated_window_ratio,
        }
        receipt["measurement"] = {
            "correlated_windows_after_cancel": len(present),
            "last_old_audio_source_timeline_end_ms": last_old_end_ms,
            "observed_cancel_to_last_old_audio_tail_ms": observed_tail_ms,
            "declared_bound_end_ms": bound_end_ms,
            "post_bound_observation_window_count": len(post_bound_observed),
            "post_bound_old_audio_window_count": len(post_bound),
            "max_post_bound_correlation": max_post_bound_corr,
        }
        receipt["window_scan"] = windows

        if not post_bound_observed:
            return _write_terminal(
                receipt,
                args.output,
                "EVIDENCE_INVALID_NO_POST_BOUND_OBSERVATION_WINDOWS",
                "no complete analyzable monitor window exists after the declared in-flight bound",
            )

        pass_tail = observed_tail_ms <= args.max_inflight_ms + args.window_ms
        pass_post_bound = len(post_bound) == 0
        receipt["invariants"] = {
            "CONTROL_VALID": control_valid,
            "CONTROL_FULL_PLAYBACK_READBACK": True,
            "POST_BOUND_COVERAGE": True,
            "BOUNDED_TAIL": pass_tail,
            "NO_POST_BOUND_OLD_AUDIO": pass_post_bound,
            "PACKET_FENCE": "NOT_MEASURED_BY_AUDIO_ANALYZER__BIND_EXTERNAL_PACKET_RECEIPT",
            "CLEANUP": "NOT_MEASURED_BY_AUDIO_ANALYZER__BIND_EXTERNAL_PIPEWIRE_RECEIPT",
        }
        receipt["pass"] = bool(control_valid and pass_tail and pass_post_bound)
        receipt["classification"] = (
            "NO_COUNTEREXAMPLE_AT_AUDIO_CORRELATION_SCOPE"
            if receipt["pass"]
            else "PRODUCT_NEGATIVE_OLD_PACKET_AUDIO_PERSISTS_BEYOND_DECLARED_BOUND"
        )
        receipt["explicit_zero_credit"] = {
            "runtime_credit_from_analyzer": 0,
            "packet_fence_credit_without_external_receipt": 0,
            "cleanup_credit_without_external_receipt": 0,
            "physical_speaker": 0,
            "human_heard_output": 0,
            "physical_microphone": 0,
            "whole_voice_e2e": 0,
            "whole_product": 0,
        }
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        return 0 if receipt["pass"] else 1
    except Exception as exc:
        receipt["classification"] = "EVIDENCE_INVALID_ANALYZER_INPUT_OR_ENVIRONMENT"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())