from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoiceInputPacket, VoicePacketCortex, VoicePacketCortexError


class VoicePacketCortexTests(unittest.TestCase):
    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-t7-packet",
            agent_id="frankenstein-2",
            task_id="task-t7-packet",
            turn_id="turn-input",
            causal_id="causal-input-t7-packet",
            generation=3,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="packet-fixture:de-turn",
            input_sha256="a" * 64,
            provenance_refs=("trigger7:packet-fixture",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-t7-packet", generation=4, turn_id="turn-session"
            ),
            provenance_refs=("trigger7:packet-session",),
        )

    def input_packet(self, cortex: VoicePacketCortex, **overrides) -> VoiceInputPacket:
        values = dict(
            session_id=cortex.session_id,
            turn_id="turn-1",
            packet_id="input-0",
            monotonic_ms=100,
            source_modality="asr_partial",
            text="Guten",
            language="de-DE",
            is_final=False,
            confidence=0.91,
            speech_start=True,
            speech_end=False,
            vad_state="SPEECH",
            endpoint_decision="HOLD",
            overlap_state="NONE",
            barge_in=False,
            source_duration_ms=160,
            sequence=0,
        )
        values.update(overrides)
        return VoiceInputPacket(**values)

    def test_partial_then_final_preserves_turn_order_and_endpoint(self) -> None:
        cortex = VoicePacketCortex(self.session())
        partial = self.input_packet(cortex)
        final = self.input_packet(
            cortex,
            packet_id="input-1",
            monotonic_ms=260,
            source_modality="asr_final",
            text="Guten Morgen",
            is_final=True,
            confidence=0.96,
            speech_start=False,
            speech_end=True,
            endpoint_decision="END",
            sequence=1,
        )
        self.assertEqual(cortex.accept_input(partial).event_kind, "SPEECH_START_ASR_PARTIAL")
        self.assertEqual(cortex.accept_input(final).event_kind, "ASR_FINAL_SPEECH_END")
        with self.assertRaises(VoicePacketCortexError):
            cortex.accept_input(self.input_packet(cortex, packet_id="input-2", sequence=2))

    def test_barge_in_interrupts_started_output_and_revokes_commit(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-0", monotonic_ms=10,
            text_segment="Ich erkläre das gerade.", expression_intent="neutral",
            speech_act="ANSWER", planned_audio_duration_ms=1200, sequence=0,
        )
        cortex.advance_output("output-0", playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        cortex.advance_output("output-0", playback_state="heard", monotonic_ms=200, heard_fraction=0.2)
        event = cortex.accept_input(
            self.input_packet(cortex, barge_in=True, overlap_state="USER_OVER_OUTPUT")
        )
        self.assertEqual(event.event_kind, "SPEECH_START_ASR_PARTIAL")
        output = cortex.outputs[0]
        self.assertEqual(output.playback_state, "interrupted")
        self.assertEqual(output.heard_fraction, 0.2)
        self.assertFalse(output.commit_eligible)
        self.assertIn("BARGE_IN_CANCEL_PROPAGATED", [item.event_kind for item in cortex.events])

    def test_unheard_queued_output_is_cancelled_not_committed(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-queued", monotonic_ms=10,
            text_segment="Noch nicht abgespielt", expression_intent="neutral",
            speech_act="ANSWER", planned_audio_duration_ms=800, sequence=0,
        )
        self.assertEqual(cortex.cancel_for_barge_in(turn_id="turn-1", monotonic_ms=11), ("output-queued",))
        output = cortex.outputs[0]
        self.assertEqual(output.playback_state, "cancelled")
        self.assertEqual(output.heard_fraction, 0.0)
        self.assertFalse(output.commit_eligible)

    def test_completed_output_is_only_full_segment_commit_path(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-0", monotonic_ms=10,
            text_segment="Fertig.", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=300, sequence=0,
        )
        cortex.advance_output("output-0", playback_state="started", monotonic_ms=15, heard_fraction=0.0)
        completed = cortex.advance_output("output-0", playback_state="completed", monotonic_ms=315, heard_fraction=1.0)
        self.assertTrue(completed.commit_eligible)
        with self.assertRaises(VoicePacketCortexError):
            cortex.advance_output("output-0", playback_state="heard", monotonic_ms=320, heard_fraction=1.0)

    def test_duplicate_is_idempotent_but_same_id_changed_content_fails(self) -> None:
        cortex = VoicePacketCortex(self.session())
        packet = self.input_packet(cortex)
        cortex.accept_input(packet)
        self.assertEqual(cortex.accept_input(packet).event_kind, "INPUT_DUPLICATE_IGNORED")
        with self.assertRaises(VoicePacketCortexError):
            cortex.accept_input(replace(packet, text="verändert"))

    def test_drop_reorder_and_corruption_faults_are_explicit(self) -> None:
        cortex = VoicePacketCortex(self.session())
        dropped = self.input_packet(cortex, packet_id="drop-0", fault_flags=("drop",))
        self.assertEqual(cortex.accept_input(dropped).event_kind, "INPUT_DROP_INJECTED")
        reordered = self.input_packet(cortex, packet_id="reorder-2", sequence=2, fault_flags=("reorder",))
        self.assertEqual(cortex.accept_input(reordered).event_kind, "INPUT_REORDER_REJECTED")
        corrupt = self.input_packet(cortex, packet_id="corrupt-0", fault_flags=("corrupt",))
        with self.assertRaises(VoicePacketCortexError):
            cortex.accept_input(corrupt)

    def test_wait_backchannel_tool_gwt_and_memory_refs_share_one_event_fabric(self) -> None:
        cortex = VoicePacketCortex(self.session())
        wait = cortex.emit_intent(
            turn_id="turn-1", monotonic_ms=100, voice_intent="WAIT",
            gwt_ref="gwt:broadcast-1", memory_refs=("memory:fact-1",), detail="user still speaking",
        )
        backchannel = cortex.emit_intent(
            turn_id="turn-1", monotonic_ms=120, voice_intent="BACKCHANNEL", detail="mhm",
        )
        tool = cortex.emit_intent(
            turn_id="turn-1", monotonic_ms=140, voice_intent="TOOL_USE",
            tool_ref="tool:status-read", memory_refs=("memory:fact-1",),
        )
        self.assertEqual((wait.voice_intent, backchannel.voice_intent, tool.voice_intent),
                         ("WAIT", "BACKCHANNEL", "TOOL_USE"))
        self.assertEqual(tool.tool_ref, "tool:status-read")

    def test_close_binds_existing_voice_outcome_contract(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-0", monotonic_ms=10,
            text_segment="Bis gleich.", expression_intent="warm", speech_act="CLOSE",
            planned_audio_duration_ms=500, sequence=0,
        )
        cortex.advance_output("output-0", playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        cortex.advance_output("output-0", playback_state="completed", monotonic_ms=520, heard_fraction=1.0)
        outcome = cortex.close_session(
            turn_id="turn-close", monotonic_ms=530,
            outcome_causal_identity=session.session_causal_identity.derive(
                causal_id="causal-outcome-t7-packet", generation=5, turn_id="turn-outcome"
            ),
            outcome_kind=OUTCOME_RETURNED,
            result_ref="voice-result:t7-packet",
            result_sha256="b" * 64,
        )
        self.assertEqual(outcome.voice_session_id, session.voice_session_id)
        self.assertFalse(cortex.is_open)
        self.assertEqual(cortex.events[-1].event_kind, "SESSION_CLOSE")

    def test_close_refuses_nonterminal_output(self) -> None:
        session = self.session()
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-0", packet_id="output-open", monotonic_ms=10,
            text_segment="läuft", expression_intent="neutral", speech_act="ANSWER",
            planned_audio_duration_ms=900, sequence=0,
        )
        with self.assertRaises(VoicePacketCortexError):
            cortex.close_session(
                turn_id="turn-close", monotonic_ms=20,
                outcome_causal_identity=session.session_causal_identity.derive(
                    causal_id="causal-outcome-open", generation=5, turn_id="turn-outcome"
                ),
                outcome_kind=OUTCOME_RETURNED,
            )


if __name__ == "__main__":
    unittest.main()
