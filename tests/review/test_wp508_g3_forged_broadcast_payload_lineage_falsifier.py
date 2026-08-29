from dataclasses import replace

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import (
    GwtReentryUptakeBindingError,
    bind_reentry_to_uptake,
)
from frankenstein2.gwt_uptake import CellUptakeReceipt
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


def make_plan() -> Grid10Plan:
    return Grid10Plan.create(
        plan_id="grid-plan-review-wp508-g3-broadcast-lineage",
        cycle_id="cycle-review-wp508-g3-broadcast-lineage",
        generation=4,
        frame_id="frame-review-wp508-g3-broadcast-lineage",
        frame_generation=5,
        frame_sha256=A,
        policy_id="grid-policy-review-wp508-g3-broadcast-lineage",
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
        provenance_refs=("prov:grid-plan-review-wp508-g3",),
    )


def make_selection(plan: Grid10Plan):
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
        output_refs=("payload:selected-candidate",),
        evidence_refs=("evidence:producer",),
        provenance_refs=("prov:producer-output",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:review-wp508-g3-broadcast-lineage",
        payload_ref="payload:selected-candidate",
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
        policy_id="gwt-policy-review-wp508-g3-broadcast-lineage",
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
        selection_id="selection:review-wp508-g3-broadcast-lineage",
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


def test_g3_must_reject_forged_broadcast_payload_lineage_even_when_selection_binding_is_valid():
    plan = make_plan()
    selection = make_selection(plan)
    valid_broadcast = create_broadcast(
        broadcast_id="broadcast:review-wp508-g3-broadcast-lineage",
        generation=3,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )

    assert valid_broadcast.candidate_payload_refs == ("payload:selected-candidate",)

    # Direct dataclass reconstruction preserves all selection/plan identity fields while
    # replacing the material payload lineage. BroadcastEnvelope currently validates shape
    # but does not independently prove that candidate_payload_refs came from selection.selected.
    forged_broadcast = replace(
        valid_broadcast,
        candidate_payload_refs=("payload:forged-not-selected",),
    )
    assert forged_broadcast.selection_id == selection.selection_id
    assert forged_broadcast.selection_generation == selection.generation
    assert forged_broadcast.selection_sha256 == selection.sha256()
    assert forged_broadcast.candidate_payload_refs == ("payload:forged-not-selected",)

    forged_reentry_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=("payload:forged-not-selected",),
        provenance_refs=("prov:reentry-review-wp508-g3",),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=forged_broadcast,
        cell_input=forged_reentry_input,
    )
    receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:review-wp508-g3-broadcast-lineage",
        broadcast=forged_broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:review-wp508-g3",
        downstream_sha256=C,
        provenance_refs=("prov:receipt-review-wp508-g3",),
    )

    # WP508 G3 claims that broadcast-payload re-entry is source-bound. The candidate
    # implementation must therefore reject a broadcast whose payload list was detached
    # from the exact selected candidate lineage, even though its selection identity fields
    # and its self-consistent broadcast digest were recomputed.
    with pytest.raises(
        GwtReentryUptakeBindingError,
        match="broadcast|payload|lineage|selection",
    ):
        bind_reentry_to_uptake(
            binding_id="binding:review-wp508-g3-broadcast-lineage",
            witness=witness,
            uptake_receipt=receipt,
            plan=plan,
            selection=selection,
            broadcast=forged_broadcast,
            cell_input=forged_reentry_input,
            provenance_refs=("prov:binding-review-wp508-g3",),
        )
