from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.context_compiler import (
    CHANNEL_EVIDENCE,
    ContextCostWitness,
    ContextNeed,
)
from frankenstein2.voice_context_reentry import (
    VoiceContextReentryError,
    bind_heard_result_to_context,
    derive_heard_result_identity,
)
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_packet_cortex import VoicePacketCortex


class VoiceContextReentryTests(unittest.TestCase):
    def session(self) -> VoiceSessionCapsule:
        root = CausalIdentity(
            session_id="session-vsr01",
            agent_id="frankenstein-2",
            task_id="task-vsr01",
            turn_id="turn-input",
            causal_id="causal-input-vsr01",
            generation=3,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="packet-fixture:vsr01",
            input_sha256="a" * 64,
            provenance_refs=("trigger7:vsr01-fixture",),
        )
        return VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-vsr01",
                generation=4,
                turn_id="turn-session",
            ),
            provenance_refs=("trigger7:vsr01-session",),
        )

    def completed_cortex(self, *, segments: tuple[str, ...] = ("Hallo.",)) -> VoicePacketCortex:
        cortex = VoicePacketCortex(self.session())
        for sequence, text in enumerate(segments):
            packet_id = f"output-{sequence}"
            cortex.queue_output(
                turn_id="turn-0",
                packet_id=packet_id,
                monotonic_ms=10 + sequence,
                text_segment=text,
                expression_intent="neutral",
                speech_act="ANSWER",
                planned_audio_duration_ms=100,
                sequence=sequence,
            )
            cortex.advance_output(
                packet_id,
                playback_state="started",
                monotonic_ms=20 + sequence * 200,
                heard_fraction=0.0,
            )
            cortex.advance_output(
                packet_id,
                playback_state="completed",
                monotonic_ms=120 + sequence * 200,
                heard_fraction=1.0,
            )
        return cortex

    def close_with_exact_heard_result(self, cortex: VoicePacketCortex):
        heard = derive_heard_result_identity(cortex)
        session = cortex.session
        outcome = cortex.close_session(
            turn_id="turn-close",
            monotonic_ms=1000,
            outcome_causal_identity=session.session_causal_identity.derive(
                causal_id="causal-outcome-vsr01",
                generation=5,
                turn_id="turn-outcome",
            ),
            outcome_kind=OUTCOME_RETURNED,
            result_ref=heard.payload_ref,
            result_sha256=heard.payload_sha256,
        )
        return heard, outcome

    def context_inputs(self, payload_sha256: str):
        need = ContextNeed.create(
            context_id="context:vsr01",
            task_id="task-vsr01",
            task_generation=5,
            allowed_channels=(CHANNEL_EVIDENCE,),
            required_channels=(CHANNEL_EVIDENCE,),
            max_items=1,
            max_cost_units=8,
            evidence_refs=("trigger7:vsr01",),
        )
        witness = ContextCostWitness.create(
            payload_sha256=payload_sha256,
            renderer_id="fixture-renderer",
            renderer_version="1",
            tokenizer_id="fixture-tokenizer",
            tokenizer_version="1",
            measured_cost_units=4,
            generation=1,
            measurement_ref="measurement:vsr01",
            provenance_refs=("trigger7:vsr01-cost",),
        )
        return need, witness

    def test_exact_fully_heard_result_enters_existing_context_compiler(self) -> None:
        cortex = self.completed_cortex(segments=("Erster Satz.", "Zweiter Satz."))
        before_close = derive_heard_result_identity(cortex)
        heard, outcome = self.close_with_exact_heard_result(cortex)
        self.assertEqual(heard, before_close)
        need, witness = self.context_inputs(heard.payload_sha256)

        binding = bind_heard_result_to_context(
            cortex=cortex,
            outcome=outcome,
            need=need,
            cost_witness=witness,
        )

        self.assertTrue(binding.voiceoutcome_result_matches_heard_result)
        self.assertEqual(
            binding.heard_result.ordered_output_packet_ids,
            ("output-0", "output-1"),
        )
        self.assertEqual(binding.heard_result.payload_sha256, heard.payload_sha256)
        self.assertEqual(binding.context_cost_witness_sha256, witness.sha256())

    def test_arbitrary_valid_voiceoutcome_digest_is_rejected_before_context(self) -> None:
        cortex = self.completed_cortex()
        heard = derive_heard_result_identity(cortex)
        session = cortex.session
        wrong_digest = "f" * 64
        self.assertNotEqual(wrong_digest, heard.payload_sha256)
        outcome = cortex.close_session(
            turn_id="turn-close",
            monotonic_ms=1000,
            outcome_causal_identity=session.session_causal_identity.derive(
                causal_id="causal-outcome-vsr01-wrong",
                generation=5,
                turn_id="turn-outcome",
            ),
            outcome_kind=OUTCOME_RETURNED,
            result_ref=heard.payload_ref,
            result_sha256=wrong_digest,
        )
        need, witness = self.context_inputs(heard.payload_sha256)

        with self.assertRaisesRegex(VoiceContextReentryError, "UNBOUND_VOICEOUTCOME_RESULT"):
            bind_heard_result_to_context(
                cortex=cortex,
                outcome=outcome,
                need=need,
                cost_witness=witness,
            )

    def test_omitted_completed_segment_invalidates_closed_outcome_binding(self) -> None:
        cortex = self.completed_cortex(segments=("A", "B"))
        heard, outcome = self.close_with_exact_heard_result(cortex)
        need, witness = self.context_inputs(heard.payload_sha256)

        # Fault injection: simulate a stale/incomplete integration snapshot after close.
        del cortex._outputs["output-1"]

        with self.assertRaisesRegex(VoiceContextReentryError, "UNBOUND_VOICEOUTCOME_RESULT"):
            bind_heard_result_to_context(
                cortex=cortex,
                outcome=outcome,
                need=need,
                cost_witness=witness,
            )

    def test_cost_witness_for_other_payload_is_rejected(self) -> None:
        cortex = self.completed_cortex()
        heard, outcome = self.close_with_exact_heard_result(cortex)
        need, _ = self.context_inputs(heard.payload_sha256)
        _, wrong_witness = self.context_inputs("e" * 64)

        with self.assertRaisesRegex(VoiceContextReentryError, "cost witness"):
            bind_heard_result_to_context(
                cortex=cortex,
                outcome=outcome,
                need=need,
                cost_witness=wrong_witness,
            )


if __name__ == "__main__":
    unittest.main()
