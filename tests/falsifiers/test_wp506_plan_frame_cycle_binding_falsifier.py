import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    GwtWorkspaceError,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
)

A = "a" * 64
B = "b" * 64


def grid_plan():
    cells = tuple(
        CellBudget(
            cell_id=f"G{i}",
            role_label=f"role-{i}",
            max_input_refs=4,
            max_output_refs=4,
            max_work_units=4,
            max_reentry_depth=1,
        )
        for i in range(1, 11)
    )
    return Grid10Plan.create(
        plan_id="grid:bound",
        cycle_id="cycle:bound",
        generation=3,
        frame_id="frame:bound",
        frame_generation=4,
        frame_sha256=A,
        policy_id="grid-policy:bound",
        policy_generation=1,
        policy_sha256=B,
        cells=cells,
        max_total_work_units=40,
        provenance_refs=("prov:grid",),
    )


def admitted_candidate(plan):
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=1,
        input_refs=("input:one",),
        provenance_refs=("prov:input",),
    )
    cell_output = CellOutput.for_input(
        plan,
        cell_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=("payload:one",),
        evidence_refs=("evidence:one",),
        provenance_refs=("prov:output",),
    )
    return WorkspaceCandidate(
        candidate_id="candidate:one",
        payload_ref="payload:one",
        epistemic_class="INFERRED",
        provenance_refs=("prov:candidate",),
        salience_micros=500_000,
        goal_relevance_micros=500_000,
        uncertainty_micros=0,
        information_gain_micros=500_000,
        estimated_cost_units=1,
        producer_admission=CandidateProducerAdmission(
            plan=plan,
            cell_input=cell_input,
            cell_output=cell_output,
        ),
    )


def policy():
    return SelectionPolicy(
        policy_id="selection-policy:one",
        generation=1,
        max_selected_candidates=1,
        max_total_cost_units=2,
        salience_weight=1,
        goal_relevance_weight=1,
        uncertainty_weight=0,
        information_gain_weight=1,
        cost_weight=0,
    )


def select(*, cycle_id, frame_id, frame_generation, frame_sha256):
    plan = grid_plan()
    return build_workspace_selection(
        selection_id="selection:one",
        cycle_id=cycle_id,
        generation=1,
        frame_id=frame_id,
        frame_generation=frame_generation,
        frame_sha256=frame_sha256,
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        policy=policy(),
        candidates=(admitted_candidate(plan),),
    )


def test_selection_rejects_frame_identity_not_bound_to_its_exact_grid10_plan():
    with pytest.raises(GwtWorkspaceError):
        select(
            cycle_id="cycle:bound",
            frame_id="frame:foreign",
            frame_generation=99,
            frame_sha256="c" * 64,
        )


def test_selection_rejects_cycle_identity_not_bound_to_its_exact_grid10_plan():
    with pytest.raises(GwtWorkspaceError):
        select(
            cycle_id="cycle:foreign",
            frame_id="frame:bound",
            frame_generation=4,
            frame_sha256=A,
        )
