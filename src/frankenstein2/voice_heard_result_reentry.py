"""Fail-closed VoiceOutcome -> heard-result/context/memory/GWT reference integration.

F2-WP-717 generation 1. This adapter is outside the accepted WP704/WP715 contracts.
It binds the exact ordered fully-heard output subject before state/memory/context promotion.
The pre-close output identity is the full canonical VoiceOutputPacket payload with only
``voiceoutcome_ref`` normalized to ``None`` to break the unavoidable result/outcome digest cycle.

No UnifiedDB write, model/provider call, GWT uptake observation, tool/effect execution,
physical-audio claim, completion claim, or whole-product credit is created here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.context_compiler import ContextCostWitness, ContextItem, ContextView
from frankenstein2.gwt_reentry_uptake_binding import GwtReentryUptakeBinding
from frankenstein2.memory_lifecycle import MemoryLifecycleState
from frankenstein2.typed_memory import TypedMemoryRecord, verify_typed_memory_binding
from frankenstein2.voice_contract import VoiceOutcome, VoiceSessionCapsule, bind_voice_outcome
from frankenstein2.voice_packet_cortex import CortexEventPacket, VoiceOutputPacket

HEARD_RESULT_SCHEMA = "FRANKENSTEIN2_VOICE_HEARD_RESULT/v1"
HEARD_PREFIX_SCHEMA = "FRANKENSTEIN2_VOICE_HEARD_PREFIX/v1"
REENTRY_RECEIPT_SCHEMA = "FRANKENSTEIN2_VOICE_HEARD_RESULT_REENTRY_RECEIPT/v1"
HEARD_RESULT_CANONICALIZATION = "F2_VOICE_HEARD_RESULT_PRE_CLOSE_FULL_PACKET_JSON_UTF8_V2"
HEARD_PREFIX_CANONICALIZATION = "F2_VOICE_HEARD_PREFIX_JSON_UTF8_V1"
RESULT_REF_PREFIX = "voice-heard-result:"
PREFIX_REF_PREFIX = "voice-heard-prefix:"
_CLASSIFICATION = "EXACT_REFERENCE_BINDING_ONLY_NOT_TRUTH_MEMORY_GWT_EFFECT_OR_COMPLETION_AUTHORITY"
_PREFIX_CLASSIFICATION = "EPHEMERAL_NEXT_TURN_CONTEXT_ONLY_NOT_DURABLE_MEMORY_OUTCOME_OR_EFFECT_AUTHORITY"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 32768
_MAX_REFS = 4096


class VoiceHeardResultReentryError(ValueError):
    """Fail-closed F2-WP-717 integration error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise VoiceHeardResultReentryError(f"{name} must be a non-empty trimmed string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise VoiceHeardResultReentryError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise VoiceHeardResultReentryError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str], *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise VoiceHeardResultReentryError(f"{name} must be an iterable of strings")
    refs = tuple(_text(name, value) for value in values)
    if not refs and not allow_empty:
        raise VoiceHeardResultReentryError(f"{name} must not be empty")
    if len(refs) > _MAX_REFS:
        raise VoiceHeardResultReentryError(f"{name} exceeds {_MAX_REFS} references")
    if len(set(refs)) != len(refs):
        raise VoiceHeardResultReentryError(f"{name} contains duplicate references")
    return refs


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _pre_close_output_material(packet: VoiceOutputPacket) -> dict[str, Any]:
    """Return the full canonical packet payload with only outcome backlink normalized.

    ``voiceoutcome_ref`` cannot participate in the heard-result digest because the resulting
    digest is itself an input to VoiceOutcome.outcome_id. Every other canonical packet field,
    including schema/classification and timing/cancellability metadata, remains identity-bearing.
    """
    if type(packet) is not VoiceOutputPacket:
        raise VoiceHeardResultReentryError("output_packets must contain exact VoiceOutputPacket values")
    if packet.playback_state != "completed" or float(packet.heard_fraction) != 1.0 or not packet.commit_eligible:
        raise VoiceHeardResultReentryError(
            "durable heard result requires fully heard completed commit-eligible output"
        )
    material = dict(packet.as_dict())
    material["voiceoutcome_ref"] = None
    return material


def _ordered_completed_packets(
    session: VoiceSessionCapsule,
    output_packets: Iterable[VoiceOutputPacket],
) -> tuple[VoiceOutputPacket, ...]:
    if type(session) is not VoiceSessionCapsule:
        raise VoiceHeardResultReentryError("session must be exact VoiceSessionCapsule")
    if isinstance(output_packets, (str, bytes)):
        raise VoiceHeardResultReentryError("output_packets must be an iterable")
    packets = tuple(output_packets)
    if not packets:
        raise VoiceHeardResultReentryError("heard result requires at least one output packet")
    for packet in packets:
        _pre_close_output_material(packet)
        if packet.session_id != session.voice_session_id:
            raise VoiceHeardResultReentryError("output packet is not bound to exact voice session")
    if len({packet.turn_id for packet in packets}) != 1:
        raise VoiceHeardResultReentryError("one heard result may bind output segments from only one turn")
    expected_order = tuple(sorted(packets, key=lambda item: (item.sequence, item.packet_id)))
    if packets != expected_order:
        raise VoiceHeardResultReentryError("output packets must be supplied in canonical sequence order")
    sequences = tuple(packet.sequence for packet in packets)
    if sequences != tuple(range(len(packets))):
        raise VoiceHeardResultReentryError("output packet sequence must be contiguous from zero")
    if len({packet.packet_id for packet in packets}) != len(packets):
        raise VoiceHeardResultReentryError("output packet ids must be unique")
    return packets


@dataclass(frozen=True, slots=True)
class HeardResultPayload:
    schema: str
    canonicalization: str
    payload_ref: str
    payload_sha256: str
    voice_session_id: str
    voice_session_sha256: str
    turn_id: str
    ordered_output_packet_ids: tuple[str, ...]
    ordered_output_material_sha256s: tuple[str, ...]
    text_segments: tuple[str, ...]
    classification: str = _CLASSIFICATION

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "canonicalization": self.canonicalization,
            "voice_session_id": self.voice_session_id,
            "voice_session_sha256": self.voice_session_sha256,
            "turn_id": self.turn_id,
            "ordered_output_packet_ids": list(self.ordered_output_packet_ids),
            "ordered_output_material_sha256s": list(self.ordered_output_material_sha256s),
            "text_segments": list(self.text_segments),
            "classification": self.classification,
        }

    def __post_init__(self) -> None:
        if self.schema != HEARD_RESULT_SCHEMA or self.canonicalization != HEARD_RESULT_CANONICALIZATION:
            raise VoiceHeardResultReentryError("heard-result schema/canonicalization mismatch")
        _text("payload_ref", self.payload_ref)
        _sha256("payload_sha256", self.payload_sha256)
        _text("voice_session_id", self.voice_session_id)
        _sha256("voice_session_sha256", self.voice_session_sha256)
        _text("turn_id", self.turn_id)
        _refs("ordered_output_packet_ids", self.ordered_output_packet_ids)
        if len(self.ordered_output_packet_ids) != len(self.ordered_output_material_sha256s):
            raise VoiceHeardResultReentryError("heard-result packet identity vectors differ in length")
        if len(self.text_segments) != len(self.ordered_output_packet_ids):
            raise VoiceHeardResultReentryError("heard-result text segment vector differs in length")
        for value in self.ordered_output_material_sha256s:
            _sha256("output material sha256", value)
        for segment in self.text_segments:
            if type(segment) is not str or len(segment) > _MAX_TEXT:
                raise VoiceHeardResultReentryError("heard-result text segment is invalid or too large")
        expected = _digest(self.identity_payload())
        if self.payload_sha256 != expected or self.payload_ref != RESULT_REF_PREFIX + expected:
            raise VoiceHeardResultReentryError("heard-result identity does not bind exact canonical payload")

    def as_dict(self) -> dict[str, Any]:
        return {"payload_ref": self.payload_ref, "payload_sha256": self.payload_sha256, **self.identity_payload()}


