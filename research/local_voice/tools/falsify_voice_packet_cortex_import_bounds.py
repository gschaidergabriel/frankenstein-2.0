#!/usr/bin/env python3
"""Trigger-7 executable discriminator for checkpoint import bound revalidation.

Research/falsifier scope only. No acoustic, target-runtime, physical-device,
semantic GWT/J-Space, effect, training, whole-voice, or whole-product credit.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from typing import Any, Callable

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

SCHEMA = "F2_T7_RECOVERY_IMPORT_BOUNDS_DIAGNOSTIC/v1"


def digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def rehash(checkpoint: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(checkpoint)
    result["payload_sha256"] = digest(result["payload"])
    return result


def make_session(tag: str) -> VoiceSessionCapsule:
    root = CausalIdentity(
        session_id=f"session-t7-rbound-{tag}",
        agent_id="frankenstein-2",
        task_id="task-t7-recovery-import-bounds",
        turn_id="turn-root",
        causal_id=f"causal-root-{tag}",
        generation=1,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref=f"trigger7:rbound:{tag}",
        input_sha256="7" * 64,
        provenance_refs=("trigger7:rbound-import-diagnostic",),
    )
    return VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id=f"causal-session-{tag}",
            generation=2,
            turn_id="turn-session",
        ),
        provenance_refs=("trigger7:rbound-import-session",),
    )


def base_checkpoint(tag: str) -> tuple[VoiceSessionCapsule, dict[str, Any]]:
    session = make_session(tag)
    cortex = VoicePacketCortex(session)
    return session, export_packet_cortex_checkpoint(cortex)


def resume_rejected(
    session: VoiceSessionCapsule,
    checkpoint: dict[str, Any],
    *,
    monotonic_ms: int = 1000,
) -> tuple[bool, str]:
    try:
        resume_packet_cortex(session, checkpoint, monotonic_ms=monotonic_ms)
    except VoicePacketCortexError as exc:
        return True, f"{type(exc).__name__}: {exc}"
    return False, "resume returned a usable cortex"


def rbound1() -> tuple[bool, str]:
    session, checkpoint = base_checkpoint("input-seen")
    cap = VoicePacketCortex.MAX_INPUT_PACKETS
    checkpoint["payload"]["input_seen"] = [
        [f"packet-{index}", f"{index:064x}"[-64:]]
        for index in range(cap + 1)
    ]
    rejected, detail = resume_rejected(session, rehash(checkpoint))
    return rejected, f"input_seen={cap + 1} cap={cap}; {detail}"


def rbound2() -> tuple[bool, str]:
    session = make_session("outputs")
    cortex = VoicePacketCortex(session)
    cortex.queue_output(
        turn_id="turn-output",
        packet_id="output-base",
        monotonic_ms=100,
        text_segment="x",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=10,
        sequence=0,
    )
    checkpoint = export_packet_cortex_checkpoint(cortex)
    base = checkpoint["payload"]["outputs"][0]
    cap = VoicePacketCortex.MAX_OUTPUT_PACKETS
    outputs = []
    for index in range(cap + 1):
        raw = copy.deepcopy(base)
        raw["packet_id"] = f"output-{index}"
        raw["turn_id"] = f"turn-{index}"
        raw["sequence"] = 0
        outputs.append(raw)
    checkpoint["payload"]["outputs"] = outputs
    rejected, detail = resume_rejected(session, rehash(checkpoint), monotonic_ms=1000)
    return rejected, f"outputs={cap + 1} cap={cap}; {detail}"


def rbound3() -> tuple[bool, str]:
    session, checkpoint = base_checkpoint("tools")
    cap = VoicePacketCortex.MAX_TOOL_REFS
    checkpoint["payload"]["active_tools"] = [
        [f"tool:{index}", f"turn-{index}"] for index in range(cap + 1)
    ]
    checkpoint["payload"]["cancelled_tools"] = []
    rejected, detail = resume_rejected(session, rehash(checkpoint))
    return rejected, f"active_tools={cap + 1} cap={cap}; {detail}"


def rbound4() -> tuple[bool, str]:
    session, checkpoint = base_checkpoint("events")
    base_event = checkpoint["payload"]["events"][0]
    cap = VoicePacketCortex.MAX_EVENTS
    events = []
    for index in range(cap + 1):
        raw = copy.deepcopy(base_event)
        raw["event_id"] = f"event-{index}"
        raw["monotonic_ms"] = index
        events.append(raw)
    checkpoint["payload"]["events"] = events
    checkpoint["payload"]["event_seq"] = cap + 1
    rejected, detail = resume_rejected(session, rehash(checkpoint), monotonic_ms=cap + 10)
    return rejected, f"events={cap + 1} cap={cap}; {detail}"


def input_packet(cortex: VoicePacketCortex) -> VoiceInputPacket:
    return VoiceInputPacket(
        session_id=cortex.session_id,
        turn_id="turn-ghost",
        packet_id="fresh-input",
        monotonic_ms=1200,
        source_modality="asr_final",
        text="weiter",
        language="de-DE",
        is_final=True,
        confidence=0.99,
        speech_start=True,
        speech_end=True,
        vad_state="SPEECH",
        endpoint_decision="END",
        overlap_state="NONE",
        barge_in=False,
        source_duration_ms=100,
        sequence=0,
        fault_flags=(),
    )


def rbound5() -> tuple[bool, str]:
    session, checkpoint = base_checkpoint("sequence-projection")
    checkpoint["payload"]["last_input_sequence"] = [["turn-ghost", 999]]
    checkpoint["payload"]["last_input_monotonic_ms"] = [["turn-ghost", 1100]]
    mutated = rehash(checkpoint)
    try:
        resumed = resume_packet_cortex(session, mutated, monotonic_ms=1150)
    except VoicePacketCortexError as exc:
        return True, f"resume rejected inconsistent projection: {type(exc).__name__}: {exc}"

    try:
        resumed.accept_input(input_packet(resumed))
    except VoicePacketCortexError as exc:
        return (
            False,
            "resume admitted unbacked last_input_sequence projection and it changed "
            f"subsequent ordering authority: {type(exc).__name__}: {exc}",
        )
    return (
        False,
        "resume admitted unbacked last_input_sequence projection; fresh sequence=0 was accepted",
    )


def main() -> int:
    probes: tuple[tuple[str, Callable[[], tuple[bool, str]]], ...] = (
        ("RBOUND1_INPUT_SEEN_IMPORT_CAP", rbound1),
        ("RBOUND2_OUTPUT_IMPORT_CAP", rbound2),
        ("RBOUND3_TOOL_IMPORT_CAP", rbound3),
        ("RBOUND4_EVENT_IMPORT_CAP", rbound4),
        ("RBOUND5_SEQUENCE_PROJECTION_CONSISTENCY", rbound5),
    )
    cases = []
    for probe_id, fn in probes:
        try:
            fail_closed, detail = fn()
        except Exception as exc:
            fail_closed = False
            detail = f"diagnostic exception {type(exc).__name__}: {exc}"
        cases.append(
            {
                "probe_id": probe_id,
                "fail_closed": fail_closed,
                "detail": detail,
            }
        )

    negatives = [case["probe_id"] for case in cases if not case["fail_closed"]]
    report = {
        "schema": SCHEMA,
        "source_sha": os.environ.get("GITHUB_SHA", "LOCAL_UNBOUND"),
        "result": "NO_COUNTEREXAMPLE" if not negatives else "PRODUCT_NEGATIVE_CANDIDATE",
        "cases": cases,
        "failed_closed_probe_ids": negatives,
        "classification": (
            "Repository-executable deterministic counterexample candidate only; "
            "route reproduced cases to Trigger4/current legal mutation owner."
        ),
        "explicit_zero_credit": {
            "acoustic": 0,
            "target_runtime": 0,
            "physical_audio": 0,
            "semantic_gwt_jspace": 0,
            "effect": 0,
            "training": 0,
            "whole_voice_e2e": 0,
            "whole_product": 0,
        },
    }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if not negatives else 2


if __name__ == "__main__":
    raise SystemExit(main())
