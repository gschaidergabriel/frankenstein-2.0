#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import unittest

from frankenstein2.voice_packet_cortex import CortexEventPacket, VoiceOutputPacket
from frankenstein2.voice_playback_adapter import (
    PlaybackCancellationAdapterError,
    propagate_packet_cancellation_to_process,
)


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "trigger4/tools/local_voice/g2_pipewire_s2_runtime.py"
LAUNCHER = ROOT / "trigger4/tools/local_voice/run_g2_pipewire_s2.sh"
WORKFLOW = ROOT / ".github/workflows/t4-g2-pipewire-monitor-cancel.yml"
ADAPTER = ROOT / "src/frankenstein2/voice_playback_adapter.py"


class FakeProcess:
    def __init__(self, *, pid: int = 4242, terminal: bool = False) -> None:
        self.pid = pid
        self.returncode = 0 if terminal else None
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.returncode = -15

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def interrupted_packet() -> VoiceOutputPacket:
    return VoiceOutputPacket(
        session_id="session:test",
        turn_id="turn-a",
        packet_id="output-old-g2-pipewire",
        monotonic_ms=120,
        text_segment="old output",
        expression_intent="neutral",
        speech_act="ANSWER",
        planned_audio_duration_ms=4000,
        first_output_ms=10,
        sequence=0,
        cancellable=True,
        playback_state="interrupted",
        heard_fraction=0.0,
        interruption_ms=120,
        commit_eligible=False,
    )


def cancel_event(packet_id: str = "output-old-g2-pipewire") -> CortexEventPacket:
    return CortexEventPacket(
        session_id="session:test",
        turn_id="turn-b",
        event_id="cortex-event:session:test:00000004",
        monotonic_ms=120,
        event_kind="BARGE_IN_CANCEL_PROPAGATED",
        voice_intent="WAIT",
        presence_state="PRESENT_INTERRUPTIBLE",
        packet_refs=(packet_id,),
        detail="authoritative barge-in",
    )


class Trigger4G2ProductCancelBindingTests(unittest.TestCase):
    def test_authoritative_cancel_event_terminalizes_exact_bound_process(self) -> None:
        process = FakeProcess()
        receipt = propagate_packet_cancellation_to_process(
            packet=interrupted_packet(),
            cancel_event=cancel_event(),
            process=process,
        )
        self.assertEqual(process.terminate_calls, 1)
        self.assertEqual(process.kill_calls, 0)
        self.assertEqual(receipt.voice_output_packet_id, "output-old-g2-pipewire")
        self.assertEqual(receipt.cancel_event_kind, "BARGE_IN_CANCEL_PROPAGATED")
        self.assertFalse(receipt.independent_test_kill_before_propagation)
        self.assertTrue(receipt.process_alive_before_propagation)

    def test_already_terminal_process_is_rejected_as_causally_ambiguous(self) -> None:
        with self.assertRaisesRegex(PlaybackCancellationAdapterError, "already terminal"):
            propagate_packet_cancellation_to_process(
                packet=interrupted_packet(),
                cancel_event=cancel_event(),
                process=FakeProcess(terminal=True),
            )

    def test_unrelated_event_cannot_stop_playback(self) -> None:
        process = FakeProcess()
        with self.assertRaisesRegex(PlaybackCancellationAdapterError, "does not reference bound packet"):
            propagate_packet_cancellation_to_process(
                packet=interrupted_packet(),
                cancel_event=cancel_event("different-output"),
                process=process,
            )
        self.assertEqual(process.terminate_calls, 0)

    def test_harness_uses_product_adapter_and_fails_closed_on_required_observables(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        self.assertIn("propagate_packet_cancellation_to_process(", text)
        self.assertNotIn("def stop_playback(", text)
        self.assertIn("CANONICAL_REQUIRED_OBSERVABLES_INCOMPLETE", text)
        for name in (
            "tts_runtime_binary_sha256",
            "playback_stream_identity",
            "capture_stream_identity",
            "pipewire_quantum_and_reported_latency",
        ):
            self.assertIn(name, text)

    def test_launcher_predeclares_pipewire_bound_and_uses_h4_analyzer(self) -> None:
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("derive-bound", text)
        self.assertIn("G2_MAX_INFLIGHT_MS_PREDECLARED", text)
        self.assertIn("t7_pipewire_g2_h4_guard.py", text)
        self.assertNotIn("--max-inflight-ms 250", text)

    def test_workflow_hashes_all_promotion_bearing_surfaces(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        for path in (
            "src/frankenstein2/voice_packet_cortex.py",
            "src/frankenstein2/voice_playback_adapter.py",
            "trigger4/tools/local_voice/g2_pipewire_evidence.py",
            "trigger4/tools/local_voice/g2_pipewire_s2_runtime.py",
            "trigger4/tools/local_voice/run_g2_pipewire_s2.sh",
            "research/local_voice/tools/t7_pipewire_g2_h4_guard.py",
            "research/local_voice/tools/t7_pipewire_monitor_cancel_analyze.py",
            "research/local_voice/benchmarks/2026-09-02_TRIGGER7_COMPLETION_DEPTH_G2.json",
        ):
            self.assertIn(path, text)


if __name__ == "__main__":
    unittest.main()
