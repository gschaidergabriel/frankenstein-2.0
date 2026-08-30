from __future__ import annotations

from copy import deepcopy
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoiceInputPacket, VoicePacketCortex, VoicePacketCortexError
from frankenstein2.voice_packet_cortex_recovery import (
    export_packet_cortex_checkpoint,
    packet_latency_report,
    resume_packet_cortex,
)


class VoicePacketCortexRecoveryTests(unittest.TestCase):
    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-t7-recovery",
            agent_id="frankenstein-2",
            task_id="task-t7-recovery",
            turn_id="turn-root",
            causal_id="causal-root-t7-recovery",
            generation=8,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="packet-fixture:recovery",
            input_sha256="c" * 64,
            provenance_refs=("trigger7:recovery-fixture",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-t7-recovery", generation=9, turn_id="turn-session"
            ),
            provenance_refs=("trigger7:recovery-session",),
        )

    def final_input(self, cortex: VoicePacketCortex, turn: str, packet: str, at: int, *, faults=()) -> VoiceInputPacket:
        return VoiceInputPacket(
            session_id=cortex.session_id,
            turn_id=turn,
            packet_id=packet,
            monotonic_ms=at,
            source_modality="asr_final",
            text="Weiter bitte",
            language="de-DE",
            is_final=True,
            confidence=0.95,
            speech_start=True,
            speech_end=True,
            vad_state="SPEECH",
            endpoint_decision="END",
            overlap_state="NONE",
            barge_in=False,
            source_duration_ms=160,
            sequence=0,
            fault_flags=faults,
        )

    def test_checkpoint_resume_preserves_exact_state_and_adds_reentry_event(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.accept_input(self.final_input(cortex, "turn-1", "input-1", 100))
        cortex.emit_intent(turn_id="turn-1", monotonic_ms=110, voice_intent="ANSWER")
        cortex.queue_output(
            turn_id="turn-1", packet_id="output-1", monotonic_ms=120,
            text_segment="Ja.", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=300, sequence=0,
        )
        cortex.advance_output("output-1", playback_state="started", monotonic_ms=130, heard_fraction=0.0)
        checkpoint = export_packet_cortex_checkpoint(cortex)
        resumed = resume_packet_cortex(session, checkpoint, monotonic_ms=200)
        self.assertEqual(resumed.session_id, cortex.session_id)
        self.assertEqual(resumed.outputs[0].playback_state, "started")
        self.assertEqual(resumed.events[-1].event_kind, "RESTART_REENTRY")
        self.assertEqual(len(resumed.events), len(cortex.events) + 1)

    def test_checkpoint_digest_and_session_binding_fail_closed(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        checkpoint = export_packet_cortex_checkpoint(cortex)
        tampered = deepcopy(checkpoint)
        tampered["payload"]["event_seq"] = 999
        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(session, tampered, monotonic_ms=10)

        other_root = CausalIdentity(
            session_id="other-session", agent_id="frankenstein-2", task_id="other-task",
            turn_id="other-turn", causal_id="other-causal", generation=1,
        )
        other_intent = VoiceIntent.create(
            causal_identity=other_root, input_ref="other:input", input_sha256="d" * 64,
            provenance_refs=("trigger7:other",),
        )
        other_session = VoiceSessionCapsule.create(
            intent=other_intent,
            session_causal_identity=other_root.derive(causal_id="other-session-causal", generation=2, turn_id="other-session-turn"),
            provenance_refs=("trigger7:other-session",),
        )
        with self.assertRaises(VoicePacketCortexError):
            resume_packet_cortex(other_session, checkpoint, monotonic_ms=10)

    def test_event_derived_latency_accounting_is_explicit(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.accept_input(self.final_input(cortex, "turn-latency", "input-latency", 100))
        cortex.emit_intent(turn_id="turn-latency", monotonic_ms=115, voice_intent="ANSWER")
        cortex.queue_output(
            turn_id="turn-latency", packet_id="output-latency", monotonic_ms=125,
            text_segment="Antwort", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=400, sequence=0,
        )
        cortex.advance_output("output-latency", playback_state="started", monotonic_ms=140, heard_fraction=0.0)
        report = packet_latency_report(cortex, "turn-latency")
        self.assertEqual(report["asr_from_speech_start_ms"], 0)
        self.assertEqual(report["decision_after_asr_ms"], 15)
        self.assertEqual(report["first_output_after_decision_ms"], 10)
        self.assertEqual(report["playback_after_first_output_ms"], 15)
        self.assertEqual(report["speech_to_playback_ms"], 40)

    def test_long_conversation_keeps_turn_sequences_independent(self) -> None:
        cortex = VoicePacketCortex(self.session())
        for index in range(100):
            turn = f"turn-{index:03d}"
            packet = f"input-{index:03d}"
            event = cortex.accept_input(self.final_input(cortex, turn, packet, 1000 + index * 10))
            self.assertIn("ASR_FINAL", event.event_kind)
            cortex.emit_intent(turn_id=turn, monotonic_ms=1001 + index * 10, voice_intent="WAIT")
        self.assertGreaterEqual(len(cortex.events), 201)

    def test_transport_fault_is_preserved_and_retry_uses_new_causal_packet_id(self) -> None:
        cortex = VoicePacketCortex(self.session())
        dropped = self.final_input(cortex, "turn-fault", "input-fault-drop", 100, faults=("drop",))
        self.assertEqual(cortex.accept_input(dropped).event_kind, "INPUT_DROP_INJECTED")
        retry = self.final_input(cortex, "turn-fault", "input-fault-retry", 110)
        self.assertIn("ASR_FINAL", cortex.accept_input(retry).event_kind)
        transport = cortex.emit_system_event(
            turn_id="turn-fault", monotonic_ms=120, event_kind="TRANSPORT_FAILURE",
            packet_refs=("input-fault-drop",), detail="injected drop; retry admitted as new packet identity",
        )
        recovery = cortex.emit_system_event(
            turn_id="turn-fault", monotonic_ms=130, event_kind="RECOVERY",
            packet_refs=("input-fault-retry",), detail="replacement packet accepted",
        )
        self.assertEqual((transport.event_kind, recovery.event_kind), ("TRANSPORT_FAILURE", "RECOVERY"))


if __name__ == "__main__":
    unittest.main()
