from dataclasses import replace

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_causal_path import (
    GwtCausalPathError,
    ReentryEvidenceBundle,
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
F = "f" * 64


def make_plan():
    return Grid10Plan.create(
        plan_id="grid-plan-wp510",
        cycle_id="cycle-wp510",
        generation=4,
        frame_id="frame-wp510",
        frame_generation=5,
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
        output_refs=("payload:candidate",),
        evidence_refs=("evidence:producer",),
        provenance_refs=("prov:producer-output",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:wp510",
        payload_ref="payload:candidate",
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
        policy_id="gwt-policy-wp510",
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
        selection_id="selection:wp510",
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


def make_fixture(
    *,
    delivery="DELIVERED",
    uptake="UPTAKEN",
    intervention_output=C,
    control_output=F,
):
    plan = make_plan()
    selection = make_selection(plan)
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp510",
        generation=3,
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
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:G1:wp510",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status=delivery,
        uptake_status=uptake,
        downstream_ref="downstream:wp510" if uptake == "UPTAKEN" else None,
        downstream_sha256=C if uptake == "UPTAKEN" else None,
        provenance_refs=("prov:wp507-receipt",),
    )
    summary = summarize_uptake(
        summary_id="summary:wp510",
        broadcast=broadcast,
        receipts=(receipt,),
        provenance_refs=("prov:wp507-summary",),
    )
    intervention = CausalProbeArm.intervention(
        arm_id="arm:intervention:wp510",
        probe_id="probe:wp510",
        broadcast=broadcast,
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=intervention_output,
        provenance_refs=("prov:intervention",),
    )
    control = CausalProbeArm.control(
        arm_id="arm:control:wp510",
        probe_id="probe:wp510",
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=control_output,
        provenance_refs=("prov:control",),
    )
    causal = evaluate_causal_influence(
        result_id="causal:wp510",
        broadcast=broadcast,
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        provenance_refs=("prov:causal",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:wp510",
        witness=witness,
        uptake_receipt=receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:wp508-binding",),
    )
    bundle = ReentryEvidenceBundle(
        binding=binding,
        witness=witness,
        uptake_receipt=receipt,
        cell_input=cell_input,
    )
    return {
        "plan": plan,
        "selection": selection,
        "broadcast": broadcast,
        "receipts": (receipt,),
        "uptake_summary": summary,
        "intervention": intervention,
        "control": control,
        "causal_result": causal,
        "reentry_bundles": (bundle,),
    }


def seal(fx, **overrides):
    values = dict(fx)
    values.update(overrides)
    return seal_gwt_causal_path(
        seal_id="seal:wp510",
        provenance_refs=("prov:wp510-seal",),
        **values,
    )


def test_positive_exact_chain_seals_without_minting_runtime_or_truth_credit():
    fx = make_fixture()
    observed = seal(fx)
    payload = observed.as_dict()
    assert observed.path_status == "CONTRACT_SCOPE_CAUSAL_PATH_SEALED"
    assert observed.causal_status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    assert observed.uptaken_cell_ids == ("G1",)
    assert observed.reentry_binding_ids == ("binding:wp510",)
    assert payload["truth_authority"] == "NONE"
    assert payload["effect_authority"] == "NONE"
    assert payload["runtime_credit"] == 0
    assert payload["physical_grid10_credit"] == 0
    assert payload["gwt_runtime_credit"] == 0
    assert payload["jspace_runtime_credit"] == 0
    assert payload["training_credit"] == 0
    assert payload["whole_system_acceptance"] is False


def test_forged_broadcast_payload_lineage_fails_closed_before_positive_path():
    fx = make_fixture()
    forged = replace(fx["broadcast"], candidate_payload_refs=("payload:forged",))
    with pytest.raises(GwtCausalPathError, match="canonical WP506 builder lineage"):
        seal(fx, broadcast=forged)


def test_positive_uptake_without_wp508_reentry_binding_is_rejected():
    fx = make_fixture()
    with pytest.raises(GwtCausalPathError, match="every UPTAKEN recipient"):
        seal(fx, reentry_bundles=())


def test_positive_probe_must_share_downstream_digest_with_uptake_reentry_evidence():
    fx = make_fixture(intervention_output=E)
    assert fx["causal_result"].status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    with pytest.raises(GwtCausalPathError, match="downstream digest does not match"):
        seal(fx)


def test_forged_causal_result_is_rejected_by_exact_re_evaluation():
    fx = make_fixture()
    forged = replace(fx["causal_result"], status="NO_CAUSAL_INFLUENCE_OBSERVED")
    with pytest.raises(GwtCausalPathError, match="matched probe"):
        seal(fx, causal_result=forged)


def test_offered_unknown_path_remains_unknown_and_never_mints_positive_causal_status():
    fx = make_fixture(delivery="OFFERED", uptake="UNKNOWN")
    observed = seal(fx, reentry_bundles=())
    assert fx["uptake_summary"].status == "UNKNOWN_INCOMPLETE_RECEIPTS"
    assert fx["causal_result"].status == "UNKNOWN_INSUFFICIENT_UPTAKE"
    assert observed.path_status == "UNKNOWN_CAUSAL_PATH_SEALED"
    assert observed.uptaken_cell_ids == ()


def test_delivered_not_uptaken_path_remains_unknown_insufficient_uptake():
    fx = make_fixture(delivery="DELIVERED", uptake="NOT_UPTAKEN")
    observed = seal(fx, reentry_bundles=())
    assert fx["uptake_summary"].status == "NO_UPTAKE_OBSERVED"
    assert fx["causal_result"].status == "UNKNOWN_INSUFFICIENT_UPTAKE"
    assert observed.path_status == "UNKNOWN_CAUSAL_PATH_SEALED"


def test_same_downstream_output_preserves_explicit_no_causal_influence():
    fx = make_fixture(control_output=C)
    observed = seal(fx)
    assert fx["causal_result"].status == "NO_CAUSAL_INFLUENCE_OBSERVED"
    assert observed.path_status == "NO_CAUSAL_INFLUENCE_PATH_SEALED"


def test_factory_bypass_of_wp508_binding_is_rejected():
    fx = make_fixture()
    bundle = fx["reentry_bundles"][0]
    forged_binding = replace(bundle.binding, _factory_seal=None)
    forged_bundle = replace(bundle, binding=forged_binding)
    with pytest.raises(ValueError, match="deterministic binding factory"):
        seal(fx, reentry_bundles=(forged_bundle,))


def test_factory_bypass_of_wp510_seal_is_rejected_on_validation():
    fx = make_fixture()
    observed = seal(fx)
    forged = replace(observed, _factory_seal=None)
    with pytest.raises(GwtCausalPathError, match="deterministic WP510 factory"):
        validate_gwt_causal_path_seal(forged, **fx)


def test_reentry_bundle_receipt_must_be_member_of_exact_sealed_receipt_set():
    fx = make_fixture()
    bundle = fx["reentry_bundles"][0]
    foreign_receipt = replace(bundle.uptake_receipt, receipt_id="receipt:foreign")
    foreign_bundle = replace(bundle, uptake_receipt=foreign_receipt)
    with pytest.raises(GwtCausalPathError, match="not in sealed WP507 receipt set"):
        seal(fx, reentry_bundles=(foreign_bundle,))
