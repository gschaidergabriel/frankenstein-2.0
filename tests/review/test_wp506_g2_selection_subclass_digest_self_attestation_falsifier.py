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
    """Review-only adversarial subtype that overrides the public digest method."""

    def sha256(self) -> str:
        return FORGED_SELECTION_SHA256


def make_plan() -> Grid10Plan:
    return Grid10Plan.create(
        plan_id="grid-plan-review-wp506-g2-selection-subtype",
        cycle_id="cycle-review-wp506-g2-selection-subtype",
        generation=4,
        frame_id="frame-review-wp506-g2-selection-subtype",
        frame_generation=5,
        frame_sha256=A,
        policy_id="grid-policy-review-wp506-g2-selection-subtype",
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
        provenance_refs=("prov:grid-plan-review-wp506-g2",),
    )


def make_selection(plan: Grid10Plan) -> WorkspaceSelection:
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
        output_refs=("payload:selected-candidate",),
        evidence_refs=("evidence:producer",),
        provenance_refs=("prov:producer-output",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:review-wp506-g2-selection-subtype",
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
            cell_input=producer_input,
            cell_output=producer_output,
        ),
    )
    policy = SelectionPolicy(
        policy_id="gwt-policy-review-wp506-g2-selection-subtype",
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
        selection_id="selection:review-wp506-g2-selection-subtype",
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


def subtype_with_identical_builder_state(selection: WorkspaceSelection) -> WorkspaceSelection:
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


def test_verify_selection_binding_must_reject_digest_self_attesting_subtype():
    plan = make_plan()
    canonical = make_selection(plan)
    adversarial = subtype_with_identical_builder_state(canonical)

    assert type(canonical) is WorkspaceSelection
    assert type(adversarial) is SelfAttestingWorkspaceSelection
    assert canonical.sha256() != FORGED_SELECTION_SHA256
    assert adversarial.sha256() == FORGED_SELECTION_SHA256
    assert adversarial.selected == canonical.selected
    assert adversarial.source_candidates == canonical.source_candidates

    with pytest.raises(GwtWorkspaceError, match="concrete|WorkspaceSelection|type"):
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


def test_create_broadcast_must_not_mint_from_digest_self_attesting_selection_subtype():
    plan = make_plan()
    canonical = make_selection(plan)
    adversarial = subtype_with_identical_builder_state(canonical)

    with pytest.raises(GwtWorkspaceError, match="concrete|WorkspaceSelection|type"):
        create_broadcast(
            broadcast_id="broadcast:review-wp506-g2-selection-subtype",
            generation=3,
            selection=adversarial,
            expected_selection_sha256=FORGED_SELECTION_SHA256,
            recipient_cell_ids=("G1",),
        )


def test_positive_reproduction_probe_current_wp506_accepts_self_attested_digest():
    """PASS means the exact current WP506 subtype/digest weakness is reproduced."""
    plan = make_plan()
    canonical = make_selection(plan)
    adversarial = subtype_with_identical_builder_state(canonical)

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
    broadcast = create_broadcast(
        broadcast_id="broadcast:review-wp506-g2-selection-subtype-positive-probe",
        generation=3,
        selection=adversarial,
        expected_selection_sha256=FORGED_SELECTION_SHA256,
        recipient_cell_ids=("G1",),
    )

    assert broadcast.selection_sha256 == FORGED_SELECTION_SHA256
    assert broadcast.selection_sha256 != canonical.sha256()
    assert broadcast.candidate_ids == tuple(item.candidate_id for item in canonical.selected)
    assert broadcast.candidate_payload_refs == tuple(item.payload_ref for item in canonical.selected)
