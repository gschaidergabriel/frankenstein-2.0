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
    GwtWorkspaceError,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
    create_broadcast,
    verify_selection_binding,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64


def make_plan():
    return Grid10Plan.create(
        plan_id="grid-plan-review-wp508-g2",
        cycle_id="cycle-review-wp508-g2",
        generation=4,
        frame_id="frame-review-wp508-g2",
        frame_generation=5,
        frame_sha256=A,
        policy_id="grid-policy-review-wp508-g2",
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
        provenance_refs=("prov:grid-plan-review",),
    )


def make_valid_selection(plan):
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
        candidate_id="candidate:review-wp508-g2",
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
        policy_id="gwt-policy-review-wp508-g2",
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
        selection_id="selection:review-wp508-g2",
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


def make_broadcast(selection):
    return create_broadcast(
        broadcast_id="broadcast:review-wp508-g2",
        generation=3,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )


def make_receipt(broadcast):
    return CellUptakeReceipt.observe(
        receipt_id="receipt:review-wp508-g2",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:review",
        downstream_sha256=C,
        provenance_refs=("prov:receipt-review",),
    )


def bind(plan, selection, broadcast, cell_input, witness):
    return bind_reentry_to_uptake(
        binding_id="binding:review-wp508-g2",
        witness=witness,
        uptake_receipt=make_receipt(broadcast),
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:binding-review",),
    )


def test_g2_must_reject_wp508_witness_with_detached_wp506_builder_lineage():
    plan = make_plan()
    valid_selection = make_valid_selection(plan)
    detached_selection = replace(
        valid_selection,
        selection_policy=None,
        source_candidates=(),
    )

    # WP506 itself proves this object has lost its accepted builder lineage.
    with pytest.raises(GwtWorkspaceError):
        verify_selection_binding(
            detached_selection,
            expected_generation=detached_selection.generation,
            expected_selection_sha256=detached_selection.sha256(),
            frame_id=plan.frame_id,
            frame_generation=plan.frame_generation,
            frame_sha256=plan.frame_sha256,
            grid_plan_id=plan.plan_id,
            grid_plan_generation=plan.generation,
            grid_plan_sha256=plan.sha256(),
        )

    valid_broadcast = make_broadcast(valid_selection)
    detached_broadcast = replace(
        valid_broadcast,
        selection_sha256=detached_selection.sha256(),
    )
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=("payload:candidate",),
        provenance_refs=("prov:reentry-review",),
    )

    # Accepted G1 currently constructs a self-consistent witness around the detached pair.
    witness = build_reentry_witness(
        plan=plan,
        selection=detached_selection,
        broadcast=detached_broadcast,
        cell_input=cell_input,
    )

    # G2 claims invalid WP508 witness lineage fails closed. This is the discriminator.
    with pytest.raises(GwtReentryUptakeBindingError):
        bind(plan, detached_selection, detached_broadcast, cell_input, witness)


def test_g2_must_reject_wp508_witness_without_broadcast_payload_reentry():
    plan = make_plan()
    selection = make_valid_selection(plan)
    broadcast = make_broadcast(selection)
    unrelated_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=("local:unrelated",),
        provenance_refs=("prov:reentry-review",),
    )
    plan.validate_input(unrelated_input)

    # Accepted G1 currently witnesses recipient/depth identity even without payload overlap.
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=unrelated_input,
    )

    # G2 must not upgrade that structural gap into an uptake-reentry binding.
    with pytest.raises(GwtReentryUptakeBindingError):
        bind(plan, selection, broadcast, unrelated_input, witness)
