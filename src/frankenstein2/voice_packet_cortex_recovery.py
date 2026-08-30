"""Restart/reconnect codec and event-derived latency accounting for VoicePacketCortex.

This is a deterministic Trigger-7 packet-simulation helper. It restores only packet-cortex
state bound to the exact VoiceSessionCapsule. It creates no acoustic/runtime/acceptance credit.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .voice_contract import VoiceSessionCapsule
from .voice_packet_cortex import (
    CortexEventPacket,
    PACKET_CLASSIFICATION,
    VoiceOutputPacket,
    VoicePacketCortex,
    VoicePacketCortexError,
)

CHECKPOINT_SCHEMA = "FRANKENSTEIN2_VOICE_PACKET_CORTEX_CHECKPOINT/v1"


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def export_packet_cortex_checkpoint(cortex: VoicePacketCortex) -> dict[str, Any]:
    if type(cortex) is not VoicePacketCortex:
        raise VoicePacketCortexError("cortex must be exact VoicePacketCortex")
    payload = {
        "schema": CHECKPOINT_SCHEMA,
        "classification": PACKET_CLASSIFICATION,
        "session_id": cortex.session_id,
        "session_sha256": cortex.session.sha256(),
        "presence_state": cortex.presence_state,
        "is_open": cortex.is_open,
        "event_seq": cortex._event_seq,
        "input_seen": [[key, cortex._input_seen[key]] for key in sorted(cortex._input_seen)],
        "last_input_sequence": [[key, cortex._last_input_sequence[key]] for key in sorted(cortex._last_input_sequence)],
        "final_turns": sorted(cortex._final_turns),
        "outputs": [packet.as_dict() for packet in cortex.outputs],
        "events": [event.as_dict() for event in cortex.events],
    }
    return {"payload": payload, "payload_sha256": _digest(payload)}


def resume_packet_cortex(
    session: VoiceSessionCapsule,
    checkpoint: Mapping[str, Any],
    *,
    monotonic_ms: int,
) -> VoicePacketCortex:
    if type(session) is not VoiceSessionCapsule:
        raise VoicePacketCortexError("session must be exact VoiceSessionCapsule")
    if type(monotonic_ms) is not int or monotonic_ms < 0:
        raise VoicePacketCortexError("monotonic_ms must be an integer >= 0")
    if not isinstance(checkpoint, Mapping) or set(checkpoint) != {"payload", "payload_sha256"}:
        raise VoicePacketCortexError("checkpoint envelope fields mismatch")
    payload = checkpoint["payload"]
    if not isinstance(payload, Mapping) or checkpoint["payload_sha256"] != _digest(payload):
        raise VoicePacketCortexError("checkpoint digest mismatch")
    required = {
        "schema", "classification", "session_id", "session_sha256", "presence_state", "is_open",
        "event_seq", "input_seen", "last_input_sequence", "final_turns", "outputs", "events",
    }
    if set(payload) != required:
        raise VoicePacketCortexError("checkpoint payload fields mismatch")
    if payload["schema"] != CHECKPOINT_SCHEMA or payload["classification"] != PACKET_CLASSIFICATION:
        raise VoicePacketCortexError("checkpoint schema/classification mismatch")
    if payload["session_id"] != session.voice_session_id or payload["session_sha256"] != session.sha256():
        raise VoicePacketCortexError("checkpoint session binding mismatch")
    if type(payload["is_open"]) is not bool or type(payload["event_seq"]) is not int or payload["event_seq"] < 0:
        raise VoicePacketCortexError("checkpoint state fields are invalid")

    # Construct without __init__: reentry must not mint a second SESSION_OPEN event.
    cortex = VoicePacketCortex.__new__(VoicePacketCortex)
    cortex.session = session
    cortex.session_id = session.voice_session_id
    cortex.presence_state = payload["presence_state"]
    cortex.is_open = payload["is_open"]
    cortex._event_seq = payload["event_seq"]
    try:
        cortex._input_seen = {str(key): str(value) for key, value in payload["input_seen"]}
        cortex._last_input_sequence = {str(key): int(value) for key, value in payload["last_input_sequence"]}
        cortex._final_turns = {str(value) for value in payload["final_turns"]}
        cortex._outputs = {}
        for raw in payload["outputs"]:
            packet = VoiceOutputPacket(**dict(raw))
            if packet.session_id != session.voice_session_id or packet.packet_id in cortex._outputs:
                raise VoicePacketCortexError("checkpoint output binding/uniqueness mismatch")
            cortex._outputs[packet.packet_id] = packet
        cortex._events = []
        for raw in payload["events"]:
            data = dict(raw)
            if type(data.get("packet_refs")) is list:
                data["packet_refs"] = tuple(data["packet_refs"])
            if type(data.get("memory_refs")) is list:
                data["memory_refs"] = tuple(data["memory_refs"])
            event = CortexEventPacket(**data)
            if event.session_id != session.voice_session_id:
                raise VoicePacketCortexError("checkpoint event session mismatch")
            cortex._events.append(event)
    except (TypeError, ValueError, KeyError) as exc:
        if isinstance(exc, VoicePacketCortexError):
            raise
        raise VoicePacketCortexError(f"invalid checkpoint content: {exc}") from exc
    if len(cortex._events) != cortex._event_seq:
        raise VoicePacketCortexError("checkpoint event sequence does not match event count")
    if cortex.is_open:
        cortex.emit_system_event(
            turn_id=session.intent.causal_identity.turn_id,
            monotonic_ms=monotonic_ms,
            event_kind="RESTART_REENTRY",
            detail="checkpoint restored into same VoiceSessionCapsule",
        )
    return cortex


def packet_latency_report(cortex: VoicePacketCortex, turn_id: str) -> dict[str, int | None]:
    if type(cortex) is not VoicePacketCortex or type(turn_id) is not str or not turn_id:
        raise VoicePacketCortexError("exact cortex and non-empty turn_id are required")
    marks: dict[str, int] = {}
    for event in cortex.events:
        if event.turn_id != turn_id:
            continue
        kind = event.event_kind
        if kind.startswith("SPEECH_START_"):
            marks.setdefault("speech_start_ms", event.monotonic_ms)
        if "ASR_FINAL" in kind:
            marks["asr_final_ms"] = event.monotonic_ms
        if kind == "VOICE_INTENT" and event.voice_intent not in ("WAIT", "BACKCHANNEL"):
            marks.setdefault("decision_ms", event.monotonic_ms)
        if kind == "OUTPUT_QUEUED":
            marks.setdefault("first_output_ms", event.monotonic_ms)
        if kind == "OUTPUT_STARTED":
            marks.setdefault("playback_start_ms", event.monotonic_ms)
        if kind in ("OUTPUT_COMPLETED", "OUTPUT_INTERRUPTED", "OUTPUT_CANCELLED"):
            marks["playback_terminal_ms"] = event.monotonic_ms

    def delta(start: str, end: str) -> int | None:
        if start not in marks or end not in marks:
            return None
        value = marks[end] - marks[start]
        if value < 0:
            raise VoicePacketCortexError(f"non-monotonic latency markers: {start}->{end}")
        return value

    return {
        **marks,
        "asr_from_speech_start_ms": delta("speech_start_ms", "asr_final_ms"),
        "decision_after_asr_ms": delta("asr_final_ms", "decision_ms"),
        "first_output_after_decision_ms": delta("decision_ms", "first_output_ms"),
        "playback_after_first_output_ms": delta("first_output_ms", "playback_start_ms"),
        "speech_to_playback_ms": delta("speech_start_ms", "playback_start_ms"),
    }
