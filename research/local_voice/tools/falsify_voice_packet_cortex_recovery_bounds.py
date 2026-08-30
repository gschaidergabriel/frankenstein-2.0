#!/usr/bin/env python3
"""Exact-source PN9/PN10 falsifier for WP715 packet recovery and bounded state.

This is packet/recovery component evidence only. It performs no model, ASR, TTS,
acoustic, physical-device, external-effect, or whole-product work.
"""
from __future__ import annotations

import json
import os
from typing import Callable

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import (
    VoiceInputPacket,
    VoicePacketCortex,
    VoicePacketCortexError,
)
from frankenstein2.voice_packet_cortex_recovery import (
    export_packet_cortex_checkpoint,
    resume_packet_cortex,
)

SCHEMA = "F2_PACKET_CORTEX_RECOVERY_BOUNDS_FALSIFIER/v1"


def make_session(suffix: str) -> VoiceSessionCapsule:
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
        input_sha256="a" * 64,
        provenance_refs=("trigger4:wp715-recovery-bounds",),
    )
    return VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id=f"causal-session-wp715-{suffix}",
            generation=2,
            turn_id="turn-session",
        ),
        provenance_refs=("trigger4:wp715-recovery-bounds-session",),
    )


def one_final(cortex: VoicePacketCortex, index: int) -> VoiceInputPacket:
    return VoiceInputPacket(
        session_id=cortex.session_id,
        turn_id=f"turn-{index}",
        packet_id=f"input-{index}",
        monotonic_ms=1000 + index,
        source_modality="asr_final",
        text="x",
        language="de-DE",
        is_final=True,
        confidence=0.99,
        speech_start=True,
        speech_end=True,
        vad_state="SPEECH",
        endpoint_decision="END",
        overlap_state="NONE",
        barge_in=False,
        source_duration_ms=1,
        sequence=0,
        fault_flags=(),
    )


def expect_cortex_error(fn: Callable[[], object]) -> bool:
    try:
        fn()
    except VoicePacketCortexError:
        return True
    return False


def pn9_restart_continuation() -> tuple[bool, str]:
    session = make_session("pn9")
    cortex = VoicePacketCortex(session)
    cortex.accept_input(
        VoiceInputPacket(
            session_id=cortex.session_id,
            turn_id="turn-0",
            packet_id="input-0",
            monotonic_ms=100,
            source_modality="asr_partial",
            text="Wei",
            language="de-DE",
            is_final=False,
            confidence=0.90,
            speech_start=True,
            speech_end=False,
            vad_state="SPEECH",
            endpoint_decision="HOLD",
            overlap_state="NONE",
            barge_in=False,
            source_duration_ms=80,
            sequence=0,
            fault_flags=(),
        )
    )
    cortex.queue_output(
        turn_id="turn-0",
        packet_id="output-0",
        monotonic_ms=120,
        text_segment="Ja",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=100,
        sequence=0,
    )
    checkpoint = export_packet_cortex_checkpoint(cortex)
    resumed = resume_packet_cortex(session, checkpoint, monotonic_ms=200)
    resumed.accept_input(
        VoiceInputPacket(
            session_id=resumed.session_id,
            turn_id="turn-0",
            packet_id="input-1",
            monotonic_ms=210,
            source_modality="asr_final",
            text="Weiter",
            language="de-DE",
            is_final=True,
            confidence=0.99,
            speech_start=False,
            speech_end=True,
            vad_state="SPEECH",
            endpoint_decision="END",
            overlap_state="NONE",
            barge_in=False,
            source_duration_ms=100,
            sequence=1,
            fault_flags=(),
        )
    )
    resumed.queue_output(
        turn_id="turn-0",
        packet_id="output-1",
        monotonic_ms=220,
        text_segment="Weiter",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=100,
        sequence=1,
    )
    ok = resumed.events[-1].event_kind == "OUTPUT_QUEUED"
    return ok, "restart preserved per-turn input/output sequence identity and allowed exact continuation"


def pn10_input_bound() -> tuple[bool, str]:
    cap = VoicePacketCortex.MAX_INPUT_PACKETS
    cortex = VoicePacketCortex(make_session("pn10-inputs"))
    for index in range(cap):
        cortex.accept_input(one_final(cortex, index))
    at_cap = len(cortex._input_seen) == cap
    rejected = expect_cortex_error(lambda: cortex.accept_input(one_final(cortex, cap)))
    return at_cap and rejected, f"input cap={cap}; at_cap={at_cap}; cap_plus_one_rejected={rejected}"