@dataclass(frozen=True, slots=True)
class EphemeralHeardPrefix:
    schema: str
    canonicalization: str
    payload_ref: str
    payload_sha256: str
    voice_session_id: str
    turn_id: str
    output_packet_id: str
    output_packet_sha256: str
    heard_fraction: float
    heard_prefix_text: str
    unheard_tail_text: str
    measurement_ref: str
    provenance_refs: tuple[str, ...]
    classification: str = _PREFIX_CLASSIFICATION

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "canonicalization": self.canonicalization,
            "voice_session_id": self.voice_session_id,
            "turn_id": self.turn_id,
            "output_packet_id": self.output_packet_id,
            "output_packet_sha256": self.output_packet_sha256,
            "heard_fraction": float(self.heard_fraction),
            "heard_prefix_text": self.heard_prefix_text,
            "unheard_tail_text": self.unheard_tail_text,
            "measurement_ref": self.measurement_ref,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def __post_init__(self) -> None:
        if self.schema != HEARD_PREFIX_SCHEMA or self.canonicalization != HEARD_PREFIX_CANONICALIZATION:
            raise VoiceHeardResultReentryError("heard-prefix schema/canonicalization mismatch")
        _text("payload_ref", self.payload_ref)
        _sha256("payload_sha256", self.payload_sha256)
        _text("voice_session_id", self.voice_session_id)
        _text("turn_id", self.turn_id)
        _text("output_packet_id", self.output_packet_id)
        _sha256("output_packet_sha256", self.output_packet_sha256)
        if type(self.heard_fraction) not in (int, float) or not 0.0 < float(self.heard_fraction) < 1.0:
            raise VoiceHeardResultReentryError("ephemeral heard prefix requires 0 < heard_fraction < 1")
        if type(self.heard_prefix_text) is not str or not self.heard_prefix_text:
            raise VoiceHeardResultReentryError("heard_prefix_text must be non-empty")
        if type(self.unheard_tail_text) is not str or not self.unheard_tail_text:
            raise VoiceHeardResultReentryError("interrupted prefix must preserve a non-empty unheard tail")
        _text("measurement_ref", self.measurement_ref)
        _refs("provenance_refs", self.provenance_refs)
        expected = _digest(self.identity_payload())
        if self.payload_sha256 != expected or self.payload_ref != PREFIX_REF_PREFIX + expected:
            raise VoiceHeardResultReentryError("heard-prefix identity does not bind exact canonical payload")

    def as_dict(self) -> dict[str, Any]:
        return {"payload_ref": self.payload_ref, "payload_sha256": self.payload_sha256, **self.identity_payload()}


