from dataclasses import replace

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import (
    GwtReentryProvenanceError,
    GwtReentryProvenanceWitness,
    assert_unique_canonical_reentries,
    build_reentry_witness,
    validate_reentry_witness,
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


def make_plan():
    return Grid10Plan.create(
        plan_id="grid-plan-wp508",
        cycle_id="cycle-wp508",
        generation=3,
        frame_id="frame-wp508",
        frame_generation=4,
        frame_sha256=D,
        policy_id="grid-policy-wp508",
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
        provenance_refs=("prov:grid-plan-wp508",),
    )


def make_selection(plan):
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
        candidate_id="candidate:wp508",
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
        policy_id="gwt-policy-wp508",
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
        selection_id="selection:wp508",
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


def make_fixture(*, recipient_ids=("G1",), cell_id="G1", trace_id=None, span_id=None):
    plan = make_plan()
    selection = make_selection(plan)
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp508",
        generation=2,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=recipient_ids,
    )
    cell_input = CellInput.for_plan(
        plan,
        cell_id=cell_id,
        work_units_requested=2,
        reentry_depth=1,
        input_refs=("payload:candidate",),
        provenance_refs=("prov:reentry-input",),
    )
    witness = None
    if cell_id in recipient_ids:
        witness = build_reentry_witness(
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=cell_input,
            external_trace_id=trace_id,
            external_span_id=span_id,
        )
    return plan, selection, broadcast, cell_input, witness


def test_positive_exact_reentry_is_component_witness_only():
    plan, selection, broadcast, cell_input, witness = make_fixture()
    assert isinstance(witness, GwtReentryProvenanceWitness)
    validate_reentry_witness(
        witness,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    payload = witness.as_dict()
    assert payload["truth_authority"] == "NONE"
    assert payload["effect_authority"] == "NONE"
    assert payload["uptake_claim"] == "NOT_OBSERVED_BY_WP508_E3_WITNESS"
    assert payload["causal_influence_claim"] == "NOT_OBSERVED_BY_WP508_E3_WITNESS"


def test_cross_recipient_is_materially_rejected_beyond_valid_broadcast_shape():
    plan, selection, broadcast, cell_input, witness = make_fixture(
        recipient_ids=("G1",), cell_id="G2"
    )
    assert broadcast.recipient_cell_ids == ("G1",)
    assert witness is None
    with pytest.raises(GwtReentryProvenanceError, match="cross-recipient"):
        build_reentry_witness(
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=cell_input,
        )


def test_stale_broadcast_generation_fails_closed():
    plan, selection, broadcast, cell_input, witness = make_fixture()
    forged = replace(witness, broadcast_generation=witness.broadcast_generation + 1)
    with pytest.raises(GwtReentryProvenanceError, match="broadcast generation mismatch"):
        validate_reentry_witness(
            forged,
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=cell_input,
        )


def test_wrong_frame_digest_fails_even_with_valid_external_trace_metadata():
    plan, selection, broadcast, cell_input, witness = make_fixture(
        trace_id="trace:correlation-only",
        span_id="span:correlation-only",
    )
    forged = replace(witness, frame_sha256="f" * 64)
    with pytest.raises(GwtReentryProvenanceError, match="frame digest mismatch"):
        validate_reentry_witness(
            forged,
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=cell_input,
        )


def test_orphan_parent_or_link_is_rejected_until_canonical_ref_is_resolved():
    plan, selection, broadcast, cell_input, _ = make_fixture()
    with pytest.raises(GwtReentryProvenanceError, match="orphan lineage reference"):
        build_reentry_witness(
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=cell_input,
            parent_ref="witness:missing-parent",
            link_refs=("witness:missing-link",),
            known_lineage_refs=(),
        )
    accepted = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        parent_ref="witness:parent",
        link_refs=("witness:contributor",),
        known_lineage_refs=("witness:parent", "witness:contributor"),
    )
    assert accepted.lineage_refs() == ("witness:contributor", "witness:parent")


def test_fresh_external_trace_id_cannot_mint_a_new_canonical_reentry():
    plan, selection, broadcast, cell_input, first = make_fixture(
        trace_id="trace:first", span_id="span:first"
    )
    second = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        external_trace_id="trace:second",
        external_span_id="span:second",
    )
    assert first.sha256() != second.sha256()
    assert first.canonical_reentry_key() == second.canonical_reentry_key()
    with pytest.raises(GwtReentryProvenanceError, match="replay alias"):
        assert_unique_canonical_reentries((first, second))


def test_trace_metadata_is_all_present_or_all_absent():
    plan, selection, broadcast, cell_input, _ = make_fixture()
    with pytest.raises(GwtReentryProvenanceError, match="trace_id and span_id together"):
        build_reentry_witness(
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=cell_input,
            external_trace_id="trace:partial",
        )


def test_zero_depth_input_is_not_reentry():
    plan = make_plan()
    selection = make_selection(plan)
    broadcast = create_broadcast(
        broadcast_id="broadcast:zero-depth",
        generation=2,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=0,
        input_refs=("payload:candidate",),
        provenance_refs=("prov:not-reentry",),
    )
    with pytest.raises(GwtReentryProvenanceError, match="not a re-entry"):
        build_reentry_witness(
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=cell_input,
        )
