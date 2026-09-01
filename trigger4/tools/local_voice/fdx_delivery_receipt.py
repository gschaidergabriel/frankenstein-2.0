#!/usr/bin/env python3
"""Run-local FDX audio delivery evidence binding for Trigger 4.

This is an execution/receipt tool, not a second playback state machine or durable
voice truth authority. It binds exact generated audio chunks to an existing
VoiceOutputPacket/session/turn lineage and fails closed on post-cancel sink
admission or scope inflation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Any

SCHEMA = "T4_FDX_AUDIO_DELIVERY_RECEIPT/v1"
SEMANTIC_KEY = "d62224bf7f52ef1db031ec7a9650a6b107f16a7a61f6f6cca253724d6419ea20"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_SCENARIOS = frozenset({
    "FDX2_BACKCHANNEL_HOLD",
    "FDX3_BARGE_IN_PARTIAL_OUTPUT",
    "FDX4_SIMULTANEOUS_USER_OVER_OUTPUT",
    "FDX6_LATE_TOOL_RESULT_AFTER_BARGE_AND_RESTART",
})
_ALLOWED_PACKET_STATES = frozenset({"queued", "started", "heard", "interrupted", "cancelled", "completed"})


class FDXReceiptError(ValueError):
    """Fail-closed FDX receipt/binding validation error."""


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise FDXReceiptError(message)


def _atom(name: str, value: Any) -> str:
    _need(type(value) is str and bool(value) and value == value.strip(), f"{name} must be a non-empty trimmed string")
    _need(not any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value), f"{name} contains control characters")
    return value


def _sha(name: str, value: Any) -> str:
    _need(type(value) is str and SHA256_RE.fullmatch(value) is not None, f"{name} must be lowercase SHA-256")
    return value


def _ms(name: str, value: Any) -> float:
    _need(type(value) in (int, float), f"{name} must be numeric")
    result = float(value)
    _need(math.isfinite(result) and result >= 0.0, f"{name} must be finite and >= 0")
    return result


def _count(name: str, value: Any) -> int:
    _need(type(value) is int and value >= 0, f"{name} must be integer >= 0")
    return value


def _fraction(name: str, value: Any) -> float:
    result = _ms(name, value)
    _need(result <= 1.0, f"{name} must be <= 1")
    return result


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def receipt_sha256(receipt: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(receipt)).hexdigest()


@dataclass(frozen=True, slots=True)
class AudioChunkEvidence:
    sequence: int
    sha256: str
    sample_rate: int
    samples: int
    byte_count: int
    generated_monotonic_ms: float
    sink_admitted: bool
    sink_admitted_monotonic_ms: float | None
    generated_after_cancel: bool
    discard_reason: str | None = None

    def __post_init__(self) -> None:
        _count("sequence", self.sequence)
        _sha("sha256", self.sha256)
        _need(type(self.sample_rate) is int and self.sample_rate > 0, "sample_rate must be positive integer")
        _need(type(self.samples) is int and self.samples > 0, "samples must be positive integer")
        _need(type(self.byte_count) is int and self.byte_count > 0, "byte_count must be positive integer")
        _ms("generated_monotonic_ms", self.generated_monotonic_ms)
        _need(type(self.sink_admitted) is bool, "sink_admitted must be bool")
        _need(type(self.generated_after_cancel) is bool, "generated_after_cancel must be bool")
        if self.sink_admitted:
            _need(self.sink_admitted_monotonic_ms is not None, "sink-admitted chunk needs sink timestamp")
            sink_ms = _ms("sink_admitted_monotonic_ms", self.sink_admitted_monotonic_ms)
            _need(sink_ms >= float(self.generated_monotonic_ms), "sink admission cannot precede chunk generation")
            _need(self.discard_reason is None, "sink-admitted chunk cannot have discard_reason")
        else:
            _need(self.sink_admitted_monotonic_ms is None, "discarded chunk cannot have sink timestamp")
            if self.generated_after_cancel:
                _atom("discard_reason", self.discard_reason)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "sha256": self.sha256,
            "sample_rate": self.sample_rate,
            "samples": self.samples,
            "byte_count": self.byte_count,
            "generated_monotonic_ms": float(self.generated_monotonic_ms),
            "sink_admitted": self.sink_admitted,
            "sink_admitted_monotonic_ms": None if self.sink_admitted_monotonic_ms is None else float(self.sink_admitted_monotonic_ms),
            "generated_after_cancel": self.generated_after_cancel,
            "discard_reason": self.discard_reason,
        }


@dataclass(slots=True)
class DeliveryBinding:
    """Strict run-local binding between generated audio and one existing output packet."""

    source_sha: str
    engine_identity: str
    voice_session_id: str
    turn_id: str
    voice_output_packet_id: str
    scenario: str
    request_admitted_monotonic_ms: float
    producer_cancel_capability: bool
    semantic_key: str = SEMANTIC_KEY
    chunks: list[AudioChunkEvidence] = field(default_factory=list)
    producer_cancel_requested_monotonic_ms: float | None = None
    sink_cancel_boundary_monotonic_ms: float | None = None
    preaccepted_buffer_samples: int = 0
    preaccepted_buffer_duration_ms: float = 0.0

    def __post_init__(self) -> None:
        _sha("source_sha", self.source_sha)
        _atom("engine_identity", self.engine_identity)
        _atom("voice_session_id", self.voice_session_id)
        _atom("turn_id", self.turn_id)
        _atom("voice_output_packet_id", self.voice_output_packet_id)
        _need(self.scenario in _ALLOWED_SCENARIOS, "scenario is not admitted")
        _ms("request_admitted_monotonic_ms", self.request_admitted_monotonic_ms)
        _need(type(self.producer_cancel_capability) is bool, "producer_cancel_capability must be bool")
        _need(self.semantic_key == SEMANTIC_KEY, "semantic_key mismatch")

    @staticmethod
    def chunk_digest(chunk_bytes: bytes | bytearray | memoryview) -> tuple[str, int]:
        raw = bytes(chunk_bytes)
        _need(bool(raw), "audio chunk must be non-empty")
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def _next_sequence(self) -> int:
        return len(self.chunks)

    def admit_chunk(self, *, chunk_bytes: bytes | bytearray | memoryview, sample_rate: int,
                    samples: int, generated_monotonic_ms: float, sink_admitted_monotonic_ms: float) -> AudioChunkEvidence:
        generated_ms = _ms("generated_monotonic_ms", generated_monotonic_ms)
        sink_ms = _ms("sink_admitted_monotonic_ms", sink_admitted_monotonic_ms)
        _need(generated_ms >= float(self.request_admitted_monotonic_ms), "chunk generation precedes request admission")
        _need(sink_ms >= generated_ms, "sink admission precedes generation")
        if self.sink_cancel_boundary_monotonic_ms is not None:
            _need(sink_ms < float(self.sink_cancel_boundary_monotonic_ms), "post-cancel sink admission rejected")
        digest, byte_count = self.chunk_digest(chunk_bytes)
        evidence = AudioChunkEvidence(
            sequence=self._next_sequence(), sha256=digest, sample_rate=sample_rate, samples=samples,
            byte_count=byte_count, generated_monotonic_ms=generated_ms, sink_admitted=True,
            sink_admitted_monotonic_ms=sink_ms,
            generated_after_cancel=(self.producer_cancel_requested_monotonic_ms is not None and generated_ms >= float(self.producer_cancel_requested_monotonic_ms)),
        )
        self.chunks.append(evidence)
        return evidence

    def request_cancel(self, *, monotonic_ms: float, preaccepted_buffer_samples: int = 0,
                       preaccepted_buffer_duration_ms: float = 0.0, request_producer_cancel: bool = True) -> None:
        cancel_ms = _ms("cancel monotonic_ms", monotonic_ms)
        _need(cancel_ms >= float(self.request_admitted_monotonic_ms), "cancel precedes request admission")
        _need(self.sink_cancel_boundary_monotonic_ms is None, "sink cancellation boundary already set")
        self.sink_cancel_boundary_monotonic_ms = cancel_ms
        self.preaccepted_buffer_samples = _count("preaccepted_buffer_samples", preaccepted_buffer_samples)
        self.preaccepted_buffer_duration_ms = _ms("preaccepted_buffer_duration_ms", preaccepted_buffer_duration_ms)
        if request_producer_cancel and self.producer_cancel_capability:
            self.producer_cancel_requested_monotonic_ms = cancel_ms

    def discard_generated_chunk(self, *, chunk_bytes: bytes | bytearray | memoryview, sample_rate: int,
                                samples: int, generated_monotonic_ms: float,
                                reason: str = "POST_CANCEL_NOT_SINK_ADMITTED") -> AudioChunkEvidence:
        generated_ms = _ms("generated_monotonic_ms", generated_monotonic_ms)
        _need(self.sink_cancel_boundary_monotonic_ms is not None, "discard_generated_chunk requires an admitted sink cancel boundary")
        _need(generated_ms >= float(self.sink_cancel_boundary_monotonic_ms), "discard path is only for generated-at/after-cancel chunks")
        digest, byte_count = self.chunk_digest(chunk_bytes)
        evidence = AudioChunkEvidence(
            sequence=self._next_sequence(), sha256=digest, sample_rate=sample_rate, samples=samples,
            byte_count=byte_count, generated_monotonic_ms=generated_ms, sink_admitted=False,
            sink_admitted_monotonic_ms=None, generated_after_cancel=True, discard_reason=_atom("reason", reason),
        )
        self.chunks.append(evidence)
        return evidence

    def build_receipt(self, *, packet_playback_state: str, heard_fraction: float, commit_eligible: bool,
                      voiceoutcome_ref: str | None, producer_last_generated_chunk_monotonic_ms: float | None = None,
                      restart_reentry_receipt_id: str | None = None, persistent_row_id_and_hash: str | None = None,
                      network_mode: str = "OFF_DURING_EVIDENCE_EXECUTION", outbound_inference_calls: int = 0) -> dict[str, Any]:
        _need(packet_playback_state in _ALLOWED_PACKET_STATES, "packet_playback_state is not admitted")
        heard = _fraction("heard_fraction", heard_fraction)
        _need(type(commit_eligible) is bool, "commit_eligible must be bool")
        if commit_eligible:
            _need(packet_playback_state == "completed" and heard == 1.0, "commit-eligible output must be completed and fully heard")
        if packet_playback_state in {"interrupted", "cancelled"}:
            _need(not commit_eligible, "interrupted/cancelled packet cannot be commit eligible")
            _need(self.sink_cancel_boundary_monotonic_ms is not None, "interrupted/cancelled receipt requires sink cancellation boundary")
        if voiceoutcome_ref is not None:
            _atom("voiceoutcome_ref", voiceoutcome_ref)
        if restart_reentry_receipt_id is not None:
            _atom("restart_reentry_receipt_id", restart_reentry_receipt_id)
        if persistent_row_id_and_hash is not None:
            _atom("persistent_row_id_and_hash", persistent_row_id_and_hash)
        if producer_last_generated_chunk_monotonic_ms is not None:
            producer_last_generated_chunk_monotonic_ms = _ms(
                "producer_last_generated_chunk_monotonic_ms", producer_last_generated_chunk_monotonic_ms
            )
        _atom("network_mode", network_mode)
        _count("outbound_inference_calls", outbound_inference_calls)

        admitted = [chunk for chunk in self.chunks if chunk.sink_admitted]
        post_cancel_admitted = [
            chunk for chunk in admitted
            if self.sink_cancel_boundary_monotonic_ms is not None
            and float(chunk.sink_admitted_monotonic_ms) >= float(self.sink_cancel_boundary_monotonic_ms)
        ]
        discarded_after_cancel = [chunk for chunk in self.chunks if chunk.generated_after_cancel and not chunk.sink_admitted]
        _need(not post_cancel_admitted, "post-cancel sink admission present in receipt")

        first_generated = min((chunk.generated_monotonic_ms for chunk in self.chunks), default=None)
        first_sink = min((float(chunk.sink_admitted_monotonic_ms) for chunk in admitted), default=None)
        last_sink = max((float(chunk.sink_admitted_monotonic_ms) for chunk in admitted), default=None)
        generated_after_cancel_count = sum(
            1 for chunk in self.chunks
            if self.sink_cancel_boundary_monotonic_ms is not None
            and float(chunk.generated_monotonic_ms) >= float(self.sink_cancel_boundary_monotonic_ms)
        )
        producer_cancel_credit = bool(
            self.producer_cancel_capability
            and self.producer_cancel_requested_monotonic_ms is not None
            and producer_last_generated_chunk_monotonic_ms is not None
            and producer_last_generated_chunk_monotonic_ms <= float(self.producer_cancel_requested_monotonic_ms)
        )
        sink_cancel_credit = bool(
            self.sink_cancel_boundary_monotonic_ms is not None
            and bool(admitted)
            and not post_cancel_admitted
        )
        packet_commit_fence_credit = bool(
            packet_playback_state in {"interrupted", "cancelled"} and not commit_eligible
        )

        return {
            "schema": SCHEMA,
            "semantic_key": self.semantic_key,
            "source_sha": self.source_sha,
            "engine_identity": self.engine_identity,
            "scenario": self.scenario,
            "voice_session_id": self.voice_session_id,
            "turn_id": self.turn_id,
            "voice_output_packet_id": self.voice_output_packet_id,
            "request_admitted_monotonic_ms": float(self.request_admitted_monotonic_ms),
            "first_generated_chunk_monotonic_ms": None if first_generated is None else float(first_generated),
            "first_sink_admission_monotonic_ms": first_sink,
            "sink_cancel_boundary_monotonic_ms": self.sink_cancel_boundary_monotonic_ms,
            "last_sink_admission_monotonic_ms": last_sink,
            "producer_cancel_capability": self.producer_cancel_capability,
            "producer_cancel_requested_monotonic_ms": self.producer_cancel_requested_monotonic_ms,
            "producer_last_generated_chunk_monotonic_ms": producer_last_generated_chunk_monotonic_ms,
            "preaccepted_buffer_samples": self.preaccepted_buffer_samples,
            "preaccepted_buffer_duration_ms": float(self.preaccepted_buffer_duration_ms),
            "generated_after_cancel_count": generated_after_cancel_count,
            "generated_after_cancel_discarded_count": len(discarded_after_cancel),
            "sink_post_cancel_admission_count": len(post_cancel_admitted),
            "chunks": [chunk.as_dict() for chunk in self.chunks],
            "packet_state": {
                "playback_state": packet_playback_state,
                "heard_fraction": heard,
                "commit_eligible": commit_eligible,
                "voiceoutcome_ref": voiceoutcome_ref,
            },
            "persistence_reentry": {
                "persistent_row_id_and_hash": persistent_row_id_and_hash,
                "restart_reentry_receipt_id": restart_reentry_receipt_id,
            },
            "network": {
                "mode": network_mode,
                "outbound_inference_calls": outbound_inference_calls,
            },
            "credits": {
                "producer_generation_cancel": int(producer_cancel_credit),
                "sink_delivery_cancel": int(sink_cancel_credit),
                "packet_commit_fence": int(packet_commit_fence_credit),
                "physical_cancellation_to_silence": 0,
                "human_heard_output": 0,
                "physical_microphone": 0,
                "physical_speaker": 0,
                "whole_voice_system": 0,
                "whole_product": 0,
            },
            "classification": "RUN_LOCAL_EVIDENCE_BINDING_NOT_SECOND_PLAYBACK_OR_DURABLE_STATE_AUTHORITY",
        }


def validate_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    _need(type(receipt) is dict, "receipt must be object")
    _need(receipt.get("schema") == SCHEMA, "schema mismatch")
    _need(receipt.get("semantic_key") == SEMANTIC_KEY, "semantic_key mismatch")
    _sha("source_sha", receipt.get("source_sha"))
    _atom("engine_identity", receipt.get("engine_identity"))
    _need(receipt.get("scenario") in _ALLOWED_SCENARIOS, "scenario is not admitted")
    for field_name in ("voice_session_id", "turn_id", "voice_output_packet_id"):
        _atom(field_name, receipt.get(field_name))
    request_ms = _ms("request_admitted_monotonic_ms", receipt.get("request_admitted_monotonic_ms"))

    chunks = receipt.get("chunks")
    _need(type(chunks) is list, "chunks must be list")
    previous_generated = request_ms
    previous_sink: float | None = None
    for expected_sequence, raw in enumerate(chunks):
        _need(type(raw) is dict, "chunk record must be object")
        chunk = AudioChunkEvidence(**raw)
        _need(chunk.sequence == expected_sequence, "chunk sequences must be contiguous in generation order")
        _need(float(chunk.generated_monotonic_ms) >= previous_generated, "chunk generation clock regressed")
        previous_generated = float(chunk.generated_monotonic_ms)
        if chunk.sink_admitted:
            sink = float(chunk.sink_admitted_monotonic_ms)
            if previous_sink is not None:
                _need(sink >= previous_sink, "sink admission clock regressed")
            previous_sink = sink

    cancel_ms = receipt.get("sink_cancel_boundary_monotonic_ms")
    if cancel_ms is not None:
        cancel_ms = _ms("sink_cancel_boundary_monotonic_ms", cancel_ms)
        for raw in chunks:
            if raw["sink_admitted"]:
                _need(float(raw["sink_admitted_monotonic_ms"]) < cancel_ms, "post-cancel sink admission")
        _need(receipt.get("sink_post_cancel_admission_count") == 0, "sink_post_cancel_admission_count must be zero")
    _count("preaccepted_buffer_samples", receipt.get("preaccepted_buffer_samples"))
    _ms("preaccepted_buffer_duration_ms", receipt.get("preaccepted_buffer_duration_ms"))

    packet = receipt.get("packet_state") or {}
    state = packet.get("playback_state")
    _need(state in _ALLOWED_PACKET_STATES, "packet playback state invalid")
    heard = _fraction("packet heard_fraction", packet.get("heard_fraction"))
    _need(type(packet.get("commit_eligible")) is bool, "packet commit_eligible must be bool")
    if packet["commit_eligible"]:
        _need(state == "completed" and heard == 1.0, "commit eligibility scope inflation")
    if state in {"interrupted", "cancelled"}:
        _need(packet["commit_eligible"] is False, "interrupted packet cannot be commit eligible")
        _need(cancel_ms is not None, "interrupted packet must bind sink cancellation boundary")

    credits = receipt.get("credits") or {}
    for zero_field in (
        "physical_cancellation_to_silence", "human_heard_output", "physical_microphone",
        "physical_speaker", "whole_voice_system", "whole_product",
    ):
        _need(credits.get(zero_field) == 0, f"{zero_field} must remain zero")
    _need(credits.get("producer_generation_cancel") in (0, 1), "producer_generation_cancel invalid")
    _need(credits.get("sink_delivery_cancel") in (0, 1), "sink_delivery_cancel invalid")
    _need(credits.get("packet_commit_fence") in (0, 1), "packet_commit_fence invalid")
    if credits.get("producer_generation_cancel") == 1:
        _need(receipt.get("producer_cancel_capability") is True, "producer cancel credit without capability")
        requested = _ms("producer_cancel_requested_monotonic_ms", receipt.get("producer_cancel_requested_monotonic_ms"))
        last_generated = _ms("producer_last_generated_chunk_monotonic_ms", receipt.get("producer_last_generated_chunk_monotonic_ms"))
        _need(last_generated <= requested, "producer cancel credit despite post-cancel generation")
    if credits.get("sink_delivery_cancel") == 1:
        _need(cancel_ms is not None, "sink cancellation credit requires boundary")
        _need(any(raw["sink_admitted"] for raw in chunks), "sink cancellation credit requires pre-cancel admitted audio")
    if credits.get("packet_commit_fence") == 1:
        _need(state in {"interrupted", "cancelled"} and packet["commit_eligible"] is False,
              "packet commit fence credit mismatch")

    network = receipt.get("network") or {}
    _atom("network.mode", network.get("mode"))
    _count("network.outbound_inference_calls", network.get("outbound_inference_calls"))
    _need(
        receipt.get("classification") == "RUN_LOCAL_EVIDENCE_BINDING_NOT_SECOND_PLAYBACK_OR_DURABLE_STATE_AUTHORITY",
        "classification mismatch",
    )
    return {
        "valid": True,
        "receipt_sha256": receipt_sha256(receipt),
        "chunk_count": len(chunks),
        "sink_admitted_chunk_count": sum(1 for raw in chunks if raw["sink_admitted"]),
        "generated_after_cancel_discarded_count": receipt.get("generated_after_cancel_discarded_count"),
        "credits": credits,
    }
