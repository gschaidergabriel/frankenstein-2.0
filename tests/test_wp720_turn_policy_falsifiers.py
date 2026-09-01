from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import (
    PacketTurnPolicy,
    VoiceInputPacket,
    VoicePacketCortex,
    VoicePacketCortexError,
)


class WP720IntegratedTurnPolicyFalsifiers(unittest.TestCase):
    def make_session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-wp720-integrated",
            agent_id="frankenstein-2",
            task_id="task-wp720-integrated",
            turn_id="turn-root",
            causal_id="causal-root-wp720-integrated",
            generation=1,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="wp720:integrated-policy-falsifier",
            input_sha256="7" * 64,
            provenance_refs=("trigger4:wp720-integrated-policy",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-wp720-integrated",
                generation=2,
                turn_id="turn-session",
            ),
            provenance_refs=("trigger4:wp720-integrated-policy-session",),
        )

    def hold_packet(self, cortex: VoicePacketCortex) -> VoiceInputPacket:
        return VoiceInputPacket(
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

    def final_packet(self, cortex: VoicePacketCortex) -> VoiceInputPacket:
        return VoiceInputPacket(
            session_id=cortex.session_id,
            turn_id="turn-1",
            packet_id="input-final-1",
            monotonic_ms=120,
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
            source_duration_ms=320,
            sequence=1,
        )

    @staticmethod
    def policy(intent: str) -> PacketTurnPolicy:
        return PacketTurnPolicy(
            policy_id="wp720-integrated-policy",
            hold_intent=intent,
            provenance_refs=("policy:wp720-integrated-v1",),
        )

    def test_pfd6_same_hold_replay_is_idempotent_and_conflicting_rebind_fails_closed(self) -> None:
        cortex = VoicePacketCortex(self.make_session())
        hold = self.hold_packet(cortex)
        cortex.accept_input(hold)

        wait = self.policy("WAIT")
        first = cortex.apply_turn_policy(hold, wait)
        replay = cortex.apply_turn_policy(hold, wait)
        self.assertEqual(replay, first)

        with self.assertRaises(VoicePacketCortexError):
            cortex.apply_turn_policy(hold, self.policy("BACKCHANNEL"))

        decisions = [
            event for event in cortex.events
            if event.event_kind == "TURN_POLICY_DECISION" and event.packet_refs == (hold.packet_id,)
        ]
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].voice_intent, "WAIT")

    def test_pfd7_stale_hold_after_later_final_endpoint_fails_closed_atomically(self) -> None:
        cortex = VoicePacketCortex(self.make_session())
        hold = self.hold_packet(cortex)
        cortex.accept_input(hold)
        cortex.accept_input(self.final_packet(cortex))
        before = tuple(cortex.events)

        with self.assertRaises(VoicePacketCortexError):
            cortex.apply_turn_policy(hold, self.policy("BACKCHANNEL"))

        self.assertEqual(tuple(cortex.events), before)
        self.assertFalse(
            any(
                event.event_kind == "TURN_POLICY_DECISION"
                and event.packet_refs == (hold.packet_id,)
                for event in cortex.events
            )
        )


if __name__ == "__main__":
    unittest.main()
