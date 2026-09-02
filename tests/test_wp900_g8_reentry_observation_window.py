from dataclasses import replace
import inspect

import pytest

from frankenstein2.gwt_reentry_observation_window import (
    MECHANISM_COMPARISON_UNKNOWN,
    MECHANISM_REENTRY_DIFFERENCE,
    NO_MECHANISM_REENTRY_DIFFERENCE,
    NO_REENTRY_OBSERVED,
    REENTRY_OBSERVATION_UNKNOWN,
    REENTRY_OBSERVED,
    TRACE_REENTRY,
    ReentryObservationError,
    ReentryObservationIdentity,
    ReentryObservationWindowReceipt,
    ReentryObservationWindowRecorder,
    bind_matched_reentry_mechanism,
    validate_reentry_observation_window,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64
G = "1" * 64
H = "2" * 64
I = "3" * 64
J = "4" * 64
K = "5" * 64
L = "6" * 64
M = "7" * 64


def identity(
    *,
    runtime="runtime:a",
    process="pid:1",
    pre_state=D,
    executor=E,
    filter_sha=H,
    clock_domain="CLOCK_MONOTONIC_RAW",
    execution_context=C,
):
    return ReentryObservationIdentity(
        exact_source_sha256=A,
        boot_id_sha256=B,
        execution_context_sha256=execution_context,
        task_id="task:wp900:g8:mechanism",
        task_input_sha256=F,
        pre_state_sha256=pre_state,
        task_executor_sha256=executor,
        observation_protocol_sha256=G,
        filter_sha256=filter_sha,
        clock_domain=clock_domain,
        observer_identity="observer:wp900:g8:condition-blind",
        runtime_instance_id=runtime,
        process_identity=process,
        provenance_refs=("prov:identity",),
    )


def recorder(
    *,
    runtime="runtime:a",
    process="pid:1",
    pre_state=D,
    executor=E,
    filter_sha=H,
    clock_domain="CLOCK_MONOTONIC_RAW",
    execution_context=C,
    ticks=(10, 20, 30),
    observer_started=5,
    filter_bound=6,
    source_open=100,
    dropped_open=0,
):
    clock = iter(ticks)
    return ReentryObservationWindowRecorder(
        window_id=f"window:{runtime}",
        identity=identity(
            runtime=runtime,
            process=process,
            pre_state=pre_state,
            executor=executor,
            filter_sha=filter_sha,
            clock_domain=clock_domain,
            execution_context=execution_context,
        ),
        opportunity_ref="opportunity:same-task-terminal",
        opportunity_sha256=I,
        observer_started_monotonic_ns=observer_started,
        filter_bound_monotonic_ns=filter_bound,
        source_sequence_at_open=source_open,
        dropped_event_count_at_open=dropped_open,
        monotonic_ns=lambda: next(clock),
        provenance_refs=("prov:window",),
    )


def positive(
    *,
    runtime="runtime:a",
    process="pid:1",
    pre_state=D,
    executor=E,
    filter_sha=H,
    clock_domain="CLOCK_MONOTONIC_RAW",
    execution_context=C,
):
    value = recorder(
        runtime=runtime,
        process=process,
        pre_state=pre_state,
        executor=executor,
        filter_sha=filter_sha,
        clock_domain=clock_domain,
        execution_context=execution_context,
    )
    value.observe_reentry(
        source_sequence=101,
        reentry_ref="reentry:observed",
        reentry_sha256=J,
    )
    return value.close_complete(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=K,
        post_state_sha256=L,
        source_sequence_at_close=101,
        dropped_event_count_at_close=0,
        observer_live_through_monotonic_ns=35,
        trace_finalized_monotonic_ns=40,
        provenance_refs=("prov:complete-positive",),
    )


def negative(
    *,
    runtime="runtime:b",
    process="pid:2",
    pre_state=D,
    executor=E,
    filter_sha=H,
    clock_domain="CLOCK_MONOTONIC_RAW",
    execution_context=C,
):
    value = recorder(
        runtime=runtime,
        process=process,
        pre_state=pre_state,
        executor=executor,
        filter_sha=filter_sha,
        clock_domain=clock_domain,
        execution_context=execution_context,
        ticks=(11, 31),
    )
    return value.close_complete(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=K,
        post_state_sha256=L,
        source_sequence_at_close=100,
        dropped_event_count_at_close=0,
        observer_live_through_monotonic_ns=35,
        trace_finalized_monotonic_ns=40,
        provenance_refs=("prov:complete-negative",),
    )


def incomplete_close(
    *,
    dropped_open=0,
    dropped_close=0,
    observer_started=5,
    filter_bound=6,
    live_through=35,
    finalized=40,
    source_open=100,
    source_close=100,
    trace_event_sequence=None,
):
    ticks = (10, 20, 30) if trace_event_sequence is not None else (10, 30)
    value = recorder(
        runtime="runtime:incomplete",
        process="pid:incomplete",
        ticks=ticks,
        observer_started=observer_started,
        filter_bound=filter_bound,
        source_open=source_open,
        dropped_open=dropped_open,
    )
    if trace_event_sequence is not None:
        value.observe_other(
            source_sequence=trace_event_sequence,
            evidence_ref="trace:other",
            evidence_sha256=M,
        )
    return value.close_complete(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=K,
        post_state_sha256=L,
        source_sequence_at_close=source_close,
        dropped_event_count_at_close=dropped_close,
        observer_live_through_monotonic_ns=live_through,
        trace_finalized_monotonic_ns=finalized,
    )


def test_g8_observer_api_is_condition_blind_and_has_no_expected_boolean():
    init_params = set(inspect.signature(ReentryObservationWindowRecorder.__init__).parameters)
    observe_params = set(inspect.signature(ReentryObservationWindowRecorder.observe_reentry).parameters)
    close_params = set(inspect.signature(ReentryObservationWindowRecorder.close_complete).parameters)
    forbidden = {
        "condition",
        "arm",
        "expected",
        "expected_result",
        "expected_boolean",
        "broadcast_present",
        "reentry_observed",
    }
    assert forbidden.isdisjoint(init_params | observe_params | close_params)


def test_g8_complete_positive_and_negative_derive_from_same_trace_abi():
    observed = positive()
    absent = negative()
    validate_reentry_observation_window(observed)
    validate_reentry_observation_window(absent)

    assert observed.status == REENTRY_OBSERVED
    assert absent.status == NO_REENTRY_OBSERVED
    assert observed.unknown_reasons == ()
    assert absent.unknown_reasons == ()
    assert observed.trace_sha256 != absent.trace_sha256

    candidate = bind_matched_reentry_mechanism(
        arm_a=observed,
        arm_b=absent,
        provenance_refs=("prov:matched-pair",),
    )
    assert candidate.classification == MECHANISM_REENTRY_DIFFERENCE
    assert candidate.semantic_gwt_runtime_credit == 0
    assert candidate.jspace_runtime_credit == 0
    assert candidate.whole_system_acceptance is False


def test_g8_complete_empty_sequence_range_is_valid_negative():
    absent = negative()
    assert absent.source_sequence_at_open == absent.source_sequence_at_close == 100
    assert absent.status == NO_REENTRY_OBSERVED
    assert [event for event in absent.events if event.source_sequence is not None] == []


def test_g8_injected_reentry_cannot_false_green_as_absence():
    value = recorder(runtime="runtime:control", process="pid:control")
    value.observe_reentry(
        source_sequence=101,
        reentry_ref="reentry:unexpected-control-event",
        reentry_sha256=J,
    )
    receipt = value.close_complete(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=K,
        post_state_sha256=L,
        source_sequence_at_close=101,
        dropped_event_count_at_close=0,
        observer_live_through_monotonic_ns=35,
        trace_finalized_monotonic_ns=40,
    )
    assert receipt.status == REENTRY_OBSERVED
    assert any(event.phase == TRACE_REENTRY for event in receipt.events)


@pytest.mark.parametrize(
    ("receipt", "reason"),
    [
        (lambda: incomplete_close(dropped_close=1), "DROPPED_EVENT_COUNTER_NONZERO"),
        (lambda: incomplete_close(observer_started=12), "OBSERVER_STARTED_AFTER_WINDOW_OPEN"),
        (lambda: incomplete_close(filter_bound=12), "FILTER_BOUND_AFTER_WINDOW_OPEN"),
        (lambda: incomplete_close(live_through=25), "OBSERVER_NOT_LIVE_THROUGH_WINDOW_END"),
        (lambda: incomplete_close(finalized=25), "TRACE_NOT_FINALIZED_THROUGH_WINDOW_END"),
        (
            lambda: incomplete_close(source_close=102, trace_event_sequence=102),
            "FILTERED_TRACE_SEQUENCE_GAP",
        ),
    ],
)
def test_g8_incomplete_or_lossy_negative_evidence_is_unknown(receipt, reason):
    observed = receipt()
    validate_reentry_observation_window(observed)
    assert observed.status == REENTRY_OBSERVATION_UNKNOWN
    assert reason in observed.unknown_reasons


def test_g8_nonzero_drop_counter_at_window_open_is_unknown_even_if_close_is_zero():
    observed = incomplete_close(dropped_open=1, dropped_close=0)
    assert observed.status == REENTRY_OBSERVATION_UNKNOWN
    assert "DROPPED_EVENT_COUNTER_NONZERO" in observed.unknown_reasons


def test_g8_contiguous_filtered_trace_can_include_non_reentry_events_and_still_prove_absence():
    ticks = iter((10, 20, 30, 40))
    value = ReentryObservationWindowRecorder(
        window_id="window:trace-other",
        identity=identity(runtime="runtime:trace-other", process="pid:trace-other"),
        opportunity_ref="opportunity:same-task-terminal",
        opportunity_sha256=I,
        observer_started_monotonic_ns=5,
        filter_bound_monotonic_ns=6,
        source_sequence_at_open=100,
        dropped_event_count_at_open=0,
        monotonic_ns=lambda: next(ticks),
        provenance_refs=("prov:trace-other",),
    )
    value.observe_other(source_sequence=101, evidence_ref="trace:other:1", evidence_sha256=M)
    value.observe_other(source_sequence=102, evidence_ref="trace:other:2", evidence_sha256=J)
    receipt = value.close_complete(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=K,
        post_state_sha256=L,
        source_sequence_at_close=102,
        dropped_event_count_at_close=0,
        observer_live_through_monotonic_ns=45,
        trace_finalized_monotonic_ns=50,
    )
    assert receipt.status == NO_REENTRY_OBSERVED
    assert receipt.unknown_reasons == ()


def test_g8_abort_is_unknown_and_cannot_be_compared_as_negative():
    value = recorder(runtime="runtime:aborted", process="pid:aborted", ticks=(10, 20))
    receipt = value.abort(
        reason_ref="abort:runner-stop",
        reason_sha256=K,
        source_sequence_at_close=100,
        dropped_event_count_at_close=0,
    )
    validate_reentry_observation_window(receipt)
    assert receipt.status == REENTRY_OBSERVATION_UNKNOWN
    assert "WINDOW_ABORTED" in receipt.unknown_reasons

    candidate = bind_matched_reentry_mechanism(
        arm_a=positive(),
        arm_b=receipt,
        provenance_refs=("prov:unknown-pair",),
    )
    assert candidate.classification == MECHANISM_COMPARISON_UNKNOWN


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"pre_state": M}, "pre_state_sha256"),
        ({"executor": M}, "task_executor_sha256"),
        ({"filter_sha": M}, "filter_sha256"),
        ({"clock_domain": "CLOCK_OTHER"}, "clock_domain"),
        ({"execution_context": M}, "execution_context_sha256"),
    ],
)
def test_g8_pair_fails_closed_on_matched_context_mismatch(kwargs, field):
    with pytest.raises(ReentryObservationError, match=field):
        bind_matched_reentry_mechanism(
            arm_a=positive(),
            arm_b=negative(**kwargs),
            provenance_refs=("prov:bad-context",),
        )


