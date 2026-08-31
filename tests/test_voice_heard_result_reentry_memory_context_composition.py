from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.context_compiler import (
    CHANNEL_STATE,
    ContextCostWitness,
    ContextItem,
    ContextNeed,
    compile_context,
)
from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_uptake import CellUptakeReceipt
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
    create_broadcast,
)
from frankenstein2.memory_lifecycle import create_memory
from frankenstein2.typed_memory import KIND_FACT, create_typed_memory
from frankenstein2.voice_contract import OUTCOME_RETURNED, VoiceIntent, VoiceSessionCapsule
from frankenstein2.voice_heard_result_reentry import (
    VoiceHeardResultReentryError,
    bind_completed_reentry,
    build_heard_result,
)
from frankenstein2.voice_packet_cortex import VoicePacketCortex


def _build_gwt_binding(*, heard):
    plan = Grid10Plan.create(
        plan_id="grid-plan-wp717-composition",
        cycle_id="cycle-wp717-composition",
        generation=1,
        frame_id="frame-wp717-composition",
        frame_generation=1,
        frame_sha256="a" * 64,
        policy_id="grid-policy-wp717-composition",
        policy_generation=1,
        policy_sha256="b" * 64,
        cells=tuple(
            CellBudget(
                cell_id=f"G{i}",
                role_label=f"role-{i}",
                max_input_refs=8,
                max_output_refs=8,
                max_work_units=8,
                max_reentry_depth=2,
            )
            for i in range(1, 11)
        ),
        max_total_work_units=80,
        provenance_refs=("test:wp717-grid-plan", heard.payload_ref),
    )
    producer_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        input_refs=(heard.payload_ref,),
        provenance_refs=("test:wp717-gwt-producer-input",),
    )
    producer_output = CellOutput.for_input(
        plan,
        producer_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=(heard.payload_ref,),
        evidence_refs=(heard.payload_ref,),
        provenance_refs=("test:wp717-gwt-producer-output",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:wp717-heard-result",
        payload_ref=heard.payload_ref,
        epistemic_class="INFERRED",
        provenance_refs=("test:wp717-gwt-candidate", heard.payload_ref),
        salience_micros=500_000,
        goal_relevance_micros=500_000,
        uncertainty_micros=100_000,
        information_gain_micros=500_000,
        estimated_cost_units=1,
        producer_admission=CandidateProducerAdmission(
            plan=plan,
            cell_input=producer_input,
            cell_output=producer_output,
        ),
    )
    policy = SelectionPolicy(
        policy_id="gwt-policy-wp717-composition",
        generation=1,
        max_selected_candidates=1,
        max_total_cost_units=4,
        salience_weight=1,
        goal_relevance_weight=1,
        uncertainty_weight=1,
        information_gain_weight=1,
        cost_weight=1,
    )
    selection = build_workspace_selection(
        selection_id="selection:wp717-composition",
        cycle_id=plan.cycle_id,
        generation=1,
        frame_id=plan.frame_id,
        frame_generation=plan.frame_generation,
        frame_sha256=plan.frame_sha256,
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        policy=policy,
        candidates=(candidate,),
    )
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp717-composition",
        generation=1,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )
    reentry_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=(heard.payload_ref,),
        provenance_refs=("test:wp717-gwt-reentry-input", heard.payload_ref),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=reentry_input,
    )
    uptake = CellUptakeReceipt.observe(
        receipt_id="receipt:wp717-heard-result:uptaken",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref=heard.payload_ref,
        downstream_sha256=heard.payload_sha256,
        provenance_refs=("test:wp717-gwt-uptake-fixture", heard.payload_ref),
    )
    return bind_reentry_to_uptake(
        binding_id="binding:wp717-heard-result",
        witness=witness,
        uptake_receipt=uptake,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=reentry_input,
        provenance_refs=("test:wp717-gwt-binding", heard.payload_ref),
    )


class WP717HeardMemoryContextCompositionTests(unittest.TestCase):
    """Exercise one completed heard result through existing memory/context/GWT reference authorities."""

    def test_completed_heard_result_composes_exact_memory_context_and_gwt_evidence(self) -> None:
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

        gwt_binding = _build_gwt_binding(heard=heard)
        gwt_event = cortex.emit_intent(
            turn_id="turn-gwt-bind",
            monotonic_ms=121,
            voice_intent="WAIT",
            gwt_ref=gwt_binding.binding_id,
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
            gwt_event=gwt_event,
            gwt_binding=gwt_binding,
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
        self.assertEqual(receipt.gwt_binding_id, gwt_binding.binding_id)
        self.assertEqual(receipt.gwt_binding_sha256, gwt_binding.sha256())

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
            gwt_event=gwt_event,
            gwt_binding=gwt_binding,
            provenance_refs=("test:wp717-composed-reentry",),
            existing=receipt,
        )
        self.assertIs(replay, receipt)

        with self.subTest("VSR07_HEARD_MEMORY_PAYLOAD_MISMATCH"):
            unrelated_memory_state = create_memory(
                memory_id=memory_state.memory_id,
                payload_ref="fixture:unrelated-memory-payload",
                payload_sha256="2" * 64,
                provenance_refs=("test:wp717-vsr07-unrelated-memory",),
            )
            unrelated_typed_memory = create_typed_memory(
                state=unrelated_memory_state,
                memory_kind=KIND_FACT,
                refs={"evidence": ("fixture:unrelated-memory-payload",)},
            )
            with self.assertRaises(VoiceHeardResultReentryError):
                bind_completed_reentry(
                    session=session,
                    outcome=outcome,
                    output_packets=cortex.outputs,
                    close_event=close_event,
                    context_item=context_item,
                    cost_witness=cost_witness,
                    context_view=context_view,
                    memory_event=memory_event,
                    memory_bindings=((unrelated_memory_state, unrelated_typed_memory),),
                    gwt_event=gwt_event,
                    gwt_binding=gwt_binding,
                    provenance_refs=("test:wp717-vsr07",),
                )

        with self.subTest("VSR08_DIRECT_GWT_BINDING_IS_REFERENCE_ONLY_ZERO_CREDIT"):
            direct_unsealed_binding = replace(gwt_binding, _factory_seal=None)
            reference_only = bind_completed_reentry(
                session=session,
                outcome=outcome,
                output_packets=cortex.outputs,
                close_event=close_event,
                context_item=context_item,
                cost_witness=cost_witness,
                context_view=context_view,
                memory_event=memory_event,
                memory_bindings=((memory_state, typed_memory),),
                gwt_event=gwt_event,
                gwt_binding=direct_unsealed_binding,
                provenance_refs=("test:wp717-vsr08-reference-only",),
            )
            scoped = reference_only.as_dict()
            self.assertIn("EXACT_REFERENCE_BINDING_ONLY", scoped["classification"])
            self.assertEqual(scoped["gwt_runtime_credit"], 0)
            self.assertEqual(scoped["effect_credit"], 0)
            self.assertFalse(scoped["whole_system_acceptance"])


if __name__ == "__main__":
    unittest.main()