@dataclass(frozen=True, slots=True)
class MemoryReferenceEvidence:
    memory_id: str
    lifecycle_generation: int
    lifecycle_state_sha256: str
    typed_memory_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VoiceHeardResultReentryReceipt:
    receipt_id: str
    heard_result_ref: str
    heard_result_sha256: str
    voiceoutcome_id: str
    voiceoutcome_sha256: str
    voice_session_id: str
    voice_session_sha256: str
    close_event_id: str
    ordered_output_packet_ids: tuple[str, ...]
    context_view_sha256: str | None
    context_item_id: str | None
    context_cost_witness_sha256: str | None
    memory_evidence: tuple[MemoryReferenceEvidence, ...]
    gwt_binding_id: str | None
    gwt_binding_sha256: str | None
    tool_ref_disposition: str
    provenance_refs: tuple[str, ...]
    schema: str = REENTRY_RECEIPT_SCHEMA
    classification: str = _CLASSIFICATION

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "heard_result_ref": self.heard_result_ref,
            "heard_result_sha256": self.heard_result_sha256,
            "voiceoutcome_id": self.voiceoutcome_id,
            "voiceoutcome_sha256": self.voiceoutcome_sha256,
            "voice_session_id": self.voice_session_id,
            "voice_session_sha256": self.voice_session_sha256,
            "close_event_id": self.close_event_id,
            "ordered_output_packet_ids": list(self.ordered_output_packet_ids),
            "context_view_sha256": self.context_view_sha256,
            "context_item_id": self.context_item_id,
            "context_cost_witness_sha256": self.context_cost_witness_sha256,
            "memory_evidence": [item.as_dict() for item in self.memory_evidence],
            "gwt_binding_id": self.gwt_binding_id,
            "gwt_binding_sha256": self.gwt_binding_sha256,
            "tool_ref_disposition": self.tool_ref_disposition,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
            "canonical_memory_write_credit": 0,
            "gwt_runtime_credit": 0,
            "effect_credit": 0,
            "physical_audio_credit": 0,
            "whole_system_acceptance": False,
        }

    def __post_init__(self) -> None:
        if self.schema != REENTRY_RECEIPT_SCHEMA or self.classification != _CLASSIFICATION:
            raise VoiceHeardResultReentryError("reentry receipt schema/classification mismatch")
        _text("receipt_id", self.receipt_id)
        _text("heard_result_ref", self.heard_result_ref)
        _sha256("heard_result_sha256", self.heard_result_sha256)
        _text("voiceoutcome_id", self.voiceoutcome_id)
        _sha256("voiceoutcome_sha256", self.voiceoutcome_sha256)
        _text("voice_session_id", self.voice_session_id)
        _sha256("voice_session_sha256", self.voice_session_sha256)
        _text("close_event_id", self.close_event_id)
        _refs("ordered_output_packet_ids", self.ordered_output_packet_ids)
        if self.context_view_sha256 is not None:
            _sha256("context_view_sha256", self.context_view_sha256)
            _text("context_item_id", self.context_item_id)
            _sha256("context_cost_witness_sha256", self.context_cost_witness_sha256)
        elif self.context_item_id is not None or self.context_cost_witness_sha256 is not None:
            raise VoiceHeardResultReentryError("partial context binding is forbidden")
        if (self.gwt_binding_id is None) != (self.gwt_binding_sha256 is None):
            raise VoiceHeardResultReentryError("GWT binding id/digest must both be present or absent")
        if self.gwt_binding_id is not None:
            _text("gwt_binding_id", self.gwt_binding_id)
            _sha256("gwt_binding_sha256", self.gwt_binding_sha256)
        _text("tool_ref_disposition", self.tool_ref_disposition)
        _refs("provenance_refs", self.provenance_refs)
        if self.receipt_id != "voice-reentry-receipt:" + _digest(self.identity_payload()):
            raise VoiceHeardResultReentryError("receipt_id does not bind exact reentry evidence")

    def as_dict(self) -> dict[str, Any]:
        return {"receipt_id": self.receipt_id, **self.identity_payload()}

    def sha256(self) -> str:
        return _digest(self.as_dict())


