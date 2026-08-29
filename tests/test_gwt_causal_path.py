from dataclasses import replace

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_causal_path import (
    GwtCausalPathError,
    ReentryBindingEvidence,
    seal_gwt_causal_path,
    validate_gwt_causal_path_seal,
)
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_uptake import (
    CausalProbeArm,
    CellUptakeReceipt,
    evaluate_causal_influence,
    summarize_uptake,
)
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
    create_broadcast,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64


def make_plan():
    return Grid10Plan.create(
        plan_id="grid-plan-wp510",
        cycle_id="cycle-wp510",
        generation=5,
        frame_id="frame-wp510",
        frame_generation=6,
        frame_sha256=A,
        policy_id="grid-policy-wp510",
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
        provenance_refs=("prov:grid-plan-wp510",),
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
        output_refs=("payload:wp510",),
        evidence_refs=("evidence:producer",),
        provenance_refs=("prov:producer-output",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:wp510",
        payload_ref="payload:wp510",
        epistemic_class="INFERRED",
        provenance_refs=("prov:candidate",),
        salience_micros=700_000,
        goal_relevance_micros=600_000,
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
        policy_id="gwt-policy-wp510",
        generation=2,
        max_selected_candidates=1,
        max_total_cost_units=4,
        salience_weight=1,
        goal_relevance_weight=1,
        uncertainty_weight=1,
        information_gain_weight=1,
        cost_weight=1,
    )
    return build_workspace_selection(
        selection_id="selection:wp510",
        cycle_id=plan.cycle_id,
        generation=9,
        frame_id=plan.frame_id,
        frame_generation=plan.frame_generation,
        frame_sha256=plan.frame_sha256,
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        policy=policy,
        candidates=(candidate,),
    )


def make_base():
    plan = make_plan()
    selection = make_selection(plan)
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp510",
        generation=4,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )
    return plan, selection, broadcast


def make_receipt(broadcast, *, receipt_id="receipt:wp510", delivery="DELIVERED", uptake="UPTAKEN"):
    return CellUptakeReceipt.observe(
        receipt_id=receipt_id,
        broadcast=broadcast,
        cell_id="G1",
        delivery_status=delivery,
        uptake_status=uptake,
        downstream_ref="downstream:wp510" if uptake == "UPTAKEN" else None,
        downstream_sha256=C if uptake == "UPTAKEN" else None,
        provenance_refs=("prov:wp507-receipt",),
    )


def make_probe_pair(broadcast, *, same_output=False):
    intervention = CausalProbeArm.intervention(
        arm_id="arm:intervention",
        probe_id="probe:wp510",
        broadcast=broadcast,
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=E,
        provenance_refs=("prov:intervention",),
    )
    control = CausalProbeArm.control(
        arm_id="arm:control",
        probe_id="probe:wp510",
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=E if same_output else B,
        provenance_refs=("prov:control",),
    )
    return intervention, control


def make_reentry(plan, selection, broadcast, receipt, *, binding_id="binding:wp510"):
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=("payload:wp510",),
        provenance_refs=("prov:reentry-input",),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    binding = bind_reentry_to_uptake(
        binding_id=binding_id,
        witness=witness,
        uptake_receipt=receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:wp508-binding",),
    )
    evidence = ReentryBindingEvidence(
        binding=binding,
        witness=witness,
        uptake_receipt=receipt,
        cell_input=cell_input,
    )
    return evidence


def make_path(*, delivery="DELIVERED", uptake="UPTAKEN", same_output=False):
    plan, selection, broadcast = make_base()
    receipt = make_receipt(broadcast, delivery=delivery, uptake=uptake)
    summary = summarize_uptake(
        summary_id="summary:wp510",
        broadcast=broadcast,
        receipts=(receipt,),
        provenance_refs=("prov:summary",),
    )
    intervention, control = make_probe_pair(broadcast, same_output=same_output)
    causal_result = evaluate_causal_influence(
        result_id="causal-result:wp510",
        broadcast=broadcast,
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        provenance_refs=("prov:causal-result",),
    )
    reentries = (
        (make_reentry(plan, selection, broadcast, receipt),)
        if uptake == "UPTAKEN"
        else ()
    )
    return plan, selection, broadcast, receipt, summary, intervention, control, causal_result, reentries


