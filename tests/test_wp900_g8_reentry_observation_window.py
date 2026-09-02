import inspect
import pytest

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
    TraceCompletenessEvidence,
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


def identity(*, runtime="runtime:a", process="pid:1", pre_state=D, executor=E, trace_filter=L, clock=M):
    return ReentryObservationIdentity(
        exact_source_sha256=A,
        boot_id_sha256=B,
        execution_context_sha256=C,
        task_id="task:wp900:g8:mechanism",
        task_input_sha256=F,
        pre_state_sha256=pre_state,
        task_executor_sha256=executor,
        observation_protocol_sha256=G,
        trace_filter_sha256=trace_filter,
        clock_domain_sha256=clock,
        observer_identity="observer:wp900:g8:condition-blind",
        runtime_instance_id=runtime,
        process_identity=process,
        provenance_refs=("prov:identity",),
    )


def recorder(*, runtime="runtime:a", process="pid:1", pre_state=D, executor=E, ticks=(10, 20, 30)):
    clock = iter(ticks)
    return ReentryObservationWindowRecorder(
        window_id=f"window:{runtime}",
        identity=identity(runtime=runtime, process=process, pre_state=pre_state, executor=executor),
        opportunity_ref="opportunity:same-task-terminal",
        opportunity_sha256=H,
        monotonic_ns=lambda: next(clock),
        provenance_refs=("prov:window",),
    )


def trace(
    *,
    observer_started=5,
    observer_live_through=40,
    finalized=41,
    source_first=100,
    source_last=102,
    source_count=3,
    captured_first=100,
    captured_last=102,
    captured_count=3,
    dropped=0,
    overflow=0,
    trace_filter=L,
    clock=M,
):
    return TraceCompletenessEvidence.record(
        observer_started_monotonic_ns=observer_started,
        observer_live_through_monotonic_ns=observer_live_through,
        trace_finalized_monotonic_ns=finalized,
        source_first_sequence=source_first,
        source_last_sequence=source_last,
        source_event_count=source_count,
        captured_first_sequence=captured_first,
        captured_last_sequence=captured_last,
        captured_event_count=captured_count,
        dropped_event_count=dropped,
        overflow_event_count=overflow,
        raw_trace_sha256=I,
        filter_sha256=trace_filter,
        clock_domain_sha256=clock,
        finalization_ref="trace:finalized",
        provenance_refs=("prov:trace",),
    )


def positive(*, runtime="runtime:a", process="pid:1", pre_state=D, executor=E, completeness=None):
    value = recorder(runtime=runtime, process=process, pre_state=pre_state, executor=executor)
    value.observe_reentry(
        reentry_ref="reentry:observed",
        reentry_sha256=I,
        source_sequence=101,
        task_id="task:wp900:g8:mechanism",
        task_input_sha256=F,
        pre_state_sha256=pre_state,
        task_executor_sha256=executor,
    )
    return value.close_complete(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=J,
        post_state_sha256=K,
        trace_completeness=trace() if completeness is None else completeness,
        provenance_refs=("prov:complete",),
    )


def negative(*, runtime="runtime:b", process="pid:2", pre_state=D, executor=E, completeness=None):
    value = recorder(runtime=runtime, process=process, pre_state=pre_state, executor=executor, ticks=(11, 31))
    return value.close_complete(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=J,
        post_state_sha256=K,
        trace_completeness=trace() if completeness is None else completeness,
        provenance_refs=("prov:complete-negative",),
    )


def test_observer_api_is_condition_blind_and_has_no_expected_boolean():
    params = set()
    for func in (
        ReentryObservationWindowRecorder.__init__,
        ReentryObservationWindowRecorder.observe_reentry,
        ReentryObservationWindowRecorder.close_complete,
        TraceCompletenessEvidence.record,
    ):
        params |= set(inspect.signature(func).parameters)
    forbidden = {
        "condition", "arm", "expected", "expected_result", "expected_boolean",
        "broadcast_present", "reentry_observed",
    }
    assert forbidden.isdisjoint(params)


def test_complete_trace_positive_and_negative_are_event_derived():
    observed = positive()
    absent = negative()
    assert observed.status == REENTRY_OBSERVED
    assert absent.status == NO_REENTRY_OBSERVED
    assert observed.trace_complete is True
    assert absent.trace_complete is True
    candidate = bind_matched_reentry_mechanism(
        arm_a=observed, arm_b=absent, provenance_refs=("prov:matched-pair",)
    )
    assert candidate.classification == MECHANISM_REENTRY_DIFFERENCE


@pytest.mark.parametrize(
    "bad_trace,reason",
    [
        (trace(dropped=1), "DROPPED_EVENTS_NONZERO"),
        (trace(overflow=1), "OVERFLOW_EVENTS_NONZERO"),
        (trace(observer_started=12), "OBSERVER_STARTED_AFTER_WINDOW_OPEN"),
        (trace(observer_live_through=20), "OBSERVER_NOT_LIVE_THROUGH_WINDOW_TERMINAL"),
        (trace(finalized=20), "TRACE_FINALIZED_BEFORE_WINDOW_TERMINAL"),
        (trace(source_count=2), "SOURCE_SEQUENCE_RANGE_NOT_CONTIGUOUS"),
        (trace(captured_first=101), "CAPTURED_SEQUENCE_RANGE_MISMATCH"),
        (trace(captured_count=2), "CAPTURED_EVENT_COUNT_MISMATCH"),
        (trace(trace_filter="8"*64), "TRACE_FILTER_IDENTITY_MISMATCH"),
        (trace(clock="9"*64), "TRACE_CLOCK_DOMAIN_MISMATCH"),
    ],
)
def test_negative_absence_fails_closed_to_unknown_on_incomplete_trace(bad_trace, reason):
    receipt = negative(completeness=bad_trace)
    assert receipt.status == REENTRY_OBSERVATION_UNKNOWN
    assert receipt.trace_complete is False
    assert reason in receipt.trace_incompleteness_reasons


