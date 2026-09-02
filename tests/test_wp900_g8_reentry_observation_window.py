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


def positive(*, runtime="runtime:a", process="pid:1", pre_state=D, executor=E):
    value = recorder(runtime=runtime, process=process, pre_state=pre_state, executor=executor)
    value.observe_reentry(reentry_ref="reentry:observed", reentry_sha256=I)
    return value.close_complete(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=J,
        post_state_sha256=K,
        provenance_refs=("prov:complete",),
    )


def negative(*, runtime="runtime:b", process="pid:2", pre_state=D, executor=E):
    value = recorder(runtime=runtime, process=process, pre_state=pre_state, executor=executor, ticks=(11, 31))
    return value.close_complete(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=J,
        post_state_sha256=K,
        provenance_refs=("prov:complete-negative",),
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


def test_g8_positive_and_complete_negative_are_derived_from_events_not_labels():
    observed = positive()
    absent = negative()

    validate_reentry_observation_window(observed)
    validate_reentry_observation_window(absent)
    assert observed.status == REENTRY_OBSERVED
    assert absent.status == NO_REENTRY_OBSERVED

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
    receipt = would_be_control.close_complete(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=J,
        post_state_sha256=K,
    )
    assert receipt.status == REENTRY_OBSERVED
    assert any(event.evidence_ref == "reentry:unexpected-control-event" for event in receipt.events)


def test_g8_incomplete_window_is_unknown_not_no_reentry():
    value = recorder(runtime="runtime:aborted", process="pid:aborted", ticks=(10, 20))
    receipt = value.abort(reason_ref="abort:runner-stop", reason_sha256=J)
    validate_reentry_observation_window(receipt)
    assert receipt.status == REENTRY_OBSERVATION_UNKNOWN

    candidate = bind_matched_reentry_mechanism(
        arm_a=positive(),
        arm_b=receipt,
        provenance_refs=("prov:unknown-pair",),
    )
    assert candidate.classification == MECHANISM_COMPARISON_UNKNOWN


def test_g8_pair_fails_closed_on_pre_state_or_executor_mismatch():
    observed = positive()
    wrong_state = negative(pre_state="6" * 64)
    with pytest.raises(ReentryObservationError, match="pre_state_sha256"):
        bind_matched_reentry_mechanism(
            arm_a=observed,
            arm_b=wrong_state,
            provenance_refs=("prov:bad-state",),
        )

    wrong_executor = negative(executor="7" * 64)
    with pytest.raises(ReentryObservationError, match="task_executor_sha256"):
        bind_matched_reentry_mechanism(
            arm_a=observed,
            arm_b=wrong_executor,
            provenance_refs=("prov:bad-executor",),
        )


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
