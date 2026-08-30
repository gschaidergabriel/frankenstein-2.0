#!/usr/bin/env python3
"""Exact-source Trigger-4 falsifier for packet-cortex ordering/clock invariants.

Exit 0 when all tested invariants fail closed. Exit 2 when one or more current
product behaviors violate the expected deterministic packet/cortex contract.
The emitted JSON is bounded component evidence only; it grants no acoustic,
target-runtime, physical-device, whole-voice, or whole-product credit.
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

SCHEMA = "F2_PACKET_CORTEX_FULL_DUPLEX_FALSIFIER/v1"


def make_session() -> VoiceSessionCapsule:
    root = CausalIdentity(
        session_id="session-t4-falsifier",
        agent_id="frankenstein-2",
        task_id="task-t4-falsifier",
        turn_id="turn-input",
        causal_id="causal-input-t4-falsifier",
        generation=3,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref="trigger4:falsifier-fixture",
        input_sha256="f" * 64,
        provenance_refs=("trigger4:full-duplex-falsifier",),
    )
    return VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id="causal-session-t4-falsifier",
            generation=4,
            turn_id="turn-session",
        ),
        provenance_refs=("trigger4:full-duplex-falsifier-session",),
    )


def input_packet(cortex: VoicePacketCortex, *, packet_id: str, sequence: int, monotonic_ms: int) -> VoiceInputPacket:
    return VoiceInputPacket(
        session_id=cortex.session_id,
        turn_id="turn-1",
        packet_id=packet_id,
        monotonic_ms=monotonic_ms,
        source_modality="asr_partial",
        text="Guten",
        language="de-DE",
        is_final=False,
        confidence=0.91,
        speech_start=sequence == 0,
        speech_end=False,
        vad_state="SPEECH",
        endpoint_decision="HOLD",
        overlap_state="NONE",
        barge_in=False,
        source_duration_ms=160,
        sequence=sequence,
    )


def expect_rejected(probe: Callable[[], object]) -> bool:
    try:
        probe()
    except VoicePacketCortexError:
        return True
    return False


def pn6_input_clock_rollback() -> tuple[bool, str]:
    cortex = VoicePacketCortex(make_session())
    cortex.accept_input(input_packet(cortex, packet_id="input-0", sequence=0, monotonic_ms=100))
    rejected = expect_rejected(
        lambda: cortex.accept_input(
            input_packet(cortex, packet_id="input-1", sequence=1, monotonic_ms=90)
        )
    )
    return rejected, "advancing input sequence must not move monotonic_ms backwards"


def pn6_output_clock_rollback() -> tuple[bool, str]:
    cortex = VoicePacketCortex(make_session())
    cortex.queue_output(
        turn_id="turn-0",
        packet_id="out-0",
        monotonic_ms=100,
        text_segment="Antwort",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=500,
        sequence=0,
    )
    rejected = expect_rejected(
        lambda: cortex.advance_output(
            "out-0", playback_state="started", monotonic_ms=90, heard_fraction=0.0
        )
    )
    return rejected, "output playback transition must not precede queued timestamp"


def pn6_barge_cancel_clock_rollback() -> tuple[bool, str]:
    cortex = VoicePacketCortex(make_session())
    cortex.queue_output(
        turn_id="turn-0",
        packet_id="out-0",
        monotonic_ms=100,
        text_segment="Antwort",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=500,
        sequence=0,
    )
    cortex.advance_output("out-0", playback_state="started", monotonic_ms=120, heard_fraction=0.0)
    rejected = expect_rejected(lambda: cortex.cancel_for_barge_in(turn_id="turn-1", monotonic_ms=110))
    return rejected, "barge-in cancellation timestamp must not precede current output state"


def pn7_duplicate_output_sequence() -> tuple[bool, str]:
    cortex = VoicePacketCortex(make_session())
    cortex.queue_output(
        turn_id="turn-0", packet_id="out-a", monotonic_ms=100,
        text_segment="A", expression_intent="neutral", speech_act="ANSWER",
        planned_audio_duration_ms=100, sequence=0,
    )
    rejected = expect_rejected(
        lambda: cortex.queue_output(
            turn_id="turn-0", packet_id="out-b", monotonic_ms=101,
            text_segment="B", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=100, sequence=0,
        )
    )
    return rejected, "duplicate output sequence within one turn must fail closed"


def pn7_output_sequence_order() -> tuple[bool, str]:
    cortex = VoicePacketCortex(make_session())
    cortex.queue_output(
        turn_id="turn-0", packet_id="z-first", monotonic_ms=100,
        text_segment="A", expression_intent="neutral", speech_act="ANSWER",
        planned_audio_duration_ms=100, sequence=0,
    )
    cortex.queue_output(
        turn_id="turn-0", packet_id="a-second", monotonic_ms=101,
        text_segment="B", expression_intent="neutral", speech_act="ANSWER",
        planned_audio_duration_ms=100, sequence=1,
    )
    observed = tuple(packet.sequence for packet in cortex.outputs)
    return observed == (0, 1), f"outputs must expose declared sequence order; observed={observed}"


def pn7_output_sequence_gap() -> tuple[bool, str]:
    cortex = VoicePacketCortex(make_session())
    cortex.queue_output(
        turn_id="turn-0", packet_id="out-0", monotonic_ms=100,
        text_segment="A", expression_intent="neutral", speech_act="ANSWER",
        planned_audio_duration_ms=100, sequence=0,
    )
    rejected = expect_rejected(
        lambda: cortex.queue_output(
            turn_id="turn-0", packet_id="out-2", monotonic_ms=101,
            text_segment="C", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=100, sequence=2,
        )
    )
    return rejected, "output sequence gap must fail closed or have an explicit policy"


def main() -> int:
    probes = {
        "PN6_INPUT_MONOTONIC_ROLLBACK": pn6_input_clock_rollback,
        "PN6_OUTPUT_MONOTONIC_ROLLBACK": pn6_output_clock_rollback,
        "PN6_BARGE_CANCEL_MONOTONIC_ROLLBACK": pn6_barge_cancel_clock_rollback,
        "PN7_DUPLICATE_OUTPUT_SEQUENCE": pn7_duplicate_output_sequence,
        "PN7_OUTPUT_SEQUENCE_ORDER": pn7_output_sequence_order,
        "PN7_OUTPUT_SEQUENCE_GAP": pn7_output_sequence_gap,
    }
    results = []
    for probe_id, fn in probes.items():
        passed, detail = fn()
        results.append({"probe_id": probe_id, "passed": passed, "detail": detail})

    failed = [item for item in results if not item["passed"]]
    report = {
        "schema": SCHEMA,
        "source_sha": os.environ.get("GITHUB_SHA", "LOCAL_UNBOUND"),
        "semantic_key": "af4da01da7ced3fa0bee3839adf7f4798e73399408fd29735c8a529a2ed2d9d9",
        "result": "PASS" if not failed else "PRODUCT_NEGATIVE",
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
