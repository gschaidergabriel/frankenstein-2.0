"""F2-WP-704 deterministic VoiceIntent -> VoiceSessionCapsule -> VoiceOutcome contracts.

This module is an identity/provenance boundary only. Voice is an interface organ of the
same Frankenstein 2.0 causal lineage, not a second entity. Nothing here opens audio I/O,
connects a provider/model, decides semantic success, writes UnifiedDB, authorizes an
effect/completion, or creates target-runtime/GRID/GWT/J-Space credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .causal_identity import CausalIdentity

VOICE_INTENT_SCHEMA = "FRANKENSTEIN2_VOICE_INTENT/v1"
VOICE_SESSION_SCHEMA = "FRANKENSTEIN2_VOICE_SESSION_CAPSULE/v1"
VOICE_OUTCOME_SCHEMA = "FRANKENSTEIN2_VOICE_OUTCOME/v1"
VOICE_CLASSIFICATION = "VOICE_EVIDENCE_ONLY_NOT_IDENTITY_EFFECT_OR_COMPLETION_AUTHORITY"

OUTCOME_RETURNED = "RETURNED"
OUTCOME_INTERRUPTED = "INTERRUPTED"
OUTCOME_ENDED = "ENDED"
OUTCOME_ERROR = "ERROR"
OUTCOME_UNKNOWN = "UNKNOWN"
_ALLOWED_OUTCOMES = frozenset(
    (OUTCOME_RETURNED, OUTCOME_INTERRUPTED, OUTCOME_ENDED, OUTCOME_ERROR, OUTCOME_UNKNOWN)
)

_MAX_IDENTIFIER_LENGTH = 512
_MAX_REF_COUNT = 4096
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class VoiceContractError(ValueError):
    """Raised when a voice-loop identity/provenance contract fails closed."""


def _identifier(name: str, value: Any) -> str:
    if type(value) is not str:
        raise VoiceContractError(f"{name} must be a string")
    if not value or value != value.strip():
        raise VoiceContractError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise VoiceContractError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise VoiceContractError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise VoiceContractError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, value: Any, *, require_nonempty: bool = True) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise VoiceContractError(f"{name} must be an immutable tuple")
    if len(value) > _MAX_REF_COUNT:
        raise VoiceContractError(f"{name} exceeds {_MAX_REF_COUNT} references")
    for item in value:
        _identifier(f"{name} item", item)
    if len(set(value)) != len(value):
        raise VoiceContractError(f"{name} must not contain duplicates")
    if value != tuple(sorted(value)):
        raise VoiceContractError(f"{name} must be in canonical lexical order")
    if require_nonempty and not value:
        raise VoiceContractError(f"{name} must contain at least one explicit reference")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _exact_causal(name: str, value: Any) -> CausalIdentity:
    if type(value) is not CausalIdentity:
        raise VoiceContractError(f"{name} must be exact concrete CausalIdentity")
    # Reconstruct to force consumer-boundary validation rather than trusting an object alone.
    try:
        rebuilt = CausalIdentity.from_mapping(value.as_dict())
    except (TypeError, ValueError) as exc:
        raise VoiceContractError(f"invalid {name}: {exc}") from exc
    if rebuilt != value or rebuilt.sha256() != value.sha256():
        raise VoiceContractError(f"{name} failed canonical reconstruction")
    return value


def _same_entity_lineage(parent: CausalIdentity, child: CausalIdentity, *, label: str) -> None:
    if child.parent_causal_id != parent.causal_id:
        raise VoiceContractError(f"{label}.parent_causal_id must equal parent causal_id")
    if child.generation <= parent.generation:
        raise VoiceContractError(f"{label} generation must advance")
    if child.session_id != parent.session_id:
        raise VoiceContractError(f"{label} session_id must remain on the same causal session")
    if child.agent_id != parent.agent_id:
        raise VoiceContractError(f"{label} agent_id must remain the same Frankenstein identity")
    if child.task_id != parent.task_id:
        raise VoiceContractError(f"{label} task_id must remain on the same task lineage")


@dataclass(frozen=True, slots=True)
class VoiceIntent:
    schema: str
    intent_id: str
    causal_identity: CausalIdentity
    causal_identity_sha256: str
    input_ref: str
    input_sha256: str
    provenance_refs: tuple[str, ...]
    classification: str = VOICE_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != VOICE_INTENT_SCHEMA:
            raise VoiceContractError("voice intent schema mismatch")
        if self.classification != VOICE_CLASSIFICATION:
            raise VoiceContractError("voice intent classification mismatch")
        _exact_causal("causal_identity", self.causal_identity)
        _sha256("causal_identity_sha256", self.causal_identity_sha256)
        if self.causal_identity_sha256 != self.causal_identity.sha256():
            raise VoiceContractError("causal_identity_sha256 does not match causal_identity")
        _identifier("input_ref", self.input_ref)
        _sha256("input_sha256", self.input_sha256)
        _refs("provenance_refs", self.provenance_refs)
        _identifier("intent_id", self.intent_id)
        if self.intent_id != self.expected_intent_id():
            raise VoiceContractError("intent_id does not bind exact voice intent content")

    @classmethod
    def create(
        cls,
        *,
        causal_identity: CausalIdentity,
        input_ref: str,
        input_sha256: str,
        provenance_refs: tuple[str, ...],
    ) -> "VoiceIntent":
        _exact_causal("causal_identity", causal_identity)
        causal_digest = causal_identity.sha256()
        payload = {
            "schema": VOICE_INTENT_SCHEMA,
            "causal_identity": causal_identity.as_dict(),
            "causal_identity_sha256": causal_digest,
            "input_ref": input_ref,
            "input_sha256": input_sha256,
            "provenance_refs": list(provenance_refs),
            "classification": VOICE_CLASSIFICATION,
        }
        return cls(intent_id="voice-intent:" + _digest(payload), **payload)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "VoiceIntent":
        expected = {
            "schema", "intent_id", "causal_identity", "causal_identity_sha256", "input_ref",
            "input_sha256", "provenance_refs", "classification",
        }
        if not isinstance(value, Mapping) or set(value.keys()) != expected:
            raise VoiceContractError("voice intent fields must match schema exactly")
        try:
            causal = CausalIdentity.from_mapping(value["causal_identity"])
        except (TypeError, ValueError) as exc:
            raise VoiceContractError(f"invalid voice intent causal identity: {exc}") from exc
        return cls(
            schema=value["schema"], intent_id=value["intent_id"], causal_identity=causal,
            causal_identity_sha256=value["causal_identity_sha256"], input_ref=value["input_ref"],
            input_sha256=value["input_sha256"],
            provenance_refs=tuple(value["provenance_refs"]) if type(value["provenance_refs"]) is list else value["provenance_refs"],
            classification=value["classification"],
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "causal_identity": self.causal_identity.as_dict(),
            "causal_identity_sha256": self.causal_identity_sha256,
            "input_ref": self.input_ref,
            "input_sha256": self.input_sha256,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def expected_intent_id(self) -> str:
        return "voice-intent:" + _digest(self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {"intent_id": self.intent_id, **self.identity_payload()}

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class VoiceSessionCapsule:
    schema: str
    voice_session_id: str
    intent: VoiceIntent
    intent_sha256: str
    session_causal_identity: CausalIdentity
    session_causal_identity_sha256: str
    provenance_refs: tuple[str, ...]
    classification: str = VOICE_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != VOICE_SESSION_SCHEMA:
            raise VoiceContractError("voice session schema mismatch")
        if self.classification != VOICE_CLASSIFICATION:
            raise VoiceContractError("voice session classification mismatch")
        if type(self.intent) is not VoiceIntent:
            raise VoiceContractError("intent must be exact concrete VoiceIntent")
        if VoiceIntent.from_mapping(self.intent.as_dict()) != self.intent:
            raise VoiceContractError("intent failed canonical reconstruction")
        _sha256("intent_sha256", self.intent_sha256)
        if self.intent_sha256 != self.intent.sha256():
            raise VoiceContractError("intent_sha256 does not match exact intent")
        _exact_causal("session_causal_identity", self.session_causal_identity)
        _same_entity_lineage(self.intent.causal_identity, self.session_causal_identity, label="session_causal_identity")
        _sha256("session_causal_identity_sha256", self.session_causal_identity_sha256)
        if self.session_causal_identity_sha256 != self.session_causal_identity.sha256():
            raise VoiceContractError("session causal digest mismatch")
        _refs("provenance_refs", self.provenance_refs)
        _identifier("voice_session_id", self.voice_session_id)
        if self.voice_session_id != self.expected_voice_session_id():
            raise VoiceContractError("voice_session_id does not bind exact session content")

    @classmethod
    def create(
        cls,
        *,
        intent: VoiceIntent,
        session_causal_identity: CausalIdentity,
        provenance_refs: tuple[str, ...],
    ) -> "VoiceSessionCapsule":
        if type(intent) is not VoiceIntent:
            raise VoiceContractError("intent must be exact concrete VoiceIntent")
        _exact_causal("session_causal_identity", session_causal_identity)
        payload = {
            "schema": VOICE_SESSION_SCHEMA,
            "intent": intent,
            "intent_sha256": intent.sha256(),
            "session_causal_identity": session_causal_identity,
            "session_causal_identity_sha256": session_causal_identity.sha256(),
            "provenance_refs": provenance_refs,
            "classification": VOICE_CLASSIFICATION,
        }
        provisional = cls(voice_session_id="placeholder", **payload)
        return cls(voice_session_id=provisional.expected_voice_session_id(), **payload)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "VoiceSessionCapsule":
        expected = {
            "schema", "voice_session_id", "intent", "intent_sha256", "session_causal_identity",
            "session_causal_identity_sha256", "provenance_refs", "classification",
        }
        if not isinstance(value, Mapping) or set(value.keys()) != expected:
            raise VoiceContractError("voice session fields must match schema exactly")
        return cls(
            schema=value["schema"], voice_session_id=value["voice_session_id"],
            intent=VoiceIntent.from_mapping(value["intent"]), intent_sha256=value["intent_sha256"],
            session_causal_identity=CausalIdentity.from_mapping(value["session_causal_identity"]),
            session_causal_identity_sha256=value["session_causal_identity_sha256"],
            provenance_refs=tuple(value["provenance_refs"]) if type(value["provenance_refs"]) is list else value["provenance_refs"],
            classification=value["classification"],
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "intent": self.intent.as_dict(),
            "intent_sha256": self.intent_sha256,
            "session_causal_identity": self.session_causal_identity.as_dict(),
            "session_causal_identity_sha256": self.session_causal_identity_sha256,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def expected_voice_session_id(self) -> str:
        return "voice-session:" + _digest(self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {"voice_session_id": self.voice_session_id, **self.identity_payload()}

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class VoiceOutcome:
    schema: str
    outcome_id: str
    voice_session_id: str
    voice_session_sha256: str
    outcome_causal_identity: CausalIdentity
    outcome_causal_identity_sha256: str
    outcome_kind: str
    result_ref: str | None
    result_sha256: str | None
    provenance_refs: tuple[str, ...]
    classification: str = VOICE_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != VOICE_OUTCOME_SCHEMA:
            raise VoiceContractError("voice outcome schema mismatch")
        if self.classification != VOICE_CLASSIFICATION:
            raise VoiceContractError("voice outcome classification mismatch")
        _identifier("voice_session_id", self.voice_session_id)
        _sha256("voice_session_sha256", self.voice_session_sha256)
        _exact_causal("outcome_causal_identity", self.outcome_causal_identity)
        _sha256("outcome_causal_identity_sha256", self.outcome_causal_identity_sha256)
        if self.outcome_causal_identity_sha256 != self.outcome_causal_identity.sha256():
            raise VoiceContractError("outcome causal digest mismatch")
        if self.outcome_kind not in _ALLOWED_OUTCOMES:
            raise VoiceContractError("outcome_kind is not admitted")
        if (self.result_ref is None) != (self.result_sha256 is None):
            raise VoiceContractError("result_ref and result_sha256 must both be present or absent")
        if self.result_ref is not None:
            _identifier("result_ref", self.result_ref)
            _sha256("result_sha256", self.result_sha256)
        _refs("provenance_refs", self.provenance_refs)
        _identifier("outcome_id", self.outcome_id)
        if self.outcome_id != self.expected_outcome_id():
            raise VoiceContractError("outcome_id does not bind exact outcome content")

    @classmethod
    def create(
        cls,
        *,
        session: VoiceSessionCapsule,
        outcome_causal_identity: CausalIdentity,
        outcome_kind: str,
        result_ref: str | None,
        result_sha256: str | None,
        provenance_refs: tuple[str, ...],
    ) -> "VoiceOutcome":
        if type(session) is not VoiceSessionCapsule:
            raise VoiceContractError("session must be exact concrete VoiceSessionCapsule")
        if VoiceSessionCapsule.from_mapping(session.as_dict()) != session:
            raise VoiceContractError("session failed canonical reconstruction")
        _exact_causal("outcome_causal_identity", outcome_causal_identity)
        _same_entity_lineage(session.session_causal_identity, outcome_causal_identity, label="outcome_causal_identity")
        payload = {
            "schema": VOICE_OUTCOME_SCHEMA,
            "voice_session_id": session.voice_session_id,
            "voice_session_sha256": session.sha256(),
            "outcome_causal_identity": outcome_causal_identity,
            "outcome_causal_identity_sha256": outcome_causal_identity.sha256(),
            "outcome_kind": outcome_kind,
            "result_ref": result_ref,
            "result_sha256": result_sha256,
            "provenance_refs": provenance_refs,
            "classification": VOICE_CLASSIFICATION,
        }
        provisional = cls(outcome_id="placeholder", **payload)
        return cls(outcome_id=provisional.expected_outcome_id(), **payload)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "VoiceOutcome":
        expected = {
            "schema", "outcome_id", "voice_session_id", "voice_session_sha256",
            "outcome_causal_identity", "outcome_causal_identity_sha256", "outcome_kind",
            "result_ref", "result_sha256", "provenance_refs", "classification",
        }
        if not isinstance(value, Mapping) or set(value.keys()) != expected:
            raise VoiceContractError("voice outcome fields must match schema exactly")
        return cls(
            schema=value["schema"], outcome_id=value["outcome_id"],
            voice_session_id=value["voice_session_id"], voice_session_sha256=value["voice_session_sha256"],
            outcome_causal_identity=CausalIdentity.from_mapping(value["outcome_causal_identity"]),
            outcome_causal_identity_sha256=value["outcome_causal_identity_sha256"],
            outcome_kind=value["outcome_kind"], result_ref=value["result_ref"], result_sha256=value["result_sha256"],
            provenance_refs=tuple(value["provenance_refs"]) if type(value["provenance_refs"]) is list else value["provenance_refs"],
            classification=value["classification"],
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "voice_session_id": self.voice_session_id,
            "voice_session_sha256": self.voice_session_sha256,
            "outcome_causal_identity": self.outcome_causal_identity.as_dict(),
            "outcome_causal_identity_sha256": self.outcome_causal_identity_sha256,
            "outcome_kind": self.outcome_kind,
            "result_ref": self.result_ref,
            "result_sha256": self.result_sha256,
            "provenance_refs": list(self.provenance_refs),
            "classification": self.classification,
        }

    def expected_outcome_id(self) -> str:
        return "voice-outcome:" + _digest(self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {"outcome_id": self.outcome_id, **self.identity_payload()}

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_voice_outcome(
    *,
    session: VoiceSessionCapsule,
    candidate: VoiceOutcome,
    existing: VoiceOutcome | None = None,
) -> VoiceOutcome:
    """Bind one outcome to an exact session; exact replay is idempotent.

    ``existing`` is explicit caller-supplied prior state. This function does not persist it.
    If no prior outcome is supplied, no claim is made that another store lacks one.
    """
    if type(session) is not VoiceSessionCapsule or type(candidate) is not VoiceOutcome:
        raise VoiceContractError("session/candidate must be exact concrete voice contract types")
    if candidate.voice_session_id != session.voice_session_id:
        raise VoiceContractError("outcome voice_session_id does not match session")
    if candidate.voice_session_sha256 != session.sha256():
        raise VoiceContractError("outcome voice_session_sha256 does not match exact session")
    _same_entity_lineage(session.session_causal_identity, candidate.outcome_causal_identity, label="outcome_causal_identity")
    if existing is None:
        return candidate
    if type(existing) is not VoiceOutcome:
        raise VoiceContractError("existing must be exact concrete VoiceOutcome")
    if existing.voice_session_id != session.voice_session_id or existing.voice_session_sha256 != session.sha256():
        raise VoiceContractError("existing outcome is not bound to this exact session")
    if existing == candidate and existing.sha256() == candidate.sha256():
        return existing
    raise VoiceContractError("voice session already has a different terminal outcome")
