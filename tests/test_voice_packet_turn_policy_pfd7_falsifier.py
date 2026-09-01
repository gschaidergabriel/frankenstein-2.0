from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoiceInputPacket, VoicePacketCortex
from frankenstein2.voice_packet_turn_policy import (
    PacketTurnPolicy,
    PacketTurnPolicyError,
    apply_packet_turn_policy,
)


class WP720PFD7StaleHoldFalsifier(unittest.TestCase):
    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-wp720-pfd7",
            agent_id="frankenstein-2",
            task_id="task-wp720-pfd7",
            turn_id="turn-root",
            causal_id="causal-root-wp720-pfd7",
            generation=1,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="wp720:pfd7:stale-hold",
            input_sha256="8" * 64,
            provenance_refs=("trigger4:wp720-pfd7-review",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-wp720-pfd7",
                generation=2,
                turn_id="turn-session",
            ),
            provenance_refs=("trigger4:wp720-pfd7-review-session",),
        )

    def test_stale_hold_event_cannot_emit_policy_intent_after_later_final_endpoint(self) -> None:
        cortex = VoicePacketCortex(self.session())
        hold = VoiceInputPacket(
            session_id=cortex.session_id,
            turn_id="turn-1",
            packet_id="input-hold-0",
            monotonic_ms=100,
            source_modality="asr_partial",
            text="Ich spreche noch",
            language="de-DE",
            is_final=False,
            confidence=0.97,
            speech_start=True,
            speech_end=False,
            vad_state="SPEECH",
            endpoint_decision="HOLD",
            overlap_state="NONE",
            barge_in=False,
            source_duration_ms=160,
            sequence=0,
        )
        hold_event = cortex.accept_input(hold)

        final = VoiceInputPacket(
            session_id=cortex.session_id,
            turn_id="turn-1",
            packet_id="input-final-1",
            monotonic_ms=200,
            source_modality="asr_final",
            text="Jetzt bin ich fertig",
            language="de-DE",
            is_final=True,
            confidence=0.99,
            speech_start=False,
            speech_end=True,
            vad_state="SPEECH",
            endpoint_decision="END",
            overlap_state="NONE",
            barge_in=False,
            source_duration_ms=220,
            sequence=1,
        )
        final_event = cortex.accept_input(final)
        self.assertIn("ASR_FINAL", final_event.event_kind)
        self.assertEqual(final_event.turn_id, hold_event.turn_id)

        before = tuple(event.as_dict() for event in cortex.events)
        policy = PacketTurnPolicy(
            policy_id="wp720-pfd7-backchannel",
            hold_intent="BACKCHANNEL",
            provenance_refs=("trigger4:wp720-pfd7-review",),
        )
        with self.assertRaises(PacketTurnPolicyError):
            apply_packet_turn_policy(cortex, hold_event, policy, monotonic_ms=210)
        after = tuple(event.as_dict() for event in cortex.events)
        self.assertEqual(after, before, "rejected stale HOLD policy application must be observationally atomic")


if __name__ == "__main__":
    unittest.main()
