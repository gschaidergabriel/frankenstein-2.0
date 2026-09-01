from dataclasses import replace

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_causal_runtime_readback import (
    CAUSAL_RUNTIME_READBACK_OBSERVED,
    ControlNoBroadcastReadback,
    GwtCausalRuntimeReadbackError,
    bind_causal_runtime_readback,
    validate_causal_runtime_readback,
)
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_runtime_witness import GwtRuntimeWitnessRecorder, RuntimeObservationIdentity
from frankenstein2.gwt_uptake import CellUptakeReceipt, summarize_uptake
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


def make_fixture():
    plan = Grid10Plan.create(
        plan_id="grid-plan-wp900-g4",
        cycle_id="cycle-wp900-g4",
        generation=4,
        frame_id="frame-wp900-g4",
        frame_generation=5,
        frame_sha256=A,
        policy_id="grid-policy-wp900-g4",
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
        provenance_refs=("prov:grid-plan-wp900-g4",),
    )
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
        candidate_id="candidate:wp900-g4",
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
        policy_id="gwt-policy-wp900-g4",
        generation=1,
        max_selected_candidates=1,
        max_total_cost_units=4,
        salience_weight=1,
        goal_relevance_weight=1,
        uncertainty_weight=1,
        information_gain_weight=1,
        cost_weight=1,
    )
    selection = build_workspace_selection(
        selection_id="selection:wp900-g4",
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
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp900-g4",
        generation=4,
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
    uptake_receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:wp900-g4:G1",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="readback:intervention",
        downstream_sha256=C,
        provenance_refs=("prov:wp507-runtime-receipt",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:wp900-g4",
        witness=witness,
        uptake_receipt=uptake_receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:wp508-runtime-binding",),
    )
    ticks = iter((10, 20, 30))
    recorder = GwtRuntimeWitnessRecorder(
        identity=RuntimeObservationIdentity(
            runtime_instance_id="runtime:wp900-g4:intervention",
            process_identity="pid:4242:start:100",
            boot_id_sha256=D,
            exact_source_sha256=E,
        ),
        monotonic_ns=lambda: next(ticks),
    )
    recorder.observe_delivery(broadcast)
    recorder.observe_uptake(uptake_receipt)
    recorder.observe_reentry(
        witness=witness,
        binding=binding,
        plan=plan,
        selection=selection,
        cell_input=cell_input,
    )
    runtime_witness = recorder.seal()
    uptake_summary = summarize_uptake(
        summary_id="summary:wp900-g4",
        broadcast=broadcast,
        receipts=(uptake_receipt,),
        provenance_refs=("prov:wp900-g4-summary",),
    )
    return broadcast, runtime_witness, uptake_receipt, uptake_summary


def control(**overrides):
    values = {
        "runtime_instance_id": "runtime:wp900-g4:control",
        "process_identity": "pid:4243:start:200",
        "boot_id_sha256": D,
        "exact_source_sha256": E,
        "probe_id": "probe:wp900-g4",
        "nonbroadcast_input_sha256": A,
        "downstream_ref": "readback:control",
        "downstream_sha256": F,
        "observed_monotonic_ns": 40,
        "reentry_observed": False,
        "provenance_refs": ("prov:control-runtime-readback",),
    }
    values.update(overrides)
    return ControlNoBroadcastReadback(**values)


def bind(*, control_readback=None, summary=None, witness=None, receipt=None):
    broadcast, runtime_witness, uptake_receipt, uptake_summary = make_fixture()
    return bind_causal_runtime_readback(
        probe_id="probe:wp900-g4",
        nonbroadcast_input_sha256=A,
        broadcast=broadcast,
        runtime_witness=runtime_witness if witness is None else witness,
        uptake_receipt=uptake_receipt if receipt is None else receipt,
        uptake_summary=uptake_summary if summary is None else summary,
        control_readback=control() if control_readback is None else control_readback,
        provenance_refs=("prov:wp900-g4-binder",),
    )


def test_positive_matched_runtime_readback_binds_existing_evidence_but_mints_zero_credit():
    observed = bind()
    validate_causal_runtime_readback(observed)

    assert observed.classification == CAUSAL_RUNTIME_READBACK_OBSERVED
    assert observed.causal_result_status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    assert observed.intervention_downstream_sha256 == C
    assert observed.control_downstream_sha256 == F
    assert observed.exact_source_sha256 == E
    assert observed.boot_id_sha256 == D
    assert observed.runtime_credit == 0
    assert observed.target_environment_component_runtime_credit == 0
    assert observed.gwt_contract_causal_runtime_candidate_credit == 0
    assert observed.gwt_runtime_credit == 0
    assert observed.jspace_runtime_credit == 0
    assert observed.physical_grid10_credit == 0
    assert observed.effect_credit == 0
    assert observed.training_credit == 0
    assert observed.completion_credit == 0
    assert observed.whole_system_acceptance is False


def test_same_downstream_readback_fails_causal_discriminator():
    with pytest.raises(GwtCausalRuntimeReadbackError, match="NO_CAUSAL_INFLUENCE_OBSERVED"):
        bind(control_readback=control(downstream_sha256=C))


def test_control_must_share_exact_source_with_positive_runtime():
    with pytest.raises(GwtCausalRuntimeReadbackError, match="exact-source identity mismatch"):
        bind(control_readback=control(exact_source_sha256=F))


def test_control_must_share_boot_with_positive_runtime():
    with pytest.raises(GwtCausalRuntimeReadbackError, match="boot identity mismatch"):
        bind(control_readback=control(boot_id_sha256=F))


def test_control_reentry_is_fail_closed_at_construction():
    with pytest.raises(GwtCausalRuntimeReadbackError, match="must not claim GWT re-entry"):
        control(reentry_observed=True)


def test_control_input_must_be_matched():
    with pytest.raises(GwtCausalRuntimeReadbackError, match="input is not matched"):
        bind(control_readback=control(nonbroadcast_input_sha256=B))


def test_tampered_positive_runtime_witness_is_rejected():
    broadcast, runtime_witness, uptake_receipt, uptake_summary = make_fixture()
    tampered = replace(runtime_witness, broadcast_sha256=F)
    with pytest.raises(GwtCausalRuntimeReadbackError, match="invalid runtime witness"):
        bind_causal_runtime_readback(
            probe_id="probe:wp900-g4",
            nonbroadcast_input_sha256=A,
            broadcast=broadcast,
            runtime_witness=tampered,
            uptake_receipt=uptake_receipt,
            uptake_summary=uptake_summary,
            control_readback=control(),
            provenance_refs=("prov:wp900-g4-binder",),
        )


def test_summary_must_contain_exact_runtime_witness_receipt():
    broadcast, runtime_witness, uptake_receipt, _ = make_fixture()
    other = CellUptakeReceipt.observe(
        receipt_id="receipt:other",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="readback:other",
        downstream_sha256=B,
        provenance_refs=("prov:other",),
    )
    other_summary = summarize_uptake(
        summary_id="summary:other",
        broadcast=broadcast,
        receipts=(other,),
        provenance_refs=("prov:other-summary",),
    )
    with pytest.raises(GwtCausalRuntimeReadbackError, match="does not contain runtime-witness receipt"):
        bind_causal_runtime_readback(
            probe_id="probe:wp900-g4",
            nonbroadcast_input_sha256=A,
            broadcast=broadcast,
            runtime_witness=runtime_witness,
            uptake_receipt=uptake_receipt,
            uptake_summary=other_summary,
            control_readback=control(),
            provenance_refs=("prov:wp900-g4-binder",),
        )


def test_bound_candidate_tamper_is_rejected():
    observed = bind()
    forged = replace(observed, control_downstream_sha256=B)
    with pytest.raises(GwtCausalRuntimeReadbackError, match="payload changed after bind"):
        validate_causal_runtime_readback(forged)
