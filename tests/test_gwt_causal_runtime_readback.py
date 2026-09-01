from dataclasses import replace

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_causal_runtime_readback import (
    CAUSAL_RUNTIME_INTERVENTION_READBACK_CANDIDATE,
    GwtCausalRuntimeReadbackError,
    INTERVENTION_ABSENT_OBSERVED,
    INTERVENTION_ACTIVE_OBSERVED,
    bind_gwt_causal_runtime_readback,
    observe_causal_arm_runtime_readback,
    validate_gwt_causal_runtime_readback,
)
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessRecorder,
    RuntimeObservationIdentity,
)
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
        plan_id="plan:wp900-g4",
        cycle_id="cycle:wp900-g4",
        generation=1,
        frame_id="frame:wp900-g4",
        frame_generation=1,
        frame_sha256=A,
        policy_id="grid-policy:wp900-g4",
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
        policy_id="gwt-policy:wp900-g4",
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
        generation=1,
        frame_id=plan.frame_id,
        frame_generation=plan.frame_generation,
        frame_sha256=plan.frame_sha256,
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        policy=policy,
        candidates=(candidate,),
    )


def runtime_identity(*, runtime_instance_id="runtime:wp900-g4"):
    return RuntimeObservationIdentity(
        runtime_instance_id=runtime_instance_id,
        process_identity="pid:900:start:4",
        boot_id_sha256=D,
        exact_source_sha256=E,
    )