def build_heard_result(
    *,
    session: VoiceSessionCapsule,
    output_packets: Iterable[VoiceOutputPacket],
) -> HeardResultPayload:
    packets = _ordered_completed_packets(session, output_packets)
    materials = tuple(_pre_close_output_material(packet) for packet in packets)
    payload = {
        "schema": HEARD_RESULT_SCHEMA,
        "canonicalization": HEARD_RESULT_CANONICALIZATION,
        "voice_session_id": session.voice_session_id,
        "voice_session_sha256": session.sha256(),
        "turn_id": packets[0].turn_id,
        "ordered_output_packet_ids": [packet.packet_id for packet in packets],
        "ordered_output_material_sha256s": [_digest(material) for material in materials],
        "text_segments": [packet.text_segment for packet in packets],
        "classification": _CLASSIFICATION,
    }
    digest = _digest(payload)
    return HeardResultPayload(
        schema=HEARD_RESULT_SCHEMA,
        canonicalization=HEARD_RESULT_CANONICALIZATION,
        payload_ref=RESULT_REF_PREFIX + digest,
        payload_sha256=digest,
        voice_session_id=session.voice_session_id,
        voice_session_sha256=session.sha256(),
        turn_id=packets[0].turn_id,
        ordered_output_packet_ids=tuple(packet.packet_id for packet in packets),
        ordered_output_material_sha256s=tuple(_digest(material) for material in materials),
        text_segments=tuple(packet.text_segment for packet in packets),
    )


