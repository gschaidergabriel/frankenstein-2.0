#!/usr/bin/env python3
"""Bounded Trigger-4 G2 PipeWire cancel-tail discriminator.

This is a research/runtime falsifier harness, not a new playback, packet, state,
effect, or Voice authority.  Promotion-bearing execution requires two exact
locally generated PCM subjects (old/new output generations), exact local TTS
runtime/model hashes, an exact F2 source identity, and a real sandbox-local
PipeWire-Pulse null-sink monitor.

Repository tests exercise only deterministic analysis and fail-closed logic.
They mint no PipeWire/runtime/physical/whole-voice credit.
"""
from __future__ import annotations

import argparse
from array import array
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

SCHEMA = "F2_T4_VOICE_PIPEWIRE_CANCEL_TAIL_G2/v1"
CLASSIFICATION = "CANDIDATE_FALSIFIER_PIPEWIRE_CANCEL_TAIL_ONLY"
DEFAULT_CHANNELS = 1
FRAME_MS = 20
POST_CANCEL_MS = 650
MIN_POST_BOUND_QUIET_MS = 200


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _samples(blob: bytes) -> list[int]:
    if len(blob) % 2:
        raise ValueError("PCM must contain complete signed-16 samples")
    values = array("h")
    values.frombytes(blob)
    if sys.byteorder != "little":
        values.byteswap()
    return list(values)


