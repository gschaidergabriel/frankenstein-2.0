from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import json
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoiceInputPacket, VoicePacketCortex
from frankenstein2.voice_packet_turn_policy import (
    PacketTurnPolicy,
    PacketTurnPolicyError,
    apply_packet_turn_policy,
)


def trajectory_sha256(cortex: VoicePacketCortex) -> str:
    raw = json.dumps(
        [event.as_dict() for event in cortex.events],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class VoicePacketTurnPolicyTests(unittest.TestCase):
    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-wp720-pfd",
            agent_id="frankenstein-2",
            task_id="task-wp720-pfd",
            turn_id="turn-root",
            causal_id="causal-root-wp720-pfd",
            generation=1,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="wp720:pfd:matched-history",
            input_sha256="7" * 64,
            provenance_refs=("trigger4:wp720-pfd",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-wp720-pfd",
                generation=2,
                turn_id="turn-session",
            ),
            provenance_refs=("trigger4:wp720-pfd-session",),
        )

    def hold_packet(self, cortex: VoicePacketCortex, *, barge_in: bool = False) -> VoiceInputPacket:
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
            overlap_state="USER_OVER_OUTPUT" if barge_in else "NONE",
            barge_in=barge_in,
            source_duration_ms=160,
            sequence=0,
        )

    def policy(self, hold_intent: str, *, provenance: str = "policy:matched-v1") -> PacketTurnPolicy:
        return PacketTurnPolicy(
            policy_id="wp720-matched-policy",
            hold_intent=hold_intent,
            provenance_refs=(provenance,),
        )

    def run_arm(self, policy: PacketTurnPolicy):
        cortex = VoicePacketCortex(self.session())
        packet = self.hold_packet(cortex)
        accepted = cortex.accept_input(packet)
        pre_trajectory = trajectory_sha256(cortex)
        decision = apply_packet_turn_policy(cortex, accepted, policy, monotonic_ms=110)
        return cortex, packet, accepted, pre_trajectory, decision, trajectory_sha256(cortex)

    def test_pfd0_policy_is_immutable_serializable_and_behavior_bounded(self) -> None:
        policy = self.policy("WAIT")
        self.assertEqual(policy.as_dict()["hold_intent"], "WAIT")
        self.assertEqual(len(policy.sha256()), 64)
        with self.assertRaises(FrozenInstanceError):
            policy.hold_intent = "BACKCHANNEL"  # type: ignore[misc]
        with self.assertRaises(PacketTurnPolicyError):
            self.policy("ANSWER")

    def test_pfd1_to_pfd4_matched_history_single_policy_dimension_changes_behavior(self) -> None:
        wait = self.policy("WAIT")
        backchannel = self.policy("BACKCHANNEL")

        wait_contract = wait.as_dict()
        back_contract = backchannel.as_dict()
        self.assertEqual(
            {k: v for k, v in wait_contract.items() if k != "hold_intent"},
            {k: v for k, v in back_contract.items() if k != "hold_intent"},
        )
        self.assertNotEqual(wait_contract["hold_intent"], back_contract["hold_intent"])

        left, left_packet, left_input, left_pre, left_decision, left_post = self.run_arm(wait)
        right, right_packet, right_input, right_pre, right_decision, right_post = self.run_arm(backchannel)

        self.assertEqual(left_packet.as_dict(), right_packet.as_dict())
        self.assertEqual(left_pre, right_pre)
        self.assertEqual(left_input.as_dict(), right_input.as_dict())
        self.assertEqual(left_decision.event_id, right_decision.event_id)
        self.assertEqual(left_decision.voice_intent, "WAIT")
        self.assertEqual(right_decision.voice_intent, "BACKCHANNEL")
        self.assertNotEqual(left_post, right_post)

        left_events = [event.as_dict() for event in left.events]
        right_events = [event.as_dict() for event in right.events]
        divergence = [index for index, pair in enumerate(zip(left_events, right_events)) if pair[0] != pair[1]]
        self.assertEqual(divergence, [2])
        self.assertEqual(left_events[:2], right_events[:2])

    def test_pfd5_same_policy_repeated_controls_have_stable_hashes(self) -> None:
        policy = self.policy("BACKCHANNEL")
        first = self.run_arm(policy)
        second = self.run_arm(policy)
        self.assertEqual(first[3], second[3])
        self.assertEqual(first[5], second[5])
        self.assertEqual(first[4].as_dict(), second[4].as_dict())

    def test_pfd5_metadata_only_change_is_not_behavioral_policy_effect(self) -> None:
        baseline = self.policy("WAIT", provenance="policy:provenance-a")
        metadata_only = self.policy("WAIT", provenance="policy:provenance-b")
        left = self.run_arm(baseline)
        right = self.run_arm(metadata_only)
        self.assertNotEqual(baseline.sha256(), metadata_only.sha256())
        self.assertEqual(left[4].voice_intent, right[4].voice_intent)
        self.assertNotEqual(left[5], right[5])
        self.assertEqual(
            [event.voice_intent for event in left[0].events],
            [event.voice_intent for event in right[0].events],
        )

    def test_foreign_equal_event_cannot_be_used_as_policy_precondition(self) -> None:
        first = VoicePacketCortex(self.session())
        second = VoicePacketCortex(self.session())
        first_event = first.accept_input(self.hold_packet(first))
        second_event = second.accept_input(self.hold_packet(second))
        self.assertEqual(first_event, second_event)
        self.assertIsNot(first_event, second_event)
        with self.assertRaises(PacketTurnPolicyError):
            apply_packet_turn_policy(first, second_event, self.policy("WAIT"))

    def test_final_or_non_hold_event_cannot_enter_policy_binding(self) -> None:
        cortex = VoicePacketCortex(self.session())
        final = VoiceInputPacket(
            session_id=cortex.session_id,
            turn_id="turn-1",
            packet_id="input-final-0",
            monotonic_ms=100,
            source_modality="asr_final",
            text="Jetzt bin ich fertig",
            language="de-DE",
            is_final=True,
            confidence=0.99,
            speech_start=True,
            speech_end=True,
            vad_state="SPEECH",
            endpoint_decision="END",
            overlap_state="NONE",
            barge_in=False,
            source_duration_ms=300,
            sequence=0,
        )
        accepted = cortex.accept_input(final)
        with self.assertRaises(PacketTurnPolicyError):
            apply_packet_turn_policy(cortex, accepted, self.policy("WAIT"))

    def test_policy_cannot_disable_mandatory_barge_in_cancellation(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-0",
            packet_id="output-active",
            monotonic_ms=10,
            text_segment="Noch laufende Ausgabe",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=1000,
            sequence=0,
        )
        cortex.advance_output("output-active", playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        accepted = cortex.accept_input(self.hold_packet(cortex, barge_in=True))
        self.assertEqual(cortex.outputs[0].playback_state, "interrupted")
        decision = apply_packet_turn_policy(cortex, accepted, self.policy("BACKCHANNEL"), monotonic_ms=110)
        self.assertEqual(decision.voice_intent, "BACKCHANNEL")
        self.assertEqual(cortex.outputs[0].playback_state, "interrupted")
        kinds = [event.event_kind for event in cortex.events]
        self.assertLess(kinds.index("BARGE_IN_CANCEL_PROPAGATED"), kinds.index("VOICE_INTENT"))

    def test_policy_decision_cannot_precede_accepted_input(self) -> None:
        cortex = VoicePacketCortex(self.session())
        accepted = cortex.accept_input(self.hold_packet(cortex))
        with self.assertRaises(PacketTurnPolicyError):
            apply_packet_turn_policy(cortex, accepted, self.policy("WAIT"), monotonic_ms=99)


if __name__ == "__main__":
    unittest.main()