def make_fixture():
    plan = make_plan()
    selection = make_selection(plan)
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp900-g4",
        generation=1,
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
    reentry_witness = build_reentry_witness(
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
        downstream_ref="downstream:intervention",
        downstream_sha256=C,
        provenance_refs=("prov:wp507-runtime-uptake",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:wp900-g4",
        witness=reentry_witness,
        uptake_receipt=uptake_receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:wp508-binding",),
    )
    identity = runtime_identity()
    times = iter((10, 20, 30))
    recorder = GwtRuntimeWitnessRecorder(
        identity=identity,
        monotonic_ns=lambda: next(times),
    )
    recorder.observe_delivery(broadcast)
    recorder.observe_uptake(uptake_receipt)
    recorder.observe_reentry(
        witness=reentry_witness,
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
        provenance_refs=("prov:wp507-summary",),
    )
    intervention = CausalProbeArm.intervention(
        arm_id="arm:intervention:wp900-g4",
        probe_id="probe:wp900-g4",
        broadcast=broadcast,
        nonbroadcast_input_sha256=A,
        downstream_output_sha256=C,
        provenance_refs=("prov:intervention",),
    )
    control = CausalProbeArm.control(
        arm_id="arm:control:wp900-g4",
        probe_id="probe:wp900-g4",
        nonbroadcast_input_sha256=A,
        downstream_output_sha256=B,
        provenance_refs=("prov:control",),
    )
    causal_result = evaluate_causal_influence(
        result_id="causal:wp900-g4",
        broadcast=broadcast,
        uptake_summary=uptake_summary,
        intervention=intervention,
        control=control,
        provenance_refs=("prov:causal-result",),
    )
    intervention_readback = observe_causal_arm_runtime_readback(
        identity=identity,
        arm=intervention,
        observed_downstream_output_sha256=C,
        observed_monotonic_ns=40,
        intervention_activation=INTERVENTION_ACTIVE_OBSERVED,
    )
    control_readback = observe_causal_arm_runtime_readback(
        identity=identity,
        arm=control,
        observed_downstream_output_sha256=B,
        observed_monotonic_ns=50,
        intervention_activation=INTERVENTION_ABSENT_OBSERVED,
    )
    return {
        "plan": plan,
        "selection": selection,
        "broadcast": broadcast,
        "cell_input": cell_input,
        "reentry_witness": reentry_witness,
        "uptake_receipt": uptake_receipt,
        "binding": binding,
        "runtime_witness": runtime_witness,
        "uptake_summary": uptake_summary,
        "intervention": intervention,
        "control": control,
        "causal_result": causal_result,
        "intervention_readback": intervention_readback,
        "control_readback": control_readback,
    }


def bind(fx, **overrides):
    values = dict(fx)
    values.update(overrides)
    return bind_gwt_causal_runtime_readback(
        readback_id="readback:wp900-g4",
        provenance_refs=("prov:wp900-g4-readback",),
        **values,
    )


def test_positive_matched_runtime_readback_binds_all_existing_lineage_and_mints_zero_credit():
    observed = bind(make_fixture())
    validate_gwt_causal_runtime_readback(observed)
    payload = observed.as_dict()
    assert observed.classification == CAUSAL_RUNTIME_INTERVENTION_READBACK_CANDIDATE
    assert observed.causal_status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    assert payload["runtime_credit"] == 0
    assert payload["target_environment_component_runtime_credit"] == 0
    assert payload["gwt_contract_causal_runtime_candidate_credit"] == 0
    assert payload["gwt_runtime_credit"] == 0
    assert payload["jspace_runtime_credit"] == 0
    assert payload["physical_grid10_credit"] == 0
    assert payload["effect_credit"] == 0
    assert payload["training_credit"] == 0
    assert payload["completion_credit"] == 0
    assert payload["whole_system_acceptance"] is False


def test_directly_modified_causal_result_is_rebuilt_and_rejected():
    fx = make_fixture()
    forged = replace(fx["causal_result"], status="NO_CAUSAL_INFLUENCE_OBSERVED")
    with pytest.raises(GwtCausalRuntimeReadbackError, match="deterministic WP507 rebuild"):
        bind(fx, causal_result=forged)


def test_runtime_uptake_must_be_exact_member_of_causal_summary():
    fx = make_fixture()
    other = CellUptakeReceipt.observe(
        receipt_id="receipt:other:G1",
        broadcast=fx["broadcast"],
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:intervention",
        downstream_sha256=C,
        provenance_refs=("prov:other",),
    )
    other_summary = summarize_uptake(
        summary_id="summary:other",
        broadcast=fx["broadcast"],
        receipts=(other,),
        provenance_refs=("prov:other-summary",),
    )
    other_result = evaluate_causal_influence(
        result_id="causal:other",
        broadcast=fx["broadcast"],
        uptake_summary=other_summary,
        intervention=fx["intervention"],
        control=fx["control"],
        provenance_refs=("prov:other-causal",),
    )
    with pytest.raises(GwtCausalRuntimeReadbackError, match="runtime uptake receipt is not uniquely present"):
        bind(fx, uptake_summary=other_summary, causal_result=other_result)


def test_wp508_factory_bypass_is_rejected_by_deep_source_lineage_validation():
    fx = make_fixture()
    forged_binding = replace(fx["binding"], _factory_seal=None)
    with pytest.raises(GwtCausalRuntimeReadbackError, match="WP507/WP508 source lineage"):
        bind(fx, binding=forged_binding)


def test_matched_probe_nonbroadcast_input_mismatch_is_not_positive_causal_evidence():
    fx = make_fixture()
    mismatched_control = CausalProbeArm.control(
        arm_id="arm:control:mismatch",
        probe_id=fx["intervention"].probe_id,
        nonbroadcast_input_sha256=F,
        downstream_output_sha256=B,
        provenance_refs=("prov:mismatched-control",),
    )
    mismatched_result = evaluate_causal_influence(
        result_id="causal:mismatch",
        broadcast=fx["broadcast"],
        uptake_summary=fx["uptake_summary"],
        intervention=fx["intervention"],
        control=mismatched_control,
        provenance_refs=("prov:mismatched-result",),
    )
    mismatched_readback = observe_causal_arm_runtime_readback(
        identity=fx["runtime_witness"].identity,
        arm=mismatched_control,
        observed_downstream_output_sha256=B,
        observed_monotonic_ns=50,
        intervention_activation=INTERVENTION_ABSENT_OBSERVED,
    )
    with pytest.raises(GwtCausalRuntimeReadbackError, match="causal influence was not observed"):
        bind(
            fx,
            control=mismatched_control,
            causal_result=mismatched_result,
            control_readback=mismatched_readback,
        )


def test_intervention_arm_requires_observed_activation():
    fx = make_fixture()
    with pytest.raises(GwtCausalRuntimeReadbackError, match="intervention arm lacks observed activation"):
        observe_causal_arm_runtime_readback(
            identity=fx["runtime_witness"].identity,
            arm=fx["intervention"],
            observed_downstream_output_sha256=C,
            observed_monotonic_ns=40,
            intervention_activation=INTERVENTION_ABSENT_OBSERVED,
        )


def test_control_arm_requires_observed_broadcast_absence():
    fx = make_fixture()
    with pytest.raises(GwtCausalRuntimeReadbackError, match="control arm did not observe broadcast absence"):
        observe_causal_arm_runtime_readback(
            identity=fx["runtime_witness"].identity,
            arm=fx["control"],
            observed_downstream_output_sha256=B,
            observed_monotonic_ns=50,
            intervention_activation=INTERVENTION_ACTIVE_OBSERVED,
        )


def test_arm_readback_must_bind_actually_observed_downstream_digest():
    fx = make_fixture()
    with pytest.raises(GwtCausalRuntimeReadbackError, match="observed downstream digest"):
        observe_causal_arm_runtime_readback(
            identity=fx["runtime_witness"].identity,
            arm=fx["control"],
            observed_downstream_output_sha256=F,
            observed_monotonic_ns=50,
            intervention_activation=INTERVENTION_ABSENT_OBSERVED,
        )


def test_control_readback_cannot_come_from_different_runtime_identity():
    fx = make_fixture()
    foreign_control_readback = observe_causal_arm_runtime_readback(
        identity=runtime_identity(runtime_instance_id="runtime:foreign"),
        arm=fx["control"],
        observed_downstream_output_sha256=B,
        observed_monotonic_ns=50,
        intervention_activation=INTERVENTION_ABSENT_OBSERVED,
    )
    with pytest.raises(GwtCausalRuntimeReadbackError, match="control readback runtime identity mismatch"):
        bind(fx, control_readback=foreign_control_readback)


def test_intervention_output_must_close_to_live_runtime_uptake_downstream_digest():
    fx = make_fixture()
    other_intervention = CausalProbeArm.intervention(
        arm_id="arm:intervention:other-output",
        probe_id=fx["control"].probe_id,
        broadcast=fx["broadcast"],
        nonbroadcast_input_sha256=A,
        downstream_output_sha256=F,
        provenance_refs=("prov:other-intervention",),
    )
    other_result = evaluate_causal_influence(
        result_id="causal:other-output",
        broadcast=fx["broadcast"],
        uptake_summary=fx["uptake_summary"],
        intervention=other_intervention,
        control=fx["control"],
        provenance_refs=("prov:other-output-result",),
    )
    other_readback = observe_causal_arm_runtime_readback(
        identity=fx["runtime_witness"].identity,
        arm=other_intervention,
        observed_downstream_output_sha256=F,
        observed_monotonic_ns=40,
        intervention_activation=INTERVENTION_ACTIVE_OBSERVED,
    )
    with pytest.raises(GwtCausalRuntimeReadbackError, match="intervention output does not match live uptake"):
        bind(
            fx,
            intervention=other_intervention,
            causal_result=other_result,
            intervention_readback=other_readback,
        )


def test_directly_constructed_arm_readback_cannot_cross_binder_boundary():
    fx = make_fixture()
    forged = replace(fx["control_readback"], _factory_seal=None)
    with pytest.raises(GwtCausalRuntimeReadbackError, match="lacks factory origin"):
        bind(fx, control_readback=forged)


def test_tampered_bound_readback_is_rejected_after_seal():
    observed = bind(make_fixture())
    forged = replace(observed, broadcast_sha256=F)
    with pytest.raises(GwtCausalRuntimeReadbackError, match="payload changed after seal"):
        validate_gwt_causal_runtime_readback(forged)
