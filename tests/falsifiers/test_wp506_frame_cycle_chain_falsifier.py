import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    GwtWorkspaceError,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
)

FRAME_SHA = "a" * 64
GRID_POLICY_SHA = "b" * 64


def plan() -> Grid10Plan:
    cells = tuple(
        CellBudget(
            cell_id=f"G{i}", role_label=f"role-{i}", max_input_refs=8,
            max_output_refs=8, max_work_units=8, max_reentry_depth=2,
        )
        for i in range(1, 11)
    )
    return Grid10Plan.create(
        plan_id="grid-plan-frame-a", cycle_id="cycle-a", generation=3,
        frame_id="frame-a", frame_generation=4, frame_sha256=FRAME_SHA,
        policy_id="grid-policy", policy_generation=1, policy_sha256=GRID_POLICY_SHA,
        cells=cells, max_total_work_units=80, provenance_refs=("plan-prov",),
    )


def candidate_for(p: Grid10Plan) -> WorkspaceCandidate:
    cell_input = CellInput.for_plan(
        p, cell_id="G1", work_units_requested=2,
        input_refs=("input:a",), provenance_refs=("input-prov",),
    )
    cell_output = CellOutput.for_input(
        p, cell_input, status="COMPLETE", work_units_used=1,
        output_refs=("payload:a",), evidence_refs=("evidence:a",),
        provenance_refs=("output-prov",),
    )
    admission = CandidateProducerAdmission(plan=p, cell_input=cell_input, cell_output=cell_output)
    return WorkspaceCandidate(
        candidate_id="candidate:a", payload_ref="payload:a", epistemic_class="INFERRED",
        provenance_refs=("candidate-prov",), salience_micros=500_000,
        goal_relevance_micros=500_000, uncertainty_micros=100_000,
        information_gain_micros=500_000, estimated_cost_units=1,
        producer_admission=admission,
    )


def policy() -> SelectionPolicy:
    return SelectionPolicy(
        policy_id="gwt-policy", generation=1, max_selected_candidates=1,
        max_total_cost_units=5, salience_weight=1, goal_relevance_weight=1,
        uncertainty_weight=1, information_gain_weight=1, cost_weight=1,
    )


@pytest.mark.parametrize(
    ("cycle_id", "frame_id", "frame_generation", "frame_sha256"),
    [
        ("cycle-b", "frame-a", 4, FRAME_SHA),
        ("cycle-a", "frame-b", 4, FRAME_SHA),
        ("cycle-a", "frame-a", 5, FRAME_SHA),
        ("cycle-a", "frame-a", 4, "c" * 64),
    ],
)
def test_selection_outer_cycle_and_frame_must_match_exact_producer_grid_plan(
    cycle_id, frame_id, frame_generation, frame_sha256
):
    p = plan()
    source = candidate_for(p)
    with pytest.raises(GwtWorkspaceError):
        build_workspace_selection(
            selection_id="selection:must-reject-mislabeled-frame",
            cycle_id=cycle_id,
            generation=7,
            frame_id=frame_id,
            frame_generation=frame_generation,
            frame_sha256=frame_sha256,
            grid_plan_id=p.plan_id,
            grid_plan_generation=p.generation,
            grid_plan_sha256=p.sha256(),
            policy=policy(),
            candidates=(source,),
        )
