#!/usr/bin/env python3
"""Trigger-4 G2 PipeWire virtual-sink playback/cancel/monitor runtime discriminator.

Runtime/falsifier scope only. This script must run inside the admitted disposable
S2 owner-VPS sandbox with a sandbox-local PipeWire/PipeWire-Pulse session.
It reuses VoicePacketCortex cancellation authority and does not create a second
turn/state/effect/playback authority.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoicePacketCortex

SCHEMA = "T4_G2_PIPEWIRE_S2_PLAYBACK_CANCEL_MONITOR/v1"
SEMANTIC_KEY = "0d83f7d13c1d8f91686cf94070f73d901a49018b40a9c058d1949af094655bff"


def run(cmd: list[str], *, check: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--analyzer", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--f2-subject-sha", required=True)
    ap.add_argument("--tts-model-sha256", required=True)
    ap.add_argument("--tts-config-sha256", required=True)
    ap.add_argument("--sink-name", default="f2_voice_g2_sink")
    ap.add_argument("--cancel-after-ms", type=float, default=1200.0)
    ap.add_argument("--max-inflight-ms", type=float, default=250.0)
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

    try:
        if not args.source.is_file() or not args.analyzer.is_file():
            raise RuntimeError("BOUND_INPUT_MISSING")
        source_meta = read_wav_meta(args.source)
        if source_meta["sample_width"] != 2 or source_meta["channels"] != 1:
            raise RuntimeError(f"SOURCE_MUST_BE_MONO_PCM16:{source_meta}")
        duration_ms = source_meta["frames"] * 1000.0 / source_meta["rate"]
        if duration_ms < args.cancel_after_ms + args.max_inflight_ms + 500:
            raise RuntimeError("SOURCE_TOO_SHORT_FOR_DECLARED_CANCEL_BOUND")
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
        pw_dump = run(["pw-dump"], check=False).stdout
        settings = run(["pw-metadata", "-n", "settings"], check=False).stdout

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

        stage = "CLEANUP"
        run(["pactl", "unload-module", module_id], check=True)
        module_id = None
        time.sleep(0.2)
        sinks_after = run(["pactl", "list", "short", "sinks"], check=False).stdout
        sources_after = run(["pactl", "list", "short", "sources"], check=False).stdout
        cleanup_ok = args.sink_name not in sinks_after and monitor_name not in sources_after

        report.update({
            "source": {
                "wav_path": str(args.source),
                "wav_sha256": sha256_file(args.source),
                "wav_meta": source_meta,
                "tts_model_sha256": args.tts_model_sha256,
                "tts_config_sha256": args.tts_config_sha256,
            },
            "pipewire": {
                "pactl_info": pactl_info,
                "pipewire_version": pipewire_version,
                "wireplumber_version": wireplumber_version,
                "sink_line": sink_line,
                "monitor_line": monitor_line,
                "pw_dump_sha256": hashlib.sha256(pw_dump.encode()).hexdigest(),
                "settings": settings[-4000:],
            },
            "control": {
                "playback_started_ns": control_play_start_ns,
                "playback_terminal_ns": control_play_end_ns,
                "capture_wav_sha256": sha256_file(control_wav),
            },
            "cancel": {
                "session_id": session_id,
                "voice_output_packet_id": packet_id,
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
            "cleanup": {
                "run_owned_sink_removed": cleanup_ok,
                "sink_present_after": args.sink_name in sinks_after,
                "monitor_present_after": monitor_name in sources_after,
            },
            "external_inference_api_calls": 0,
        })

        packet_fence_ok = interrupted.playback_state == "interrupted" and not interrupted.commit_eligible
        audio_pass = bool(analysis.get("pass"))
        complete = audio_pass and packet_fence_ok and cleanup_ok and analyzer_proc.returncode == 0
        report["measured_credit"] = {
            "owner_vps_pipewire_virtual_sink_playback_readback": 1 if complete else 0,
            "bounded_cancellation_to_virtual_audio_monitor_silence": 1 if complete else 0,
        }
        if complete:
            report["result"] = "NO_COUNTEREXAMPLE"
            report["failure_class"] = None
            report["classification"] = "ACCEPT_AT_BOUNDED_S2_OWNER_VPS_PIPEWIRE_VIRTUAL_MONITOR_SCOPE_ONLY"
        elif not audio_pass:
            cls = str(analysis.get("classification", ""))
            report["result"] = "COUNTEREXAMPLE_OR_INVALID"
            report["failure_class"] = (
                "EVIDENCE_INVALID" if cls.startswith("EVIDENCE_INVALID") else "PRODUCT_NEGATIVE"
            )
            report["classification"] = cls or "ANALYZER_REJECTED"
        elif not cleanup_ok:
            report["result"] = "COUNTEREXAMPLE"
            report["failure_class"] = "PRODUCT_NEGATIVE"
            report["classification"] = "RUN_OWNED_PIPEWIRE_NODE_CLEANUP_FAILED"
        else:
            report["result"] = "COUNTEREXAMPLE"
            report["failure_class"] = "PRODUCT_NEGATIVE"
            report["classification"] = "PACKET_FENCE_OR_ANALYZER_EXIT_FAILED"

    except AssertionError as exc:
        report["stage"] = stage
        report["result"] = "COUNTEREXAMPLE"
        report["failure_class"] = "PRODUCT_NEGATIVE"
        report["classification"] = str(exc)
    except Exception as exc:
        report["stage"] = stage
        report["result"] = "BLOCKED"
        report["failure_class"] = (
            "EVIDENCE_INVALID" if stage == "PCM_ANALYSIS" else "INFRA_AUTH_TRANSPORT_QUOTA"
        )
        report["classification"] = f"{type(exc).__name__}:{exc}"
    finally:
        if control_cap is not None and control_fh is not None:
            capture_stop(control_cap, control_fh)
        if cancel_cap is not None and cancel_fh is not None:
            capture_stop(cancel_cap, cancel_fh)
        if module_id:
            run(["pactl", "unload-module", module_id], check=False)

    encoded = base64.b64encode(json.dumps(report, sort_keys=True).encode()).decode()
    print("T4_G2_PIPEWIRE_RECEIPT_B64=" + encoded)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "NO_COUNTEREXAMPLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
