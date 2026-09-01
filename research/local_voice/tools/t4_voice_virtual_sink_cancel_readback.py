#!/usr/bin/env python3
"""Bounded Trigger-4 virtual-sink cancellation/readback discriminator.

This is a research/candidate-falsifier organ, not a new voice, memory, effect,
or playback authority.  It exercises the next VPS-representable boundary after
G4: output consumption, cancellation, stale-generation rejection and readback.

Modes:
  software  - deterministic repository-CI reference loopback only.
  pulse-null - Linux PipeWire-Pulse/PulseAudio null-sink probe when pactl,
               pacat and parec are available on the target sandbox.

A PASS may only earn the exact executed candidate-observation scope. This tool
cannot mint admitted VPS runtime credit by itself because source/runner/sandbox
identity is bound by the external execution receipt/reconciliation boundary.
It never earns physical speaker, microphone, human-heard, acoustic, S4,
whole-voice, whole-product, GWT/J-Space, effect, UnifiedDB or training credit.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import tempfile
import time
from typing import Any

SCHEMA = "F2_T4_VOICE_VIRTUAL_SINK_CANCEL_READBACK/v1"
CLASSIFICATION = "CANDIDATE_FALSIFIER_VIRTUAL_SINK_ONLY"
SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
FRAME_MS = 10
FRAMES_PER_CHUNK = SAMPLE_RATE * FRAME_MS // 1000


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pcm_constant(value: int, chunks: int) -> bytes:
    if not -32768 <= value <= 32767:
        raise ValueError("sample value out of int16 range")
    frame = struct.pack("<h", value)
    return frame * FRAMES_PER_CHUNK * chunks


PRE = _pcm_constant(2000, 6)
OLD_SENTINEL = _pcm_constant(12000, 6)
NEW_SENTINEL = _pcm_constant(-12000, 6)


@dataclass(frozen=True)
class Chunk:
    session_id: str
    packet_id: str
    generation: int
    chunk_index: int
    pcm: bytes


class GenerationFence:
    """Research-only stale-generation rejection oracle."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.generation = 1
        self.rejected = 0

    def admit(self, chunk: Chunk) -> bool:
        if chunk.session_id != self.session_id or chunk.generation != self.generation:
            self.rejected += 1
            return False
        return True

    def cancel(self) -> tuple[int, int]:
        old = self.generation
        self.generation += 1
        return old, self.generation


class SoftwareLoopback:
    """Deterministic reference sink; repository evidence only."""

    backend_name = "SOFTWARE_LOOPBACK_REFERENCE"

    def __init__(self) -> None:
        self.played = bytearray()
        self.cancelled = False

    def write(self, pcm: bytes) -> None:
        if self.cancelled:
            raise RuntimeError("write attempted after cancellation")
        self.played.extend(pcm)

    def cancel(self) -> None:
        self.cancelled = True

    def reset(self) -> None:
        self.cancelled = False

    def readback(self) -> bytes:
        return bytes(self.played)


