from dataclasses import replace
import hashlib
import inspect
import json

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessRecorder,
    RuntimeObservationIdentity,
)
from frankenstein2.gwt_semantic_content_causality import (
    BlindSemanticOutcome,
    ContentAddressedSemanticPayload,
    GwtSemanticContentCausalityError,
    MatchedCrossoverMechanics,
    SEMANTIC_CONTENT_CAUSALITY_CANDIDATE,
    SemanticContentTrial,
    build_semantic_content_crossover,
    validate_semantic_content_crossover,
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
D = "d" * 64
E = "e" * 64


def canonical_bytes(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def make_plan():
    return Grid10Plan.create(
        plan_id="grid-plan-wp900-g9",
        cycle_id="cycle-wp900-g9",
        generation=9,
        frame_id="frame-wp900-g9",
        frame_generation=9,
        frame_sha256=A,
        policy_id="grid-policy-wp900-g9",
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
        provenance_refs=("prov:grid-plan-wp900-g9",),
    )


def make_selection(plan, *, suffix, payload_ref):
    producer_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        input_refs=(f"input:{suffix}",),
        provenance_refs=(f"prov:producer-input:{suffix}",),
    )
    producer_output = CellOutput.for_input(
        plan,
        producer_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=(payload_ref,),
        evidence_refs=(f"evidence:producer:{suffix}",),
        provenance_refs=(f"prov:producer-output:{suffix}",),
    )
    candidate = WorkspaceCandidate(
        candidate_id=f"candidate:wp900-g9:{suffix}",
        payload_ref=payload_ref,
        epistemic_class="INFERRED",
        provenance_refs=(f"prov:candidate:{suffix}",),
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
        policy_id="gwt-policy-wp900-g9",
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
        selection_id=f"selection:wp900-g9:{suffix}",
        cycle_id=plan.cycle_id,
        generation=9,
        frame_id=plan.frame_id,
        frame_generation=plan.frame_generation,
        frame_sha256=plan.frame_sha256,
        grid_plan_id=plan.plan_id,
        grid_plan_generation=plan.generation,
        grid_plan_sha256=plan.sha256(),
        policy=policy,
        candidates=(candidate,),
    )


def identity():
    return RuntimeObservationIdentity(
        runtime_instance_id="runtime:wp900-g9:test",
        process_identity="pid:9009:start:1",
        boot_id_sha256=D,
        exact_source_sha256=E,
    )


def mechanics():
    return MatchedCrossoverMechanics(
        task_id="task:wp900-g9",
        task_schema="F2_WP900_G9_MATCHED_TASK/v1",
        context_sha256=A,
        pre_state_sha256=B,
        executor_identity="executor:wp900-g9",
        execution_context_sha256=C,
    )


def clock(*values):
    sequence = iter(values)
    return lambda: next(sequence)


def make_trial(
    *,
    order_position,
    semantic_class_id,
    surface_variant_id,
    treatment,
    outcome,
    matched_mechanics=None,
):
    payload = ContentAddressedSemanticPayload.from_bytes(
        semantic_class_id=semantic_class_id,
        surface_variant_id=surface_variant_id,
        payload_bytes=canonical_bytes(treatment),
    )
    plan = make_plan()
    suffix = f"{semantic_class_id.lower()}-{surface_variant_id.lower()}-{order_position}"
    selection = make_selection(plan, suffix=suffix, payload_ref=payload.payload_ref)
    broadcast = create_broadcast(
        broadcast_id=f"broadcast:wp900-g9:{suffix}",
        generation=9,
        selection=selection,
        expected_selection_sha256=selection.sha256(),
        recipient_cell_ids=("G1",),
    )
    cell_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        reentry_depth=1,
        input_refs=(payload.payload_ref,),
        provenance_refs=(f"prov:reentry-input:{suffix}",),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    raw_outcome = canonical_bytes(outcome)
    uptake = CellUptakeReceipt.observe(
        receipt_id=f"receipt:wp900-g9:{suffix}",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref=f"downstream:wp900-g9:{suffix}",
        downstream_sha256=hashlib.sha256(raw_outcome).hexdigest(),
        provenance_refs=(f"prov:uptake:{suffix}",),
    )
    binding = bind_reentry_to_uptake(
        binding_id=f"binding:wp900-g9:{suffix}",
        witness=witness,
        uptake_receipt=uptake,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=(f"prov:binding:{suffix}",),
    )
    base = order_position * 100
    recorder = GwtRuntimeWitnessRecorder(
        identity=identity(),
        monotonic_ns=clock(base + 10, base + 20, base + 30),
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
    outcome_observation = BlindSemanticOutcome.observe_json(
        uptake_receipt=uptake,
        raw_downstream_bytes=raw_outcome,
        observer_identity="observer:wp900-g9:blind",
        observed_monotonic_ns=base + 40,
        provenance_refs=(f"prov:blind-observer:{suffix}",),
    )
    return SemanticContentTrial.bind(
        order_position=order_position,
        mechanics=matched_mechanics or mechanics(),
        payload=payload,
        broadcast=broadcast,
        uptake_receipt=uptake,
        runtime_witness=runtime_witness,
        blind_outcome=outcome_observation,
    )


def positive_trials():
    # ABBA counterbalance with two byte-distinct surface forms per semantic class.
    return (
        make_trial(
            order_position=1,
            semantic_class_id="ALLOW",
            surface_variant_id="A1",
            treatment={"meaning": "allow", "surface": "permit"},
            outcome={"decision": "allow"},
        ),
        make_trial(
            order_position=2,
            semantic_class_id="DENY",
            surface_variant_id="B1",
            treatment={"meaning": "deny", "surface": "reject"},
            outcome={"decision": "deny"},
        ),
        make_trial(
            order_position=3,
            semantic_class_id="DENY",
            surface_variant_id="B2",
            treatment={"meaning": "deny", "surface": "refuse"},
            outcome={"decision": "deny"},
        ),
        make_trial(
            order_position=4,
            semantic_class_id="ALLOW",
            surface_variant_id="A2",
            treatment={"meaning": "allow", "surface": "approve"},
            outcome={"decision": "allow"},
        ),
    )


def test_positive_orthogonalized_crossover_is_candidate_only_and_mints_zero_credit():
    candidate = build_semantic_content_crossover(
        crossover_id="crossover:wp900-g9:positive",
        trials=positive_trials(),
        provenance_refs=("prov:wp900-g9:repository-test",),
    )
    validate_semantic_content_crossover(candidate)

    assert candidate.classification == SEMANTIC_CONTENT_CAUSALITY_CANDIDATE
    assert len({trial.payload.payload_sha256 for trial in candidate.trials}) == 4
    assert tuple(trial.payload.semantic_class_id for trial in candidate.trials) == (
        "ALLOW",
        "DENY",
        "DENY",
        "ALLOW",
    )
    assert candidate.class_outcome_sha256[0] != candidate.class_outcome_sha256[1]
    assert candidate.repository_ci_credit == 0
    assert candidate.target_environment_component_runtime_credit == 0
    assert candidate.semantic_content_causal_candidate_credit == 0
    assert candidate.semantic_gwt_runtime_credit == 0
    assert candidate.jspace_runtime_credit == 0
    assert candidate.effect_credit == 0
    assert candidate.training_credit == 0
    assert candidate.completion_credit == 0
    assert candidate.whole_system_acceptance is False


def test_blind_observer_api_has_no_treatment_or_semantic_class_parameter():
    parameters = inspect.signature(BlindSemanticOutcome.observe_json).parameters
    forbidden = {
        "condition",
        "treatment",
        "semantic_class",
        "semantic_class_id",
        "surface_variant_id",
        "expected_outcome",
    }
    assert forbidden.isdisjoint(parameters)


def test_one_payload_per_class_repeated_is_rejected_as_equivalence_confound():
    trials = list(positive_trials())
    # Build a second independently bound trial with the same treatment bytes.
    # Broadcast identity is new, but the treatment content address repeats.
    trials[3] = make_trial(
        order_position=4,
        semantic_class_id="ALLOW",
        surface_variant_id="A2",
        treatment={"meaning": "allow", "surface": "permit"},
        outcome={"decision": "allow"},
    )
    assert trials[3].payload.payload_sha256 == trials[0].payload.payload_sha256
    with pytest.raises(
        GwtSemanticContentCausalityError,
        match="four byte-distinct payload variants",
    ):
        build_semantic_content_crossover(
            crossover_id="crossover:wp900-g9:payload-confound",
            trials=tuple(trials),
            provenance_refs=("prov:test",),
        )


def test_within_class_semantic_instability_fails_closed():
    trials = list(positive_trials())
    trials[3] = make_trial(
        order_position=4,
        semantic_class_id="ALLOW",
        surface_variant_id="A2",
        treatment={"meaning": "allow", "surface": "approve"},
        outcome={"decision": "deny"},
    )
    with pytest.raises(
        GwtSemanticContentCausalityError,
        match="not stable across same-class surface variants",
    ):
        build_semantic_content_crossover(
            crossover_id="crossover:wp900-g9:unstable",
            trials=tuple(trials),
            provenance_refs=("prov:test",),
        )


def test_cross_class_same_outcome_fails_closed():
    trials = list(positive_trials())
    trials[1] = make_trial(
        order_position=2,
        semantic_class_id="DENY",
        surface_variant_id="B1",
        treatment={"meaning": "deny", "surface": "reject"},
        outcome={"decision": "allow"},
    )
    trials[2] = make_trial(
        order_position=3,
        semantic_class_id="DENY",
        surface_variant_id="B2",
        treatment={"meaning": "deny", "surface": "refuse"},
        outcome={"decision": "allow"},
    )
    with pytest.raises(
        GwtSemanticContentCausalityError,
        match="did not produce different blind downstream semantics",
    ):
        build_semantic_content_crossover(
            crossover_id="crossover:wp900-g9:no-difference",
            trials=tuple(trials),
            provenance_refs=("prov:test",),
        )


def test_non_counterbalanced_class_order_is_rejected():
    reordered = (
        make_trial(
            order_position=1,
            semantic_class_id="ALLOW",
            surface_variant_id="A1",
            treatment={"meaning": "allow", "surface": "permit"},
            outcome={"decision": "allow"},
        ),
        make_trial(
            order_position=2,
            semantic_class_id="ALLOW",
            surface_variant_id="A2",
            treatment={"meaning": "allow", "surface": "approve"},
            outcome={"decision": "allow"},
        ),
        make_trial(
            order_position=3,
            semantic_class_id="DENY",
            surface_variant_id="B1",
            treatment={"meaning": "deny", "surface": "reject"},
            outcome={"decision": "deny"},
        ),
        make_trial(
            order_position=4,
            semantic_class_id="DENY",
            surface_variant_id="B2",
            treatment={"meaning": "deny", "surface": "refuse"},
            outcome={"decision": "deny"},
        ),
    )
    with pytest.raises(
        GwtSemanticContentCausalityError,
        match="counterbalanced",
    ):
        build_semantic_content_crossover(
            crossover_id="crossover:wp900-g9:order",
            trials=reordered,
            provenance_refs=("prov:test",),
        )


def test_unmatched_pre_state_is_rejected():
    trials = list(positive_trials())
    altered = MatchedCrossoverMechanics(
        task_id="task:wp900-g9",
        task_schema="F2_WP900_G9_MATCHED_TASK/v1",
        context_sha256=A,
        pre_state_sha256=E,
        executor_identity="executor:wp900-g9",
        execution_context_sha256=C,
    )
    trials[2] = make_trial(
        order_position=3,
        semantic_class_id="DENY",
        surface_variant_id="B2",
        treatment={"meaning": "deny", "surface": "refuse"},
        outcome={"decision": "deny"},
        matched_mechanics=altered,
    )
    with pytest.raises(
        GwtSemanticContentCausalityError,
        match="mechanics are not matched",
    ):
        build_semantic_content_crossover(
            crossover_id="crossover:wp900-g9:prestate",
            trials=tuple(trials),
            provenance_refs=("prov:test",),
        )


def test_forged_runtime_witness_cannot_enter_trial_binder():
    trial = positive_trials()[0]
    forged_witness = replace(trial.runtime_witness, _factory_seal=None)
    with pytest.raises(ValueError, match="factory origin"):
        SemanticContentTrial.bind(
            order_position=trial.order_position,
            mechanics=trial.mechanics,
            payload=trial.payload,
            broadcast=trial.broadcast,
            uptake_receipt=trial.uptake_receipt,
            runtime_witness=forged_witness,
            blind_outcome=trial.blind_outcome,
        )


def test_payload_must_be_bound_as_exact_single_broadcast_candidate_ref():
    trial = positive_trials()[0]
    other_payload = ContentAddressedSemanticPayload.from_bytes(
        semantic_class_id="ALLOW",
        surface_variant_id="A3",
        payload_bytes=canonical_bytes({"meaning": "allow", "surface": "authorize"}),
    )
    with pytest.raises(
        GwtSemanticContentCausalityError,
        match="broadcast payload ref does not bind",
    ):
        SemanticContentTrial.bind(
            order_position=trial.order_position,
            mechanics=trial.mechanics,
            payload=other_payload,
            broadcast=trial.broadcast,
            uptake_receipt=trial.uptake_receipt,
            runtime_witness=trial.runtime_witness,
            blind_outcome=trial.blind_outcome,
        )
