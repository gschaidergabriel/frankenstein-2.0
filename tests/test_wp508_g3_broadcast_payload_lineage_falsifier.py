"""REVIEW_ONLY executable falsifier for F2-WP-508 generation 3.

Hypothesis under test:
A directly constructed BroadcastEnvelope can preserve an exact valid WorkspaceSelection
identity while replacing candidate_ids/candidate_payload_refs with payload lineage that was
never selected. If WP508 G3 accepts a re-entry whose only matching input ref comes from that
forged broadcast payload list, then the new G3 payload-lineage fence still trusts a
self-attested BroadcastEnvelope field instead of exact WP506 broadcast-builder lineage.

This file changes no production source and grants no runtime/GWT/J-Space credit.
The expected result on a vulnerable source is FAILURE_AS_EXPECTED (DID NOT RAISE).
"""

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import (
    GwtReentryProvenanceError,
    build_reentry_witness,
)
from frankenstein2.gwt_reentry_uptake_binding import (
    GwtReentryUptakeBindingError,
    bind_reentry_to_uptake,
)
from frankenstein2.gwt_uptake import CellUptakeReceipt, GWTUptakeError
from frankenstein2.gwt_workspace import (
    BroadcastEnvelope,
    CandidateProducerAdmission,
    GwtWorkspaceError,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
)

A = "a" * 64
B = "b" * 64


def _plan() -> Grid10Plan:
    return Grid10Plan.create(
        plan_id="grid-plan-wp508-g3-broadcast-lineage-falsifier",
        cycle_id="cycle-wp508-g3-broadcast-lineage-falsifier",
        generation=4,
        frame_id="frame-wp508-g3-broadcast-lineage-falsifier",
        frame_generation=5,
        frame_sha256=A,
        policy_id="grid-policy-wp508-g3-broadcast-lineage-falsifier",
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
        provenance_refs=("prov:grid-plan",),
    )


def _selection(plan: Grid10Plan):
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
        output_refs=("payload:selected",),
        evidence_refs=("evidence:producer",),
        provenance_refs=("prov:producer-output",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:selected",
        payload_ref="payload:selected",
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
        policy_id="gwt-policy-wp508-g3-broadcast-lineage-falsifier",
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
        selection_id="selection:wp508-g3-broadcast-lineage-falsifier",
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


def test_direct_broadcast_constructor_cannot_replace_selected_payload_lineage():
    plan = _plan()
    selection = _selection(plan)

    # Exact valid selection identity, but the broadcast payload was never selected.
    # Current BroadcastEnvelope validation only checks local field shape, so this is the
    # candidate self-attestation boundary the falsifier targets.
    with pytest.raises(
        (
            GwtWorkspaceError,
            GwtReentryProvenanceError,
            GwtReentryUptakeBindingError,
            GWTUptakeError,
        )
    ):
        forged_broadcast = BroadcastEnvelope(
            broadcast_id="broadcast:forged-payload-lineage",
            cycle_id=selection.cycle_id,
            generation=3,
            selection_id=selection.selection_id,
            selection_generation=selection.generation,
            selection_sha256=selection.sha256(),
            plan_id=selection.grid_plan_id,
            plan_generation=selection.grid_plan_generation,
            plan_sha256=selection.grid_plan_sha256,
            recipient_cell_ids=("G1",),
            candidate_ids=("candidate:forged",),
            candidate_payload_refs=("payload:forged",),
        )
        assert "payload:forged" not in tuple(item.payload_ref for item in selection.selected)

        reentry_input = CellInput.for_plan(
            plan,
            cell_id="G1",
            work_units_requested=2,
            reentry_depth=1,
            input_refs=("payload:forged",),
            provenance_refs=("prov:forged-reentry",),
        )
        witness = build_reentry_witness(
            plan=plan,
            selection=selection,
            broadcast=forged_broadcast,
            cell_input=reentry_input,
        )
        receipt = CellUptakeReceipt.observe(
            receipt_id="receipt:forged-payload-lineage",
            broadcast=forged_broadcast,
            cell_id="G1",
            delivery_status="OFFERED",
            uptake_status="UNKNOWN",
            provenance_refs=("prov:receipt",),
        )
        bind_reentry_to_uptake(
            binding_id="binding:forged-payload-lineage",
            witness=witness,
            uptake_receipt=receipt,
            plan=plan,
            selection=selection,
            broadcast=forged_broadcast,
            cell_input=reentry_input,
            provenance_refs=("prov:binding",),
        )
