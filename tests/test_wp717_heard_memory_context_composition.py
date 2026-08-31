from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.context_compiler import (
    CHANNEL_STATE,
    ContextCostWitness,
    ContextItem,
    ContextNeed,
    compile_context,
)
from frankenstein2.memory_lifecycle import create_memory
from frankenstein2.typed_memory import KIND_FACT, create_typed_memory
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import bind_completed_reentry, build_heard_result
from frankenstein2.voice_packet_cortex import VoicePacketCortex


class WP717HeardMemoryContextCompositionTests(unittest.TestCase):
    """Exercise one completed heard result through existing memory/context reference authorities."""

    def test_completed_heard_result_composes_exact_memory_and_context_evidence(self) -> None:
        root = CausalIdentity(
            session_id="session-wp717-composition",
            agent_id="frankenstein-2",
            task_id="task-wp717-composition",
            turn_id="turn-input",
            causal_id="causal-input-wp717-composition",
            generation=3,
        )
        intent = VoiceIntent.create(
            causal_identity=root,
            input_ref="fixture:wp717-composition",
            input_sha256="1" * 64,
            provenance_refs=("test:wp717-composition",),
        )
        session = VoiceSessionCapsule.create(
            intent=intent,
            session_causal_identity=root.derive(
                causal_id="causal-session-wp717-composition",
                generation=4,
                turn_id="turn-session",
            ),
            provenance_refs=("test:wp717-composition-session",),
        )
        cortex = VoicePacketCortex(session)
        cortex.queue_output(
            turn_id="turn-voice",
            packet_id="output-0",
            monotonic_ms=10,
            text_segment="Exakt gehoert",
            expression_intent="neutral",
            speech_act="ANSWER",
            planned_audio_duration_ms=100,
            sequence=0,
        )
        cortex.advance_output(
            "output-0",
            playback_state="started",
            monotonic_ms=11,
            heard_fraction=0.0,
        )
        cortex.advance_output(
            "output-0",
            playback_state="completed",
            monotonic_ms=111,
            heard_fraction=1.0,
        )

        heard = build_heard_result(session=session, output_packets=cortex.outputs)
        memory_state = create_memory(
            memory_id="memory:wp717-heard-result",
            payload_ref=heard.payload_ref,
            payload_sha256=heard.payload_sha256,
            provenance_refs=(heard.payload_ref, "test:wp717-memory-admission"),
        )
        typed_memory = create_typed_memory(
            state=memory_state,
            memory_kind=KIND_FACT,
            refs={"evidence": (heard.payload_ref,)},
        )
        memory_event = cortex.emit_intent(
            turn_id="turn-memory-bind",
            monotonic_ms=120,
            voice_intent="WAIT",
            memory_refs=(memory_state.memory_id,),
        )

        outcome = cortex.close_session(
            turn_id="turn-voice",
            monotonic_ms=130,
            outcome_causal_identity=session.session_causal_identity.derive(
                causal_id="causal-outcome-wp717-composition",
                generation=5,
                turn_id="turn-outcome",
            ),
            outcome_kind=OUTCOME_RETURNED,
            result_ref=heard.payload_ref,
            result_sha256=heard.payload_sha256,
            provenance_refs=("test:wp717-composition-outcome",),
        )
        close_event = cortex.events[-1]

        context_item = ContextItem.create(
            item_id="context:wp717-heard-result",
            channel=CHANNEL_STATE,
            payload_ref=heard.payload_ref,
            payload_sha256=heard.payload_sha256,
            source_ref=outcome.outcome_id,
            source_sha256=outcome.sha256(),
            source_generation=1,
            source_classification="VOICE_REENTRY_REFERENCE_ONLY",
            priority_bp=9000,
            cost_units=7,
            required=True,
            provenance_refs=("test:wp717-context",),
            evidence_refs=(heard.payload_ref,),
        )
        cost_witness = ContextCostWitness.create(
            payload_sha256=heard.payload_sha256,
            renderer_id="test-renderer",
            renderer_version="1",
            tokenizer_id="test-tokenizer",
            tokenizer_version="1",
            measured_cost_units=7,
            generation=1,
            measurement_ref="measurement:wp717-context-cost",
            provenance_refs=("test:wp717-context-cost",),
        )
        need = ContextNeed.create(
            context_id="context-view:wp717-composition",
            task_id="task-wp717-composition",
            task_generation=1,
            allowed_channels=(CHANNEL_STATE,),
            required_channels=(CHANNEL_STATE,),
            max_items=1,
            max_cost_units=7,
            evidence_refs=("test:wp717-context-need",),
        )
        context_view = compile_context(need, (context_item,), cost_witnesses=(cost_witness,))

        receipt = bind_completed_reentry(
            session=session,
            outcome=outcome,
            output_packets=cortex.outputs,
            close_event=close_event,
            context_item=context_item,
            cost_witness=cost_witness,
            context_view=context_view,
            memory_event=memory_event,
            memory_bindings=((memory_state, typed_memory),),
            provenance_refs=("test:wp717-composed-reentry",),
        )

        self.assertEqual(receipt.heard_result_ref, heard.payload_ref)
        self.assertEqual(receipt.heard_result_sha256, heard.payload_sha256)
        self.assertEqual(receipt.context_view_sha256, context_view.sha256())
        self.assertEqual(receipt.context_item_id, context_item.item_id)
        self.assertEqual(len(receipt.memory_evidence), 1)
        self.assertEqual(receipt.memory_evidence[0].memory_id, memory_state.memory_id)
        self.assertEqual(receipt.memory_evidence[0].lifecycle_state_sha256, memory_state.sha256())
        self.assertEqual(receipt.memory_evidence[0].typed_memory_sha256, typed_memory.sha256())

        evidence = receipt.as_dict()
        self.assertEqual(evidence["canonical_memory_write_credit"], 0)
        self.assertEqual(evidence["gwt_runtime_credit"], 0)
        self.assertEqual(evidence["effect_credit"], 0)
        self.assertEqual(evidence["physical_audio_credit"], 0)
        self.assertFalse(evidence["whole_system_acceptance"])

        replay = bind_completed_reentry(
            session=session,
            outcome=outcome,
            output_packets=cortex.outputs,
            close_event=close_event,
            context_item=context_item,
            cost_witness=cost_witness,
            context_view=context_view,
            memory_event=memory_event,
            memory_bindings=((memory_state, typed_memory),),
            provenance_refs=("test:wp717-composed-reentry",),
            existing=receipt,
        )
        self.assertIs(replay, receipt)


if __name__ == "__main__":
    unittest.main()
