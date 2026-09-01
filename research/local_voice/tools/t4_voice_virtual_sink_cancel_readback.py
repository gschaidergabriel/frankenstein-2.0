#!/usr/bin/env python3
"""Trigger-4 G2 virtual-sink cancellation/readback falsifier.

Bounded candidate falsifier for the existing Frankenstein 2.0 local Voice-Slice.
It adds no Voice/playback/effect authority. The probe isolates the VPS-
representable G2 PipeWire monitor boundary: an old generation is genuinely
queued at a sink, the generation fence advances *before* cancellation, the old
sentinel is observed before cancel but truncated within a bounded tail, a late
old-generation chunk is rejected, a new generation restarts, and monitor
readback is inspected for stale leakage.

Modes:
  software   deterministic repository reference (never target-runtime credit)
  pulse-null PipeWire-Pulse/PulseAudio null sink + monitor for admitted S1/S2 VPS

A pulse-null PASS is only a promotion candidate. Exact source/runtime identity
and an external receipt are still required before any target-runtime credit.
Physical speaker/microphone/human-heard, producer-side TTS cancellation,
whole-voice, GWT/J-Space, effect, training and whole-product credit stay zero.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import tempfile
import time
from typing import Any

SCHEMA = "F2_T4_VOICE_VIRTUAL_SINK_CANCEL_READBACK_G2/v1"
RESEARCH_ID = "T7-20260902-PIPEWIRE-MONITOR-CANCEL-G2"
SEMANTIC_KEY = "0d83f7d13c1d8f91686cf94070f73d901a49018b40a9c058d1949af094655bff"
CLASSIFICATION = "CANDIDATE_FALSIFIER_G2_PIPEWIRE_MONITOR_ONLY"

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
FRAME_MS = 10
FRAMES_PER_CHUNK = SAMPLE_RATE * FRAME_MS // 1000
PRE_CHUNKS = 20
OLD_SENTINEL_CHUNKS = 40
NEW_SENTINEL_CHUNKS = 20
CUT_DELAY_S = 0.260
MAX_RESIDUAL_OLD_MS = 150
POST_RESTART_WAIT_S = 0.300


def _pcm_constant(value: int, chunks: int) -> bytes:
    if not -32768 <= value <= 32767:
        raise ValueError("sample value out of int16 range")
    return struct.pack("<h", value) * FRAMES_PER_CHUNK * chunks


PRE = _pcm_constant(2_000, PRE_CHUNKS)
OLD_SENTINEL = _pcm_constant(12_000, OLD_SENTINEL_CHUNKS)
NEW_SENTINEL = _pcm_constant(-12_000, NEW_SENTINEL_CHUNKS)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sample_count(blob: bytes, value: int) -> int:
    if len(blob) % SAMPLE_WIDTH:
        blob = blob[: len(blob) - (len(blob) % SAMPLE_WIDTH)]
    if not blob:
        return 0
    samples = struct.unpack(f"<{len(blob) // SAMPLE_WIDTH}h", blob)
    return sum(sample == value for sample in samples)


@dataclass(frozen=True)
class Chunk:
    session_id: str
    packet_id: str
    generation: int
    chunk_index: int
    pcm: bytes


class GenerationFence:
    """Session-bound, monotonic application fence for playback generations."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.generation = 1
        self.rejected = 0
        self.last_advance_ns: int | None = None

    def admit(self, chunk: Chunk) -> bool:
        if chunk.session_id != self.session_id or chunk.generation != self.generation:
            self.rejected += 1
            return False
        return True

    def cancel_generation(self) -> tuple[int, int, int]:
        old = self.generation
        self.generation += 1
        self.last_advance_ns = time.monotonic_ns()
        return old, self.generation, self.last_advance_ns


