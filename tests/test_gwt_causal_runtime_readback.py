import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_causal_runtime_readback import (
    GwtCausalRuntimeReadbackError,
    GwtCausalRuntimeReadbackRecorder,
    validate_gwt_causal_runtime_readback_receipt,
)
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessRecorder,
    RuntimeObservationIdentity,
)
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


def clock(*values):
    sequence = iter(values)
    return lambda: next(sequence)


def make_plan():
    return Grid10Plan.create(
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
    return build_workspace_selection(
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


def make_fixture():
    plan = make_plan()
    selection = make_selection(plan)
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp900-g4",
        generation=3,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1", "G2"),
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
    live_receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:wp900-g4:G1",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:live-intervention",
        downstream_sha256=C,
        provenance_refs=("prov:wp507-live-receipt",),
    )
    g2_receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:wp900-g4:G2",
        broadcast=broadcast,
        cell_id="G2",
        delivery_status="DELIVERED",
        uptake_status="NOT_UPTAKEN",
        provenance_refs=("prov:wp507-g2-receipt",),
    )
    summary = summarize_uptake(
        summary_id="summary:wp900-g4",
        broadcast=broadcast,
        receipts=(live_receipt, g2_receipt),
        provenance_refs=("prov:wp507-summary",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:wp900-g4",
        witness=witness,
        uptake_receipt=live_receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:wp508-binding",),
    )
    runtime = GwtRuntimeWitnessRecorder(
        identity=RuntimeObservationIdentity(
            runtime_instance_id="runtime:wp900-g4:test",
            process_identity="pid:4242:start:100",
            boot_id_sha256=D,
            exact_source_sha256=A,
        ),
        monotonic_ns=clock(10, 20, 30),
    )
    runtime.observe_delivery(broadcast)
    runtime.observe_uptake(live_receipt)
    runtime.observe_reentry(
        witness=witness,
        binding=binding,
        plan=plan,
        selection=selection,
        cell_input=cell_input,
    )
    runtime_witness = runtime.seal()
    return runtime_witness, broadcast, summary, live_receipt, g2_receipt


def make_recorder(*, times=(40, 50), summary=None):
    runtime_witness, broadcast, default_summary, live_receipt, g2_receipt = make_fixture()
    recorder = GwtCausalRuntimeReadbackRecorder(
        runtime_witness=runtime_witness,
        broadcast=broadcast,
        uptake_summary=default_summary if summary is None else summary,
        monotonic_ns=clock(*times),
    )
    return recorder, runtime_witness, broadcast, default_summary, live_receipt, g2_receipt


def record_pair(*, control_output=D, times=(40, 50)):
    recorder, runtime_witness, broadcast, summary, live_receipt, g2_receipt = make_recorder(times=times)
    intervention = recorder.observe_intervention_readback(
        arm_id="arm:wp900-g4:intervention",
        probe_id="probe:wp900-g4",
        nonbroadcast_input_sha256=B,
        observed_downstream_output_sha256=C,
        provenance_refs=("prov:runtime-intervention",),
    )
    control = recorder.observe_control_readback(
        arm_id="arm:wp900-g4:control",
        probe_id="probe:wp900-g4",
        nonbroadcast_input_sha256=B,
        observed_downstream_output_sha256=control_output,
        provenance_refs=("prov:runtime-control",),
    )
    return recorder, intervention, control, runtime_witness, broadcast, summary, live_receipt, g2_receipt


def test_positive_candidate_binds_live_intervention_and_matched_control_but_mints_zero_credit():
    recorder, intervention, control, runtime_witness, broadcast, summary, live_receipt, _ = record_pair()
    receipt = recorder.seal(
        result_id="result:wp900-g4",
        provenance_refs=("prov:runtime-causal-evaluation",),
    )
    validate_gwt_causal_runtime_readback_receipt(receipt)

    assert receipt.causal_status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    assert receipt.runtime_witness_sha256 == runtime_witness.sha256()
    assert receipt.broadcast_id == broadcast.broadcast_id
    assert receipt.broadcast_sha256 == broadcast.sha256()
    assert receipt.uptake_summary_id == summary.summary_id
    assert receipt.uptake_summary_sha256 == summary.sha256()
    assert receipt.uptake_receipt_id == live_receipt.receipt_id
    assert receipt.uptake_receipt_sha256 == live_receipt.sha256()
    assert receipt.intervention_arm_sha256 == intervention.sha256()
    assert receipt.control_arm_sha256 == control.sha256()
    assert receipt.intervention_output_sha256 == C
    assert receipt.control_output_sha256 == D
    assert [item.condition for item in receipt.observations] == [
        "INTERVENTION_BROADCAST",
        "CONTROL_NO_BROADCAST",
    ]
    assert receipt.repository_ci_credit == 0
    assert receipt.target_environment_component_runtime_credit == 0
    assert receipt.gwt_contract_causal_runtime_candidate_credit == 0
    assert receipt.gwt_runtime_credit == 0
    assert receipt.jspace_runtime_credit == 0
    assert receipt.physical_grid10_credit == 0
    assert receipt.effect_credit == 0
    assert receipt.training_credit == 0
    assert receipt.completion_credit == 0
    assert receipt.whole_system_acceptance is False


def test_equal_intervention_and_control_outputs_are_preserved_as_negative_evidence():
    recorder, *_ = record_pair(control_output=C)
    receipt = recorder.seal(
        result_id="result:wp900-g4:no-effect",
        provenance_refs=("prov:runtime-causal-no-effect",),
    )
    assert receipt.causal_status == "NO_CAUSAL_INFLUENCE_OBSERVED"
    assert receipt.gwt_contract_causal_runtime_candidate_credit == 0
    validate_gwt_causal_runtime_readback_receipt(receipt)


def test_intervention_output_must_equal_exact_live_wp900_uptake_readback():
    recorder, *_ = make_recorder()
    with pytest.raises(GwtCausalRuntimeReadbackError, match="exact live WP900 uptake receipt"):
        recorder.observe_intervention_readback(
            arm_id="arm:bad-intervention",
            probe_id="probe:wp900-g4",
            nonbroadcast_input_sha256=B,
            observed_downstream_output_sha256=E,
            provenance_refs=("prov:bad-intervention",),
        )


def test_control_cannot_be_recorded_before_live_intervention():
    recorder, *_ = make_recorder()
    with pytest.raises(GwtCausalRuntimeReadbackError, match="intervention must be recorded before control"):
        recorder.observe_control_readback(
            arm_id="arm:early-control",
            probe_id="probe:wp900-g4",
            nonbroadcast_input_sha256=B,
            observed_downstream_output_sha256=D,
            provenance_refs=("prov:early-control",),
        )


def test_control_probe_identity_must_match_intervention():
    recorder, *_ = make_recorder()
    recorder.observe_intervention_readback(
        arm_id="arm:intervention",
        probe_id="probe:wp900-g4",
        nonbroadcast_input_sha256=B,
        observed_downstream_output_sha256=C,
        provenance_refs=("prov:intervention",),
    )
    with pytest.raises(GwtCausalRuntimeReadbackError, match="probe_id must match"):
        recorder.observe_control_readback(
            arm_id="arm:control",
            probe_id="probe:other",
            nonbroadcast_input_sha256=B,
            observed_downstream_output_sha256=D,
            provenance_refs=("prov:control",),
        )


def test_control_nonbroadcast_input_must_match_intervention():
    recorder, *_ = make_recorder()
    recorder.observe_intervention_readback(
        arm_id="arm:intervention",
        probe_id="probe:wp900-g4",
        nonbroadcast_input_sha256=B,
        observed_downstream_output_sha256=C,
        provenance_refs=("prov:intervention",),
    )
    with pytest.raises(GwtCausalRuntimeReadbackError, match="nonbroadcast input must match"):
        recorder.observe_control_readback(
            arm_id="arm:control",
            probe_id="probe:wp900-g4",
            nonbroadcast_input_sha256=E,
            observed_downstream_output_sha256=D,
            provenance_refs=("prov:control",),
        )


def test_runtime_clock_must_advance_between_intervention_and_control():
    recorder, *_ = make_recorder(times=(50, 50))
    recorder.observe_intervention_readback(
        arm_id="arm:intervention",
        probe_id="probe:wp900-g4",
        nonbroadcast_input_sha256=B,
        observed_downstream_output_sha256=C,
        provenance_refs=("prov:intervention",),
    )
    with pytest.raises(GwtCausalRuntimeReadbackError, match="clock did not advance"):
        recorder.observe_control_readback(
            arm_id="arm:control",
            probe_id="probe:wp900-g4",
            nonbroadcast_input_sha256=B,
            observed_downstream_output_sha256=D,
            provenance_refs=("prov:control",),
        )


def test_summary_must_contain_exact_uptake_receipt_observed_by_live_runtime_witness():
    runtime_witness, broadcast, _, _, g2_receipt = make_fixture()
    alternate_live = CellUptakeReceipt.observe(
        receipt_id="receipt:alternate:G1",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:alternate",
        downstream_sha256=C,
        provenance_refs=("prov:alternate",),
    )
    alternate_summary = summarize_uptake(
        summary_id="summary:alternate",
        broadcast=broadcast,
        receipts=(alternate_live, g2_receipt),
        provenance_refs=("prov:alternate-summary",),
    )
    with pytest.raises(GwtCausalRuntimeReadbackError, match="exact live WP900 uptake receipt"):
        GwtCausalRuntimeReadbackRecorder(
            runtime_witness=runtime_witness,
            broadcast=broadcast,
            uptake_summary=alternate_summary,
            monotonic_ns=clock(40, 50),
        )


def test_sealed_receipt_detects_post_seal_tampering():
    recorder, *_ = record_pair()
    receipt = recorder.seal(
        result_id="result:wp900-g4",
        provenance_refs=("prov:runtime-causal-evaluation",),
    )
    object.__setattr__(receipt, "control_output_sha256", E)
    with pytest.raises(GwtCausalRuntimeReadbackError, match="changed after seal"):
        validate_gwt_causal_runtime_readback_receipt(receipt)
