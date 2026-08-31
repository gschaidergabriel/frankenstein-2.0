#!/usr/bin/env python3
"""Deterministic Trigger-7 restart/reentry composition falsifier.

Research-only packet/cortex evidence. This script intentionally creates no acoustic,
provider, canonical-memory, GWT/J-Space, effect, target-runtime, or whole-product credit.

Priority after the already-bound F18 VPS discriminator resolves:
  F15 completed-heard closed restart -> reentry exact-once
  F17 partial/interrupted restart -> never durable heard-result
  F16 completed-heard open restart -> close once -> reentry once
"""
from __future__ import annotations

import json

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import (
    VoiceHeardResultReentryError,
    bind_completed_reentry,
    build_heard_result,
    build_interrupted_heard_prefix,
)
from frankenstein2.voice_packet_cortex import VoicePacketCortex
from frankenstein2.voice_packet_cortex_recovery import (
    export_packet_cortex_checkpoint,
    resume_packet_cortex,
)

SCHEMA = "T7_RESTART_EXACT_ONCE_REENTRY_COMPOSITION_FALSIFIER/v1"


def make_session(suffix: str) -> VoiceSessionCapsule:
    root = CausalIdentity(
        session_id=f"session-t7-restart-composition-{suffix}",
        agent_id="frankenstein-2",
        task_id=f"t7-restart-composition-{suffix}",
        turn_id="turn-input",
        causal_id=f"causal-root-{suffix}",
        generation=1,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref=f"trigger7:restart-composition:{suffix}",
        input_sha256=("1" if suffix == "f15" else "2" if suffix == "f17" else "3") * 64,
        provenance_refs=("trigger7:T7-ARCH-003", f"trigger7:{suffix}"),
    )
    return VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id=f"causal-session-{suffix}", generation=2, turn_id="turn-session"
        ),
        provenance_refs=("trigger7:T7-ARCH-003", f"trigger7:{suffix}:session"),
    )


def complete_one_output(cortex: VoicePacketCortex, *, packet_id: str, text: str, start_ms: int) -> None:
    cortex.queue_output(
        turn_id="turn-voice",
        packet_id=packet_id,
        monotonic_ms=start_ms,
        text_segment=text,
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=120,
        sequence=0,
    )
    cortex.advance_output(packet_id, playback_state="started", monotonic_ms=start_ms + 10, heard_fraction=0.0)
    cortex.advance_output(packet_id, playback_state="completed", monotonic_ms=start_ms + 130, heard_fraction=1.0)


def f15_completed_closed_restart_exact_once() -> dict[str, object]:
    session = make_session("f15")
    cortex = VoicePacketCortex(session)
    complete_one_output(cortex, packet_id="output-f15", text="Vollständig gehört.", start_ms=100)
    heard = build_heard_result(session=session, output_packets=cortex.outputs)
    outcome_identity = session.session_causal_identity.derive(
        causal_id="causal-outcome-f15", generation=3, turn_id="turn-outcome"
    )
    cortex.close_session(
        turn_id="turn-close",
        monotonic_ms=300,
        outcome_causal_identity=outcome_identity,
        outcome_kind=OUTCOME_RETURNED,
        result_ref=heard.payload_ref,
        result_sha256=heard.payload_sha256,
        provenance_refs=("trigger7:T7-ARCH-003:F15",),
    )
    checkpoint = export_packet_cortex_checkpoint(cortex)
    resumed = resume_packet_cortex(session, checkpoint, monotonic_ms=400)
    if resumed.is_open or resumed._closed_outcome is None:
        raise AssertionError("F15_PRODUCT_NEGATIVE: closed checkpoint did not restore as closed")
    close_events = [event for event in resumed.events if event.event_kind == "SESSION_CLOSE"]
    if len(close_events) != 1:
        raise AssertionError("F15_PRODUCT_NEGATIVE: closed restart does not contain exactly one SESSION_CLOSE")
    first = bind_completed_reentry(
        session=session,
        outcome=resumed._closed_outcome,
        output_packets=resumed.outputs,
        close_event=close_events[0],
        provenance_refs=("trigger7:T7-ARCH-003:F15",),
    )
    replay = bind_completed_reentry(
        session=session,
        outcome=resumed._closed_outcome,
        output_packets=resumed.outputs,
        close_event=close_events[0],
        provenance_refs=("trigger7:T7-ARCH-003:F15",),
        existing=first,
    )
    if replay != first or replay.sha256() != first.sha256():
        raise AssertionError("F15_PRODUCT_NEGATIVE: exact replay minted a different reentry receipt")
    return {
        "id": "F15_COMPLETED_HEARD_CLOSED_RESTART_REENTRY_EXACT_ONCE",
        "result": "PASS",
        "receipt_id": first.receipt_id,
        "receipt_sha256": first.sha256(),
        "session_close_count_after_restore": len(close_events),
    }


