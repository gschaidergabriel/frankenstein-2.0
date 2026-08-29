"""REVIEW_ONLY falsifier for F2-WP-508 G1.

Hypothesis under test: a WP508 witness can currently bind an otherwise valid recipient
CellInput whose input_refs do not contain any payload offered by the bound BroadcastEnvelope.
If so, recipient/identity provenance exists without broadcast-content re-entry provenance.
"""
from __future__ import annotations

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import (
    GwtReentryProvenanceError,
    build_reentry_witness,
)
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
    create_broadcast,
)

D = "a" * 64
G = "e" * 64


def _plan() -> Grid10Plan:
    return Grid10Plan.create(
        plan_id="grid-plan-wp508-payload-falsifier",
        cycle_id="cycle-wp508-payload-falsifier",
        generation=3,
        frame_id="frame-wp508-payload-falsifier",
        frame_generation=4,
        frame_sha256=D,
        policy_id="grid-policy-wp508-payload-falsifier",
        policy_generation=1,
        policy_sha256=G,
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
        provenance_refs=("prov:grid-plan-wp508-payload-falsifier",),
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
        output_refs=("payload:broadcast-candidate",),
        evidence_refs=("evidence:producer",),
        provenance_refs=("prov:producer-output",),
    )
    admission = CandidateProducerAdmission(
        plan=plan,
        cell_input=producer_input,
        cell_output=producer_output,
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:wp508-payload-falsifier",
        payload_ref="payload:broadcast-candidate",
        epistemic_class="INFERRED",
        provenance_refs=("prov:candidate",),
        salience_micros=500_000,
        goal_relevance_micros=500_000,
        uncertainty_micros=100_000,
        information_gain_micros=500_000,
        estimated_cost_units=1,
        producer_admission=admission,
    )
    policy = SelectionPolicy(
        policy_id="gwt-policy-wp508-payload-falsifier",
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
        selection_id="selection:wp508-payload-falsifier",
        cycle_id=plan.cycle_id,
        generation=7,
        frame_id=plan.frame_id,
        frame_generation=plan.frame_generation,
        frame_sha256=plan.frame_sha256,
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        policy=policy,
        candidates=(candidate,),
    )


def test_reentry_must_reference_at_least_one_payload_from_bound_broadcast():
    plan = _plan()
    selection = _selection(plan)
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp508-payload-falsifier",
        generation=2,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )
    assert broadcast.candidate_payload_refs == ("payload:broadcast-candidate",)

    unrelated_reentry = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=("payload:unrelated-local-state",),
        provenance_refs=("prov:unrelated-reentry",),
    )

    # A provenance witness claiming this input is a re-entry from `broadcast` must fail
    # closed unless the input actually references content offered by that broadcast.
    with pytest.raises(GwtReentryProvenanceError, match="broadcast.*payload|payload.*broadcast"):
        build_reentry_witness(
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=unrelated_reentry,
        )
