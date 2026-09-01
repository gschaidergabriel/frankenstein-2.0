#!/usr/bin/env python3
"""Trigger-4 G2 PipeWire terminal-scope runtime discriminator.

Evidence scope only. Runs inside admitted disposable S2 owner-VPS sandbox.
Reuses VoicePacketCortex cancellation authority and binds playback termination to
its BARGE_IN_CANCEL_PROPAGATED event through a measurement adapter. No physical,
GWT/J-Space, effect, training, whole-voice, or whole-product credit is created.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import wave
from typing import Any

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoicePacketCortex

SCHEMA = "T4_G2_PIPEWIRE_S2_PLAYBACK_CANCEL_MONITOR/v2"
SEMANTIC_KEY = "0d83f7d13c1d8f91686cf94070f73d901a49018b40a9c058d1949af094655bff"
BOUND_POLICY = "PIPEWIRE_PREFLIGHT_BOUND_V1"
MIN_POSTROLL_MS = 500.0


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


def raw_to_wav(raw: Path, wav_path: Path, *, rate: int, channels: int) -> None:
    data = raw.read_bytes()
    frame_bytes = 2 * channels
    data = data[: len(data) - (len(data) % frame_bytes)]
    with wave.open(str(wav_path), "wb") as wf:
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


def parse_pipewire_settings(settings: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for key in ("clock.rate", "clock.quantum", "clock.min-quantum", "clock.max-quantum"):
        match = re.search(rf"{re.escape(key)}[^0-9]+([0-9]+(?:\.[0-9]+)?)", settings)
        if match:
            values[key] = float(match.group(1))
    if values.get("clock.rate", 0.0) <= 0 or values.get("clock.quantum", 0.0) <= 0:
        raise RuntimeError("EVIDENCE_INVALID_PIPEWIRE_RATE_QUANTUM_NOT_BOUND")
    return values


def derive_inflight_bound_ms(settings: str) -> tuple[float, dict[str, Any]]:
    values = parse_pipewire_settings(settings)
    rate = values["clock.rate"]
    quantum = values["clock.quantum"]
    quantum_ms = 1000.0 * quantum / rate
    bound_ms = max(250.0, (8.0 * quantum_ms) + 20.0)
    receipt = {
        "schema": "T4_G2_PIPEWIRE_PREFLIGHT_BOUND/v1",
        "policy": BOUND_POLICY,
        "clock_rate_hz": rate,
        "clock_quantum_frames": quantum,
        "clock_quantum_ms": quantum_ms,
        "clock_min_quantum_frames": values.get("clock.min-quantum"),
        "clock_max_quantum_frames": values.get("clock.max-quantum"),
        "formula": "max(250ms, 8*clock_quantum_ms + 20ms)",
        "max_inflight_ms": bound_ms,
        "observed_before_playback": True,
    }
    receipt["sha256"] = sha256_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return bound_ms, receipt


def parse_pw_objects(pw_dump: str, sink_name: str, monitor_name: str) -> dict[str, dict[str, Any]]:
    try:
        objects = json.loads(pw_dump)
    except json.JSONDecodeError as exc:
        raise RuntimeError("EVIDENCE_INVALID_PW_DUMP_JSON") from exc
    if not isinstance(objects, list):
        raise RuntimeError("EVIDENCE_INVALID_PW_DUMP_NOT_LIST")

    def select(name: str) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            info = obj.get("info")
            props = info.get("props") if isinstance(info, dict) else None
            if not isinstance(props, dict):
                continue
            names = {str(props.get(k, "")) for k in ("node.name", "node.nick", "node.description")}
            if name not in names:
                continue
            serial = props.get("object.serial")
            if serial in (None, ""):
                raise RuntimeError(f"EVIDENCE_INVALID_PIPEWIRE_OBJECT_SERIAL_MISSING:{name}")
            candidates.append({
                "id": obj.get("id"),
                "type": obj.get("type"),
                "object_serial": str(serial),
                "node_name": props.get("node.name"),
                "node_nick": props.get("node.nick"),
                "node_description": props.get("node.description"),
                "media_class": props.get("media.class"),
                "device_id": props.get("device.id"),
            })
        if len(candidates) != 1:
            raise RuntimeError(f"EVIDENCE_INVALID_PIPEWIRE_OBJECT_IDENTITY_AMBIGUOUS:{name}:{len(candidates)}")
        return candidates[0]

    return {"sink": select(sink_name), "monitor": select(monitor_name)}


def identities_absent(pw_dump: str, identities: dict[str, dict[str, Any]]) -> bool:
    try:
        objects = json.loads(pw_dump)
    except json.JSONDecodeError:
        return False
    serials = {x["object_serial"] for x in identities.values()}
    for obj in objects if isinstance(objects, list) else []:
        info = obj.get("info") if isinstance(obj, dict) else None
        props = info.get("props") if isinstance(info, dict) else None
        if isinstance(props, dict) and str(props.get("object.serial", "")) in serials:
            return False
    return True


def make_cortex(packet_id: str, planned_ms: int) -> tuple[VoicePacketCortex, str]:
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
        input_sha256="4" * 64,
        provenance_refs=("trigger4:g2-pipewire-monitor",),
    )
    session = VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id="causal-t4-g2-session", generation=2, turn_id="turn-session"
        ),
        provenance_refs=("trigger4:g2-pipewire-session",),
    )
    cortex = VoicePacketCortex(session, presence_state="PRESENT_INTERRUPTIBLE", opened_monotonic_ms=0)
    cortex.queue_output(
        turn_id="turn-a", packet_id=packet_id, monotonic_ms=10,
        text_segment="Dies ist die gebundene alte Ausgabe fuer den PipeWire Abbruchtest.",
        expression_intent="neutral", speech_act="ANSWER", planned_audio_duration_ms=planned_ms,
        sequence=0, cancellable=True,
    )
    return cortex, session.voice_session_id


def capture_start(monitor: str, raw_path: Path, *, rate: int, channels: int) -> tuple[subprocess.Popen, Any]:
    fh = raw_path.open("wb")
    proc = subprocess.Popen(
        ["parec", f"--device={monitor}", "--format=s16le", f"--rate={rate}", f"--channels={channels}", "--raw"],
        stdout=fh, stderr=subprocess.PIPE,
    )
    time.sleep(0.3)
    if proc.poll() is not None:
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        fh.close()
        raise RuntimeError(f"MONITOR_CAPTURE_DIED:{proc.returncode}:{err[-1000:]}")
    return proc, fh


def terminate_process(proc: subprocess.Popen, *, timeout_s: float = 3.0) -> int:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout_s)
    return time.monotonic_ns()


def capture_stop(proc: subprocess.Popen, fh: Any) -> None:
    terminate_process(proc)
    try:
        fh.close()
    except Exception:
        pass


def play_start(sink: str, source: Path) -> tuple[subprocess.Popen, int]:
    proc = subprocess.Popen(["paplay", f"--device={sink}", str(source)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    started_ns = time.monotonic_ns()
    time.sleep(0.15)
    if proc.poll() is not None:
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise RuntimeError(f"PLAYBACK_DIED_EARLY:{proc.returncode}:{err[-1000:]}")
    return proc, started_ns


class CancelPlaybackBridge:
    """Measurement adapter: only BARGE_IN_CANCEL_PROPAGATED may stop bound playback."""

    def __init__(self, cortex: VoicePacketCortex, packet_id: str, proc: subprocess.Popen) -> None:
        self.cortex = cortex
        self.packet_id = packet_id
        self.proc = proc
        self.adapter_id = f"g2-cancel-playback-bridge:{packet_id}"
        self.event_id: str | None = None
        self.event_kind: str | None = None
        self.terminal_ns: int | None = None
        self.error: str | None = None
        self.safety_teardown_used = False
        self.done = threading.Event()
        self._thread = threading.Thread(target=self._run, name=self.adapter_id, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        try:
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                for event in reversed(self.cortex.events):
                    if event.event_kind == "BARGE_IN_CANCEL_PROPAGATED" and self.packet_id in event.packet_refs:
                        self.event_id = event.event_id
                        self.event_kind = event.event_kind
                        self.terminal_ns = terminate_process(self.proc)
                        self.done.set()
                        return
                if self.proc.poll() is not None:
                    self.error = "PLAYBACK_TERMINATED_BEFORE_CANCEL_AUTHORITY_EVENT"
                    self.done.set()
                    return
                time.sleep(0.005)
            self.error = "CANCEL_AUTHORITY_EVENT_NOT_OBSERVED_BY_PLAYBACK_BRIDGE"
            self.done.set()
        except Exception as exc:
            self.error = f"{type(exc).__name__}:{exc}"
            self.done.set()

    def wait(self, timeout_s: float = 5.5) -> None:
        if not self.done.wait(timeout_s):
            self.error = "PLAYBACK_BRIDGE_TIMEOUT"
        if self.error:
            raise RuntimeError("EVIDENCE_INVALID_PRODUCT_CANCEL_PLAYBACK_BINDING:" + self.error)
        if self.event_id is None or self.terminal_ns is None:
            raise RuntimeError("EVIDENCE_INVALID_PRODUCT_CANCEL_PLAYBACK_BINDING_INCOMPLETE")

    def safety_teardown(self) -> None:
        if self.proc.poll() is None:
            self.safety_teardown_used = True
            terminate_process(self.proc)


def correlate_exact_source(source: Path, capture: Path) -> dict[str, Any]:
    import numpy as np

    def load(path: Path) -> tuple[int, Any]:
        with wave.open(str(path), "rb") as wf:
            if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
                raise RuntimeError("EVIDENCE_INVALID_REPLACEMENT_WAV_FORMAT")
            rate = wf.getframerate()
            frames = wf.getnframes()
            arr = np.frombuffer(wf.readframes(frames), dtype="<i2").astype(np.float64) / 32768.0
            return rate, arr

    rate_s, src = load(source)
    rate_c, cap = load(capture)
    if rate_s != rate_c:
        raise RuntimeError("EVIDENCE_INVALID_REPLACEMENT_RATE_MISMATCH")
    if len(cap) < len(src):
        raise RuntimeError("EVIDENCE_INVALID_REPLACEMENT_CAPTURE_TOO_SHORT")
    ref = src - float(src.mean())
    obs = cap - float(cap.mean())
    nfft = 1 << (len(obs) + len(ref) - 2).bit_length()
    corr = np.fft.irfft(np.fft.rfft(obs, n=nfft) * np.fft.rfft(ref[::-1], n=nfft), n=nfft)
    valid = corr[len(ref) - 1 : len(obs)]
    if valid.size == 0:
        raise RuntimeError("EVIDENCE_INVALID_REPLACEMENT_ALIGNMENT_EMPTY")
    offset = int(np.argmax(np.abs(valid)))
    aligned = cap[offset : offset + len(src)]
    a = src - float(src.mean())
    b = aligned - float(aligned.mean())
    denom = float(np.sqrt(np.dot(a, a) * np.dot(b, b)))
    score = float(np.dot(a, b) / denom) if denom > 1e-15 else 0.0
    return {"offset_frames": offset, "correlation": score, "pass": score >= 0.90}


def text_binding(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError("EVIDENCE_INVALID_TTS_TEXT_PROVENANCE_EMPTY")
    return {"path": str(path), "sha256": sha256_file(path), "text": text}


def packet_audio_binding(*, packet_id: str, output_generation: int, wav: Path, text_file: Path,
                         tts_model_sha256: str, tts_config_sha256: str,
                         tts_runtime_version: str, f2_subject_sha: str) -> dict[str, Any]:
    binding = {
        "schema": "T4_G2_PACKET_AUDIO_TTS_BINDING/v1",
        "packet_id": packet_id,
        "output_generation": output_generation,
        "wav_sha256": sha256_file(wav),
        "wav_meta": read_wav_meta(wav),
        "text_provenance": text_binding(text_file),
        "tts_model_sha256": tts_model_sha256,
        "tts_config_sha256": tts_config_sha256,
        "tts_runtime_version": tts_runtime_version,
        "python_version": sys.version,
        "python_executable": sys.executable,
        "python_executable_sha256": sha256_file(Path(sys.executable)) if Path(sys.executable).is_file() else None,
        "f2_subject_sha": f2_subject_sha,
        "bound_before_playback": True,
    }
    binding["sha256"] = sha256_text(json.dumps(binding, sort_keys=True, separators=(",", ":")))
    return binding


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--source-text-file", type=Path, required=True)
    ap.add_argument("--replacement-source", type=Path, required=True)
    ap.add_argument("--replacement-text-file", type=Path, required=True)
    ap.add_argument("--analyzer", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--f2-subject-sha", required=True)
    ap.add_argument("--tts-model-sha256", required=True)
    ap.add_argument("--tts-config-sha256", required=True)
    ap.add_argument("--tts-runtime-version", required=True)
    ap.add_argument("--sink-name", default="f2_voice_g2_sink")
    ap.add_argument("--cancel-after-ms", type=float, default=1200.0)
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
            "producer_tts_generation_cancel": 0,
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
    replacement_raw = args.workdir / "replacement.raw"
    control_wav = args.workdir / "control.wav"
    cancel_wav = args.workdir / "cancel.wav"
    replacement_wav = args.workdir / "replacement.wav"
    analysis_json = args.workdir / "analysis.json"
    active_capture: tuple[subprocess.Popen, Any] | None = None
    cancel_bridge: CancelPlaybackBridge | None = None

    try:
        for required in (args.source, args.source_text_file, args.replacement_source, args.replacement_text_file, args.analyzer):
            if not required.is_file():
                raise RuntimeError(f"BOUND_INPUT_MISSING:{required}")
        if sha256_file(args.source) == sha256_file(args.replacement_source):
            raise RuntimeError("EVIDENCE_INVALID_REPLACEMENT_WAV_NOT_DISTINCT")
        source_meta = read_wav_meta(args.source)
        replacement_meta = read_wav_meta(args.replacement_source)
        if source_meta["sample_width"] != 2 or source_meta["channels"] != 1:
            raise RuntimeError(f"SOURCE_MUST_BE_MONO_PCM16:{source_meta}")
        if replacement_meta["sample_width"] != 2 or replacement_meta["channels"] != 1:
            raise RuntimeError(f"REPLACEMENT_SOURCE_MUST_BE_MONO_PCM16:{replacement_meta}")
        if replacement_meta["rate"] != source_meta["rate"]:
            raise RuntimeError("EVIDENCE_INVALID_REPLACEMENT_SOURCE_RATE_MISMATCH")
        duration_ms = source_meta["frames"] * 1000.0 / source_meta["rate"]
        wait_pulse()

        stage = "PIPEWIRE_GRAPH_PREFLIGHT"
        pactl_info = run(["pactl", "info"]).stdout
        pipewire_version = run(["pipewire", "--version"], check=False).stdout.strip()
        wireplumber_version = run(["wireplumber", "--version"], check=False).stdout.strip()
        if "PipeWire" not in pactl_info and "pipewire" not in pactl_info.lower():
            raise RuntimeError("PACTL_SERVER_NOT_IDENTIFIED_AS_PIPEWIRE")
        loaded = run([
            "pactl", "load-module", "module-null-sink", f"sink_name={args.sink_name}",
            "format=s16le", f"rate={source_meta['rate']}", "channels=1",
        ])
        module_id = loaded.stdout.strip()
        if not module_id.isdigit():
            raise RuntimeError(f"NULL_SINK_MODULE_ID_INVALID:{module_id}")
        sink_line = wait_named_line(["pactl", "list", "short", "sinks"], args.sink_name)
        monitor_name = f"{args.sink_name}.monitor"
        monitor_line = wait_named_line(["pactl", "list", "short", "sources"], monitor_name)
        pw_dump = run(["pw-dump"]).stdout
        settings = run(["pw-metadata", "-n", "settings"]).stdout
        identities = parse_pw_objects(pw_dump, args.sink_name, monitor_name)
        max_inflight_ms, bound_receipt = derive_inflight_bound_ms(settings)
        if duration_ms < args.cancel_after_ms + max_inflight_ms + MIN_POSTROLL_MS:
            raise RuntimeError("SOURCE_TOO_SHORT_FOR_PREFLIGHT_DERIVED_CANCEL_BOUND")
        preflight_receipt = {
            "pipewire_versions": {"pipewire": pipewire_version, "wireplumber": wireplumber_version},
            "pactl_info_sha256": sha256_text(pactl_info),
            "settings_sha256": sha256_text(settings),
            "pw_dump_sha256": sha256_text(pw_dump),
            "object_identities": identities,
            "inflight_bound": bound_receipt,
            "captured_before_control": True,
        }
        preflight_receipt["sha256"] = sha256_text(json.dumps(preflight_receipt, sort_keys=True, separators=(",", ":")))

        old_packet_id = "output-old-g2-pipewire"
        cortex, session_id = make_cortex(old_packet_id, int(round(duration_ms)))
        old_binding = packet_audio_binding(
            packet_id=old_packet_id,
            output_generation=1,
            wav=args.source,
            text_file=args.source_text_file,
            tts_model_sha256=args.tts_model_sha256,
            tts_config_sha256=args.tts_config_sha256,
            tts_runtime_version=args.tts_runtime_version,
            f2_subject_sha=args.f2_subject_sha,
        )

        stage = "CONTROL"
        active_capture = capture_start(monitor_name, control_raw, rate=source_meta["rate"], channels=1)
        control_play, control_play_start_ns = play_start(args.sink_name, args.source)
        control_rc = control_play.wait(timeout=max(10.0, duration_ms / 1000.0 + 5.0))
        control_play_end_ns = time.monotonic_ns()
        if control_rc != 0:
            err = control_play.stderr.read().decode(errors="replace") if control_play.stderr else ""
            raise RuntimeError(f"CONTROL_PLAYBACK_FAILED:{control_rc}:{err[-1000:]}")
        time.sleep(0.5)
        capture_stop(*active_capture)
        active_capture = None
        raw_to_wav(control_raw, control_wav, rate=source_meta["rate"], channels=1)

        stage = "CAUSAL_CANCEL"
        cortex.advance_output(old_packet_id, playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        active_capture = capture_start(monitor_name, cancel_raw, rate=source_meta["rate"], channels=1)
        cancel_play, cancel_play_start_ns = play_start(args.sink_name, args.source)
        cancel_bridge = CancelPlaybackBridge(cortex, old_packet_id, cancel_play)
        cancel_bridge.start()
        time.sleep(max(0.0, args.cancel_after_ms / 1000.0 - 0.15))
        cancel_request_ns = time.monotonic_ns()
        cancel_offset_ms = (cancel_request_ns - cancel_play_start_ns) / 1_000_000.0
        packet_cancel_ms = max(21, int(round(cancel_offset_ms)) + 20)
        changed = cortex.cancel_for_barge_in(turn_id="turn-b", monotonic_ms=packet_cancel_ms)
        packet_terminal_ns = time.monotonic_ns()
        if old_packet_id not in changed:
            raise AssertionError("PACKET_CANCEL_DID_NOT_TOUCH_BOUND_OUTPUT")
        interrupted = next(p for p in cortex.outputs if p.packet_id == old_packet_id)
        if interrupted.playback_state != "interrupted" or interrupted.commit_eligible:
            raise AssertionError("PACKET_FENCE_FAILED_AFTER_CANCEL")
        cancel_bridge.wait()
        playback_terminal_ns = cancel_bridge.terminal_ns
        time.sleep(max_inflight_ms / 1000.0 + 0.8)
        capture_stop(*active_capture)
        active_capture = None
        raw_to_wav(cancel_raw, cancel_wav, rate=source_meta["rate"], channels=1)

        stage = "PCM_ANALYSIS"
        analyzer_cmd = [
            sys.executable, str(args.analyzer),
            "--source", str(args.source),
            "--control", str(control_wav),
            "--cancel", str(cancel_wav),
            "--output", str(analysis_json),
            "--cancel-offset-ms", f"{cancel_offset_ms:.6f}",
            "--max-inflight-ms", f"{max_inflight_ms:.6f}",
            "--voice-output-packet-id", old_packet_id,
            "--f2-subject-sha", args.f2_subject_sha,
        ]
        analyzer_proc = run(analyzer_cmd, check=False)
        analysis = json.loads(analysis_json.read_text()) if analysis_json.exists() else None
        if not isinstance(analysis, dict):
            raise RuntimeError(f"ANALYZER_DID_NOT_EMIT_RECEIPT:{analyzer_proc.returncode}")
        if not analysis.get("pass") or analyzer_proc.returncode != 0:
            cls = str(analysis.get("classification", "ANALYZER_REJECTED"))
            report["analysis"] = analysis
            report["result"] = "COUNTEREXAMPLE_OR_INVALID"
            report["failure_class"] = "EVIDENCE_INVALID" if cls.startswith("EVIDENCE_INVALID") else "PRODUCT_NEGATIVE"
            report["classification"] = cls
            raise StopIteration

        stage = "REPLACEMENT_GENERATION_READBACK"
        replacement_packet_id = "output-new-g2-pipewire"
        replacement_duration_ms = replacement_meta["frames"] * 1000.0 / replacement_meta["rate"]
        cortex.queue_output(
            turn_id="turn-c",
            packet_id=replacement_packet_id,
            monotonic_ms=packet_cancel_ms + 10,
            text_segment=text_binding(args.replacement_text_file)["text"],
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=int(round(replacement_duration_ms)),
            sequence=0,
            cancellable=True,
        )
        replacement_binding = packet_audio_binding(
            packet_id=replacement_packet_id,
            output_generation=2,
            wav=args.replacement_source,
            text_file=args.replacement_text_file,
            tts_model_sha256=args.tts_model_sha256,
            tts_config_sha256=args.tts_config_sha256,
            tts_runtime_version=args.tts_runtime_version,
            f2_subject_sha=args.f2_subject_sha,
        )
        cortex.advance_output(
            replacement_packet_id,
            playback_state="started",
            monotonic_ms=packet_cancel_ms + 20,
            heard_fraction=0.0,
        )
        active_capture = capture_start(monitor_name, replacement_raw, rate=replacement_meta["rate"], channels=1)
        replacement_play, replacement_play_start_ns = play_start(args.sink_name, args.replacement_source)
        replacement_rc = replacement_play.wait(timeout=max(10.0, replacement_duration_ms / 1000.0 + 5.0))
        replacement_play_end_ns = time.monotonic_ns()
        if replacement_rc != 0:
            raise RuntimeError(f"REPLACEMENT_PLAYBACK_FAILED:{replacement_rc}")
        time.sleep(0.5)
        capture_stop(*active_capture)
        active_capture = None
        raw_to_wav(replacement_raw, replacement_wav, rate=replacement_meta["rate"], channels=1)
        replacement_analysis = correlate_exact_source(args.replacement_source, replacement_wav)
        if not replacement_analysis["pass"]:
            raise RuntimeError("EVIDENCE_INVALID_REPLACEMENT_GENERATION_MONITOR_READBACK")
        cortex.advance_output(
            replacement_packet_id,
            playback_state="completed",
            monotonic_ms=packet_cancel_ms + 30,
            heard_fraction=1.0,
        )
        replacement_packet = next(p for p in cortex.outputs if p.packet_id == replacement_packet_id)
        if not replacement_packet.commit_eligible:
            raise AssertionError("REPLACEMENT_PACKET_NOT_COMMIT_ELIGIBLE_AFTER_POSITIVE_READBACK")

        stage = "CLEANUP"
        run(["pactl", "unload-module", module_id], check=True)
        module_id = None
        time.sleep(0.2)
        sinks_after = run(["pactl", "list", "short", "sinks"], check=False).stdout
        sources_after = run(["pactl", "list", "short", "sources"], check=False).stdout
        pw_dump_after = run(["pw-dump"], check=False).stdout
        cleanup_ok = (
            args.sink_name not in sinks_after
            and monitor_name not in sources_after
            and identities_absent(pw_dump_after, identities)
        )
        if not cleanup_ok:
            raise RuntimeError("EVIDENCE_INVALID_RUN_OWNED_PIPEWIRE_IDENTITY_CLEANUP_FAILED")

        cancel_event = next(
            e for e in reversed(cortex.events)
            if e.event_kind == "BARGE_IN_CANCEL_PROPAGATED" and old_packet_id in e.packet_refs
        )
        report.update({
            "preflight": preflight_receipt,
            "source": {
                "old_packet_audio_binding": old_binding,
                "replacement_packet_audio_binding": replacement_binding,
            },
            "pipewire": {
                "pactl_info": pactl_info,
                "pipewire_version": pipewire_version,
                "wireplumber_version": wireplumber_version,
                "sink_line": sink_line,
                "monitor_line": monitor_line,
                "object_identities": identities,
                "settings": settings[-4000:],
                "pw_dump_sha256": sha256_text(pw_dump),
            },
            "control": {
                "playback_started_ns": control_play_start_ns,
                "playback_terminal_ns": control_play_end_ns,
                "capture_wav_sha256": sha256_file(control_wav),
                "source_wav_sha256": sha256_file(args.source),
            },
            "cancel": {
                "session_id": session_id,
                "voice_output_packet_id": old_packet_id,
                "playback_started_ns": cancel_play_start_ns,
                "cancel_request_ns": cancel_request_ns,
                "cancel_offset_ms": cancel_offset_ms,
                "packet_terminal_ns": packet_terminal_ns,
                "playback_terminal_ns": playback_terminal_ns,
                "changed_packet_ids": list(changed),
                "packet_state": interrupted.playback_state,
                "commit_eligible": interrupted.commit_eligible,
                "capture_wav_sha256": sha256_file(cancel_wav),
                "max_inflight_ms_predeclared": max_inflight_ms,
                "bound_receipt_sha256": bound_receipt["sha256"],
                "cancel_authority_event": cancel_event.as_dict(),
                "playback_bridge": {
                    "adapter_id": cancel_bridge.adapter_id,
                    "authority_event_id": cancel_bridge.event_id,
                    "authority_event_kind": cancel_bridge.event_kind,
                    "terminal_ns": cancel_bridge.terminal_ns,
                    "safety_teardown_used_before_terminalization": cancel_bridge.safety_teardown_used,
                },
            },
            "analysis": analysis,
            "replacement": {
                "packet_id": replacement_packet_id,
                "output_generation": 2,
                "playback_started_ns": replacement_play_start_ns,
                "playback_terminal_ns": replacement_play_end_ns,
                "capture_wav_sha256": sha256_file(replacement_wav),
                "source_wav_sha256": sha256_file(args.replacement_source),
                "monitor_readback": replacement_analysis,
                "packet_commit_eligible_after_positive_readback": True,
            },
            "cleanup": {"run_owned_sink_monitor_removed_by_exact_identity": True},
            "external_inference_api_calls": 0,
            "measured_credit": {
                "owner_vps_pipewire_virtual_sink_playback_readback": 1,
                "bounded_cancellation_to_virtual_audio_monitor_silence": 1,
                "replacement_generation_positive_virtual_monitor_readback": 1,
                "packet_audio_tts_causal_binding": 1,
                "pipewire_object_serial_binding": 1,
                "preflight_derived_inflight_bound": 1,
                "packet_cancel_event_to_playback_adapter_terminalization": 1,
            },
            "result": "NO_COUNTEREXAMPLE",
            "failure_class": None,
            "classification": "ACCEPT_AT_BOUNDED_S2_OWNER_VPS_PIPEWIRE_G2_TERMINAL_MEASUREMENT_SCOPE_ONLY",
        })

    except StopIteration:
        pass
    except AssertionError as exc:
        report["stage"] = stage
        report["result"] = "COUNTEREXAMPLE"
        report["failure_class"] = "PRODUCT_NEGATIVE"
        report["classification"] = str(exc)
    except Exception as exc:
        report["stage"] = stage
        report["result"] = "BLOCKED"
        message = f"{type(exc).__name__}:{exc}"
        report["classification"] = message
        if "PRODUCT_NEGATIVE" in message:
            report["failure_class"] = "PRODUCT_NEGATIVE"
        elif "EVIDENCE_INVALID" in message or stage in {"PCM_ANALYSIS", "REPLACEMENT_GENERATION_READBACK", "CLEANUP"}:
            report["failure_class"] = "EVIDENCE_INVALID"
        else:
            report["failure_class"] = "INFRA_AUTH_TRANSPORT_QUOTA"
    finally:
        if active_capture is not None:
            capture_stop(*active_capture)
        if cancel_bridge is not None:
            cancel_bridge.safety_teardown()
        if module_id:
            run(["pactl", "unload-module", module_id], check=False)

    encoded = base64.b64encode(json.dumps(report, sort_keys=True).encode()).decode()
    print("T4_G2_PIPEWIRE_RECEIPT_B64=" + encoded)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "NO_COUNTEREXAMPLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
