"""Run-local audio delivery evidence for the Trigger-4 owner-VPS FDX slice.

This module is an execution-evidence helper only. It does not own playback state,
VoiceOutcome state, durable memory, or canonical acceptance. The existing
VoiceOutputPacket remains the semantic playback/commit authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from frankenstein2.voice_packet_cortex import VoiceOutputPacket

SCHEMA = "T4_OWNER_VPS_FDX_AUDIO_DELIVERY_EVIDENCE/v1"
CLASSIFICATION = "RUN_LOCAL_EXECUTION_EVIDENCE_ONLY"


class AudioDeliveryEvidenceError(ValueError):
    """Fail-closed validation error for one run-local audio delivery binding."""


def _nonnegative(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise AudioDeliveryEvidenceError(f"{name} must be an integer >= 0")
    return value


def _atom(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise AudioDeliveryEvidenceError(f"{name} must be a non-empty trimmed string")
    return value


def _sha256_bytes(payload: bytes) -> str:
    if type(payload) is not bytes or not payload:
        raise AudioDeliveryEvidenceError("canonical_audio_bytes must be non-empty bytes")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class AudioChunkObservation:
    sequence: int
    generated_monotonic_ms: int
    sample_rate: int
    sample_count: int
    byte_count: int
    sha256: str
    sink_admitted: bool
    sink_admission_monotonic_ms: int | None
    generated_after_cancel_discarded: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "generated_monotonic_ms": self.generated_monotonic_ms,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
            "sink_admitted": self.sink_admitted,
            "sink_admission_monotonic_ms": self.sink_admission_monotonic_ms,
            "generated_after_cancel_discarded": self.generated_after_cancel_discarded,
        }


class RunLocalAudioDeliveryBinding:
    """Evidence-only binding between one existing VoiceOutputPacket and audio bytes."""

    def __init__(
        self,
        *,
        voice_session_id: str,
        turn_id: str,
        voice_output_packet_id: str,
        request_admission_monotonic_ms: int,
        producer_cancel_capability: bool,
    ) -> None:
        self.voice_session_id = _atom("voice_session_id", voice_session_id)
        self.turn_id = _atom("turn_id", turn_id)
        self.voice_output_packet_id = _atom("voice_output_packet_id", voice_output_packet_id)
        self.request_admission_monotonic_ms = _nonnegative(
            "request_admission_monotonic_ms", request_admission_monotonic_ms
        )
        if type(producer_cancel_capability) is not bool:
            raise AudioDeliveryEvidenceError("producer_cancel_capability must be exact bool")
        self.producer_cancel_capability = producer_cancel_capability
        self.producer_cancel_requested_monotonic_ms: int | None = None
        self.producer_cancel_executed = False
        self.sink_cancel_boundary_monotonic_ms: int | None = None
        self._chunks: list[AudioChunkObservation] = []

    @property
    def chunks(self) -> tuple[AudioChunkObservation, ...]:
        return tuple(self._chunks)

    def request_producer_cancel(self, *, monotonic_ms: int, executed: bool) -> None:
        monotonic_ms = _nonnegative("monotonic_ms", monotonic_ms)
        if monotonic_ms < self.request_admission_monotonic_ms:
            raise AudioDeliveryEvidenceError("producer cancel cannot precede output request admission")
        if self.producer_cancel_requested_monotonic_ms is not None:
            raise AudioDeliveryEvidenceError("producer cancel request already recorded")
        if type(executed) is not bool:
            raise AudioDeliveryEvidenceError("executed must be exact bool")
        if executed and not self.producer_cancel_capability:
            raise AudioDeliveryEvidenceError("cannot claim executed producer cancel without capability")
        self.producer_cancel_requested_monotonic_ms = monotonic_ms
        self.producer_cancel_executed = executed

    def cancel_sink(self, *, monotonic_ms: int) -> None:
        monotonic_ms = _nonnegative("monotonic_ms", monotonic_ms)
        if monotonic_ms < self.request_admission_monotonic_ms:
            raise AudioDeliveryEvidenceError("sink cancel cannot precede output request admission")
        if self.sink_cancel_boundary_monotonic_ms is not None:
            raise AudioDeliveryEvidenceError("sink cancel boundary already recorded")
        self.sink_cancel_boundary_monotonic_ms = monotonic_ms

    def record_chunk(
        self,
        *,
        sequence: int,
        generated_monotonic_ms: int,
        sample_rate: int,
        sample_count: int,
        canonical_audio_bytes: bytes,
        sink_admission_monotonic_ms: int | None,
    ) -> AudioChunkObservation:
        sequence = _nonnegative("sequence", sequence)
        generated_monotonic_ms = _nonnegative("generated_monotonic_ms", generated_monotonic_ms)
        sample_rate = _nonnegative("sample_rate", sample_rate)
        sample_count = _nonnegative("sample_count", sample_count)
        if sample_rate == 0 or sample_count == 0:
            raise AudioDeliveryEvidenceError("sample_rate and sample_count must be positive")
        if sequence != len(self._chunks):
            raise AudioDeliveryEvidenceError("chunk sequence must be contiguous from zero")
        if generated_monotonic_ms < self.request_admission_monotonic_ms:
            raise AudioDeliveryEvidenceError("generated chunk cannot precede output request admission")
        if self._chunks and generated_monotonic_ms < self._chunks[-1].generated_monotonic_ms:
            raise AudioDeliveryEvidenceError("generated chunk clock cannot regress")

        digest = _sha256_bytes(canonical_audio_bytes)
        sink_admitted = sink_admission_monotonic_ms is not None
        if sink_admitted:
            sink_admission_monotonic_ms = _nonnegative(
                "sink_admission_monotonic_ms", sink_admission_monotonic_ms
            )
            if sink_admission_monotonic_ms < generated_monotonic_ms:
                raise AudioDeliveryEvidenceError("sink admission cannot precede generation")
            prior_sink = next(
                (
                    item.sink_admission_monotonic_ms
                    for item in reversed(self._chunks)
                    if item.sink_admission_monotonic_ms is not None
                ),
                None,
            )
            if prior_sink is not None and sink_admission_monotonic_ms < prior_sink:
                raise AudioDeliveryEvidenceError("sink admission clock cannot regress")

        cancel = self.sink_cancel_boundary_monotonic_ms
        generated_after_cancel_discarded = (
            cancel is not None and generated_monotonic_ms > cancel and not sink_admitted
        )
        item = AudioChunkObservation(
            sequence=sequence,
            generated_monotonic_ms=generated_monotonic_ms,
            sample_rate=sample_rate,
            sample_count=sample_count,
            byte_count=len(canonical_audio_bytes),
            sha256=digest,
            sink_admitted=sink_admitted,
            sink_admission_monotonic_ms=sink_admission_monotonic_ms,
            generated_after_cancel_discarded=generated_after_cancel_discarded,
        )
        self._chunks.append(item)
        return item

    def receipt(self, *, packet: VoiceOutputPacket) -> dict[str, Any]:
        if type(packet) is not VoiceOutputPacket:
            raise AudioDeliveryEvidenceError("packet must be exact VoiceOutputPacket")
        if (
            packet.session_id != self.voice_session_id
            or packet.turn_id != self.turn_id
            or packet.packet_id != self.voice_output_packet_id
        ):
            raise AudioDeliveryEvidenceError("VoiceOutputPacket identity does not match audio binding")
        if not self._chunks:
            raise AudioDeliveryEvidenceError("at least one generated audio chunk is required")

        cancel = self.sink_cancel_boundary_monotonic_ms
        admitted = tuple(item for item in self._chunks if item.sink_admitted)
        post_cancel_admitted = tuple(
            item
            for item in admitted
            if cancel is not None
            and item.sink_admission_monotonic_ms is not None
            and item.sink_admission_monotonic_ms > cancel
        )
        generated_after_cancel = tuple(
            item for item in self._chunks if cancel is not None and item.generated_monotonic_ms > cancel
        )
        discarded_after_cancel = tuple(
            item for item in generated_after_cancel if item.generated_after_cancel_discarded
        )
        first_generated = self._chunks[0].generated_monotonic_ms
        first_sink = admitted[0].sink_admission_monotonic_ms if admitted else None
        last_sink = admitted[-1].sink_admission_monotonic_ms if admitted else None

        interrupted = packet.playback_state in ("interrupted", "cancelled")
        packet_commit_fence = interrupted and not packet.commit_eligible
        sink_delivery_cancel = cancel is not None and len(post_cancel_admitted) == 0
        producer_cancel = (
            self.producer_cancel_executed
            and self.producer_cancel_requested_monotonic_ms is not None
            and all(
                item.generated_monotonic_ms <= self.producer_cancel_requested_monotonic_ms
                for item in self._chunks
            )
        )

        product_negative_reasons: list[str] = []
        if post_cancel_admitted:
            product_negative_reasons.append("POST_CANCEL_CHUNK_ADMITTED_TO_OLD_PACKET")
        if cancel is not None and packet.commit_eligible:
            product_negative_reasons.append("INTERRUPTED_OUTPUT_BECOMES_COMMIT_ELIGIBLE")

        if product_negative_reasons:
            result = "PRODUCT_NEGATIVE"
        elif cancel is None:
            result = "EVIDENCE_INCOMPLETE_NO_SINK_CANCEL_BOUNDARY"
        elif not admitted:
            result = "EVIDENCE_INCOMPLETE_NO_SINK_ADMISSION"
        elif not packet_commit_fence:
            result = "EVIDENCE_INVALID_PACKET_COMMIT_FENCE_NOT_OBSERVED"
        else:
            result = "EXECUTED_NO_COUNTEREXAMPLE_AT_RUN_LOCAL_SINK_PACKET_SCOPE"

        return {
            "schema": SCHEMA,
            "classification": CLASSIFICATION,
            "result": result,
            "voice_session_id": self.voice_session_id,
            "turn_id": self.turn_id,
            "voice_output_packet_id": self.voice_output_packet_id,
            "voice_output_packet_sha256": packet.sha256(),
            "request_admission_monotonic_ms": self.request_admission_monotonic_ms,
            "first_generated_chunk_monotonic_ms": first_generated,
            "first_sink_admission_monotonic_ms": first_sink,
            "request_to_first_generated_chunk_ms": first_generated - self.request_admission_monotonic_ms,
            "request_to_first_sink_admission_ms": (
                None if first_sink is None else first_sink - self.request_admission_monotonic_ms
            ),
            "producer_cancel_capability": self.producer_cancel_capability,
            "producer_cancel_requested_monotonic_ms": self.producer_cancel_requested_monotonic_ms,
            "producer_cancel_executed": self.producer_cancel_executed,
            "producer_generation_cancel_candidate": producer_cancel,
            "sink_cancel_boundary_monotonic_ms": cancel,
            "sink_last_admission_monotonic_ms": last_sink,
            "sink_post_cancel_admission_count": len(post_cancel_admitted),
            "generated_after_cancel_count": len(generated_after_cancel),
            "generated_after_cancel_discarded_count": len(discarded_after_cancel),
            "sink_delivery_cancel_candidate": sink_delivery_cancel,
            "packet_commit_fence_candidate": packet_commit_fence,
            "playback_state": packet.playback_state,
            "heard_fraction": packet.heard_fraction,
            "commit_eligible": packet.commit_eligible,
            "voiceoutcome_ref": packet.voiceoutcome_ref,
            "chunks": [item.as_dict() for item in self._chunks],
            "product_negative_reasons": product_negative_reasons,
            "credit_boundary": {
                "run_local_sink_delivery_evidence_candidate": int(
                    result == "EXECUTED_NO_COUNTEREXAMPLE_AT_RUN_LOCAL_SINK_PACKET_SCOPE"
                ),
                "producer_generation_cancel": 0,
                "physical_cancellation_to_silence": 0,
                "human_heard_output": 0,
                "physical_speaker": 0,
                "whole_voice_system": 0,
                "whole_product": 0,
            },
        }
