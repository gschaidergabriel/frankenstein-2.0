#!/usr/bin/env python3
"""Trigger-4 G2 PipeWire virtual-sink playback/cancel/replacement runtime discriminator.

Runtime/falsifier scope only. This script must run inside the admitted disposable
S2 owner-VPS sandbox with a sandbox-local PipeWire/PipeWire-Pulse session.
It reuses VoicePacketCortex cancellation authority and does not create a second
turn/state/effect/playback authority.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import wave

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoicePacketCortex

SCHEMA = "T4_G2_PIPEWIRE_S2_PLAYBACK_CANCEL_MONITOR/v2"
SEMANTIC_KEY = "0d83f7d13c1d8f91686cf94070f73d901a49018b40a9c058d1949af094655bff"
MIN_REPLACEMENT_CORRELATION = 0.80


def run(cmd: list[str], *, check: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_sha256(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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


def _pactl_named(items: object, name: str, kind: str) -> dict:
    if not isinstance(items, list):
        raise RuntimeError(f"PACTL_{kind.upper()}_JSON_NOT_LIST")
    matches = [row for row in items if isinstance(row, dict) and row.get("name") == name]
    if len(matches) != 1:
        raise RuntimeError(f"PACTL_{kind.upper()}_IDENTITY_AMBIGUOUS:{name}:{len(matches)}")
    row = matches[0]
    props = row.get("properties")
    if not isinstance(props, dict):
        raise RuntimeError(f"PACTL_{kind.upper()}_PROPERTIES_MISSING:{name}")
    serial = props.get("object.serial")
    if serial is None or str(serial).strip() == "":
        raise RuntimeError(f"PACTL_{kind.upper()}_OBJECT_SERIAL_MISSING:{name}")
    return {
        "kind": kind,
        "index": row.get("index"),
        "name": row.get("name"),
        "description": row.get("description"),
        "object_serial": str(serial),
        "node_name": props.get("node.name"),
        "media_class": props.get("media.class"),
        "device_id": props.get("device.id"),
        "monitor_of_sink": row.get("monitor_of_sink"),
        "monitor_source": row.get("monitor_source"),
    }


def _pw_dump_by_serial(pw_dump_text: str, object_serial: str, kind: str) -> dict:
    try:
        payload = json.loads(pw_dump_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("PW_DUMP_INVALID_JSON") from exc
    if not isinstance(payload, list):
        raise RuntimeError("PW_DUMP_NOT_LIST")
    matches: list[dict] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        info = row.get("info")
        props = info.get("props") if isinstance(info, dict) else None
        if not isinstance(props, dict):
            continue
        if str(props.get("object.serial", "")) == object_serial:
            matches.append(
                {
                    "kind": kind,
                    "id": row.get("id"),
                    "type": row.get("type"),
                    "object_serial": object_serial,
                    "node_name": props.get("node.name"),
                    "media_class": props.get("media.class"),
                    "device_id": props.get("device.id"),
                    "object_path": props.get("object.path"),
                }
            )
    if len(matches) != 1:
        raise RuntimeError(f"PW_DUMP_{kind.upper()}_SERIAL_AMBIGUOUS:{object_serial}:{len(matches)}")
    return matches[0]


def bind_pipewire_objects(sink_name: str, monitor_name: str) -> tuple[dict, str]:
    sinks = json.loads(run(["pactl", "-f", "json", "list", "sinks"]).stdout)
    sources = json.loads(run(["pactl", "-f", "json", "list", "sources"]).stdout)
    sink_pactl = _pactl_named(sinks, sink_name, "sink")
    monitor_pactl = _pactl_named(sources, monitor_name, "monitor")
    if sink_pactl["object_serial"] == monitor_pactl["object_serial"]:
        raise RuntimeError("PIPEWIRE_SINK_MONITOR_SERIAL_COLLISION")
    pw_dump = run(["pw-dump"]).stdout
    sink_pw = _pw_dump_by_serial(pw_dump, sink_pactl["object_serial"], "sink")
    monitor_pw = _pw_dump_by_serial(pw_dump, monitor_pactl["object_serial"], "monitor")
    bound = {
        "sink": {"pactl": sink_pactl, "pw_dump": sink_pw},
        "monitor": {"pactl": monitor_pactl, "pw_dump": monitor_pw},
    }
    return bound, pw_dump


def assert_bound_objects_absent(bound: dict) -> dict:
    after_dump = run(["pw-dump"], check=False).stdout
    try:
        payload = json.loads(after_dump)
    except json.JSONDecodeError:
        payload = []
    serials: set[str] = set()
    if isinstance(payload, list):
        for row in payload:
            if not isinstance(row, dict):
                continue
            info = row.get("info")
            props = info.get("props") if isinstance(info, dict) else None
            if isinstance(props, dict) and props.get("object.serial") is not None:
                serials.add(str(props["object.serial"]))
    expected = {
        str(bound["sink"]["pactl"]["object_serial"]),
        str(bound["monitor"]["pactl"]["object_serial"]),
    }
    remaining = sorted(expected.intersection(serials))
    return {
        "bound_object_serials_absent": not remaining,
        "remaining_bound_object_serials": remaining,
        "pw_dump_after_sha256": sha256_bytes(after_dump.encode()),
    }


def load_tts_receipt(path: Path, source: Path, replacement: Path) -> tuple[dict, str]:
    try:
        receipt = json.loads(path.read_text())
    except Exception as exc:
        raise RuntimeError("TTS_RECEIPT_INVALID") from exc
    if not isinstance(receipt, dict):
        raise RuntimeError("TTS_RECEIPT_NOT_OBJECT")
    expected_source = sha256_file(source)
    expected_replacement = sha256_file(replacement)
    if receipt.get("source_wav_sha256") != expected_source:
        raise RuntimeError("TTS_RECEIPT_SOURCE_HASH_MISMATCH")
    if receipt.get("replacement_wav_sha256") != expected_replacement:
        raise RuntimeError("TTS_RECEIPT_REPLACEMENT_HASH_MISMATCH")
    if expected_source == expected_replacement:
        raise RuntimeError("REPLACEMENT_SOURCE_MUST_BE_DISTINCT")
    if not receipt.get("source_text") or not receipt.get("replacement_text"):
        raise RuntimeError("TTS_RECEIPT_TEXT_PROVENANCE_MISSING")
    return receipt, sha256_file(path)


def load_preflight_receipt(path: Path, expected_bound_ms: float) -> tuple[dict, str]:
    try:
        receipt = json.loads(path.read_text())
    except Exception as exc:
        raise RuntimeError("PREFLIGHT_RECEIPT_INVALID") from exc
    if not isinstance(receipt, dict):
        raise RuntimeError("PREFLIGHT_RECEIPT_NOT_OBJECT")
    if receipt.get("schema") != "T4_G2_PIPEWIRE_PREFLIGHT_BOUND/v1":
        raise RuntimeError("PREFLIGHT_RECEIPT_SCHEMA_MISMATCH")
    derived = receipt.get("derived_max_inflight_ms")
    if type(derived) not in (int, float) or not math.isfinite(float(derived)):
        raise RuntimeError("PREFLIGHT_DERIVED_BOUND_MISSING")
    if abs(float(derived) - float(expected_bound_ms)) > 1e-6:
        raise RuntimeError("PREFLIGHT_DERIVED_BOUND_MISMATCH")
    if not receipt.get("clock_rate") or not receipt.get("clock_quantum"):
        raise RuntimeError("PREFLIGHT_LATENCY_INPUT_MISSING")
    return receipt, sha256_file(path)


def packet_audio_binding(
    *,
    packet_id: str,
    output_generation: int,
    source: Path,
    tts_receipt: dict,
    tts_receipt_sha256: str,
    source_role: str,
    f2_subject_sha: str,
    tts_model_sha256: str,
    tts_config_sha256: str,
) -> dict:
    text_key = "source_text" if source_role == "old" else "replacement_text"
    return {
        "schema": "T4_G2_PACKET_AUDIO_BINDING/v1",
        "packet_id": packet_id,
        "output_generation": output_generation,
        "source_role": source_role,
        "source_wav_sha256": sha256_file(source),
        "source_text_sha256": sha256_bytes(str(tts_receipt[text_key]).encode("utf-8")),
        "tts_receipt_sha256": tts_receipt_sha256,
        "tts_provenance": tts_receipt.get("provenance"),
        "piper_tts_version": tts_receipt.get("piper_tts_version"),
        "tts_model_sha256": tts_model_sha256,
        "tts_config_sha256": tts_config_sha256,
        "python_version": platform.python_version(),
        "f2_subject_sha": f2_subject_sha,
    }


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
        text_segment="Dies ist die gebundene alte Ausgabe fuer den PipeWire Abbruchtest.",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=planned_ms,
        sequence=0,
        cancellable=True,
    )
    cortex.advance_output(packet_id, playback_state="started", monotonic_ms=20, heard_fraction=0.0)
    return cortex, session.voice_session_id


def queue_replacement(cortex: VoicePacketCortex, packet_id: str, planned_ms: int, monotonic_ms: int) -> None:
    cortex.queue_output(
        turn_id="turn-c",
        packet_id=packet_id,
        monotonic_ms=monotonic_ms,
        text_segment="Dies ist die neue gebundene Ausgabe nach dem Abbruch.",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=planned_ms,
        sequence=0,
        cancellable=True,
    )
    cortex.advance_output(packet_id, playback_state="started", monotonic_ms=monotonic_ms + 1, heard_fraction=0.0)


def capture_start(monitor: str, raw_path: Path, *, rate: int, channels: int) -> tuple[subprocess.Popen, object]:
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
    time.sleep(0.3)
    if proc.poll() is not None:
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        fh.close()
        raise RuntimeError(f"MONITOR_CAPTURE_DIED:{proc.returncode}:{err[-1000:]}")
    return proc, fh


def capture_stop(proc: subprocess.Popen, fh: object) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    try:
        fh.close()
    except Exception:
        pass


def play_start(sink: str, source: Path) -> tuple[subprocess.Popen, int]:
    proc = subprocess.Popen(
        ["paplay", f"--device={sink}", str(source)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    started_ns = time.monotonic_ns()
    time.sleep(0.15)
    if proc.poll() is not None:
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise RuntimeError(f"PLAYBACK_DIED_EARLY:{proc.returncode}:{err[-1000:]}")
    return proc, started_ns


def stop_playback(proc: subprocess.Popen) -> int:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    return time.monotonic_ns()


def _load_mono_pcm16(path: Path):
    try:
        import numpy as np
    except Exception as exc:
        raise RuntimeError("NUMPY_REQUIRED_FOR_REPLACEMENT_READBACK") from exc
    with wave.open(str(path), "rb") as wf:
        if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
            raise RuntimeError("REPLACEMENT_READBACK_REQUIRES_MONO_PCM16")
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    return rate, np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0


def _norm_corr(a, b) -> float:
    import numpy as np
    n = min(len(a), len(b))
    if n < 128:
        return 0.0
    x = np.asarray(a[:n], dtype=np.float64)
    y = np.asarray(b[:n], dtype=np.float64)
    x = x - float(x.mean())
    y = y - float(y.mean())
    denom = math.sqrt(float(np.dot(x, x)) * float(np.dot(y, y)))
    return float(np.dot(x, y) / denom) if denom > 1e-15 else 0.0


def positive_replacement_readback(source: Path, capture: Path) -> dict:
    import numpy as np
    source_rate, src = _load_mono_pcm16(source)
    capture_rate, cap = _load_mono_pcm16(capture)
    if source_rate != capture_rate:
        raise RuntimeError("REPLACEMENT_READBACK_RATE_MISMATCH")
    if len(cap) < len(src):
        raise RuntimeError("REPLACEMENT_CAPTURE_SHORTER_THAN_SOURCE")
    probe = min(len(src), max(256, int(source_rate * 0.4)))
    ref = src[:probe] - float(src[:probe].mean())
    centered = cap - float(cap.mean())
    conv_len = len(centered) + len(ref) - 1
    nfft = 1 << (conv_len - 1).bit_length()
    corr = np.fft.irfft(
        np.fft.rfft(centered, n=nfft) * np.fft.rfft(ref[::-1], n=nfft),
        n=nfft,
    )[:conv_len]
    valid = corr[probe - 1 : len(cap)]
    if valid.size == 0:
        raise RuntimeError("REPLACEMENT_ALIGNMENT_EMPTY")
    offset = int(np.argmax(np.abs(valid)))
    if offset + len(src) > len(cap):
        raise RuntimeError("REPLACEMENT_CAPTURE_DOES_NOT_COVER_SOURCE")
    score = _norm_corr(src, cap[offset : offset + len(src)])
    return {
        "source_wav_sha256": sha256_file(source),
        "capture_wav_sha256": sha256_file(capture),
        "alignment_offset_frames": offset,
        "alignment_offset_ms": offset * 1000.0 / source_rate,
        "full_source_correlation": score,
        "threshold": MIN_REPLACEMENT_CORRELATION,
        "pass": score >= MIN_REPLACEMENT_CORRELATION,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--replacement-source", type=Path, required=True)
    ap.add_argument("--tts-receipt", type=Path, required=True)
    ap.add_argument("--preflight-receipt", type=Path, required=True)
    ap.add_argument("--analyzer", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--f2-subject-sha", required=True)
    ap.add_argument("--tts-model-sha256", required=True)
    ap.add_argument("--tts-config-sha256", required=True)
    ap.add_argument("--sink-name", default="f2_voice_g2_sink")
    ap.add_argument("--cancel-after-ms", type=float, default=1200.0)
    ap.add_argument("--max-inflight-ms", type=float, required=True)
    args = ap.parse_args()

    report: dict = {
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
            "producer_tts_generation_cancel": 0,
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
    replacement_capture_wav = args.workdir / "replacement-capture.wav"
    analysis_json = args.workdir / "analysis.json"
    graph_preflight_json = args.workdir / "graph-preflight.json"
    control_cap = cancel_cap = replacement_cap = None
    control_fh = cancel_fh = replacement_fh = None

    try:
        for path in (args.source, args.replacement_source, args.tts_receipt, args.preflight_receipt, args.analyzer):
            if not path.is_file():
                raise RuntimeError(f"BOUND_INPUT_MISSING:{path}")
        source_meta = read_wav_meta(args.source)
        replacement_meta = read_wav_meta(args.replacement_source)
        if source_meta["sample_width"] != 2 or source_meta["channels"] != 1:
            raise RuntimeError(f"SOURCE_MUST_BE_MONO_PCM16:{source_meta}")
        if replacement_meta["sample_width"] != 2 or replacement_meta["channels"] != 1:
            raise RuntimeError(f"REPLACEMENT_MUST_BE_MONO_PCM16:{replacement_meta}")
        if source_meta["rate"] != replacement_meta["rate"]:
            raise RuntimeError("SOURCE_REPLACEMENT_RATE_MISMATCH")
        duration_ms = source_meta["frames"] * 1000.0 / source_meta["rate"]
        replacement_duration_ms = replacement_meta["frames"] * 1000.0 / replacement_meta["rate"]
        if duration_ms < args.cancel_after_ms + args.max_inflight_ms + 500:
            raise RuntimeError("SOURCE_TOO_SHORT_FOR_DECLARED_CANCEL_BOUND")
        tts_receipt, tts_receipt_sha = load_tts_receipt(
            args.tts_receipt, args.source, args.replacement_source
        )
        preflight_receipt, preflight_receipt_sha = load_preflight_receipt(
            args.preflight_receipt, args.max_inflight_ms
        )
        try:
            observed_piper = importlib.metadata.version("piper-tts")
        except importlib.metadata.PackageNotFoundError:
            observed_piper = None
        if observed_piper != tts_receipt.get("piper_tts_version"):
            raise RuntimeError("TTS_RUNTIME_VERSION_MISMATCH")
        wait_pulse()

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
        bound_objects, pw_dump = bind_pipewire_objects(args.sink_name, monitor_name)
        settings = run(["pw-metadata", "-n", "settings"], check=False).stdout
        graph_preflight = {
            "schema": "T4_G2_PIPEWIRE_GRAPH_PREFLIGHT/v1",
            "semantic_key": SEMANTIC_KEY,
            "captured_before_control": True,
            "f2_subject_sha": args.f2_subject_sha,
            "launcher_preflight_receipt_sha256": preflight_receipt_sha,
            "derived_max_inflight_ms": args.max_inflight_ms,
            "bound_objects": bound_objects,
            "pw_dump_sha256": sha256_bytes(pw_dump.encode()),
            "settings_sha256": sha256_bytes(settings.encode()),
        }
        graph_preflight_json.write_text(json.dumps(graph_preflight, indent=2, sort_keys=True) + "\n")
        graph_preflight_sha = sha256_file(graph_preflight_json)

        stage = "CONTROL"
        control_cap, control_fh = capture_start(
            monitor_name, control_raw, rate=source_meta["rate"], channels=1
        )
        control_play, control_play_start_ns = play_start(args.sink_name, args.source)
        control_rc = control_play.wait(timeout=max(10.0, duration_ms / 1000.0 + 5.0))
        control_play_end_ns = time.monotonic_ns()
        if control_rc != 0:
            err = control_play.stderr.read().decode(errors="replace") if control_play.stderr else ""
            raise RuntimeError(f"CONTROL_PLAYBACK_FAILED:{control_rc}:{err[-1000:]}")
        time.sleep(0.5)
        capture_stop(control_cap, control_fh)
        control_cap = control_fh = None
        raw_to_wav(control_raw, control_wav, rate=source_meta["rate"], channels=1)

        stage = "CAUSAL_CANCEL"
        packet_id = "output-old-g2-pipewire"
        cortex, session_id = make_cortex(packet_id, int(round(duration_ms)))
        old_binding = packet_audio_binding(
            packet_id=packet_id,
            output_generation=1,
            source=args.source,
            tts_receipt=tts_receipt,
            tts_receipt_sha256=tts_receipt_sha,
            source_role="old",
            f2_subject_sha=args.f2_subject_sha,
            tts_model_sha256=args.tts_model_sha256,
            tts_config_sha256=args.tts_config_sha256,
        )
        old_binding_sha = canonical_sha256(old_binding)
        cancel_cap, cancel_fh = capture_start(
            monitor_name, cancel_raw, rate=source_meta["rate"], channels=1
        )
        cancel_play, cancel_play_start_ns = play_start(args.sink_name, args.source)
        time.sleep(max(0.0, args.cancel_after_ms / 1000.0 - 0.15))
        cancel_request_ns = time.monotonic_ns()
        cancel_offset_ms = (cancel_request_ns - cancel_play_start_ns) / 1_000_000.0
        packet_cancel_ms = max(21, int(round(cancel_offset_ms)) + 20)
        changed = cortex.cancel_for_barge_in(turn_id="turn-b", monotonic_ms=packet_cancel_ms)
        packet_terminal_ns = time.monotonic_ns()
        if packet_id not in changed:
            raise AssertionError("PACKET_CANCEL_DID_NOT_TOUCH_BOUND_OUTPUT")
        interrupted = next(p for p in cortex.outputs if p.packet_id == packet_id)
        if interrupted.playback_state != "interrupted" or interrupted.commit_eligible:
            raise AssertionError("PACKET_FENCE_FAILED_AFTER_CANCEL")
        playback_terminal_ns = stop_playback(cancel_play)
        post_roll_s = args.max_inflight_ms / 1000.0 + 0.8
        time.sleep(post_roll_s)
        capture_stop(cancel_cap, cancel_fh)
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
            raise RuntimeError(
                f"ANALYZER_DID_NOT_EMIT_RECEIPT:{analyzer_proc.returncode}:"
                f"{analyzer_proc.stdout[-500:]}:{analyzer_proc.stderr[-500:]}"
            )
        if not bool(analysis.get("pass")) or analyzer_proc.returncode != 0:
            cls = str(analysis.get("classification", ""))
            report["analysis"] = analysis
            report["result"] = "COUNTEREXAMPLE_OR_INVALID"
            report["failure_class"] = (
                "EVIDENCE_INVALID" if cls.startswith("EVIDENCE_INVALID") else "PRODUCT_NEGATIVE"
            )
            report["classification"] = cls or "ANALYZER_REJECTED"
            raise StopIteration

        stage = "REPLACEMENT_READBACK"
        replacement_packet_id = "output-replacement-g2-pipewire"
        replacement_monotonic_ms = packet_cancel_ms + max(1, int(round(args.max_inflight_ms))) + 100
        queue_replacement(
            cortex,
            replacement_packet_id,
            int(round(replacement_duration_ms)),
            replacement_monotonic_ms,
        )
        replacement_binding = packet_audio_binding(
            packet_id=replacement_packet_id,
            output_generation=2,
            source=args.replacement_source,
            tts_receipt=tts_receipt,
            tts_receipt_sha256=tts_receipt_sha,
            source_role="replacement",
            f2_subject_sha=args.f2_subject_sha,
            tts_model_sha256=args.tts_model_sha256,
            tts_config_sha256=args.tts_config_sha256,
        )
        replacement_binding_sha = canonical_sha256(replacement_binding)
        if old_binding_sha == replacement_binding_sha:
            raise RuntimeError("PACKET_AUDIO_BINDINGS_NOT_DISTINCT")
        replacement_cap, replacement_fh = capture_start(
            monitor_name, replacement_raw, rate=replacement_meta["rate"], channels=1
        )
        replacement_play, replacement_start_ns = play_start(args.sink_name, args.replacement_source)
        replacement_rc = replacement_play.wait(
            timeout=max(10.0, replacement_duration_ms / 1000.0 + 5.0)
        )
        replacement_end_ns = time.monotonic_ns()
        if replacement_rc != 0:
            err = replacement_play.stderr.read().decode(errors="replace") if replacement_play.stderr else ""
            raise RuntimeError(f"REPLACEMENT_PLAYBACK_FAILED:{replacement_rc}:{err[-1000:]}")
        time.sleep(0.5)
        capture_stop(replacement_cap, replacement_fh)
        replacement_cap = replacement_fh = None
        raw_to_wav(
            replacement_raw,
            replacement_capture_wav,
            rate=replacement_meta["rate"],
            channels=1,
        )
        replacement_readback = positive_replacement_readback(
            args.replacement_source, replacement_capture_wav
        )
        if not replacement_readback["pass"]:
            raise AssertionError("REPLACEMENT_GENERATION_POSITIVE_READBACK_FAILED")
        completed = cortex.advance_output(
            replacement_packet_id,
            playback_state="completed",
            monotonic_ms=replacement_monotonic_ms + int(round(replacement_duration_ms)) + 2,
            heard_fraction=1.0,
        )
        if not completed.commit_eligible:
            raise AssertionError("REPLACEMENT_PACKET_NOT_COMMIT_ELIGIBLE_AFTER_POSITIVE_READBACK")

        stage = "CLEANUP"
        run(["pactl", "unload-module", module_id], check=True)
        module_id = None
        time.sleep(0.25)
        sinks_after = run(["pactl", "list", "short", "sinks"], check=False).stdout
        sources_after = run(["pactl", "list", "short", "sources"], check=False).stdout
        name_cleanup_ok = args.sink_name not in sinks_after and monitor_name not in sources_after
        identity_cleanup = assert_bound_objects_absent(bound_objects)
        cleanup_ok = name_cleanup_ok and bool(identity_cleanup["bound_object_serials_absent"])

        report.update({
            "source": {
                "wav_path": str(args.source),
                "wav_sha256": sha256_file(args.source),
                "wav_meta": source_meta,
                "replacement_wav_path": str(args.replacement_source),
                "replacement_wav_sha256": sha256_file(args.replacement_source),
                "replacement_wav_meta": replacement_meta,
                "tts_model_sha256": args.tts_model_sha256,
                "tts_config_sha256": args.tts_config_sha256,
                "tts_receipt_sha256": tts_receipt_sha,
                "piper_tts_version": observed_piper,
            },
            "preflight": {
                "launcher_receipt": preflight_receipt,
                "launcher_receipt_sha256": preflight_receipt_sha,
                "graph_receipt_sha256": graph_preflight_sha,
                "derived_max_inflight_ms": args.max_inflight_ms,
                "causally_prior_to_control": True,
            },
            "pipewire": {
                "pactl_info": pactl_info,
                "pipewire_version": pipewire_version,
                "wireplumber_version": wireplumber_version,
                "sink_line": sink_line,
                "monitor_line": monitor_line,
                "bound_objects": bound_objects,
                "pw_dump_sha256": sha256_bytes(pw_dump.encode()),
                "settings": settings[-4000:],
            },
            "packet_audio_bindings": {
                "old": old_binding,
                "old_sha256": old_binding_sha,
                "replacement": replacement_binding,
                "replacement_sha256": replacement_binding_sha,
            },
            "control": {
                "playback_started_ns": control_play_start_ns,
                "playback_terminal_ns": control_play_end_ns,
                "capture_wav_sha256": sha256_file(control_wav),
            },
            "cancel": {
                "session_id": session_id,
                "voice_output_packet_id": packet_id,
                "output_generation": 1,
                "playback_started_ns": cancel_play_start_ns,
                "cancel_request_ns": cancel_request_ns,
                "cancel_offset_ms": cancel_offset_ms,
                "packet_terminal_ns": packet_terminal_ns,
                "playback_terminal_ns": playback_terminal_ns,
                "changed_packet_ids": list(changed),
                "packet_state": interrupted.playback_state,
                "commit_eligible": interrupted.commit_eligible,
                "capture_wav_sha256": sha256_file(cancel_wav),
                "max_inflight_ms_predeclared": args.max_inflight_ms,
            },
            "analysis": analysis,
            "replacement": {
                "voice_output_packet_id": replacement_packet_id,
                "output_generation": 2,
                "playback_started_ns": replacement_start_ns,
                "playback_terminal_ns": replacement_end_ns,
                "capture_wav_sha256": sha256_file(replacement_capture_wav),
                "readback": replacement_readback,
                "packet_state": completed.playback_state,
                "commit_eligible": completed.commit_eligible,
            },
            "cleanup": {
                "run_owned_sink_removed_by_name": name_cleanup_ok,
                "bound_object_identity_cleanup": identity_cleanup,
                "sink_present_after": args.sink_name in sinks_after,
                "monitor_present_after": monitor_name in sources_after,
            },
            "external_inference_api_calls": 0,
        })

        packet_fence_ok = interrupted.playback_state == "interrupted" and not interrupted.commit_eligible
        bindings_ok = (
            old_binding["source_wav_sha256"] == sha256_file(args.source)
            and replacement_binding["source_wav_sha256"] == sha256_file(args.replacement_source)
            and old_binding["output_generation"] == 1
            and replacement_binding["output_generation"] == 2
        )
        complete = (
            bool(analysis.get("pass"))
            and packet_fence_ok
            and bindings_ok
            and replacement_readback["pass"]
            and completed.commit_eligible
            and cleanup_ok
            and analyzer_proc.returncode == 0
        )
        report["measured_credit"] = {
            "owner_vps_pipewire_virtual_sink_playback_readback": 1 if complete else 0,
            "bounded_cancellation_to_virtual_audio_monitor_silence": 1 if complete else 0,
            "replacement_generation_positive_virtual_monitor_readback": 1 if complete else 0,
            "packet_audio_tts_causal_binding": 1 if complete else 0,
            "exact_pipewire_object_identity_cleanup": 1 if complete else 0,
            "preflight_derived_inflight_bound": 1 if complete else 0,
        }
        if complete:
            report["result"] = "NO_COUNTEREXAMPLE"
            report["failure_class"] = None
            report["classification"] = (
                "ACCEPT_AT_TERMINAL_G2_S2_OWNER_VPS_PIPEWIRE_TEST_DRIVER_SCOPE_ONLY"
            )
        elif not cleanup_ok:
            report["result"] = "COUNTEREXAMPLE"
            report["failure_class"] = "PRODUCT_NEGATIVE"
            report["classification"] = "RUN_OWNED_PIPEWIRE_NODE_IDENTITY_CLEANUP_FAILED"
        else:
            report["result"] = "COUNTEREXAMPLE"
            report["failure_class"] = "PRODUCT_NEGATIVE"
            report["classification"] = "TERMINAL_G2_COMPOSITE_INVARIANT_FAILED"

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
        evidence_stages = {"PRECHECK", "PIPEWIRE_GRAPH", "PCM_ANALYSIS"}
        report["failure_class"] = (
            "EVIDENCE_INVALID" if stage in evidence_stages else "INFRA_AUTH_TRANSPORT_QUOTA"
        )
        report["classification"] = f"{type(exc).__name__}:{exc}"
    finally:
        if control_cap is not None and control_fh is not None:
            capture_stop(control_cap, control_fh)
        if cancel_cap is not None and cancel_fh is not None:
            capture_stop(cancel_cap, cancel_fh)
        if replacement_cap is not None and replacement_fh is not None:
            capture_stop(replacement_cap, replacement_fh)
        if module_id:
            run(["pactl", "unload-module", module_id], check=False)

    encoded = base64.b64encode(json.dumps(report, sort_keys=True).encode()).decode()
    print("T4_G2_PIPEWIRE_RECEIPT_B64=" + encoded)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "NO_COUNTEREXAMPLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
