#!/usr/bin/env python3
"""WP715 PN14/PN15/EVENTSEQ exact-source falsifier.

Packet/controller component evidence only. No model, ASR, TTS, acoustic, physical,
effect, target-runtime, whole-voice, or whole-product credit is created here.
"""
from __future__ import annotations

import json
import os

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoiceInputPacket, VoicePacketCortex, VoicePacketCortexError
from frankenstein2.voice_packet_cortex_recovery import export_packet_cortex_checkpoint, resume_packet_cortex

SCHEMA = "F2_PACKET_CORTEX_ATOMICITY_FALSIFIER/v1"


def make_cortex(suffix: str) -> VoicePacketCortex:
    root = CausalIdentity(
        session_id=f"session-wp715-{suffix}",
        agent_id="frankenstein-2",
        task_id=f"wp715-{suffix}",
        turn_id="turn-root",
        causal_id=f"causal-root-wp715-{suffix}",
        generation=1,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref=f"wp715:{suffix}",
        input_sha256="b" * 64,
        provenance_refs=(f"trigger4:wp715:{suffix}",),
    )
    session = VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id=f"causal-session-wp715-{suffix}", generation=2, turn_id="turn-session"
        ),
        provenance_refs=(f"trigger4:wp715:{suffix}:session",),
    )
    return VoicePacketCortex(session)


def barge_packet(cortex: VoicePacketCortex, *, packet_id: str, at: int) -> VoiceInputPacket:
    return VoiceInputPacket(
        session_id=cortex.session_id,
        turn_id="turn-new",
        packet_id=packet_id,
        monotonic_ms=at,
        source_modality="asr_partial",
        text="Stopp",
        language="de-DE",
        is_final=False,
        confidence=0.99,
        speech_start=True,
        speech_end=False,
        vad_state="SPEECH",
        endpoint_decision="HOLD",
        overlap_state="USER_OVER_OUTPUT",
        barge_in=True,
        source_duration_ms=10,
        sequence=0,
        fault_flags=(),
    )


def pn14_tool_only_barge_ownership() -> tuple[bool, str]:
    cortex = make_cortex("pn14")
    cortex.emit_intent(turn_id="turn-old", monotonic_ms=100, voice_intent="TOOL_USE", tool_ref="tool:slow")
    cortex.accept_input(barge_packet(cortex, packet_id="barge-pn14", at=200))
    try:
        cortex.emit_system_event(
            turn_id="turn-old", monotonic_ms=210, event_kind="TOOL_RESULT", tool_ref="tool:slow"
        )
    except VoicePacketCortexError:
        return True, "stale tool-only ownership rejected after barge-in"
    return False, "stale tool-only ownership survived barge-in"


def pn15_rejected_near_cap_barge_atomicity() -> tuple[bool, str]:
    cortex = make_cortex("pn15")
    cortex.queue_output(
        turn_id="turn-old",
        packet_id="output-old",
        monotonic_ms=100,
        text_segment="Antwort",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=100,
        sequence=0,
    )
    cortex.advance_output("output-old", playback_state="started", monotonic_ms=110, heard_fraction=0.0)
    cortex.emit_intent(turn_id="turn-old", monotonic_ms=120, voice_intent="TOOL_USE", tool_ref="tool:old")
    while len(cortex.events) < VoicePacketCortex.MAX_EVENTS - 1:
        cortex.emit_intent(turn_id="turn-fill", monotonic_ms=1000 + len(cortex.events), voice_intent="WAIT")
    before = (
        dict(cortex._input_seen),
        dict(cortex._last_input_sequence),
        dict(cortex._last_input_monotonic_ms),
        set(cortex._final_turns),
        dict(cortex._outputs),
        dict(cortex._active_tools),
        set(cortex._cancelled_tools),
        cortex._event_seq,
        tuple(cortex.events),
    )
    rejected = False
    try:
        cortex.accept_input(barge_packet(cortex, packet_id="barge-pn15", at=10000))
    except VoicePacketCortexError:
        rejected = True
    after = (
        dict(cortex._input_seen),
        dict(cortex._last_input_sequence),
        dict(cortex._last_input_monotonic_ms),
        set(cortex._final_turns),
        dict(cortex._outputs),
        dict(cortex._active_tools),
        set(cortex._cancelled_tools),
        cortex._event_seq,
        tuple(cortex.events),
    )
    unchanged = after == before
    return rejected and unchanged, f"near-cap barge rejected={rejected}; state_unchanged={unchanged}"


def eventseq_reject_atomicity() -> tuple[bool, str]:
    cortex = make_cortex("eventseq")
    checkpoint_before = export_packet_cortex_checkpoint(cortex)
    seq_before = cortex._event_seq
    events_before = cortex.events
    rejected = False
    try:
        cortex.emit_system_event(
            turn_id="turn-eventseq", monotonic_ms=100, event_kind="ERROR", detail=1  # type: ignore[arg-type]
        )
    except VoicePacketCortexError:
        rejected = True
    seq_unchanged = cortex._event_seq == seq_before
    events_unchanged = cortex.events == events_before
    checkpoint_after = export_packet_cortex_checkpoint(cortex)
    digest_unchanged = checkpoint_after["payload_sha256"] == checkpoint_before["payload_sha256"]
    restartable = True
    try:
        resume_packet_cortex(cortex.session, checkpoint_after, monotonic_ms=200)
    except VoicePacketCortexError:
        restartable = False
    ok = rejected and seq_unchanged and events_unchanged and digest_unchanged and restartable
    return ok, (
        f"rejected={rejected}; seq_unchanged={seq_unchanged}; events_unchanged={events_unchanged}; "
        f"digest_unchanged={digest_unchanged}; restartable={restartable}"
    )


def main() -> int:
    probes = (
        ("PN14_TOOL_ONLY_BARGE_OWNERSHIP", pn14_tool_only_barge_ownership),
        ("PN15_REJECTED_NEAR_CAP_BARGE_ATOMICITY", pn15_rejected_near_cap_barge_atomicity),
        ("EVENTSEQ_REJECT_ATOMICITY", eventseq_reject_atomicity),
    )
    results = []
    for probe_id, fn in probes:
        try:
            passed, detail = fn()
        except Exception as exc:
            passed = False
            detail = f"{type(exc).__name__}: {exc}"
        results.append({"probe_id": probe_id, "passed": passed, "detail": detail})
    failed = [item for item in results if not item["passed"]]
    report = {
        "schema": SCHEMA,
        "source_sha": os.environ.get("GITHUB_SHA", "LOCAL_UNBOUND"),
        "result": "PASS" if not failed else "PRODUCT_NEGATIVE",
        "probes": results,
        "failed_probe_ids": [item["probe_id"] for item in failed],
        "outbound_model_asr_tts_calls": 0,
        "acoustic_credit": 0,
        "target_runtime_credit": 0,
        "physical_device_credit": 0,
        "gwt_jspace_credit": 0,
        "effect_credit": 0,
        "training_credit": 0,
        "whole_voice_e2e_credit": 0,
        "whole_product_credit": 0,
    }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