def _corr(a: list[int], b: list[int]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    aa = sum(float(x) * x for x in a)
    bb = sum(float(x) * x for x in b)
    if aa <= 0.0 or bb <= 0.0:
        return 0.0
    return sum(float(x) * y for x, y in zip(a, b)) / math.sqrt(aa * bb)


@dataclass(frozen=True)
class Alignment:
    valid: bool
    method: str
    offset_samples: int | None
    score: float
    error_bound_ms: float


def align_pcm(source: bytes, capture: bytes, sample_rate: int) -> Alignment:
    """Identity-first alignment with bounded correlation fallback.

    Exact byte identity is preferred.  The fallback is intentionally strict and
    coarse: it is for discovering a stable same-waveform offset, not for hiding
    arbitrary resampling/format changes.  A promotion run that cannot establish
    a high-confidence binding is EVIDENCE_INVALID.
    """
    exact = capture.find(source)
    if exact >= 0 and exact % 2 == 0:
        return Alignment(True, "EXACT_PCM_SUBSTRING", exact // 2, 1.0, 0.0)

    src = _samples(source)
    cap = _samples(capture)
    if len(src) < sample_rate // 4 or len(cap) < len(src) // 4:
        return Alignment(False, "INSUFFICIENT_PCM", None, 0.0, 1000.0)

    stride = max(1, sample_rate // 200)  # ~5 ms sampling grid
    src_ds = src[::stride]
    cap_ds = cap[::stride]
    window = min(len(src_ds), 400)  # up to ~2 s signature
    if window < 50 or len(cap_ds) < window:
        return Alignment(False, "INSUFFICIENT_SIGNATURE", None, 0.0, 1000.0)
    signature = src_ds[:window]

    best_score = -1.0
    best_offset = 0
    for offset in range(0, len(cap_ds) - window + 1):
        score = _corr(signature, cap_ds[offset : offset + window])
        if score > best_score:
            best_score = score
            best_offset = offset
    valid = best_score >= 0.96
    return Alignment(
        valid,
        "COARSE_NORMALIZED_CORRELATION" if valid else "NO_HIGH_CONFIDENCE_ALIGNMENT",
        best_offset * stride if valid else None,
        max(0.0, best_score),
        1000.0 * stride / sample_rate,
    )


@dataclass(frozen=True)
class TailMeasurement:
    valid: bool
    last_correlated_capture_sample: int | None
    cancel_capture_sample: int
    cancel_to_last_old_sample_ms: float | None
    post_bound_quiet_ms: float
    matched_frames: int
    reason: str


def measure_cancel_tail(
    source: bytes,
    capture: bytes,
    *,
    source_offset_samples: int,
    sample_rate: int,
    cancel_capture_sample: int,
    frame_ms: int = FRAME_MS,
    corr_threshold: float = 0.94,
) -> TailMeasurement:
    src = _samples(source)
    cap = _samples(capture)
    frame = max(1, sample_rate * frame_ms // 1000)
    if source_offset_samples < 0 or source_offset_samples >= len(cap):
        return TailMeasurement(False, None, cancel_capture_sample, None, 0.0, 0, "offset_out_of_capture")

    matched = 0
    last_sample: int | None = None
    # Track the old waveform from its aligned beginning until it stops matching.
    for src_i in range(0, len(src) - frame + 1, frame):
        cap_i = source_offset_samples + src_i
        if cap_i + frame > len(cap):
            break
        score = _corr(src[src_i : src_i + frame], cap[cap_i : cap_i + frame])
        if score < corr_threshold:
            # Before the cancel wall, scheduling gaps can create one bad frame;
            # after cancel, the first sustained mismatch defines old-wave end.
            if cap_i >= cancel_capture_sample:
                break
            continue
        matched += 1
        last_sample = cap_i + frame - 1

    if last_sample is None:
        return TailMeasurement(False, None, cancel_capture_sample, None, 0.0, matched, "old_waveform_not_bound")
    tail_ms = 1000.0 * (last_sample - cancel_capture_sample) / sample_rate
    quiet_ms = 1000.0 * max(0, len(cap) - 1 - last_sample) / sample_rate
    return TailMeasurement(True, last_sample, cancel_capture_sample, tail_ms, quiet_ms, matched, "measured")


def _make_cortex(packet_id: str, planned_ms: int):
    # Import lazily so pure analysis tests can import the module with normal repo
    # PYTHONPATH rules and runtime execution stays bound to current product code.
    from frankenstein2.causal_identity import CausalIdentity
    from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
    from frankenstein2.voice_packet_cortex import VoicePacketCortex

    root = CausalIdentity(
        session_id="session-t4-pipewire-g2",
        agent_id="frankenstein-2",
        task_id="task-t4-pipewire-g2",
        turn_id="turn-output",
        causal_id="causal-t4-pipewire-g2",
        generation=2,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref="trigger4:pipewire-g2",
        input_sha256="e" * 64,
        provenance_refs=("trigger4:pipewire-g2-cancel-tail",),
    )
    session = VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id="causal-session-t4-pipewire-g2", generation=3, turn_id="turn-session"
        ),
        provenance_refs=("trigger4:pipewire-g2-session",),
    )
    cortex = VoicePacketCortex(session)
    cortex.queue_output(
        turn_id="turn-output",
        packet_id=packet_id,
        monotonic_ms=0,
        text_segment="lokal erzeugte Piper Ausgabe",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=planned_ms,
        sequence=0,
        cancellable=True,
    )
    cortex.advance_output(packet_id, playback_state="started", monotonic_ms=1, heard_fraction=0.0)
    return cortex


def _packet_state(cortex, packet_id: str) -> dict[str, Any]:
    packet = next(item for item in cortex.outputs if item.packet_id == packet_id)
    return packet.as_dict()


class PipeWireNullGraph:
    def __init__(self, sample_rate: int, channels: int = DEFAULT_CHANNELS) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.sink_name = f"f2_voice_g2_{os.getpid()}"
        self.module_id: str | None = None
        self.tmp = tempfile.TemporaryDirectory(prefix="f2-pipewire-g2-")
        self.root = Path(self.tmp.name)

    @staticmethod
    def available() -> bool:
        return all(shutil.which(cmd) for cmd in ("pactl", "pacat", "parec"))

    def _run(self, args: list[str], *, timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)

    def start(self) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("pactl/pacat/parec not all available")
        cp = self._run([
            "pactl", "load-module", "module-null-sink", f"sink_name={self.sink_name}",
            f"rate={self.sample_rate}", f"channels={self.channels}",
        ])
        if cp.returncode != 0 or not cp.stdout.strip().isdigit():
            raise RuntimeError(f"null sink creation failed: {cp.stderr.strip()}")
        self.module_id = cp.stdout.strip()
        sinks = self._run(["pactl", "list", "short", "sinks"]).stdout
        sources = self._run(["pactl", "list", "short", "sources"]).stdout
        sink_line = next((line for line in sinks.splitlines() if self.sink_name in line), "")
        monitor_line = next((line for line in sources.splitlines() if f"{self.sink_name}.monitor" in line), "")
        if not sink_line or not monitor_line:
            raise RuntimeError("created sink/monitor identity could not be enumerated")
        return {
            "module_id": self.module_id,
            "sink_identity": sink_line,
            "monitor_identity": monitor_line,
            "pipewire_version": self._version("pipewire"),
            "pipewire_pulse_version": self._version("pipewire-pulse"),
        }

    def _version(self, command: str) -> str:
        if not shutil.which(command):
            return "UNAVAILABLE"
        cp = self._run([command, "--version"])
        return (cp.stdout or cp.stderr).strip()[:500]

    def capture_playback(
        self,
        pcm: bytes,
        *,
        label: str,
        cancel_after_ms: int | None = None,
        cancel_hook=None,
    ) -> dict[str, Any]:
        path = self.root / f"{label}.raw"
        fp = path.open("wb")
        capture = subprocess.Popen([
            "parec", f"--device={self.sink_name}.monitor", "--format=s16le",
            f"--rate={self.sample_rate}", f"--channels={self.channels}", "--raw",
        ], stdout=fp, stderr=subprocess.PIPE)
        time.sleep(0.20)
        capture_ready_ns = time.monotonic_ns()
        player = subprocess.Popen([
            "pacat", "--playback", f"--device={self.sink_name}", "--format=s16le",
            f"--rate={self.sample_rate}", f"--channels={self.channels}", "--raw",
        ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        playback_start_ns = time.monotonic_ns()
        frame_bytes = max(2, self.sample_rate * self.channels * 2 * FRAME_MS // 1000)
        sent = 0
        cancel_request_ns = None
        player_terminal_ns = None
        try:
            assert player.stdin is not None
            for offset in range(0, len(pcm), frame_bytes):
                chunk = pcm[offset : offset + frame_bytes]
                player.stdin.write(chunk)
                player.stdin.flush()
                sent += len(chunk)
                elapsed_ms = 1000.0 * sent / (self.sample_rate * self.channels * 2)
                if cancel_after_ms is not None and elapsed_ms >= cancel_after_ms:
                    cancel_request_ns = time.monotonic_ns()
                    if cancel_hook is not None:
                        cancel_hook(cancel_request_ns)
                    player.send_signal(signal.SIGTERM)
                    try:
                        player.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        player.kill()
                        player.wait(timeout=2)
                    player_terminal_ns = time.monotonic_ns()
                    break
                time.sleep(FRAME_MS / 1000.0)
            else:
                player.stdin.close()
                player.wait(timeout=5)
                player_terminal_ns = time.monotonic_ns()
        finally:
            if player.poll() is None:
                player.kill()
                player.wait(timeout=2)
            time.sleep(POST_CANCEL_MS / 1000.0 if cancel_after_ms is not None else 0.25)
            if capture.poll() is None:
                capture.send_signal(signal.SIGTERM)
                try:
                    capture.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    capture.kill()
                    capture.wait(timeout=2)
            fp.close()
        blob = path.read_bytes()
        return {
            "label": label,
            "capture": blob,
            "capture_sha256": _sha(blob),
            "capture_ready_monotonic_ns": capture_ready_ns,
            "playback_start_monotonic_ns": playback_start_ns,
            "cancel_request_monotonic_ns": cancel_request_ns,
            "playback_terminal_monotonic_ns": player_terminal_ns,
            "source_bytes_sent_before_terminal": sent,
        }

    def close(self) -> None:
        try:
            if self.module_id is not None:
                self._run(["pactl", "unload-module", self.module_id])
                self.module_id = None
        finally:
            self.tmp.cleanup()


def _require_runtime_subjects(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    paths = tuple(Path(value) for value in (
        args.source_pcm, args.next_source_pcm, args.tts_runtime_binary, args.tts_model
    ))
    if any(not path.is_file() for path in paths):
        raise ValueError("promotion-bearing pulse mode requires source/next PCM and TTS runtime/model files")
    if paths[0].read_bytes() == paths[1].read_bytes():
        raise ValueError("old and new generation PCM must be distinguishable")
    if os.environ.get("F2_EXTERNAL_INFERENCE_API_CALLS") != "0":
        raise ValueError("pulse mode requires F2_EXTERNAL_INFERENCE_API_CALLS=0 evidence fence")
    return paths  # type: ignore[return-value]


def run_pulse(args: argparse.Namespace) -> dict[str, Any]:
    old_path, new_path, runtime_path, model_path = _require_runtime_subjects(args)
    old_pcm = old_path.read_bytes()
    new_pcm = new_path.read_bytes()
    if not old_pcm or not new_pcm or len(old_pcm) % 2 or len(new_pcm) % 2:
        raise ValueError("PCM subjects must be nonempty raw s16le")
    source_sha = os.environ.get("F2_SUBJECT_SHA") or os.environ.get("GITHUB_SHA")
    if not source_sha or source_sha == "LOCAL_UNBOUND":
        raise ValueError("pulse mode requires exact F2_SUBJECT_SHA or GITHUB_SHA")

    old_packet_id = "voice-output-g2-old"
    new_packet_id = "voice-output-g2-new"
    old_ms = int(1000 * len(old_pcm) / (args.sample_rate * args.channels * 2))
    cancel_ms = min(args.cancel_after_ms, max(FRAME_MS * 2, old_ms // 2))
    cortex = _make_cortex(old_packet_id, old_ms)
    graph = PipeWireNullGraph(args.sample_rate, args.channels)
    graph_info: dict[str, Any] = {}
    try:
        graph_info = graph.start()
        control = graph.capture_playback(old_pcm, label="control")
        control_alignment = align_pcm(old_pcm, control["capture"], args.sample_rate)
        if not control_alignment.valid or control_alignment.offset_samples is None:
            return _report(
                result="EVIDENCE_INVALID", failure_class="EVIDENCE_INVALID",
                source_sha=source_sha, old_path=old_path, new_path=new_path,
                runtime_path=runtime_path, model_path=model_path, graph_info=graph_info,
                control=control, control_alignment=control_alignment,
                reason="control_monitor_cannot_bind_source",
            )

        packet_terminal_ns: int | None = None
        packet_state: dict[str, Any] = {}

        def cancel_hook(cancel_ns: int) -> None:
            nonlocal packet_terminal_ns, packet_state
            monotonic_ms = max(2, int((cancel_ns - control["playback_start_monotonic_ns"]) / 1_000_000) + 2)
            cortex.cancel_for_barge_in(turn_id="turn-barge", monotonic_ms=monotonic_ms)
            packet_terminal_ns = time.monotonic_ns()
            packet_state = _packet_state(cortex, old_packet_id)

        cancel_run = graph.capture_playback(
            old_pcm, label="cancel", cancel_after_ms=cancel_ms, cancel_hook=cancel_hook
        )
        cancel_alignment = align_pcm(old_pcm[: max(2, min(len(old_pcm), args.sample_rate * args.channels * 2))], cancel_run["capture"], args.sample_rate)
        if not cancel_alignment.valid or cancel_alignment.offset_samples is None or cancel_run["cancel_request_monotonic_ns"] is None:
            return _report(
                result="EVIDENCE_INVALID", failure_class="EVIDENCE_INVALID",
                source_sha=source_sha, old_path=old_path, new_path=new_path,
                runtime_path=runtime_path, model_path=model_path, graph_info=graph_info,
                control=control, control_alignment=control_alignment,
                cancel_run=cancel_run, cancel_alignment=cancel_alignment,
                packet_state=packet_state, packet_terminal_ns=packet_terminal_ns,
                reason="cancel_monitor_cannot_bind_old_source",
            )
        cancel_capture_sample = int(
            (cancel_run["cancel_request_monotonic_ns"] - cancel_run["capture_ready_monotonic_ns"])
            * args.sample_rate / 1_000_000_000
        )
        tail = measure_cancel_tail(
            old_pcm, cancel_run["capture"], source_offset_samples=cancel_alignment.offset_samples,
            sample_rate=args.sample_rate, cancel_capture_sample=cancel_capture_sample,
        )

        new_cortex = _make_cortex(new_packet_id, int(1000 * len(new_pcm) / (args.sample_rate * args.channels * 2)))
        new_run = graph.capture_playback(new_pcm, label="new-generation")
        new_alignment = align_pcm(new_pcm, new_run["capture"], args.sample_rate)
        new_packet_state = _packet_state(new_cortex, new_packet_id)

        packet_fenced = bool(packet_state) and packet_state.get("playback_state") in ("interrupted", "cancelled") and packet_state.get("commit_eligible") is False
        quiet_bound = tail.valid and tail.post_bound_quiet_ms >= MIN_POST_BOUND_QUIET_MS
        clean_new = new_alignment.valid and new_alignment.offset_samples is not None
        if not tail.valid:
            result, failure = "EVIDENCE_INVALID", "EVIDENCE_INVALID"
            reason = tail.reason
        elif not packet_fenced:
            result, failure = "EXECUTED_PRODUCT_NEGATIVE", "PRODUCT_NEGATIVE"
            reason = "existing_packet_cancel_boundary_did_not_fence_commit"
        elif not quiet_bound:
            result, failure = "EXECUTED_PRODUCT_NEGATIVE", "PRODUCT_NEGATIVE"
            reason = "old_audio_not_bounded_inside_observation_window"
        elif not clean_new:
            result, failure = "EVIDENCE_INVALID", "EVIDENCE_INVALID"
            reason = "new_generation_monitor_readback_not_bound"
        else:
            result, failure = "EXECUTED_NO_COUNTEREXAMPLE", None
            reason = "bounded_virtual_sink_cancel_tail_observed"

        report = _report(
            result=result, failure_class=failure, source_sha=source_sha,
            old_path=old_path, new_path=new_path, runtime_path=runtime_path,
            model_path=model_path, graph_info=graph_info, control=control,
            control_alignment=control_alignment, cancel_run=cancel_run,
            cancel_alignment=cancel_alignment, tail=tail, packet_state=packet_state,
            packet_terminal_ns=packet_terminal_ns, new_run=new_run,
            new_alignment=new_alignment, new_packet_state=new_packet_state, reason=reason,
        )
        return report
    finally:
        graph.close()


def _alignment_dict(value: Alignment | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "valid": value.valid, "method": value.method,
        "offset_samples": value.offset_samples, "score": value.score,
        "error_bound_ms": value.error_bound_ms,
    }


def _tail_dict(value: TailMeasurement | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "valid": value.valid,
        "last_old_sample_index_after_alignment": value.last_correlated_capture_sample,
        "cancel_capture_sample": value.cancel_capture_sample,
        "cancel_to_last_old_sample_tail_ms": value.cancel_to_last_old_sample_ms,
        "post_bound_quiet_ms": value.post_bound_quiet_ms,
        "matched_frames": value.matched_frames,
        "reason": value.reason,
    }


def _report(
    *, result: str, failure_class: str | None, source_sha: str,
    old_path: Path, new_path: Path, runtime_path: Path, model_path: Path,
    graph_info: dict[str, Any], control: dict[str, Any], control_alignment: Alignment,
    reason: str, cancel_run: dict[str, Any] | None = None,
    cancel_alignment: Alignment | None = None, tail: TailMeasurement | None = None,
    packet_state: dict[str, Any] | None = None, packet_terminal_ns: int | None = None,
    new_run: dict[str, Any] | None = None, new_alignment: Alignment | None = None,
    new_packet_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "classification": CLASSIFICATION,
        "result": result,
        "failure_class": failure_class,
        "reason": reason,
        "f2_subject_sha": source_sha,
        "source_waveform_sha256": _sha_file(old_path),
        "next_generation_waveform_sha256": _sha_file(new_path),
        "tts_runtime_binary_sha256": _sha_file(runtime_path),
        "tts_model_sha256": _sha_file(model_path),
        "graph": graph_info,
        "control": {k: v for k, v in control.items() if k != "capture"},
        "control_alignment": _alignment_dict(control_alignment),
        "cancel": None if cancel_run is None else {k: v for k, v in cancel_run.items() if k != "capture"},
        "cancel_alignment": _alignment_dict(cancel_alignment),
        "tail": _tail_dict(tail),
        "packet_terminal_monotonic_ns": packet_terminal_ns,
        "old_packet_state": packet_state,
        "new_generation": None if new_run is None else {k: v for k, v in new_run.items() if k != "capture"},
        "new_alignment": _alignment_dict(new_alignment),
        "new_packet_state": new_packet_state,
        "external_inference_api_calls": 0,
        "measured_credit": {
            "owner_vps_pipewire_virtual_sink_playback_readback": int(result == "EXECUTED_NO_COUNTEREXAMPLE"),
            "bounded_cancellation_to_virtual_audio_monitor_silence": int(result == "EXECUTED_NO_COUNTEREXAMPLE"),
            "physical_microphone": 0,
            "physical_speaker": 0,
            "human_heard_output": 0,
            "physical_acoustic_loopback": 0,
            "whole_voice_e2e": 0,
            "whole_product": 0,
            "gwt_jspace": 0,
            "effect": 0,
            "unifieddb_write": 0,
            "training": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-pcm", required=True, help="exact old-generation raw s16le Piper PCM")
    parser.add_argument("--next-source-pcm", required=True, help="distinct next-generation raw s16le Piper PCM")
    parser.add_argument("--tts-runtime-binary", required=True)
    parser.add_argument("--tts-model", required=True)
    parser.add_argument("--sample-rate", type=int, required=True)
    parser.add_argument("--channels", type=int, default=DEFAULT_CHANNELS)
    parser.add_argument("--cancel-after-ms", type=int, default=320)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        report = run_pulse(args)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        report = {
            "schema": SCHEMA,
            "classification": CLASSIFICATION,
            "result": "EVIDENCE_INVALID",
            "failure_class": "INFRA_AUTH_TRANSPORT_QUOTA" if isinstance(exc, (OSError, subprocess.SubprocessError)) else "EVIDENCE_INVALID",
            "reason": str(exc),
            "measured_credit": {
                "owner_vps_pipewire_virtual_sink_playback_readback": 0,
                "bounded_cancellation_to_virtual_audio_monitor_silence": 0,
                "physical_microphone": 0, "physical_speaker": 0,
                "human_heard_output": 0, "physical_acoustic_loopback": 0,
                "whole_voice_e2e": 0, "whole_product": 0, "gwt_jspace": 0,
                "effect": 0, "unifieddb_write": 0, "training": 0,
            },
        }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if report["result"] == "EXECUTED_NO_COUNTEREXAMPLE":
        return 0
    if report.get("failure_class") == "PRODUCT_NEGATIVE":
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