def test_g8_swapping_pair_order_does_not_change_mechanism_classification():
    observed = positive()
    absent = negative()
    forward = bind_matched_reentry_mechanism(
        arm_a=observed,
        arm_b=absent,
        provenance_refs=("prov:forward",),
    )
    reverse = bind_matched_reentry_mechanism(
        arm_a=absent,
        arm_b=observed,
        provenance_refs=("prov:reverse",),
    )
    assert forward.classification == reverse.classification == MECHANISM_REENTRY_DIFFERENCE


def test_g8_equal_independent_observations_do_not_claim_mechanism_difference():
    first = positive(runtime="runtime:a", process="pid:a")
    second = positive(runtime="runtime:b", process="pid:b")
    candidate = bind_matched_reentry_mechanism(
        arm_a=first,
        arm_b=second,
        provenance_refs=("prov:equal",),
    )
    assert candidate.classification == NO_MECHANISM_REENTRY_DIFFERENCE
    assert candidate.semantic_gwt_runtime_credit == 0


def test_g8_direct_receipt_construction_lacks_observer_origin():
    valid = negative()
    forged = ReentryObservationWindowReceipt(
        window_id=valid.window_id,
        identity=valid.identity,
        opportunity_sha256=valid.opportunity_sha256,
        terminal_evidence_sha256=valid.terminal_evidence_sha256,
        post_state_sha256=valid.post_state_sha256,
        observer_started_monotonic_ns=valid.observer_started_monotonic_ns,
        filter_bound_monotonic_ns=valid.filter_bound_monotonic_ns,
        window_start_monotonic_ns=valid.window_start_monotonic_ns,
        window_end_monotonic_ns=valid.window_end_monotonic_ns,
        observer_live_through_monotonic_ns=valid.observer_live_through_monotonic_ns,
        trace_finalized_monotonic_ns=valid.trace_finalized_monotonic_ns,
        source_sequence_at_open=valid.source_sequence_at_open,
        source_sequence_at_close=valid.source_sequence_at_close,
        dropped_event_count_at_open=valid.dropped_event_count_at_open,
        dropped_event_count_at_close=valid.dropped_event_count_at_close,
        trace_sha256=valid.trace_sha256,
        events=valid.events,
        unknown_reasons=valid.unknown_reasons,
        status=valid.status,
        provenance_refs=valid.provenance_refs,
    )
    with pytest.raises(ReentryObservationError, match="lacks recorder origin"):
        validate_reentry_observation_window(forged)


def test_g8_tamper_after_factory_seal_is_detected():
    valid = negative()
    tampered = replace(valid, provenance_refs=("prov:tampered",))
    with pytest.raises(ReentryObservationError, match="payload changed after seal"):
        validate_reentry_observation_window(tampered)


def test_g8_candidate_remains_mechanism_scoped_with_all_higher_credits_zero():
    candidate = bind_matched_reentry_mechanism(
        arm_a=positive(),
        arm_b=negative(),
        provenance_refs=("prov:scope",),
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