class QueueingSoftwareLoopback:
    """Deterministic queueing sink used only as repository reference evidence."""

    backend_name = "SOFTWARE_QUEUEING_LOOPBACK_REFERENCE"

    def __init__(self, *, discard_pending_on_cancel: bool = True) -> None:
        self.pending = bytearray()
        self.played = bytearray()
        self.discard_pending_on_cancel = discard_pending_on_cancel
        self.cancelled = False
        self.discarded_bytes = 0

    def enqueue(self, pcm: bytes) -> None:
        if self.cancelled:
            raise RuntimeError("enqueue attempted while sink generation cancelled")
        self.pending.extend(pcm)

    def play_bytes(self, count: int) -> None:
        n = min(count, len(self.pending))
        self.played.extend(self.pending[:n])
        del self.pending[:n]

    def play_all(self) -> None:
        self.play_bytes(len(self.pending))

    def cancel(self) -> None:
        self.cancelled = True
        if self.discard_pending_on_cancel:
            self.discarded_bytes += len(self.pending)
            self.pending.clear()

    def reset(self) -> None:
        self.cancelled = False

    def readback(self) -> bytes:
        return bytes(self.played)


class PulseNullSink:
    """Headless PipeWire-Pulse/PulseAudio null-sink discriminator.

    The full old preamble+sentinel is written to pacat before cancellation.
    SIGTERM closes the playback stream instead of using drain semantics; monitor
    capture supplies sink-side readback. This remains virtual-sink evidence only.
    """

    backend_name = "PIPEWIRE_PULSE_NULL_SINK"

    def __init__(self, sink_name: str = "f2_voice_pipewire_g2") -> None:
        self.sink_name = sink_name
        self.module_id: str | None = None
        self.capture: subprocess.Popen[bytes] | None = None
        self.player: subprocess.Popen[bytes] | None = None
        self.capture_path: Path | None = None
        self._capture_fp: Any | None = None
        self._tmp: tempfile.TemporaryDirectory[str] | None = None

    @staticmethod
    def available() -> bool:
        return all(shutil.which(cmd) for cmd in ("pactl", "pacat", "parec"))

    def start(self) -> None:
        if not self.available():
            raise RuntimeError("pactl/pacat/parec not all available")
        self._tmp = tempfile.TemporaryDirectory(prefix="f2-voice-pipewire-g2-")
        self.capture_path = Path(self._tmp.name) / "monitor.raw"
        cp = subprocess.run(
            [
                "pactl", "load-module", "module-null-sink",
                f"sink_name={self.sink_name}",
                f"rate={SAMPLE_RATE}", f"channels={CHANNELS}",
            ],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if cp.returncode != 0:
            raise RuntimeError(f"null sink creation failed: {cp.stderr.strip()}")
        self.module_id = cp.stdout.strip()
        if not self.module_id.isdigit():
            raise RuntimeError("pactl did not return numeric module id")

        self._capture_fp = self.capture_path.open("wb")
        self.capture = subprocess.Popen(
            [
                "parec", f"--device={self.sink_name}.monitor",
                "--format=s16le", f"--rate={SAMPLE_RATE}",
                f"--channels={CHANNELS}", "--raw",
            ],
            stdout=self._capture_fp, stderr=subprocess.PIPE,
        )
        time.sleep(0.150)

    def _new_player(self) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [
                "pacat", "--playback", f"--device={self.sink_name}",
                "--format=s16le", f"--rate={SAMPLE_RATE}",
                f"--channels={CHANNELS}", "--raw",
            ],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )

    def enqueue(self, pcm: bytes) -> None:
        if self.player is None or self.player.poll() is not None:
            self.player = self._new_player()
        assert self.player.stdin is not None
        self.player.stdin.write(pcm)
        self.player.stdin.flush()

    def cancel(self) -> None:
        if self.player is None:
            return
        if self.player.poll() is None:
            self.player.send_signal(signal.SIGTERM)
            try:
                self.player.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.player.kill()
                self.player.wait(timeout=2)
        self.player = None

    def reset(self) -> None:
        self.player = None

    def readback(self) -> bytes:
        if self.capture is not None and self.capture.poll() is None:
            self.capture.send_signal(signal.SIGTERM)
            try:
                self.capture.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.capture.kill()
                self.capture.wait(timeout=2)
        if self._capture_fp is not None and not self._capture_fp.closed:
            self._capture_fp.close()
        if self.capture_path is None:
            return b""
        return self.capture_path.read_bytes()

    def close(self) -> None:
        try:
            self.cancel()
        finally:
            if self.capture is not None and self.capture.poll() is None:
                self.capture.kill()
                self.capture.wait(timeout=2)
            if self._capture_fp is not None and not self._capture_fp.closed:
                self._capture_fp.close()
            if self.module_id is not None:
                subprocess.run(
                    ["pactl", "unload-module", self.module_id],
                    capture_output=True, text=True, timeout=10, check=False,
                )
                self.module_id = None
            if self._tmp is not None:
                self._tmp.cleanup()
                self._tmp = None


