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
        plan_id="grid-plan-wp718",
        cycle_id="cycle-wp718",
        generation=1,
        frame_id="frame-wp718",
        frame_generation=1,
        frame_sha256="a" * 64,
        policy_id="grid-policy-wp718",
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
        provenance_refs=("test:wp718-grid-plan", heard.payload_ref),
    )
    producer_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        input_refs=(heard.payload_ref,),
        provenance_refs=("test:wp718-producer-input",),
    )
    producer_output = CellOutput.for_input(
        plan,
        producer_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=(heard.payload_ref,),
        evidence_refs=(heard.payload_ref,),
        provenance_refs=("test:wp718-producer-output",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:wp718-heard-result",
        payload_ref=heard.payload_ref,
        epistemic_class="INFERRED",
        provenance_refs=("test:wp718-candidate", heard.payload_ref),
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
        policy_id="gwt-policy-wp718",
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
        selection_id="selection:wp718",
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
        broadcast_id="broadcast:wp718",
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
        provenance_refs=("test:wp718-reentry-input", heard.payload_ref),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=reentry_input,
    )
    uptake = CellUptakeReceipt.observe(
        receipt_id="receipt:wp718:uptaken",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref=heard.payload_ref,
        downstream_sha256=heard.payload_sha256,
        provenance_refs=("test:wp718-wp507-uptake-fixture", heard.payload_ref),
    )
    return bind_reentry_to_uptake(
        binding_id="binding:wp718-heard-result",
        witness=witness,
        uptake_receipt=uptake,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=reentry_input,
        provenance_refs=("test:wp718-wp508-binding", heard.payload_ref),
    )


def _build_whole_fixture():
    root = CausalIdentity(
        session_id="session-wp718",
        agent_id="frankenstein-2",
        task_id="task-wp718",
        turn_id="turn-input",
        causal_id="causal-input-wp718",
        generation=1,
    )
    intent = VoiceIntent.create(
        causal_identity=root,
        input_ref="fixture:wp718",
        input_sha256="1" * 64,
        provenance_refs=("test:wp718-intent",),
    )
    session = VoiceSessionCapsule.create(
        intent=intent,
        session_causal_identity=root.derive(
            causal_id="causal-session-wp718",
            generation=2,
            turn_id="turn-session",
        ),
        provenance_refs=("test:wp718-session",),
    )
    cortex = VoicePacketCortex(session)
    cortex.queue_output(
        turn_id="turn-voice",
        packet_id="output-0",
        monotonic_ms=10,
        text_segment="WP718 exact heard result",
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
        memory_id="memory:wp718-heard-result",
        payload_ref=heard.payload_ref,
        payload_sha256=heard.payload_sha256,
        provenance_refs=(heard.payload_ref, "test:wp718-memory"),
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
            causal_id="causal-outcome-wp718",
            generation=3,
            turn_id="turn-outcome",
        ),
        outcome_kind=OUTCOME_RETURNED,
        result_ref=heard.payload_ref,
        result_sha256=heard.payload_sha256,
        provenance_refs=("test:wp718-outcome",),
    )
    close_event = cortex.events[-1]

    context_item = ContextItem.create(
        item_id="context:wp718-heard-result",
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
        provenance_refs=("test:wp718-context-item",),
        evidence_refs=(heard.payload_ref,),
    )
    cost_witness = ContextCostWitness.create(
        payload_sha256=heard.payload_sha256,
        renderer_id="test-renderer-wp718",
        renderer_version="1",
        tokenizer_id="test-tokenizer-wp718",
        tokenizer_version="1",
        measured_cost_units=7,
        generation=1,
        measurement_ref="measurement:wp718-context-cost",
        provenance_refs=("test:wp718-context-cost",),
    )
    need = ContextNeed.create(
        context_id="context-view:wp718",
        task_id="task-wp718",
        task_generation=1,
        allowed_channels=(CHANNEL_STATE,),
        required_channels=(CHANNEL_STATE,),
        max_items=1,
        max_cost_units=7,
        evidence_refs=("test:wp718-context-need",),
    )
    context_view = compile_context(need, (context_item,), cost_witnesses=(cost_witness,))

    return {
        "session": session,
        "cortex": cortex,
        "heard": heard,
        "memory_state": memory_state,
        "typed_memory": typed_memory,
        "memory_event": memory_event,
        "gwt_binding": gwt_binding,
        "gwt_event": gwt_event,
        "outcome": outcome,
        "close_event": close_event,
        "context_item": context_item,
        "cost_witness": cost_witness,
        "context_view": context_view,
    }


def _bind(fixture, *, gwt_event=None, existing=None):
    return bind_completed_reentry(
        session=fixture["session"],
        outcome=fixture["outcome"],
        output_packets=fixture["cortex"].outputs,
        close_event=fixture["close_event"],
        context_item=fixture["context_item"],
        cost_witness=fixture["cost_witness"],
        context_view=fixture["context_view"],
        memory_event=fixture["memory_event"],
        memory_bindings=((fixture["memory_state"], fixture["typed_memory"]),),
        gwt_event=fixture["gwt_event"] if gwt_event is None else gwt_event,
        gwt_binding=fixture["gwt_binding"],
        provenance_refs=("test:wp718-whole-reentry",),
        existing=existing,
    )


class WP718StateMemoryVoiceOutcomeGwtReentryIntegrationTests(unittest.TestCase):
    def test_whole_composition_binds_exact_memory_context_and_factory_gwt_evidence(self) -> None:
        fixture = _build_whole_fixture()
        receipt = _bind(fixture)

        self.assertEqual(receipt.heard_result_ref, fixture["heard"].payload_ref)
        self.assertEqual(receipt.heard_result_sha256, fixture["heard"].payload_sha256)
        self.assertEqual(receipt.context_view_sha256, fixture["context_view"].sha256())
        self.assertEqual(receipt.context_item_id, fixture["context_item"].item_id)
        self.assertEqual(len(receipt.memory_evidence), 1)
        self.assertEqual(receipt.memory_evidence[0].memory_id, fixture["memory_state"].memory_id)
        self.assertEqual(
            receipt.memory_evidence[0].lifecycle_state_sha256,
            fixture["memory_state"].sha256(),
        )
        self.assertEqual(
            receipt.memory_evidence[0].typed_memory_sha256,
            fixture["typed_memory"].sha256(),
        )
        self.assertEqual(receipt.gwt_binding_id, fixture["gwt_binding"].binding_id)
        self.assertEqual(receipt.gwt_binding_sha256, fixture["gwt_binding"].sha256())

        evidence = receipt.as_dict()
        self.assertEqual(evidence["canonical_memory_write_credit"], 0)
        self.assertEqual(evidence["gwt_runtime_credit"], 0)
        self.assertEqual(evidence["effect_credit"], 0)
        self.assertEqual(evidence["physical_audio_credit"], 0)
        self.assertFalse(evidence["whole_system_acceptance"])

        replay = _bind(fixture, existing=receipt)
        self.assertIs(replay, receipt)

    def test_wrong_gwt_event_reference_fails_closed(self) -> None:
        fixture = _build_whole_fixture()
        forged_event = replace(
            fixture["gwt_event"],
            gwt_ref="binding:wp718-wrong-subject",
        )
        with self.assertRaisesRegex(
            VoiceHeardResultReentryError,
            "opaque/stale/wrong gwt_ref",
        ):
            _bind(fixture, gwt_event=forged_event)


if __name__ == "__main__":
    unittest.main()
