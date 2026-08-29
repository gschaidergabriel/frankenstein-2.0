"""REVIEW_ONLY executable discriminator for F2-WP-510 generation 1.

This file does not modify canonical WP510 source. It tests the preregistered
cross-recipient invariant: binding cardinality must never substitute for exact
UPTAKEN-recipient set equality.
"""
import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_causal_path import (
    GwtCausalPathError,
    ReentryEvidenceBundle,
    seal_gwt_causal_path,
)
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

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64


def _plan():
    return Grid10Plan.create(
        plan_id="grid-plan-wp510-review",
        cycle_id="cycle-wp510-review",
        generation=4,
        frame_id="frame-wp510-review",
        frame_generation=5,
        frame_sha256=A,
        policy_id="grid-policy-wp510-review",
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
        provenance_refs=("prov:grid-plan-wp510-review",),
    )


def _selection(plan):
    producer_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        input_refs=("input:producer",),
        provenance_refs=("prov:producer-input",),
    )
    producer_output = CellOutput.for_input(
        plan,
        producer_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=("payload:candidate",),
        evidence_refs=("evidence:producer",),
        provenance_refs=("prov:producer-output",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:wp510-review",
        payload_ref="payload:candidate",
        epistemic_class="INFERRED",
        provenance_refs=("prov:candidate",),
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
        policy_id="gwt-policy-wp510-review",
        generation=1,
        max_selected_candidates=1,
        max_total_cost_units=4,
        salience_weight=1,
        goal_relevance_weight=1,
        uncertainty_weight=1,
        information_gain_weight=1,
        cost_weight=1,
    )
    return build_workspace_selection(
        selection_id="selection:wp510-review",
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


def _fixture():
    plan = _plan()
    selection = _selection(plan)
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp510-review",
        generation=3,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1", "G2"),
    )
    receipts = tuple(
        CellUptakeReceipt.observe(
            receipt_id=f"receipt:{cell}:wp510-review",
            broadcast=broadcast,
            cell_id=cell,
            delivery_status="DELIVERED",
            uptake_status="UPTAKEN",
            downstream_ref=f"downstream:{cell}",
            downstream_sha256=C,
            provenance_refs=(f"prov:receipt:{cell}",),
        )
        for cell in ("G1", "G2")
    )
    summary = summarize_uptake(
        summary_id="summary:wp510-review",
        broadcast=broadcast,
        receipts=receipts,
        provenance_refs=("prov:summary",),
    )
    intervention = CausalProbeArm.intervention(
        arm_id="arm:intervention:wp510-review",
        probe_id="probe:wp510-review",
        broadcast=broadcast,
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=E,
        provenance_refs=("prov:intervention",),
    )
    control = CausalProbeArm.control(
        arm_id="arm:control:wp510-review",
        probe_id="probe:wp510-review",
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=F,
        provenance_refs=("prov:control",),
    )
    causal = evaluate_causal_influence(
        result_id="causal:wp510-review",
        broadcast=broadcast,
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        provenance_refs=("prov:causal",),
    )
    return plan, selection, broadcast, receipts, summary, intervention, control, causal


def _bundle(plan, selection, broadcast, receipt, cell_id, binding_id):
    cell_input = CellInput.for_plan(
        plan,
        cell_id=cell_id,
        work_units_requested=2,
        reentry_depth=1,
        input_refs=("payload:candidate",),
        provenance_refs=(f"prov:reentry-input:{binding_id}",),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    binding = bind_reentry_to_uptake(
        binding_id=binding_id,
        witness=witness,
        uptake_receipt=receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=(f"prov:binding:{binding_id}",),
    )
    return ReentryEvidenceBundle(
        binding=binding,
        witness=witness,
        uptake_receipt=receipt,
        cell_input=cell_input,
    )


def _seal(fx, bundles):
    plan, selection, broadcast, receipts, summary, intervention, control, causal = fx
    return seal_gwt_causal_path(
        seal_id="seal:wp510-review",
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        receipts=receipts,
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        causal_result=causal,
        reentry_bundles=tuple(bundles),
        provenance_refs=("prov:seal",),
    )


def test_two_uptaken_recipients_cannot_be_satisfied_by_two_bindings_for_g1():
    fx = _fixture()
    plan, selection, broadcast, receipts, *_ = fx
    g1_a = _bundle(plan, selection, broadcast, receipts[0], "G1", "binding:G1:a")
    g1_b = _bundle(plan, selection, broadcast, receipts[0], "G1", "binding:G1:b")

    # Cardinality matches (2 bindings, 2 UPTAKEN recipients), but recipient identity does not.
    with pytest.raises(GwtCausalPathError, match="multiple re-entry bindings for one recipient"):
        _seal(fx, (g1_a, g1_b))


def test_exact_one_to_one_binding_for_each_uptaken_recipient_remains_admissible():
    fx = _fixture()
    plan, selection, broadcast, receipts, *_ = fx
    g1 = _bundle(plan, selection, broadcast, receipts[0], "G1", "binding:G1")
    g2 = _bundle(plan, selection, broadcast, receipts[1], "G2", "binding:G2")

    observed = _seal(fx, (g1, g2))
    assert observed.uptaken_cell_ids == ("G1", "G2")
    assert observed.path_status == "CONTRACT_SCOPE_CAUSAL_PATH_SEALED"
    assert observed.as_dict()["runtime_credit"] == 0
    assert observed.as_dict()["whole_system_acceptance"] is False
