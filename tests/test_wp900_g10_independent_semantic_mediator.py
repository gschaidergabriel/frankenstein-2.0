import hashlib
import inspect
import json
import os

import pytest

from frankenstein2.grid10_interface import CellInput
from frankenstein2.gwt_independent_semantic_mediator import (
    FORBIDDEN_BEHAVIORAL_INPUT_KEYS,
    FORBIDDEN_TRIAL_WIRE_KEYS,
    G10MediatorError,
    MEDIATOR_AUTHORITY_CANDIDATE,
    TRIAL_BEHAVIOR_WIRE_SCHEMA,
    TRIAL_WIRE_ALLOWED_KEYS,
    IndependentSemanticMediatorReceipt,
    MediatedSemanticState,
    behavioral_input_keys,
    bind_independent_semantic_mediator_crossover,
    execute_mediated_reentry_only,
    trial_wire_keys,
    validate_independent_semantic_mediator_crossover,
)
from frankenstein2.gwt_reentry_causal_admission import IndependentEventSourceRangeRecorder
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_runtime_witness import GwtRuntimeWitnessRecorder, RuntimeObservationIdentity
from frankenstein2.gwt_uptake import CellUptakeReceipt

from test_wp900_g9_reentry_only_execution import (
    D,
    E,
    PAYLOADS,
    SLOT,
    executor_plan,
    make_plan,
    make_selection,
    slot_plan,
)


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def source_mediator(*, position, payload):
    semantic_slot_plan, invariant_selection, broadcast = slot_plan()
    plan = make_plan()
    selection = make_selection(plan, suffix="semantic-slot-invariant", payload_ref=SLOT)
    assert selection.sha256() == invariant_selection.sha256()
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=(SLOT,),
        provenance_refs=(f"prov:g10:source-input:{position}",),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    uptake = CellUptakeReceipt.observe(
        receipt_id=f"receipt:g10:source:{position}",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref=SLOT,
        downstream_sha256=hashlib.sha256(payload).hexdigest(),
        provenance_refs=(f"prov:g10:source-uptake:{position}",),
    )
    binding = bind_reentry_to_uptake(
        binding_id=f"binding:g10:source:{position}",
        witness=witness,
        uptake_receipt=uptake,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=(f"prov:g10:source-binding:{position}",),
    )
    source_identity = f"source-process:g10:{position}"
    ticks = iter((position * 1000 + 10, position * 1000 + 20, position * 1000 + 30))
    runtime = GwtRuntimeWitnessRecorder(
        identity=RuntimeObservationIdentity(
            runtime_instance_id=f"runtime:g10:source:{position}",
            process_identity=source_identity,
            boot_id_sha256=D,
            exact_source_sha256=E,
        ),
        monotonic_ns=lambda: next(ticks),
    )
    runtime.observe_delivery(broadcast)
    runtime.observe_uptake(uptake)
    runtime.observe_reentry(
        witness=witness,
        binding=binding,
        plan=plan,
        selection=selection,
        cell_input=cell_input,
    )
    runtime_witness = runtime.seal()

    recorder = IndependentEventSourceRangeRecorder(
        trace_source_sha256=hashlib.sha256(f"trace:g10:{position}".encode()).hexdigest(),
        filter_schema_sha256=hashlib.sha256(b"filter:g10:semantic-slot:v2").hexdigest(),
        clock_domain="CLOCK_MONOTONIC_RAW",
        clock_mapping_sha256=hashlib.sha256(b"clock:g10:identity:v2").hexdigest(),
        observer_identity=source_identity,
        observer_started_monotonic_ns=position * 1000 + 1,
        window_start_monotonic_ns=position * 1000 + 2,
        provenance_refs=(f"prov:g10:source-range:{position}",),
    )
    recorder.observe(
        source_sequence=position,
        observed_monotonic_ns=position * 1000 + 40,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        runtime_witness=runtime_witness,
    )
    source_range = recorder.seal(
        window_end_monotonic_ns=position * 1000 + 50,
        observer_finalized_monotonic_ns=position * 1000 + 60,
        provenance_refs=(f"prov:g10:source-seal:{position}",),
    )
    mediator = IndependentSemanticMediatorReceipt.observe(
        plan=semantic_slot_plan,
        broadcast=broadcast,
        source_range=source_range,
        uptake_receipt=uptake,
        semantic_payload=payload,
        trial_position=position,
        source_process_identity=source_identity,
        provenance_refs=(f"prov:g10:mediator:{position}",),
    )
    return semantic_slot_plan, mediator


