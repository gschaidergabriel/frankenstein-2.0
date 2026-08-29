import pytest

from frankenstein2.grid10_interface import CellBudget, Grid10Plan
from frankenstein2.gwt_workspace import (
    GWTWorkspaceError,
    WORKSPACE_SELECTION_SCHEMA,
    SelectedCandidate,
    WorkspaceSelection,
    create_broadcast,
)
from frankenstein2.situation_frame import EpistemicRef, SituationFrame

H64 = "a" * 64
P64 = "b" * 64
Q64 = "c" * 64
R64 = "d" * 64


def make_frame() -> SituationFrame:
    return SituationFrame.create(
        frame_id="frame-forged-boundary",
        cycle_id="cycle-forged-boundary",
        generation=1,
        situation_epoch=1,
        agency_state_ref="agency-state-1",
        agency_state_generation=1,
        agency_state_sha256=H64,
        epistemic_refs=(EpistemicRef(kind="UNKNOWN", ref="unknown-1"),),
        unresolved_alternative_refs=("alt-a", "alt-b"),
        authority_scope_refs=("candidate-only",),
        provenance_refs=("frame-source",),
    )


def make_plan(frame: SituationFrame) -> Grid10Plan:
    cells = tuple(
        CellBudget(
            cell_id=f"G{i}",
            role_label=f"role-{i}",
            max_input_refs=8,
            max_output_refs=8,
            max_work_units=20,
            max_reentry_depth=2,
        )
        for i in range(1, 11)
    )
    return Grid10Plan.create(
        plan_id="grid-plan-forged-boundary",
        cycle_id=frame.cycle_id,
        generation=2,
        frame_id=frame.frame_id,
        frame_generation=frame.generation,
        frame_sha256=frame.sha256(),
        policy_id="grid-policy-1",
        policy_generation=1,
        policy_sha256=P64,
        cells=cells,
        max_total_work_units=100,
        provenance_refs=("grid-plan-source",),
    )


def test_direct_workspace_selection_cannot_bypass_policy_before_broadcast():
    """A self-consistent forged selection must not become broadcast-admissible."""
    frame = make_frame()
    plan = make_plan(frame)
    forged_selected = SelectedCandidate(
        candidate_id="candidate:forged",
        candidate_sha256=R64,
        payload_ref="payload:forged",
        epistemic_class="OBSERVATION",
        rank_score=10**18,
        cost_units=0,
        provenance_refs=("caller-only",),
    )
    forged_selection = WorkspaceSelection(
        schema=WORKSPACE_SELECTION_SCHEMA,
        selection_id="selection:forged",
        frame_id=frame.frame_id,
        frame_generation=frame.generation,
        frame_sha256=frame.sha256(),
        plan_id=plan.plan_id,
        plan_generation=plan.generation,
        plan_sha256=plan.sha256(),
        policy_id="policy:never-evaluated",
        policy_generation=999,
        policy_sha256=Q64,
        hyperposition_id=None,
        hyperposition_generation=None,
        hyperposition_sha256=None,
        selected=(forged_selected,),
        unresolved_candidate_ids=(),
        total_cost_units=0,
        provenance_refs=("caller-only",),
    )

    with pytest.raises(GWTWorkspaceError):
        create_broadcast(
            broadcast_id="broadcast:must-reject-forged-selection",
            selection=forged_selection,
            plan=plan,
            provenance_refs=("broadcast-source",),
        )
