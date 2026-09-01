from __future__ import annotations

from dataclasses import replace
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
    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-wp720-integrated",
            agent_id="frankenstein-2",
            task_id="task-wp720-integrated",
            turn_id="turn-input",
            causal_id="causal-input-wp720-integrated",
            generation=1,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="wp720:integrated-policy-falsifier",
            input_sha256="8" * 64,
            provenance_refs=("trigger4:wp720-integrated-falsifier",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-wp720-integrated",
                generation=2,
                turn_id="turn-session",
            ),
            provenance_refs=("trigger4:wp720-integrated-session",),
        )

    def hold(self, cortex: VoicePacketCortex) -> VoiceInputPacket:
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

    def policy(self, hold_intent: str) -> PacketTurnPolicy:
        return PacketTurnPolicy(
            policy_id="packet-policy:wp720-authoritative",
            hold_intent=hold_intent,
            provenance_refs=("trigger4:wp720-pfd6-pfd7",),
        )

    def test_pfd6_one_accepted_hold_cannot_mint_conflicting_policy_decisions(self) -> None:
        cortex = VoicePacketCortex(self.session())
        packet = self.hold(cortex)
        cortex.accept_input(packet)
        wait = self.policy("WAIT")
        first = cortex.apply_turn_policy(packet, wait)
        self.assertEqual(first.event_kind, "TURN_POLICY_DECISION")
        self.assertEqual(first.voice_intent, "WAIT")
        self.assertIs(cortex.apply_turn_policy(packet, wait), first, "exact replay must be idempotent")
        with self.assertRaises(VoicePacketCortexError):
            cortex.apply_turn_policy(packet, replace(wait, hold_intent="BACKCHANNEL"))
        decisions = [
            event
            for event in cortex.events
            if event.event_kind == "TURN_POLICY_DECISION" and event.packet_refs == (packet.packet_id,)
        ]
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].voice_intent, "WAIT")

    def test_pfd7_stale_hold_cannot_emit_after_later_final_endpoint(self) -> None:
        cortex = VoicePacketCortex(self.session())
        hold = self.hold(cortex)
        cortex.accept_input(hold)
        final = VoiceInputPacket(
            session_id=cortex.session_id,
            turn_id=hold.turn_id,
            packet_id="input-final-1",
            monotonic_ms=260,
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
        final_event = cortex.accept_input(final)
        self.assertEqual(final_event.event_kind, "ASR_FINAL_SPEECH_END")
        event_count = len(cortex.events)
        with self.assertRaises(VoicePacketCortexError):
            cortex.apply_turn_policy(hold, self.policy("BACKCHANNEL"))
        self.assertEqual(len(cortex.events), event_count, "rejected stale HOLD policy must be event-atomic")
        self.assertFalse(
            any(
                event.event_kind == "TURN_POLICY_DECISION" and event.packet_refs == (hold.packet_id,)
                for event in cortex.events
            )
        )


if __name__ == "__main__":
    unittest.main()
