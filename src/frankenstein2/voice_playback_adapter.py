"""Deterministic VoiceOutputPacket terminal-state -> playback-process adapter.

The adapter owns no cancellation policy and cannot make an output terminal by
itself. It only translates an already-authoritative VoicePacketCortex barge-in
terminal event for the exact packet into termination of the bound playback
client. This prevents test/runtime code from becoming a second cancel authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import subprocess
import time
from typing import Any

from .voice_packet_cortex import CortexEventPacket, VoiceOutputPacket

ADAPTER_SCHEMA = "FRANKENSTEIN2_VOICE_PACKET_PLAYBACK_CANCELLATION_ADAPTER/v1"
ADAPTER_ID = "voice-output-packet-terminal-event-to-bound-playback-process"


class PlaybackCancellationAdapterError(ValueError):
    """Fail-closed causal binding error."""


def _module_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class PlaybackCancellationReceipt:
    schema: str
    adapter_id: str
    adapter_module_sha256: str
    voice_session_id: str
    voice_output_packet_id: str
    voice_output_packet_sha256: str
    cancel_event_id: str
    cancel_event_kind: str
    cancel_event_monotonic_ms: int
    playback_process_pid: int
    process_alive_before_propagation: bool
    propagation_started_monotonic_ns: int
    playback_terminal_monotonic_ns: int
    terminal_method: str
    process_returncode: int
    independent_test_kill_before_propagation: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "adapter_id": self.adapter_id,
            "adapter_module_sha256": self.adapter_module_sha256,
            "voice_session_id": self.voice_session_id,
            "voice_output_packet_id": self.voice_output_packet_id,
            "voice_output_packet_sha256": self.voice_output_packet_sha256,
            "cancel_event_id": self.cancel_event_id,
            "cancel_event_kind": self.cancel_event_kind,
            "cancel_event_monotonic_ms": self.cancel_event_monotonic_ms,
            "playback_process_pid": self.playback_process_pid,
            "process_alive_before_propagation": self.process_alive_before_propagation,
            "propagation_started_monotonic_ns": self.propagation_started_monotonic_ns,
            "playback_terminal_monotonic_ns": self.playback_terminal_monotonic_ns,
            "terminal_method": self.terminal_method,
            "process_returncode": self.process_returncode,
            "independent_test_kill_before_propagation": self.independent_test_kill_before_propagation,
        }


def propagate_packet_cancellation_to_process(
    *,
    packet: VoiceOutputPacket,
    cancel_event: CortexEventPacket,
    process: subprocess.Popen,
    timeout_s: float = 3.0,
) -> PlaybackCancellationReceipt:
    """Terminate one bound playback client only after authoritative packet cancellation.

    SIGTERM/SIGKILL here are transport translations caused by the exact admitted
    barge-in event; they are not independent test decisions. A process that is
    already terminal before propagation is rejected as causally ambiguous.
    """
    if type(packet) is not VoiceOutputPacket:
        raise PlaybackCancellationAdapterError("packet must be exact VoiceOutputPacket")
    if type(cancel_event) is not CortexEventPacket:
        raise PlaybackCancellationAdapterError("cancel_event must be exact CortexEventPacket")
    if packet.playback_state not in ("interrupted", "cancelled") or packet.commit_eligible:
        raise PlaybackCancellationAdapterError("packet is not authoritative non-commit terminal output")
    if cancel_event.event_kind != "BARGE_IN_CANCEL_PROPAGATED":
        raise PlaybackCancellationAdapterError("cancel event kind is not admitted barge-in propagation")
    if cancel_event.session_id != packet.session_id:
        raise PlaybackCancellationAdapterError("cancel event session does not match packet")
    if packet.packet_id not in cancel_event.packet_refs:
        raise PlaybackCancellationAdapterError("cancel event does not reference bound packet")
    if packet.interruption_ms != cancel_event.monotonic_ms:
        raise PlaybackCancellationAdapterError("packet interruption clock does not match cancel event")
    pid = getattr(process, "pid", None)
    if type(pid) is not int or pid <= 0:
        raise PlaybackCancellationAdapterError("playback process pid is invalid")
    if process.poll() is not None:
        raise PlaybackCancellationAdapterError("playback already terminal before cancel propagation")
    if timeout_s <= 0:
        raise PlaybackCancellationAdapterError("timeout_s must be positive")

    started_ns = time.monotonic_ns()
    terminal_method = "SIGTERM_BY_PACKET_CANCEL_ADAPTER"
    process.terminate()
    try:
        returncode = int(process.wait(timeout=timeout_s))
    except subprocess.TimeoutExpired:
        terminal_method = "SIGTERM_THEN_SIGKILL_BY_PACKET_CANCEL_ADAPTER"
        process.kill()
        returncode = int(process.wait(timeout=timeout_s))
    terminal_ns = time.monotonic_ns()
    if process.poll() is None:
        raise PlaybackCancellationAdapterError("playback process did not terminalize after propagation")

    return PlaybackCancellationReceipt(
        schema=ADAPTER_SCHEMA,
        adapter_id=ADAPTER_ID,
        adapter_module_sha256=_module_sha256(),
        voice_session_id=packet.session_id,
        voice_output_packet_id=packet.packet_id,
        voice_output_packet_sha256=packet.sha256(),
        cancel_event_id=cancel_event.event_id,
        cancel_event_kind=cancel_event.event_kind,
        cancel_event_monotonic_ms=cancel_event.monotonic_ms,
        playback_process_pid=pid,
        process_alive_before_propagation=True,
        propagation_started_monotonic_ns=started_ns,
        playback_terminal_monotonic_ns=terminal_ns,
        terminal_method=terminal_method,
        process_returncode=returncode,
        independent_test_kill_before_propagation=False,
    )