class PulseNullSink:
    """PipeWire-Pulse/PulseAudio null-sink probe for S1/S2 execution.

    This deliberately uses the Pulse compatibility tools because they provide a
    portable headless null sink + monitor on common PipeWire deployments.  A
    PASS is virtual-sink candidate evidence, not admitted VPS/runtime, native
    PipeWire-stream, or physical-audio credit.
    """

    backend_name = "PIPEWIRE_PULSE_NULL_SINK"

    def __init__(self, sink_name: str = "f2_voice_probe") -> None:
        self.sink_name = sink_name
        self.module_id: str | None = None
        self.capture: subprocess.Popen[bytes] | None = None
        self.player: subprocess.Popen[bytes] | None = None
        self.capture_path: Path | None = None
        self._tmp: tempfile.TemporaryDirectory[str] | None = None

    @staticmethod
    def available() -> bool:
        return all(shutil.which(cmd) for cmd in ("pactl", "pacat", "parec"))

    def start(self) -> None:
        if not self.available():
            raise RuntimeError("pactl/pacat/parec not all available")
        self._tmp = tempfile.TemporaryDirectory(prefix="f2-voice-null-sink-")
        self.capture_path = Path(self._tmp.name) / "monitor.raw"
        cp = subprocess.run(
            [
                "pactl",
                "load-module",
                "module-null-sink",
                f"sink_name={self.sink_name}",
                f"rate={SAMPLE_RATE}",
                f"channels={CHANNELS}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if cp.returncode != 0:
            raise RuntimeError(f"null sink creation failed: {cp.stderr.strip()}")
        self.module_id = cp.stdout.strip()
        if not self.module_id.isdigit():
            raise RuntimeError("pactl did not return numeric module id")
        capture_fp = self.capture_path.open("wb")
        self.capture = subprocess.Popen(
            [
                "parec",
                f"--device={self.sink_name}.monitor",
                "--format=s16le",
                f"--rate={SAMPLE_RATE}",
                f"--channels={CHANNELS}",
                "--raw",
            ],
            stdout=capture_fp,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.15)
        self._capture_fp = capture_fp

    def _new_player(self) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [
                "pacat",
                "--playback",
                f"--device={self.sink_name}",
                "--format=s16le",
                f"--rate={SAMPLE_RATE}",
                f"--channels={CHANNELS}",
                "--raw",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def write(self, pcm: bytes) -> None:
        if self.player is None or self.player.poll() is not None:
            self.player = self._new_player()
        assert self.player.stdin is not None
        self.player.stdin.write(pcm)
        self.player.stdin.flush()
        duration = len(pcm) / (SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH)
        time.sleep(min(duration, 0.12))

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
        time.sleep(0.20)
        if self.capture is not None and self.capture.poll() is None:
            self.capture.send_signal(signal.SIGTERM)
            try:
                self.capture.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.capture.kill()
                self.capture.wait(timeout=2)
        if hasattr(self, "_capture_fp"):
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
            if hasattr(self, "_capture_fp") and not self._capture_fp.closed:
                self._capture_fp.close()
            if self.module_id is not None:
                subprocess.run(
                    ["pactl", "unload-module", self.module_id],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                self.module_id = None
            if self._tmp is not None:
                self._tmp.cleanup()
                self._tmp = None


def _count_exact_chunk(blob: bytes, pattern: bytes) -> int:
    if not pattern:
        return 0
    return blob.count(pattern)


def run(backend: str) -> dict[str, Any]:
    session_id = "session-t4-voice-virtual-sink-g5"
    fence = GenerationFence(session_id)
    sink: SoftwareLoopback | PulseNullSink
    runtime_class = "REPOSITORY_SIMULATION_ONLY"
    if backend == "software":
        sink = SoftwareLoopback()
    elif backend == "pulse-null":
        sink = PulseNullSink()
        runtime_class = "VPS_VIRTUAL_SINK_IF_EXECUTED_ON_ADMITTED_TARGET"
        sink.start()
    else:
        raise ValueError(f"unsupported backend: {backend}")

    admitted: list[str] = []
    try:
        old_pre = Chunk(session_id, "output-a-0", 1, 0, PRE)
        old_queued = Chunk(session_id, "output-a-0", 1, 1, OLD_SENTINEL)
        if not fence.admit(old_pre):
            raise AssertionError("current generation preamble rejected")
        sink.write(old_pre.pcm)
        admitted.append("old-pre")

        old_generation, new_generation = fence.cancel()
        cancel_called_ns = time.monotonic_ns()
        sink.cancel()
        cancel_finished_ns = time.monotonic_ns()

        late_old_accepted = fence.admit(old_queued)
        if late_old_accepted:
            sink.write(old_queued.pcm)
            admitted.append("late-old-sentinel")

        sink.reset()
        new_chunk = Chunk(session_id, "output-b-0", new_generation, 0, NEW_SENTINEL)
        if not fence.admit(new_chunk):
            raise AssertionError("new generation rejected after reset")
        sink.write(new_chunk.pcm)
        admitted.append("new-sentinel")

        readback = sink.readback()
    finally:
        if isinstance(sink, PulseNullSink):
            sink.close()

    old_sentinel_occurrences = _count_exact_chunk(readback, OLD_SENTINEL)
    new_sentinel_occurrences = _count_exact_chunk(readback, NEW_SENTINEL)
    software_pass = (
        backend != "software"
        or (
            not late_old_accepted
            and fence.rejected == 1
            and old_sentinel_occurrences == 0
            and new_sentinel_occurrences == 1
        )
    )
    pulse_pass = (
        backend != "pulse-null"
        or (
            not late_old_accepted
            and fence.rejected == 1
            and len(readback) > 0
            and OLD_SENTINEL not in readback
        )
    )
    passed = software_pass and pulse_pass

    return {
        "schema": SCHEMA,
        "classification": CLASSIFICATION,
        "backend": sink.backend_name,
        "execution_scope": runtime_class,
        "session_id": session_id,
        "old_generation": old_generation,
        "new_generation": new_generation,
        "late_old_generation_accepted": late_old_accepted,
        "stale_chunks_rejected": fence.rejected,
        "admitted_chunks": admitted,
        "cancel_call_duration_ms": (cancel_finished_ns - cancel_called_ns) / 1_000_000.0,
        "readback_bytes": len(readback),
        "readback_sha256": _sha(readback),
        "old_sentinel_exact_occurrences": old_sentinel_occurrences,
        "new_sentinel_exact_occurrences": new_sentinel_occurrences,
        "pass": passed,
        "failure_class": None if passed else "PRODUCT_NEGATIVE",
        "measured_credit": {
            "repository_software_reference_credit": int(passed and backend == "software"),
            "candidate_pulse_null_output_consumption_observed": int(passed and backend == "pulse-null"),
            "virtual_sink_output_consumption_control": 0,
            "target_vps_virtual_sink_runtime_credit": 0,
            "stale_generation_rejection": int(not late_old_accepted and fence.rejected == 1),
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
            "If repository software mode passes, execute pulse-null on admitted S1/S2 VPS and bind exact source/runtime identity. "
            "A pulse-null PASS from this tool remains candidate observation only; promote virtual-sink runtime credit only in the external receipt/reconciliation after exact subject and admitted runtime identity are verified. "
            "Reserve physical speaker/microphone/human-heard cancellation-to-silence for S4."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("software", "pulse-null"), default="software")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = run(args.backend)
    payload = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
