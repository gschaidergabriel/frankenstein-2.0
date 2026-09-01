from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoiceInputPacket, VoicePacketCortex, VoicePacketCortexError


CLASSIFICATION = "REPOSITORY_PACKET_COMPOSITION_ONLY_NOT_ASR_RUNTIME_OR_PRODUCT_CREDIT"


def make_session() -> VoiceSessionCapsule:
    root = CausalIdentity(
        session_id="session-fdx3-barge-in",
        agent_id="frankenstein-2",
        task_id="task-fdx3-barge-in",
        turn_id="turn-root-fdx3",
        causal_id="causal-root-fdx3",
        generation=1,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref="fdx3:barge-in:input",
        input_sha256="c" * 64,
        provenance_refs=(CLASSIFICATION, "trigger4:fdx3:barge-in"),
    )
    return VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id="causal-session-fdx3",
            generation=2,
            turn_id="turn-session-fdx3",
        ),
        provenance_refs=(CLASSIFICATION, "trigger4:fdx3:barge-in:session"),
    )


class Trigger4FDX3BargeInConvergenceTests(unittest.TestCase):
    """Packet-level FDX3 falsifier; no acoustic, VPS, effect, or product credit."""

    def test_barge_in_interrupts_playback_fences_tool_and_hands_control_to_new_turn(self) -> None:
        cortex = VoicePacketCortex(make_session())
        old_turn = "turn-output-before-barge-in"
        new_turn = "turn-user-barge-in"

        output = cortex.queue_output(
            turn_id=old_turn,
            packet_id="output-fdx3-0",
            monotonic_ms=100,
            text_segment="Das ist die laufende Antwort, die unterbrochen werden soll.",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=2_000,
            sequence=0,
            cancellable=True,
        )
        cortex.advance_output(output.packet_id, playback_state="started", monotonic_ms=110, heard_fraction=0.0)
        cortex.advance_output(output.packet_id, playback_state="heard", monotonic_ms=160, heard_fraction=0.35)
        cortex.emit_intent(
            turn_id=old_turn,
            monotonic_ms=170,
            voice_intent="TOOL_USE",
            tool_ref="tool:fdx3:old-turn",
            detail="outstanding tool ownership must be fenced by user barge-in",
        )

        barge_packet = VoiceInputPacket(
            session_id=cortex.session_id,
            turn_id=new_turn,
            packet_id="input-fdx3-barge-in-0",
            monotonic_ms=200,
            source_modality="asr_partial",
            text="Stopp, anders.",
            language="de-DE",
            is_final=False,
            confidence=0.95,
            speech_start=True,
            speech_end=False,
            vad_state="SPEECH",
            endpoint_decision="HOLD",
            overlap_state="USER_OVER_OUTPUT",
            barge_in=True,
            source_duration_ms=160,
            sequence=0,
            fault_flags=(),
        )
        input_event = cortex.accept_input(barge_packet)

        interrupted = next(packet for packet in cortex.outputs if packet.packet_id == output.packet_id)
        self.assertEqual(interrupted.playback_state, "interrupted")
        self.assertEqual(interrupted.heard_fraction, 0.35)
        self.assertEqual(interrupted.interruption_ms, 200)
        self.assertFalse(interrupted.commit_eligible)

        cancel_event = next(event for event in cortex.events if event.event_kind == "BARGE_IN_CANCEL_PROPAGATED")
        self.assertEqual(cancel_event.turn_id, new_turn)
        self.assertEqual(cancel_event.packet_refs, (output.packet_id,))
        cancel_index = next(i for i, event in enumerate(cortex.events) if event.event_id == cancel_event.event_id)
        input_index = next(i for i, event in enumerate(cortex.events) if event.event_id == input_event.event_id)
        self.assertLess(cancel_index, input_index)
        self.assertEqual(input_event.turn_id, new_turn)
        self.assertIn("SPEECH_START", input_event.event_kind)

        with self.assertRaises(VoicePacketCortexError):
            cortex.emit_system_event(
                turn_id=old_turn,
                monotonic_ms=205,
                event_kind="TOOL_RESULT",
                tool_ref="tool:fdx3:old-turn",
                detail="late result from pre-barge-in tool",
            )

        with self.assertRaises(VoicePacketCortexError):
            cortex.advance_output(output.packet_id, playback_state="completed", monotonic_ms=210, heard_fraction=1.0)

        resumed = cortex.queue_output(
            turn_id=new_turn,
            packet_id="output-fdx3-new-turn-0",
            monotonic_ms=220,
            text_segment="Verstanden, ich richte mich nach der Unterbrechung.",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=700,
            sequence=0,
            cancellable=True,
        )
        self.assertEqual(resumed.turn_id, new_turn)
        self.assertEqual(resumed.sequence, 0)
        self.assertFalse(resumed.commit_eligible)


if __name__ == "__main__":
    unittest.main()
