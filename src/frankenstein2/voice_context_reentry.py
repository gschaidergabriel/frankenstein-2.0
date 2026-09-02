"""Trigger-7 VoiceOutcome -> bounded context integration adapter.

This module closes only the deterministic packet/context provenance seam. It does not
open audio devices, write canonical memory, mint GWT uptake, execute effects, contact
providers/models, or grant target-runtime/physical/whole-product credit.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Any

from .context_compiler import (
    CHANNEL_EVIDENCE,
    ContextCostWitness,
    ContextItem,
    ContextNeed,
    ContextView,
    compile_context,
)
from .voice_contract import VoiceOutcome, VoiceSessionCapsule
from .voice_packet_cortex import VoiceOutputPacket, VoicePacketCortex

HEARD_RESULT_SCHEMA = "FRANKENSTEIN2_VOICE_HEARD_RESULT/v1"
HEARD_RESULT_CANONICALIZATION = "F2_HEARD_RESULT_ORDERED_COMMIT_ELIGIBLE_OUTPUTS/v1"
INTEGRATION_CLASSIFICATION = (
    "VOICE_HEARD_RESULT_CONTEXT_BINDING_NOT_MEMORY_GWT_EFFECT_OR_COMPLETION_AUTHORITY"
)


class VoiceContextReentryError(ValueError):
    """Fail-closed error for the VoiceOutcome -> ContextView integration seam."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _exact_session(value: Any) -> VoiceSessionCapsule:
    if type(value) is not VoiceSessionCapsule:
        raise VoiceContextReentryError("session must be exact VoiceSessionCapsule")
    try:
        rebuilt = VoiceSessionCapsule.from_mapping(value.as_dict())
    except (TypeError, ValueError) as exc:
        raise VoiceContextReentryError(f"invalid VoiceSessionCapsule: {exc}") from exc
    if rebuilt != value or rebuilt.sha256() != value.sha256():
        raise VoiceContextReentryError("VoiceSessionCapsule failed canonical reconstruction")
    return value


def _exact_outcome(value: Any) -> VoiceOutcome:
    if type(value) is not VoiceOutcome:
        raise VoiceContextReentryError("outcome must be exact VoiceOutcome")
    try:
        rebuilt = VoiceOutcome.from_mapping(value.as_dict())
    except (TypeError, ValueError) as exc:
        raise VoiceContextReentryError(f"invalid VoiceOutcome: {exc}") from exc
    if rebuilt != value or rebuilt.sha256() != value.sha256():
        raise VoiceContextReentryError("VoiceOutcome failed canonical reconstruction")
    return value


def _exact_cortex(value: Any) -> VoicePacketCortex:
    if type(value) is not VoicePacketCortex:
        raise VoiceContextReentryError("cortex must be exact VoicePacketCortex")
    _exact_session(value.session)
    return value


def _ordered_heard_snapshots(cortex: VoicePacketCortex) -> tuple[VoiceOutputPacket, ...]:
    _exact_cortex(cortex)
    selected = tuple(packet for packet in cortex.outputs if packet.commit_eligible)
    if not selected:
        raise VoiceContextReentryError("no fully heard commit-eligible output exists")
    expected = tuple(sorted(selected, key=lambda packet: (packet.turn_id, packet.sequence, packet.packet_id)))
    if selected != expected:
        raise VoiceContextReentryError("commit-eligible output order is not canonical")
    packet_ids = [packet.packet_id for packet in selected]
    if len(set(packet_ids)) != len(packet_ids):
        raise VoiceContextReentryError("duplicate commit-eligible output packet identity")
    snapshots: list[VoiceOutputPacket] = []
    for packet in selected:
        if type(packet) is not VoiceOutputPacket:
            raise VoiceContextReentryError("cortex output must be exact VoiceOutputPacket")
        if packet.session_id != cortex.session_id:
            raise VoiceContextReentryError("output packet crossed voice session")
        if packet.playback_state != "completed" or float(packet.heard_fraction) != 1.0:
            raise VoiceContextReentryError("commit-eligible output is not exactly fully heard/completed")
        snapshots.append(replace(packet, voiceoutcome_ref=None))
    return tuple(snapshots)


@dataclass(frozen=True, slots=True)
class HeardResultIdentity:
    payload_ref: str
    payload_sha256: str
    ordered_output_packet_ids: tuple[str, ...]
    ordered_output_packet_sha256s: tuple[str, ...]
    canonicalization: str = HEARD_RESULT_CANONICALIZATION

    def as_dict(self) -> dict[str, Any]:
        return {
            "payload_ref": self.payload_ref,
            "payload_sha256": self.payload_sha256,
            "ordered_output_packet_ids": list(self.ordered_output_packet_ids),
            "ordered_output_packet_sha256s": list(self.ordered_output_packet_sha256s),
            "canonicalization": self.canonicalization,
        }


