from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import json
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.voice_contract import VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoiceInputPacket, VoicePacketCortex, VoicePacketCortexError
from frankenstein2.voice_packet_turn_policy import (
    PacketTurnPolicy,
    bind_packet_turn_policy,
    select_packet_turn_intent,
)


def _digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PacketTurnPolicyPfdTests(unittest.TestCase):
    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-pfd-policy",
            agent_id="frankenstein-2",
            task_id="task-pfd-policy",
            turn_id="turn-input",
            causal_id="causal-input-pfd-policy",
            generation=3,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="packet-fixture:pfd",
            input_sha256="a" * 64,
            provenance_refs=("trigger4:candidate-pfd",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-pfd-policy", generation=4, turn_id="turn-session"
            ),
            provenance_refs=("trigger4:candidate-pfd-session",),
        )

    def packet(self, cortex: VoicePacketCortex, **overrides) -> VoiceInputPacket:
        values = dict(
            session_id=cortex.session_id,
            turn_id="turn-pfd",
            packet_id="input-pfd-0",
            monotonic_ms=100,
            source_modality="asr_partial",
            text="Ich bin noch nicht fertig",
            language="de-DE",
            is_final=False,
            confidence=0.95,
            speech_start=True,
            speech_end=False,
            vad_state="SPEECH",
            endpoint_decision="HOLD",
            overlap_state="NONE",
            barge_in=False,
            source_duration_ms=180,
            sequence=0,
        )
        values.update(overrides)
        return VoiceInputPacket(**values)

    def policy(self, hold_partial_intent: str, *, policy_id: str = "policy:pfd:matched") -> PacketTurnPolicy:
        return PacketTurnPolicy(
            policy_id=policy_id,
            hold_partial_intent=hold_partial_intent,
            provenance_refs=("trigger7:pfd-handoff", "trigger4:candidate-pfd"),
        )

    def state_hash(self, cortex: VoicePacketCortex) -> str:
        return _digest({
            "session_id": cortex.session_id,
            "presence_state": cortex.presence_state,
            "is_open": cortex.is_open,
            "events": [event.as_dict() for event in cortex.events],
            "outputs": [output.as_dict() for output in cortex.outputs],
        })

    def behavior_trajectory(self, cortex: VoicePacketCortex):
        return [
            (event.event_kind, event.voice_intent, tuple(event.packet_refs))
            for event in cortex.events
        ]

    def matched_pair(self):
        left = VoicePacketCortex(self.session())
        right = VoicePacketCortex(self.session())
        left_packet = self.packet(left)
        right_packet = self.packet(right)
        left.accept_input(left_packet)
        right.accept_input(right_packet)
        self.assertEqual(left_packet, right_packet)
        self.assertEqual(self.state_hash(left), self.state_hash(right))
        return left, left_packet, right, right_packet

    def test_pfd0_policy_is_immutable_serializable_and_hash_stable(self) -> None:
        policy = self.policy("WAIT")
        self.assertEqual(PacketTurnPolicy(**{
            "policy_id": policy.policy_id,
            "hold_partial_intent": policy.hold_partial_intent,
            "provenance_refs": policy.provenance_refs,
        }).sha256(), policy.sha256())
        self.assertEqual(policy.as_dict()["hold_partial_intent"], "WAIT")
        with self.assertRaises(FrozenInstanceError):
            policy.hold_partial_intent = "BACKCHANNEL"  # type: ignore[misc]

    def test_pfd1_same_history_one_policy_dimension_changes_wait_to_backchannel(self) -> None:
        left, left_packet, right, right_packet = self.matched_pair()
        pre_hash = self.state_hash(left)
        wait_policy = self.policy("WAIT")
        backchannel_policy = self.policy("BACKCHANNEL")

        left_event = bind_packet_turn_policy(left, left_packet, wait_policy, monotonic_ms=120)
        right_event = bind_packet_turn_policy(right, right_packet, backchannel_policy, monotonic_ms=120)

        self.assertEqual(left_event.voice_intent, "WAIT")
        self.assertEqual(right_event.voice_intent, "BACKCHANNEL")
        self.assertNotEqual(self.behavior_trajectory(left), self.behavior_trajectory(right))
        self.assertNotEqual(wait_policy.sha256(), backchannel_policy.sha256())
        self.assertIn(f"packet_sha256={left_packet.sha256()}", left_event.detail)
        self.assertIn(f"turn_policy_sha256={wait_policy.sha256()}", left_event.detail)
        self.assertIn(f"turn_policy_sha256={backchannel_policy.sha256()}", right_event.detail)
        self.assertNotEqual(self.state_hash(left), pre_hash)
        self.assertNotEqual(self.state_hash(right), pre_hash)

    def test_pfd2_repeated_same_policy_has_stable_event_and_state_hashes(self) -> None:
        left, left_packet, right, right_packet = self.matched_pair()
        policy = self.policy("BACKCHANNEL")
        left_event = bind_packet_turn_policy(left, left_packet, policy, monotonic_ms=120)
        right_event = bind_packet_turn_policy(right, right_packet, policy, monotonic_ms=120)
        self.assertEqual(left_event.as_dict(), right_event.as_dict())
        self.assertEqual(self.state_hash(left), self.state_hash(right))

    def test_pfd3_metadata_only_policy_change_is_not_behavioral_delta(self) -> None:
        left, left_packet, right, right_packet = self.matched_pair()
        left_policy = self.policy("WAIT", policy_id="policy:pfd:meta-a")
        right_policy = PacketTurnPolicy(
            policy_id="policy:pfd:meta-b",
            hold_partial_intent="WAIT",
            provenance_refs=("trigger7:pfd-handoff", "trigger4:candidate-pfd:metadata-only"),
        )
        self.assertNotEqual(left_policy.sha256(), right_policy.sha256())
        bind_packet_turn_policy(left, left_packet, left_policy, monotonic_ms=120)
        bind_packet_turn_policy(right, right_packet, right_policy, monotonic_ms=120)
        self.assertEqual(self.behavior_trajectory(left), self.behavior_trajectory(right))
        self.assertEqual(left.events[-1].voice_intent, "WAIT")
        self.assertEqual(right.events[-1].voice_intent, "WAIT")

    def test_pfd4_final_endpoint_answer_is_policy_invariant(self) -> None:
        left = VoicePacketCortex(self.session())
        right = VoicePacketCortex(self.session())
        left_packet = self.packet(
            left,
            source_modality="asr_final",
            text="Jetzt bin ich fertig",
            is_final=True,
            speech_end=True,
            endpoint_decision="END",
        )
        right_packet = self.packet(
            right,
            source_modality="asr_final",
            text="Jetzt bin ich fertig",
            is_final=True,
            speech_end=True,
            endpoint_decision="END",
        )
        left.accept_input(left_packet)
        right.accept_input(right_packet)
        self.assertEqual(select_packet_turn_intent(left_packet, self.policy("WAIT")), "ANSWER")
        self.assertEqual(select_packet_turn_intent(right_packet, self.policy("BACKCHANNEL")), "ANSWER")

    def test_pfd5_barge_in_cancellation_remains_mandatory_before_policy_intent(self) -> None:
        cortex = VoicePacketCortex(self.session())
        cortex.queue_output(
            turn_id="turn-old",
            packet_id="output-old",
            monotonic_ms=10,
            text_segment="Noch spreche ich.",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=500,
            sequence=0,
        )
        cortex.advance_output("output-old", playback_state="started", monotonic_ms=20, heard_fraction=0.0)
        cortex.advance_output("output-old", playback_state="heard", monotonic_ms=90, heard_fraction=0.2)
        packet = self.packet(
            cortex,
            monotonic_ms=100,
            overlap_state="USER_OVER_OUTPUT",
            barge_in=True,
        )
        cortex.accept_input(packet)
        event = bind_packet_turn_policy(cortex, packet, self.policy("BACKCHANNEL"), monotonic_ms=120)

        output = cortex.outputs[0]
        self.assertEqual(output.playback_state, "interrupted")
        self.assertFalse(output.commit_eligible)
        kinds = [item.event_kind for item in cortex.events]
        self.assertLess(kinds.index("BARGE_IN_CANCEL_PROPAGATED"), len(kinds) - 1)
        self.assertEqual(event.voice_intent, "BACKCHANNEL")

    def test_policy_binding_rejects_packet_not_in_exact_accepted_history(self) -> None:
        cortex = VoicePacketCortex(self.session())
        packet = self.packet(cortex)
        with self.assertRaises(VoicePacketCortexError):
            bind_packet_turn_policy(cortex, packet, self.policy("WAIT"), monotonic_ms=120)

    def test_unknown_endpoint_fails_conservatively_to_wait(self) -> None:
        cortex = VoicePacketCortex(self.session())
        packet = self.packet(cortex, endpoint_decision="UNKNOWN")
        cortex.accept_input(packet)
        event = bind_packet_turn_policy(cortex, packet, self.policy("BACKCHANNEL"), monotonic_ms=120)
        self.assertEqual(event.voice_intent, "WAIT")


if __name__ == "__main__":
    unittest.main()
