import hashlib
import json
from dataclasses import replace

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_causal_runtime_readback import (
    ControlNoBroadcastReadback,
    ProbeExecutionContext,
    bind_causal_runtime_readback,
)
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_runtime_witness import GwtRuntimeWitnessRecorder, RuntimeObservationIdentity
from frankenstein2.gwt_semantic_runtime_readback import (
    GwtSemanticRuntimeReadbackError,
    NO_SEMANTIC_CAUSAL_DIFFERENCE,
    SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE,
    SEMANTIC_COMPARISON_UNKNOWN,
    SEMANTIC_DIFFERENCE_OBSERVED,
    SEMANTIC_EQUIVALENCE_OBSERVED,
    SEMANTIC_UNKNOWN_FAIL_CLOSED,
    SemanticArmReadback,
    bind_semantic_causal_readback,
    validate_semantic_causal_readback,
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
D = "d" * 64
E = "e" * 64
G = "1" * 64
H = "2" * 64
I = "3" * 64


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def context(**overrides):
    values = {
        "runner_identity": "runner:vps-clay-host",
        "execution_surface": "S1:ubuntu-24.04-oci",
        "runtime_engine_identity": "python:cpython-3.11",
        "runtime_engine_config_sha256": G,
        "environment_sha256": H,
        "dependency_set_sha256": I,
        "boot_id_sha256": D,
        "exact_source_sha256": E,
        "provenance_refs": ("prov:shared-execution-context",),
    }
    values.update(overrides)
    return ProbeExecutionContext(**values)


def make_contract(intervention_sha256: str, control_sha256: str):
    plan = Grid10Plan.create(
        plan_id="grid-plan-wp900-g6",
        cycle_id="cycle-wp900-g6",
        generation=6,
        frame_id="frame-wp900-g6",
        frame_generation=7,
        frame_sha256=A,
        policy_id="grid-policy-wp900-g6",
        policy_generation=1,
        policy_sha256=B,
        cells=tuple(
            CellBudget(
                cell_id=f"G{index}",
                role_label=f"role-{index}",
                max_input_refs=8,
                max_output_refs=8,
                max_work_units=8,
                max_reentry_depth=2,
            )
            for index in range(1, 11)
        ),
        max_total_work_units=80,
        provenance_refs=("prov:grid-plan-wp900-g6",),
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
        candidate_id="candidate:wp900-g6",
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
        policy_id="gwt-policy-wp900-g6",
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
        selection_id="selection:wp900-g6",
        cycle_id=plan.cycle_id,
        generation=10,
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
        broadcast_id="broadcast:wp900-g6",
        generation=6,
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
        receipt_id="receipt:wp900-g6:G1",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="readback:intervention",
        downstream_sha256=intervention_sha256,
        provenance_refs=("prov:wp900-g6-intervention",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:wp900-g6",
        witness=witness,
        uptake_receipt=uptake_receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:wp900-g6-runtime-binding",),
    )
    ticks = iter((10, 20, 30))
    recorder = GwtRuntimeWitnessRecorder(
        identity=RuntimeObservationIdentity(
            runtime_instance_id="runtime:wp900-g6:intervention",
            process_identity="pid:6100:start:100",
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
        summary_id="summary:wp900-g6",
        broadcast=broadcast,
        receipts=(uptake_receipt,),
        provenance_refs=("prov:wp900-g6-summary",),
    )
    shared_context = context()
    control_readback = ControlNoBroadcastReadback.observe(
        execution_context=shared_context,
        runtime_instance_id="runtime:wp900-g6:control",
        process_identity="pid:6101:start:200",
        boot_id_sha256=D,
        exact_source_sha256=E,
        probe_id="probe:wp900-g6",
        nonbroadcast_input_sha256=A,
        downstream_ref="readback:control",
        downstream_sha256=control_sha256,
        observed_monotonic_ns=40,
        reentry_observed=False,
        provenance_refs=("prov:wp900-g6-control",),
    )
    return bind_causal_runtime_readback(
        probe_id="probe:wp900-g6",
        nonbroadcast_input_sha256=A,
        execution_context=shared_context,
        broadcast=broadcast,
        runtime_witness=runtime_witness,
        uptake_receipt=uptake_receipt,
        uptake_summary=uptake_summary,
        control_readback=control_readback,
        provenance_refs=("prov:wp900-g6-contract",),
    )


def arm(*, contract, condition: str, raw_payload: bytes, task_schema="decision-task/v1", outcome_schema="decision-outcome/v1", source=E):
    if condition == "INTERVENTION_BROADCAST":
        downstream_ref = contract.intervention_downstream_ref
        downstream_sha256 = contract.intervention_downstream_sha256
        runtime_id = "runtime:wp900-g6:intervention"
        producer = "producer:intervention"
        observed = 50
    else:
        downstream_ref = contract.control_downstream_ref
        downstream_sha256 = contract.control_downstream_sha256
        runtime_id = "runtime:wp900-g6:control"
        producer = "producer:control"
        observed = 60
    return SemanticArmReadback.observe_json(
        condition=condition,
        task_id="task:decision-42",
        task_schema=task_schema,
        outcome_schema=outcome_schema,
        downstream_ref=downstream_ref,
        expected_downstream_sha256=downstream_sha256,
        raw_payload=raw_payload,
        exact_source_sha256=source,
        boot_id_sha256=D,
        execution_context_sha256=context().sha256(),
        producer_identity=producer,
        runtime_instance_id=runtime_id,
        observed_monotonic_ns=observed,
        provenance_refs=(f"prov:{condition.lower()}",),
    )


def bind_semantics(intervention_payload: bytes, control_payload: bytes, **control_overrides):
    contract = make_contract(sha256_bytes(intervention_payload), sha256_bytes(control_payload))
    intervention = arm(
        contract=contract,
        condition="INTERVENTION_BROADCAST",
        raw_payload=intervention_payload,
    )
    control = arm(
        contract=contract,
        condition="CONTROL_NO_BROADCAST",
        raw_payload=control_payload,
        **control_overrides,
    )
    result = bind_semantic_causal_readback(
        contract_candidate=contract,
        intervention=intervention,
        control=control,
        provenance_refs=("prov:wp900-g6-semantic-binder",),
    )
    return contract, intervention, control, result


def test_pr884_byte_distinct_semantic_equivalence_is_not_semantic_causal_difference():
    semantic_value = {"decision": "ABSTAIN", "reason": "insufficient-evidence"}
    intervention_payload = json.dumps(semantic_value, sort_keys=True, separators=(",", ":")).encode()
    control_payload = json.dumps(semantic_value, sort_keys=False, indent=2).encode()

    assert intervention_payload != control_payload
    assert sha256_bytes(intervention_payload) != sha256_bytes(control_payload)
    assert json.loads(intervention_payload) == json.loads(control_payload)

    _, _, _, result = bind_semantics(intervention_payload, control_payload)
    validate_semantic_causal_readback(result)

    assert result.comparison_status == SEMANTIC_EQUIVALENCE_OBSERVED
    assert result.classification == NO_SEMANTIC_CAUSAL_DIFFERENCE
    assert result.intervention_semantic_sha256 == result.control_semantic_sha256
    assert result.semantic_gwt_runtime_credit == 0
    assert result.jspace_runtime_credit == 0
    assert result.runtime_credit == 0
    assert result.whole_system_acceptance is False


def test_actual_outcome_difference_is_only_a_zero_credit_semantic_candidate():
    intervention_payload = b'{"decision":"ALLOW","reason":"evidence-present"}'
    control_payload = b'{"decision":"ABSTAIN","reason":"insufficient-evidence"}'

    _, _, _, result = bind_semantics(intervention_payload, control_payload)

    assert result.comparison_status == SEMANTIC_DIFFERENCE_OBSERVED
    assert result.classification == SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE
    assert result.intervention_semantic_sha256 != result.control_semantic_sha256
    assert result.target_environment_component_runtime_credit == 0
    assert result.semantic_gwt_runtime_credit == 0
    assert result.jspace_runtime_credit == 0
    assert result.effect_credit == 0
    assert result.training_credit == 0
    assert result.completion_credit == 0


def test_outcome_schema_mismatch_is_first_class_unknown_not_difference():
    intervention_payload = b'{"decision":"ALLOW"}'
    control_payload = b'{"decision":"ABSTAIN"}'

    _, _, _, result = bind_semantics(
        intervention_payload,
        control_payload,
        outcome_schema="different-outcome-schema/v2",
    )

    assert result.comparison_status == SEMANTIC_COMPARISON_UNKNOWN
    assert result.classification == SEMANTIC_UNKNOWN_FAIL_CLOSED
    assert result.semantic_gwt_runtime_credit == 0
    assert result.jspace_runtime_credit == 0


def test_raw_payload_must_match_exact_g4_downstream_digest():
    expected_payload = b'{"decision":"ALLOW"}'
    contract = make_contract(sha256_bytes(expected_payload), sha256_bytes(b'{"decision":"ABSTAIN"}'))

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="raw payload does not match accepted downstream SHA-256"):
        SemanticArmReadback.observe_json(
            condition="INTERVENTION_BROADCAST",
            task_id="task:decision-42",
            task_schema="decision-task/v1",
            outcome_schema="decision-outcome/v1",
            downstream_ref=contract.intervention_downstream_ref,
            expected_downstream_sha256=contract.intervention_downstream_sha256,
            raw_payload=b'{"decision":"DENY"}',
            exact_source_sha256=E,
            boot_id_sha256=D,
            execution_context_sha256=context().sha256(),
            producer_identity="producer:intervention",
            runtime_instance_id="runtime:intervention",
            observed_monotonic_ns=50,
            provenance_refs=("prov:bad-raw",),
        )


def test_source_lineage_mismatch_fails_closed_before_semantic_comparison():
    intervention_payload = b'{"decision":"ALLOW"}'
    control_payload = b'{"decision":"ABSTAIN"}'
    contract = make_contract(sha256_bytes(intervention_payload), sha256_bytes(control_payload))
    intervention = arm(contract=contract, condition="INTERVENTION_BROADCAST", raw_payload=intervention_payload)
    control = arm(
        contract=contract,
        condition="CONTROL_NO_BROADCAST",
        raw_payload=control_payload,
        source="9" * 64,
    )

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="control exact-source identity mismatch"):
        bind_semantic_causal_readback(
            contract_candidate=contract,
            intervention=intervention,
            control=control,
            provenance_refs=("prov:mismatch",),
        )


def test_duplicate_json_keys_are_rejected_as_semantically_ambiguous():
    payload = b'{"decision":"ALLOW","decision":"DENY"}'
    contract = make_contract(sha256_bytes(payload), sha256_bytes(b'{"decision":"ABSTAIN"}'))

    with pytest.raises(GwtSemanticRuntimeReadbackError, match="duplicate JSON key"):
        arm(contract=contract, condition="INTERVENTION_BROADCAST", raw_payload=payload)
