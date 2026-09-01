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


CLASSIFICATION = "REPOSITORY_PACKET_COMPOSITION_ONLY_NOT_ASR_RUNTIME_OR_PRODUCT_CREDIT"


def make_session(label: str) -> VoiceSessionCapsule:
    root = CausalIdentity(
        session_id=f"session-fdx15-{label}",
        agent_id="frankenstein-2",
        task_id=f"task-fdx15-{label}",
        turn_id=f"turn-root-{label}",
        causal_id=f"causal-root-fdx15-{label}",
        generation=1,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref=f"fdx15:{label}:input",
        input_sha256=("a" if label == "silence" else "b") * 64,
        provenance_refs=(CLASSIFICATION, f"trigger4:fdx15:{label}"),
    )
    return VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id=f"causal-session-fdx15-{label}",
            generation=2,
            turn_id=f"turn-session-{label}",
        ),
        provenance_refs=(CLASSIFICATION, f"trigger4:fdx15:{label}:session"),
    )


def input_packet(
    cortex: VoicePacketCortex,
    *,
    turn_id: str,
    packet_id: str,
    monotonic_ms: int,
    sequence: int,
    text: str,
    is_final: bool,
    endpoint: str,
    speech_start: bool,
    speech_end: bool,
) -> VoiceInputPacket:
    return VoiceInputPacket(
        session_id=cortex.session_id,
        turn_id=turn_id,
        packet_id=packet_id,
        monotonic_ms=monotonic_ms,
        source_modality="asr_final" if is_final else "asr_partial",
        text=text,
        language="de-DE",
        is_final=is_final,
        confidence=0.95,
        speech_start=speech_start,
        speech_end=speech_end,
        vad_state="SPEECH",
        endpoint_decision=endpoint,
        overlap_state="NONE",
        barge_in=False,
        source_duration_ms=160,
        sequence=sequence,
        fault_flags=(),
    )


class Trigger4FDX1FDX5ConvergenceTests(unittest.TestCase):
    """Independent packet-level falsifiers while the FDX7/8 S2 subject is frozen.

    These tests deliberately do not claim real ASR timing, acoustic silence, model runtime,
    VPS runtime, physical audio, GWT/J-Space, effects, training, or whole-product credit.
    """

    def test_fdx1_long_silence_keeps_session_identity_and_starts_distinct_turn_sequence(self) -> None:
        session = make_session("silence")
        cortex = VoicePacketCortex(session)

        old_turn = "turn-before-silence"
        old_partial = input_packet(
            cortex,
            turn_id=old_turn,
            packet_id="input-before-silence-0",
            monotonic_ms=100,
            sequence=0,
            text="Ich überlege noch",
            is_final=False,
            endpoint="HOLD",
            speech_start=True,
            speech_end=False,
        )
        cortex.accept_input(old_partial)
        old_policy = PacketTurnPolicy(
            policy_id="policy-before-silence",
            hold_intent="WAIT",
            provenance_refs=(CLASSIFICATION, "trigger4:fdx1:long-silence"),
        )
        old_policy_event = cortex.apply_turn_policy(old_partial, old_policy)

        # A large monotonic gap is represented without inventing a new session identity.
        new_turn = "turn-after-silence"
        resumed_final = input_packet(
            cortex,
            turn_id=new_turn,
            packet_id="input-after-silence-0",
            monotonic_ms=120_000,
            sequence=0,
            text="Jetzt weiter mit der neuen Frage.",
            is_final=True,
            endpoint="END",
            speech_start=True,
            speech_end=True,
        )
        resumed_event = cortex.accept_input(resumed_final)

        self.assertEqual(cortex.session_id, session.voice_session_id)
        self.assertEqual(old_policy_event.turn_id, old_turn)
        self.assertEqual(old_policy_event.packet_refs, (old_partial.packet_id,))
        self.assertEqual(resumed_event.turn_id, new_turn)
        self.assertEqual(resumed_event.packet_refs, (resumed_final.packet_id,))
        self.assertNotEqual(old_turn, new_turn)

        output = cortex.queue_output(
            turn_id=new_turn,
            packet_id="output-after-silence-0",
            monotonic_ms=120_010,
            text_segment="Antwort nach der Pause",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=500,
            sequence=0,
        )
        self.assertEqual(output.turn_id, new_turn)
        self.assertEqual(output.sequence, 0)
        self.assertFalse(any(e.turn_id == old_turn and e.voice_intent == "ANSWER" for e in cortex.events))

    def test_fdx5_self_correction_keeps_partial_without_tool_authority_until_final(self) -> None:
        session = make_session("self-correction")
        cortex = VoicePacketCortex(session)
        turn = "turn-self-correction"

        partial = input_packet(
            cortex,
            turn_id=turn,
            packet_id="input-self-correction-0",
            monotonic_ms=100,
            sequence=0,
            text="Buche morgen um neun einen Termin",
            is_final=False,
            endpoint="HOLD",
            speech_start=True,
            speech_end=False,
        )
        cortex.accept_input(partial)
        wait_policy = PacketTurnPolicy(
            policy_id="policy-self-correction-wait",
            hold_intent="WAIT",
            provenance_refs=(CLASSIFICATION, "trigger4:fdx5:self-correction"),
        )
        policy_event = cortex.apply_turn_policy(partial, wait_policy)
        self.assertEqual(policy_event.voice_intent, "WAIT")
        self.assertEqual(sum(e.voice_intent == "TOOL_USE" for e in cortex.events), 0)

        final = input_packet(
            cortex,
            turn_id=turn,
            packet_id="input-self-correction-1",
            monotonic_ms=200,
            sequence=1,
            text="Nein, buche keinen Termin; zeig mir nur freie Zeiten.",
            is_final=True,
            endpoint="END",
            speech_start=False,
            speech_end=True,
        )
        final_event = cortex.accept_input(final)
        self.assertIn("ASR_FINAL", final_event.event_kind)

        # Once the corrected final packet is current, the superseded partial can no longer
        # receive a new authoritative HOLD-policy binding.
        with self.assertRaises(VoicePacketCortexError):
            cortex.apply_turn_policy(
                partial,
                PacketTurnPolicy(
                    policy_id="policy-stale-conflict",
                    hold_intent="BACKCHANNEL",
                    provenance_refs=(CLASSIFICATION, "trigger4:fdx5:stale-partial-falsifier"),
                ),
            )

        tool_event = cortex.emit_intent(
            turn_id=turn,
            monotonic_ms=210,
            voice_intent="TOOL_USE",
            tool_ref="tool:fdx5:final-only",
            detail="tool ownership admitted only after corrected final packet",
        )
        self.assertEqual(tool_event.turn_id, final.turn_id)
        self.assertEqual(tool_event.tool_ref, "tool:fdx5:final-only")
        self.assertEqual(sum(e.voice_intent == "TOOL_USE" for e in cortex.events), 1)

        final_index = next(i for i, event in enumerate(cortex.events) if event.event_id == final_event.event_id)
        tool_index = next(i for i, event in enumerate(cortex.events) if event.event_id == tool_event.event_id)
        self.assertGreater(tool_index, final_index)


if __name__ == "__main__":
    unittest.main()
