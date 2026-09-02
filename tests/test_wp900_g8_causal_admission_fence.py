import dataclasses
import inspect

import pytest

from frankenstein2.gwt_reentry_causal_admission import (
    NEGATIVE_ABSENCE_CONTRADICTED,
    NEGATIVE_ABSENCE_UNPROVEN,
    SOURCE_EVENT_GWT_REENTRY,
    SOURCE_EVENT_OTHER,
    IndependentEventSourceRangeRecorder,
    IndependentRangeError,
    admit_reentry_observation,
    admit_reentry_observation_with_independent_range,
    validate_independent_event_source_range,
)
from frankenstein2.gwt_reentry_observation_window import (
    NO_REENTRY_OBSERVED,
    ReentryObservationIdentity,
    ReentryObservationWindowRecorder,
)
from test_wp900_g8_reentry_observation_window import identity, negative, runtime_witness

SOURCE = "a" * 64
BOOT = "b" * 64
CONTEXT = "c" * 64
TASK_INPUT = "d" * 64
PRE_STATE = "e" * 64
EXECUTOR = "f" * 64
PROTOCOL = "1" * 64
REENTRY_KEY = "2" * 64
REENTRY_BINDING = "3" * 64
TRACE_SOURCE = "4" * 64
FILTER = "5" * 64
CLOCK_MAP = "6" * 64
OPPORTUNITY = "7" * 64
TERMINAL = "8" * 64
POST_STATE = "9" * 64
RAW_TRACE = "0" * 64
CONTROL_RUNTIME = "runtime:control"
CONTROL_PROCESS = "pid:200:start:1"


def _caller_asserted_complete_negative(*, raw_trace_sha256=RAW_TRACE):
    ticks = iter((10, 30))
    candidate_identity = ReentryObservationIdentity(
        exact_source_sha256=SOURCE,
        boot_id_sha256=BOOT,
        execution_context_sha256=CONTEXT,
        task_id="task:wp900:g8:negative-fence",
        task_input_sha256=TASK_INPUT,
        pre_state_sha256=PRE_STATE,
        task_executor_sha256=EXECUTOR,
        observation_protocol_sha256=PROTOCOL,
        expected_reentry_key_sha256=REENTRY_KEY,
        expected_reentry_binding_sha256=REENTRY_BINDING,
        expected_recipient_cell_id="G1",
        trace_source_sha256=TRACE_SOURCE,
        filter_schema_sha256=FILTER,
        clock_domain="CLOCK_MONOTONIC_RAW",
        clock_mapping_sha256=CLOCK_MAP,
        observer_identity="observer:wp900:g8:test",
        runtime_instance_id=CONTROL_RUNTIME,
        process_identity="pid:control",
        provenance_refs=("prov:test-identity",),
    )
    recorder = ReentryObservationWindowRecorder(
        window_id="window:caller-asserted-control",
        identity=candidate_identity,
        opportunity_ref="opportunity:task-terminal",
        opportunity_sha256=OPPORTUNITY,
        monotonic_ns=lambda: next(ticks),
        provenance_refs=("prov:test-window",),
    )
    return recorder.close_with_trace(
        terminal_ref="terminal:task-complete",
        terminal_evidence_sha256=TERMINAL,
        post_state_sha256=POST_STATE,
        observer_started_monotonic_ns=1,
        observer_finalized_monotonic_ns=40,
        source_sequence_start=1000,
        source_sequence_end=1010,
        captured_sequence_start=1000,
        captured_sequence_end=1010,
        sequence_gap_count=0,
        dropped_event_count=0,
        overflow_count=0,
        raw_trace_sha256=raw_trace_sha256,
        filter_schema_sha256=FILTER,
        clock_domain="CLOCK_MONOTONIC_RAW",
        clock_mapping_sha256=CLOCK_MAP,
        finalized=True,
        provenance_refs=("prov:caller-asserted-complete",),
    )


def _source_range(*, include_matching_witness: bool):
    witness = runtime_witness(runtime=CONTROL_RUNTIME, process=CONTROL_PROCESS)
    expected_identity = identity(
        runtime=CONTROL_RUNTIME,
        process=CONTROL_PROCESS,
        expected=witness,
    )
    recorder = IndependentEventSourceRangeRecorder(
        trace_source_sha256=expected_identity.trace_source_sha256,
        filter_schema_sha256=expected_identity.filter_schema_sha256,
        clock_domain=expected_identity.clock_domain,
        clock_mapping_sha256=expected_identity.clock_mapping_sha256,
        observer_identity="source-tap:wp900:g8:test",
        observer_started_monotonic_ns=1,
        window_start_monotonic_ns=11,
        provenance_refs=("prov:structural-source-tap",),
    )
    for offset, sequence in enumerate(range(1000, 1011), start=1):
        recorder.observe(
            source_sequence=sequence,
            observed_monotonic_ns=11 + offset,
            payload_sha256=f"{sequence:064x}",
            runtime_witness=witness if include_matching_witness and sequence == 1005 else None,
        )
    source_range = recorder.seal(
        window_end_monotonic_ns=31,
        observer_finalized_monotonic_ns=40,
        provenance_refs=("prov:structural-range-seal",),
    )
    return witness, source_range


def _negative_for(source_range, witness):
    return negative(
        runtime=CONTROL_RUNTIME,
        process=CONTROL_PROCESS,
        expected=witness,
        raw_trace_sha256=source_range.raw_trace_sha256,
    )


