"""Deterministic prior-reentry -> fresh voice-turn successor projection.

F2-WP-719 generation 1. This is integration glue only. It consumes an already
validated ``VoiceHeardResultReentryReceipt`` and an exact predecessor
``VoiceSessionCapsule`` and creates a distinct fresh ``VoiceIntent`` /
``VoiceSessionCapsule`` with explicit predecessor linkage.

The projector does not write canonical memory, execute tools/effects, perform
GWT/J-Space uptake, call providers, touch audio devices, or mint completion.
GWT and memory evidence are carried only as exact reference digests.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import VoiceHeardResultReentryReceipt

FRESH_TURN_SUCCESSOR_SCHEMA = "FRANKENSTEIN2_FRESH_TURN_SUCCESSOR_PROJECTION/v1"
FRESH_TURN_SUCCESSOR_CLASSIFICATION = (
    "EXACT_PREDECESSOR_REFERENCE_ONLY_NOT_MEMORY_GWT_EFFECT_AUDIO_OR_COMPLETION_AUTHORITY"
)
PROJECTION_PREFIX = "fresh-turn-projection:"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_REFS = 4096


class FreshTurnSuccessorError(ValueError):
    """Fail-closed fresh-turn successor composition error."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise FreshTurnSuccessorError(f"{name} must be a non-empty trimmed string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise FreshTurnSuccessorError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise FreshTurnSuccessorError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise FreshTurnSuccessorError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance ref", item) for item in values)
    if len(refs) > _MAX_REFS:
        raise FreshTurnSuccessorError(f"provenance_refs exceeds {_MAX_REFS} references")
    if len(set(refs)) != len(refs):
        raise FreshTurnSuccessorError("provenance_refs contains duplicates")
    return tuple(sorted(refs))


def memory_evidence_sha256(receipt: VoiceHeardResultReentryReceipt) -> str:
    if type(receipt) is not VoiceHeardResultReentryReceipt:
        raise FreshTurnSuccessorError("receipt must be exact VoiceHeardResultReentryReceipt")
    return _digest([item.as_dict() for item in receipt.memory_evidence])


def _validate_predecessor(
    *,
    session: VoiceSessionCapsule,
    receipt: VoiceHeardResultReentryReceipt,
    receipt_sha256: str,
    expected_gwt_binding_id: str | None,
    expected_gwt_binding_sha256: str | None,
    expected_memory_evidence_sha256: str,
) -> None:
    if type(session) is not VoiceSessionCapsule:
        raise FreshTurnSuccessorError("predecessor_session must be exact VoiceSessionCapsule")
    if VoiceSessionCapsule.from_mapping(session.as_dict()) != session:
        raise FreshTurnSuccessorError("predecessor VoiceSessionCapsule failed canonical reconstruction")
    if type(receipt) is not VoiceHeardResultReentryReceipt:
        raise FreshTurnSuccessorError("predecessor_reentry must be exact VoiceHeardResultReentryReceipt")
    _sha256("predecessor_reentry_sha256", receipt_sha256)
    if receipt.sha256() != receipt_sha256:
        raise FreshTurnSuccessorError("predecessor reentry digest mismatch")
    if receipt.voice_session_id != session.voice_session_id or receipt.voice_session_sha256 != session.sha256():
        raise FreshTurnSuccessorError("predecessor reentry is not bound to exact predecessor voice session")

    if (expected_gwt_binding_id is None) != (expected_gwt_binding_sha256 is None):
        raise FreshTurnSuccessorError("expected GWT id/digest must both be present or absent")
    if receipt.gwt_binding_id is None:
        if expected_gwt_binding_id is not None:
            raise FreshTurnSuccessorError("fresh-turn request invents GWT lineage absent from predecessor")
    else:
        if expected_gwt_binding_id != receipt.gwt_binding_id:
            raise FreshTurnSuccessorError("stale/foreign GWT binding id")
        _sha256("expected_gwt_binding_sha256", expected_gwt_binding_sha256)
        if expected_gwt_binding_sha256 != receipt.gwt_binding_sha256:
            raise FreshTurnSuccessorError("stale/foreign GWT binding digest")

    _sha256("expected_memory_evidence_sha256", expected_memory_evidence_sha256)
    if expected_memory_evidence_sha256 != memory_evidence_sha256(receipt):
        raise FreshTurnSuccessorError("memory relation evidence digest mismatch")


