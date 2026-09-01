#!/usr/bin/env python3
"""FDX5 candidate falsifier for premature durable tool authority.

This probe reuses the existing VoicePacketCortex and checkpoint/reentry authority only.
It does not repair product code and cannot mint physical, whole-voice, effect, training,
or whole-product credit.
"""
from __future__ import annotations

import json
import os

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoiceInputPacket, VoicePacketCortex, VoicePacketCortexError
from frankenstein2.voice_packet_cortex_recovery import export_packet_cortex_checkpoint, resume_packet_cortex

SCHEMA = "T4_FDX5_SELF_CORRECTION_TOOL_AUTHORITY_FALSIFIER/v1"
TURN_ID = "turn-fdx5-self-correction"
PREMATURE_TOOL = "tool:fdx5-premature-partial"
FINAL_TOOL = "tool:fdx5-corrected-final"


def make_session() -> VoiceSessionCapsule:
    root = CausalIdentity(
        session_id="session-fdx5-self-correction",
        agent_id="frankenstein-2",
        task_id="task-fdx5-self-correction",
        turn_id="turn-input",
        causal_id="causal-input-fdx5-self-correction",
        generation=1,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref="fdx5:self-correction-fixture",
        input_sha256="5" * 64,
        provenance_refs=("trigger4:fdx5-candidate-falsifier",),
    )
    return VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id="causal-session-fdx5-self-correction",
            generation=2,
            turn_id="turn-session",
        ),
        provenance_refs=("trigger4:fdx5-candidate-falsifier",),
    )


def input_packet(cortex: VoicePacketCortex, *, packet_id: str, monotonic_ms: int, text: str,
                 is_final: bool, speech_start: bool, speech_end: bool, endpoint_decision: str,
                 sequence: int) -> VoiceInputPacket:
    return VoiceInputPacket(
        session_id=cortex.session_id,
        turn_id=TURN_ID,
        packet_id=packet_id,
        monotonic_ms=monotonic_ms,
        source_modality="asr_final" if is_final else "asr_partial",
        text=text,
        language="de-DE",
        is_final=is_final,
        confidence=0.95,
        speech_start=speech_start,
        speech_end=speech_end,
        vad_state="SPEECH" if not speech_end else "SILENCE",
        endpoint_decision=endpoint_decision,
        overlap_state="NONE",
        barge_in=False,
        source_duration_ms=320,
        sequence=sequence,
    )


def main() -> int:
    session = make_session()
    cortex = VoicePacketCortex(session, opened_monotonic_ms=0)

    partial = input_packet(
        cortex,
        packet_id="fdx5-input-0-partial",
        monotonic_ms=100,
        text="Öffne die erste Datei ... nein,",
        is_final=False,
        speech_start=True,
        speech_end=False,
        endpoint_decision="HOLD",
        sequence=0,
    )
    partial_event = cortex.accept_input(partial)

    premature_tool_accepted = False
    premature_tool_error = None
    try:
        cortex.emit_intent(
            turn_id=TURN_ID,
            monotonic_ms=120,
            voice_intent="TOOL_USE",
            tool_ref=PREMATURE_TOOL,
            detail="candidate derived from supersedable ASR partial before admitted endpoint",
        )
        premature_tool_accepted = True
    except VoicePacketCortexError as exc:
        premature_tool_error = str(exc)

    final = input_packet(
        cortex,
        packet_id="fdx5-input-1-final",
        monotonic_ms=220,
        text="Öffne stattdessen die zweite Datei.",
        is_final=True,
        speech_start=False,
        speech_end=True,
        endpoint_decision="END",
        sequence=1,
    )
    final_event = cortex.accept_input(final)

    final_tool_accepted = False
    final_tool_error = None
    try:
        cortex.emit_intent(
            turn_id=TURN_ID,
            monotonic_ms=240,
            voice_intent="TOOL_USE",
            tool_ref=FINAL_TOOL,
            detail="tool request derived from corrected admitted final transcript",
        )
        final_tool_accepted = True
    except VoicePacketCortexError as exc:
        final_tool_error = str(exc)

    checkpoint = export_packet_cortex_checkpoint(cortex)
    checkpoint_active_tools = dict(checkpoint["payload"]["active_tools"])
    resumed = resume_packet_cortex(session, checkpoint, monotonic_ms=300)

    premature_tool_result_accepted_after_restart = False
    premature_tool_result_error = None
    if premature_tool_accepted:
        try:
            resumed.emit_system_event(
                turn_id=TURN_ID,
                monotonic_ms=320,
                event_kind="TOOL_RESULT",
                tool_ref=PREMATURE_TOOL,
                detail="late result for superseded partial-derived tool",
            )
            premature_tool_result_accepted_after_restart = True
        except VoicePacketCortexError as exc:
            premature_tool_result_error = str(exc)

    violations = []
    if premature_tool_accepted:
        violations.append("TOOL_USE_ACCEPTED_BEFORE_FINAL_ENDPOINT")
    if checkpoint_active_tools.get(PREMATURE_TOOL) == TURN_ID:
        violations.append("PREMATURE_TOOL_OWNERSHIP_PERSISTED_IN_CHECKPOINT")
    if premature_tool_result_accepted_after_restart:
        violations.append("PREMATURE_TOOL_RESULT_ACCEPTED_AFTER_RESTART")

    result = "PRODUCT_NEGATIVE" if violations else "NO_COUNTEREXAMPLE"
    receipt = {
        "schema": SCHEMA,
        "result": result,
        "failure_class": "PRODUCT_NEGATIVE" if violations else None,
        "source": {
            "f2_subject_sha": os.environ.get("F2_SUBJECT_SHA") or os.environ.get("GITHUB_SHA") or "UNKNOWN",
            "voice_packet_cortex_authority": "src/frankenstein2/voice_packet_cortex.py",
            "recovery_authority": "src/frankenstein2/voice_packet_cortex_recovery.py",
        },
        "case": "FDX5_SELF_CORRECTION_BEFORE_TOOL_USE",
        "matrix_invariant": (
            "Superseded partial/self-corrected content must not gain durable tool authority; "
            "only the admitted final causal turn may own the tool request."
        ),
        "observed": {
            "partial_event_kind": partial_event.event_kind,
            "final_event_kind": final_event.event_kind,
            "premature_tool_accepted": premature_tool_accepted,
            "premature_tool_error": premature_tool_error,
            "final_tool_accepted": final_tool_accepted,
            "final_tool_error": final_tool_error,
            "checkpoint_active_tools": checkpoint_active_tools,
            "premature_tool_result_accepted_after_restart": premature_tool_result_accepted_after_restart,
            "premature_tool_result_error": premature_tool_result_error,
            "checkpoint_payload_sha256": checkpoint["payload_sha256"],
        },
        "violations": violations,
        "classification": "CANDIDATE_FALSIFIER_ONLY_NO_REPAIR_PERFORMED",
        "explicit_zero_credit": {
            "acoustic_asr": 0,
            "physical_audio": 0,
            "gwt_jspace": 0,
            "effect": 0,
            "training": 0,
            "whole_voice_e2e": 0,
            "whole_product": 0,
        },
        "next_action_if_product_negative": (
            "Classify as executed PRODUCT_NEGATIVE only after admitted VPS execution; then repair the existing "
            "VoicePacketCortex tool-ownership boundary without creating a second turn/tool authority, add a regression, "
            "and treat older FDX7/FDX8 runtime subjects as historical unless semantic invariance is proven."
        ),
    }
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
