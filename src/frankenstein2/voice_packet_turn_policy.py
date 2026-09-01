"""Deterministic policy binding for the existing packet-only voice cortex.

WP720 scope is intentionally narrow: this module does not create a second turn FSM,
state store, output queue, cancellation authority, VoiceIntent authority, model route,
or acoustic runtime. It is a compatibility adapter over the existing
``VoicePacketCortex`` event fabric and must fail closed if an accepted source event
already carries an authoritative policy decision.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

POLICY_SCHEMA = "FRANKENSTEIN2_PACKET_TURN_POLICY/v1"
POLICY_CLASSIFICATION = "PACKET_POLICY_BINDING_ONLY_NOT_ACOUSTIC_OR_MODEL_RUNTIME"
_HOLD_INTENTS = frozenset(("WAIT", "BACKCHANNEL"))


class PacketTurnPolicyError(ValueError):
    """Fail-closed policy-binding validation error."""


def _atom(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise PacketTurnPolicyError(f"{name} must be a non-empty trimmed string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PacketTurnPolicyError(f"{name} contains control characters")
    return value


def _nonnegative(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PacketTurnPolicyError(f"{name} must be an integer >= 0")
    return value


def _refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise PacketTurnPolicyError(f"{name} must be a non-empty immutable tuple")
    for item in value:
        _atom(f"{name} item", item)
    if len(set(value)) != len(value):
        raise PacketTurnPolicyError(f"{name} must not contain duplicates")
    return value


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _detail_field(detail: str, name: str) -> str | None:
    prefix = name + "="
    for atom in detail.split(";"):
        if atom.startswith(prefix):
            return atom[len(prefix):]
    return None


@dataclass(frozen=True, slots=True)
class PacketTurnPolicy:
    """One provenance-bound policy dimension for a non-final HOLD input.

    ``hold_intent`` is deliberately restricted to WAIT/BACKCHANNEL. Mandatory
    user barge-in cancellation remains owned by ``VoicePacketCortex.accept_input``
    and cannot be disabled or weakened by this policy object.
    """

    policy_id: str
    hold_intent: str
    provenance_refs: tuple[str, ...]
    schema: str = POLICY_SCHEMA
    classification: str = POLICY_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != POLICY_SCHEMA or self.classification != POLICY_CLASSIFICATION:
            raise PacketTurnPolicyError("policy schema/classification mismatch")
        _atom("policy_id", self.policy_id)
        if self.hold_intent not in _HOLD_INTENTS:
            raise PacketTurnPolicyError("hold_intent must be WAIT or BACKCHANNEL")
        _refs("provenance_refs", self.provenance_refs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "hold_intent": self.hold_intent,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def apply_packet_turn_policy(
    cortex: Any,
    accepted_input_event: Any,
    policy: PacketTurnPolicy,
    *,
    monotonic_ms: int | None = None,
) -> Any:
    """Emit one policy-selected intent for an exact accepted HOLD input event.

    The accepted event must be the *same in-memory event object* already present in
    this cortex. Equality with a reconstructed/foreign event is insufficient. The
    existing cortex event history is the replay/conflict fence: an exact replay is
    idempotent and a conflicting second policy fails closed. No second persistent
    state authority is introduced.
    """

    from .voice_packet_cortex import CortexEventPacket, VoicePacketCortex

    if type(cortex) is not VoicePacketCortex:
        raise PacketTurnPolicyError("cortex must be exact VoicePacketCortex")
    if type(accepted_input_event) is not CortexEventPacket:
        raise PacketTurnPolicyError("accepted_input_event must be exact CortexEventPacket")
    if type(policy) is not PacketTurnPolicy:
        raise PacketTurnPolicyError("policy must be exact PacketTurnPolicy")
    if not cortex.is_open:
        raise PacketTurnPolicyError("cannot apply policy to a closed cortex")
    if not any(candidate is accepted_input_event for candidate in cortex.events):
        raise PacketTurnPolicyError("input event was not admitted by this cortex instance")
    if accepted_input_event.session_id != cortex.session_id:
        raise PacketTurnPolicyError("accepted input event session mismatch")
    if "ASR_PARTIAL" not in accepted_input_event.event_kind:
        raise PacketTurnPolicyError("turn policy requires an accepted non-final ASR_PARTIAL event")
    if _detail_field(accepted_input_event.detail, "endpoint") != "HOLD":
        raise PacketTurnPolicyError("turn policy requires endpoint=HOLD")
    if len(accepted_input_event.packet_refs) != 1:
        raise PacketTurnPolicyError("turn policy requires exactly one accepted input packet ref")

    decision_ms = accepted_input_event.monotonic_ms if monotonic_ms is None else _nonnegative(
        "monotonic_ms", monotonic_ms
    )
    if decision_ms < accepted_input_event.monotonic_ms:
        raise PacketTurnPolicyError("policy decision cannot precede its accepted input event")

    policy_sha = policy.sha256()
    for event in cortex.events:
        if event.event_kind != "VOICE_INTENT":
            continue
        if _detail_field(event.detail, "source_event_id") != accepted_input_event.event_id:
            continue
        prior_policy_sha = _detail_field(event.detail, "policy_sha256")
        prior_policy_id = _detail_field(event.detail, "packet_turn_policy")
        if (
            prior_policy_sha == policy_sha
            and prior_policy_id == policy.policy_id
            and event.voice_intent == policy.hold_intent
        ):
            return event
        raise PacketTurnPolicyError("accepted HOLD event already has a different authoritative policy decision")

    return cortex.emit_intent(
        turn_id=accepted_input_event.turn_id,
        monotonic_ms=decision_ms,
        voice_intent=policy.hold_intent,
        detail=(
            f"packet_turn_policy={policy.policy_id};"
            f"policy_sha256={policy_sha};"
            f"source_event_id={accepted_input_event.event_id}"
        ),
    )