def all_mediators_states_and_receipts():
    semantic_slot_plan = None
    mediators = []
    states = []
    for position, payload in enumerate(PAYLOADS, 1):
        semantic_slot_plan, mediator = source_mediator(position=position, payload=payload)
        state = MediatedSemanticState.from_wire(
            mediator=mediator,
            wire=mediator.to_wire(),
        )
        mediators.append(mediator)
        states.append(state)
    assert semantic_slot_plan is not None
    plan = executor_plan()
    receipts = tuple(
        execute_mediated_reentry_only(executor_plan=plan, semantic_state=state)
        for state in states
    )
    return semantic_slot_plan, plan, tuple(mediators), tuple(states), receipts


def test_independent_semantic_mediator_crossover_is_candidate_only():
    semantic_slot_plan, _, mediators, states, receipts = all_mediators_states_and_receipts()
    candidate = bind_independent_semantic_mediator_crossover(
        plan=semantic_slot_plan,
        mediators=mediators,
        states=states,
        execution_receipts=receipts,
        provenance_refs=("prov:g10:repository-crossover:v2",),
    )
    validate_independent_semantic_mediator_crossover(candidate)
    assert candidate.classification == MEDIATOR_AUTHORITY_CANDIDATE
    assert candidate.semantic_order == ("allow", "deny", "deny", "allow")
    assert candidate.outcome_order == ("allow", "deny", "deny", "allow")
    assert len(set(candidate.raw_payload_sha256s)) == 4
    assert len(set(candidate.wire_sha256s)) == 4
    assert len(set(candidate.source_process_identities)) == 4
    assert len(set(candidate.child_pids)) == 4
    assert candidate.observed_mapping == (("allow", "allow"), ("deny", "deny"))
    assert candidate.repository_ci_credit == 0
    assert candidate.target_environment_component_runtime_credit == 0
    assert candidate.semantic_gwt_runtime_credit == 0
    assert candidate.jspace_runtime_credit == 0
    assert candidate.whole_system_acceptance is False


def test_trial_visible_wire_is_minimal_and_plan_free():
    _, mediator = source_mediator(position=1, payload=PAYLOADS[0])
    wire = mediator.to_wire()
    value = json.loads(wire)
    assert set(value) == TRIAL_WIRE_ALLOWED_KEYS
    assert value["schema"] == TRIAL_BEHAVIOR_WIRE_SCHEMA
    assert trial_wire_keys(wire) == TRIAL_WIRE_ALLOWED_KEYS
    assert FORBIDDEN_TRIAL_WIRE_KEYS.isdisjoint(value)

    params = inspect.signature(MediatedSemanticState.from_wire).parameters
    assert set(params) == {"mediator", "wire"}
    assert "plan" not in params
    assert "trial_position" not in params
    assert "semantic_class" not in params
    assert "raw_payload_sha256" not in params

    state = MediatedSemanticState.from_wire(mediator=mediator, wire=wire)
    assert set(state.as_dict()) == {"schema", "canonical_semantic_json"}
    assert "semantic_class" not in state.as_dict()
    assert "trial_position" not in state.as_dict()
    assert "source_process_identity" not in state.as_dict()
    assert "runtime_witness_sha256" not in state.as_dict()


