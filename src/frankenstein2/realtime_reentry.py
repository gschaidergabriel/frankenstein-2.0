"""F2-WP-705 deterministic realtime voice re-entry evidence contract.

This component records caller-supplied realtime transition evidence for barge-in,
bilateral silence and tool-return re-entry. It deliberately does not open audio devices,
run VAD/ASR/TTS, contact a provider/model/tool, execute effects, or mutate canonical state.

Generation 1 established the opaque session-id/digest evidence contract. Generation 2
hardens its consumer boundary against the now-admitted F2-WP-704 VoiceSessionCapsule by
requiring exact concrete canonical reconstruction while preserving all G1 event semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .voice_contract import VoiceSessionCapsule

REALTIME_REENTRY_VERSION = "F2_REALTIME_REENTRY/v1"
BARGE_IN = "BARGE_IN"
BILATERAL_SILENCE = "BILATERAL_SILENCE"
TOOL_RETURN = "TOOL_RETURN"
_EVENT_TYPES = frozenset({BARGE_IN, BILATERAL_SILENCE, TOOL_RETURN})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_IDENTIFIER_LENGTH = 512


class RealtimeReentryError(ValueError):
    """Raised when WP705 evidence violates the fail-closed contract."""


def _exact_voice_session(value: Any) -> VoiceSessionCapsule:
    """Require the exact canonical WP704 VoiceSessionCapsule boundary."""

    if type(value) is not VoiceSessionCapsule:
        raise RealtimeReentryError("voice session must be exact concrete VoiceSessionCapsule")
    try:
        rebuilt = VoiceSessionCapsule.from_mapping(value.as_dict())
    except (TypeError, ValueError) as exc:
        raise RealtimeReentryError(f"invalid voice session capsule: {exc}") from exc
    if rebuilt != value or rebuilt.sha256() != value.sha256():
        raise RealtimeReentryError("voice session capsule failed canonical reconstruction")
    return value


def _identifier(name: str, value: Any) -> str:
    if type(value) is not str:
        raise RealtimeReentryError(f"{name} must be a string")
    if not value or value != value.strip():
        raise RealtimeReentryError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise RealtimeReentryError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RealtimeReentryError(f"{name} contains control characters")
    return value


def _digest(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise RealtimeReentryError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _json_int(name: str, value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        qualifier = "positive" if minimum == 1 else "non-negative"
        raise RealtimeReentryError(f"{name} must be a {qualifier} integer")
    try:
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RealtimeReentryError(f"{name} is outside the canonical JSON integer domain") from exc
    return value


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RealtimeReentryError("re-entry value is not canonically JSON serializable") from exc


@dataclass(frozen=True, slots=True)
class RealtimeReentryPolicy:
    """Declaration-only timing bound for bilateral-silence evidence."""

    bilateral_silence_threshold_ms: int

    def __post_init__(self) -> None:
        _json_int("bilateral_silence_threshold_ms", self.bilateral_silence_threshold_ms, minimum=1)

    def as_dict(self) -> dict[str, int]:
        return {"bilateral_silence_threshold_ms": self.bilateral_silence_threshold_ms}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RealtimeReentryPolicy":
        if not isinstance(value, Mapping) or set(value.keys()) != {"bilateral_silence_threshold_ms"}:
            raise RealtimeReentryError("invalid realtime re-entry policy fields")
        return cls(bilateral_silence_threshold_ms=value["bilateral_silence_threshold_ms"])


@dataclass(frozen=True, slots=True)
class RealtimeReentryCursor:
    """Exact caller-supplied predecessor reference for one voice session.

    The cursor is not canonical state authority. It is only the predecessor evidence that
    lets this component reject stale/cross-session event chains deterministically.
    """

    session_id: str
    session_sha256: str
    last_event_sequence: int
    last_causal_generation: int
    last_observed_at_ms: int
    last_event_id: str | None
    last_event_sha256: str | None

    def __post_init__(self) -> None:
        _identifier("session_id", self.session_id)
        _digest("session_sha256", self.session_sha256)
        _json_int("last_event_sequence", self.last_event_sequence)
        _json_int("last_causal_generation", self.last_causal_generation)
        _json_int("last_observed_at_ms", self.last_observed_at_ms)
        if self.last_event_sequence == 0:
            if self.last_causal_generation != 0:
                raise RealtimeReentryError("empty cursor must have causal generation 0")
            if self.last_event_id is not None or self.last_event_sha256 is not None:
                raise RealtimeReentryError("empty cursor cannot carry predecessor event identity")
        else:
            if self.last_causal_generation < 1:
                raise RealtimeReentryError("non-empty cursor requires positive causal generation")
            if self.last_event_id is None or self.last_event_sha256 is None:
                raise RealtimeReentryError("non-empty cursor requires exact predecessor event identity")
            _identifier("last_event_id", self.last_event_id)
            _digest("last_event_sha256", self.last_event_sha256)

    @classmethod
    def initial(cls, *, session_id: str, session_sha256: str) -> "RealtimeReentryCursor":
        return cls(
            session_id=session_id,
            session_sha256=session_sha256,
            last_event_sequence=0,
            last_causal_generation=0,
            last_observed_at_ms=0,
            last_event_id=None,
            last_event_sha256=None,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_sha256": self.session_sha256,
            "last_event_sequence": self.last_event_sequence,
            "last_causal_generation": self.last_causal_generation,
            "last_observed_at_ms": self.last_observed_at_ms,
            "last_event_id": self.last_event_id,
            "last_event_sha256": self.last_event_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RealtimeReentryCursor":
        if not isinstance(value, Mapping):
            raise RealtimeReentryError("cursor input must be a mapping")
        expected = {
            "session_id",
            "session_sha256",
            "last_event_sequence",
            "last_causal_generation",
            "last_observed_at_ms",
            "last_event_id",
            "last_event_sha256",
        }
        if set(value.keys()) != expected:
            raise RealtimeReentryError("invalid realtime re-entry cursor fields")
        return cls(**{key: value[key] for key in expected})


@dataclass(frozen=True, slots=True)
class RealtimeReentryEvidence:
    """Immutable, non-executing realtime re-entry evidence candidate."""

    reentry_version: str
    session_id: str
    session_sha256: str
    event_type: str
    event_sequence: int
    causal_generation: int
    observed_at_ms: int
    predecessor_event_id: str | None
    predecessor_event_sha256: str | None
    barge_in_input_id: str | None
    local_silence_ms: int
    remote_silence_ms: int
    tool_call_id: str | None
    tool_result_sha256: str | None
    policy: RealtimeReentryPolicy

    def __post_init__(self) -> None:
        if self.reentry_version != REALTIME_REENTRY_VERSION:
            raise RealtimeReentryError(f"reentry_version must equal {REALTIME_REENTRY_VERSION}")
        _identifier("session_id", self.session_id)
        _digest("session_sha256", self.session_sha256)
        if self.event_type not in _EVENT_TYPES:
            raise RealtimeReentryError("event_type is not admitted")
        _json_int("event_sequence", self.event_sequence, minimum=1)
        _json_int("causal_generation", self.causal_generation, minimum=1)
        _json_int("observed_at_ms", self.observed_at_ms)
        _json_int("local_silence_ms", self.local_silence_ms)
        _json_int("remote_silence_ms", self.remote_silence_ms)
        if type(self.policy) is not RealtimeReentryPolicy:
            raise RealtimeReentryError("policy must be exact concrete RealtimeReentryPolicy")

        if self.event_sequence == 1:
            if self.predecessor_event_id is not None or self.predecessor_event_sha256 is not None:
                raise RealtimeReentryError("first event cannot carry predecessor identity")
            if self.causal_generation != 1:
                raise RealtimeReentryError("first event causal generation must equal 1")
        else:
            if self.predecessor_event_id is None or self.predecessor_event_sha256 is None:
                raise RealtimeReentryError("successor event requires exact predecessor identity")
            _identifier("predecessor_event_id", self.predecessor_event_id)
            _digest("predecessor_event_sha256", self.predecessor_event_sha256)

        if self.event_type == BARGE_IN:
            if self.barge_in_input_id is None:
                raise RealtimeReentryError("BARGE_IN requires explicit input activity identity")
            _identifier("barge_in_input_id", self.barge_in_input_id)
            if self.local_silence_ms != 0 or self.remote_silence_ms != 0:
                raise RealtimeReentryError("BARGE_IN cannot carry silence-window evidence")
            if self.tool_call_id is not None or self.tool_result_sha256 is not None:
                raise RealtimeReentryError("BARGE_IN cannot carry tool-return evidence")

        elif self.event_type == BILATERAL_SILENCE:
            if self.barge_in_input_id is not None:
                raise RealtimeReentryError("BILATERAL_SILENCE cannot carry barge-in identity")
            if self.tool_call_id is not None or self.tool_result_sha256 is not None:
                raise RealtimeReentryError("BILATERAL_SILENCE cannot carry tool-return evidence")
            threshold = self.policy.bilateral_silence_threshold_ms
            if self.local_silence_ms < threshold or self.remote_silence_ms < threshold:
                raise RealtimeReentryError("bilateral silence evidence does not meet policy threshold")

        elif self.event_type == TOOL_RETURN:
            if self.barge_in_input_id is not None:
                raise RealtimeReentryError("TOOL_RETURN cannot carry barge-in identity")
            if self.local_silence_ms != 0 or self.remote_silence_ms != 0:
                raise RealtimeReentryError("TOOL_RETURN cannot carry silence-window evidence")
            if self.tool_call_id is None or self.tool_result_sha256 is None:
                raise RealtimeReentryError("TOOL_RETURN requires exact tool-call and result digest")
            _identifier("tool_call_id", self.tool_call_id)
            _digest("tool_result_sha256", self.tool_result_sha256)

    def as_dict(self) -> dict[str, Any]:
        return {
            "reentry_version": self.reentry_version,
            "session_id": self.session_id,
            "session_sha256": self.session_sha256,
            "event_type": self.event_type,
            "event_sequence": self.event_sequence,
            "causal_generation": self.causal_generation,
            "observed_at_ms": self.observed_at_ms,
            "predecessor_event_id": self.predecessor_event_id,
            "predecessor_event_sha256": self.predecessor_event_sha256,
            "barge_in_input_id": self.barge_in_input_id,
            "local_silence_ms": self.local_silence_ms,
            "remote_silence_ms": self.remote_silence_ms,
            "tool_call_id": self.tool_call_id,
            "tool_result_sha256": self.tool_result_sha256,
            "policy": self.policy.as_dict(),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RealtimeReentryEvidence":
        if not isinstance(value, Mapping):
            raise RealtimeReentryError("re-entry evidence input must be a mapping")
        expected = {
            "reentry_version",
            "session_id",
            "session_sha256",
            "event_type",
            "event_sequence",
            "causal_generation",
            "observed_at_ms",
            "predecessor_event_id",
            "predecessor_event_sha256",
            "barge_in_input_id",
            "local_silence_ms",
            "remote_silence_ms",
            "tool_call_id",
            "tool_result_sha256",
            "policy",
        }
        if set(value.keys()) != expected:
            raise RealtimeReentryError("invalid realtime re-entry evidence fields")
        return cls(
            reentry_version=value["reentry_version"],
            session_id=value["session_id"],
            session_sha256=value["session_sha256"],
            event_type=value["event_type"],
            event_sequence=value["event_sequence"],
            causal_generation=value["causal_generation"],
            observed_at_ms=value["observed_at_ms"],
            predecessor_event_id=value["predecessor_event_id"],
            predecessor_event_sha256=value["predecessor_event_sha256"],
            barge_in_input_id=value["barge_in_input_id"],
            local_silence_ms=value["local_silence_ms"],
            remote_silence_ms=value["remote_silence_ms"],
            tool_call_id=value["tool_call_id"],
            tool_result_sha256=value["tool_result_sha256"],
            policy=RealtimeReentryPolicy.from_mapping(value["policy"]),
        )

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def reentry_id(self) -> str:
        return "wrr:" + self.sha256()

    def next_cursor(self) -> RealtimeReentryCursor:
        return RealtimeReentryCursor(
            session_id=self.session_id,
            session_sha256=self.session_sha256,
            last_event_sequence=self.event_sequence,
            last_causal_generation=self.causal_generation,
            last_observed_at_ms=self.observed_at_ms,
            last_event_id=self.reentry_id(),
            last_event_sha256=self.sha256(),
        )


def build_realtime_reentry_evidence(
    *,
    cursor: RealtimeReentryCursor,
    event_type: str,
    observed_at_ms: int,
    policy: RealtimeReentryPolicy,
    barge_in_input_id: str | None = None,
    local_silence_ms: int = 0,
    remote_silence_ms: int = 0,
    tool_call_id: str | None = None,
    tool_result_sha256: str | None = None,
) -> RealtimeReentryEvidence:
    """Build one exact successor evidence object from caller-supplied predecessor state."""

    if type(cursor) is not RealtimeReentryCursor:
        raise RealtimeReentryError("cursor must be exact concrete RealtimeReentryCursor")
    if type(policy) is not RealtimeReentryPolicy:
        raise RealtimeReentryError("policy must be exact concrete RealtimeReentryPolicy")
    _json_int("observed_at_ms", observed_at_ms)
    if observed_at_ms < cursor.last_observed_at_ms:
        raise RealtimeReentryError("observed_at_ms regresses predecessor timing evidence")
    return RealtimeReentryEvidence(
        reentry_version=REALTIME_REENTRY_VERSION,
        session_id=cursor.session_id,
        session_sha256=cursor.session_sha256,
        event_type=event_type,
        event_sequence=cursor.last_event_sequence + 1,
        causal_generation=cursor.last_causal_generation + 1,
        observed_at_ms=observed_at_ms,
        predecessor_event_id=cursor.last_event_id,
        predecessor_event_sha256=cursor.last_event_sha256,
        barge_in_input_id=barge_in_input_id,
        local_silence_ms=local_silence_ms,
        remote_silence_ms=remote_silence_ms,
        tool_call_id=tool_call_id,
        tool_result_sha256=tool_result_sha256,
        policy=policy,
    )


def bind_voice_session_cursor(session: VoiceSessionCapsule) -> RealtimeReentryCursor:
    """Create the initial WP705 cursor only from an exact WP704 voice session."""

    _exact_voice_session(session)
    return RealtimeReentryCursor.initial(
        session_id=session.voice_session_id,
        session_sha256=session.sha256(),
    )


def verify_realtime_reentry_against_voice_session(
    evidence: RealtimeReentryEvidence,
    session: VoiceSessionCapsule,
) -> RealtimeReentryEvidence:
    """Bind existing WP705 evidence to one exact concrete WP704 session capsule."""

    _exact_voice_session(session)
    if type(evidence) is not RealtimeReentryEvidence:
        raise RealtimeReentryError("evidence must be exact concrete RealtimeReentryEvidence")
    reconstructed = RealtimeReentryEvidence.from_mapping(evidence.as_dict())
    if reconstructed != evidence:
        raise RealtimeReentryError("re-entry evidence canonical reconstruction mismatch")
    if evidence.session_id != session.voice_session_id or evidence.session_sha256 != session.sha256():
        raise RealtimeReentryError("voice session binding mismatch")
    return evidence


def verify_realtime_reentry_evidence(
    evidence: RealtimeReentryEvidence,
    *,
    expected_reentry_id: str,
    expected_sha256: str,
    expected_session_id: str,
    expected_session_sha256: str,
    expected_event_type: str,
    expected_event_sequence: int,
    expected_causal_generation: int,
) -> RealtimeReentryEvidence:
    """Revalidate exact canonical WP705 evidence at a consumer boundary."""

    if type(evidence) is not RealtimeReentryEvidence:
        raise RealtimeReentryError("evidence must be exact concrete RealtimeReentryEvidence")
    _identifier("expected_reentry_id", expected_reentry_id)
    _digest("expected_sha256", expected_sha256)
    _identifier("expected_session_id", expected_session_id)
    _digest("expected_session_sha256", expected_session_sha256)
    if expected_event_type not in _EVENT_TYPES:
        raise RealtimeReentryError("expected_event_type is not admitted")
    _json_int("expected_event_sequence", expected_event_sequence, minimum=1)
    _json_int("expected_causal_generation", expected_causal_generation, minimum=1)

    reconstructed = RealtimeReentryEvidence.from_mapping(evidence.as_dict())
    if reconstructed != evidence:
        raise RealtimeReentryError("re-entry evidence canonical reconstruction mismatch")
    if evidence.reentry_id() != expected_reentry_id:
        raise RealtimeReentryError("re-entry identity mismatch")
    if evidence.sha256() != expected_sha256:
        raise RealtimeReentryError("re-entry digest mismatch")
    if evidence.session_id != expected_session_id or evidence.session_sha256 != expected_session_sha256:
        raise RealtimeReentryError("voice session binding mismatch")
    if evidence.event_type != expected_event_type:
        raise RealtimeReentryError("re-entry event type mismatch")
    if evidence.event_sequence != expected_event_sequence:
        raise RealtimeReentryError("re-entry sequence mismatch")
    if evidence.causal_generation != expected_causal_generation:
        raise RealtimeReentryError("re-entry causal generation mismatch")
    return evidence