def validate_completed_heard_result(
    *,
    session: VoiceSessionCapsule,
    outcome: VoiceOutcome,
    output_packets: Iterable[VoiceOutputPacket],
    close_event: CortexEventPacket,
) -> HeardResultPayload:
    if type(outcome) is not VoiceOutcome:
        raise VoiceHeardResultReentryError("outcome must be exact VoiceOutcome")
    try:
        bind_voice_outcome(session=session, candidate=outcome)
    except ValueError as exc:
        raise VoiceHeardResultReentryError(f"VoiceOutcome session binding failed: {exc}") from exc

    # Materialize exactly once. A single-pass iterator must not bypass later backlink checks.
    if isinstance(output_packets, (str, bytes)):
        raise VoiceHeardResultReentryError("output_packets must be an iterable")
    packets = tuple(output_packets)
    payload = build_heard_result(session=session, output_packets=packets)

    if outcome.result_ref != payload.payload_ref or outcome.result_sha256 != payload.payload_sha256:
        raise VoiceHeardResultReentryError("UNBOUND_VOICEOUTCOME_RESULT")
    for packet in packets:
        if packet.voiceoutcome_ref != outcome.outcome_id:
            raise VoiceHeardResultReentryError("fully heard output is not bound back to exact VoiceOutcome")
    if type(close_event) is not CortexEventPacket or close_event.event_kind != "SESSION_CLOSE":
        raise VoiceHeardResultReentryError("exact SESSION_CLOSE event is required")
    if close_event.session_id != session.voice_session_id:
        raise VoiceHeardResultReentryError("SESSION_CLOSE event is not bound to exact voice session")
    # WP715 permits a dedicated close-transition turn_id (for example turn-close). Do not conflate
    # it with the heard output turn; exact session + result + output inventory are the causal fences.
    if tuple(close_event.packet_refs) != tuple(sorted(payload.ordered_output_packet_ids)):
        raise VoiceHeardResultReentryError("SESSION_CLOSE packet inventory does not match heard-result outputs")
    return payload


