"""Stateless policy binding for the existing VoicePacketCortex turn-control boundary.

This module does not create a second cortex, FSM, output/cancellation authority, acoustic runtime,
or product acceptance.  It supplies one immutable, provenance-bound policy value and routes the
result through VoicePacketCortex.emit_intent after verifying the exact input packet is already in
the cortex's accepted history.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from .voice_packet_cortex import VoiceInputPacket, VoicePacketCortex, VoicePacketCortexError

POLICY_SCHEMA = "FRANKENSTEIN2_PACKET_TURN_POLICY/v1"
POLICY_CLASSIFICATION = "POLICY_BINDING_ONLY_NOT_SECOND_CORTEX_OR_RUNTIME_CREDIT"
_HOLD_PARTIAL_INTENTS = frozenset(("WAIT", "BACKCHANNEL"))


def _atom(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise VoicePacketCortexError(f"{name} must be a non-empty trimmed string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise VoicePacketCortexError(f"{name} contains control characters")
    return value


def _refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise VoicePacketCortexError(f"{name} must be a non-empty immutable tuple")
    for item in value:
        _atom(f"{name} item", item)
    if len(set(value)) != len(value):
        raise VoicePacketCortexError(f"{name} must not contain duplicates")
    return value


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PacketTurnPolicy:
    """One immutable policy dimension for a non-final HOLD packet.

    Final/END packets remain ANSWER and UNKNOWN endpoints remain conservative WAIT.  Therefore
    changing ``hold_partial_intent`` is the only admitted behavioral intervention in this object.
    """

    policy_id: str
    hold_partial_intent: str
    provenance_refs: tuple[str, ...]
    schema: str = POLICY_SCHEMA
    classification: str = POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != POLICY_SCHEMA or self.classification != POLICY_CLASSIFICATION:
            raise VoicePacketCortexError("turn policy schema/classification mismatch")
        _atom("policy_id", self.policy_id)
        _refs("provenance_refs", self.provenance_refs)
        if self.hold_partial_intent not in _HOLD_PARTIAL_INTENTS:
            raise VoicePacketCortexError("hold_partial_intent must be WAIT or BACKCHANNEL")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "hold_partial_intent": self.hold_partial_intent,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def select_packet_turn_intent(packet: VoiceInputPacket, policy: PacketTurnPolicy) -> str:
    """Pure policy decision over one validated packet; no state/effect authority."""
    if type(packet) is not VoiceInputPacket:
        raise VoicePacketCortexError("packet must be exact VoiceInputPacket")
    if type(policy) is not PacketTurnPolicy:
        raise VoicePacketCortexError("policy must be exact PacketTurnPolicy")
    if packet.fault_flags:
        raise VoicePacketCortexError("fault-injected packet cannot drive a policy intent")
    if packet.is_final or packet.endpoint_decision == "END":
        return "ANSWER"
    if packet.endpoint_decision == "HOLD":
        return policy.hold_partial_intent
    return "WAIT"


def bind_packet_turn_policy(
    cortex: VoicePacketCortex,
    packet: VoiceInputPacket,
    policy: PacketTurnPolicy,
    *,
    monotonic_ms: int,
):
    """Bind a policy decision to the existing cortex's VOICE_INTENT event boundary.

    The exact packet must already have been accepted by ``cortex``.  This function owns no
    cancellation, output, tool, memory, GWT, effect, or persistence state; it delegates emission
    to the existing ``VoicePacketCortex.emit_intent`` authority.
    """
    if type(cortex) is not VoicePacketCortex:
        raise VoicePacketCortexError("cortex must be exact VoicePacketCortex")
    if type(packet) is not VoiceInputPacket:
        raise VoicePacketCortexError("packet must be exact VoiceInputPacket")
    if type(policy) is not PacketTurnPolicy:
        raise VoicePacketCortexError("policy must be exact PacketTurnPolicy")
    if type(monotonic_ms) is not int or monotonic_ms < packet.monotonic_ms:
        raise VoicePacketCortexError("policy intent monotonic_ms must be >= packet monotonic_ms")
    if packet.session_id != cortex.session_id:
        raise VoicePacketCortexError("policy packet session mismatch")
    if cortex._input_seen.get(packet.packet_id) != packet.sha256():
        raise VoicePacketCortexError("policy packet is not the exact accepted cortex input")

    intent = select_packet_turn_intent(packet, policy)
    return cortex.emit_intent(
        turn_id=packet.turn_id,
        monotonic_ms=monotonic_ms,
        voice_intent=intent,
        detail=(
            f"turn_policy={policy.policy_id};turn_policy_sha256={policy.sha256()};"
            f"packet_sha256={packet.sha256()};policy_dimension=hold_partial_intent"
        ),
    )