def _run_with_sink(sink: QueueingSoftwareLoopback | PulseNullSink, *, pulse: bool) -> dict[str, Any]:
    session_id = "session-t4-pipewire-g2"
    fence = GenerationFence(session_id)
    old_blob = PRE + OLD_SENTINEL
    old_chunk = Chunk(session_id, "output-old", 1, 0, old_blob)
    late_old = Chunk(session_id, "output-old-late", 1, 1, OLD_SENTINEL)

    if not fence.admit(old_chunk):
        raise AssertionError("current generation old payload rejected")

    # Critical repair: old sentinel is genuinely queued before the cancel.
    sink.enqueue(old_blob)
    old_sentinel_queued_before_cancel = True

    if pulse:
        time.sleep(CUT_DELAY_S)
    else:
        # Play through 200 ms preamble and 60 ms into old sentinel. The rest
        # stays pending so cancellation must discard the stale tail.
        pre_cut_bytes = int(SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH * CUT_DELAY_S)
        sink.play_bytes(pre_cut_bytes)

    old_generation, new_generation, generation_advanced_ns = fence.cancel_generation()
    cancel_requested_ns = time.monotonic_ns()
    sink.cancel()
    cancel_finished_ns = time.monotonic_ns()

    # Deliberately late old-generation delivery must fail before sink enqueue.
    late_old_accepted = fence.admit(late_old)
    if late_old_accepted:
        sink.reset()
        sink.enqueue(late_old.pcm)

    sink.reset()
    new_chunk = Chunk(session_id, "output-new", new_generation, 0, NEW_SENTINEL)
    if not fence.admit(new_chunk):
        raise AssertionError("new generation rejected after reset")
    sink.enqueue(new_chunk.pcm)

    if pulse:
        time.sleep(POST_RESTART_WAIT_S)
    else:
        sink.play_all()
    readback = sink.readback()

    old_samples = _sample_count(readback, 12_000)
    new_samples = _sample_count(readback, -12_000)
    expected_new_samples = len(NEW_SENTINEL) // SAMPLE_WIDTH
    expected_old_samples = len(OLD_SENTINEL) // SAMPLE_WIDTH
    pre_samples = len(PRE) // SAMPLE_WIDTH
    cut_samples = int(SAMPLE_RATE * CUT_DELAY_S)
    expected_old_before_cancel = max(0, cut_samples - pre_samples)
    residual_old_samples = max(0, old_samples - expected_old_before_cancel)
    max_residual_old_samples = int(SAMPLE_RATE * MAX_RESIDUAL_OLD_MS / 1000.0)

    # A zero old-sentinel observation is non-discriminating: it would not show
    # that the old generation reached the actual playback graph. The sentinel
    # must start, then truncate before completion, with a hard-bounded tail.
    passed = (
        old_sentinel_queued_before_cancel
        and generation_advanced_ns <= cancel_requested_ns <= cancel_finished_ns
        and not late_old_accepted
        and fence.rejected == 1
        and old_samples > 0
        and old_samples < expected_old_samples
        and residual_old_samples <= max_residual_old_samples
        and new_samples > 0
    )
    if not pulse:
        passed = (
            passed
            and old_samples == expected_old_before_cancel
            and residual_old_samples == 0
            and new_samples == expected_new_samples
        )

    repository_reference = int(passed and not pulse)
    pulse_runtime_candidate = int(passed and pulse)
    discarded_bytes = getattr(sink, "discarded_bytes", None)

    return {
        "schema": SCHEMA,
        "research_id": RESEARCH_ID,
        "semantic_key": SEMANTIC_KEY,
        "classification": CLASSIFICATION,
        "backend": sink.backend_name,
        "execution_scope": "VPS_PIPEWIRE_MONITOR_CANDIDATE" if pulse else "REPOSITORY_REFERENCE_ONLY",
        "session_id": session_id,
        "old_generation": old_generation,
        "new_generation": new_generation,
        "old_sentinel_queued_before_cancel": old_sentinel_queued_before_cancel,
        "generation_advanced_before_sink_cancel": generation_advanced_ns <= cancel_requested_ns,
        "late_old_generation_accepted": late_old_accepted,
        "stale_chunks_rejected": fence.rejected,
        "cancel_call_duration_ms": (cancel_finished_ns - cancel_requested_ns) / 1_000_000.0,
        "software_discarded_pending_bytes": discarded_bytes,
        "readback_bytes": len(readback),
        "readback_sha256": _sha(readback),
        "old_sentinel_samples": old_samples,
        "expected_old_sentinel_samples_without_cancel": expected_old_samples,
        "expected_old_samples_before_cancel": expected_old_before_cancel,
        "residual_old_samples_after_cancel_bound_model": residual_old_samples,
        "max_residual_old_samples": max_residual_old_samples,
        "new_sentinel_samples": new_samples,
        "expected_new_sentinel_samples": expected_new_samples,
        "pass": passed,
        "failure_class": None if passed else "PRODUCT_NEGATIVE",
        "evidence": {
            "repository_reference_pass": repository_reference,
            "pipewire_monitor_promotion_candidate": pulse_runtime_candidate,
            "target_runtime_credit_from_probe_alone": 0,
            "pipewire_runtime_credit_from_probe_alone": 0,
            "producer_generation_cancel": 0,
            "true_streaming_partial_asr": 0,
            "physical_speaker": 0,
            "physical_microphone": 0,
            "human_heard_output": 0,
            "acoustic_playback_readback": 0,
            "whole_voice_e2e": 0,
            "gwt_jspace": 0,
            "effect": 0,
            "unifieddb_write": 0,
            "training": 0,
            "whole_product": 0,
        },
        "next_exact_action": (
            "Execute --backend pulse-null on admitted owner-VPS S1/S2 against the identical accepted source; "
            "bind exact source/runtime/monitor-readback in an external receipt before promoting bounded G2 PipeWire-monitor credit. "
            "Keep producer-side TTS cancel and true partial ASR unclaimed until this G2 terminates; reserve physical speaker/mic/human-heard for S4."
        ),
    }


def run(backend: str, *, software_cancel_discards_pending: bool = True) -> dict[str, Any]:
    if backend == "software":
        return _run_with_sink(
            QueueingSoftwareLoopback(discard_pending_on_cancel=software_cancel_discards_pending),
            pulse=False,
        )
    if backend != "pulse-null":
        raise ValueError(f"unsupported backend: {backend}")

    sink = PulseNullSink()
    sink.start()
    try:
        return _run_with_sink(sink, pulse=True)
    finally:
        sink.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("software", "pulse-null"), default="software")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.backend)
    except RuntimeError as exc:
        result = {
            "schema": SCHEMA,
            "research_id": RESEARCH_ID,
            "semantic_key": SEMANTIC_KEY,
            "classification": CLASSIFICATION,
            "backend_requested": args.backend,
            "pass": False,
            "execution_status": "BLOCKED_BEFORE_VALID_DISCRIMINATOR",
            "failure_class": "INFRA_AUTH_TRANSPORT_QUOTA",
            "error": str(exc),
            "target_runtime_credit_from_probe_alone": 0,
        }
        exit_code = 2
    else:
        exit_code = 0 if result["pass"] else 1

    payload = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
