"""REVIEW_ONLY falsifier for WP508 G4 exact-type fail-closed ordering.

The accepted WP508 binding promises exact concrete object lineage via the downstream
WP508 provenance validator.  This test checks a stronger trust-boundary invariant:
untrusted subclass methods must not execute before the concrete-type guard rejects
that object.

Expected on the currently accepted source: FAIL, because bind_reentry_to_uptake()
reaches plan.sha256() inside _validate_wp506_reentry_lineage() before
validate_reentry_witness() runs the exact Grid10Plan type check.
"""

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import (
    GwtReentryProvenanceError,
    build_reentry_witness,
)
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
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


def _plan(plan_cls=Grid10Plan):
    return plan_cls.create(
        plan_id="grid-plan-wp508-prevalidation-review",
        cycle_id="cycle-wp508-prevalidation-review",
        generation=4,
        frame_id="frame-wp508-prevalidation-review",
        frame_generation=5,
        frame_sha256=A,
        policy_id="grid-policy-wp508-prevalidation-review",
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
        provenance_refs=("prov:grid-plan-wp508-prevalidation-review",),
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
        candidate_id="candidate:wp508-prevalidation-review",
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
        policy_id="gwt-policy-wp508-prevalidation-review",
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
        selection_id="selection:wp508-prevalidation-review",
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
        broadcast_id="broadcast:wp508-prevalidation-review",
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
        input_refs=("payload:candidate",),
        provenance_refs=("prov:reentry-input",),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:G1:DELIVERED:UPTAKEN",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:observed",
        downstream_sha256=C,
        provenance_refs=("prov:wp507-receipt",),
    )
    return plan, selection, broadcast, cell_input, witness, receipt


def test_wp508_rejects_plan_subclass_before_invoking_overridden_sha256():
    plan, selection, broadcast, cell_input, witness, receipt = _fixture()

    class HostileGrid10Plan(Grid10Plan):
        def sha256(self):
            raise RuntimeError("HOSTILE_GRID10_PLAN_SHA256_EXECUTED_BEFORE_TYPE_REJECTION")

    hostile_plan = _plan(HostileGrid10Plan)

    # The desired fail-closed boundary is the exact-type error from WP508 provenance
    # validation. Any RuntimeError here proves hostile subtype code executed first.
    with pytest.raises(GwtReentryProvenanceError, match="plan must be concrete Grid10Plan"):
        bind_reentry_to_uptake(
            binding_id="binding:wp508-prevalidation-review",
            witness=witness,
            uptake_receipt=receipt,
            plan=hostile_plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=cell_input,
            provenance_refs=("prov:wp508-prevalidation-review",),
        )