def pn10_output_bound() -> tuple[bool, str]:
    cap = VoicePacketCortex.MAX_OUTPUT_PACKETS
    cortex = VoicePacketCortex(make_session("pn10-outputs"))
    for index in range(cap):
        cortex.queue_output(
            turn_id=f"turn-{index}",
            packet_id=f"output-{index}",
            monotonic_ms=1000 + index,
            text_segment="x",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=1,
            sequence=0,
        )
    at_cap = len(cortex.outputs) == cap
    rejected = expect_cortex_error(
        lambda: cortex.queue_output(
            turn_id=f"turn-{cap}",
            packet_id=f"output-{cap}",
            monotonic_ms=1000 + cap,
            text_segment="x",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=1,
            sequence=0,
        )
    )
    return at_cap and rejected, f"output cap={cap}; at_cap={at_cap}; cap_plus_one_rejected={rejected}"


def pn10_tool_bound() -> tuple[bool, str]:
    cap = VoicePacketCortex.MAX_TOOL_REFS
    cortex = VoicePacketCortex(make_session("pn10-tools"))
    for index in range(cap):
        cortex.emit_intent(
            turn_id=f"turn-{index}",
            monotonic_ms=1000 + index,
            voice_intent="TOOL_USE",
            tool_ref=f"tool:{index}",
        )
    observed = len(cortex._active_tools) + len(cortex._cancelled_tools)
    at_cap = observed == cap
    rejected = expect_cortex_error(
        lambda: cortex.emit_intent(
            turn_id=f"turn-{cap}",
            monotonic_ms=1000 + cap,
            voice_intent="TOOL_USE",
            tool_ref=f"tool:{cap}",
        )
    )
    return at_cap and rejected, f"tool cap={cap}; at_cap={at_cap}; cap_plus_one_rejected={rejected}"


def pn10_event_bound() -> tuple[bool, str]:
    cap = VoicePacketCortex.MAX_EVENTS
    cortex = VoicePacketCortex(make_session("pn10-events"))
    # SESSION_OPEN already consumed one event.
    for index in range(cap - 1):
        cortex.emit_intent(
            turn_id="turn-events",
            monotonic_ms=1000 + index,
            voice_intent="WAIT",
        )
    at_cap = len(cortex.events) == cap
    rejected = expect_cortex_error(
        lambda: cortex.emit_intent(
            turn_id="turn-events",
            monotonic_ms=1000 + cap,
            voice_intent="WAIT",
        )
    )
    return at_cap and rejected, f"event cap={cap}; at_cap={at_cap}; cap_plus_one_rejected={rejected}"


def pn10_checkpoint_bound() -> tuple[bool, str]:
    cortex = VoicePacketCortex(make_session("pn10-checkpoint"))
    checkpoint = export_packet_cortex_checkpoint(cortex)
    event_count = len(checkpoint["payload"]["events"])
    ok = event_count <= VoicePacketCortex.MAX_EVENTS
    return ok, f"checkpoint events={event_count}; source event cap={VoicePacketCortex.MAX_EVENTS}"


def main() -> int:
    probes: tuple[tuple[str, Callable[[], tuple[bool, str]]], ...] = (
        ("PN9_RESTART_CONTINUATION", pn9_restart_continuation),
        ("PN10_INPUT_CAP", pn10_input_bound),
        ("PN10_OUTPUT_CAP", pn10_output_bound),
        ("PN10_TOOL_CAP", pn10_tool_bound),
        ("PN10_EVENT_CAP", pn10_event_bound),
        ("PN10_CHECKPOINT_BOUND", pn10_checkpoint_bound),
    )
    results = []
    for probe_id, fn in probes:
        try:
            passed, detail = fn()
        except Exception as exc:  # report exact executable counterexample instead of losing it
            passed = False
            detail = f"{type(exc).__name__}: {exc}"
        results.append({"probe_id": probe_id, "passed": passed, "detail": detail})

    failed = [item for item in results if not item["passed"]]
    report = {
        "schema": SCHEMA,
        "source_sha": os.environ.get("GITHUB_SHA", "LOCAL_UNBOUND"),
        "result": "PASS" if not failed else "PRODUCT_NEGATIVE",
        "source_limits": {
            "MAX_INPUT_PACKETS": VoicePacketCortex.MAX_INPUT_PACKETS,
            "MAX_OUTPUT_PACKETS": VoicePacketCortex.MAX_OUTPUT_PACKETS,
            "MAX_TOOL_REFS": VoicePacketCortex.MAX_TOOL_REFS,
            "MAX_EVENTS": VoicePacketCortex.MAX_EVENTS,
        },
        "probes": results,
        "failed_probe_ids": [item["probe_id"] for item in failed],
        "outbound_model_asr_tts_calls": 0,
        "acoustic_credit": 0,
        "target_runtime_credit": 0,
        "physical_device_credit": 0,
        "whole_voice_e2e_credit": 0,
        "whole_product_credit": 0,
    }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
