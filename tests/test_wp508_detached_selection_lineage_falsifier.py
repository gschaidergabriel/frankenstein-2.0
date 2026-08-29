"""REVIEW_ONLY / CANDIDATE_FALSIFIER for F2-WP-508 generation 1.

A WP508 re-entry witness claims exact accepted WP506 selection/broadcast lineage.
This regression proves that a directly reconstructed WorkspaceSelection whose builder
lineage has been stripped must be rejected even when a directly reconstructed
BroadcastEnvelope is re-digested to match it.
"""
from dataclasses import replace

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import (
    GwtReentryProvenanceError,
    build_reentry_witness,
)
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    GwtWorkspaceError,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
    create_broadcast,
    verify_selection_binding,
)

D = "a" * 64
G = "e" * 64


def _fixture():
    plan = Grid10Plan.create(
        plan_id="grid-plan-wp508-review",
        cycle_id="cycle-wp508-review",
        generation=3,
        frame_id="frame-wp508-review",
        frame_generation=4,
        frame_sha256=D,
        policy_id="grid-policy-wp508-review",
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
        provenance_refs=("prov:grid-plan-wp508-review",),
    )
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
    admission = CandidateProducerAdmission(
        plan=plan,
        cell_input=producer_input,
        cell_output=producer_output,
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:wp508-review",
        payload_ref="payload:candidate",
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
        policy_id="gwt-policy-wp508-review",
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
        selection_id="selection:wp508-review",
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
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp508-review",
        generation=2,
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
    return plan, selection, broadcast, cell_input


def test_wp508_rejects_selection_with_stripped_wp506_builder_lineage():
    plan, selection, broadcast, cell_input = _fixture()

    # Direct dataclass reconstruction retains selected output while stripping the exact
    # builder policy/candidate lineage that WP506 itself requires at the consuming boundary.
    detached_selection = replace(
        selection,
        selection_policy=None,
        source_candidates=(),
    )

    with pytest.raises(GwtWorkspaceError, match="lacks exact builder policy/candidate lineage"):
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

    # Re-digest a concrete BroadcastEnvelope around the invalid selection. WP508 must
    # still reject it; internal digest agreement is not equivalent to accepted WP506 lineage.
    detached_broadcast = replace(
        broadcast,
        selection_sha256=detached_selection.sha256(),
    )

    with pytest.raises(GwtReentryProvenanceError):
        build_reentry_witness(
            plan=plan,
            selection=detached_selection,
            broadcast=detached_broadcast,
            cell_input=cell_input,
        )
