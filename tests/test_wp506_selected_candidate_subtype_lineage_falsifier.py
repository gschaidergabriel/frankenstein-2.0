"""Regression for the WP506 G3 SelectedCandidate subtype lineage split.

This originated as REVIEW_ONLY negative evidence in PR #274. The production repair must
reject a SelectedCandidate subtype that self-reports canonical as_dict() lineage while
exposing a different direct payload_ref later consumed by create_broadcast().
"""

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    GwtWorkspaceError,
    SelectedCandidate,
    SelectionPolicy,
    WorkspaceCandidate,
    WorkspaceSelection,
    build_workspace_selection,
    create_broadcast,
)

D = "a" * 64
G = "e" * 64


def _plan() -> Grid10Plan:
    cells = tuple(
        CellBudget(
            cell_id=f"G{i}",
            role_label=f"role-{i}",
            max_input_refs=8,
            max_output_refs=8,
            max_work_units=8,
            max_reentry_depth=2,
        )
        for i in range(1, 11)
    )
    return Grid10Plan.create(
        plan_id="grid-plan-falsifier",
        cycle_id="cycle-falsifier",
        generation=3,
        frame_id="frame-falsifier",
        frame_generation=4,
        frame_sha256=D,
        policy_id="grid-policy-falsifier",
        policy_generation=1,
        policy_sha256=G,
        cells=cells,
        max_total_work_units=80,
        provenance_refs=("prov:grid-plan-falsifier",),
    )


def _selection() -> WorkspaceSelection:
    plan = _plan()
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        input_refs=("input:a",),
        provenance_refs=("input-prov:a",),
    )
    cell_output = CellOutput.for_input(
        plan,
        cell_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=("payload:a",),
        evidence_refs=("evidence:a",),
        provenance_refs=("output-prov:a",),
    )
    admission = CandidateProducerAdmission(
        plan=plan,
        cell_input=cell_input,
        cell_output=cell_output,
    )
    candidate = WorkspaceCandidate(
        candidate_id="a",
        payload_ref="payload:a",
        epistemic_class="INFERRED",
        provenance_refs=("prov:a",),
        salience_micros=500_000,
        goal_relevance_micros=500_000,
        uncertainty_micros=100_000,
        information_gain_micros=500_000,
        estimated_cost_units=1,
        producer_admission=admission,
    )
    policy = SelectionPolicy(
        policy_id="gwt-policy-falsifier",
        generation=1,
        max_selected_candidates=3,
        max_total_cost_units=5,
        salience_weight=1,
        goal_relevance_weight=1,
        uncertainty_weight=1,
        information_gain_weight=1,
        cost_weight=1,
    )
    return build_workspace_selection(
        selection_id="sel-falsifier",
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


class ForgedSelectedCandidate(SelectedCandidate):
    """Expose a forged direct payload_ref while self-reporting canonical serialized lineage."""

    def as_dict(self):
        payload = super().as_dict()
        payload["payload_ref"] = "payload:a"
        return payload


def test_wp506_rejects_selected_candidate_subtype_attribute_lineage_split():
    canonical = _selection()
    original = canonical.selected[0]
    forged_item = ForgedSelectedCandidate(
        candidate_id=original.candidate_id,
        candidate_sha256=original.candidate_sha256,
        payload_ref="payload:forged",
        epistemic_class=original.epistemic_class,
        provenance_refs=original.provenance_refs,
        alternative_refs=original.alternative_refs,
        score=original.score,
        estimated_cost_units=original.estimated_cost_units,
        producer_admission_sha256=original.producer_admission_sha256,
        producer_cell_id=original.producer_cell_id,
        producer_output_sha256=original.producer_output_sha256,
    )
    forged = WorkspaceSelection(
        selection_id=canonical.selection_id,
        cycle_id=canonical.cycle_id,
        generation=canonical.generation,
        frame_id=canonical.frame_id,
        frame_generation=canonical.frame_generation,
        frame_sha256=canonical.frame_sha256,
        grid_plan_id=canonical.grid_plan_id,
        grid_plan_generation=canonical.grid_plan_generation,
        grid_plan_sha256=canonical.grid_plan_sha256,
        policy_id=canonical.policy_id,
        policy_generation=canonical.policy_generation,
        policy_sha256=canonical.policy_sha256,
        selected=(forged_item,),
        deferred_candidate_ids=canonical.deferred_candidate_ids,
        hyperposition_id=canonical.hyperposition_id,
        hyperposition_generation=canonical.hyperposition_generation,
        hyperposition_sha256=canonical.hyperposition_sha256,
        hyperposition=canonical.hyperposition,
        selection_policy=canonical.selection_policy,
        source_candidates=canonical.source_candidates,
    )

    # The adversarial subtype preserves the prior vulnerable canonical selection digest.
    assert forged.sha256() == canonical.sha256()

    # The repaired public broadcast boundary must reject before direct payload_ref consumption.
    with pytest.raises(GwtWorkspaceError, match="concrete SelectedCandidate"):
        create_broadcast(
            broadcast_id="broadcast-falsifier",
            generation=1,
            selection=forged,
            expected_selection_sha256=canonical.sha256(),
            recipient_cell_ids=("G1",),
        )