def test_behavioral_child_has_no_attestation_or_treatment_metadata_inputs():
    assert behavioral_input_keys().isdisjoint(FORBIDDEN_BEHAVIORAL_INPUT_KEYS)
    assert {
        "raw_payload_sha256",
        "semantic_class",
        "trial_position",
        "source_range_sha256",
        "source_process_identity",
        "runtime_witness_sha256",
        "wire_sha256",
        "arm",
        "condition",
        "trial_semantic_order",
        "provenance_refs",
    }.isdisjoint(behavioral_input_keys())


def test_complete_forged_wire_without_factory_valid_mediator_is_rejected():
    semantic = canonical({"meaning": "allow", "surface": "forged"})
    fake = IndependentSemanticMediatorReceipt(
        plan_sha256="1" * 64,
        trial_position=1,
        semantic_slot_ref="slot:g10:forged",
        canonical_semantic_json=semantic,
        semantic_sha256=hashlib.sha256(semantic.encode()).hexdigest(),
        raw_payload_sha256="2" * 64,
        semantic_class="allow",
        source_range_sha256="3" * 64,
        source_event_sequence=1,
        source_process_identity="source-process:g10:forged",
        runtime_witness_sha256="4" * 64,
        exact_source_sha256="5" * 64,
        boot_id_sha256="6" * 64,
        provenance_refs=("prov:g10:forged",),
    )
    forged_wire = canonical(
        {
            "schema": TRIAL_BEHAVIOR_WIRE_SCHEMA,
            "canonical_semantic_json": semantic,
        }
    ).encode()
    with pytest.raises(G10MediatorError, match="factory origin"):
        MediatedSemanticState.from_wire(mediator=fake, wire=forged_wire)


def test_self_consistent_public_wire_cannot_override_factory_mediator_origin():
    _, mediator = source_mediator(position=1, payload=PAYLOADS[0])
    alternate = canonical(json.loads(PAYLOADS[1]))
    forged_wire = canonical(
        {
            "schema": TRIAL_BEHAVIOR_WIRE_SCHEMA,
            "canonical_semantic_json": alternate,
        }
    ).encode()
    with pytest.raises(G10MediatorError, match="differs from factory-valid mediator"):
        MediatedSemanticState.from_wire(mediator=mediator, wire=forged_wire)