def seal_path(path):
    plan, selection, broadcast, receipt, summary, intervention, control, causal_result, reentries = path
    return seal_gwt_causal_path(
        seal_id="seal:wp510",
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        uptake_receipts=(receipt,),
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        causal_result=causal_result,
        reentry_evidence=reentries,
        provenance_refs=("prov:wp510-seal",),
    )


def test_positive_path_rederives_wp506_wp507_wp508_and_preserves_bounded_causal_status():
    path = make_path()
    observed = seal_path(path)
    assert observed.uptake_status == "UPTAKE_OBSERVED"
    assert observed.causal_status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    assert observed.uptaken_cell_ids == ("G1",)
    assert len(observed.reentry_binding_sha256s) == 1
    payload = observed.as_dict()
    assert payload["runtime_execution_observed"] is False
    assert payload["runtime_credit"] == 0
    assert payload["physical_grid10_credit"] == 0
    assert payload["gwt_runtime_credit"] == 0
    assert payload["jspace_runtime_credit"] == 0
    assert payload["training_credit"] == 0
    assert payload["truth_authority"] == "NONE"
    assert payload["effect_authority"] == "NONE"
    assert payload["whole_system_acceptance"] is False


def test_unknown_uptake_and_unknown_causal_state_are_preserved_without_reentry_invention():
    path = make_path(delivery="OFFERED", uptake="UNKNOWN")
    observed = seal_path(path)
    assert observed.uptake_status == "UNKNOWN_INCOMPLETE_RECEIPTS"
    assert observed.causal_status == "UNKNOWN_INSUFFICIENT_UPTAKE"
    assert observed.uptaken_cell_ids == ()
    assert observed.reentry_binding_sha256s == ()


def test_no_causal_influence_state_is_preserved_after_valid_uptake_and_reentry():
    path = make_path(same_output=True)
    observed = seal_path(path)
    assert observed.uptake_status == "UPTAKE_OBSERVED"
    assert observed.causal_status == "NO_CAUSAL_INFLUENCE_OBSERVED"
    assert observed.uptaken_cell_ids == ("G1",)


def test_missing_reentry_binding_for_uptaken_recipient_fails_closed():
    path = make_path()
    plan, selection, broadcast, receipt, summary, intervention, control, causal_result, _ = path
    with pytest.raises(GwtCausalPathError, match="missing UPTAKEN re-entry binding.*G1"):
        seal_gwt_causal_path(
            seal_id="seal:missing-reentry",
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            uptake_receipts=(receipt,),
            uptake_summary=summary,
            intervention=intervention,
            control=control,
            causal_result=causal_result,
            reentry_evidence=(),
            provenance_refs=("prov:seal",),
        )


def test_two_bindings_for_same_recipient_fail_closed_even_if_both_are_individually_valid():
    path = make_path()
    plan, selection, broadcast, receipt, summary, intervention, control, causal_result, reentries = path
    duplicate = make_reentry(
        plan,
        selection,
        broadcast,
        receipt,
        binding_id="binding:wp510:duplicate",
    )
    with pytest.raises(GwtCausalPathError, match="multiple re-entry bindings for one recipient"):
        seal_gwt_causal_path(
            seal_id="seal:duplicate-reentry",
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            uptake_receipts=(receipt,),
            uptake_summary=summary,
            intervention=intervention,
            control=control,
            causal_result=causal_result,
            reentry_evidence=(reentries[0], duplicate),
            provenance_refs=("prov:seal",),
        )


def test_forged_broadcast_payload_cannot_cross_wp510_even_with_self_consistent_downstream_objects():
    path = make_path()
    plan, selection, broadcast, receipt, summary, intervention, control, causal_result, reentries = path
    forged = replace(broadcast, candidate_payload_refs=("payload:forged",))
    with pytest.raises(GwtCausalPathError, match="deterministic WP506 builder output"):
        seal_gwt_causal_path(
            seal_id="seal:forged-broadcast",
            plan=plan,
            selection=selection,
            broadcast=forged,
            uptake_receipts=(receipt,),
            uptake_summary=summary,
            intervention=intervention,
            control=control,
            causal_result=causal_result,
            reentry_evidence=reentries,
            provenance_refs=("prov:seal",),
        )


