from dataclasses import replace
import hashlib
import json

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_causal_runtime_admission import (
    CAUSAL_GWT_RUNTIME_CANDIDATE_OBSERVED,
    GwtCausalRuntimeAdmissionError,
    admit_causal_runtime_candidate,
    validate_gwt_causal_runtime_admission,
)
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_runtime_witness import GwtRuntimeWitnessRecorder, RuntimeObservationIdentity
from frankenstein2.gwt_uptake import (
    CellUptakeReceipt,
    CausalProbeArm,
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


def make_fixture():
    plan = Grid10Plan.create(
        plan_id="plan:causal-runtime", cycle_id="cycle:causal-runtime", generation=1,
        frame_id="frame:causal-runtime", frame_generation=1, frame_sha256=A,
        policy_id="grid-policy:causal-runtime", policy_generation=1, policy_sha256=B,
        cells=tuple(
            CellBudget(
                cell_id=f"G{i}", role_label=f"role-{i}", max_input_refs=8,
                max_output_refs=8, max_work_units=8, max_reentry_depth=2,
            )
            for i in range(1, 11)
        ),
        max_total_work_units=80,
        provenance_refs=("prov:grid-plan",),
    )
    producer_input = CellInput.for_plan(
        plan, cell_id="G1", work_units_requested=2,
        input_refs=("input:producer",), provenance_refs=("prov:producer-input",),
    )
    producer_output = CellOutput.for_input(
        plan, producer_input, status="COMPLETE", work_units_used=1,
        output_refs=("payload:candidate",), evidence_refs=("evidence:producer",),
        provenance_refs=("prov:producer-output",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:causal-runtime", payload_ref="payload:candidate",
        epistemic_class="INFERRED", provenance_refs=("prov:candidate",),
        salience_micros=500_000, goal_relevance_micros=500_000,
        uncertainty_micros=100_000, information_gain_micros=500_000,
        estimated_cost_units=1,
        producer_admission=CandidateProducerAdmission(
            plan=plan, cell_input=producer_input, cell_output=producer_output,
        ),
    )
    policy = SelectionPolicy(
        policy_id="gwt-policy:causal-runtime", generation=1,
        max_selected_candidates=1, max_total_cost_units=4,
        salience_weight=1, goal_relevance_weight=1, uncertainty_weight=1,
        information_gain_weight=1, cost_weight=1,
    )
    selection = build_workspace_selection(
        selection_id="selection:causal-runtime", cycle_id=plan.cycle_id, generation=1,
        frame_id=plan.frame_id, frame_generation=plan.frame_generation,
        frame_sha256=plan.frame_sha256, grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation, grid_plan_sha256=plan.sha256(),
        policy=policy, candidates=(candidate,),
    )
    broadcast = create_broadcast(
        broadcast_id="broadcast:causal-runtime", generation=1,
        selection=selection, expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )
    reentry_input = CellInput.for_plan(
        plan, cell_id="G1", work_units_requested=2, reentry_depth=1,
        input_refs=("payload:candidate",), provenance_refs=("prov:reentry-input",),
    )
    reentry_witness = build_reentry_witness(
        plan=plan, selection=selection, broadcast=broadcast, cell_input=reentry_input,
    )
    uptake = CellUptakeReceipt.observe(
        receipt_id="receipt:runtime:G1", broadcast=broadcast, cell_id="G1",
        delivery_status="DELIVERED", uptake_status="UPTAKEN",
        downstream_ref="downstream:runtime", downstream_sha256=C,
        provenance_refs=("prov:runtime-uptake",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:causal-runtime", witness=reentry_witness,
        uptake_receipt=uptake, plan=plan, selection=selection,
        broadcast=broadcast, cell_input=reentry_input,
        provenance_refs=("prov:binding",),
    )
    times = iter((10, 20, 30))
    recorder = GwtRuntimeWitnessRecorder(
        identity=RuntimeObservationIdentity(
            runtime_instance_id="runtime:causal-runtime",
            process_identity="pid:1:start:1", boot_id_sha256=D,
            exact_source_sha256=E,
        ),
        monotonic_ns=lambda: next(times),
    )
    recorder.observe_delivery(broadcast)
    recorder.observe_uptake(uptake)
    recorder.observe_reentry(
        witness=reentry_witness, binding=binding, plan=plan,
        selection=selection, cell_input=reentry_input,
    )
    runtime_witness = recorder.seal()

    uptake_summary = summarize_uptake(
        summary_id="summary:causal-runtime", broadcast=broadcast,
        receipts=(uptake,), provenance_refs=("prov:summary",),
    )
    intervention = CausalProbeArm.intervention(
        arm_id="arm:intervention", probe_id="probe:causal-runtime",
        broadcast=broadcast, nonbroadcast_input_sha256=A,
        downstream_output_sha256=C, provenance_refs=("prov:intervention",),
    )
    control = CausalProbeArm.control(
        arm_id="arm:control", probe_id="probe:causal-runtime",
        nonbroadcast_input_sha256=A, downstream_output_sha256=B,
        provenance_refs=("prov:control",),
    )
    causal_result = evaluate_causal_influence(
        result_id="result:causal-runtime", broadcast=broadcast,
        uptake_summary=uptake_summary, intervention=intervention, control=control,
        provenance_refs=("prov:causal-result",),
    )
    return runtime_witness, broadcast, uptake_summary, intervention, control, causal_result


def admit(fixture):
    runtime_witness, broadcast, uptake_summary, intervention, control, causal_result = fixture
    return admit_causal_runtime_candidate(
        admission_id="admission:causal-runtime",
        runtime_witness=runtime_witness,
        broadcast=broadcast,
        uptake_summary=uptake_summary,
        causal_result=causal_result,
        intervention=intervention,
        control=control,
        provenance_refs=("prov:admission",),
    )


def test_positive_bridge_binds_existing_causal_result_to_runtime_and_mints_zero_credit():
    observed = admit(make_fixture())
    validate_gwt_causal_runtime_admission(observed)
    payload = observed.as_dict()
    assert observed.classification == CAUSAL_GWT_RUNTIME_CANDIDATE_OBSERVED
    assert payload["runtime_credit"] == 0
    assert payload["gwt_runtime_credit"] == 0
    assert payload["jspace_runtime_credit"] == 0
    assert payload["effect_credit"] == 0
    assert payload["completion_credit"] == 0
    assert payload["training_credit"] == 0
    assert payload["whole_system_acceptance"] is False


def test_directly_modified_causal_result_is_rebuilt_and_rejected():
    fixture = list(make_fixture())
    fixture[5] = replace(fixture[5], status="NO_CAUSAL_INFLUENCE_OBSERVED")
    with pytest.raises(GwtCausalRuntimeAdmissionError, match="deterministic source rebuild"):
        admit(tuple(fixture))


def test_no_causal_difference_is_not_admitted():
    runtime_witness, broadcast, uptake_summary, intervention, control, _ = make_fixture()
    no_effect_control = CausalProbeArm.control(
        arm_id="arm:control-same", probe_id=intervention.probe_id,
        nonbroadcast_input_sha256=intervention.nonbroadcast_input_sha256,
        downstream_output_sha256=intervention.downstream_output_sha256,
        provenance_refs=("prov:control-same",),
    )
    no_effect = evaluate_causal_influence(
        result_id="result:no-effect", broadcast=broadcast,
        uptake_summary=uptake_summary, intervention=intervention,
        control=no_effect_control, provenance_refs=("prov:no-effect",),
    )
    with pytest.raises(GwtCausalRuntimeAdmissionError, match="causal influence was not observed"):
        admit_causal_runtime_candidate(
            admission_id="admission:no-effect", runtime_witness=runtime_witness,
            broadcast=broadcast, uptake_summary=uptake_summary,
            causal_result=no_effect, intervention=intervention, control=no_effect_control,
            provenance_refs=("prov:admission",),
        )


def test_runtime_uptake_must_be_part_of_causal_summary():
    runtime_witness, broadcast, _, intervention, control, _ = make_fixture()
    other = CellUptakeReceipt.observe(
        receipt_id="receipt:other:G1", broadcast=broadcast, cell_id="G1",
        delivery_status="DELIVERED", uptake_status="UPTAKEN",
        downstream_ref="downstream:other", downstream_sha256=C,
        provenance_refs=("prov:other",),
    )
    other_summary = summarize_uptake(
        summary_id="summary:other", broadcast=broadcast, receipts=(other,),
        provenance_refs=("prov:other-summary",),
    )
    other_result = evaluate_causal_influence(
        result_id="result:other", broadcast=broadcast, uptake_summary=other_summary,
        intervention=intervention, control=control, provenance_refs=("prov:other-result",),
    )
    with pytest.raises(GwtCausalRuntimeAdmissionError, match="runtime uptake receipt"):
        admit_causal_runtime_candidate(
            admission_id="admission:other", runtime_witness=runtime_witness,
            broadcast=broadcast, uptake_summary=other_summary,
            causal_result=other_result, intervention=intervention, control=control,
            provenance_refs=("prov:admission",),
        )


def test_tampered_admission_is_rejected_after_seal():
    observed = admit(make_fixture())
    forged = replace(observed, exact_source_sha256=A)
    with pytest.raises(GwtCausalRuntimeAdmissionError, match="payload changed after seal"):
        validate_gwt_causal_runtime_admission(forged)