def test_mediator_requires_gwt_source_event_bound_to_exact_semantic_bytes():
    semantic_slot_plan, _, broadcast = slot_plan()
    plan = make_plan()
    selection = make_selection(plan, suffix="semantic-slot-invariant", payload_ref=SLOT)
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=(SLOT,),
        provenance_refs=("prov:g10:mismatch-input",),
    )
    witness = build_reentry_witness(plan=plan, selection=selection, broadcast=broadcast, cell_input=cell_input)
    payload = PAYLOADS[0]
    uptake = CellUptakeReceipt.observe(
        receipt_id="receipt:g10:mismatch",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref=SLOT,
        downstream_sha256=hashlib.sha256(payload).hexdigest(),
        provenance_refs=("prov:g10:mismatch-uptake",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:g10:mismatch",
        witness=witness,
        uptake_receipt=uptake,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:g10:mismatch-binding",),
    )
    ticks = iter((10, 20, 30))
    runtime = GwtRuntimeWitnessRecorder(
        identity=RuntimeObservationIdentity(
            runtime_instance_id="runtime:g10:mismatch",
            process_identity="source-process:g10:mismatch",
            boot_id_sha256=D,
            exact_source_sha256=E,
        ),
        monotonic_ns=lambda: next(ticks),
    )
    runtime.observe_delivery(broadcast)
    runtime.observe_uptake(uptake)
    runtime.observe_reentry(
        witness=witness,
        binding=binding,
        plan=plan,
        selection=selection,
        cell_input=cell_input,
    )
    runtime_witness = runtime.seal()
    recorder = IndependentEventSourceRangeRecorder(
        trace_source_sha256=hashlib.sha256(b"trace:g10:mismatch").hexdigest(),
        filter_schema_sha256=hashlib.sha256(b"filter:g10:mismatch").hexdigest(),
        clock_domain="CLOCK_MONOTONIC_RAW",
        clock_mapping_sha256=hashlib.sha256(b"clock:g10:mismatch").hexdigest(),
        observer_identity="source-process:g10:mismatch",
        observer_started_monotonic_ns=1,
        window_start_monotonic_ns=2,
        provenance_refs=("prov:g10:mismatch-range",),
    )
    recorder.observe(
        source_sequence=1,
        observed_monotonic_ns=40,
        payload_sha256=hashlib.sha256(b'{"meaning":"deny","surface":"wrong"}').hexdigest(),
        runtime_witness=runtime_witness,
    )
    source_range = recorder.seal(
        window_end_monotonic_ns=50,
        observer_finalized_monotonic_ns=60,
        provenance_refs=("prov:g10:mismatch-seal",),
    )
    with pytest.raises(G10MediatorError, match="exactly one GWT_REENTRY event bound"):
        IndependentSemanticMediatorReceipt.observe(
            plan=semantic_slot_plan,
            broadcast=broadcast,
            source_range=source_range,
            uptake_receipt=uptake,
            semantic_payload=payload,
            trial_position=1,
            source_process_identity="source-process:g10:mismatch",
            provenance_refs=("prov:g10:mismatch-mediator",),
        )


def test_behavior_wire_tamper_is_rejected_before_behavior():
    _, mediator = source_mediator(position=1, payload=PAYLOADS[0])
    value = json.loads(mediator.to_wire())
    value["canonical_semantic_json"] = canonical({"meaning": "deny", "surface": "reject"})
    tampered = canonical(value).encode()
    with pytest.raises(G10MediatorError, match="differs from factory-valid mediator"):
        MediatedSemanticState.from_wire(mediator=mediator, wire=tampered)


def test_external_payload_or_arm_hints_cannot_change_mediated_behavior(monkeypatch):
    _, mediator = source_mediator(position=1, payload=PAYLOADS[0])
    state = MediatedSemanticState.from_wire(
        mediator=mediator,
        wire=mediator.to_wire(),
    )
    monkeypatch.setenv("WP900_G10_DIRECT_PAYLOAD_CLASS", "deny")
    monkeypatch.setenv("WP900_G10_ARM", "deny")
    monkeypatch.setenv("WP900_G10_PAYLOAD_SHA256", "f" * 64)
    monkeypatch.setenv("WP900_G10_TRIAL_POSITION", "2")
    receipt = execute_mediated_reentry_only(executor_plan=executor_plan(), semantic_state=state)
    assert receipt.outcome_class == "allow"
    assert set(receipt.environment_keys) == {"PYTHONHASHSEED", "PYTHONIOENCODING"}
    assert receipt.child_pid != os.getpid()


def test_crossover_verifier_rejects_swapped_behavior_state_even_with_same_semantic_class():
    semantic_slot_plan, _, mediators, states, receipts = all_mediators_states_and_receipts()
    swapped = (states[3], states[1], states[2], states[0])
    with pytest.raises(G10MediatorError, match="not bound to corresponding source mediator"):
        bind_independent_semantic_mediator_crossover(
            plan=semantic_slot_plan,
            mediators=mediators,
            states=swapped,
            execution_receipts=receipts,
            provenance_refs=("prov:g10:swapped",),
        )


def test_repository_objects_cannot_self_mint_runtime_or_semantic_credit():
    _, mediator = source_mediator(position=1, payload=PAYLOADS[0])
    state = MediatedSemanticState.from_wire(mediator=mediator, wire=mediator.to_wire())
    receipt = execute_mediated_reentry_only(executor_plan=executor_plan(), semantic_state=state)
    for value in (mediator, state, receipt):
        assert value.repository_ci_credit == 0
        assert value.target_environment_component_runtime_credit == 0
        assert value.semantic_gwt_runtime_credit == 0
        assert value.jspace_runtime_credit == 0
        assert value.whole_system_acceptance is False