def test_forged_uptake_summary_is_rejected_by_deterministic_rederivation():
    path = make_path()
    plan, selection, broadcast, receipt, summary, intervention, control, causal_result, reentries = path
    forged = replace(summary, status="NO_UPTAKE_OBSERVED")
    with pytest.raises(GwtCausalPathError, match="deterministic WP507 summarizer output"):
        seal_gwt_causal_path(
            seal_id="seal:forged-summary",
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            uptake_receipts=(receipt,),
            uptake_summary=forged,
            intervention=intervention,
            control=control,
            causal_result=causal_result,
            reentry_evidence=reentries,
            provenance_refs=("prov:seal",),
        )


def test_forged_causal_result_is_rejected_by_matched_probe_re_evaluation():
    path = make_path()
    plan, selection, broadcast, receipt, summary, intervention, control, causal_result, reentries = path
    forged = replace(causal_result, status="NO_CAUSAL_INFLUENCE_OBSERVED")
    with pytest.raises(GwtCausalPathError, match="deterministic WP507 evaluation"):
        seal_gwt_causal_path(
            seal_id="seal:forged-causal-result",
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            uptake_receipts=(receipt,),
            uptake_summary=summary,
            intervention=intervention,
            control=control,
            causal_result=forged,
            reentry_evidence=reentries,
            provenance_refs=("prov:seal",),
        )


def test_reentry_binding_receipt_must_be_exact_source_receipt_of_summary():
    path = make_path()
    plan, selection, broadcast, receipt, summary, intervention, control, causal_result, _ = path
    alternate_receipt = make_receipt(broadcast, receipt_id="receipt:alternate")
    alternate_reentry = make_reentry(plan, selection, broadcast, alternate_receipt)
    with pytest.raises(GwtCausalPathError, match="not an exact source receipt"):
        seal_gwt_causal_path(
            seal_id="seal:foreign-receipt",
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            uptake_receipts=(receipt,),
            uptake_summary=summary,
            intervention=intervention,
            control=control,
            causal_result=causal_result,
            reentry_evidence=(alternate_reentry,),
            provenance_refs=("prov:seal",),
        )


def test_stale_reentry_binding_is_revalidated_against_witness_receipt_and_cell_input():
    path = make_path()
    plan, selection, broadcast, receipt, summary, intervention, control, causal_result, reentries = path
    stale_binding = replace(reentries[0].binding, broadcast_sha256="f" * 64)
    stale_evidence = ReentryBindingEvidence(
        binding=stale_binding,
        witness=reentries[0].witness,
        uptake_receipt=receipt,
        cell_input=reentries[0].cell_input,
    )
    with pytest.raises(GwtCausalPathError, match="invalid WP508 re-entry/uptake binding"):
        seal_gwt_causal_path(
            seal_id="seal:stale-binding",
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            uptake_receipts=(receipt,),
            uptake_summary=summary,
            intervention=intervention,
            control=control,
            causal_result=causal_result,
            reentry_evidence=(stale_evidence,),
            provenance_refs=("prov:seal",),
        )


def test_direct_seal_constructor_bypass_is_rejected_on_validation():
    path = make_path()
    observed = seal_path(path)
    forged = replace(observed, _factory_seal=None)
    plan, selection, broadcast, receipt, summary, intervention, control, causal_result, reentries = path
    with pytest.raises(GwtCausalPathError, match="deterministic WP510 factory"):
        validate_gwt_causal_path_seal(
            forged,
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            uptake_receipts=(receipt,),
            uptake_summary=summary,
            intervention=intervention,
            control=control,
            causal_result=causal_result,
            reentry_evidence=reentries,
        )


def test_seal_is_deterministic_for_identical_exact_path_objects():
    path = make_path()
    first = seal_path(path)
    second = seal_path(path)
    assert first.as_dict() == second.as_dict()
    assert first.sha256() == second.sha256()
