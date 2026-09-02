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
N = "8" * 64
O = "9" * 64


def identity(*, runtime="runtime:a", process="pid:1", pre_state=D, executor=E):
    return ReentryObservationIdentity(
        exact_source_sha256=A,
        boot_id_sha256=B,
        execution_context_sha256=C,
        task_id="task:wp900:g8:mechanism",
        task_input_sha256=F,
        pre_state_sha256=pre_state,
        task_executor_sha256=executor,
        observation_protocol_sha256=G,
        trace_source_sha256=L,
        filter_schema_sha256=M,
        clock_domain="CLOCK_MONOTONIC_RAW",
        clock_mapping_sha256=N,
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


def trace_kwargs(**overrides):
    values = {
        "observer_started_monotonic_ns": 1,
        "observer_finalized_monotonic_ns": 40,
        "source_sequence_start": 100,
        "source_sequence_end": 110,
        "captured_sequence_start": 100,
        "captured_sequence_end": 110,
        "sequence_gap_count": 0,
        "dropped_event_count": 0,
        "overflow_count": 0,
        "raw_trace_sha256": O,
        "filter_schema_sha256": M,
        "clock_domain": "CLOCK_MONOTONIC_RAW",
        "clock_mapping_sha256": N,
        "finalized": True,
    }
    values.update(overrides)
    return values


def close(value, **trace_overrides):
    return value.close_with_trace(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=J,
        post_state_sha256=K,
        provenance_refs=("prov:complete",),
        **trace_kwargs(**trace_overrides),
    )


def positive(*, runtime="runtime:a", process="pid:1", pre_state=D, executor=E, **trace_overrides):
    value = recorder(runtime=runtime, process=process, pre_state=pre_state, executor=executor)
    value.observe_reentry(reentry_ref="reentry:observed", reentry_sha256=I)
    return close(value, **trace_overrides)


def negative(*, runtime="runtime:b", process="pid:2", pre_state=D, executor=E, **trace_overrides):
    value = recorder(runtime=runtime, process=process, pre_state=pre_state, executor=executor, ticks=(11, 31))
    return close(value, **trace_overrides)


def test_g8_observer_api_is_condition_blind_and_has_no_expected_boolean():
    init_params = set(inspect.signature(ReentryObservationWindowRecorder.__init__).parameters)
    observe_params = set(inspect.signature(ReentryObservationWindowRecorder.observe_reentry).parameters)
    close_params = set(inspect.signature(ReentryObservationWindowRecorder.close_with_trace).parameters)
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


def test_g8_positive_and_trace_complete_negative_derive_from_evidence_not_labels():
    observed = positive()
    absent = negative()

    validate_reentry_observation_window(observed)
    validate_reentry_observation_window(absent)
    assert observed.status == REENTRY_OBSERVED
    assert absent.status == NO_REENTRY_OBSERVED
    assert observed.trace_complete is True
    assert absent.trace_complete is True
    assert absent.trace_completeness.raw_trace_sha256 == O

    candidate = bind_matched_reentry_mechanism(
        arm_a=observed,
        arm_b=absent,
        provenance_refs=("prov:matched-pair",),
    )
    assert candidate.classification == MECHANISM_REENTRY_DIFFERENCE
    assert candidate.semantic_gwt_runtime_credit == 0
    assert candidate.jspace_runtime_credit == 0
    assert candidate.whole_system_acceptance is False


def test_g8_injected_reentry_cannot_false_green_as_control_absence():
    would_be_control = recorder(runtime="runtime:control", process="pid:control")
    would_be_control.observe_reentry(
        reentry_ref="reentry:unexpected-control-event",
        reentry_sha256=I,
    )
    receipt = close(would_be_control)
    assert receipt.status == REENTRY_OBSERVED
    assert any(event.evidence_ref == "reentry:unexpected-control-event" for event in receipt.events)


@pytest.mark.parametrize(
    "trace_overrides",
    [
        {"dropped_event_count": 1},
        {"overflow_count": 1},
        {"sequence_gap_count": 1},
        {"captured_sequence_end": 109},
        {"observer_started_monotonic_ns": 11},
        {"observer_finalized_monotonic_ns": 31},
        {"finalized": False},
    ],
)
def test_g8_negative_absence_is_unknown_if_trace_completeness_is_not_proven(trace_overrides):
    receipt = negative(**trace_overrides)
    validate_reentry_observation_window(receipt)
    assert receipt.status == REENTRY_OBSERVATION_UNKNOWN
    assert receipt.trace_complete is False

    candidate = bind_matched_reentry_mechanism(
        arm_a=positive(),
        arm_b=receipt,
        provenance_refs=("prov:incomplete-pair",),
    )
    assert candidate.classification == MECHANISM_COMPARISON_UNKNOWN


def test_g8_aborted_window_is_unknown_not_no_reentry():
    value = recorder(runtime="runtime:aborted", process="pid:aborted", ticks=(10, 20))
    receipt = value.abort(reason_ref="abort:runner-stop", reason_sha256=J)
    validate_reentry_observation_window(receipt)
    assert receipt.status == REENTRY_OBSERVATION_UNKNOWN
    assert receipt.trace_complete is False


def test_g8_pair_fails_closed_on_pre_state_or_executor_mismatch():
    observed = positive()
    wrong_state = negative(pre_state="0" * 64)
    with pytest.raises(ReentryObservationError, match="pre_state_sha256"):
        bind_matched_reentry_mechanism(
            arm_a=observed,
            arm_b=wrong_state,
            provenance_refs=("prov:bad-state",),
        )

    wrong_executor = negative(executor="b" * 64)
    with pytest.raises(ReentryObservationError, match="task_executor_sha256"):
        bind_matched_reentry_mechanism(
            arm_a=observed,
            arm_b=wrong_executor,
            provenance_refs=("prov:bad-executor",),
        )


def test_g8_close_fails_closed_on_filter_or_clock_identity_mismatch():
    value = recorder(runtime="runtime:filter", process="pid:filter", ticks=(10, 30))
    with pytest.raises(ReentryObservationError, match="filter schema"):
        close(value, filter_schema_sha256="c" * 64)

    value = recorder(runtime="runtime:clock", process="pid:clock", ticks=(10, 30))
    with pytest.raises(ReentryObservationError, match="clock domain"):
        close(value, clock_domain="CLOCK_BOOTTIME")


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
