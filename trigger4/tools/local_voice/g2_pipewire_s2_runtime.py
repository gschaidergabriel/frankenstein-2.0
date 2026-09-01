#!/usr/bin/env python3
"""Trigger-4 G2 PipeWire virtual-sink playback/cancel/monitor discriminator.

Promotion-bearing scope is deliberately narrow: exact local TTS bytes are bound
to one VoiceOutputPacket, the admitted VoicePacketCortex barge-in transition is
translated by the deterministic playback adapter to the exact paplay client,
and PipeWire monitor readback measures the bounded in-flight tail. No physical
speaker, microphone, human-heard, GWT/J-Space, effect, training, or whole-product
credit is created here.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import wave
from typing import Any

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoicePacketCortex
from frankenstein2.voice_playback_adapter import (
    PlaybackCancellationAdapterError,
    propagate_packet_cancellation_to_process,
)

import g2_pipewire_evidence as g2e

SCHEMA = "T4_G2_PIPEWIRE_S2_PLAYBACK_CANCEL_MONITOR/v2"
SEMANTIC_KEY = "0d83f7d13c1d8f91686cf94070f73d901a49018b40a9c058d1949af094655bff"
PACKET_AUDIO_BINDING_SCHEMA = "T4_G2_PACKET_TTS_WAVEFORM_BINDING/v1"
STREAM_IDENTITY_SCHEMA = "T4_G2_PULSE_STREAM_IDENTITY/v1"


class EvidenceInvalid(RuntimeError):
    pass


class ProductNegative(RuntimeError):
    pass


def run(cmd: list[str], *, check: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_wav_meta(path: Path) -> dict[str, int]:
    with wave.open(str(path), "rb") as wf:
        return {
            "rate": wf.getframerate(),
            "channels": wf.getnchannels(),
            "sample_width": wf.getsampwidth(),
            "frames": wf.getnframes(),
        }


def raw_to_wav(raw: Path, wav: Path, *, rate: int, channels: int) -> None:
    data = raw.read_bytes()
    frame_bytes = 2 * channels
    data = data[: len(data) - (len(data) % frame_bytes)]
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(data)


def wait_pulse(timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        p = run(["pactl", "info"], check=False)
        last = (p.stdout or "") + (p.stderr or "")
        if p.returncode == 0:
            return
        time.sleep(0.25)
    raise RuntimeError("PIPEWIRE_PULSE_NOT_READY:" + last[-1000:])


def wait_named_line(command: list[str], needle: str, timeout_s: float = 5.0) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        p = run(command, check=False)
        if p.returncode == 0:
            for line in p.stdout.splitlines():
                if needle in line:
                    return line.strip()
        time.sleep(0.1)
    raise RuntimeError(f"IDENTITY_NOT_ENUMERATED:{needle}")


def pactl_json(target: str) -> list[dict[str, Any]]:
    p = run(["pactl", "-f", "json", "list", target], check=False)
    if p.returncode != 0:
        raise RuntimeError(f"PACTL_JSON_FAILED:{target}:{p.returncode}:{p.stderr[-500:]}")
    try:
        value = json.loads(p.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise EvidenceInvalid(f"PACTL_JSON_INVALID:{target}") from exc
    if not isinstance(value, list):
        raise EvidenceInvalid(f"PACTL_JSON_NOT_LIST:{target}")
    return [row for row in value if isinstance(row, dict)]


def wait_stream_identity(kind: str, pid: int, timeout_s: float = 2.0) -> dict[str, Any]:
    if kind not in ("playback", "capture"):
        raise ValueError("stream kind must be playback or capture")
    target = "sink-inputs" if kind == "playback" else "source-outputs"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for row in pactl_json(target):
            props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
            if str(props.get("application.process.id", "")) != str(pid):
                continue
            result: dict[str, Any] = {
                "schema": STREAM_IDENTITY_SCHEMA,
                "kind": kind,
                "process_id": pid,
                "index": row.get("index"),
                "client": row.get("client"),
                "sample_spec": row.get("sample_spec"),
                "channel_map": row.get("channel_map"),
                "buffer_latency_usec": row.get("buffer_latency_usec"),
                "application_name": props.get("application.name"),
                "application_process_id": props.get("application.process.id"),
                "media_name": props.get("media.name"),
                "observed_monotonic_ns": time.monotonic_ns(),
            }
            if kind == "playback":
                result["sink"] = row.get("sink")
                result["sink_latency_usec"] = row.get("sink_latency_usec")
            else:
                result["source"] = row.get("source")
                result["source_latency_usec"] = row.get("source_latency_usec")
            if result["index"] is None or result["application_process_id"] is None:
                raise EvidenceInvalid(f"{kind.upper()}_STREAM_IDENTITY_INCOMPLETE")
            return result
        time.sleep(0.05)
    raise EvidenceInvalid(f"{kind.upper()}_STREAM_IDENTITY_NOT_OBSERVED_FOR_PID:{pid}")


def sink_latency_identity(sink_name: str) -> dict[str, Any]:
    rows = [row for row in pactl_json("sinks") if row.get("name") == sink_name]
    if len(rows) != 1:
        raise EvidenceInvalid(f"RUN_OWNED_SINK_LATENCY_IDENTITY_AMBIGUOUS:{len(rows)}")
    row = rows[0]
    if row.get("latency") is None and row.get("configured_latency") is None:
        raise EvidenceInvalid("RUN_OWNED_SINK_REPORTED_LATENCY_MISSING")
    return {
        "name": sink_name,
        "index": row.get("index"),
        "sample_spec": row.get("sample_spec"),
        "latency_usec": row.get("latency"),
        "configured_latency_usec": row.get("configured_latency"),
    }


def _latency_usec(value: Any) -> float | None:
    if isinstance(value, (int, float)) and float(value) >= 0:
        return float(value)
    if isinstance(value, str):
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:usec|us|µs)?", value)
        if match:
            return float(match.group(1))
    return None


def required_observables_complete(required: dict[str, Any]) -> bool:
    runtime_sha = required.get("tts_runtime_binary_sha256")
    playback = required.get("playback_stream_identity")
    capture = required.get("capture_stream_identity")
    quantum_latency = required.get("pipewire_quantum_and_reported_latency")
    if not isinstance(runtime_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", runtime_sha):
        return False
    if not isinstance(playback, dict) or playback.get("index") is None or playback.get("application_process_id") is None:
        return False
    if not isinstance(capture, dict) or capture.get("index") is None or capture.get("application_process_id") is None:
        return False
    if not isinstance(quantum_latency, dict):
        return False
    if not isinstance(quantum_latency.get("clock_rate_hz"), int) or quantum_latency["clock_rate_hz"] <= 0:
        return False
    if not isinstance(quantum_latency.get("clock_quantum_frames"), int) or quantum_latency["clock_quantum_frames"] <= 0:
        return False
    latencies = quantum_latency.get("reported_latency_usec")
    if not isinstance(latencies, dict) or not any(_latency_usec(value) is not None for value in latencies.values()):
        return False
    return True


def make_cortex(packet_id: str, planned_ms: int, text_segment: str) -> tuple[VoicePacketCortex, str]:
    root = CausalIdentity(
        session_id="session-t4-g2-pipewire",
        agent_id="frankenstein-2",
        task_id="task-t4-g2-pipewire",
        turn_id="turn-root",
        causal_id="causal-t4-g2-root",
        generation=1,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref="trigger4:g2-pipewire-monitor",
        input_sha256=sha256_text(text_segment),
        provenance_refs=("trigger4:g2-pipewire-monitor",),
    )
    session = VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id="causal-t4-g2-session",
            generation=2,
            turn_id="turn-session",
        ),
        provenance_refs=("trigger4:g2-pipewire-session",),
    )
    cortex = VoicePacketCortex(session, presence_state="PRESENT_INTERRUPTIBLE", opened_monotonic_ms=0)
    cortex.queue_output(
        turn_id="turn-a",
        packet_id=packet_id,
        monotonic_ms=10,
        text_segment=text_segment,
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=planned_ms,
        sequence=0,
        cancellable=True,
    )
    return cortex, session.voice_session_id


def capture_start(monitor: str, raw_path: Path, *, rate: int, channels: int) -> tuple[subprocess.Popen, object, dict[str, Any]]:
    fh = raw_path.open("wb")
    proc = subprocess.Popen(
        [
            "parec",
            f"--device={monitor}",
            "--format=s16le",
            f"--rate={rate}",
            f"--channels={channels}",
            "--raw",
        ],
        stdout=fh,
        stderr=subprocess.PIPE,
    )
    try:
        identity = wait_stream_identity("capture", proc.pid)
    except Exception:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=3)
        fh.close()
        raise
    if proc.poll() is not None:
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        fh.close()
        raise RuntimeError(f"MONITOR_CAPTURE_DIED:{proc.returncode}:{err[-1000:]}")
    return proc, fh, identity


def capture_stop(proc: subprocess.Popen, fh: object) -> int:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    terminal_ns = time.monotonic_ns()
    try:
        fh.close()
    except Exception:
        pass
    return terminal_ns


def play_start(sink: str, source: Path) -> tuple[subprocess.Popen, int, dict[str, Any]]:
    proc = subprocess.Popen(
        ["paplay", f"--device={sink}", str(source)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    started_ns = time.monotonic_ns()
    try:
        identity = wait_stream_identity("playback", proc.pid)
    except Exception:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=3)
        raise
    if proc.poll() is not None:
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise RuntimeError(f"PLAYBACK_DIED_EARLY:{proc.returncode}:{err[-1000:]}")
    return proc, started_ns, identity


def _hex64(name: str, value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise EvidenceInvalid(f"{name}_NOT_SHA256")
    return value


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    # Current launcher may still provide non-terminal replacement evidence. The
    # canonical G2 terminal benchmark does not require it, so these inputs are
    # accepted for compatibility but cannot substitute for required observables.
    ap.add_argument("--replacement-source", type=Path)
    ap.add_argument("--tts-text-file", type=Path, required=True)
    ap.add_argument("--replacement-tts-text-file", type=Path)
    ap.add_argument("--analyzer", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--bound-preflight-receipt", type=Path, required=True)
    ap.add_argument("--f2-subject-sha", required=True)
    ap.add_argument("--tts-model-sha256", required=True)
    ap.add_argument("--tts-config-sha256", required=True)
    ap.add_argument("--sink-name", default="f2_voice_g2_sink")
    ap.add_argument("--cancel-after-ms", type=float, default=1200.0)
    ap.add_argument("--max-inflight-ms", type=float, required=True)
    args = ap.parse_args()

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "semantic_key": SEMANTIC_KEY,
        "trigger": "4",
        "work_class": "RUNTIME_CREDIT_CLOSURE",
        "target_surface": "clay-direct-dev",
        "sandbox_tier": "S2_OWNER_VPS",
        "f2_subject_sha": args.f2_subject_sha,
        "result": "BLOCKED",
        "failure_class": "UNKNOWN_NONTERMINAL",
        "explicit_zero_credit": {
            "physical_microphone": 0,
            "physical_speaker": 0,
            "human_heard_output": 0,
            "physical_presence": 0,
            "cancellation_to_physical_silence": 0,
            "true_streaming_partial_asr": 0,
            "canonical_durable_state_reentry": 0,
            "gwt_jspace": 0,
            "effect": 0,
            "training": 0,
            "whole_voice_e2e": 0,
            "whole_product": 0,
        },
    }
    stage = "PRECHECK"
    module_id: str | None = None
    args.workdir.mkdir(parents=True, exist_ok=True)
    control_raw = args.workdir / "control.raw"
    cancel_raw = args.workdir / "cancel.raw"
    control_wav = args.workdir / "control.wav"
    cancel_wav = args.workdir / "cancel.wav"
    analysis_json = args.workdir / "analysis.json"
    control_cap = cancel_cap = None
    control_fh = cancel_fh = None
    cancel_play = None
    cleanup_direct_kill_used = False

    try:
        if not args.source.is_file() or not args.tts_text_file.is_file() or not args.analyzer.is_file():
            raise EvidenceInvalid("BOUND_INPUT_MISSING")
        if not args.bound_preflight_receipt.is_file():
            raise EvidenceInvalid("BOUND_PREFLIGHT_RECEIPT_MISSING")
        if not re.fullmatch(r"[0-9a-f]{40}", args.f2_subject_sha):
            raise EvidenceInvalid("F2_SUBJECT_SHA_INVALID")
        _hex64("TTS_MODEL_SHA256", args.tts_model_sha256)
        _hex64("TTS_CONFIG_SHA256", args.tts_config_sha256)
        try:
            piper_version = importlib.metadata.version("piper-tts")
        except importlib.metadata.PackageNotFoundError as exc:
            raise EvidenceInvalid("TTS_RUNTIME_PACKAGE_NOT_OBSERVED:piper-tts") from exc
        piper_runtime_path = Path(sys.executable).with_name("piper")
        if not piper_runtime_path.is_file():
            raise EvidenceInvalid(f"TTS_RUNTIME_EXECUTABLE_NOT_OBSERVED:{piper_runtime_path}")
        runtime_sha = sha256_file(piper_runtime_path)
        tts_text = args.tts_text_file.read_text(encoding="utf-8").strip()
        if not tts_text:
            raise EvidenceInvalid("TTS_TEXT_EMPTY")
        source_meta = read_wav_meta(args.source)
        if source_meta["sample_width"] != 2 or source_meta["channels"] != 1:
            raise EvidenceInvalid(f"SOURCE_MUST_BE_MONO_PCM16:{source_meta}")
        duration_ms = source_meta["frames"] * 1000.0 / source_meta["rate"]
        if duration_ms < args.cancel_after_ms + args.max_inflight_ms + 500:
            raise EvidenceInvalid("SOURCE_TOO_SHORT_FOR_DECLARED_CANCEL_BOUND")
        wait_pulse()

        packet_id = "output-old-g2-pipewire"
        cortex, session_id = make_cortex(packet_id, int(round(duration_ms)), tts_text)
        queued_packet = next(p for p in cortex.outputs if p.packet_id == packet_id)
        packet_audio_binding = {
            "schema": PACKET_AUDIO_BINDING_SCHEMA,
            "f2_subject_sha": args.f2_subject_sha,
            "voice_session_id": session_id,
            "voice_output_packet_id": packet_id,
            "queued_voice_output_packet_sha256": queued_packet.sha256(),
            "tts_text_sha256": sha256_text(tts_text),
            "source_waveform_sha256": sha256_file(args.source),
            "tts_runtime_path": str(piper_runtime_path),
            "tts_runtime_binary_sha256": runtime_sha,
            "tts_distribution_version": piper_version,
            "tts_model_sha256": args.tts_model_sha256,
            "tts_config_sha256": args.tts_config_sha256,
        }

        stage = "PIPEWIRE_GRAPH"
        pactl_info = run(["pactl", "info"]).stdout
        pipewire_version = run(["pipewire", "--version"], check=False).stdout.strip()
        wireplumber_version = run(["wireplumber", "--version"], check=False).stdout.strip()
        if "PipeWire" not in pactl_info and "pipewire" not in pactl_info.lower():
            raise RuntimeError("PACTL_SERVER_NOT_IDENTIFIED_AS_PIPEWIRE")
        loaded = run([
            "pactl", "load-module", "module-null-sink",
            f"sink_name={args.sink_name}",
            "format=s16le",
            f"rate={source_meta['rate']}",
            "channels=1",
        ])
        module_id = loaded.stdout.strip()
        if not module_id.isdigit():
            raise RuntimeError(f"NULL_SINK_MODULE_ID_INVALID:{module_id}")
        sink_line = wait_named_line(["pactl", "list", "short", "sinks"], args.sink_name)
        monitor_name = f"{args.sink_name}.monitor"
        monitor_line = wait_named_line(["pactl", "list", "short", "sources"], monitor_name)
        pw_dump = run(["pw-dump"]).stdout
        settings = run(["pw-metadata", "-n", "settings"]).stdout
        bound_receipt = json.loads(args.bound_preflight_receipt.read_text(encoding="utf-8"))
        g2e.validate_bound_receipt(bound_receipt, settings, args.max_inflight_ms)
        object_binding = g2e.resolve_pipewire_objects(pw_dump, args.sink_name, monitor_name)
        reported_latency = sink_latency_identity(args.sink_name)

        stage = "CONTROL"
        control_cap, control_fh, control_capture_identity = capture_start(
            monitor_name, control_raw, rate=source_meta["rate"], channels=1
        )
        control_play, control_play_start_ns, control_playback_identity = play_start(args.sink_name, args.source)
        control_rc = control_play.wait(timeout=max(10.0, duration_ms / 1000.0 + 5.0))
        control_play_end_ns = time.monotonic_ns()
        if control_rc != 0:
            err = control_play.stderr.read().decode(errors="replace") if control_play.stderr else ""
            raise RuntimeError(f"CONTROL_PLAYBACK_FAILED:{control_rc}:{err[-1000:]}")
        time.sleep(0.5)
        control_capture_terminal_ns = capture_stop(control_cap, control_fh)
        control_cap = control_fh = None
        raw_to_wav(control_raw, control_wav, rate=source_meta["rate"], channels=1)

        stage = "CAUSAL_CANCEL"
        cancel_cap, cancel_fh, cancel_capture_identity = capture_start(
            monitor_name, cancel_raw, rate=source_meta["rate"], channels=1
        )
        cancel_play, cancel_play_start_ns, cancel_playback_identity = play_start(args.sink_name, args.source)
        cortex.advance_output(packet_id, playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        elapsed_since_play_start_s = (time.monotonic_ns() - cancel_play_start_ns) / 1_000_000_000.0
        time.sleep(max(0.0, args.cancel_after_ms / 1000.0 - elapsed_since_play_start_s))
        cancel_request_ns = time.monotonic_ns()
        cancel_offset_ms = (cancel_request_ns - cancel_play_start_ns) / 1_000_000.0
        packet_cancel_ms = max(21, int(round(cancel_offset_ms)) + 20)
        changed = cortex.cancel_for_barge_in(turn_id="turn-b", monotonic_ms=packet_cancel_ms)
        packet_terminal_ns = time.monotonic_ns()
        if packet_id not in changed:
            raise ProductNegative("PACKET_CANCEL_DID_NOT_TOUCH_BOUND_OUTPUT")
        interrupted = next(p for p in cortex.outputs if p.packet_id == packet_id)
        if interrupted.playback_state != "interrupted" or interrupted.commit_eligible:
            raise ProductNegative("PACKET_FENCE_FAILED_AFTER_CANCEL")
        cancel_event = cortex.events[-1]
        try:
            propagation = propagate_packet_cancellation_to_process(
                packet=interrupted,
                cancel_event=cancel_event,
                process=cancel_play,
                timeout_s=3.0,
            )
        except PlaybackCancellationAdapterError as exc:
            raise EvidenceInvalid(f"PLAYBACK_CANCEL_PROPAGATION_INVALID:{exc}") from exc
        cancel_play = None
        post_roll_s = args.max_inflight_ms / 1000.0 + 0.8
        time.sleep(post_roll_s)
        cancel_capture_terminal_ns = capture_stop(cancel_cap, cancel_fh)
        cancel_cap = cancel_fh = None
        raw_to_wav(cancel_raw, cancel_wav, rate=source_meta["rate"], channels=1)

        stage = "PCM_ANALYSIS"
        analyzer_cmd = [
            sys.executable, str(args.analyzer),
            "--source", str(args.source),
            "--control", str(control_wav),
            "--cancel", str(cancel_wav),
            "--output", str(analysis_json),
            "--cancel-offset-ms", f"{cancel_offset_ms:.6f}",
            "--max-inflight-ms", f"{args.max_inflight_ms:.6f}",
            "--voice-output-packet-id", packet_id,
            "--f2-subject-sha", args.f2_subject_sha,
        ]
        analyzer_proc = run(analyzer_cmd, check=False)
        analysis = json.loads(analysis_json.read_text()) if analysis_json.exists() else None
        if not isinstance(analysis, dict):
            raise EvidenceInvalid(
                f"ANALYZER_DID_NOT_EMIT_RECEIPT:{analyzer_proc.returncode}:"
                f"{analyzer_proc.stdout[-500:]}:{analyzer_proc.stderr[-500:]}"
            )

        stage = "CLEANUP"
        run(["pactl", "unload-module", module_id], check=True)
        module_id = None
        time.sleep(0.2)
        pw_dump_after = run(["pw-dump"], check=False).stdout
        exact_identity_cleanup_ok = g2e.identities_absent(pw_dump_after, object_binding)
        sinks_after = run(["pactl", "list", "short", "sinks"], check=False).stdout
        sources_after = run(["pactl", "list", "short", "sources"], check=False).stdout
        name_cleanup_ok = args.sink_name not in sinks_after and monitor_name not in sources_after
        cleanup_ok = bool(exact_identity_cleanup_ok and name_cleanup_ok)

        reported_latency_values = {
            "sink_latency": reported_latency.get("latency_usec"),
            "sink_configured_latency": reported_latency.get("configured_latency_usec"),
            "control_playback_sink_latency": control_playback_identity.get("sink_latency_usec"),
            "control_playback_buffer_latency": control_playback_identity.get("buffer_latency_usec"),
            "control_capture_source_latency": control_capture_identity.get("source_latency_usec"),
            "control_capture_buffer_latency": control_capture_identity.get("buffer_latency_usec"),
            "cancel_playback_sink_latency": cancel_playback_identity.get("sink_latency_usec"),
            "cancel_playback_buffer_latency": cancel_playback_identity.get("buffer_latency_usec"),
            "cancel_capture_source_latency": cancel_capture_identity.get("source_latency_usec"),
            "cancel_capture_buffer_latency": cancel_capture_identity.get("buffer_latency_usec"),
        }
        pipewire_quantum_and_reported_latency = {
            "clock_rate_hz": bound_receipt["clock_rate_hz"],
            "clock_quantum_frames": bound_receipt["clock_quantum_frames"],
            "derived_max_inflight_ms": bound_receipt["derived_max_inflight_ms"],
            "reported_latency_usec": reported_latency_values,
            "reported_sink_identity": reported_latency,
        }
        required_observables = {
            "tts_runtime_binary_sha256": runtime_sha,
            "playback_stream_identity": cancel_playback_identity,
            "capture_stream_identity": cancel_capture_identity,
            "pipewire_quantum_and_reported_latency": pipewire_quantum_and_reported_latency,
        }
        required_observables_ok = required_observables_complete(required_observables)
        if not required_observables_ok:
            raise EvidenceInvalid("CANONICAL_REQUIRED_OBSERVABLES_INCOMPLETE")

        report.update({
            "canonical_required_observables": required_observables,
            "packet_audio_binding": packet_audio_binding,
            "source": {
                "wav_path": str(args.source),
                "wav_sha256": sha256_file(args.source),
                "wav_meta": source_meta,
                "text_sha256": sha256_text(tts_text),
                "tts_runtime_path": str(piper_runtime_path),
                "tts_runtime_binary_sha256": runtime_sha,
                "tts_distribution_version": piper_version,
                "tts_model_sha256": args.tts_model_sha256,
                "tts_config_sha256": args.tts_config_sha256,
            },
            "pipewire": {
                "pactl_info": pactl_info,
                "pipewire_version": pipewire_version,
                "wireplumber_version": wireplumber_version,
                "sink_line": sink_line,
                "monitor_line": monitor_line,
                "exact_object_binding": object_binding,
                "pw_dump_sha256": hashlib.sha256(pw_dump.encode()).hexdigest(),
                "settings_sha256": hashlib.sha256(settings.encode()).hexdigest(),
                "preflight_bound": bound_receipt,
                "quantum_and_reported_latency": pipewire_quantum_and_reported_latency,
            },
            "control": {
                "playback_started_ns": control_play_start_ns,
                "playback_terminal_ns": control_play_end_ns,
                "capture_terminal_ns": control_capture_terminal_ns,
                "playback_stream_identity": control_playback_identity,
                "capture_stream_identity": control_capture_identity,
                "capture_wav_sha256": sha256_file(control_wav),
            },
            "cancel": {
                "session_id": session_id,
                "voice_output_packet_id": packet_id,
                "playback_started_ns": cancel_play_start_ns,
                "cancel_request_ns": cancel_request_ns,
                "cancel_offset_ms": cancel_offset_ms,
                "packet_terminal_ns": packet_terminal_ns,
                "playback_terminal_ns": propagation.playback_terminal_monotonic_ns,
                "capture_terminal_ns": cancel_capture_terminal_ns,
                "changed_packet_ids": list(changed),
                "packet_state": interrupted.playback_state,
                "commit_eligible": interrupted.commit_eligible,
                "cancel_authority_event": cancel_event.as_dict(),
                "playback_cancel_propagation": propagation.as_dict(),
                "playback_stream_identity": cancel_playback_identity,
                "capture_stream_identity": cancel_capture_identity,
                "capture_wav_sha256": sha256_file(cancel_wav),
                "max_inflight_ms_predeclared": args.max_inflight_ms,
                "independent_test_kill_before_propagation": False,
            },
            "analysis": analysis,
            "cleanup": {
                "exact_object_serials_absent_after_unload": exact_identity_cleanup_ok,
                "run_owned_names_absent_after_unload": name_cleanup_ok,
                "run_owned_sink_removed": cleanup_ok,
                "independent_direct_playback_kill_used_for_cleanup": cleanup_direct_kill_used,
            },
            "replacement_generation_extra_evidence": {
                "terminal_gate_required": False,
                "provided_by_launcher": bool(args.replacement_source and args.replacement_source.is_file()),
                "consumed_for_terminal_credit": False,
            },
            "external_inference_api_calls": 0,
        })

        packet_fence_ok = interrupted.playback_state == "interrupted" and not interrupted.commit_eligible
        audio_pass = bool(analysis.get("pass"))
        causal_propagation_ok = (
            propagation.independent_test_kill_before_propagation is False
            and propagation.voice_output_packet_id == packet_id
            and propagation.cancel_event_id == cancel_event.event_id
            and propagation.process_alive_before_propagation
        )
        complete = bool(
            audio_pass
            and required_observables_ok
            and packet_fence_ok
            and causal_propagation_ok
            and cleanup_ok
            and analyzer_proc.returncode == 0
        )
        report["measured_credit"] = {
            "owner_vps_pipewire_virtual_sink_playback_readback": 1 if complete else 0,
            "bounded_cancellation_to_virtual_audio_monitor_silence": 1 if complete else 0,
            "packet_cancel_to_bound_playback_client_terminalization": 1 if complete else 0,
            "canonical_required_observables_bound": 1 if complete else 0,
        }
        if complete:
            report["result"] = "NO_COUNTEREXAMPLE"
            report["failure_class"] = None
            report["classification"] = "ACCEPT_AT_BOUNDED_S2_OWNER_VPS_PIPEWIRE_PRODUCT_CAUSAL_MONITOR_SCOPE_ONLY"
        elif not audio_pass:
            cls = str(analysis.get("classification", ""))
            report["result"] = "COUNTEREXAMPLE_OR_INVALID"
            report["failure_class"] = "EVIDENCE_INVALID" if cls.startswith("EVIDENCE_INVALID") else "PRODUCT_NEGATIVE"
            report["classification"] = cls or "ANALYZER_REJECTED"
        elif not cleanup_ok:
            report["result"] = "COUNTEREXAMPLE"
            report["failure_class"] = "PRODUCT_NEGATIVE"
            report["classification"] = "RUN_OWNED_PIPEWIRE_NODE_CLEANUP_FAILED"
        elif not causal_propagation_ok:
            report["result"] = "NOT_ACCEPTED"
            report["failure_class"] = "EVIDENCE_INVALID"
            report["classification"] = "PRODUCT_CANCEL_TO_PLAYBACK_CAUSAL_BINDING_INVALID"
        else:
            report["result"] = "COUNTEREXAMPLE"
            report["failure_class"] = "PRODUCT_NEGATIVE"
            report["classification"] = "PACKET_FENCE_OR_ANALYZER_EXIT_FAILED"

    except ProductNegative as exc:
        report["stage"] = stage
        report["result"] = "COUNTEREXAMPLE"
        report["failure_class"] = "PRODUCT_NEGATIVE"
        report["classification"] = str(exc)
    except (EvidenceInvalid, ValueError, json.JSONDecodeError) as exc:
        report["stage"] = stage
        report["result"] = "BLOCKED"
        report["failure_class"] = "EVIDENCE_INVALID"
        report["classification"] = f"{type(exc).__name__}:{exc}"
    except Exception as exc:
        report["stage"] = stage
        report["result"] = "BLOCKED"
        report["failure_class"] = "INFRA_AUTH_TRANSPORT_QUOTA"
        report["classification"] = f"{type(exc).__name__}:{exc}"
    finally:
        if control_cap is not None and control_fh is not None:
            capture_stop(control_cap, control_fh)
        if cancel_cap is not None and cancel_fh is not None:
            capture_stop(cancel_cap, cancel_fh)
        if cancel_play is not None and cancel_play.poll() is None:
            cleanup_direct_kill_used = True
            cancel_play.terminate()
            try:
                cancel_play.wait(timeout=3)
            except subprocess.TimeoutExpired:
                cancel_play.kill()
                cancel_play.wait(timeout=3)
        if module_id:
            run(["pactl", "unload-module", module_id], check=False)
        report.setdefault("cleanup", {})["independent_direct_playback_kill_used_for_cleanup"] = cleanup_direct_kill_used

    encoded = base64.b64encode(json.dumps(report, sort_keys=True).encode()).decode()
    print("T4_G2_PIPEWIRE_RECEIPT_B64=" + encoded)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "NO_COUNTEREXAMPLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
