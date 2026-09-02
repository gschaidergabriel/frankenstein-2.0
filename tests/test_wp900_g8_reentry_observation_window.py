import inspect
from dataclasses import replace

import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.gwt_reentry_provenance import build_reentry_witness
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake
from frankenstein2.gwt_runtime_witness import GwtRuntimeWitnessRecorder, RuntimeObservationIdentity
from frankenstein2.gwt_uptake import CellUptakeReceipt
from frankenstein2.gwt_workspace import (
    CandidateProducerAdmission,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
    create_broadcast,
)
from frankenstein2.gwt_reentry_observation_window import (
    MECHANISM_COMPARISON_UNKNOWN,
    MECHANISM_REENTRY_DIFFERENCE,
    NO_MECHANISM_REENTRY_DIFFERENCE,
    NO_REENTRY_OBSERVED,
    REENTRY_OBSERVATION_UNKNOWN,
    REENTRY_OBSERVED,
    ReentryObservationError,
    ReentryObservationIdentity,
    ReentryObservationWindowReceipt,
    ReentryObservationWindowRecorder,
    bind_matched_reentry_mechanism,
    validate_reentry_observation_window,
)

SOURCE = "a" * 64
BOOT = "b" * 64
CONTEXT = "c" * 64
PRE_STATE = "d" * 64
EXECUTOR = "e" * 64
TASK_INPUT = "f" * 64
PROTOCOL = "1" * 64
OPPORTUNITY = "2" * 64
TERMINAL = "3" * 64
POST_STATE = "4" * 64
TRACE_SOURCE = "5" * 64
FILTER = "6" * 64
CLOCK_MAP = "7" * 64
RAW_TRACE = "8" * 64
FRAME = "9" * 64


