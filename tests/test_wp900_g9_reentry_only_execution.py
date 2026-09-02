import dataclasses
import hashlib
import inspect
import os

import pytest

from frankenstein2.grid10_interface import CellInput
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_runtime_witness import GwtRuntimeWitnessRecorder, RuntimeObservationIdentity
from frankenstein2.gwt_semantic_reentry_only_execution import (
    FORBIDDEN_BEHAVIORAL_INPUT_KEYS,
    FrozenSemanticOracle,
    G9NoBypassError,
    NO_BYPASS_SEMANTIC_CANDIDATE,
    PostSelectionSemanticSlotPlan,
    ReentryDerivedSemanticState,
    ReentryOnlyExecutorPlan,
    behavioral_input_keys,
    bind_no_bypass_crossover,
    execute_reentry_only,
    validate_no_bypass_crossover,
)
from frankenstein2.gwt_uptake import CellUptakeReceipt
from frankenstein2.gwt_workspace import create_broadcast

from test_wp900_g9_semantic_content_causality import A, B, D, E, make_plan, make_selection

SLOT = "semantic-slot:wp900-g9:post-selection"
PAYLOADS = (
    b'{"meaning":"allow","surface":"permit"}',
    b'{"meaning":"deny","surface":"reject"}',
    b'{"meaning":"deny","surface":"refuse"}',
    b'{"meaning":"allow","surface":"approve"}',
)


def payload_oracle():
    return FrozenSemanticOracle.create(
        oracle_id="oracle:g9:payload:v1",
        field_name="meaning",
        allowed_values=("allow", "deny"),
        unknown_value="UNKNOWN",
        provenance_refs=("prov:oracle:payload",),
    )


def outcome_oracle():
    return FrozenSemanticOracle.create(
        oracle_id="oracle:g9:outcome:v1",
        field_name="decision",
        allowed_values=("allow", "deny"),
        unknown_value="UNKNOWN",
        provenance_refs=("prov:oracle:outcome",),
    )


def invariant_selection_and_broadcast():
    plan = make_plan()
    selection = make_selection(plan, suffix="semantic-slot-invariant", payload_ref=SLOT)
    broadcast = create_broadcast(
        broadcast_id="broadcast:wp900-g9:semantic-slot-invariant",
        generation=9,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )
    return plan, selection, broadcast


def slot_plan():
    _, selection, broadcast = invariant_selection_and_broadcast()
    return PostSelectionSemanticSlotPlan.create(
        plan_id="g9:no-bypass:slot-plan:v1",
        semantic_slot_ref=SLOT,
        selection=selection,
        broadcast=broadcast,
        payload_oracle=payload_oracle(),
        outcome_oracle=outcome_oracle(),
        trial_semantic_order=("allow", "deny", "deny", "allow"),
        provenance_refs=("prov:slot-plan",),
    ), selection, broadcast


def executor_plan():
    return ReentryOnlyExecutorPlan.create(
        plan_id="g9:no-bypass:executor-plan:v1",
        semantic_field_name="meaning",
        decision_mapping=(("allow", "allow"), ("deny", "deny")),
        task_context_sha256=A,
        runtime_pre_state_sha256=B,
        provenance_refs=("prov:executor-plan",),
    )


def runtime_state(*, semantic_slot_plan, broadcast, trial_position, payload):
    plan = make_plan()
    selection = make_selection(plan, suffix="semantic-slot-invariant", payload_ref=SLOT)
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=(SLOT,),
        provenance_refs=(f"prov:reentry-input:{trial_position}",),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    uptake = CellUptakeReceipt.observe(
        receipt_id=f"receipt:g9:no-bypass:{trial_position}",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref=SLOT,
        downstream_sha256=hashlib.sha256(payload).hexdigest(),
        provenance_refs=(f"prov:uptake:{trial_position}",),
    )
    binding = bind_reentry_to_uptake(
        binding_id=f"binding:g9:no-bypass:{trial_position}",
        witness=witness,
        uptake_receipt=uptake,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=(f"prov:binding:{trial_position}",),
    )
    ticks = iter((trial_position * 100 + 10, trial_position * 100 + 20, trial_position * 100 + 30))
    recorder = GwtRuntimeWitnessRecorder(
        identity=RuntimeObservationIdentity(
            runtime_instance_id=f"runtime:g9:no-bypass:{trial_position}",
            process_identity=f"runtime-process:g9:no-bypass:{trial_position}",
            boot_id_sha256=D,
            exact_source_sha256=E,
        ),
        monotonic_ns=lambda: next(ticks),
    )
    recorder.observe_delivery(broadcast)
    recorder.observe_uptake(uptake)
    recorder.observe_reentry(
        witness=witness,
        binding=binding,
        plan=plan,
        selection=selection,
        cell_input=cell_input,
    )
    runtime_witness = recorder.seal()
    return ReentryDerivedSemanticState.observe(
        plan=semantic_slot_plan,
        broadcast=broadcast,
        runtime_witness=runtime_witness,
        uptake_receipt=uptake,
        trial_position=trial_position,
        semantic_payload=payload,
        provenance_refs=(f"prov:semantic-state:{trial_position}",),
    )