def test_structurally_perfect_caller_trace_cannot_mint_causal_negative_absence():
    observation = _caller_asserted_complete_negative()
    assert observation.status == NO_REENTRY_OBSERVED
    assert observation.trace_complete is True

    admitted = admit_reentry_observation(observation)
    assert admitted.admission_status == NEGATIVE_ABSENCE_UNPROVEN
    assert admitted.causal_positive_credit == 0
    assert admitted.causal_negative_credit == 0
    assert admitted.independent_negative_range_authority is False
    assert admitted.independent_range_sha256 is None
    assert admitted.semantic_gwt_runtime_credit == 0
    assert admitted.jspace_runtime_credit == 0
    assert admitted.whole_system_acceptance is False


def test_range_recorder_api_has_no_caller_selected_gwt_classification_metadata():
    params = set(inspect.signature(IndependentEventSourceRangeRecorder.observe).parameters)
    assert params == {
        "self",
        "source_sequence",
        "observed_monotonic_ns",
        "payload_sha256",
        "runtime_witness",
    }
    assert {
        "event_kind",
        "canonical_reentry_key_sha256",
        "binding_sha256",
        "recipient_cell_id",
        "reentry_observed",
        "expected_result",
    }.isdisjoint(params)


def test_source_event_gwt_classification_is_derived_from_factory_valid_runtime_witness():
    witness, source_range = _source_range(include_matching_witness=True)
    matching = source_range.events[5]
    other = source_range.events[4]

    assert matching.event_kind == SOURCE_EVENT_GWT_REENTRY
    assert matching.canonical_reentry_key_sha256 == witness.canonical_reentry_key
    assert matching.binding_sha256 == witness.binding_sha256
    assert matching.recipient_cell_id == witness.recipient_cell_id
    assert other.event_kind == SOURCE_EVENT_OTHER
    assert other.canonical_reentry_key_sha256 is None


def test_same_caller_self_minted_complete_range_still_has_zero_negative_causal_credit():
    witness, source_range = _source_range(include_matching_witness=False)
    observation = _negative_for(source_range, witness)

    validate_independent_event_source_range(source_range)
    admitted = admit_reentry_observation_with_independent_range(observation, source_range)

    assert admitted.admission_status == NEGATIVE_ABSENCE_UNPROVEN
    assert admitted.causal_positive_credit == 0
    assert admitted.causal_negative_credit == 0
    assert admitted.independent_negative_range_authority is False
    assert admitted.independent_range_sha256 == source_range.sha256()
    assert admitted.blocker == "TARGET_SOURCE_INDEPENDENCE_BINDING_NOT_PROVEN"
    assert admitted.semantic_gwt_runtime_credit == 0
    assert admitted.jspace_runtime_credit == 0
    assert admitted.whole_system_acceptance is False


def test_caller_omission_cannot_hide_factory_valid_matching_witness_in_source_range():
    witness, source_range = _source_range(include_matching_witness=True)
    observation = _negative_for(source_range, witness)
    assert observation.status == NO_REENTRY_OBSERVED
    assert observation.trace_complete is True

    admitted = admit_reentry_observation_with_independent_range(observation, source_range)

    assert admitted.admission_status == NEGATIVE_ABSENCE_CONTRADICTED
    assert admitted.causal_positive_credit == 0
    assert admitted.causal_negative_credit == 0
    assert admitted.independent_negative_range_authority is False
    assert admitted.blocker == "MATCHING_REENTRY_PRESENT_IN_SOURCE_RANGE_CANDIDATE"


def test_forged_runtime_witness_cannot_classify_source_event_as_gwt_reentry():
    witness = runtime_witness(runtime=CONTROL_RUNTIME, process=CONTROL_PROCESS)
    forged = dataclasses.replace(witness, _factory_seal=None, _factory_payload_sha256=None)
    expected_identity = identity(runtime=CONTROL_RUNTIME, process=CONTROL_PROCESS, expected=witness)
    recorder = IndependentEventSourceRangeRecorder(
        trace_source_sha256=expected_identity.trace_source_sha256,
        filter_schema_sha256=expected_identity.filter_schema_sha256,
        clock_domain=expected_identity.clock_domain,
        clock_mapping_sha256=expected_identity.clock_mapping_sha256,
        observer_identity="source-tap:forged-witness-test",
        observer_started_monotonic_ns=1,
        window_start_monotonic_ns=11,
        provenance_refs=("prov:forged-witness-test",),
    )
    with pytest.raises(IndependentRangeError, match="runtime witness origin"):
        recorder.observe(
            source_sequence=1000,
            observed_monotonic_ns=12,
            payload_sha256="1" * 64,
            runtime_witness=forged,
        )


def test_unsealed_range_object_cannot_act_as_source_range_evidence():
    witness, source_range = _source_range(include_matching_witness=False)
    forged = dataclasses.replace(source_range, _factory_seal=None, _factory_payload_sha256=None)

    with pytest.raises(IndependentRangeError, match="lacks recorder origin"):
        validate_independent_event_source_range(forged)

    observation = _negative_for(source_range, witness)
    with pytest.raises(IndependentRangeError, match="lacks recorder origin"):
        admit_reentry_observation_with_independent_range(observation, forged)


def test_source_recorder_refuses_sequence_gaps():
    recorder = IndependentEventSourceRangeRecorder(
        trace_source_sha256=TRACE_SOURCE,
        filter_schema_sha256=FILTER,
        clock_domain="CLOCK_MONOTONIC_RAW",
        clock_mapping_sha256=CLOCK_MAP,
        observer_identity="source-tap:gap-test",
        observer_started_monotonic_ns=1,
        window_start_monotonic_ns=10,
        provenance_refs=("prov:gap-test",),
    )
    recorder.observe(
        source_sequence=1000,
        observed_monotonic_ns=11,
        payload_sha256="1" * 64,
    )
    with pytest.raises(IndependentRangeError, match="contiguous"):
        recorder.observe(
            source_sequence=1002,
            observed_monotonic_ns=12,
            payload_sha256="2" * 64,
        )
