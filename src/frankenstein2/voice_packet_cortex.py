"""Deterministic text/information-packet surrogate for the F2 local-voice cortex.

WP715 packet/controller scope only: no acoustic I/O, model inference, UnifiedDB write,
external effect, target-runtime credit, or whole-product acceptance is created here.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Any, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .causal_identity import CausalIdentity
    from .voice_contract import VoiceOutcome, VoiceSessionCapsule

INPUT_SCHEMA = "FRANKENSTEIN2_VOICE_INPUT_PACKET/v1"
OUTPUT_SCHEMA = "FRANKENSTEIN2_VOICE_OUTPUT_PACKET/v1"
EVENT_SCHEMA = "FRANKENSTEIN2_CORTEX_EVENT_PACKET/v1"
PACKET_CLASSIFICATION = "PACKET_SIMULATION_ONLY_NOT_ACOUSTIC_RUNTIME_OR_ACCEPTANCE_CREDIT"

_INPUT_MODALITIES = frozenset(("simulated_audio_text", "transcript_fixture", "asr_partial", "asr_final"))
_ENDPOINTS = frozenset(("HOLD", "END", "UNKNOWN"))
_PLAYBACK = frozenset(("queued", "started", "heard", "interrupted", "cancelled", "completed"))
_INTENTS = frozenset(("WAIT", "BACKCHANNEL", "ANSWER", "TOOL_USE", "CLOSE"))
_VAD = frozenset(("SILENCE", "SPEECH", "UNKNOWN"))
_OVERLAP = frozenset(("NONE", "USER_OVER_OUTPUT", "OUTPUT_OVER_USER", "UNKNOWN"))
_PRESENCE = frozenset(("PRESENT_INTERRUPTIBLE", "PRESENT_BUSY", "ABSENT", "UNKNOWN"))
_FAULTS = frozenset(("drop", "duplicate", "reorder", "corrupt"))
_SYSTEM_EVENTS = frozenset((
    "WAKE", "VAD_TRANSITION", "ENDPOINT_DECISION", "CANCELLATION", "TOOL_RESULT",
    "MEMORY_BIND", "ERROR", "FALLBACK", "RECOVERY", "TRANSPORT_FAILURE", "RESTART_REENTRY",
))
_TERMINAL_PLAYBACK = frozenset(("interrupted", "cancelled", "completed"))
_MAX_TEXT_CHARS = 32768


class VoicePacketCortexError(ValueError):
    """Fail-closed packet/cortex validation error."""


def _atom(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise VoicePacketCortexError(f"{name} must be a non-empty trimmed string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise VoicePacketCortexError(f"{name} contains control characters")
    return value


def _nonnegative(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise VoicePacketCortexError(f"{name} must be an integer >= 0")
    return value


def _fraction(name: str, value: Any) -> float:
    if type(value) not in (int, float):
        raise VoicePacketCortexError(f"{name} must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise VoicePacketCortexError(f"{name} must be within [0, 1]")
    return result


def _refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise VoicePacketCortexError(f"{name} must be an immutable tuple")
    for item in value:
        _atom(f"{name} item", item)
    if len(set(value)) != len(value):
        raise VoicePacketCortexError(f"{name} must not contain duplicates")
    return value


def _digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class VoiceInputPacket:
    session_id: str
    turn_id: str
    packet_id: str
    monotonic_ms: int
    source_modality: str
    text: str
    language: str
    is_final: bool
    confidence: float
    speech_start: bool
    speech_end: bool
    vad_state: str
    endpoint_decision: str
    overlap_state: str
    barge_in: bool
    source_duration_ms: int
    sequence: int
    fault_flags: tuple[str, ...] = ()
    schema: str = INPUT_SCHEMA
    classification: str = PACKET_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != INPUT_SCHEMA or self.classification != PACKET_CLASSIFICATION:
            raise VoicePacketCortexError("input packet schema/classification mismatch")
        for name in ("session_id", "turn_id", "packet_id", "language"):
            _atom(name, getattr(self, name))
        for name in ("monotonic_ms", "source_duration_ms", "sequence"):
            _nonnegative(name, getattr(self, name))
        if self.source_modality not in _INPUT_MODALITIES:
            raise VoicePacketCortexError("source_modality is not admitted")
        if type(self.text) is not str:
            raise VoicePacketCortexError("text must be a string")
        if len(self.text) > _MAX_TEXT_CHARS:
            raise VoicePacketCortexError("text exceeds bounded packet payload")
        if any(type(v) is not bool for v in (self.is_final, self.speech_start, self.speech_end, self.barge_in)):
            raise VoicePacketCortexError("input boolean fields must be exact bool")
        _fraction("confidence", self.confidence)
        if self.vad_state not in _VAD or self.endpoint_decision not in _ENDPOINTS or self.overlap_state not in _OVERLAP:
            raise VoicePacketCortexError("input state enum is not admitted")
        _refs("fault_flags", self.fault_flags)
        if any(flag not in _FAULTS for flag in self.fault_flags):
            raise VoicePacketCortexError("fault_flags contains an unadmitted fault")
        if self.source_modality == "asr_final" and not self.is_final:
            raise VoicePacketCortexError("asr_final must set is_final")
        if self.is_final and self.endpoint_decision == "HOLD":
            raise VoicePacketCortexError("final packet cannot explicitly HOLD endpoint")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema, "session_id": self.session_id, "turn_id": self.turn_id,
            "packet_id": self.packet_id, "monotonic_ms": self.monotonic_ms,
            "source_modality": self.source_modality, "text": self.text, "language": self.language,
            "is_final": self.is_final, "confidence": float(self.confidence),
            "speech_start": self.speech_start, "speech_end": self.speech_end,
            "vad_state": self.vad_state, "endpoint_decision": self.endpoint_decision,
            "overlap_state": self.overlap_state, "barge_in": self.barge_in,
            "source_duration_ms": self.source_duration_ms, "sequence": self.sequence,
            "fault_flags": list(self.fault_flags), "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class VoiceOutputPacket:
    session_id: str
    turn_id: str
    packet_id: str
    monotonic_ms: int
    text_segment: str
    expression_intent: str
    speech_act: str
    planned_audio_duration_ms: int
    first_output_ms: int
    sequence: int
    cancellable: bool
    playback_state: str
    heard_fraction: float
    interruption_ms: int | None
    commit_eligible: bool
    voiceoutcome_ref: str | None = None
    schema: str = OUTPUT_SCHEMA
    classification: str = PACKET_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != OUTPUT_SCHEMA or self.classification != PACKET_CLASSIFICATION:
            raise VoicePacketCortexError("output packet schema/classification mismatch")
        for name in ("session_id", "turn_id", "packet_id", "expression_intent"):
            _atom(name, getattr(self, name))
        for name in ("monotonic_ms", "planned_audio_duration_ms", "first_output_ms", "sequence"):
            _nonnegative(name, getattr(self, name))
        if type(self.text_segment) is not str:
            raise VoicePacketCortexError("text_segment must be a string")
        if len(self.text_segment) > _MAX_TEXT_CHARS:
            raise VoicePacketCortexError("text_segment exceeds bounded packet payload")
        if self.speech_act not in _INTENTS or self.playback_state not in _PLAYBACK:
            raise VoicePacketCortexError("output state/intent is not admitted")
        if type(self.cancellable) is not bool or type(self.commit_eligible) is not bool:
            raise VoicePacketCortexError("output boolean fields must be exact bool")
        heard = _fraction("heard_fraction", self.heard_fraction)
        if self.interruption_ms is not None:
            _nonnegative("interruption_ms", self.interruption_ms)
        if self.voiceoutcome_ref is not None:
            _atom("voiceoutcome_ref", self.voiceoutcome_ref)
        if self.commit_eligible and not (self.playback_state == "completed" and heard == 1.0):
            raise VoicePacketCortexError("only fully heard completed output may be commit eligible")
        if self.playback_state in ("queued", "cancelled") and heard != 0.0:
            raise VoicePacketCortexError("queued/cancelled output cannot claim heard audio")
        if self.playback_state in ("interrupted", "cancelled") and self.interruption_ms is None:
            raise VoicePacketCortexError("interrupted/cancelled output requires interruption_ms")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema, "session_id": self.session_id, "turn_id": self.turn_id,
            "packet_id": self.packet_id, "monotonic_ms": self.monotonic_ms,
            "text_segment": self.text_segment, "expression_intent": self.expression_intent,
            "speech_act": self.speech_act, "planned_audio_duration_ms": self.planned_audio_duration_ms,
            "first_output_ms": self.first_output_ms, "sequence": self.sequence,
            "cancellable": self.cancellable, "playback_state": self.playback_state,
            "heard_fraction": float(self.heard_fraction), "interruption_ms": self.interruption_ms,
            "commit_eligible": self.commit_eligible, "voiceoutcome_ref": self.voiceoutcome_ref,
            "classification": self.classification,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class CortexEventPacket:
    session_id: str
    turn_id: str
    event_id: str
    monotonic_ms: int
    event_kind: str
    voice_intent: str
    presence_state: str
    packet_refs: tuple[str, ...] = ()
    gwt_ref: str | None = None
    memory_refs: tuple[str, ...] = ()
    tool_ref: str | None = None
    detail: str = ""
    schema: str = EVENT_SCHEMA
    classification: str = PACKET_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != EVENT_SCHEMA or self.classification != PACKET_CLASSIFICATION:
            raise VoicePacketCortexError("event packet schema/classification mismatch")
        for name in ("session_id", "turn_id", "event_id", "event_kind"):
            _atom(name, getattr(self, name))
        _nonnegative("monotonic_ms", self.monotonic_ms)
        if self.voice_intent not in _INTENTS or self.presence_state not in _PRESENCE:
            raise VoicePacketCortexError("event intent/presence is not admitted")
        _refs("packet_refs", self.packet_refs)
        _refs("memory_refs", self.memory_refs)
        if self.gwt_ref is not None:
            _atom("gwt_ref", self.gwt_ref)
        if self.tool_ref is not None:
            _atom("tool_ref", self.tool_ref)
        if type(self.detail) is not str:
            raise VoicePacketCortexError("detail must be a string")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema, "session_id": self.session_id, "turn_id": self.turn_id,
            "event_id": self.event_id, "monotonic_ms": self.monotonic_ms,
            "event_kind": self.event_kind, "voice_intent": self.voice_intent,
            "presence_state": self.presence_state, "packet_refs": list(self.packet_refs),
            "gwt_ref": self.gwt_ref, "memory_refs": list(self.memory_refs), "tool_ref": self.tool_ref,
            "detail": self.detail, "classification": self.classification,
        }


class VoicePacketCortex:
    """In-memory deterministic state machine for packet-only voice-cortex testing.

    Resource limits are per VoiceSessionCapsule and fail closed.  The controller never evicts
    replay/causal identity silently because doing so could turn an old replay into a new packet.
    A caller approaching a cap must close/roll to a new causally bound VoiceSessionCapsule.
    """

    MAX_EVENTS = 512
    MAX_INPUT_PACKETS = 256
    MAX_OUTPUT_PACKETS = 256
    MAX_TOOL_REFS = 128
    MAX_TEXT_CHARS = _MAX_TEXT_CHARS

    def __init__(self, session: "VoiceSessionCapsule", *, presence_state: str = "PRESENT_INTERRUPTIBLE",
                 opened_monotonic_ms: int = 0) -> None:
        from .voice_contract import VoiceSessionCapsule
        if type(session) is not VoiceSessionCapsule:
            raise VoicePacketCortexError("session must be exact VoiceSessionCapsule")
        if presence_state not in _PRESENCE:
            raise VoicePacketCortexError("presence_state is not admitted")
        _nonnegative("opened_monotonic_ms", opened_monotonic_ms)
        self.session = session
        self.session_id = session.voice_session_id
        self.presence_state = presence_state
        self.is_open = True
        self._event_seq = 0
        self._input_seen: dict[str, str] = {}
        self._last_input_sequence: dict[str, int] = {}
        self._last_input_monotonic_ms: dict[str, int] = {}
        self._final_turns: set[str] = set()
        self._outputs: dict[str, VoiceOutputPacket] = {}
        self._last_output_sequence: dict[str, int] = {}
        self._events: list[CortexEventPacket] = []
        self._active_tools: dict[str, str] = {}
        self._cancelled_tools: set[str] = set()
        self._closed_outcome: "VoiceOutcome | None" = None
        self._closed_signature: tuple[Any, ...] | None = None
        self._event(
            turn_id=session.intent.causal_identity.turn_id,
            monotonic_ms=opened_monotonic_ms,
            kind="SESSION_OPEN",
            detail="packet cortex session opened",
        )

    @property
    def events(self) -> tuple[CortexEventPacket, ...]:
        return tuple(self._events)

    @property
    def outputs(self) -> tuple[VoiceOutputPacket, ...]:
        return tuple(sorted(self._outputs.values(), key=lambda packet: (packet.turn_id, packet.sequence, packet.packet_id)))

    def _require_event_slots(self, required: int) -> None:
        if type(required) is not int or required <= 0:
            raise VoicePacketCortexError("required event slots must be a positive integer")
        if len(self._events) + required > self.MAX_EVENTS:
            raise VoicePacketCortexError("event capacity exhausted; rotate VoiceSessionCapsule")

    def _require_event_capacity(self) -> None:
        self._require_event_slots(1)

    def _require_new_input_capacity(self) -> None:
        if len(self._input_seen) >= self.MAX_INPUT_PACKETS:
            raise VoicePacketCortexError("input replay capacity exhausted; rotate VoiceSessionCapsule")

    def _require_new_output_capacity(self) -> None:
        if len(self._outputs) >= self.MAX_OUTPUT_PACKETS:
            raise VoicePacketCortexError("output packet capacity exhausted; rotate VoiceSessionCapsule")

    def _require_new_tool_capacity(self) -> None:
        if len(self._active_tools) + len(self._cancelled_tools) >= self.MAX_TOOL_REFS:
            raise VoicePacketCortexError("tool ownership capacity exhausted; rotate VoiceSessionCapsule")

    def _event(self, *, turn_id: str, monotonic_ms: int, kind: str, intent: str = "WAIT",
               packet_refs: tuple[str, ...] = (), gwt_ref: str | None = None,
               memory_refs: tuple[str, ...] = (), tool_ref: str | None = None,
               detail: str = "") -> CortexEventPacket:
        if not self.is_open and kind != "SESSION_CLOSE":
            raise VoicePacketCortexError("session is closed")
        self._require_event_capacity()
        next_event_seq = self._event_seq + 1
        event = CortexEventPacket(
            session_id=self.session_id,
            turn_id=turn_id,
            event_id=f"cortex-event:{self.session_id}:{next_event_seq:08d}",
            monotonic_ms=monotonic_ms,
            event_kind=kind,
            voice_intent=intent,
            presence_state=self.presence_state,
            packet_refs=packet_refs,
            gwt_ref=gwt_ref,
            memory_refs=memory_refs,
            tool_ref=tool_ref,
            detail=detail,
        )
        self._event_seq = next_event_seq
        self._events.append(event)
        return event

    def accept_input(self, packet: VoiceInputPacket) -> CortexEventPacket:
        if not self.is_open or packet.session_id != self.session_id:
            raise VoicePacketCortexError("closed session or input packet session mismatch")
        self._require_event_capacity()
        digest = packet.sha256()
        prior = self._input_seen.get(packet.packet_id)
        if prior is not None:
            if prior != digest:
                raise VoicePacketCortexError("packet_id replay changed content")
            return self._event(
                turn_id=packet.turn_id, monotonic_ms=packet.monotonic_ms,
                kind="INPUT_DUPLICATE_IGNORED", packet_refs=(packet.packet_id,),
            )
        if "duplicate" in packet.fault_flags:
            return self._event(
                turn_id=packet.turn_id, monotonic_ms=packet.monotonic_ms,
                kind="INPUT_DUPLICATE_WITHOUT_ORIGINAL_REJECTED", packet_refs=(packet.packet_id,),
            )
        if "corrupt" in packet.fault_flags:
            raise VoicePacketCortexError("explicitly corrupt packet rejected")
        if "drop" in packet.fault_flags:
            return self._event(
                turn_id=packet.turn_id, monotonic_ms=packet.monotonic_ms,
                kind="INPUT_DROP_INJECTED", packet_refs=(packet.packet_id,),
            )
        expected = self._last_input_sequence.get(packet.turn_id, -1) + 1
        if packet.sequence != expected:
            if "reorder" in packet.fault_flags:
                return self._event(
                    turn_id=packet.turn_id, monotonic_ms=packet.monotonic_ms,
                    kind="INPUT_REORDER_REJECTED", packet_refs=(packet.packet_id,),
                    detail=f"expected={expected};observed={packet.sequence}",
                )
            raise VoicePacketCortexError(f"input sequence gap/reorder: expected {expected}, got {packet.sequence}")
        previous_ms = self._last_input_monotonic_ms.get(packet.turn_id)
        if previous_ms is not None and packet.monotonic_ms < previous_ms:
            raise VoicePacketCortexError(
                f"input monotonic_ms regressed: previous {previous_ms}, got {packet.monotonic_ms}"
            )
        if packet.turn_id in self._final_turns:
            raise VoicePacketCortexError("input arrived after final turn packet")
        self._require_new_input_capacity()
        self._require_event_slots(2 if packet.barge_in else 1)
        if packet.barge_in:
            self.cancel_for_barge_in(turn_id=packet.turn_id, monotonic_ms=packet.monotonic_ms)
        self._input_seen[packet.packet_id] = digest
        self._last_input_sequence[packet.turn_id] = packet.sequence
        self._last_input_monotonic_ms[packet.turn_id] = packet.monotonic_ms
        if packet.is_final:
            self._final_turns.add(packet.turn_id)
        kind = "ASR_FINAL" if packet.is_final else "ASR_PARTIAL"
        if packet.speech_start:
            kind = "SPEECH_START_" + kind
        if packet.speech_end:
            kind += "_SPEECH_END"
        return self._event(
            turn_id=packet.turn_id, monotonic_ms=packet.monotonic_ms, kind=kind,
            packet_refs=(packet.packet_id,),
            detail=f"vad={packet.vad_state};endpoint={packet.endpoint_decision};confidence={packet.confidence:.3f}",
        )

    def queue_output(self, *, turn_id: str, packet_id: str, monotonic_ms: int, text_segment: str,
                     expression_intent: str, speech_act: str, planned_audio_duration_ms: int,
                     sequence: int, cancellable: bool = True) -> VoiceOutputPacket:
        if not self.is_open or packet_id in self._outputs:
            raise VoicePacketCortexError("closed session or duplicate output packet_id")
        self._require_event_capacity()
        self._require_new_output_capacity()
        expected = self._last_output_sequence.get(turn_id, -1) + 1
        if sequence != expected:
            raise VoicePacketCortexError(f"output sequence gap/reorder: expected {expected}, got {sequence}")
        packet = VoiceOutputPacket(
            session_id=self.session_id,
            turn_id=turn_id,
            packet_id=packet_id,
            monotonic_ms=monotonic_ms,
            text_segment=text_segment,
            expression_intent=expression_intent,
            speech_act=speech_act,
            planned_audio_duration_ms=planned_audio_duration_ms,
            first_output_ms=monotonic_ms,
            sequence=sequence,
            cancellable=cancellable,
            playback_state="queued",
            heard_fraction=0.0,
            interruption_ms=None,
            commit_eligible=False,
        )
        self._outputs[packet_id] = packet
        self._last_output_sequence[turn_id] = sequence
        self._event(
            turn_id=turn_id, monotonic_ms=monotonic_ms, kind="OUTPUT_QUEUED",
            intent=speech_act, packet_refs=(packet_id,),
        )
        return packet

    def advance_output(self, packet_id: str, *, playback_state: str, monotonic_ms: int,
                       heard_fraction: float) -> VoiceOutputPacket:
        if packet_id not in self._outputs:
            raise VoicePacketCortexError("unknown output packet")
        self._require_event_capacity()
        current = self._outputs[packet_id]
        allowed = {
            "queued": frozenset(("started", "cancelled")),
            "started": frozenset(("heard", "interrupted", "cancelled", "completed")),
            "heard": frozenset(("heard", "interrupted", "completed")),
            "interrupted": frozenset(),
            "cancelled": frozenset(),
            "completed": frozenset(),
        }
        if playback_state not in allowed[current.playback_state]:
            raise VoicePacketCortexError(f"illegal playback transition {current.playback_state}->{playback_state}")
        if monotonic_ms < current.monotonic_ms:
            raise VoicePacketCortexError(
                f"output monotonic_ms regressed: previous {current.monotonic_ms}, got {monotonic_ms}"
            )
        heard = _fraction("heard_fraction", heard_fraction)
        if heard < float(current.heard_fraction):
            raise VoicePacketCortexError("heard_fraction cannot decrease")
        if playback_state == "completed" and heard != 1.0:
            raise VoicePacketCortexError("completed output must be fully heard")
        interruption = monotonic_ms if playback_state in ("interrupted", "cancelled") else None
        updated = replace(
            current,
            monotonic_ms=monotonic_ms,
            playback_state=playback_state,
            heard_fraction=heard,
            interruption_ms=interruption,
            commit_eligible=(playback_state == "completed" and heard == 1.0),
        )
        self._outputs[packet_id] = updated
        self._event(
            turn_id=current.turn_id, monotonic_ms=monotonic_ms,
            kind="OUTPUT_" + playback_state.upper(), intent=current.speech_act,
            packet_refs=(packet_id,), detail=f"heard_fraction={heard:.3f}",
        )
        return updated

    def cancel_for_barge_in(self, *, turn_id: str, monotonic_ms: int) -> tuple[str, ...]:
        self._require_event_capacity()
        candidates = tuple(
            (packet_id, current)
            for packet_id, current in self._outputs.items()
            if current.playback_state not in _TERMINAL_PLAYBACK and current.cancellable
        )
        if any(monotonic_ms < current.monotonic_ms for _, current in candidates):
            raise VoicePacketCortexError("barge-in monotonic_ms precedes output state it would cancel")
        changed: list[str] = []
        for packet_id, current in candidates:
            state = "cancelled" if current.playback_state == "queued" else "interrupted"
            self._outputs[packet_id] = replace(
                current,
                monotonic_ms=monotonic_ms,
                playback_state=state,
                interruption_ms=monotonic_ms,
                commit_eligible=False,
            )
            changed.append(packet_id)
        # A barge-in is the controller's interruption boundary.  Until a finer tool epoch exists,
        # all outstanding tool ownership is stale relative to the new user turn and must be fenced.
        for tool_ref in tuple(self._active_tools):
            self._active_tools.pop(tool_ref, None)
            self._cancelled_tools.add(tool_ref)
        changed_tuple = tuple(sorted(changed))
        self._event(
            turn_id=turn_id, monotonic_ms=monotonic_ms, kind="BARGE_IN_CANCEL_PROPAGATED",
            packet_refs=changed_tuple, detail="unheard/full-segment commit and stale tool ownership revoked",
        )
        return changed_tuple

    def emit_system_event(self, *, turn_id: str, monotonic_ms: int, event_kind: str,
                          packet_refs: tuple[str, ...] = (), gwt_ref: str | None = None,
                          memory_refs: tuple[str, ...] = (), tool_ref: str | None = None,
                          detail: str = "") -> CortexEventPacket:
        if event_kind not in _SYSTEM_EVENTS:
            raise VoicePacketCortexError("system event kind is not admitted")
        self._require_event_capacity()
        if event_kind == "TOOL_RESULT":
            if tool_ref is None or tool_ref in self._cancelled_tools or self._active_tools.get(tool_ref) != turn_id:
                raise VoicePacketCortexError("late, cancelled, unknown, or cross-turn tool result rejected")
        event = self._event(
            turn_id=turn_id, monotonic_ms=monotonic_ms, kind=event_kind,
            packet_refs=packet_refs, gwt_ref=gwt_ref, memory_refs=memory_refs,
            tool_ref=tool_ref, detail=detail,
        )
        if event_kind == "TOOL_RESULT" and tool_ref is not None:
            self._active_tools.pop(tool_ref, None)
        return event

    def emit_intent(self, *, turn_id: str, monotonic_ms: int, voice_intent: str,
                    gwt_ref: str | None = None, memory_refs: tuple[str, ...] = (),
                    tool_ref: str | None = None, detail: str = "") -> CortexEventPacket:
        if voice_intent not in _INTENTS:
            raise VoicePacketCortexError("voice_intent is not admitted")
        self._require_event_capacity()
        if voice_intent == "TOOL_USE":
            if tool_ref is None:
                raise VoicePacketCortexError("TOOL_USE requires tool_ref")
            if tool_ref in self._active_tools or tool_ref in self._cancelled_tools:
                raise VoicePacketCortexError("tool_ref already used or cancelled")
            self._require_new_tool_capacity()
        event = self._event(
            turn_id=turn_id, monotonic_ms=monotonic_ms, kind="VOICE_INTENT",
            intent=voice_intent, gwt_ref=gwt_ref, memory_refs=memory_refs,
            tool_ref=tool_ref, detail=detail,
        )
        if voice_intent == "TOOL_USE" and tool_ref is not None:
            self._active_tools[tool_ref] = turn_id
        return event

    def close_session(self, *, turn_id: str, monotonic_ms: int, outcome_causal_identity: "CausalIdentity",
                      outcome_kind: str, result_ref: str | None = None,
                      result_sha256: str | None = None,
                      provenance_refs: tuple[str, ...] = ("trigger4:wp715-packet-cortex",)) -> "VoiceOutcome":
        signature = (
            turn_id, monotonic_ms, outcome_causal_identity, outcome_kind,
            result_ref, result_sha256, provenance_refs,
        )
        if not self.is_open:
            if self._closed_outcome is not None and signature == self._closed_signature:
                return self._closed_outcome
            raise VoicePacketCortexError("session is already closed with different close identity")
        self._require_event_capacity()
        if any(packet.playback_state not in _TERMINAL_PLAYBACK for packet in self._outputs.values()):
            raise VoicePacketCortexError("cannot close session with nonterminal output")
        commit_eligible = [packet for packet in self._outputs.values() if packet.commit_eligible]
        if (result_ref is not None or result_sha256 is not None) and not commit_eligible:
            raise VoicePacketCortexError("result reference requires fully heard commit-eligible output")
        from .voice_contract import VoiceOutcome
        outcome = VoiceOutcome.create(
            session=self.session,
            outcome_causal_identity=outcome_causal_identity,
            outcome_kind=outcome_kind,
            result_ref=result_ref,
            result_sha256=result_sha256,
            provenance_refs=provenance_refs,
        )
        for packet_id, packet in tuple(self._outputs.items()):
            if packet.commit_eligible:
                self._outputs[packet_id] = replace(packet, voiceoutcome_ref=outcome.outcome_id)
        self._event(
            turn_id=turn_id, monotonic_ms=monotonic_ms, kind="SESSION_CLOSE", intent="CLOSE",
            packet_refs=tuple(sorted(packet.packet_id for packet in commit_eligible)),
            detail=f"voiceoutcome={outcome.outcome_id};commit_eligible_outputs={len(commit_eligible)}",
        )
        self.is_open = False
        self._active_tools.clear()
        self._closed_outcome = outcome
        self._closed_signature = signature
        return outcome
