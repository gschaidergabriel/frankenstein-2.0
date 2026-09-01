"""Bounded kernel-pipe virtual-sink readback evidence for Trigger-4 voice convergence.

Evidence helper only.  It does not own playback state, VoiceOutcome state,
durable memory, or canonical acceptance.  ``VoiceOutputPacket`` remains the
semantic playback/commit authority and ``RunLocalAudioDeliveryBinding`` remains
the packet-to-audio delivery evidence binder.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import threading
from typing import Any

from frankenstein2.voice_packet_cortex import VoiceOutputPacket
from trigger4.tools.local_voice.fdx_audio_delivery_evidence import (
    RunLocalAudioDeliveryBinding,
)

SCHEMA = "T4_OWNER_VPS_FDX_KERNEL_PIPE_VIRTUAL_SINK_READBACK/v1"
CLASSIFICATION = "CANDIDATE_FALSIFIER_VIRTUAL_SINK_READBACK_ONLY"


class VirtualSinkEvidenceError(RuntimeError):
    """Fail-closed virtual-sink evidence error."""


def _exact_bytes(name: str, payload: Any) -> bytes:
    if type(payload) is not bytes or not payload:
        raise VirtualSinkEvidenceError(f"{name} must be non-empty exact bytes")
    return payload


@dataclass(frozen=True, slots=True)
class KernelPipeReadback:
    byte_count: int
    sha256: str
    eof_observed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "byte_count": self.byte_count,
            "sha256": self.sha256,
            "eof_observed": self.eof_observed,
        }


class KernelPipeVirtualSink:
    """A bounded POSIX-pipe sink with an independent reader and exact readback."""

    def __init__(self) -> None:
        self._read_fd, self._write_fd = os.pipe()
        self._reader_bytes = bytearray()
        self._reader_error: BaseException | None = None
        self._eof_observed = False
        self._cancelled = False
        self._reader = threading.Thread(
            target=self._drain,
            name="f2-fdx-kernel-pipe-virtual-sink",
            daemon=True,
        )
        self._reader.start()

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def _drain(self) -> None:
        try:
            while True:
                block = os.read(self._read_fd, 65536)
                if not block:
                    self._eof_observed = True
                    break
                self._reader_bytes.extend(block)
        except BaseException as exc:  # evidence path must surface reader failures
            self._reader_error = exc
        finally:
            try:
                os.close(self._read_fd)
            except OSError:
                pass

    def write(self, payload: bytes) -> int:
        payload = _exact_bytes("payload", payload)
        if self._cancelled:
            raise VirtualSinkEvidenceError("virtual sink is cancelled; post-cancel write rejected")
        sent = 0
        while sent < len(payload):
            try:
                written = os.write(self._write_fd, payload[sent:])
            except OSError as exc:
                raise VirtualSinkEvidenceError(f"kernel-pipe sink write failed: {exc}") from exc
            if written <= 0:
                raise VirtualSinkEvidenceError("kernel-pipe sink write made no forward progress")
            sent += written
        return sent

    def cancel_and_readback(self) -> KernelPipeReadback:
        if self._cancelled:
            raise VirtualSinkEvidenceError("virtual sink cancellation already executed")
        self._cancelled = True
        try:
            os.close(self._write_fd)
        except OSError as exc:
            raise VirtualSinkEvidenceError(f"kernel-pipe sink close failed: {exc}") from exc
        self._reader.join(timeout=5.0)
        if self._reader.is_alive():
            raise VirtualSinkEvidenceError("kernel-pipe reader did not reach EOF after cancellation")
        if self._reader_error is not None:
            raise VirtualSinkEvidenceError(
                f"kernel-pipe reader failed: {self._reader_error}"
            ) from self._reader_error
        payload = bytes(self._reader_bytes)
        return KernelPipeReadback(
            byte_count=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            eof_observed=self._eof_observed,
        )


def exercise_interrupted_packet_virtual_sink(
    *,
    packet: VoiceOutputPacket,
    pre_cancel_audio_bytes: bytes,
    post_cancel_generated_audio_bytes: bytes,
    request_admission_monotonic_ms: int,
    generated_monotonic_ms: int,
    sink_admission_monotonic_ms: int,
    cancel_monotonic_ms: int,
    post_cancel_generated_monotonic_ms: int,
    sample_rate: int,
    pre_cancel_sample_count: int,
    post_cancel_sample_count: int,
) -> dict[str, Any]:
    """Bind byte-identical kernel-pipe readback and cancellation to one packet.

    The post-cancel audio bytes are deliberately generated but must not be
    admitted to the sink.  This is not physical playback or human-heard proof.
    """
    if type(packet) is not VoiceOutputPacket:
        raise VirtualSinkEvidenceError("packet must be exact VoiceOutputPacket")
    pre = _exact_bytes("pre_cancel_audio_bytes", pre_cancel_audio_bytes)
    post = _exact_bytes("post_cancel_generated_audio_bytes", post_cancel_generated_audio_bytes)

    binding = RunLocalAudioDeliveryBinding(
        voice_session_id=packet.session_id,
        turn_id=packet.turn_id,
        voice_output_packet_id=packet.packet_id,
        request_admission_monotonic_ms=request_admission_monotonic_ms,
        producer_cancel_capability=False,
    )
    sink = KernelPipeVirtualSink()
    written = sink.write(pre)
    if written != len(pre):
        raise VirtualSinkEvidenceError("virtual sink did not accept the complete pre-cancel chunk")
    binding.record_chunk(
        sequence=0,
        generated_monotonic_ms=generated_monotonic_ms,
        sample_rate=sample_rate,
        sample_count=pre_cancel_sample_count,
        canonical_audio_bytes=pre,
        sink_admission_monotonic_ms=sink_admission_monotonic_ms,
    )

    binding.cancel_sink(monotonic_ms=cancel_monotonic_ms)
    readback = sink.cancel_and_readback()
    if readback.byte_count != len(pre):
        raise VirtualSinkEvidenceError("virtual sink readback byte count drifted")
    expected_sha = hashlib.sha256(pre).hexdigest()
    if readback.sha256 != expected_sha or not readback.eof_observed:
        raise VirtualSinkEvidenceError("virtual sink readback identity/EOF invariant failed")

    post_cancel_write_rejected = False
    try:
        sink.write(post)
    except VirtualSinkEvidenceError:
        post_cancel_write_rejected = True
    if not post_cancel_write_rejected:
        raise VirtualSinkEvidenceError("post-cancel bytes were accepted by the virtual sink")

    binding.record_chunk(
        sequence=1,
        generated_monotonic_ms=post_cancel_generated_monotonic_ms,
        sample_rate=sample_rate,
        sample_count=post_cancel_sample_count,
        canonical_audio_bytes=post,
        sink_admission_monotonic_ms=None,
    )
    delivery = binding.receipt(packet=packet)
    if delivery["result"] != "EXECUTED_NO_COUNTEREXAMPLE_AT_RUN_LOCAL_SINK_PACKET_SCOPE":
        raise VirtualSinkEvidenceError(
            f"packet/sink delivery binder did not close: {delivery['result']}"
        )

    return {
        "schema": SCHEMA,
        "classification": CLASSIFICATION,
        "result": "EXECUTED_NO_COUNTEREXAMPLE_AT_KERNEL_PIPE_VIRTUAL_SINK_SCOPE",
        "voice_session_id": packet.session_id,
        "turn_id": packet.turn_id,
        "voice_output_packet_id": packet.packet_id,
        "voice_output_packet_sha256": packet.sha256(),
        "transport": "POSIX_KERNEL_PIPE",
        "pre_cancel_generated_sha256": expected_sha,
        "pre_cancel_sink_readback": readback.as_dict(),
        "post_cancel_generated_sha256": hashlib.sha256(post).hexdigest(),
        "post_cancel_write_rejected": post_cancel_write_rejected,
        "delivery_receipt": delivery,
        "credit_boundary": {
            "virtual_sink_byte_identical_readback_candidate": 1,
            "virtual_sink_cancel_to_eof_candidate": 1,
            "post_cancel_sink_admission_fence_candidate": 1,
            "physical_audio": 0,
            "physical_speaker": 0,
            "human_heard_output": 0,
            "acoustic_cancellation_to_silence": 0,
            "whole_voice_system": 0,
            "whole_product": 0,
        },
    }