def runtime_witness(*, runtime="runtime:intervention", process="pid:100:start:1"):
    plan = Grid10Plan.create(
        plan_id="grid-plan-wp900-g8",
        cycle_id="cycle-wp900-g8",
        generation=8,
        frame_id="frame-wp900-g8",
        frame_generation=1,
        frame_sha256=FRAME,
        policy_id="grid-policy-wp900-g8",
        policy_generation=1,
        policy_sha256=PROTOCOL,
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
        provenance_refs=("prov:g8-plan",),
    )
    producer_input = CellInput.for_plan(
        plan,
        cell_id="G1",
        work_units_requested=2,
        input_refs=("input:g8",),
        provenance_refs=("prov:g8-producer-input",),
    )
    producer_output = CellOutput.for_input(
        plan,
        producer_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=("payload:g8",),
        evidence_refs=("evidence:g8",),
        provenance_refs=("prov:g8-producer-output",),
    )
    candidate = WorkspaceCandidate(
        candidate_id="candidate:g8",
        payload_ref="payload:g8",
        epistemic_class="INFERRED",
        provenance_refs=("prov:g8-candidate",),
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
        policy_id="selection-policy:g8",
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
        selection_id="selection:g8",
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
    broadcast = create_broadcast(
        broadcast_id="broadcast:g8",
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
        input_refs=("payload:g8",),
        provenance_refs=("prov:g8-reentry-input",),
    )
    witness = build_reentry_witness(
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
    )
    uptake = CellUptakeReceipt.observe(
        receipt_id="receipt:g8:G1",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:g8",
        downstream_sha256=TASK_INPUT,
        provenance_refs=("prov:g8-uptake",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:g8",
        witness=witness,
        uptake_receipt=uptake,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:g8-binding",),
    )
    ticks = iter((100, 110, 120))
    recorder = GwtRuntimeWitnessRecorder(
        identity=RuntimeObservationIdentity(
            runtime_instance_id=runtime,
            process_identity=process,
            boot_id_sha256=BOOT,
            exact_source_sha256=SOURCE,
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
    return recorder.seal()


BASE_WITNESS = runtime_witness()


def identity(
    *,
    runtime="runtime:intervention",
    process="pid:100:start:1",
    pre_state=PRE_STATE,
    executor=EXECUTOR,
    expected=BASE_WITNESS,
):
    return ReentryObservationIdentity(
        exact_source_sha256=SOURCE,
        boot_id_sha256=BOOT,
        execution_context_sha256=CONTEXT,
        task_id="task:wp900:g8:mechanism",
        task_input_sha256=TASK_INPUT,
        pre_state_sha256=pre_state,
        task_executor_sha256=executor,
        observation_protocol_sha256=PROTOCOL,
        expected_reentry_key_sha256=expected.canonical_reentry_key,
        expected_reentry_binding_sha256=expected.binding_sha256,
        expected_recipient_cell_id=expected.recipient_cell_id,
        trace_source_sha256=TRACE_SOURCE,
        filter_schema_sha256=FILTER,
        clock_domain="CLOCK_MONOTONIC_RAW",
        clock_mapping_sha256=CLOCK_MAP,
        observer_identity="observer:wp900:g8:condition-blind",
        runtime_instance_id=runtime,
        process_identity=process,
        provenance_refs=("prov:g8-identity",),
    )


def recorder(
    *,
    runtime="runtime:intervention",
    process="pid:100:start:1",
    pre_state=PRE_STATE,
    executor=EXECUTOR,
    expected=BASE_WITNESS,
    ticks=(10, 20, 30),
):
    clock = iter(ticks)
    return ReentryObservationWindowRecorder(
        window_id=f"window:{runtime}",
        identity=identity(
            runtime=runtime,
            process=process,
            pre_state=pre_state,
            executor=executor,
            expected=expected,
        ),
        opportunity_ref="opportunity:same-task-terminal",
        opportunity_sha256=OPPORTUNITY,
        monotonic_ns=lambda: next(clock),
        provenance_refs=("prov:g8-window",),
    )


def trace_kwargs(**overrides):
    values = {
        "observer_started_monotonic_ns": 1,
        "observer_finalized_monotonic_ns": 40,
        "source_sequence_start": 1000,
        "source_sequence_end": 1010,
        "captured_sequence_start": 1000,
        "captured_sequence_end": 1010,
        "sequence_gap_count": 0,
        "dropped_event_count": 0,
        "overflow_count": 0,
        "raw_trace_sha256": RAW_TRACE,
        "filter_schema_sha256": FILTER,
        "clock_domain": "CLOCK_MONOTONIC_RAW",
        "clock_mapping_sha256": CLOCK_MAP,
        "finalized": True,
    }
    values.update(overrides)
    return values


def close(value, **trace_overrides):
    return value.close_with_trace(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=TERMINAL,
        post_state_sha256=POST_STATE,
        provenance_refs=("prov:g8-complete",),
        **trace_kwargs(**trace_overrides),
    )


def positive(
    *,
    runtime="runtime:intervention",
    process="pid:100:start:1",
    pre_state=PRE_STATE,
    executor=EXECUTOR,
    witness=BASE_WITNESS,
    **trace_overrides,
):
    value = recorder(
        runtime=runtime,
        process=process,
        pre_state=pre_state,
        executor=executor,
        expected=witness,
    )
    value.observe_runtime_witness(witness)
    return close(value, **trace_overrides)


def negative(
    *,
    runtime="runtime:control",
    process="pid:200:start:1",
    pre_state=PRE_STATE,
    executor=EXECUTOR,
    expected=BASE_WITNESS,
    **trace_overrides,
):
    value = recorder(
        runtime=runtime,
        process=process,
        pre_state=pre_state,
        executor=executor,
        expected=expected,
        ticks=(11, 31),
    )
    return close(value, **trace_overrides)


def test_g8_observer_api_has_no_caller_injected_reentry_ref_or_expected_boolean():
    init_params = set(inspect.signature(ReentryObservationWindowRecorder.__init__).parameters)
    observe_params = set(inspect.signature(ReentryObservationWindowRecorder.observe_runtime_witness).parameters)
    close_params = set(inspect.signature(ReentryObservationWindowRecorder.close_with_trace).parameters)
    forbidden = {
        "condition",
        "arm",
        "expected",
        "expected_result",
        "expected_boolean",
        "broadcast_present",
        "reentry_observed",
        "reentry_ref",
        "reentry_sha256",
    }
    assert forbidden.isdisjoint(init_params | observe_params | close_params)
    assert not hasattr(ReentryObservationWindowRecorder, "observe_reentry")


def test_g8_positive_requires_recorder_origin_witness_and_complete_negative_is_trace_derived():
    observed = positive()
    absent = negative()

    validate_reentry_observation_window(observed)
    validate_reentry_observation_window(absent)
    assert observed.status == REENTRY_OBSERVED
    assert absent.status == NO_REENTRY_OBSERVED
    assert observed.trace_complete is True
    assert absent.trace_complete is True

    candidate = bind_matched_reentry_mechanism(
        arm_a=observed,
        arm_b=absent,
        provenance_refs=("prov:g8-matched",),
    )
    assert candidate.classification == MECHANISM_REENTRY_DIFFERENCE
    assert candidate.semantic_gwt_runtime_credit == 0
    assert candidate.jspace_runtime_credit == 0


def test_g8_condition_aware_caller_cannot_mint_reentry_with_arbitrary_strings():
    value = recorder()
    with pytest.raises(AttributeError):
        value.observe_reentry(reentry_ref="fake", reentry_sha256="a" * 64)


def test_g8_forged_or_wrong_runtime_witness_fails_closed():
    value = recorder()
    forged = replace(BASE_WITNESS, _factory_seal=None)
    with pytest.raises(ReentryObservationError, match="origin"):
        value.observe_runtime_witness(forged)

    other = runtime_witness(runtime="runtime:other", process="pid:other")
    value = recorder()
    with pytest.raises(ReentryObservationError, match="runtime instance"):
        value.observe_runtime_witness(other)


def test_g8_witness_from_wrong_reentry_binding_fails_closed():
    wrong_expected = replace(identity(), expected_reentry_binding_sha256="0" * 64)
    clock = iter((10, 20))
    value = ReentryObservationWindowRecorder(
        window_id="window:wrong-binding",
        identity=wrong_expected,
        opportunity_ref="opportunity:same-task-terminal",
        opportunity_sha256=OPPORTUNITY,
        monotonic_ns=lambda: next(clock),
        provenance_refs=("prov:wrong-binding",),
    )
    with pytest.raises(ReentryObservationError, match="binding"):
        value.observe_runtime_witness(BASE_WITNESS)


@pytest.mark.parametrize(
    "trace_overrides",
    [
        {"dropped_event_count": 1},
        {"overflow_count": 1},
        {"sequence_gap_count": 1},
        {"captured_sequence_end": 1009},
        {"observer_started_monotonic_ns": 11},
        {"observer_finalized_monotonic_ns": 31},
        {"finalized": False},
    ],
)
def test_g8_negative_absence_is_unknown_if_trace_completeness_is_not_proven(trace_overrides):
    receipt = negative(**trace_overrides)
    assert receipt.status == REENTRY_OBSERVATION_UNKNOWN
    assert receipt.trace_complete is False

    candidate = bind_matched_reentry_mechanism(
        arm_a=positive(),
        arm_b=receipt,
        provenance_refs=("prov:g8-incomplete-pair",),
    )
    assert candidate.classification == MECHANISM_COMPARISON_UNKNOWN


def test_g8_aborted_window_is_unknown():
    value = recorder(runtime="runtime:control", process="pid:200:start:1", ticks=(10, 20))
    receipt = value.abort(reason_ref="abort:runner-stop", reason_sha256=TERMINAL)
    assert receipt.status == REENTRY_OBSERVATION_UNKNOWN
    assert receipt.trace_complete is False


def test_g8_pair_fails_closed_on_pre_state_or_executor_mismatch():
    observed = positive()
    wrong_state = negative(pre_state="0" * 64)
    with pytest.raises(ReentryObservationError, match="pre_state_sha256"):
        bind_matched_reentry_mechanism(
            arm_a=observed,
            arm_b=wrong_state,
            provenance_refs=("prov:g8-bad-state",),
        )

    wrong_executor = negative(executor="b" * 64)
    with pytest.raises(ReentryObservationError, match="task_executor_sha256"):
        bind_matched_reentry_mechanism(
            arm_a=observed,
            arm_b=wrong_executor,
            provenance_refs=("prov:g8-bad-executor",),
        )


def test_g8_equal_real_witness_observations_do_not_claim_difference():
    witness_b = runtime_witness(runtime="runtime:b", process="pid:b")
    first = positive()
    second = positive(runtime="runtime:b", process="pid:b", witness=witness_b)
    candidate = bind_matched_reentry_mechanism(
        arm_a=first,
        arm_b=second,
        provenance_refs=("prov:g8-equal",),
    )
    assert candidate.classification == NO_MECHANISM_REENTRY_DIFFERENCE


def test_g8_direct_receipt_construction_lacks_observer_origin():
    valid = negative()
    forged = ReentryObservationWindowReceipt(
        window_id=valid.window_id,
        identity=valid.identity,
        opportunity_sha256=valid.opportunity_sha256,
        terminal_evidence_sha256=valid.terminal_evidence_sha256,
        post_state_sha256=valid.post_state_sha256,
        trace_completeness=valid.trace_completeness,
        events=valid.events,
        status=valid.status,
        provenance_refs=valid.provenance_refs,
    )
    with pytest.raises(ReentryObservationError, match="lacks recorder origin"):
        validate_reentry_observation_window(forged)


def test_g8_candidate_remains_mechanism_scoped_with_all_higher_credits_zero():
    candidate = bind_matched_reentry_mechanism(
        arm_a=positive(),
        arm_b=negative(),
        provenance_refs=("prov:g8-scope",),
    )
    assert "MECHANISM_REENTRY" in candidate.evidence_scope
    assert candidate.repository_ci_credit == 0
    assert candidate.target_environment_component_runtime_credit == 0
    assert candidate.runtime_credit == 0
    assert candidate.gwt_runtime_credit == 0
    assert candidate.semantic_gwt_runtime_credit == 0
    assert candidate.jspace_runtime_credit == 0
    assert candidate.physical_grid10_credit == 0
    assert candidate.effect_credit == 0
    assert candidate.training_credit == 0
    assert candidate.completion_credit == 0
    assert candidate.whole_system_acceptance is False