def all_states_and_receipts():
    semantic_slot_plan, _, broadcast = slot_plan()
    plan = executor_plan()
    states = tuple(
        runtime_state(
            semantic_slot_plan=semantic_slot_plan,
            broadcast=broadcast,
            trial_position=position,
            payload=payload,
        )
        for position, payload in enumerate(PAYLOADS, start=1)
    )
    receipts = tuple(
        execute_reentry_only(
            executor_plan=plan,
            semantic_state=state,
            outcome_oracle=semantic_slot_plan.outcome_oracle,
        )
        for state in states
    )
    return semantic_slot_plan, plan, states, receipts


def test_no_bypass_crossover_is_preregistered_fresh_process_candidate_only():
    semantic_slot_plan, plan, states, receipts = all_states_and_receipts()
    candidate = bind_no_bypass_crossover(
        semantic_slot_plan=semantic_slot_plan,
        executor_plan=plan,
        semantic_states=states,
        execution_receipts=receipts,
        provenance_refs=("prov:g9:no-bypass:repository",),
    )
    validate_no_bypass_crossover(candidate)
    assert candidate.classification == NO_BYPASS_SEMANTIC_CANDIDATE
    assert candidate.semantic_order == ("allow", "deny", "deny", "allow")
    assert len(set(candidate.raw_payload_sha256s)) == 4
    assert len(set(candidate.child_pids)) == 4
    assert candidate.observed_mapping == (("allow", "allow"), ("deny", "deny"))
    assert candidate.repository_ci_credit == 0
    assert candidate.target_environment_component_runtime_credit == 0
    assert candidate.semantic_content_causal_candidate_credit == 0
    assert candidate.semantic_gwt_runtime_credit == 0
    assert candidate.jspace_runtime_credit == 0
    assert candidate.whole_system_acceptance is False


def test_behavioral_input_has_no_payload_identity_arm_or_runtime_witness_side_channel():
    assert behavioral_input_keys().isdisjoint(FORBIDDEN_BEHAVIORAL_INPUT_KEYS)
    forbidden = {
        "payload_ref", "payload_sha256", "broadcast_id", "broadcast_sha256",
        "condition", "arm", "trial_position", "semantic_class", "expected_outcome",
        "runtime_witness_sha256", "registry_handle", "resolver",
    }
    assert forbidden.isdisjoint(behavioral_input_keys())


def test_semantic_class_is_derived_by_frozen_oracle_not_caller_parameter():
    params = inspect.signature(ReentryDerivedSemanticState.observe).parameters
    assert "semantic_class" not in params
    assert "expected_outcome" not in params
    semantic_slot_plan, _, broadcast = slot_plan()
    state = runtime_state(
        semantic_slot_plan=semantic_slot_plan,
        broadcast=broadcast,
        trial_position=1,
        payload=PAYLOADS[0],
    )
    assert state.semantic_class == "allow"


def test_direct_parent_environment_payload_side_channel_cannot_change_child_behavior(monkeypatch):
    semantic_slot_plan, _, broadcast = slot_plan()
    plan = executor_plan()
    state = runtime_state(
        semantic_slot_plan=semantic_slot_plan,
        broadcast=broadcast,
        trial_position=1,
        payload=PAYLOADS[0],
    )
    monkeypatch.setenv("WP900_G9_DIRECT_PAYLOAD_CLASS", "deny")
    monkeypatch.setenv("WP900_G9_PAYLOAD_REF", "sha256:" + "f" * 64)
    receipt = execute_reentry_only(
        executor_plan=plan,
        semantic_state=state,
        outcome_oracle=semantic_slot_plan.outcome_oracle,
    )
    assert receipt.outcome_class == "allow"
    assert set(receipt.environment_keys) == {"PYTHONHASHSEED", "PYTHONIOENCODING"}
    assert receipt.child_pid != os.getpid()