def derive_heard_result_identity(cortex: VoicePacketCortex) -> HeardResultIdentity:
    """Derive the exact ordered fully-heard result identity without granting authority."""
    cortex = _exact_cortex(cortex)
    snapshots = _ordered_heard_snapshots(cortex)
    packet_rows = [
        {
            "packet_id": packet.packet_id,
            "packet_sha256": packet.sha256(),
            "turn_id": packet.turn_id,
            "sequence": packet.sequence,
            "text_segment": packet.text_segment,
        }
        for packet in snapshots
    ]
    payload = {
        "schema": HEARD_RESULT_SCHEMA,
        "voice_session_id": cortex.session_id,
        "voice_session_sha256": cortex.session.sha256(),
        "ordered_outputs": packet_rows,
        "canonicalization": HEARD_RESULT_CANONICALIZATION,
        "classification": INTEGRATION_CLASSIFICATION,
    }
    digest = _digest(payload)
    return HeardResultIdentity(
        payload_ref="voice-heard-result:" + digest,
        payload_sha256=digest,
        ordered_output_packet_ids=tuple(row["packet_id"] for row in packet_rows),
        ordered_output_packet_sha256s=tuple(row["packet_sha256"] for row in packet_rows),
    )


@dataclass(frozen=True, slots=True)
class VoiceHeardContextBinding:
    heard_result: HeardResultIdentity
    voice_session_sha256: str
    voiceoutcome_sha256: str
    context_item_sha256: str
    context_view_sha256: str
    context_cost_witness_sha256: str
    voiceoutcome_result_matches_heard_result: bool
    classification: str = INTEGRATION_CLASSIFICATION


def bind_heard_result_to_context(
    *,
    cortex: VoicePacketCortex,
    outcome: VoiceOutcome,
    need: ContextNeed,
    cost_witness: ContextCostWitness,
    priority_bp: int = 10_000,
) -> VoiceHeardContextBinding:
    """Admit an exact fully-heard VoiceOutcome into the existing bounded ContextView path.

    The caller must first close the packet cortex using the identity returned by
    :func:`derive_heard_result_identity`. This adapter then proves that the closed
    VoiceOutcome, every commit-eligible output, the context payload and the typed cost
    witness all bind the same exact heard-result digest before delegating selection to
    the existing context compiler.
    """
    cortex = _exact_cortex(cortex)
    outcome = _exact_outcome(outcome)
    if cortex.is_open:
        raise VoiceContextReentryError("cortex must be closed before context promotion")
    session = _exact_session(cortex.session)
    if outcome.voice_session_id != session.voice_session_id:
        raise VoiceContextReentryError("VoiceOutcome voice_session_id mismatch")
    if outcome.voice_session_sha256 != session.sha256():
        raise VoiceContextReentryError("VoiceOutcome voice_session_sha256 mismatch")

    heard = derive_heard_result_identity(cortex)
    current_commit_eligible = tuple(packet for packet in cortex.outputs if packet.commit_eligible)
    if any(packet.voiceoutcome_ref != outcome.outcome_id for packet in current_commit_eligible):
        raise VoiceContextReentryError("commit-eligible output is not bound to exact VoiceOutcome")
    if outcome.result_ref != heard.payload_ref or outcome.result_sha256 != heard.payload_sha256:
        raise VoiceContextReentryError("UNBOUND_VOICEOUTCOME_RESULT")

    if type(cost_witness) is not ContextCostWitness:
        raise VoiceContextReentryError("cost_witness must be exact ContextCostWitness")
    if cost_witness.payload_sha256 != heard.payload_sha256:
        raise VoiceContextReentryError("context cost witness is not bound to exact heard-result digest")
    if type(need) is not ContextNeed:
        raise VoiceContextReentryError("need must be exact ContextNeed")

    item = ContextItem.create(
        item_id="voice-heard-context:" + heard.payload_sha256,
        channel=CHANNEL_EVIDENCE,
        payload_ref=heard.payload_ref,
        payload_sha256=heard.payload_sha256,
        source_ref=outcome.outcome_id,
        source_sha256=outcome.sha256(),
        source_generation=outcome.outcome_causal_identity.generation,
        source_classification=outcome.classification,
        priority_bp=priority_bp,
        cost_units=cost_witness.measured_cost_units,
        required=True,
        provenance_refs=(
            "trigger7:voice-heard-context-binding",
            session.voice_session_id,
            outcome.outcome_id,
        ),
        evidence_refs=heard.ordered_output_packet_ids,
    )
    try:
        view: ContextView = compile_context(need, (item,), cost_witnesses=(cost_witness,))
    except (TypeError, ValueError) as exc:
        raise VoiceContextReentryError(f"context admission rejected: {exc}") from exc
    selected = tuple(entry for entry in view.selected if entry.item_id == item.item_id)
    if len(selected) != 1:
        raise VoiceContextReentryError("heard-result context item was not selected exactly once")
    entry = selected[0]
    if entry.payload_sha256 != heard.payload_sha256:
        raise VoiceContextReentryError("selected context payload digest changed")
    if entry.cost_witness_sha256 != cost_witness.sha256():
        raise VoiceContextReentryError("selected context cost witness identity changed")

    return VoiceHeardContextBinding(
        heard_result=heard,
        voice_session_sha256=session.sha256(),
        voiceoutcome_sha256=outcome.sha256(),
        context_item_sha256=item.sha256(),
        context_view_sha256=view.sha256(),
        context_cost_witness_sha256=cost_witness.sha256(),
        voiceoutcome_result_matches_heard_result=True,
    )


__all__ = [
    "HEARD_RESULT_CANONICALIZATION",
    "HEARD_RESULT_SCHEMA",
    "HeardResultIdentity",
    "INTEGRATION_CLASSIFICATION",
    "VoiceContextReentryError",
    "VoiceHeardContextBinding",
    "bind_heard_result_to_context",
    "derive_heard_result_identity",
]
