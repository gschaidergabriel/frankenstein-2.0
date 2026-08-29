import pytest

from frankenstein2.grid10_interface import CellBudget, Grid10Plan
from frankenstein2.gwt_workspace import (
    GWTWorkspaceError,
    WORKSPACE_SELECTION_SCHEMA,
    SelectedCandidate,
    WorkspaceSelection,
    create_broadcast,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64


def _plan() -> Grid10Plan:
    cells = tuple(
        CellBudget(
            cell_id=f"G{i}",
            role_label=f"role-{i}",
            max_input_refs=1,
            max_output_refs=1,
            max_work_units=10,
            max_reentry_depth=0,
        )
        for i in range(1, 11)
    )
    return Grid10Plan.create(
        plan_id="grid:canonical-main",
        cycle_id="cycle:canonical-main",
        generation=3,
        frame_id="frame:canonical-main",
        frame_generation=4,
        frame_sha256=A,
        policy_id="grid-policy:canonical-main",
        policy_generation=2,
        policy_sha256=B,
        cells=cells,
        max_total_work_units=100,
        provenance_refs=("prov:grid-plan",),
    )


def test_canonical_main_broadcast_rejects_direct_constructed_selection_without_producer_lineage():
    """REVIEW_ONLY: self-consistent object/digest is not proof of selection-policy execution."""
    plan = _plan()
    forged_selected = SelectedCandidate(
        candidate_id="candidate:forged",
        candidate_sha256=D,
        payload_ref="payload:forged",
        epistemic_class="OBSERVATION",
        rank_score=10**18,
        cost_units=0,
        provenance_refs=("prov:caller-only",),
    )
    forged_selection = WorkspaceSelection(
        schema=WORKSPACE_SELECTION_SCHEMA,
        selection_id="selection:forged",
        frame_id="frame:canonical-main",
        frame_generation=4,
        frame_sha256=A,
        plan_id=plan.plan_id,
        plan_generation=plan.generation,
        plan_sha256=plan.sha256(),
        policy_id="selection-policy:never-evaluated",
        policy_generation=999,
        policy_sha256=C,
        hyperposition_id=None,
        hyperposition_generation=None,
        hyperposition_sha256=None,
        selected=(forged_selected,),
        unresolved_candidate_ids=(),
        total_cost_units=0,
        provenance_refs=("prov:forged-selection",),
    )

    with pytest.raises(GWTWorkspaceError):
        create_broadcast(
            broadcast_id="broadcast:must-reject-forged-selection",
            selection=forged_selection,
            plan=plan,
            provenance_refs=("prov:broadcast",),
        )
