"""Restart/reconnect codec and event-derived latency accounting for VoicePacketCortex.

This is a deterministic packet-simulation helper under the WP715 Trigger-4 convergence scope.
It restores only packet-cortex state bound to the exact VoiceSessionCapsule and creates no
acoustic/runtime/acceptance credit.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Any, Mapping

from .voice_contract import VoiceOutcome, VoiceSessionCapsule
from .voice_packet_cortex import (
    CortexEventPacket,
    PACKET_CLASSIFICATION,
    VoiceOutputPacket,
    VoicePacketCortex,
    VoicePacketCortexError,
)

CHECKPOINT_SCHEMA = "FRANKENSTEIN2_VOICE_PACKET_CORTEX_CHECKPOINT/v2"


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _pairs(name: str, value: Any) -> dict[str, Any]:
    if type(value) is not list:
        raise VoicePacketCortexError(f"checkpoint {name} must be a list")
    result: dict[str, Any] = {}
    for item in value:
        if type(item) is not list or len(item) != 2:
            raise VoicePacketCortexError(f"checkpoint {name} entries must be two-item lists")
        key, item_value = item
        if type(key) is not str or not key or key != key.strip():
            raise VoicePacketCortexError(f"checkpoint {name} key is invalid")
        if key in result:
            raise VoicePacketCortexError(f"checkpoint {name} contains duplicate keys")
        result[key] = item_value
    return result


def _string_set(name: str, value: Any) -> set[str]:
    if type(value) is not list:
        raise VoicePacketCortexError(f"checkpoint {name} must be a list")
    if any(type(item) is not str or not item or item != item.strip() for item in value):
        raise VoicePacketCortexError(f"checkpoint {name} contains an invalid identifier")
    if len(set(value)) != len(value):
        raise VoicePacketCortexError(f"checkpoint {name} contains duplicates")
    return set(value)


def _validate_imported_state(payload: Mapping[str, Any]) -> None:
    """Validate imported projections before they can become live ordering/resource authority."""
    input_seen = _pairs("input_seen", payload["input_seen"])
    if len(input_seen) > VoicePacketCortex.MAX_INPUT_PACKETS:
        raise VoicePacketCortexError("checkpoint input replay capacity exceeded")
    for digest in input_seen.values():
        if type(digest) is not str or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise VoicePacketCortexError("checkpoint input_seen digest is invalid")

    last_input_sequence = _pairs("last_input_sequence", payload["last_input_sequence"])
    last_input_monotonic_ms = _pairs("last_input_monotonic_ms", payload["last_input_monotonic_ms"])
    for name, projection in (
        ("last_input_sequence", last_input_sequence),
        ("last_input_monotonic_ms", last_input_monotonic_ms),
    ):
        if any(type(value) is not int or value < 0 for value in projection.values()):
            raise VoicePacketCortexError(f"checkpoint {name} contains an invalid value")
    if set(last_input_sequence) != set(last_input_monotonic_ms):
        raise VoicePacketCortexError("checkpoint input ordering/monotonic projections disagree")
    # Accepted input sequences are contiguous from zero per turn and _input_seen never drops an
    # accepted packet. Therefore this equality is a necessary causal backing invariant.
    expected_input_count = sum(sequence + 1 for sequence in last_input_sequence.values())
    if expected_input_count != len(input_seen):
        raise VoicePacketCortexError("checkpoint input ordering projection is not backed by restored packets")
    final_turns = _string_set("final_turns", payload["final_turns"])
    if not final_turns.issubset(last_input_sequence):
        raise VoicePacketCortexError("checkpoint final_turn projection is not backed by input ordering state")

    if type(payload["outputs"]) is not list:
        raise VoicePacketCortexError("checkpoint outputs must be a list")
    if len(payload["outputs"]) > VoicePacketCortex.MAX_OUTPUT_PACKETS:
        raise VoicePacketCortexError("checkpoint output packet capacity exceeded")
    last_output_sequence = _pairs("last_output_sequence", payload["last_output_sequence"])
    if any(type(value) is not int or value < 0 for value in last_output_sequence.values()):
        raise VoicePacketCortexError("checkpoint last_output_sequence contains an invalid value")

    if type(payload["events"]) is not list:
        raise VoicePacketCortexError("checkpoint events must be a list")
    if len(payload["events"]) > VoicePacketCortex.MAX_EVENTS:
        raise VoicePacketCortexError("checkpoint event capacity exceeded")

    active_tools = _pairs("active_tools", payload["active_tools"])
    if any(type(turn_id) is not str or not turn_id or turn_id != turn_id.strip() for turn_id in active_tools.values()):
        raise VoicePacketCortexError("checkpoint active_tools contains an invalid turn binding")
    cancelled_tools = _string_set("cancelled_tools", payload["cancelled_tools"])
    if set(active_tools) & cancelled_tools:
        raise VoicePacketCortexError("checkpoint tool projections overlap active and cancelled state")
    if len(active_tools) + len(cancelled_tools) > VoicePacketCortex.MAX_TOOL_REFS:
        raise VoicePacketCortexError("checkpoint tool ownership capacity exceeded")


def _validate_restored_output_projection(cortex: VoicePacketCortex) -> None:
    sequences_by_turn: dict[str, set[int]] = {}
    for packet in cortex._outputs.values():
        sequences = sequences_by_turn.setdefault(packet.turn_id, set())
        if packet.sequence in sequences:
            raise VoicePacketCortexError("checkpoint output sequence projection contains duplicates")
        sequences.add(packet.sequence)
    expected_last: dict[str, int] = {}
    for turn_id, sequences in sequences_by_turn.items():
        highest = max(sequences)
        if sequences != set(range(highest + 1)):
            raise VoicePacketCortexError("checkpoint output sequence projection contains a gap")
        expected_last[turn_id] = highest
    if cortex._last_output_sequence != expected_last:
        raise VoicePacketCortexError("checkpoint last_output_sequence is not backed by restored outputs")


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
        "last_input_monotonic_ms": [
            [key, cortex._last_input_monotonic_ms[key]] for key in sorted(cortex._last_input_monotonic_ms)
        ],
        "last_output_sequence": [
            [key, cortex._last_output_sequence[key]] for key in sorted(cortex._last_output_sequence)
        ],
        "final_turns": sorted(cortex._final_turns),
        "outputs": [packet.as_dict() for packet in cortex.outputs],
        "events": [event.as_dict() for event in cortex.events],
        "active_tools": [[key, cortex._active_tools[key]] for key in sorted(cortex._active_tools)],
        "cancelled_tools": sorted(cortex._cancelled_tools),
        "closed_outcome": cortex._closed_outcome.as_dict() if cortex._closed_outcome is not None else None,
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
        "event_seq", "input_seen", "last_input_sequence", "last_input_monotonic_ms",
        "last_output_sequence", "final_turns", "outputs", "events", "active_tools",
        "cancelled_tools", "closed_outcome",
    }
    if set(payload) != required:
        raise VoicePacketCortexError("checkpoint payload fields mismatch")
    if payload["schema"] != CHECKPOINT_SCHEMA or payload["classification"] != PACKET_CLASSIFICATION:
        raise VoicePacketCortexError("checkpoint schema/classification mismatch")
    if payload["session_id"] != session.voice_session_id or payload["session_sha256"] != session.sha256():
        raise VoicePacketCortexError("checkpoint session binding mismatch")
    if type(payload["is_open"]) is not bool or type(payload["event_seq"]) is not int or payload["event_seq"] < 0:
        raise VoicePacketCortexError("checkpoint state fields are invalid")
    _validate_imported_state(payload)

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
        cortex._last_input_monotonic_ms = {
            str(key): int(value) for key, value in payload["last_input_monotonic_ms"]
        }
        cortex._last_output_sequence = {
            str(key): int(value) for key, value in payload["last_output_sequence"]
        }
        cortex._final_turns = {str(value) for value in payload["final_turns"]}
        cortex._outputs = {}
        for raw in payload["outputs"]:
            packet = VoiceOutputPacket(**dict(raw))
            if packet.session_id != session.voice_session_id or packet.packet_id in cortex._outputs:
                raise VoicePacketCortexError("checkpoint output binding/uniqueness mismatch")
            cortex._outputs[packet.packet_id] = packet
        _validate_restored_output_projection(cortex)
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
        active_tools = {str(key): str(value) for key, value in payload["active_tools"]}
        cortex._active_tools = {}
        cortex._cancelled_tools = {str(value) for value in payload["cancelled_tools"]} | set(active_tools)
        raw_outcome = payload["closed_outcome"]
        cortex._closed_outcome = VoiceOutcome.from_mapping(raw_outcome) if raw_outcome is not None else None
        cortex._closed_signature = None
    except (TypeError, ValueError, KeyError) as exc:
        if isinstance(exc, VoicePacketCortexError):
            raise
        raise VoicePacketCortexError(f"invalid checkpoint content: {exc}") from exc
    if len(cortex._events) != cortex._event_seq:
        raise VoicePacketCortexError("checkpoint event sequence does not match event count")
    if cortex.is_open and cortex._closed_outcome is not None:
        raise VoicePacketCortexError("open checkpoint cannot contain terminal outcome")
    if not cortex.is_open:
        if cortex._closed_outcome is None:
            raise VoicePacketCortexError("closed checkpoint requires terminal outcome")
        close_events = [event for event in cortex._events if event.event_kind == "SESSION_CLOSE"]
        if len(close_events) != 1:
            raise VoicePacketCortexError("closed checkpoint requires exactly one SESSION_CLOSE event")
        close_event = close_events[0]
        outcome = cortex._closed_outcome
        expected_close_packet_refs = tuple(sorted(
            packet.packet_id for packet in cortex._outputs.values() if packet.commit_eligible
        ))
        if close_event.packet_refs != expected_close_packet_refs:
            raise VoicePacketCortexError("closed checkpoint SESSION_CLOSE packet_refs mismatch restored commit-eligible outputs")
        for packet in cortex._outputs.values():
            expected_outcome_ref = outcome.outcome_id if packet.commit_eligible else None
            if packet.voiceoutcome_ref != expected_outcome_ref:
                raise VoicePacketCortexError("closed checkpoint output VoiceOutcome binding mismatch")
        expected_close_detail = (
            f"voiceoutcome={outcome.outcome_id};commit_eligible_outputs={len(expected_close_packet_refs)}"
        )
        if close_event.detail != expected_close_detail:
            raise VoicePacketCortexError("closed checkpoint SESSION_CLOSE detail mismatch terminal outcome")
        cortex._closed_signature = (
            close_event.turn_id,
            close_event.monotonic_ms,
            outcome.outcome_causal_identity,
            outcome.outcome_kind,
            outcome.result_ref,
            outcome.result_sha256,
            outcome.provenance_refs,
        )
    if cortex.is_open:
        restart_terminalized: list[str] = []
        for packet_id, packet in tuple(cortex._outputs.items()):
            if packet.playback_state not in ("queued", "started", "heard"):
                continue
            if monotonic_ms < packet.monotonic_ms:
                raise VoicePacketCortexError(
                    "restart monotonic_ms precedes restored nonterminal output state"
                )
            terminal_state = "cancelled" if packet.playback_state == "queued" else "interrupted"
            cortex._outputs[packet_id] = replace(
                packet,
                monotonic_ms=monotonic_ms,
                playback_state=terminal_state,
                interruption_ms=monotonic_ms,
                commit_eligible=False,
                voiceoutcome_ref=None,
            )
            restart_terminalized.append(packet_id)
        cortex.emit_system_event(
            turn_id=session.intent.causal_identity.turn_id,
            monotonic_ms=monotonic_ms,
            event_kind="RESTART_REENTRY",
            packet_refs=tuple(sorted(restart_terminalized)),
            detail=(
                "checkpoint restored into same VoiceSessionCapsule; active tool ownership fenced stale; "
                f"nonterminal playback terminalized={len(restart_terminalized)}"
            ),
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