def test_positive_presence_remains_observed_but_records_trace_incompleteness():
    receipt = positive(completeness=trace(dropped=1))
    assert receipt.status == REENTRY_OBSERVED
    assert receipt.trace_complete is False
    assert "DROPPED_EVENTS_NONZERO" in receipt.trace_incompleteness_reasons


def test_aborted_window_is_unknown():
    value = recorder(runtime="runtime:aborted", process="pid:aborted", ticks=(10, 20))
    receipt = value.abort(reason_ref="abort:runner-stop", reason_sha256=J)
    validate_reentry_observation_window(receipt)
    assert receipt.status == REENTRY_OBSERVATION_UNKNOWN
    assert receipt.trace_incompleteness_reasons == ("WINDOW_ABORTED",)


def test_reentry_must_match_task_input_prestate_and_executor():
    value = recorder()
    with pytest.raises(ReentryObservationError, match="task_id"):
        value.observe_reentry(
            reentry_ref="reentry:bad-task", reentry_sha256=I, source_sequence=101,
            task_id="task:other", task_input_sha256=F, pre_state_sha256=D, task_executor_sha256=E,
        )
    value = recorder()
    with pytest.raises(ReentryObservationError, match="task_input_sha256"):
        value.observe_reentry(
            reentry_ref="reentry:bad-input", reentry_sha256=I, source_sequence=101,
            task_id="task:wp900:g8:mechanism", task_input_sha256="0"*64,
            pre_state_sha256=D, task_executor_sha256=E,
        )
    value = recorder()
    with pytest.raises(ReentryObservationError, match="pre_state_sha256"):
        value.observe_reentry(
            reentry_ref="reentry:bad-state", reentry_sha256=I, source_sequence=101,
            task_id="task:wp900:g8:mechanism", task_input_sha256=F,
            pre_state_sha256="0"*64, task_executor_sha256=E,
        )
    value = recorder()
    with pytest.raises(ReentryObservationError, match="task_executor_sha256"):
        value.observe_reentry(
            reentry_ref="reentry:bad-executor", reentry_sha256=I, source_sequence=101,
            task_id="task:wp900:g8:mechanism", task_input_sha256=F,
            pre_state_sha256=D, task_executor_sha256="0"*64,
        )


def test_reentry_sequence_must_be_inside_captured_trace_range():
    value = recorder()
    value.observe_reentry(
        reentry_ref="reentry:outside", reentry_sha256=I, source_sequence=999,
        task_id="task:wp900:g8:mechanism", task_input_sha256=F,
        pre_state_sha256=D, task_executor_sha256=E,
    )
    with pytest.raises(ReentryObservationError, match="outside captured trace range"):
        value.close_complete(
            terminal_ref="terminal:task-complete", terminal_evidence_sha256=J,
            post_state_sha256=K, trace_completeness=trace(),
        )


def test_pair_fails_closed_on_pre_state_executor_filter_or_clock_mismatch():
    observed = positive()
    cases = [
        ("pre_state_sha256", negative(pre_state="0"*64)),
        ("task_executor_sha256", negative(executor="0"*64)),
    ]
    for field, other in cases:
        with pytest.raises(ReentryObservationError, match=field):
            bind_matched_reentry_mechanism(
                arm_a=observed, arm_b=other, provenance_refs=("prov:mismatch",)
            )


def test_unknown_arm_makes_pair_unknown():
    candidate = bind_matched_reentry_mechanism(
        arm_a=positive(),
        arm_b=negative(completeness=trace(dropped=1)),
        provenance_refs=("prov:unknown",),
    )
    assert candidate.classification == MECHANISM_COMPARISON_UNKNOWN


def test_equal_observations_do_not_claim_difference():
    candidate = bind_matched_reentry_mechanism(
        arm_a=positive(runtime="runtime:a", process="pid:a"),
        arm_b=positive(runtime="runtime:b", process="pid:b"),
        provenance_refs=("prov:equal",),
    )
    assert candidate.classification == NO_MECHANISM_REENTRY_DIFFERENCE


def test_direct_receipt_construction_lacks_factory_origin():
    valid = negative()
    forged = ReentryObservationWindowReceipt(
        window_id=valid.window_id,
        identity=valid.identity,
        opportunity_sha256=valid.opportunity_sha256,
        terminal_evidence_sha256=valid.terminal_evidence_sha256,
        post_state_sha256=valid.post_state_sha256,
        trace_completeness=valid.trace_completeness,
        trace_complete=valid.trace_complete,
        trace_incompleteness_reasons=valid.trace_incompleteness_reasons,
        events=valid.events,
        status=valid.status,
        provenance_refs=valid.provenance_refs,
    )
    with pytest.raises(ReentryObservationError, match="lacks recorder origin"):
        validate_reentry_observation_window(forged)


def test_candidate_keeps_all_higher_credits_zero():
    candidate = bind_matched_reentry_mechanism(
        arm_a=positive(), arm_b=negative(), provenance_refs=("prov:scope",)
    )
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