def f17_partial_restart_never_durable() -> dict[str, object]:
    session = make_session("f17")
    cortex = VoicePacketCortex(session)
    cortex.queue_output(
        turn_id="turn-voice",
        packet_id="output-f17",
        monotonic_ms=100,
        text_segment="gehört|NICHTGEHOERT",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=500,
        sequence=0,
    )
    cortex.advance_output("output-f17", playback_state="started", monotonic_ms=110, heard_fraction=0.0)
    cortex.advance_output("output-f17", playback_state="heard", monotonic_ms=180, heard_fraction=0.35)
    checkpoint = export_packet_cortex_checkpoint(cortex)
    resumed = resume_packet_cortex(session, checkpoint, monotonic_ms=250)
    packet = resumed.outputs[0]
    if packet.playback_state != "interrupted" or packet.commit_eligible or packet.voiceoutcome_ref is not None:
        raise AssertionError("F17_PRODUCT_NEGATIVE: restart promoted or retained durable authority for partial output")
    prefix = build_interrupted_heard_prefix(
        packet=packet,
        heard_prefix_text="gehört|",
        measurement_ref="trigger7:packet-simulation:f17",
        provenance_refs=("trigger7:T7-ARCH-003:F17",),
    )
    try:
        build_heard_result(session=session, output_packets=resumed.outputs)
    except VoiceHeardResultReentryError:
        durable_rejected = True
    else:
        durable_rejected = False
    if not durable_rejected:
        raise AssertionError("F17_PRODUCT_NEGATIVE: interrupted restart minted durable heard-result payload")
    outcome_identity = session.session_causal_identity.derive(
        causal_id="causal-outcome-f17", generation=3, turn_id="turn-outcome"
    )
    outcome = resumed.close_session(
        turn_id="turn-close",
        monotonic_ms=300,
        outcome_causal_identity=outcome_identity,
        outcome_kind=OUTCOME_RETURNED,
        provenance_refs=("trigger7:T7-ARCH-003:F17",),
    )
    if outcome.result_ref is not None or outcome.result_sha256 is not None:
        raise AssertionError("F17_PRODUCT_NEGATIVE: partial restart close carries durable result identity")
    return {
        "id": "F17_PARTIAL_OR_INTERRUPTED_RESTART_CAN_NEVER_PROMOTE_TO_DURABLE_HEARD_RESULT",
        "result": "PASS",
        "playback_state_after_restart": packet.playback_state,
        "heard_prefix_ref": prefix.payload_ref,
        "durable_heard_result_rejected": durable_rejected,
    }


def f16_completed_open_restart_then_close_once() -> dict[str, object]:
    session = make_session("f16")
    cortex = VoicePacketCortex(session)
    complete_one_output(cortex, packet_id="output-f16", text="Nach Neustart schließen.", start_ms=100)
    pre_restart_heard = build_heard_result(session=session, output_packets=cortex.outputs)
    checkpoint = export_packet_cortex_checkpoint(cortex)
    resumed = resume_packet_cortex(session, checkpoint, monotonic_ms=300)
    if not resumed.is_open:
        raise AssertionError("F16_PRODUCT_NEGATIVE: open checkpoint restored closed")
    if resumed.outputs[0].playback_state != "completed" or not resumed.outputs[0].commit_eligible:
        raise AssertionError("F16_PRODUCT_NEGATIVE: completed pre-restart output lost exact commit eligibility")
    post_restart_heard = build_heard_result(session=session, output_packets=resumed.outputs)
    if post_restart_heard != pre_restart_heard:
        raise AssertionError("F16_PRODUCT_NEGATIVE: completed heard-result identity drifted across restart")
    outcome_identity = session.session_causal_identity.derive(
        causal_id="causal-outcome-f16", generation=3, turn_id="turn-outcome"
    )
    close_kwargs = dict(
        turn_id="turn-close",
        monotonic_ms=350,
        outcome_causal_identity=outcome_identity,
        outcome_kind=OUTCOME_RETURNED,
        result_ref=post_restart_heard.payload_ref,
        result_sha256=post_restart_heard.payload_sha256,
        provenance_refs=("trigger7:T7-ARCH-003:F16",),
    )
    first_outcome = resumed.close_session(**close_kwargs)
    replay_outcome = resumed.close_session(**close_kwargs)
    if replay_outcome != first_outcome or replay_outcome.sha256() != first_outcome.sha256():
        raise AssertionError("F16_PRODUCT_NEGATIVE: exact duplicate close minted a different VoiceOutcome")
    close_events = [event for event in resumed.events if event.event_kind == "SESSION_CLOSE"]
    if len(close_events) != 1:
        raise AssertionError("F16_PRODUCT_NEGATIVE: duplicate exact close minted multiple SESSION_CLOSE events")
    receipt = bind_completed_reentry(
        session=session,
        outcome=first_outcome,
        output_packets=resumed.outputs,
        close_event=close_events[0],
        provenance_refs=("trigger7:T7-ARCH-003:F16",),
    )
    return {
        "id": "F16_COMPLETED_HEARD_OPEN_RESTART_THEN_CLOSE_ONCE",
        "result": "PASS",
        "voiceoutcome_id": first_outcome.outcome_id,
        "receipt_id": receipt.receipt_id,
        "session_close_count": len(close_events),
    }


def main() -> int:
    results: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for fn in (
        f15_completed_closed_restart_exact_once,
        f17_partial_restart_never_durable,
        f16_completed_open_restart_then_close_once,
    ):
        try:
            results.append(fn())
        except Exception as exc:  # deliberate falsifier boundary
            failures.append({"test": fn.__name__, "error": f"{type(exc).__name__}: {exc}"})
    payload = {
        "schema": SCHEMA,
        "result": "PASS" if not failures else "PRODUCT_NEGATIVE",
        "tests": results,
        "failures": failures,
        "classification": "PACKET_CORTEX_RESTART_REENTRY_RESEARCH_FALSIFIER_ONLY",
        "outbound_model_asr_tts_calls": 0,
        "repository_ci_credit": 0,
        "vps_target_component_credit": 0,
        "canonical_memory_write_credit": 0,
        "gwt_runtime_credit": 0,
        "jspace_runtime_credit": 0,
        "effect_credit": 0,
        "asr_runtime_credit": 0,
        "tts_runtime_credit": 0,
        "physical_audio_credit": 0,
        "whole_voice_e2e_credit": 0,
        "whole_product_credit": 0,
        "training_credit": 0,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