def build_interrupted_heard_prefix(
    *,
    packet: VoiceOutputPacket,
    heard_prefix_text: str,
    measurement_ref: str,
    provenance_refs: Iterable[str],
) -> EphemeralHeardPrefix:
    if type(packet) is not VoiceOutputPacket:
        raise VoiceHeardResultReentryError("packet must be exact VoiceOutputPacket")
    if packet.playback_state != "interrupted" or not 0.0 < float(packet.heard_fraction) < 1.0:
        raise VoiceHeardResultReentryError("heard-prefix binding requires an interrupted partially heard output")
    if packet.commit_eligible or packet.voiceoutcome_ref is not None:
        raise VoiceHeardResultReentryError("interrupted prefix cannot carry durable commit/outcome authority")
    if type(heard_prefix_text) is not str or not heard_prefix_text or not packet.text_segment.startswith(heard_prefix_text):
        raise VoiceHeardResultReentryError("heard prefix must be a non-empty exact prefix of output text")
    unheard = packet.text_segment[len(heard_prefix_text):]
    if not unheard:
        raise VoiceHeardResultReentryError("partially heard output must retain a non-empty unheard tail")
    refs = _refs("provenance_refs", provenance_refs)
    payload = {
        "schema": HEARD_PREFIX_SCHEMA,
        "canonicalization": HEARD_PREFIX_CANONICALIZATION,
        "voice_session_id": packet.session_id,
        "turn_id": packet.turn_id,
        "output_packet_id": packet.packet_id,
        "output_packet_sha256": packet.sha256(),
        "heard_fraction": float(packet.heard_fraction),
        "heard_prefix_text": heard_prefix_text,
        "unheard_tail_text": unheard,
        "measurement_ref": _text("measurement_ref", measurement_ref),
        "provenance_refs": list(refs),
        "classification": _PREFIX_CLASSIFICATION,
    }
    digest = _digest(payload)
    return EphemeralHeardPrefix(
        schema=HEARD_PREFIX_SCHEMA,
        canonicalization=HEARD_PREFIX_CANONICALIZATION,
        payload_ref=PREFIX_REF_PREFIX + digest,
        payload_sha256=digest,
        voice_session_id=packet.session_id,
        turn_id=packet.turn_id,
        output_packet_id=packet.packet_id,
        output_packet_sha256=packet.sha256(),
        heard_fraction=float(packet.heard_fraction),
        heard_prefix_text=heard_prefix_text,
        unheard_tail_text=unheard,
        measurement_ref=measurement_ref,
        provenance_refs=refs,
    )


def validate_context_binding(
    *,
    payload_ref: str,
    payload_sha256: str,
    source_ref: str,
    source_sha256: str,
    context_item: ContextItem,
    cost_witness: ContextCostWitness,
    context_view: ContextView,
) -> None:
    if type(context_item) is not ContextItem or type(cost_witness) is not ContextCostWitness or type(context_view) is not ContextView:
        raise VoiceHeardResultReentryError("context binding requires exact ContextItem/CostWitness/ContextView")
    if (
        context_item.payload_ref != payload_ref
        or context_item.payload_sha256 != payload_sha256
        or context_item.source_ref != source_ref
        or context_item.source_sha256 != source_sha256
    ):
        raise VoiceHeardResultReentryError("context item does not bind exact voice payload/source")
    if cost_witness.payload_sha256 != payload_sha256 or cost_witness.measured_cost_units != context_item.cost_units:
        raise VoiceHeardResultReentryError("ContextCostWitness does not bind exact voice payload/cost")
    matches = [item for item in context_view.selected if item.item_id == context_item.item_id]
    if len(matches) != 1:
        raise VoiceHeardResultReentryError("context view must select exact voice context item once")
    selected = matches[0]
    if selected.item_sha256 != context_item.sha256() or selected.payload_sha256 != payload_sha256:
        raise VoiceHeardResultReentryError("selected context item identity mismatch")
    if selected.cost_witness_sha256 != cost_witness.sha256():
        raise VoiceHeardResultReentryError("selected context cost witness identity mismatch")


