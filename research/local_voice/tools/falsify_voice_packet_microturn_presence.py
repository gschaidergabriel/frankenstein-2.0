#!/usr/bin/env python3
"""Trigger-7 research diagnostic: composed micro-turn + Presence semantics.

No acoustic/target-runtime/physical/GWT/effect/training/whole-product credit.
"""
from __future__ import annotations
import json, os
from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoiceInputPacket, VoicePacketCortex, VoicePacketCortexError

SCHEMA = "F2_T7_MICROTURN_PRESENCE_DIAGNOSTIC/v1"

def session(tag: str) -> VoiceSessionCapsule:
    root = CausalIdentity(
        session_id=f"session-t7-{tag}", agent_id="frankenstein-2",
        task_id="task-t7-microturn-presence", turn_id="turn-input",
        causal_id=f"causal-input-{tag}", generation=3,
    )
    intent = VoiceIntent.create(
        causal_identity=root, input_ref=f"trigger7:microturn:{tag}",
        input_sha256="7"*64, provenance_refs=("trigger7:microturn-presence-diagnostic",),
    )
    return VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id=f"causal-session-{tag}", generation=4, turn_id="turn-session"
        ),
        provenance_refs=("trigger7:microturn-presence-session",),
    )

def inp(cortex: VoicePacketCortex, packet_id: str, sequence: int, ms: int, text: str,
        *, speech_start: bool = False, barge_in: bool = False,
        overlap_state: str = "NONE") -> VoiceInputPacket:
    return VoiceInputPacket(
        session_id=cortex.session_id, turn_id="turn-user", packet_id=packet_id,
        monotonic_ms=ms, source_modality="asr_partial", text=text, language="de-DE",
        is_final=False, confidence=0.93, speech_start=speech_start, speech_end=False,
        vad_state="SPEECH", endpoint_decision="HOLD", overlap_state=overlap_state,
        barge_in=barge_in, source_duration_ms=160, sequence=sequence,
    )

def probe(presence: str, tag: str) -> dict[str, object]:
    c = VoicePacketCortex(session(tag), presence_state=presence)
    first = c.accept_input(inp(c, "in-0", 0, 100, "Also ich wollte", speech_start=True))
    wait = c.emit_intent(
        turn_id="turn-user", monotonic_ms=110, voice_intent="WAIT",
        gwt_ref="gwt:microturn-wait", memory_refs=("memory:conversation-state",),
        detail="speaker continuation expected",
    )
    back = c.queue_output(
        turn_id="turn-user", packet_id="out-back", monotonic_ms=120,
        text_segment="mhm", expression_intent="attentive", speech_act="BACKCHANNEL",
        planned_audio_duration_ms=120, sequence=0,
    )
    c.advance_output("out-back", playback_state="started", monotonic_ms=125, heard_fraction=0.0)
    c.advance_output("out-back", playback_state="completed", monotonic_ms=245, heard_fraction=1.0)
    cont = c.accept_input(inp(c, "in-1", 1, 260, "und dann noch etwas ergänzen"))
    c.queue_output(
        turn_id="turn-user", packet_id="out-answer", monotonic_ms=300,
        text_segment="Ich antworte jetzt.", expression_intent="neutral", speech_act="ANSWER",
        planned_audio_duration_ms=900, sequence=1,
    )
    c.advance_output("out-answer", playback_state="started", monotonic_ms=305, heard_fraction=0.0)
    c.advance_output("out-answer", playback_state="heard", monotonic_ms=420, heard_fraction=0.15)
    tool = c.emit_intent(
        turn_id="turn-user", monotonic_ms=430, voice_intent="TOOL_USE",
        tool_ref="tool:microturn-status", detail="becomes stale on barge-in",
    )
    barge = c.accept_input(inp(
        c, "in-2", 2, 450, "warte, anders",
        barge_in=True, overlap_state="USER_OVER_OUTPUT",
    ))
    late_rejected = False
    try:
        c.emit_system_event(
            turn_id="turn-user", monotonic_ms=470, event_kind="TOOL_RESULT",
            tool_ref="tool:microturn-status", detail="late result after barge-in",
        )
    except VoicePacketCortexError:
        late_rejected = True
    answer = {x.packet_id: x for x in c.outputs}["out-answer"]
    kinds = [x.event_kind for x in c.events]
    ok = (
        first.event_kind.startswith("SPEECH_START_") and wait.voice_intent == "WAIT"
        and back.speech_act == "BACKCHANNEL" and cont.event_kind == "ASR_PARTIAL"
        and tool.voice_intent == "TOOL_USE" and barge.event_kind == "ASR_PARTIAL"
        and answer.playback_state == "interrupted" and answer.heard_fraction == 0.15
        and not answer.commit_eligible and "BARGE_IN_CANCEL_PROPAGATED" in kinds
        and late_rejected
    )
    return {
        "presence_state": presence, "transition_ok": ok,
        "answer_playback_state": answer.playback_state,
        "answer_heard_fraction": answer.heard_fraction,
        "answer_commit_eligible": answer.commit_eligible,
        "late_tool_rejected": late_rejected, "event_kinds": kinds,
    }

def behavior(x: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in x.items() if k != "presence_state"}

def main() -> int:
    a = probe("PRESENT_INTERRUPTIBLE", "interruptible")
    b = probe("PRESENT_BUSY", "busy")
    same = behavior(a) == behavior(b)
    report = {
        "schema": SCHEMA, "source_sha": os.environ.get("GITHUB_SHA", "LOCAL_UNBOUND"),
        "result": (
            "DISCOVERY_PRESENCE_METADATA_ONLY_AT_PROBED_BOUNDARY"
            if same and a["transition_ok"] and b["transition_ok"]
            else "COMPOSED_MICROTURN_BEHAVIOR_DIFFERS_OR_PROBE_FAILED"
        ),
        "interruptible": a, "busy": b, "presence_behavior_equivalent": same,
        "interpretation": (
            "Equivalent behavior is a candidate Presence/Interruptibility semantic gap; "
            "it is not authority to invent policy. Check for an admitted downstream consumer first."
            if same else
            "Presence already changes probed behavior or the composed probe failed; inspect trace."
        ),
        "explicit_zero_credit": {
            "acoustic": 0, "target_runtime": 0, "physical_audio": 0,
            "semantic_gwt_jspace": 0, "effect": 0, "training": 0,
            "whole_voice_e2e": 0, "whole_product": 0,
        },
    }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if a["transition_ok"] and b["transition_ok"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
