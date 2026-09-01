#!/usr/bin/env python3
"""Trigger-7 composed packet-only Voice-Slice causal discriminator.

Research/falsifier scope only.  It composes existing product surfaces without
mutating product code and deliberately substitutes text/information packets for
physical ASR/TTS audio.  Passing this script creates repository-executable
research evidence only; it creates no acoustic, target-runtime, UnifiedDB,
GWT/effect, whole-voice or whole-product acceptance credit.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import (
    bind_completed_reentry,
    build_heard_result,
    build_interrupted_heard_prefix,
)
from frankenstein2.voice_packet_cortex import (
    PacketTurnPolicy,
    VoiceInputPacket,
    VoicePacketCortex,
    VoicePacketCortexError,
)
from frankenstein2.voice_packet_cortex_recovery import (
    export_packet_cortex_checkpoint,
    packet_latency_report,
    resume_packet_cortex,
)

SCHEMA = "F2_T7_COMPOSED_PACKET_VOICE_SLICE_DIAGNOSTIC/v1"
SEMANTIC_KEY = "29bf28d8f3b3cec294de2126c002b90fedbacdec961e823503c2c4d8f11ddbdc"
RESEARCH_ID = "T7-20260902-COMPOSED-VOICE-SLICE-G4"


def _make_session() -> VoiceSessionCapsule:
    root = CausalIdentity(
        session_id="session-t7-composed-voice-slice-g4",
        agent_id="frankenstein-2",
        task_id="task-t7-composed-voice-slice-g4",
        turn_id="turn-root",
        causal_id="causal-t7-composed-root-g4",
        generation=1,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref="trigger7:composed-voice-slice-g4",
        input_sha256="7" * 64,
        provenance_refs=("trigger7:composed-voice-slice-g4",),
    )
    return VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id="causal-t7-composed-session-g4",
            generation=2,
            turn_id="turn-session",
        ),
        provenance_refs=("trigger7:composed-voice-slice-session-g4",),
    )


def _input(
    session: VoiceSessionCapsule,
    *,
    turn_id: str,
    packet_id: str,
    monotonic_ms: int,
    text: str,
    sequence: int,
    final: bool,
    speech_start: bool,
    speech_end: bool,
    endpoint: str,
    barge_in: bool = False,
    overlap: str = "NONE",
) -> VoiceInputPacket:
    return VoiceInputPacket(
        session_id=session.voice_session_id,
        turn_id=turn_id,
        packet_id=packet_id,
        monotonic_ms=monotonic_ms,
        source_modality="asr_final" if final else "asr_partial",
        text=text,
        language="de",
        is_final=final,
        confidence=0.97 if final else 0.90,
        speech_start=speech_start,
        speech_end=speech_end,
        vad_state="SILENCE" if speech_end else "SPEECH",
        endpoint_decision=endpoint,
        overlap_state=overlap,
        barge_in=barge_in,
        source_duration_ms=max(1, monotonic_ms),
        sequence=sequence,
    )


def _persist_roundtrip(checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Exercise an actual serialized filesystem roundtrip, not object aliasing."""
    with tempfile.TemporaryDirectory(prefix="f2-t7-voice-slice-") as tmp:
        path = Path(tmp) / "voice_packet_cortex_checkpoint.json"
        path.write_text(
            json.dumps(checkpoint, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
        return json.loads(path.read_text(encoding="utf-8"))


def run_discriminator() -> dict[str, Any]:
    session = _make_session()
    cortex = VoicePacketCortex(session, presence_state="PRESENT_INTERRUPTIBLE", opened_monotonic_ms=0)

    # ASR surrogate -> Packet Cortex -> explicit HOLD turn policy.
    hold = _input(
        session,
        turn_id="turn-a",
        packet_id="input-a-0",
        monotonic_ms=10,
        text="Also ich wollte noch",
        sequence=0,
        final=False,
        speech_start=True,
        speech_end=False,
        endpoint="HOLD",
    )
    cortex.accept_input(hold)
    policy = PacketTurnPolicy(
        policy_id="t7-g4-hold-policy",
        hold_intent="WAIT",
        provenance_refs=("trigger7:g4:presence-turn-policy",),
    )
    policy_event = cortex.apply_turn_policy(hold, policy)
    if policy_event.voice_intent != "WAIT" or policy_event.presence_state != "PRESENT_INTERRUPTIBLE":
        raise AssertionError("HOLD policy/presence binding changed")

    final_a = _input(
        session,
        turn_id="turn-a",
        packet_id="input-a-1",
        monotonic_ms=30,
        text="Also ich wollte noch eine erste Antwort.",
        sequence=1,
        final=True,
        speech_start=False,
        speech_end=True,
        endpoint="END",
    )
    cortex.accept_input(final_a)
    cortex.emit_intent(turn_id="turn-a", monotonic_ms=40, voice_intent="ANSWER")

    # Output/TTS surrogate begins, is partially heard, and owns a tool before barge-in.
    cortex.queue_output(
        turn_id="turn-a",
        packet_id="output-a-0",
        monotonic_ms=50,
        text_segment="Ich beantworte die erste Frage jetzt vollständig.",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=500,
        sequence=0,
    )
    cortex.advance_output("output-a-0", playback_state="started", monotonic_ms=60, heard_fraction=0.0)
    cortex.advance_output("output-a-0", playback_state="heard", monotonic_ms=100, heard_fraction=0.25)
    cortex.emit_intent(
        turn_id="turn-a",
        monotonic_ms=110,
        voice_intent="TOOL_USE",
        tool_ref="tool:t7-g4-stale-after-barge",
        detail="ownership must be revoked by barge-in",
    )

    # New user speech overlaps output: mandatory barge-in cancellation is exercised.
    barge = _input(
        session,
        turn_id="turn-b",
        packet_id="input-b-0",
        monotonic_ms=120,
        text="Stopp",
        sequence=0,
        final=False,
        speech_start=True,
        speech_end=False,
        endpoint="HOLD",
        barge_in=True,
        overlap="USER_OVER_OUTPUT",
    )
    cortex.accept_input(barge)
    interrupted = next(packet for packet in cortex.outputs if packet.packet_id == "output-a-0")
    if interrupted.playback_state != "interrupted" or interrupted.commit_eligible:
        raise AssertionError("barge-in failed to terminalize partial output without commit authority")
    if float(interrupted.heard_fraction) != 0.25 or interrupted.voiceoutcome_ref is not None:
        raise AssertionError("barge-in changed measured heard fraction or minted outcome authority")
    prefix = build_interrupted_heard_prefix(
        packet=interrupted,
        heard_prefix_text="Ich beantworte",
        measurement_ref="trigger7:g4:packet-heard-fraction-0.25",
        provenance_refs=("trigger7:g4:barge-prefix",),
    )

    late_tool_rejected_pre_restart = False
    try:
        cortex.emit_system_event(
            turn_id="turn-a",
            monotonic_ms=125,
            event_kind="TOOL_RESULT",
            tool_ref="tool:t7-g4-stale-after-barge",
            detail="must be rejected after barge-in",
        )
    except VoicePacketCortexError:
        late_tool_rejected_pre_restart = True
    if not late_tool_rejected_pre_restart:
        raise AssertionError("barge-in left stale tool result authority live")

    final_b = _input(
        session,
        turn_id="turn-b",
        packet_id="input-b-1",
        monotonic_ms=150,
        text="Stopp, beantworte stattdessen die neue Frage.",
        sequence=1,
        final=True,
        speech_start=False,
        speech_end=True,
        endpoint="END",
    )
    cortex.accept_input(final_b)

    # Persistent-state surrogate boundary: canonical checkpoint -> bytes on disk -> fresh parse -> resume.
    before_restart = export_packet_cortex_checkpoint(cortex)
    persisted = _persist_roundtrip(before_restart)
    resumed = resume_packet_cortex(session, persisted, monotonic_ms=200)
    restart_events = [event for event in resumed.events if event.event_kind == "RESTART_REENTRY"]
    if len(restart_events) != 1:
        raise AssertionError("restart did not create exactly one reentry boundary")

    late_tool_rejected_post_restart = False
    try:
        resumed.emit_system_event(
            turn_id="turn-a",
            monotonic_ms=205,
            event_kind="TOOL_RESULT",
            tool_ref="tool:t7-g4-stale-after-barge",
            detail="must remain fenced after restart",
        )
    except VoicePacketCortexError:
        late_tool_rejected_post_restart = True
    if not late_tool_rejected_post_restart:
        raise AssertionError("restart resurrected stale tool ownership")

    # New answer after restart becomes fully heard and is the only durable result subject.
    resumed.emit_intent(turn_id="turn-b", monotonic_ms=210, voice_intent="ANSWER")
    resumed.queue_output(
        turn_id="turn-b",
        packet_id="output-b-0",
        monotonic_ms=220,
        text_segment="Die neue Frage wird nach dem Neustart vollständig beantwortet.",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=300,
        sequence=0,
    )
    resumed.advance_output("output-b-0", playback_state="started", monotonic_ms=230, heard_fraction=0.0)
    completed_pre_close = resumed.advance_output(
        "output-b-0", playback_state="completed", monotonic_ms=300, heard_fraction=1.0
    )
    heard = build_heard_result(session=session, output_packets=(completed_pre_close,))

    outcome_identity = session.session_causal_identity.derive(
        causal_id="causal-t7-composed-outcome-g4",
        generation=3,
        turn_id="turn-b-outcome",
    )
    outcome = resumed.close_session(
        turn_id="turn-close",
        monotonic_ms=320,
        outcome_causal_identity=outcome_identity,
        outcome_kind=OUTCOME_RETURNED,
        result_ref=heard.payload_ref,
        result_sha256=heard.payload_sha256,
        provenance_refs=("trigger7:g4:composed-close",),
    )
    close_event = [event for event in resumed.events if event.event_kind == "SESSION_CLOSE"][-1]
    completed_post_close = next(packet for packet in resumed.outputs if packet.packet_id == "output-b-0")
    interrupted_post_close = next(packet for packet in resumed.outputs if packet.packet_id == "output-a-0")
    if completed_post_close.voiceoutcome_ref != outcome.outcome_id or not completed_post_close.commit_eligible:
        raise AssertionError("completed/heard output did not bind to exact VoiceOutcome")
    if interrupted_post_close.voiceoutcome_ref is not None or interrupted_post_close.commit_eligible:
        raise AssertionError("interrupted output leaked into durable VoiceOutcome authority")

    receipt = bind_completed_reentry(
        session=session,
        outcome=outcome,
        output_packets=(completed_post_close,),
        close_event=close_event,
        provenance_refs=("trigger7:g4:heard-result-reentry",),
    )
    if tuple(receipt.ordered_output_packet_ids) != ("output-b-0",):
        raise AssertionError("reentry receipt includes non-heard/interrupted output")
    if receipt.heard_result_ref != heard.payload_ref or receipt.heard_result_sha256 != heard.payload_sha256:
        raise AssertionError("reentry receipt drifted from pre-close heard-result identity")

    # Closed checkpoint gets a second serialized restart/readback. Exact close + reentry must replay idempotently.
    closed_checkpoint = _persist_roundtrip(export_packet_cortex_checkpoint(resumed))
    closed_reentry = resume_packet_cortex(session, closed_checkpoint, monotonic_ms=400)
    if closed_reentry.is_open:
        raise AssertionError("closed session reopened after persisted restart")
    replay_outcome = closed_reentry.close_session(
        turn_id="turn-close",
        monotonic_ms=320,
        outcome_causal_identity=outcome_identity,
        outcome_kind=OUTCOME_RETURNED,
        result_ref=heard.payload_ref,
        result_sha256=heard.payload_sha256,
        provenance_refs=("trigger7:g4:composed-close",),
    )
    if replay_outcome != outcome or replay_outcome.sha256() != outcome.sha256():
        raise AssertionError("closed VoiceOutcome replay is not idempotent")
    replay_close_event = [event for event in closed_reentry.events if event.event_kind == "SESSION_CLOSE"][-1]
    replay_completed = next(packet for packet in closed_reentry.outputs if packet.packet_id == "output-b-0")
    replay_receipt = bind_completed_reentry(
        session=session,
        outcome=replay_outcome,
        output_packets=(replay_completed,),
        close_event=replay_close_event,
        provenance_refs=("trigger7:g4:heard-result-reentry",),
        existing=receipt,
    )
    if replay_receipt != receipt or replay_receipt.sha256() != receipt.sha256():
        raise AssertionError("heard-result reentry receipt is not idempotent after restart")

    latency = packet_latency_report(resumed, "turn-b")
    expected_latency = {
        "asr_from_speech_start_ms": 30,
        "decision_after_asr_ms": 60,
        "first_output_after_decision_ms": 10,
        "playback_after_first_output_ms": 10,
        "speech_to_playback_ms": 110,
    }
    for key, expected in expected_latency.items():
        if latency.get(key) != expected:
            raise AssertionError(f"latency marker {key} changed: expected={expected} observed={latency.get(key)}")

    return {
        "schema": SCHEMA,
        "source_sha": os.environ.get("GITHUB_SHA", "LOCAL_UNBOUND"),
        "semantic_key": SEMANTIC_KEY,
        "research_id": RESEARCH_ID,
        "result": "NO_COUNTEREXAMPLE",
        "composition": [
            "ASR_SURROGATE_VOICE_INPUT_PACKET",
            "VOICE_PACKET_CORTEX",
            "PRESENCE_STATE_AND_PACKET_TURN_POLICY",
            "BARGE_IN_CANCELLATION",
            "OUTPUT_TTS_SURROGATE_PACKET",
            "CHECKPOINT_FILESYSTEM_ROUNDTRIP",
            "RESTART_REENTRY",
            "FULLY_HEARD_RESULT",
            "VOICE_OUTCOME",
            "HEARD_RESULT_REENTRY_RECEIPT",
            "CLOSED_RESTART_IDEMPOTENCE",
        ],
        "observations": {
            "hold_policy_intent": policy_event.voice_intent,
            "presence_state": policy_event.presence_state,
            "interrupted_output_state": interrupted_post_close.playback_state,
            "interrupted_heard_fraction": float(interrupted_post_close.heard_fraction),
            "interrupted_commit_eligible": interrupted_post_close.commit_eligible,
            "interrupted_prefix_ref": prefix.payload_ref,
            "late_tool_rejected_pre_restart": late_tool_rejected_pre_restart,
            "late_tool_rejected_post_restart": late_tool_rejected_post_restart,
            "restart_reentry_event_count": len(restart_events),
            "durable_output_packet_ids": list(receipt.ordered_output_packet_ids),
            "voiceoutcome_id": outcome.outcome_id,
            "reentry_receipt_id": receipt.receipt_id,
            "closed_restart_replay_idempotent": True,
            "latency_ms": latency,
        },
        "classification": (
            "Repository-executable deterministic text/information-packet composition evidence only; "
            "physical ASR/TTS/device/runtime and canonical durable state remain unproven."
        ),
        "explicit_zero_credit": {
            "acoustic": 0,
            "asr_runtime": 0,
            "tts_runtime": 0,
            "target_runtime": 0,
            "vps_runtime": 0,
            "physical_audio": 0,
            "physical_presence": 0,
            "unifieddb_write": 0,
            "semantic_gwt_jspace": 0,
            "effect": 0,
            "training": 0,
            "whole_voice_e2e": 0,
            "whole_product": 0,
        },
    }


def main() -> int:
    try:
        report = run_discriminator()
    except Exception as exc:
        report = {
            "schema": SCHEMA,
            "source_sha": os.environ.get("GITHUB_SHA", "LOCAL_UNBOUND"),
            "semantic_key": SEMANTIC_KEY,
            "research_id": RESEARCH_ID,
            "result": "COUNTEREXAMPLE_OR_HARNESS_DEFECT_REQUIRES_TRIAGE",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "explicit_zero_credit": {
                "acoustic": 0,
                "asr_runtime": 0,
                "tts_runtime": 0,
                "target_runtime": 0,
                "vps_runtime": 0,
                "physical_audio": 0,
                "physical_presence": 0,
                "unifieddb_write": 0,
                "semantic_gwt_jspace": 0,
                "effect": 0,
                "training": 0,
                "whole_voice_e2e": 0,
                "whole_product": 0,
            },
        }
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
