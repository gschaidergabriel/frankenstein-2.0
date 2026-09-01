#!/usr/bin/env python3
"""Trigger-7 recovery composition discriminator for VoicePacketCortex.

Research/falsifier scope only. This tool deliberately mutates exported checkpoint
payloads and re-hashes them to test semantic revalidation at restart/reconnect.
It performs no product mutation and creates no acoustic/runtime/acceptance credit.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from typing import Any, Callable

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoicePacketCortex, VoicePacketCortexError
from frankenstein2.voice_packet_cortex_recovery import (
    export_packet_cortex_checkpoint,
    resume_packet_cortex,
)

SCHEMA = "F2_T7_RECOVERY_COMMIT_CANCEL_COMPOSITION_DIAGNOSTIC/v1"


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
        session_id=f"session-t7-rcomp-{tag}",
        agent_id="frankenstein-2",
        task_id="task-t7-recovery-commit-cancel-composition",
        turn_id="turn-root",
        causal_id=f"causal-root-{tag}",
        generation=1,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref=f"trigger7:rcomp:{tag}",
        input_sha256="7" * 64,
        provenance_refs=("trigger7:recovery-composition-diagnostic",),
    )
    return VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id=f"causal-session-{tag}",
            generation=2,
            turn_id="turn-session",
        ),
        provenance_refs=("trigger7:recovery-composition-session",),
    )


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


def completed_output_checkpoint(tag: str) -> tuple[VoiceSessionCapsule, dict[str, Any]]:
    session = make_session(tag)
    cortex = VoicePacketCortex(session)
    cortex.queue_output(
        turn_id="turn-output",
        packet_id="output-0",
        monotonic_ms=100,
        text_segment="vollstaendig gehoert",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=200,
        sequence=0,
    )
    cortex.advance_output("output-0", playback_state="started", monotonic_ms=110, heard_fraction=0.0)
    cortex.advance_output("output-0", playback_state="completed", monotonic_ms=310, heard_fraction=1.0)
    return session, export_packet_cortex_checkpoint(cortex)


def rcomp1_completed_heard_commit_projection() -> tuple[bool, str]:
    session, checkpoint = completed_output_checkpoint("commit-projection")
    raw = checkpoint["payload"]["outputs"][0]
    if raw["playback_state"] != "completed" or raw["heard_fraction"] != 1.0 or raw["commit_eligible"] is not True:
        return False, "diagnostic setup failed to produce canonical fully-heard commit-eligible output"
    raw["commit_eligible"] = False
    mutated = rehash(checkpoint)
    try:
        resumed = resume_packet_cortex(session, mutated, monotonic_ms=400)
    except VoicePacketCortexError as exc:
        return True, f"resume rejected contradictory completed/heard commit projection: {type(exc).__name__}: {exc}"
    restored = resumed.outputs[0]
    return (
        False,
        "resume admitted fully-heard completed output with commit_eligible=false; "
        f"restored_state={restored.playback_state};heard={restored.heard_fraction};commit={restored.commit_eligible}",
    )


def tool_checkpoint(tag: str) -> tuple[VoiceSessionCapsule, dict[str, Any]]:
    session = make_session(tag)
    cortex = VoicePacketCortex(session)
    cortex.emit_intent(
        turn_id="turn-tool-a",
        monotonic_ms=100,
        voice_intent="TOOL_USE",
        tool_ref="tool:shared",
        detail="first ownership",
    )
    return session, export_packet_cortex_checkpoint(cortex)


def rcomp2_tool_history_projection_drop() -> tuple[bool, str]:
    session, checkpoint = tool_checkpoint("tool-history-drop")
    checkpoint["payload"]["active_tools"] = []
    checkpoint["payload"]["cancelled_tools"] = []
    mutated = rehash(checkpoint)
    try:
        resumed = resume_packet_cortex(session, mutated, monotonic_ms=200)
    except VoicePacketCortexError as exc:
        return True, f"resume rejected tool-history/projection mismatch: {type(exc).__name__}: {exc}"
    try:
        resumed.emit_intent(
            turn_id="turn-tool-b",
            monotonic_ms=210,
            voice_intent="TOOL_USE",
            tool_ref="tool:shared",
            detail="second ownership after corrupted restore",
        )
    except VoicePacketCortexError as exc:
        return True, f"restored cortex fenced historical tool ref despite missing ownership projection: {type(exc).__name__}: {exc}"
    return False, "historical TOOL_USE remained in events but removing ownership projections allowed tool:shared to be re-issued"


def rcomp3_valid_active_tool_restart_fence() -> tuple[bool, str]:
    session, checkpoint = tool_checkpoint("tool-fence-baseline")
    try:
        resumed = resume_packet_cortex(session, checkpoint, monotonic_ms=200)
    except VoicePacketCortexError as exc:
        return False, f"valid active-tool checkpoint unexpectedly rejected: {type(exc).__name__}: {exc}"
    result_rejected = False
    reuse_rejected = False
    details: list[str] = []
    try:
        resumed.emit_system_event(
            turn_id="turn-tool-a",
            monotonic_ms=210,
            event_kind="TOOL_RESULT",
            tool_ref="tool:shared",
            detail="late result after restart",
        )
    except VoicePacketCortexError as exc:
        result_rejected = True
        details.append(f"late-result={exc}")
    try:
        resumed.emit_intent(
            turn_id="turn-tool-b",
            monotonic_ms=220,
            voice_intent="TOOL_USE",
            tool_ref="tool:shared",
            detail="reuse after restart",
        )
    except VoicePacketCortexError as exc:
        reuse_rejected = True
        details.append(f"reuse={exc}")
    return result_rejected and reuse_rejected, ";".join(details) or "restart did not fence active tool ownership"


def rcomp4_output_sequence_projection() -> tuple[bool, str]:
    session = make_session("output-sequence-projection")
    cortex = VoicePacketCortex(session)
    checkpoint = export_packet_cortex_checkpoint(cortex)
    checkpoint["payload"]["last_output_sequence"] = [["turn-ghost", 999]]
    mutated = rehash(checkpoint)
    try:
        resumed = resume_packet_cortex(session, mutated, monotonic_ms=200)
    except VoicePacketCortexError as exc:
        return True, f"resume rejected unbacked output ordering projection: {type(exc).__name__}: {exc}"
    try:
        resumed.queue_output(
            turn_id="turn-ghost",
            packet_id="fresh-output",
            monotonic_ms=210,
            text_segment="neu",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=50,
            sequence=0,
        )
    except VoicePacketCortexError as exc:
        return False, f"unbacked last_output_sequence minted ordering authority: {type(exc).__name__}: {exc}"
    return False, "resume admitted unbacked last_output_sequence projection; fresh sequence=0 was accepted"


def queued_output_checkpoint(tag: str) -> tuple[VoiceSessionCapsule, dict[str, Any]]:
    session = make_session(tag)
    cortex = VoicePacketCortex(session)
    cortex.queue_output(
        turn_id="turn-output",
        packet_id="output-0",
        monotonic_ms=100,
        text_segment="wartend",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=100,
        sequence=0,
    )
    return session, export_packet_cortex_checkpoint(cortex)


def rcomp5_duplicate_output_packet_id() -> tuple[bool, str]:
    session, checkpoint = queued_output_checkpoint("duplicate-output")
    checkpoint["payload"]["outputs"].append(copy.deepcopy(checkpoint["payload"]["outputs"][0]))
    rejected, detail = resume_rejected(session, rehash(checkpoint), monotonic_ms=200)
    return rejected, f"duplicate output packet_id; {detail}"


def rcomp6_corrupt_queued_heard_fraction() -> tuple[bool, str]:
    session, checkpoint = queued_output_checkpoint("corrupt-heard")
    checkpoint["payload"]["outputs"][0]["heard_fraction"] = 0.5
    rejected, detail = resume_rejected(session, rehash(checkpoint), monotonic_ms=200)
    return rejected, f"queued output claims heard_fraction=0.5; {detail}"


def main() -> int:
    probes: tuple[tuple[str, Callable[[], tuple[bool, str]]], ...] = (
        ("RCOMP1_COMPLETED_HEARD_COMMIT_PROJECTION", rcomp1_completed_heard_commit_projection),
        ("RCOMP2_TOOL_HISTORY_PROJECTION_DROP", rcomp2_tool_history_projection_drop),
        ("RCOMP3_VALID_ACTIVE_TOOL_RESTART_FENCE", rcomp3_valid_active_tool_restart_fence),
        ("RCOMP4_OUTPUT_SEQUENCE_PROJECTION", rcomp4_output_sequence_projection),
        ("RCOMP5_DUPLICATE_OUTPUT_PACKET_ID", rcomp5_duplicate_output_packet_id),
        ("RCOMP6_CORRUPT_QUEUED_HEARD_FRACTION", rcomp6_corrupt_queued_heard_fraction),
    )
    cases = []
    for probe_id, fn in probes:
        try:
            fail_closed, detail = fn()
        except Exception as exc:
            fail_closed = False
            detail = f"diagnostic exception {type(exc).__name__}: {exc}"
        cases.append({"probe_id": probe_id, "fail_closed": fail_closed, "detail": detail})

    negatives = [case["probe_id"] for case in cases if not case["fail_closed"]]
    report = {
        "schema": SCHEMA,
        "source_sha": os.environ.get("GITHUB_SHA", "LOCAL_UNBOUND"),
        "research_id": "T7-20260901-RECOVERY-COMMIT-CANCEL-COMPOSITION",
        "result": "NO_COUNTEREXAMPLE" if not negatives else "PRODUCT_NEGATIVE_CANDIDATE",
        "cases": cases,
        "failed_closed_probe_ids": negatives,
        "classification": (
            "Repository-executable deterministic recovery-composition counterexample candidate only; "
            "route reproduced product negatives to Trigger4/current legal mutation owner."
        ),
        "explicit_zero_credit": {
            "acoustic": 0,
            "target_runtime": 0,
            "physical_audio": 0,
            "asr_runtime": 0,
            "tts_runtime": 0,
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