def _validate_fresh_intent_causal(
    predecessor: VoiceSessionCapsule,
    fresh: CausalIdentity,
) -> None:
    if type(fresh) is not CausalIdentity:
        raise FreshTurnSuccessorError("fresh_intent_causal_identity must be exact CausalIdentity")
    parent = predecessor.session_causal_identity
    if fresh.parent_causal_id != parent.causal_id:
        raise FreshTurnSuccessorError("fresh intent causal parent must equal predecessor session causal_id")
    if fresh.session_id != parent.session_id:
        raise FreshTurnSuccessorError("fresh intent must preserve canonical causal session identity")
    if fresh.agent_id != parent.agent_id or fresh.task_id != parent.task_id:
        raise FreshTurnSuccessorError("fresh intent must preserve agent/task lineage")
    if fresh.generation <= parent.generation:
        raise FreshTurnSuccessorError("fresh intent generation must advance predecessor generation")
    if fresh.turn_id == parent.turn_id:
        raise FreshTurnSuccessorError("fresh intent turn_id must be distinct from predecessor turn")


@dataclass(frozen=True, slots=True)
class FreshTurnSuccessorProjection:
    projection_id: str
    predecessor_conversation_id: str
    fresh_conversation_id: str
    predecessor_reentry_receipt_id: str
    predecessor_reentry_sha256: str
    predecessor_voice_session_sha256: str
    fresh_intent_id: str
    fresh_intent_sha256: str
    fresh_voice_session_sha256: str
    fresh_turn_id: str
    gwt_binding_id: str | None
    gwt_binding_sha256: str | None
    memory_evidence_sha256: str
    tool_ref_disposition: str
    provenance_refs: tuple[str, ...]
    schema: str = FRESH_TURN_SUCCESSOR_SCHEMA
    classification: str = FRESH_TURN_SUCCESSOR_CLASSIFICATION

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "predecessor_conversation_id": self.predecessor_conversation_id,
            "fresh_conversation_id": self.fresh_conversation_id,
            "predecessor_reentry_receipt_id": self.predecessor_reentry_receipt_id,
            "predecessor_reentry_sha256": self.predecessor_reentry_sha256,
            "predecessor_voice_session_sha256": self.predecessor_voice_session_sha256,
            "fresh_intent_id": self.fresh_intent_id,
            "fresh_intent_sha256": self.fresh_intent_sha256,
            "fresh_voice_session_sha256": self.fresh_voice_session_sha256,
            "fresh_turn_id": self.fresh_turn_id,
            "gwt_binding_id": self.gwt_binding_id,
            "gwt_binding_sha256": self.gwt_binding_sha256,
            "memory_evidence_sha256": self.memory_evidence_sha256,
            "tool_ref_disposition": self.tool_ref_disposition,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
            "canonical_memory_write_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "effect_credit": 0,
            "asr_runtime_credit": 0,
            "tts_runtime_credit": 0,
            "physical_audio_credit": 0,
            "whole_voice_e2e_credit": 0,
            "whole_system_acceptance": False,
            "training_credit": 0,
        }

    def __post_init__(self) -> None:
        if self.schema != FRESH_TURN_SUCCESSOR_SCHEMA or self.classification != FRESH_TURN_SUCCESSOR_CLASSIFICATION:
            raise FreshTurnSuccessorError("fresh-turn projection schema/classification mismatch")
        _text("projection_id", self.projection_id)
        _text("predecessor_conversation_id", self.predecessor_conversation_id)
        _text("fresh_conversation_id", self.fresh_conversation_id)
        if self.predecessor_conversation_id == self.fresh_conversation_id:
            raise FreshTurnSuccessorError("fresh conversation must be distinct from predecessor")
        _text("predecessor_reentry_receipt_id", self.predecessor_reentry_receipt_id)
        _sha256("predecessor_reentry_sha256", self.predecessor_reentry_sha256)
        _sha256("predecessor_voice_session_sha256", self.predecessor_voice_session_sha256)
        _text("fresh_intent_id", self.fresh_intent_id)
        _sha256("fresh_intent_sha256", self.fresh_intent_sha256)
        _sha256("fresh_voice_session_sha256", self.fresh_voice_session_sha256)
        _text("fresh_turn_id", self.fresh_turn_id)
        if (self.gwt_binding_id is None) != (self.gwt_binding_sha256 is None):
            raise FreshTurnSuccessorError("projection GWT id/digest must both be present or absent")
        if self.gwt_binding_id is not None:
            _text("gwt_binding_id", self.gwt_binding_id)
            _sha256("gwt_binding_sha256", self.gwt_binding_sha256)
        _sha256("memory_evidence_sha256", self.memory_evidence_sha256)
        _text("tool_ref_disposition", self.tool_ref_disposition)
        if _refs(self.provenance_refs) != self.provenance_refs:
            raise FreshTurnSuccessorError("projection provenance_refs must be unique canonical lexical order")
        if self.projection_id != PROJECTION_PREFIX + _digest(self.identity_payload()):
            raise FreshTurnSuccessorError("projection_id does not bind exact successor projection")

    def as_dict(self) -> dict[str, Any]:
        return {"projection_id": self.projection_id, **self.identity_payload()}

    def sha256(self) -> str:
        return _digest(self.as_dict())


