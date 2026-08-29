from dataclasses import replace

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import (
    GwtReentryUptakeBindingError,
    bind_reentry_to_uptake,
    validate_reentry_uptake_binding,
)
from frankenstein2.gwt_uptake import CellUptakeReceipt
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


def make_plan():
    return Grid10Plan.create(
        plan_id="grid-plan-wp508-g2",
        cycle_id="cycle-wp508-g2",
        generation=4,
        frame_id="frame-wp508-g2",
        frame_generation=5,
        frame_sha256=A,
        policy_id="grid-policy-wp508-g2",
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
        provenance_refs=("prov:grid-plan-wp508-g2",),
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
        candidate_id="candidate:wp508-g2",
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
        policy_id="gwt-policy-wp508-g2",
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
        selection_id="selection:wp508-g2",
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


def make_fixture(*, recipients=("G1", "G2"), cell_id="G1"):
    plan = make_plan()
    selection = make_selection(plan)
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp508-g2",
        generation=3,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=recipients,
    )
    cell_input = CellInput.for_plan(
        plan,
        cell_id=cell_id,
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
    return plan, selection, broadcast, cell_input, witness


def make_receipt(broadcast, *, cell_id="G1", delivery="DELIVERED", uptake="UPTAKEN"):
    return CellUptakeReceipt.observe(
        receipt_id=f"receipt:{cell_id}:{delivery}:{uptake}",
        broadcast=broadcast,
        cell_id=cell_id,
        delivery_status=delivery,
        uptake_status=uptake,
        downstream_ref="downstream:observed" if uptake == "UPTAKEN" else None,
        downstream_sha256=C if uptake == "UPTAKEN" else None,
        provenance_refs=("prov:wp507-receipt",),
    )


def bind(witness, receipt, plan, selection, broadcast, cell_input):
    return bind_reentry_to_uptake(
        binding_id="binding:wp508-g2",
        witness=witness,
        uptake_receipt=receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:wp508-g2-binding",),
    )


def test_positive_uptake_is_preserved_from_wp507_not_inferred_by_wp508():
    plan, selection, broadcast, cell_input, witness = make_fixture()
    receipt = make_receipt(broadcast)
    observed = bind(witness, receipt, plan, selection, broadcast, cell_input)
    payload = observed.as_dict()
    assert observed.binding_status == "WP507_UPTAKEN_BOUND"
    assert observed.uptake_status == "UPTAKEN"
    assert payload["uptake_authority"] == "WP507_CELL_UPTAKE_RECEIPT_ONLY"
    assert payload["reentry_authority"] == "WP508_G1_CANONICAL_REENTRY_WITNESS_ONLY"
    assert payload["causal_influence_claim"] == "NOT_ESTABLISHED_BY_BINDING"
    assert payload["runtime_credit"] == 0
    assert payload["gwt_runtime_credit"] == 0
    assert payload["jspace_runtime_credit"] == 0
    assert payload["whole_system_acceptance"] is False


def test_offered_unknown_remains_nonpositive_and_has_no_downstream_evidence():
    plan, selection, broadcast, cell_input, witness = make_fixture()
    receipt = make_receipt(broadcast, delivery="OFFERED", uptake="UNKNOWN")
    observed = bind(witness, receipt, plan, selection, broadcast, cell_input)
    assert observed.binding_status == "WP507_UNKNOWN_BOUND"
    assert observed.delivery_status == "OFFERED"
    assert observed.uptake_status == "UNKNOWN"
    assert observed.downstream_ref is None
    assert observed.downstream_sha256 is None


def test_wp507_not_uptaken_is_preserved_without_becoming_positive():
    plan, selection, broadcast, cell_input, witness = make_fixture()
    receipt = make_receipt(broadcast, delivery="DELIVERED", uptake="NOT_UPTAKEN")
    observed = bind(witness, receipt, plan, selection, broadcast, cell_input)
    assert observed.binding_status == "WP507_NOT_UPTAKEN_BOUND"
    assert observed.uptake_status == "NOT_UPTAKEN"
    assert observed.downstream_ref is None


def test_cross_recipient_valid_receipt_is_rejected_for_other_reentry():
    plan, selection, broadcast, cell_input, witness = make_fixture()
    receipt = make_receipt(broadcast, cell_id="G2", delivery="DELIVERED", uptake="NOT_UPTAKEN")
    with pytest.raises(GwtReentryUptakeBindingError, match="recipient does not match re-entry recipient"):
        bind(witness, receipt, plan, selection, broadcast, cell_input)


def test_stale_wp507_broadcast_digest_fails_closed():
    plan, selection, broadcast, cell_input, witness = make_fixture()
    receipt = replace(make_receipt(broadcast), broadcast_sha256="f" * 64)
    with pytest.raises(GwtReentryUptakeBindingError, match="invalid WP507 uptake receipt lineage"):
        bind(witness, receipt, plan, selection, broadcast, cell_input)


def test_direct_constructor_wp507_receipt_cannot_be_used_as_uptake_authority():
    plan, selection, broadcast, cell_input, witness = make_fixture()
    receipt = replace(make_receipt(broadcast), _factory_seal=None)
    with pytest.raises(GwtReentryUptakeBindingError, match="observation factory"):
        bind(witness, receipt, plan, selection, broadcast, cell_input)


def test_stale_wp508_witness_lineage_fails_before_binding():
    plan, selection, broadcast, cell_input, witness = make_fixture()
    forged = replace(witness, broadcast_sha256="f" * 64)
    receipt = make_receipt(broadcast)
    with pytest.raises(Exception, match="broadcast digest mismatch"):
        bind(forged, receipt, plan, selection, broadcast, cell_input)


def test_direct_binding_constructor_bypass_is_rejected_on_validation():
    plan, selection, broadcast, cell_input, witness = make_fixture()
    receipt = make_receipt(broadcast)
    observed = bind(witness, receipt, plan, selection, broadcast, cell_input)
    forged = replace(observed, _factory_seal=None)
    with pytest.raises(GwtReentryUptakeBindingError, match="deterministic binding factory"):
        validate_reentry_uptake_binding(
            forged,
            witness=witness,
            uptake_receipt=receipt,
            plan=plan,
            selection=selection,
            broadcast=broadcast,
            cell_input=cell_input,
        )
