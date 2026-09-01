#!/usr/bin/env python3
"""FDX1 candidate falsifier: long-silence reentry on one local ASR stream.

This is a candidate falsifier only. It creates no Voice, ASR, state, endpoint,
or runtime authority and mints no promotion credit by itself.

Why this exists
---------------
The already accepted FDX2/FDX4 controller invokes ``nemo-speech transcribe``
separately for each WAV. That is adequate for final-transcript composition but
cannot falsify FDX1's long-silence state invariant because a fresh recognizer
process is created for every fixture.

NeMo-Speech.cpp 0.1.0 exposes ``nemo-speech serve`` + ``/v1/realtime``. With
endpointing enabled, one WebSocket stream can emit multiple final utterances and
re-arm after silence. This probe therefore keeps ONE realtime ASR session open,
feeds speech A -> long digital silence -> speech B, records partial/final timing,
and binds both finals into the existing VoicePacketCortex session.

The probe intentionally does not infer an opaque internal decoder reset from a
transcript. It records only externally measurable endpoint/final boundaries,
single-stream continuity, transcript error, and F2 causal identity.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

UPSTREAM_REPO = "NVIDIA/NeMo-Speech.cpp"
UPSTREAM_RELEASE_SOURCE_SHA = "4f9676226f667d14608487df744f375db87127f8"
UPSTREAM_API_DOC = "docs/api.md"
UPSTREAM_ASR_CONFIG_DOC = "docs/asr/configuration.md"
NEMO_010_LINUX_X86_64_CPU_SHA256 = "0f74131d631ad2c694cf0ec53490866bb6461147959589a69fb6fc231944065b"
NEMOTRON_35_STREAMING_06B_Q8_SHA256 = "a5c435f294eea8f88ce68dd27b8c3bfea7f777cb2fbba04fcd30eaa555f429ae"
SCHEMA = "T4_FDX1_REALTIME_LONG_SILENCE_CANDIDATE_FALSIFIER/v1"


@dataclass(frozen=True)
class PcmFixture:
    path: str
    sample_rate: int
    frames: int
    pcm16: bytes

    @property
    def duration_ms(self) -> float:
        return (self.frames / self.sample_rate) * 1000.0


def load_pcm16_mono(path: Path) -> PcmFixture:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.getnframes()
        pcm = wf.readframes(frames)
    if channels != 1:
        raise ValueError(f"FDX1_FIXTURE_NOT_MONO:{path}:{channels}")
    if width != 2:
        raise ValueError(f"FDX1_FIXTURE_NOT_PCM16:{path}:sample_width={width}")
    if not 8000 <= rate <= 96000:
        raise ValueError(f"FDX1_FIXTURE_RATE_OUT_OF_RANGE:{path}:{rate}")
    if not pcm or frames <= 0:
        raise ValueError(f"FDX1_FIXTURE_EMPTY:{path}")
    return PcmFixture(str(path), rate, frames, pcm)


def norm_words(text: str) -> list[str]:
    return re.findall(r"[\wäöüÄÖÜß]+", text.casefold(), flags=re.UNICODE)


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = norm_words(reference)
    hyp = norm_words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, rw in enumerate(ref, 1):
        cur = [i]
        for j, hw in enumerate(hyp, 1):
            cur.append(min(
                cur[-1] + 1,
                prev[j] + 1,
                prev[j - 1] + (rw != hw),
            ))
        prev = cur
    return prev[-1] / len(ref)


def extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("transcript", "text", "delta"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for key in ("item", "transcription", "result", "data"):
            if key in value:
                candidate = extract_text(value[key])
                if candidate:
                    return candidate
    return ""


def session_identity(event: dict[str, Any]) -> str | None:
    session = event.get("session")
    if isinstance(session, dict):
        for key in ("id", "session_id"):
            value = session.get(key)
            if isinstance(value, str) and value:
                return value
    for key in ("session_id", "id"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return None


async def recv_json(ws: Any, *, timeout: float) -> tuple[dict[str, Any], int]:
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    received_ns = time.monotonic_ns()
    if isinstance(raw, bytes):
        raise RuntimeError("FDX1_UNEXPECTED_BINARY_SERVER_EVENT")
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        raise RuntimeError("FDX1_SERVER_EVENT_NOT_OBJECT")
    return doc, received_ns


async def wait_event(ws: Any, wanted: str, *, timeout: float, trace: list[dict[str, Any]]) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError(f"FDX1_TIMEOUT_WAITING_FOR:{wanted}")
        doc, ns = await recv_json(ws, timeout=left)
        trace.append({"received_ns": ns, "event": doc})
        typ = str(doc.get("type", ""))
        if typ == "error":
            raise RuntimeError(f"FDX1_SERVER_ERROR:{json.dumps(doc, sort_keys=True)}")
        if typ == wanted:
            return doc


async def send_pcm(ws: Any, pcm: bytes, *, sample_rate: int, chunk_ms: int) -> list[int]:
    bytes_per_frame = 2
    frames_per_chunk = max(1, int(sample_rate * chunk_ms / 1000))
    chunk_bytes = frames_per_chunk * bytes_per_frame
    sent_ns: list[int] = []
    for offset in range(0, len(pcm), chunk_bytes):
        await ws.send(pcm[offset: offset + chunk_bytes])
        sent_ns.append(time.monotonic_ns())
        await asyncio.sleep(0)
    return sent_ns


async def run_stream(
    *,
    url: str,
    first: PcmFixture | None,
    second: PcmFixture,
    silence_ms: int,
    endpointing_ms: int,
    chunk_ms: int,
    language: str,
    timeout_s: float,
) -> dict[str, Any]:
    try:
        from websockets.asyncio.client import connect
    except Exception as exc:  # pragma: no cover - execution surface dependency
        raise RuntimeError("FDX1_WEBSOCKETS_PACKAGE_MISSING") from exc

    if first is not None and first.sample_rate != second.sample_rate:
        raise ValueError("FDX1_FIXTURE_SAMPLE_RATE_MISMATCH")
    rate = second.sample_rate
    silence_frames = math.ceil(rate * silence_ms / 1000)
    silence_pcm = b"\x00\x00" * silence_frames
    trailing_ms = max(endpointing_ms + 500, 1200)
    trailing_frames = math.ceil(rate * trailing_ms / 1000)
    trailing_pcm = b"\x00\x00" * trailing_frames

    trace: list[dict[str, Any]] = []
    send_marks: dict[str, Any] = {}
    async with connect(url, max_size=16 * 1024 * 1024, open_timeout=timeout_s) as ws:
        created = await wait_event(ws, "session.created", timeout=timeout_s, trace=trace)
        created_id = session_identity(created)
        update = {
            "type": "session.update",
            "session": {
                "sample_rate": rate,
                "language": language,
                "automatic_punctuation": True,
                "word_timestamps": True,
                "endpointing_ms": endpointing_ms,
            },
        }
        await ws.send(json.dumps(update, separators=(",", ":")))
        updated = await wait_event(ws, "session.updated", timeout=timeout_s, trace=trace)
        updated_id = session_identity(updated)

        if first is not None:
            send_marks["first_started_ns"] = time.monotonic_ns()
            first_marks = await send_pcm(ws, first.pcm16, sample_rate=rate, chunk_ms=chunk_ms)
            send_marks["first_last_chunk_ns"] = first_marks[-1]
            send_marks["long_silence_started_ns"] = time.monotonic_ns()
            silence_marks = await send_pcm(ws, silence_pcm, sample_rate=rate, chunk_ms=chunk_ms)
            send_marks["long_silence_last_chunk_ns"] = silence_marks[-1]

        send_marks["second_started_ns"] = time.monotonic_ns()
        second_marks = await send_pcm(ws, second.pcm16, sample_rate=rate, chunk_ms=chunk_ms)
        send_marks["second_last_chunk_ns"] = second_marks[-1]
        trailing_marks = await send_pcm(ws, trailing_pcm, sample_rate=rate, chunk_ms=chunk_ms)
        send_marks["trailing_silence_last_chunk_ns"] = trailing_marks[-1]
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}, separators=(",", ":")))
        send_marks["commit_sent_ns"] = time.monotonic_ns()

        completed: list[dict[str, Any]] = []
        deltas: list[dict[str, Any]] = []
        committed = False
        deadline = time.monotonic() + timeout_s
        needed = 2 if first is not None else 1
        while time.monotonic() < deadline and (len(completed) < needed or not committed):
            left = max(0.01, deadline - time.monotonic())
            doc, ns = await recv_json(ws, timeout=left)
            trace.append({"received_ns": ns, "event": doc})
            typ = str(doc.get("type", ""))
            if typ == "error":
                raise RuntimeError(f"FDX1_SERVER_ERROR:{json.dumps(doc, sort_keys=True)}")
            if typ == "conversation.item.input_audio_transcription.delta":
                deltas.append({"received_ns": ns, "text": extract_text(doc), "event": doc})
            elif typ == "conversation.item.input_audio_transcription.completed":
                completed.append({"received_ns": ns, "text": extract_text(doc), "event": doc})
            elif typ == "input_audio_buffer.committed":
                committed = True

        return {
            "session_created_id": created_id,
            "session_updated_id": updated_id,
            "single_websocket_connection": True,
            "completed": completed,
            "deltas": deltas,
            "committed": committed,
            "send_marks": send_marks,
            "trace": trace,
            "sample_rate": rate,
            "silence_ms": silence_ms if first is not None else None,
            "endpointing_ms": endpointing_ms,
            "trailing_silence_ms": trailing_ms,
        }


def bind_packet_cortex(
    *,
    f2_root: Path,
    first_text: str,
    second_text: str,
) -> dict[str, Any]:
    sys.path.insert(0, str(f2_root / "src"))
    from frankenstein2.causal_identity import CausalIdentity
    from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
    from frankenstein2.voice_packet_cortex import VoiceInputPacket, VoicePacketCortex

    root = CausalIdentity(
        session_id="session-fdx1-realtime-long-silence",
        agent_id="frankenstein-2",
        task_id="task-fdx1-realtime-long-silence",
        turn_id="turn-root",
        causal_id="causal-fdx1-root",
        generation=1,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref="trigger4:fdx1:single-realtime-stream",
        input_sha256="1" * 64,
        provenance_refs=("trigger4:fdx1:candidate-falsifier",),
    )
    session = VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id="causal-fdx1-session",
            generation=2,
            turn_id="turn-session",
        ),
        provenance_refs=("trigger4:fdx1:candidate-falsifier",),
    )
    cortex = VoicePacketCortex(session, opened_monotonic_ms=0)

    packets = []
    for sequence, (turn_id, text, ms) in enumerate((
        ("turn-fdx1-before-silence", first_text, 100),
        ("turn-fdx1-after-silence", second_text, 200),
    )):
        packet = VoiceInputPacket(
            session_id=session.voice_session_id,
            turn_id=turn_id,
            packet_id=f"fdx1-input-{sequence}",
            monotonic_ms=ms,
            source_modality="asr_final",
            text=text,
            language="de-DE",
            is_final=True,
            confidence=0.0,
            speech_start=True,
            speech_end=True,
            vad_state="SILENCE",
            endpoint_decision="END",
            overlap_state="NONE",
            barge_in=False,
            source_duration_ms=max(1, ms),
            sequence=0,
        )
        event = cortex.accept_input(packet)
        packets.append({
            "turn_id": packet.turn_id,
            "packet_id": packet.packet_id,
            "event_kind": event.event_kind,
            "session_id": packet.session_id,
            "endpoint_decision": packet.endpoint_decision,
        })

    return {
        "voice_session_id": session.voice_session_id,
        "cortex_session_id": cortex.session_id,
        "same_session_identity": cortex.session_id == session.voice_session_id,
        "distinct_turn_ids": packets[0]["turn_id"] != packets[1]["turn_id"],
        "packets": packets,
        "restart_reentry_event_count": sum(1 for event in cortex.events if event.event_kind == "RESTART_REENTRY"),
    }


async def async_main(args: argparse.Namespace) -> dict[str, Any]:
    before = load_pcm16_mono(args.before_wav.resolve())
    after = load_pcm16_mono(args.after_wav.resolve())
    if before.sample_rate != after.sample_rate:
        raise ValueError("FDX1_FIXTURE_SAMPLE_RATE_MISMATCH")

    baseline = await run_stream(
        url=args.server_url,
        first=None,
        second=after,
        silence_ms=args.silence_ms,
        endpointing_ms=args.endpointing_ms,
        chunk_ms=args.chunk_ms,
        language=args.language,
        timeout_s=args.timeout_s,
    )
    reentry = await run_stream(
        url=args.server_url,
        first=before,
        second=after,
        silence_ms=args.silence_ms,
        endpointing_ms=args.endpointing_ms,
        chunk_ms=args.chunk_ms,
        language=args.language,
        timeout_s=args.timeout_s,
    )

    baseline_finals = [row["text"] for row in baseline["completed"] if row["text"]]
    reentry_finals = [row["text"] for row in reentry["completed"] if row["text"]]
    baseline_after = baseline_finals[-1] if baseline_finals else ""
    reentry_before = reentry_finals[0] if len(reentry_finals) >= 1 else ""
    reentry_after = reentry_finals[1] if len(reentry_finals) >= 2 else ""

    packet_binding = None
    if len(reentry_finals) >= 2:
        packet_binding = bind_packet_cortex(
            f2_root=args.f2_root.resolve(),
            first_text=reentry_before,
            second_text=reentry_after,
        )

    metrics = {
        "baseline_after_wer": word_error_rate(args.expected_after, baseline_after),
        "reentry_before_wer": word_error_rate(args.expected_before, reentry_before),
        "reentry_after_wer": word_error_rate(args.expected_after, reentry_after),
    }
    metrics["after_onset_wer_delta_vs_fresh_stream"] = (
        metrics["reentry_after_wer"] - metrics["baseline_after_wer"]
    )
    metrics["reentry_after_similarity_target_is_better_than_stale_prior"] = (
        word_error_rate(args.expected_after, reentry_after)
        <= word_error_rate(args.expected_before, reentry_after)
    )

    evidence_gaps = []
    product_counterexample_candidates = []
    if not baseline["committed"] or not reentry["committed"]:
        evidence_gaps.append("INPUT_AUDIO_BUFFER_COMMIT_ACK_NOT_OBSERVED")
    if len(reentry["completed"]) < 2:
        product_counterexample_candidates.append("SECOND_FINAL_NOT_OBSERVED_ON_SINGLE_STREAM_AFTER_LONG_SILENCE")
    if not reentry["deltas"]:
        evidence_gaps.append("PARTIAL_DELTA_NOT_OBSERVED")
    if reentry["session_created_id"] and reentry["session_updated_id"] and (
        reentry["session_created_id"] != reentry["session_updated_id"]
    ):
        product_counterexample_candidates.append("SERVER_SESSION_ID_CHANGED_DURING_INITIAL_UPDATE")
    if len(reentry_finals) >= 2 and not metrics["reentry_after_similarity_target_is_better_than_stale_prior"]:
        product_counterexample_candidates.append("SECOND_FINAL_IS_CLOSER_TO_STALE_PRIOR_UTTERANCE_THAN_CURRENT_UTTERANCE")
    if packet_binding is not None:
        if not packet_binding["same_session_identity"]:
            product_counterexample_candidates.append("F2_PACKET_CORTEX_SESSION_ID_CHANGED")
        if not packet_binding["distinct_turn_ids"]:
            product_counterexample_candidates.append("F2_REENTRY_REUSED_PRIOR_TURN_ID")
        if packet_binding["restart_reentry_event_count"] != 0:
            product_counterexample_candidates.append("LONG_SILENCE_INVENTED_RESTART_REENTRY_EVENT")

    if product_counterexample_candidates:
        result = "COUNTEREXAMPLE_CANDIDATE"
    elif evidence_gaps:
        result = "MEASUREMENT_INCOMPLETE"
    else:
        result = "MEASURED_NO_COUNTEREXAMPLE_AT_BOUNDED_FDX1_SCOPE"

    return {
        "schema": SCHEMA,
        "result": result,
        "case": "FDX1_LONG_SILENCE_REENTRY_ONSET",
        "work_class": "CANDIDATE_FALSIFIER",
        "source": {
            "f2_subject_sha": args.f2_subject_sha,
            "f2_root": str(args.f2_root.resolve()),
            "upstream_runtime_repo": UPSTREAM_REPO,
            "upstream_release_source_sha": UPSTREAM_RELEASE_SOURCE_SHA,
            "upstream_api_doc": UPSTREAM_API_DOC,
            "upstream_asr_config_doc": UPSTREAM_ASR_CONFIG_DOC,
            "expected_nemo_0_1_0_linux_x86_64_cpu_sha256": NEMO_010_LINUX_X86_64_CPU_SHA256,
            "expected_nemotron_3_5_streaming_0_6b_q8_sha256": NEMOTRON_35_STREAMING_06B_Q8_SHA256,
            "runtime_sha256_observed": args.nemo_runtime_sha256,
            "model_sha256_observed": args.nemo_model_sha256,
            "server_url": args.server_url,
        },
        "fixture": {
            "before": {"path": before.path, "duration_ms": before.duration_ms, "sample_rate": before.sample_rate},
            "after": {"path": after.path, "duration_ms": after.duration_ms, "sample_rate": after.sample_rate},
            "expected_before": args.expected_before,
            "expected_after": args.expected_after,
            "long_silence_ms": args.silence_ms,
            "endpointing_ms": args.endpointing_ms,
            "chunk_ms": args.chunk_ms,
        },
        "baseline_fresh_stream": {
            "finals": baseline_finals,
            "partial_count": len(baseline["deltas"]),
            "session_created_id": baseline["session_created_id"],
            "session_updated_id": baseline["session_updated_id"],
        },
        "reentry_single_stream": {
            "finals": reentry_finals,
            "partial_count": len(reentry["deltas"]),
            "session_created_id": reentry["session_created_id"],
            "session_updated_id": reentry["session_updated_id"],
            "single_websocket_connection": reentry["single_websocket_connection"],
            "send_marks": reentry["send_marks"],
            "completed_events": reentry["completed"],
            "partial_events": reentry["deltas"],
        },
        "packet_cortex_binding": packet_binding,
        "metrics": metrics,
        "evidence_gaps": evidence_gaps,
        "counterexample_candidates": product_counterexample_candidates,
        "epistemic_scope": {
            "explicit_endpoint_final_boundaries_measured": len(reentry["completed"]) >= 2,
            "single_transport_stream_continuity_measured": True,
            "opaque_internal_decoder_reset_state_claimed": False,
            "note": (
                "A server final/EOU boundary is an observable reset/re-arm boundary. This probe does not claim "
                "visibility into any additional opaque decoder-state mutation not surfaced by the runtime."
            ),
        },
        "explicit_zero_credit": {
            "physical_microphone": 0,
            "physical_speaker": 0,
            "human_heard_output": 0,
            "physical_presence": 0,
            "gwt_jspace": 0,
            "effect": 0,
            "training": 0,
            "whole_voice_e2e": 0,
            "whole_product": 0,
        },
        "classification": "CANDIDATE_FALSIFIER_ONLY_NO_PRODUCT_REPAIR_PERFORMED",
        "next_action": (
            "Execute this exact probe only on an admitted owner-VPS S1/S2 runtime with the bound NeMo 0.1.0 and "
            "Nemotron 3.5 artifacts. Classify runtime/transport/setup failures separately from executable product "
            "counterevidence. Promote only the measured bounded FDX1 scope."
        ),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--server-url", default="ws://127.0.0.1:8080/v1/realtime")
    p.add_argument("--f2-root", type=Path, required=True)
    p.add_argument("--f2-subject-sha", required=True)
    p.add_argument("--before-wav", type=Path, required=True)
    p.add_argument("--after-wav", type=Path, required=True)
    p.add_argument("--expected-before", required=True)
    p.add_argument("--expected-after", required=True)
    p.add_argument("--language", default="de-DE")
    p.add_argument("--silence-ms", type=int, default=5000)
    p.add_argument("--endpointing-ms", type=int, default=800)
    p.add_argument("--chunk-ms", type=int, default=80)
    p.add_argument("--timeout-s", type=float, default=120.0)
    p.add_argument("--nemo-runtime-sha256", default="UNBOUND")
    p.add_argument("--nemo-model-sha256", default="UNBOUND")
    args = p.parse_args()
    if args.silence_ms <= args.endpointing_ms:
        p.error("--silence-ms must exceed --endpointing-ms")
    if args.chunk_ms <= 0:
        p.error("--chunk-ms must be positive")
    return args


def main() -> int:
    args = parse_args()
    receipt = asyncio.run(async_main(args))
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    if receipt["result"] == "COUNTEREXAMPLE_CANDIDATE":
        return 2
    if receipt["result"] == "MEASUREMENT_INCOMPLETE":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
