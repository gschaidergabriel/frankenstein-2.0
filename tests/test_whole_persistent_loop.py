from __future__ import annotations

from dataclasses import replace

import pytest

from frankenstein2.agency_state import AgencyState, Interest, OpenLoop
from frankenstein2.effect_executor_interlock import (
    ExecutorObservation,
    ExternalGateDecision,
    ExternalGateEvidence,
    dispatch_through_external_gate,
)
from frankenstein2.effect_invocation_correlation import EffectCallBinding, EffectCorrelationStage
from frankenstein2.goal_lifecycle import (
    GOAL_ACTIVE,
    GOAL_CANDIDATE,
    GOAL_PATCH_SCHEMA,
    GoalRecord,
    GoalState,
    GoalStatePatch,
    GoalStatusChange,
)
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
from frankenstein2.wake_hold import OP_EQUALS, WAKE_ANY, WakeCondition
from frankenstein2.whole_persistent_loop import (
    EFFECT_VERIFIED,
    EffectOutcomeReentry,
    WholePersistentLoopError,
    seal_whole_persistent_loop,
)

A = "a" * 64
B = "b" * 64
D = "d" * 64
F = "f" * 64
RESULT_SHA = "9" * 64
CHILD_SHA = "8" * 64


def make_checkpoint():
    agency = AgencyState.create(
        state_id="agency:wp900",
        generation=3,
        interests=(
            Interest(
                interest_id="interest:wp900",
                label="Close typed whole-loop repository lineage",
                salience_ppm=800_000,
                provenance_refs=("owner:trigger4",),
            ),
        ),
        open_loops=(
            OpenLoop(
                loop_id="loop:wp900",
                summary="Bind persistent state through GRID/GWT and outcome re-entry",
                state="WAITING",
                priority_ppm=900_000,
                provenance_refs=("workpackage:F2-WP-900",),
            ),
        ),
    )
    genesis = GoalState.create(
        state_id="goal-state:wp900",
        generation=0,
        goals=(
            GoalRecord.candidate(
                goal_id="goal:wp900",
                summary="Produce bounded repository whole-loop evidence",
                priority_ppm=900_000,
                provenance_refs=("owner:trigger4",),
            ),
        ),
    )
    patch = GoalStatePatch(
        schema=GOAL_PATCH_SCHEMA,
        transition_id="goal-transition:wp900",
        expected_state_id=genesis.state_id,
        expected_generation=genesis.generation,
        expected_state_sha256=genesis.sha256(),
        next_generation=1,
        transition_refs=("evidence:explicit-adoption:wp900",),
        status_changes=(
            GoalStatusChange(
                goal_id="goal:wp900",
                expected_status=GOAL_CANDIDATE,
                next_status=GOAL_ACTIVE,
                evidence_refs=("evidence:explicit-adoption:wp900",),
                adoption_authority_ref="caller:trigger4-test",
            ),
        ),
    )
    replay = GoalReplayEnvelope.create(genesis=genesis, patches=(patch,))
    condition = WakeCondition(
        condition_id="wake:wp900",
        observation_key="ready",
        operator=OP_EQUALS,
        expected_value="yes",
        provenance_refs=("condition:wp900",),
    )
    return create_checkpoint(
        checkpoint_id="checkpoint:wp900:0",
        previous_checkpoint_id=None,
        kernel_state_id="kernel:wp900",
        generation=0,
        change_policy=CHANGE_POLICY_PROJECTION,
        agency_state=agency,
        goal_replay=replay,
        hold_id="hold:wp900",
        wake_policy=WAKE_ANY,
        wake_conditions=(condition,),
        hold_provenance_refs=("hold:wp900",),
        pulse_id="pulse:wp900:0",
        observation_id="observation:wp900:0",
        act_candidate_ref="candidate:act:wp900",
        wait_condition_ref="wait:wp900",
        hold_reason_ref="hold:wp900",
        delegate_candidate_ref="candidate:delegate:wp900",
        provenance_refs=("checkpoint:fixture:wp900", "owner:trigger4"),
    )


