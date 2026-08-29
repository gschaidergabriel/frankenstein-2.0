#!/usr/bin/env python3
"""Repository-component falsifiers for F2-WP-900 whole persistent loop."""
from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.agency_state import AgencyState, Interest, OpenLoop
from frankenstein2.direct_delegate_router import (
    RoutingPolicy,
    TaskRouteRequest,
    route_task,
)
from frankenstein2.effect_invocation_correlation import (
    EffectCallBinding,
    EffectCorrelationStage,
)
from frankenstein2.goal_lifecycle import GoalRecord, GoalState
from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_causal_path import ReentryEvidenceBundle, seal_gwt_causal_path
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_uptake import (
    CausalProbeArm,
    CellUptakeReceipt,
    evaluate_causal_influence,
    summarize_uptake,
)
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
    create_broadcast,
)
from frankenstein2.persistent_agency_kernel import (
    CHANGE_POLICY_PROJECTION,
    GoalReplayEnvelope,
    advance_checkpoint,
    create_checkpoint,
)
from frankenstein2.situation_frame import CycleContract, SituationFrame
from frankenstein2.wake_hold import OP_EQUALS, WAKE_ANY, WakeCondition
from frankenstein2.whole_persistent_loop import (
    EFFECT_OUTCOME_UNKNOWN,
    EFFECT_RESULT_OBSERVED,
    GwtCausalValidationEvidence,
    LoopOutcomeEvidence,
    NO_EFFECT,
    WholePersistentLoopError,
    checkpoint_ref,
    required_reentry_refs,
    seal_whole_persistent_loop,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


def fixture_checkpoint():
    agency = AgencyState.create(
        state_id="agency-state-wp900",
        generation=3,
        interests=(
            Interest(
                interest_id="interest-loop",
                label="Close one explicit persistent loop",
                salience_ppm=800_000,
                provenance_refs=("owner:wp900",),
            ),
        ),
        open_loops=(
            OpenLoop(
                loop_id="loop-wp900",
                summary="Persist causal cycle re-entry",
                state="OPEN",
                priority_ppm=900_000,
                provenance_refs=("test:wp900",),
            ),
        ),
    )
    genesis = GoalState.create(
        state_id="goal-state-wp900",
        generation=0,
        goals=(
            GoalRecord.candidate(
                goal_id="goal-loop",
                summary="Prove a bounded persistent loop",
                priority_ppm=900_000,
                provenance_refs=("owner:wp900",),
            ),
        ),
    )
    replay = GoalReplayEnvelope.create(genesis=genesis, patches=())
    condition = WakeCondition(
        condition_id="wake-wp900",
        observation_key="ready",
        operator=OP_EQUALS,
        expected_value="yes",
        provenance_refs=("condition:wp900",),
    )
    return create_checkpoint(
        checkpoint_id="checkpoint-wp900-0",
        previous_checkpoint_id=None,
        kernel_state_id="kernel-wp900",
        generation=0,
        change_policy=CHANGE_POLICY_PROJECTION,
        agency_state=agency,
        goal_replay=replay,
        hold_id="hold-wp900",
        wake_policy=WAKE_ANY,
        wake_conditions=(condition,),
        hold_provenance_refs=("hold:wp900",),
        pulse_id="pulse-wp900-0",
        observation_id="observation-wp900-0",
        act_candidate_ref="candidate:act-wp900",
        delegate_candidate_ref="candidate:delegate-wp900",
        provenance_refs=("checkpoint:fixture-wp900",),
    )


def fixture_gwt(plan: Grid10Plan, *, delivery="DELIVERED", uptake="UPTAKEN"):
    producer_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        input_refs=("input:producer-wp900",),
        provenance_refs=("prov:producer-input-wp900",),
    )
    producer_output = CellOutput.for_input(
        plan,
        producer_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=("payload:candidate-wp900",),
        evidence_refs=("evidence:producer-wp900",),
        provenance_refs=("prov:producer-output-wp900",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:gwt-wp900",
        payload_ref="payload:candidate-wp900",
        epistemic_class="INFERRED",
        provenance_refs=("prov:candidate-wp900",),
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
    selection_policy = SelectionPolicy(
        policy_id="gwt-policy-wp900",
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
        selection_id="selection-wp900",
        cycle_id=plan.cycle_id,
        generation=8,
        frame_id=plan.frame_id,
        frame_generation=plan.frame_generation,
        frame_sha256=plan.frame_sha256,
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        policy=selection_policy,
        candidates=(candidate,),
    )
    broadcast = create_broadcast(
        broadcast_id="broadcast-wp900",
        generation=3,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=("payload:candidate-wp900",),
        provenance_refs=("prov:reentry-input-wp900",),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    downstream_output = None
    if uptake == "UPTAKEN":
        downstream_output = CellOutput.for_input(
            plan,
            cell_input,
            status="COMPLETE",
            work_units_used=1,
            output_refs=("downstream:wp900",),
            evidence_refs=("evidence:downstream-wp900",),
            provenance_refs=("prov:downstream-output-wp900",),
        )
    receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:G1:wp900",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status=delivery,
        uptake_status=uptake,
        downstream_ref="downstream:wp900" if uptake == "UPTAKEN" else None,
        downstream_sha256=(
            downstream_output.sha256() if downstream_output is not None else None
        ),
        provenance_refs=("prov:wp507-receipt-wp900",),
    )
    summary = summarize_uptake(
        summary_id="summary:wp900",
        broadcast=broadcast,
        receipts=(receipt,),
        provenance_refs=("prov:wp507-summary-wp900",),
    )
    intervention = CausalProbeArm.intervention(
        arm_id="arm:intervention:wp900",
        probe_id="probe:wp900",
        broadcast=broadcast,
        nonbroadcast_input_sha256=SHA_A,
        downstream_output_sha256=(
            downstream_output.sha256() if downstream_output is not None else SHA_A
        ),
        provenance_refs=("prov:intervention-wp900",),
    )
    control = CausalProbeArm.control(
        arm_id="arm:control:wp900",
        probe_id="probe:wp900",
        nonbroadcast_input_sha256=SHA_A,
        downstream_output_sha256=SHA_B,
        provenance_refs=("prov:control-wp900",),
    )
    causal_result = evaluate_causal_influence(
        result_id="causal-wp900",
        broadcast=broadcast,
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        provenance_refs=("prov:causal-wp900",),
    )
    reentry_bundles: tuple[ReentryEvidenceBundle, ...]
    if uptake == "UPTAKEN":
        binding = bind_reentry_to_uptake(
            binding_id="binding:wp900",
            witness=witness,
            uptake_receipt=receipt,
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=cell_input,
            provenance_refs=("prov:wp508-binding-wp900",),
        )
        reentry_bundles = (
            ReentryEvidenceBundle(
                binding=binding,
                witness=witness,
                uptake_receipt=receipt,
                cell_input=cell_input,
                downstream_output=downstream_output,
            ),
        )
    else:
        reentry_bundles = ()

    evidence = GwtCausalValidationEvidence(
        selection=selection,
        broadcast=broadcast,
        receipts=(receipt,),
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        causal_result=causal_result,
        reentry_bundles=reentry_bundles,
    )
    gwt = seal_gwt_causal_path(
        seal_id="gwt-seal-wp900",
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        receipts=(receipt,),
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        causal_result=causal_result,
        reentry_bundles=reentry_bundles,
        provenance_refs=("gwt:wp900",),
    )
    return gwt, evidence


def fixture_components():
    checkpoint = fixture_checkpoint()
    frame = SituationFrame.create(
        frame_id="frame-wp900",
        cycle_id="cycle-wp900",
        generation=0,
        situation_epoch=0,
        agency_state_ref=checkpoint.agency_state.state_id,
        agency_state_generation=checkpoint.agency_state.generation,
        agency_state_sha256=checkpoint.agency_state.sha256(),
        authority_scope_refs=("authority:explicit-test-scope",),
        provenance_refs=(checkpoint_ref(checkpoint), "frame:wp900"),
    )
    contract = CycleContract.for_frame(
        frame,
        contract_id="contract-wp900",
        cycle_generation=0,
        max_grid_cells=10,
        allowed_exits=("ACT", "ASK", "WAIT", "OBSERVE"),
        continuation_refs=("continue:wp900",),
        provenance_refs=("contract:wp900",),
    )
    cells = tuple(
        CellBudget(
            cell_id=f"G{i}",
            role_label=f"role-{i}",
            max_input_refs=8,
            max_output_refs=8,
            max_work_units=100,
            max_reentry_depth=2,
        )
        for i in range(1, 11)
    )
    plan = Grid10Plan.create(
        plan_id="grid-plan-wp900",
        cycle_id=frame.cycle_id,
        generation=0,
        frame_id=frame.frame_id,
        frame_generation=frame.generation,
        frame_sha256=frame.sha256(),
        policy_id="grid-policy-wp900",
        policy_generation=0,
        policy_sha256=SHA_A,
        cells=cells,
        max_total_work_units=1000,
        provenance_refs=("grid:wp900",),
    )
    gwt, gwt_evidence = fixture_gwt(plan)
    routing_policy = RoutingPolicy.create(
        policy_id="route-policy-wp900",
        generation=0,
        max_direct_work_units=100,
        max_direct_context_tokens=1000,
        provenance_refs=("route-policy:wp900",),
    )
    request = TaskRouteRequest.for_cycle(
        contract,
        task_id="task-wp900",
        task_generation=0,
        task_sha256=SHA_B,
        estimated_work_units=10,
        estimated_context_tokens=100,
        provenance_refs=("task:wp900",),
    )
    decision = route_task(
        cycle_contract=contract,
        request=request,
        policy=routing_policy,
    )
    outcome = LoopOutcomeEvidence(
        outcome_id="outcome-wp900-no-effect",
        status=NO_EFFECT,
        provenance_refs=("outcome:wp900",),
    )
    refs = required_reentry_refs(
        current_checkpoint=checkpoint,
        frame=frame,
        contract=contract,
        plan=plan,
        gwt_seal=gwt,
        decision=decision,
        outcome=outcome,
    )
    next_checkpoint = advance_checkpoint(
        checkpoint,
        checkpoint_id="checkpoint-wp900-1",
        pulse_id="pulse-wp900-1",
        observation_id="observation-wp900-1",
        provenance_refs=refs,
    )
    return (
        checkpoint,
        frame,
        contract,
        plan,
        gwt,
        gwt_evidence,
        decision,
        outcome,
        next_checkpoint,
    )


class WholePersistentLoopTests(unittest.TestCase):
    def test_exact_direct_successor_cycle_seals_without_authority_inflation(self):
        (
            checkpoint,
            frame,
            contract,
            plan,
            gwt,
            gwt_evidence,
            decision,
            outcome,
            next_checkpoint,
        ) = fixture_components()
        self.assertEqual(
            gwt.causal_status, "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
        )
        seal = seal_whole_persistent_loop(
            seal_id="whole-loop-seal-1",
            generation=0,
            current_checkpoint=checkpoint,
            frame=frame,
            contract=contract,
            plan=plan,
            gwt_seal=gwt,
            gwt_evidence=gwt_evidence,
            decision=decision,
            outcome=outcome,
            next_checkpoint=next_checkpoint,
            provenance_refs=("test:wp900:positive",),
        )
        payload = seal.as_dict()
        self.assertEqual(payload["current_checkpoint_id"], checkpoint.checkpoint_id)
        self.assertEqual(payload["next_checkpoint_id"], next_checkpoint.checkpoint_id)
        self.assertEqual(set(payload["reentry_refs"]), set(next_checkpoint.provenance_refs))
        self.assertEqual(payload["effect_authority"], "NONE")
        self.assertEqual(payload["completion_authority"], "NONE")
        self.assertEqual(payload["runtime_credit"], 0)
        self.assertFalse(payload["whole_system_acceptance"])

    def test_non_factory_gwt_seal_is_rejected_before_whole_loop_closure(self):
        (
            checkpoint,
            frame,
            contract,
            plan,
            gwt,
            gwt_evidence,
            decision,
            outcome,
            next_checkpoint,
        ) = fixture_components()
        forged = replace(gwt, _factory_seal=None)
        with self.assertRaisesRegex(
            WholePersistentLoopError, "deterministic WP510 factory"
        ):
            seal_whole_persistent_loop(
                seal_id="whole-loop-seal-forged-gwt",
                generation=0,
                current_checkpoint=checkpoint,
                frame=frame,
                contract=contract,
                plan=plan,
                gwt_seal=forged,
                gwt_evidence=gwt_evidence,
                decision=decision,
                outcome=outcome,
                next_checkpoint=next_checkpoint,
                provenance_refs=("test:wp900:negative",),
            )

    def test_mismatched_gwt_source_evidence_is_rejected(self):
        (
            checkpoint,
            frame,
            contract,
            plan,
            gwt,
            gwt_evidence,
            decision,
            outcome,
            next_checkpoint,
        ) = fixture_components()
        forged_broadcast = replace(
            gwt_evidence.broadcast,
            candidate_payload_refs=("payload:forged",),
        )
        forged_evidence = replace(gwt_evidence, broadcast=forged_broadcast)
        with self.assertRaisesRegex(
            WholePersistentLoopError, "source lineage rejected"
        ):
            seal_whole_persistent_loop(
                seal_id="whole-loop-seal-forged-gwt-source",
                generation=0,
                current_checkpoint=checkpoint,
                frame=frame,
                contract=contract,
                plan=plan,
                gwt_seal=gwt,
                gwt_evidence=forged_evidence,
                decision=decision,
                outcome=outcome,
                next_checkpoint=next_checkpoint,
                provenance_refs=("test:wp900:negative",),
            )

    def test_unknown_gwt_path_remains_unknown_and_cannot_close_whole_loop(self):
        (
            checkpoint,
            frame,
            contract,
            plan,
            _,
            _,
            decision,
            outcome,
            _,
        ) = fixture_components()
        unknown_gwt, unknown_evidence = fixture_gwt(
            plan, delivery="OFFERED", uptake="UNKNOWN"
        )
        self.assertTrue(unknown_gwt.causal_status.startswith("UNKNOWN_"))
        refs = required_reentry_refs(
            current_checkpoint=checkpoint,
            frame=frame,
            contract=contract,
            plan=plan,
            gwt_seal=unknown_gwt,
            decision=decision,
            outcome=outcome,
        )
        next_checkpoint = advance_checkpoint(
            checkpoint,
            checkpoint_id="checkpoint-wp900-unknown",
            pulse_id="pulse-wp900-unknown",
            observation_id="observation-wp900-unknown",
            provenance_refs=refs,
        )
        with self.assertRaisesRegex(
            WholePersistentLoopError, "UNKNOWN/no-causal remains non-positive"
        ):
            seal_whole_persistent_loop(
                seal_id="whole-loop-seal-unknown-gwt",
                generation=0,
                current_checkpoint=checkpoint,
                frame=frame,
                contract=contract,
                plan=plan,
                gwt_seal=unknown_gwt,
                gwt_evidence=unknown_evidence,
                decision=decision,
                outcome=outcome,
                next_checkpoint=next_checkpoint,
                provenance_refs=("test:wp900:unknown",),
            )

    def test_logging_only_successor_without_exact_reentry_refs_is_rejected(self):
        (
            checkpoint,
            frame,
            contract,
            plan,
            gwt,
            gwt_evidence,
            decision,
            outcome,
            _,
        ) = fixture_components()
        next_checkpoint = advance_checkpoint(
            checkpoint,
            checkpoint_id="checkpoint-wp900-1",
            pulse_id="pulse-wp900-1",
            observation_id="observation-wp900-1",
            provenance_refs=("logging:ids-only",),
        )
        with self.assertRaisesRegex(
            WholePersistentLoopError, "lacks exact loop re-entry refs"
        ):
            seal_whole_persistent_loop(
                seal_id="whole-loop-seal-logging-only",
                generation=0,
                current_checkpoint=checkpoint,
                frame=frame,
                contract=contract,
                plan=plan,
                gwt_seal=gwt,
                gwt_evidence=gwt_evidence,
                decision=decision,
                outcome=outcome,
                next_checkpoint=next_checkpoint,
                provenance_refs=("test:wp900:negative",),
            )

    def test_wrong_checkpoint_parent_is_rejected(self):
        (
            checkpoint,
            frame,
            contract,
            plan,
            gwt,
            gwt_evidence,
            decision,
            outcome,
            next_checkpoint,
        ) = fixture_components()
        wrong_parent = replace(
            next_checkpoint,
            previous_checkpoint_id="checkpoint-not-parent",
        )
        with self.assertRaisesRegex(
            WholePersistentLoopError, "checkpoint parent identity mismatch"
        ):
            seal_whole_persistent_loop(
                seal_id="whole-loop-seal-wrong-parent",
                generation=0,
                current_checkpoint=checkpoint,
                frame=frame,
                contract=contract,
                plan=plan,
                gwt_seal=gwt,
                gwt_evidence=gwt_evidence,
                decision=decision,
                outcome=outcome,
                next_checkpoint=wrong_parent,
                provenance_refs=("test:wp900:negative",),
            )

    def test_frame_without_exact_checkpoint_provenance_is_rejected_before_digest_chain(self):
        (
            checkpoint,
            frame,
            contract,
            plan,
            gwt,
            gwt_evidence,
            decision,
            outcome,
            next_checkpoint,
        ) = fixture_components()
        unbound_frame = replace(frame, provenance_refs=("frame:unbound",))
        with self.assertRaisesRegex(
            WholePersistentLoopError, "lacks exact current-checkpoint provenance"
        ):
            seal_whole_persistent_loop(
                seal_id="whole-loop-seal-unbound-frame",
                generation=0,
                current_checkpoint=checkpoint,
                frame=unbound_frame,
                contract=contract,
                plan=plan,
                gwt_seal=gwt,
                gwt_evidence=gwt_evidence,
                decision=decision,
                outcome=outcome,
                next_checkpoint=next_checkpoint,
                provenance_refs=("test:wp900:negative",),
            )

    def test_gwt_plan_substitution_is_rejected(self):
        (
            checkpoint,
            frame,
            contract,
            plan,
            gwt,
            gwt_evidence,
            decision,
            outcome,
            next_checkpoint,
        ) = fixture_components()
        wrong_gwt = replace(gwt, plan_sha256="f" * 64)
        with self.assertRaisesRegex(
            WholePersistentLoopError, "GWT seal GRID10 plan digest mismatch"
        ):
            seal_whole_persistent_loop(
                seal_id="whole-loop-seal-wrong-gwt",
                generation=0,
                current_checkpoint=checkpoint,
                frame=frame,
                contract=contract,
                plan=plan,
                gwt_seal=wrong_gwt,
                gwt_evidence=gwt_evidence,
                decision=decision,
                outcome=outcome,
                next_checkpoint=next_checkpoint,
                provenance_refs=("test:wp900:negative",),
            )

    def test_unknown_effect_outcome_remains_unknown_and_result_claim_fails_closed(self):
        prepared = EffectCallBinding(
            effect_id="effect-wp900",
            return_id=None,
            binding_id="binding-wp900",
            invocation_id="invocation-wp900",
            tool_use_id="tool-use-wp900",
            delegation_id="delegation-wp900",
            child_identity_sha256=SHA_A,
            stage=EffectCorrelationStage.PREPARED,
        )
        unknown = LoopOutcomeEvidence(
            outcome_id="outcome-wp900-unknown",
            status=EFFECT_OUTCOME_UNKNOWN,
            effect_call=prepared,
            unknown_reason_ref="unknown:transport-after-dispatch",
            provenance_refs=("outcome:unknown",),
        )
        payload = unknown.as_dict()
        self.assertEqual(payload["status"], EFFECT_OUTCOME_UNKNOWN)
        self.assertEqual(payload["completion_authority"], "NONE")
        with self.assertRaisesRegex(
            WholePersistentLoopError, "requires RESULT_OBSERVED"
        ):
            LoopOutcomeEvidence(
                outcome_id="outcome-wp900-fake-result",
                status=EFFECT_RESULT_OBSERVED,
                effect_call=prepared,
                provenance_refs=("outcome:invalid",),
            )

    def test_bool_generation_is_rejected(self):
        (
            checkpoint,
            frame,
            contract,
            plan,
            gwt,
            gwt_evidence,
            decision,
            outcome,
            next_checkpoint,
        ) = fixture_components()
        with self.assertRaisesRegex(
            WholePersistentLoopError, "generation must be a non-negative integer"
        ):
            seal_whole_persistent_loop(
                seal_id="whole-loop-seal-bool-generation",
                generation=True,
                current_checkpoint=checkpoint,
                frame=frame,
                contract=contract,
                plan=plan,
                gwt_seal=gwt,
                gwt_evidence=gwt_evidence,
                decision=decision,
                outcome=outcome,
                next_checkpoint=next_checkpoint,
                provenance_refs=("test:wp900:negative",),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
