import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    GwtWorkspaceError,
    SelectionPolicy,
    WorkspaceCandidate,
    WorkspaceSelection,
    build_workspace_selection,
    create_broadcast,
    verify_selection_binding,
)

A = "a" * 64
B = "b" * 64
FORGED_SELECTION_SHA256 = "f" * 64


class SelfAttestingWorkspaceSelection(WorkspaceSelection):
    """Adversarial subtype reproducing the generation-2 digest self-attestation flaw."""

    def sha256(self) -> str:
        return FORGED_SELECTION_SHA256


def _plan() -> Grid10Plan:
    return Grid10Plan.create(
        plan_id="grid-plan-wp506-g3-selection-subtype",
        cycle_id="cycle-wp506-g3-selection-subtype",
        generation=4,
        frame_id="frame-wp506-g3-selection-subtype",
        frame_generation=5,
        frame_sha256=A,
        policy_id="grid-policy-wp506-g3-selection-subtype",
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
        provenance_refs=("prov:grid-plan-wp506-g3",),
    )


def _selection(plan: Grid10Plan) -> WorkspaceSelection:
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        input_refs=("input:producer",),
        provenance_refs=("prov:producer-input",),
    )
    cell_output = CellOutput.for_input(
        plan,
        cell_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=("payload:selected-candidate",),
        evidence_refs=("evidence:producer",),
        provenance_refs=("prov:producer-output",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:wp506-g3-selection-subtype",
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
            cell_input=cell_input,
            cell_output=cell_output,
        ),
    )
    policy = SelectionPolicy(
        policy_id="gwt-policy-wp506-g3-selection-subtype",
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
        selection_id="selection:wp506-g3-selection-subtype",
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


def _subtype(selection: WorkspaceSelection) -> WorkspaceSelection:
    return SelfAttestingWorkspaceSelection(
        selection_id=selection.selection_id,
        cycle_id=selection.cycle_id,
        generation=selection.generation,
        frame_id=selection.frame_id,
        frame_generation=selection.frame_generation,
        frame_sha256=selection.frame_sha256,
        grid_plan_id=selection.grid_plan_id,
        grid_plan_generation=selection.grid_plan_generation,
        grid_plan_sha256=selection.grid_plan_sha256,
        policy_id=selection.policy_id,
        policy_generation=selection.policy_generation,
        policy_sha256=selection.policy_sha256,
        selected=selection.selected,
        deferred_candidate_ids=selection.deferred_candidate_ids,
        hyperposition_id=selection.hyperposition_id,
        hyperposition_generation=selection.hyperposition_generation,
        hyperposition_sha256=selection.hyperposition_sha256,
        hyperposition=selection.hyperposition,
        selection_policy=selection.selection_policy,
        source_candidates=selection.source_candidates,
    )


def test_verify_selection_binding_rejects_digest_self_attesting_subtype():
    plan = _plan()
    canonical = _selection(plan)
    adversarial = _subtype(canonical)
    assert type(canonical) is WorkspaceSelection
    assert type(adversarial) is SelfAttestingWorkspaceSelection
    assert adversarial.sha256() == FORGED_SELECTION_SHA256

    with pytest.raises(GwtWorkspaceError, match="concrete WorkspaceSelection"):
        verify_selection_binding(
            adversarial,
            expected_generation=adversarial.generation,
            expected_selection_sha256=FORGED_SELECTION_SHA256,
            frame_id=plan.frame_id,
            frame_generation=plan.frame_generation,
            frame_sha256=plan.frame_sha256,
            grid_plan_id=plan.plan_id,
            grid_plan_generation=plan.generation,
            grid_plan_sha256=plan.sha256(),
        )


def test_create_broadcast_rejects_digest_self_attesting_subtype():
    canonical = _selection(_plan())
    adversarial = _subtype(canonical)

    with pytest.raises(GwtWorkspaceError, match="concrete WorkspaceSelection"):
        create_broadcast(
            broadcast_id="broadcast:wp506-g3-selection-subtype",
            generation=3,
            selection=adversarial,
            expected_selection_sha256=FORGED_SELECTION_SHA256,
            recipient_cell_ids=("G1",),
        )
