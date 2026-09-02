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
    IndependentSemanticMediatorReceipt,
    MediatedSemanticState,
    admit_mediated_semantic_state,
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
    return mediator


def all_mediators_states_and_receipts():
    mediators = tuple(
        source_mediator(position=position, payload=payload)
        for position, payload in enumerate(PAYLOADS, 1)
    )
    states = tuple(
        admit_mediated_semantic_state(
            mediator=mediator,
            wire=mediator.to_wire(),
            trial_process_identity=f"trial-process:g10:{position}",
        )
        for position, mediator in enumerate(mediators, 1)
    )
    plan = executor_plan()
    receipts = tuple(
        execute_mediated_reentry_only(executor_plan=plan, semantic_state=state)
        for state in states
    )
    return mediators, plan, states, receipts


def test_independent_semantic_mediator_crossover_is_candidate_only():
    mediators, _, states, receipts = all_mediators_states_and_receipts()
    candidate = bind_independent_semantic_mediator_crossover(
        mediators=mediators,
        states=states,
        execution_receipts=receipts,
        provenance_refs=("prov:g10:repository-crossover-v2",),
    )
    validate_independent_semantic_mediator_crossover(candidate)
    assert candidate.semantic_order == ("allow", "deny", "deny", "allow")
    assert candidate.outcome_order == ("allow", "deny", "deny", "allow")
    assert len(set(candidate.raw_payload_sha256s)) == 4
    assert len(set(candidate.wire_sha256s)) == 4
    assert len(set(candidate.source_process_identities)) == 4
    assert len(set(candidate.trial_process_identities)) == 4
    assert set(candidate.source_process_identities).isdisjoint(candidate.trial_process_identities)
    assert len(set(candidate.child_pids)) == 4
    assert candidate.observed_mapping == (("allow", "allow"), ("deny", "deny"))
    assert candidate.classification == MEDIATOR_AUTHORITY_CANDIDATE
    assert candidate.repository_ci_credit == 0
    assert candidate.target_environment_component_runtime_credit == 0
    assert candidate.semantic_gwt_runtime_credit == 0
    assert candidate.jspace_runtime_credit == 0
    assert candidate.whole_system_acceptance is False


def test_trial_visible_wire_is_minimal_and_has_no_attestation_or_plan_sidechannels():
    mediator = source_mediator(position=1, payload=PAYLOADS[0])
    wire = mediator.to_wire()
    parsed = json.loads(wire)
    assert set(parsed) == {"schema", "canonical_semantic_json"}
    assert trial_wire_keys(wire).isdisjoint(FORBIDDEN_TRIAL_WIRE_KEYS)
    params = inspect.signature(admit_mediated_semantic_state).parameters
    assert "plan" not in params
    assert "semantic_payload" not in params
    assert "semantic_class" not in params
    assert "trial_position" not in params
    assert "source_range" not in params
    assert "runtime_witness" not in params
    assert behavioral_input_keys().isdisjoint(FORBIDDEN_BEHAVIORAL_INPUT_KEYS)


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


def test_self_consistent_forged_wire_is_rejected_before_behavioral_execution():
    mediator = source_mediator(position=1, payload=PAYLOADS[0])
    forged = json.dumps(
        {
            "schema": json.loads(mediator.to_wire())["schema"],
            "canonical_semantic_json": '{"meaning":"deny","surface":"reject"}',
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    with pytest.raises(G10MediatorError, match="not emitted by the factory-valid semantic mediator"):
        admit_mediated_semantic_state(
            mediator=mediator,
            wire=forged,
            trial_process_identity="trial-process:g10:forged",
        )


def test_direct_state_construction_cannot_reach_behavioral_execution():
    canonical = '{"meaning":"allow","surface":"approve"}'
    forged = MediatedSemanticState(
        canonical_semantic_json=canonical,
        semantic_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        wire_sha256="f" * 64,
        trial_process_identity="trial-process:g10:direct-forge",
    )
    with pytest.raises(G10MediatorError, match="lacks valid factory origin"):
        execute_mediated_reentry_only(executor_plan=executor_plan(), semantic_state=forged)


def test_source_and_trial_process_identity_must_differ():
    mediator = source_mediator(position=1, payload=PAYLOADS[0])
    with pytest.raises(G10MediatorError, match="must differ"):
        admit_mediated_semantic_state(
            mediator=mediator,
            wire=mediator.to_wire(),
            trial_process_identity=mediator.source_process_identity,
        )


def test_external_payload_or_arm_hints_cannot_change_mediated_behavior(monkeypatch):
    mediator = source_mediator(position=1, payload=PAYLOADS[0])
    state = admit_mediated_semantic_state(
        mediator=mediator,
        wire=mediator.to_wire(),
        trial_process_identity="trial-process:g10:hints",
    )
    monkeypatch.setenv("WP900_G10_DIRECT_PAYLOAD_CLASS", "deny")
    monkeypatch.setenv("WP900_G10_ARM", "deny")
    monkeypatch.setenv("WP900_G10_PAYLOAD_SHA256", "f" * 64)
    receipt = execute_mediated_reentry_only(executor_plan=executor_plan(), semantic_state=state)
    assert receipt.outcome_class == "allow"
    assert set(receipt.environment_keys) == {"PYTHONHASHSEED", "PYTHONIOENCODING"}
    assert receipt.child_pid != os.getpid()


def test_crossover_rejects_state_not_bound_to_corresponding_source_mediator():
    mediators, _, states, receipts = all_mediators_states_and_receipts()
    swapped = (mediators[1], mediators[0], mediators[2], mediators[3])
    with pytest.raises(G10MediatorError):
        bind_independent_semantic_mediator_crossover(
            mediators=swapped,
            states=states,
            execution_receipts=receipts,
            provenance_refs=("prov:g10:swapped-source-authority",),
        )


def test_repository_objects_cannot_self_mint_runtime_or_semantic_credit():
    mediators, _, states, receipts = all_mediators_states_and_receipts()
    candidate = bind_independent_semantic_mediator_crossover(
        mediators=mediators,
        states=states,
        execution_receipts=receipts,
        provenance_refs=("prov:g10:credit-v2",),
    )
    for value in (*mediators, *states, *receipts, candidate):
        assert value.repository_ci_credit == 0
        assert value.target_environment_component_runtime_credit == 0
        assert value.semantic_gwt_runtime_credit == 0
        assert value.jspace_runtime_credit == 0
        assert value.whole_system_acceptance is False