def project_fresh_turn(
    *,
    predecessor_session: VoiceSessionCapsule,
    predecessor_reentry: VoiceHeardResultReentryReceipt,
    predecessor_reentry_sha256: str,
    fresh_intent_causal_identity: CausalIdentity,
    fresh_session_causal_identity: CausalIdentity,
    input_ref: str,
    input_sha256: str,
    expected_gwt_binding_id: str | None,
    expected_gwt_binding_sha256: str | None,
    expected_memory_evidence_sha256: str,
    provenance_refs: Iterable[str] = ("trigger4:F2-WP-719",),
    existing: FreshTurnSuccessorProjection | None = None,
) -> tuple[VoiceIntent, VoiceSessionCapsule, FreshTurnSuccessorProjection]:
    """Create one deterministic, reference-only successor projection.

    Repeating the same exact request produces the same projection id. Passing an
    ``existing`` projection turns this into an explicit idempotence check: an
    exact replay is accepted, while any semantic drift fails closed.
    """
    _validate_predecessor(
        session=predecessor_session,
        receipt=predecessor_reentry,
        receipt_sha256=predecessor_reentry_sha256,
        expected_gwt_binding_id=expected_gwt_binding_id,
        expected_gwt_binding_sha256=expected_gwt_binding_sha256,
        expected_memory_evidence_sha256=expected_memory_evidence_sha256,
    )
    _validate_fresh_intent_causal(predecessor_session, fresh_intent_causal_identity)
    _sha256("input_sha256", input_sha256)
    _text("input_ref", input_ref)

    refs = _refs(tuple(provenance_refs) + (
        "predecessor-reentry:" + predecessor_reentry.receipt_id,
        "predecessor-session:" + predecessor_session.voice_session_id,
    ))
    intent = VoiceIntent.create(
        causal_identity=fresh_intent_causal_identity,
        input_ref=input_ref,
        input_sha256=input_sha256,
        provenance_refs=refs,
    )
    session = VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=fresh_session_causal_identity,
        provenance_refs=refs,
    )
    if session.voice_session_id == predecessor_session.voice_session_id:
        raise FreshTurnSuccessorError("successor VoiceSessionCapsule must be distinct")

    payload = {
        "schema": FRESH_TURN_SUCCESSOR_SCHEMA,
        "predecessor_conversation_id": predecessor_session.voice_session_id,
        "fresh_conversation_id": session.voice_session_id,
        "predecessor_reentry_receipt_id": predecessor_reentry.receipt_id,
        "predecessor_reentry_sha256": predecessor_reentry_sha256,
        "predecessor_voice_session_sha256": predecessor_session.sha256(),
        "fresh_intent_id": intent.intent_id,
        "fresh_intent_sha256": intent.sha256(),
        "fresh_voice_session_sha256": session.sha256(),
        "fresh_turn_id": fresh_intent_causal_identity.turn_id,
        "gwt_binding_id": predecessor_reentry.gwt_binding_id,
        "gwt_binding_sha256": predecessor_reentry.gwt_binding_sha256,
        "memory_evidence_sha256": memory_evidence_sha256(predecessor_reentry),
        "tool_ref_disposition": predecessor_reentry.tool_ref_disposition,
        "provenance_refs": list(refs),
        "classification": FRESH_TURN_SUCCESSOR_CLASSIFICATION,
        "canonical_memory_write_credit": 0,
        "gwt_runtime_credit": 0,
        "jspace_runtime_credit": 0,
        "effect_credit": 0,
        "asr_runtime_credit": 0,
        "tts_runtime_credit": 0,
        "physical_audio_credit": 0,
        "whole_voice_e2e_credit": 0,
        "whole_system_acceptance": False,
        "training_credit": 0,
    }
    candidate = FreshTurnSuccessorProjection(
        projection_id=PROJECTION_PREFIX + _digest(payload),
        predecessor_conversation_id=predecessor_session.voice_session_id,
        fresh_conversation_id=session.voice_session_id,
        predecessor_reentry_receipt_id=predecessor_reentry.receipt_id,
        predecessor_reentry_sha256=predecessor_reentry_sha256,
        predecessor_voice_session_sha256=predecessor_session.sha256(),
        fresh_intent_id=intent.intent_id,
        fresh_intent_sha256=intent.sha256(),
        fresh_voice_session_sha256=session.sha256(),
        fresh_turn_id=fresh_intent_causal_identity.turn_id,
        gwt_binding_id=predecessor_reentry.gwt_binding_id,
        gwt_binding_sha256=predecessor_reentry.gwt_binding_sha256,
        memory_evidence_sha256=memory_evidence_sha256(predecessor_reentry),
        tool_ref_disposition=predecessor_reentry.tool_ref_disposition,
        provenance_refs=refs,
    )
    if existing is not None:
        if type(existing) is not FreshTurnSuccessorProjection or existing != candidate:
            raise FreshTurnSuccessorError("existing successor projection conflicts with exact deterministic replay")
        return intent, session, existing
    return intent, session, candidate