def validate_memory_event_bindings(
    *,
    event: CortexEventPacket,
    bindings: Iterable[tuple[MemoryLifecycleState, TypedMemoryRecord]],
    heard_result_ref: str | None = None,
    heard_result_sha256: str | None = None,
) -> tuple[MemoryReferenceEvidence, ...]:
    if type(event) is not CortexEventPacket:
        raise VoiceHeardResultReentryError("memory event must be exact CortexEventPacket")
    if (heard_result_ref is None) != (heard_result_sha256 is None):
        raise VoiceHeardResultReentryError("partial heard-result memory payload identity is forbidden")
    if heard_result_ref is not None:
        _text("heard_result_ref", heard_result_ref)
        _sha256("heard_result_sha256", heard_result_sha256)
    pairs = tuple(bindings)
    if len(pairs) != len(event.memory_refs):
        raise VoiceHeardResultReentryError("opaque or missing memory reference binding")
    evidence: list[MemoryReferenceEvidence] = []
    for expected_ref, pair in zip(event.memory_refs, pairs):
        if type(pair) is not tuple or len(pair) != 2:
            raise VoiceHeardResultReentryError("memory binding must be (MemoryLifecycleState, TypedMemoryRecord)")
        state, record = pair
        if type(state) is not MemoryLifecycleState or type(record) is not TypedMemoryRecord:
            raise VoiceHeardResultReentryError("memory binding types are invalid")
        if expected_ref != state.memory_id or record.memory_id != state.memory_id:
            raise VoiceHeardResultReentryError("memory_ref does not equal exact lifecycle/typed-memory identity")
        if heard_result_ref is not None and (
            state.payload_ref != heard_result_ref or state.payload_sha256 != heard_result_sha256
        ):
            raise VoiceHeardResultReentryError("heard-result memory payload relation mismatch")
        try:
            verify_typed_memory_binding(record, state)
        except ValueError as exc:
            raise VoiceHeardResultReentryError(f"memory lifecycle/typed binding failed: {exc}") from exc
        evidence.append(MemoryReferenceEvidence(
            memory_id=state.memory_id,
            lifecycle_generation=state.generation,
            lifecycle_state_sha256=state.sha256(),
            typed_memory_sha256=record.sha256(),
        ))
    return tuple(evidence)


def validate_gwt_event_binding(*, event: CortexEventPacket, binding: GwtReentryUptakeBinding) -> None:
    if type(event) is not CortexEventPacket or type(binding) is not GwtReentryUptakeBinding:
        raise VoiceHeardResultReentryError("GWT event binding requires exact event/binding types")
    if event.gwt_ref != binding.binding_id:
        raise VoiceHeardResultReentryError("opaque/stale/wrong gwt_ref cannot be treated as uptake evidence")
    _sha256("gwt binding sha256", binding.sha256())