def make_plan(start_checkpoint):
    start_ref = f"checkpoint:{start_checkpoint.checkpoint_id}:{start_checkpoint.sha256()}"
    return Grid10Plan.create(
        plan_id="grid-plan:wp900",
        cycle_id="cycle:wp900",
        generation=5,
        frame_id="frame:wp900",
        frame_generation=2,
        frame_sha256=A,
        policy_id="grid-policy:wp900",
        policy_generation=1,
        policy_sha256=B,
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
        provenance_refs=(start_ref, "workpackage:F2-WP-900"),
    )


def make_gwt_fixture(plan):
    producer_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        input_refs=("input:producer:wp900",),
        provenance_refs=("prov:producer-input:wp900",),
    )
    producer_output = CellOutput.for_input(
        plan,
        producer_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=("payload:candidate:wp900",),
        evidence_refs=("evidence:producer:wp900",),
        provenance_refs=("prov:producer-output:wp900",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:wp900",
        payload_ref="payload:candidate:wp900",
        epistemic_class="INFERRED",
        provenance_refs=("prov:candidate:wp900",),
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
        policy_id="gwt-policy:wp900",
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
        selection_id="selection:wp900",
        cycle_id=plan.cycle_id,
        generation=8,
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
        broadcast_id="broadcast:wp900",
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
        input_refs=("payload:candidate:wp900",),
        provenance_refs=("prov:reentry-input:wp900",),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    downstream_output = CellOutput.for_input(
        plan,
        cell_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=("downstream:wp900",),
        evidence_refs=("evidence:downstream:wp900",),
        provenance_refs=("prov:downstream-output:wp900",),
    )
    receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:G1:wp900",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:wp900",
        downstream_sha256=downstream_output.sha256(),
        provenance_refs=("prov:uptake:wp900",),
    )
    summary = summarize_uptake(
        summary_id="summary:wp900",
        broadcast=broadcast,
        receipts=(receipt,),
        provenance_refs=("prov:summary:wp900",),
    )
    intervention = CausalProbeArm.intervention(
        arm_id="arm:intervention:wp900",
        probe_id="probe:wp900",
        broadcast=broadcast,
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=downstream_output.sha256(),
        provenance_refs=("prov:intervention:wp900",),
    )
    control = CausalProbeArm.control(
        arm_id="arm:control:wp900",
        probe_id="probe:wp900",
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=F,
        provenance_refs=("prov:control:wp900",),
    )
    causal = evaluate_causal_influence(
        result_id="causal:wp900",
        broadcast=broadcast,
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        provenance_refs=("prov:causal:wp900",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:wp900",
        witness=witness,
        uptake_receipt=receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:binding:wp900",),
    )
    return {
        "selection": selection,
        "broadcast": broadcast,
        "receipts": (receipt,),
        "uptake_summary": summary,
        "intervention": intervention,
        "control": control,
        "causal_result": causal,
        "reentry_bundles": (
            ReentryEvidenceBundle(
                binding=binding,
                witness=witness,
                uptake_receipt=receipt,
                cell_input=cell_input,
                downstream_output=downstream_output,
            ),
        ),
    }


def make_verified_effect_outcome(generation):
    prepared = EffectCallBinding(
        effect_id="effect:wp900",
        return_id="return:wp900",
        binding_id="binding:effect:wp900",
        invocation_id="invocation:wp900",
        tool_use_id="tool:wp900",
        delegation_id="delegation:wp900",
        child_identity_sha256=CHILD_SHA,
        stage=EffectCorrelationStage.PREPARED,
    )

    def authorize(call):
        return ExternalGateEvidence(
            authority_ref="canonical-effectgate:test-double",
            decision_id="decision:allow:wp900",
            decision=ExternalGateDecision.ALLOW,
            effect_id=call.effect_id,
            binding_id=call.binding_id,
            invocation_id=call.invocation_id,
            tool_use_id=call.tool_use_id,
            delegation_id=call.delegation_id,
            child_identity_sha256=call.child_identity_sha256,
        )

    def executor(call):
        return ExecutorObservation(
            effect_id=call.effect_id,
            binding_id=call.binding_id,
            invocation_id=call.invocation_id,
            tool_use_id=call.tool_use_id,
            delegation_id=call.delegation_id,
            child_identity_sha256=call.child_identity_sha256,
            result_id="result:wp900",
            result_sha256=RESULT_SHA,
        )

    interlock = dispatch_through_external_gate(
        prepared,
        authorize=authorize,
        executor=executor,
    )
    return EffectOutcomeReentry.from_interlock(
        interlock,
        cycle_id="cycle:wp900",
        generation=generation,
        provenance_refs=("test-double:in-memory-no-external-effect",),
    )


def make_bound_fixture():
    start = make_checkpoint()
    plan = make_plan(start)
    gwt = make_gwt_fixture(plan)
    nxt = advance_checkpoint(
        start,
        checkpoint_id="checkpoint:wp900:1",
        pulse_id="pulse:wp900:1",
        observation_id="observation:wp900:1",
    )
    outcome = make_verified_effect_outcome(nxt.generation)
    gwt_seal = seal_gwt_causal_path(
        seal_id="gwt-seal:wp900",
        plan=plan,
        provenance_refs=("prov:gwt-seal:wp900",),
        **gwt,
    )
    gwt_ref = f"gwt-seal:{gwt_seal.seal_id}:{gwt_seal.sha256()}"
    nxt = replace(
        nxt,
        provenance_refs=tuple(
            sorted(set(nxt.provenance_refs + (gwt_ref, outcome.outcome_ref)))
        ),
    )
    return start, nxt, plan, gwt, outcome


def seal(start, nxt, plan, gwt, outcome):
    return seal_whole_persistent_loop(
        seal_id="whole-loop:wp900",
        start_checkpoint=start,
        next_checkpoint=nxt,
        plan=plan,
        gwt_seal_id="gwt-seal:wp900",
        gwt_provenance_refs=("prov:gwt-seal:wp900",),
        effect_outcome=outcome,
        provenance_refs=("workpackage:F2-WP-900",),
        **gwt,
    )


def test_exact_typed_chain_seals_without_minting_runtime_or_whole_system_credit():
    start, nxt, plan, gwt, outcome = make_bound_fixture()
    observed = seal(start, nxt, plan, gwt, outcome)
    payload = observed.as_dict()
    assert observed.gwt_path_status == "CONTRACT_SCOPE_CAUSAL_PATH_SEALED"
    assert observed.effect_outcome_status == EFFECT_VERIFIED
    assert observed.next_checkpoint_generation == observed.start_checkpoint_generation + 1
    assert payload["runtime_credit"] == 0
    assert payload["target_runtime_credit"] == 0
    assert payload["physical_grid10_credit"] == 0
    assert payload["provider_model_credit"] == 0
    assert payload["training_credit"] == 0
    assert payload["whole_system_acceptance"] is False


def test_wrong_successor_generation_fails_closed():
    start, nxt, plan, gwt, outcome = make_bound_fixture()
    forged = replace(nxt, generation=nxt.generation + 1)
    with pytest.raises(WholePersistentLoopError, match="GENERATION_MISMATCH"):
        seal(start, forged, plan, gwt, outcome)


def test_wrong_successor_lineage_fails_closed():
    start, nxt, plan, gwt, outcome = make_bound_fixture()
    forged = replace(nxt, previous_checkpoint_id="checkpoint:foreign")
    with pytest.raises(WholePersistentLoopError, match="LINEAGE_MISMATCH"):
        seal(start, forged, plan, gwt, outcome)


def test_grid_plan_without_exact_start_checkpoint_lineage_is_rejected():
    start, nxt, plan, gwt, outcome = make_bound_fixture()
    forged_plan = replace(plan, provenance_refs=("workpackage:F2-WP-900",))
    with pytest.raises(
        WholePersistentLoopError, match="MISSING_START_CHECKPOINT_LINEAGE"
    ):
        seal(start, nxt, forged_plan, gwt, outcome)


def test_unknown_effect_outcome_cannot_close_or_replay_as_verified():
    start, nxt, plan, gwt, _outcome = make_bound_fixture()
    unknown = EffectOutcomeReentry.unknown(
        cycle_id=plan.cycle_id,
        generation=nxt.generation,
        outcome_ref="effect-outcome:unknown:wp900",
        effect_id="effect:wp900",
        provenance_refs=("canonical-journal:unknown:wp900",),
    )
    forged_next = replace(
        nxt,
        provenance_refs=tuple(
            sorted(set(nxt.provenance_refs + (unknown.outcome_ref,)))
        ),
    )
    with pytest.raises(
        WholePersistentLoopError, match="UNKNOWN_CANNOT_CLOSE_LOOP"
    ):
        seal(start, forged_next, plan, gwt, unknown)