def test_same_reentry_semantic_state_is_invariant_to_conflicting_external_payload_hint(monkeypatch):
    semantic_slot_plan, _, broadcast = slot_plan()
    plan = executor_plan()
    state = runtime_state(
        semantic_slot_plan=semantic_slot_plan,
        broadcast=broadcast,
        trial_position=1,
        payload=PAYLOADS[0],
    )
    monkeypatch.setenv("WP900_G9_DIRECT_PAYLOAD_CLASS", "deny")
    first = execute_reentry_only(
        executor_plan=plan,
        semantic_state=state,
        outcome_oracle=semantic_slot_plan.outcome_oracle,
    )
    monkeypatch.setenv("WP900_G9_DIRECT_PAYLOAD_CLASS", "allow")
    second = execute_reentry_only(
        executor_plan=plan,
        semantic_state=state,
        outcome_oracle=semantic_slot_plan.outcome_oracle,
    )
    assert first.outcome_class == second.outcome_class == "allow"
    assert first.child_pid != second.child_pid


def test_forged_runtime_witness_cannot_create_reentry_semantic_state():
    semantic_slot_plan, _, broadcast = slot_plan()
    plan = make_plan()
    selection = make_selection(plan, suffix="semantic-slot-invariant", payload_ref=SLOT)
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=(SLOT,),
        provenance_refs=("prov:forged-input",),
    )
    witness = build_reentry_witness(plan=plan, selection=selection, broadcast=broadcast, cell_input=cell_input)
    uptake = CellUptakeReceipt.observe(
        receipt_id="receipt:forged",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref=SLOT,
        downstream_sha256=hashlib.sha256(PAYLOADS[0]).hexdigest(),
        provenance_refs=("prov:forged-uptake",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:forged",
        witness=witness,
        uptake_receipt=uptake,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:forged-binding",),
    )
    ticks = iter((10, 20, 30))
    recorder = GwtRuntimeWitnessRecorder(
        identity=RuntimeObservationIdentity(
            runtime_instance_id="runtime:forged",
            process_identity="process:forged",
            boot_id_sha256=D,
            exact_source_sha256=E,
        ),
        monotonic_ns=lambda: next(ticks),
    )
    recorder.observe_delivery(broadcast)
    recorder.observe_uptake(uptake)
    recorder.observe_reentry(
        witness=witness,
        binding=binding,
        plan=plan,
        selection=selection,
        cell_input=cell_input,
    )
    forged = dataclasses.replace(recorder.seal(), _factory_seal=None)
    with pytest.raises(G9NoBypassError, match="factory-valid"):
        ReentryDerivedSemanticState.observe(
            plan=semantic_slot_plan,
            broadcast=broadcast,
            runtime_witness=forged,
            uptake_receipt=uptake,
            trial_position=1,
            semantic_payload=PAYLOADS[0],
            provenance_refs=("prov:forged-state",),
        )


def test_prebroadcast_treatment_specific_payload_ref_is_rejected():
    plan = make_plan()
    payload_ref = "sha256:" + hashlib.sha256(PAYLOADS[0]).hexdigest()
    selection = make_selection(plan, suffix="bad-prebroadcast-treatment", payload_ref=payload_ref)
    broadcast = create_broadcast(
        broadcast_id="broadcast:bad-prebroadcast-treatment",
        generation=9,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )
    with pytest.raises(G9NoBypassError, match="treatment-invariant semantic slot"):
        PostSelectionSemanticSlotPlan.create(
            plan_id="bad-plan",
            semantic_slot_ref=SLOT,
            selection=selection,
            broadcast=broadcast,
            payload_oracle=payload_oracle(),
            outcome_oracle=outcome_oracle(),
            trial_semantic_order=("allow", "deny", "deny", "allow"),
            provenance_refs=("prov:bad-plan",),
        )


def test_executor_receipt_cannot_be_swapped_between_semantic_states():
    semantic_slot_plan, plan, states, receipts = all_states_and_receipts()
    swapped = list(receipts)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    with pytest.raises(G9NoBypassError, match="corresponding reentry semantic state"):
        bind_no_bypass_crossover(
            semantic_slot_plan=semantic_slot_plan,
            executor_plan=plan,
            semantic_states=states,
            execution_receipts=tuple(swapped),
            provenance_refs=("prov:swapped",),
        )