def bind_completed_reentry(
    *,
    session: VoiceSessionCapsule,
    outcome: VoiceOutcome,
    output_packets: Iterable[VoiceOutputPacket],
    close_event: CortexEventPacket,
    context_item: ContextItem | None = None,
    cost_witness: ContextCostWitness | None = None,
    context_view: ContextView | None = None,
    memory_event: CortexEventPacket | None = None,
    memory_bindings: Iterable[tuple[MemoryLifecycleState, TypedMemoryRecord]] = (),
    gwt_event: CortexEventPacket | None = None,
    gwt_binding: GwtReentryUptakeBinding | None = None,
    tool_ref_disposition: str = "NO_EFFECT_AUTHORITY_FROM_VOICE_REFERENCE",
    provenance_refs: Iterable[str] = ("trigger4:F2-WP-717",),
    existing: VoiceHeardResultReentryReceipt | None = None,
) -> VoiceHeardResultReentryReceipt:
    packets = tuple(output_packets)
    heard = validate_completed_heard_result(
        session=session, outcome=outcome, output_packets=packets, close_event=close_event
    )

    if any(value is not None for value in (context_item, cost_witness, context_view)):
        if context_item is None or cost_witness is None or context_view is None:
            raise VoiceHeardResultReentryError("partial context binding is forbidden")
        validate_context_binding(
            payload_ref=heard.payload_ref,
            payload_sha256=heard.payload_sha256,
            source_ref=outcome.outcome_id,
            source_sha256=outcome.sha256(),
            context_item=context_item,
            cost_witness=cost_witness,
            context_view=context_view,
        )
        context_fields = (context_view.sha256(), context_item.item_id, cost_witness.sha256())
    else:
        context_fields = (None, None, None)

    memory_pairs = tuple(memory_bindings)
    if memory_event is None:
        if memory_pairs:
            raise VoiceHeardResultReentryError("memory bindings require exact CortexEventPacket")
        memory_evidence: tuple[MemoryReferenceEvidence, ...] = ()
    else:
        memory_evidence = validate_memory_event_bindings(
            event=memory_event,
            bindings=memory_pairs,
            heard_result_ref=heard.payload_ref,
            heard_result_sha256=heard.payload_sha256,
        )

    if (gwt_event is None) != (gwt_binding is None):
        raise VoiceHeardResultReentryError("GWT event/binding must both be present or absent")
    if gwt_event is not None and gwt_binding is not None:
        validate_gwt_event_binding(event=gwt_event, binding=gwt_binding)
        gwt_fields = (gwt_binding.binding_id, gwt_binding.sha256())
    else:
        gwt_fields = (None, None)

    refs = _refs("provenance_refs", provenance_refs)
    payload = {
        "schema": REENTRY_RECEIPT_SCHEMA,
        "heard_result_ref": heard.payload_ref,
        "heard_result_sha256": heard.payload_sha256,
        "voiceoutcome_id": outcome.outcome_id,
        "voiceoutcome_sha256": outcome.sha256(),
        "voice_session_id": session.voice_session_id,
        "voice_session_sha256": session.sha256(),
        "close_event_id": close_event.event_id,
        "ordered_output_packet_ids": list(heard.ordered_output_packet_ids),
        "context_view_sha256": context_fields[0],
        "context_item_id": context_fields[1],
        "context_cost_witness_sha256": context_fields[2],
        "memory_evidence": [item.as_dict() for item in memory_evidence],
        "gwt_binding_id": gwt_fields[0],
        "gwt_binding_sha256": gwt_fields[1],
        "tool_ref_disposition": _text("tool_ref_disposition", tool_ref_disposition),
        "provenance_refs": list(refs),
        "classification": _CLASSIFICATION,
        "canonical_memory_write_credit": 0,
        "gwt_runtime_credit": 0,
        "effect_credit": 0,
        "physical_audio_credit": 0,
        "whole_system_acceptance": False,
    }
    candidate = VoiceHeardResultReentryReceipt(
        receipt_id="voice-reentry-receipt:" + _digest(payload),
        heard_result_ref=heard.payload_ref,
        heard_result_sha256=heard.payload_sha256,
        voiceoutcome_id=outcome.outcome_id,
        voiceoutcome_sha256=outcome.sha256(),
        voice_session_id=session.voice_session_id,
        voice_session_sha256=session.sha256(),
        close_event_id=close_event.event_id,
        ordered_output_packet_ids=heard.ordered_output_packet_ids,
        context_view_sha256=context_fields[0],
        context_item_id=context_fields[1],
        context_cost_witness_sha256=context_fields[2],
        memory_evidence=memory_evidence,
        gwt_binding_id=gwt_fields[0],
        gwt_binding_sha256=gwt_fields[1],
        tool_ref_disposition=tool_ref_disposition,
        provenance_refs=refs,
    )
    if existing is None:
        return candidate
    if type(existing) is not VoiceHeardResultReentryReceipt:
        raise VoiceHeardResultReentryError("existing receipt must be exact VoiceHeardResultReentryReceipt")
    if existing == candidate and existing.sha256() == candidate.sha256():
        return existing
    raise VoiceHeardResultReentryError("replay would rebind completed voice result to different authority")


__all__ = [
    "HEARD_PREFIX_CANONICALIZATION",
    "HEARD_PREFIX_SCHEMA",
    "HEARD_RESULT_CANONICALIZATION",
    "HEARD_RESULT_SCHEMA",
    "REENTRY_RECEIPT_SCHEMA",
    "EphemeralHeardPrefix",
    "HeardResultPayload",
    "MemoryReferenceEvidence",
    "VoiceHeardResultReentryError",
    "VoiceHeardResultReentryReceipt",
    "bind_completed_reentry",
    "build_heard_result",
    "build_interrupted_heard_prefix",
    "validate_completed_heard_result",
    "validate_context_binding",
    "validate_gwt_event_binding",
    "validate_memory_event_bindings",
]
