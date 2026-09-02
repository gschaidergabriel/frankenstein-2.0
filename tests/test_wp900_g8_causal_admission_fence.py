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


def _identity():
    return ReentryObservationIdentity(
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
        runtime_instance_id="runtime:control",
        process_identity="pid:control",
        provenance_refs=("prov:test-identity",),
    )


def _caller_asserted_complete_negative(
    *,
    raw_trace_sha256=RAW_TRACE,
    source_sequence_start=1000,
    source_sequence_end=1010,
):
    ticks = iter((10, 30))
    recorder = ReentryObservationWindowRecorder(
        window_id="window:caller-asserted-control",
        identity=_identity(),
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
        source_sequence_start=source_sequence_start,
        source_sequence_end=source_sequence_end,
        captured_sequence_start=source_sequence_start,
        captured_sequence_end=source_sequence_end,
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


def _range_candidate(*, include_matching_reentry):
    recorder = IndependentEventSourceRangeRecorder(
        trace_source_sha256=TRACE_SOURCE,
        filter_schema_sha256=FILTER,
        clock_domain="CLOCK_MONOTONIC_RAW",
        clock_mapping_sha256=CLOCK_MAP,
        observer_identity="source-tap:wp900:g8:test",
        observer_started_monotonic_ns=1,
        window_start_monotonic_ns=10,
        provenance_refs=("prov:source-range-candidate",),
    )
    for offset, sequence in enumerate(range(1000, 1011), start=1):
        if include_matching_reentry and sequence == 1005:
            recorder.observe(
                source_sequence=sequence,
                observed_monotonic_ns=10 + offset,
                event_kind=SOURCE_EVENT_GWT_REENTRY,
                payload_sha256="a" * 64,
                canonical_reentry_key_sha256=REENTRY_KEY,
                binding_sha256=REENTRY_BINDING,
                recipient_cell_id="G1",
            )
        else:
            recorder.observe(
                source_sequence=sequence,
                observed_monotonic_ns=10 + offset,
                event_kind=SOURCE_EVENT_OTHER,
                payload_sha256=f"{sequence:064x}"[-64:],
            )
    return recorder.seal(
        window_end_monotonic_ns=30,
        observer_finalized_monotonic_ns=40,
        provenance_refs=("prov:range-seal",),
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
    assert admitted.blocker == "INDEPENDENT_NEGATIVE_COMPLETE_RANGE_AUTHORITY_MISSING"
    assert admitted.semantic_gwt_runtime_credit == 0
    assert admitted.jspace_runtime_credit == 0
    assert admitted.whole_system_acceptance is False


def test_no_boolean_or_metadata_escape_hatch_exists_on_legacy_admission_api():
    assert set(inspect.signature(admit_reentry_observation).parameters) == {"observation"}


def test_public_self_minted_range_cannot_unlock_negative_causal_credit():
    """Regression for the G8 FACTORY_ORIGIN != INDEPENDENCE falsifier."""
    source_range = _range_candidate(include_matching_reentry=False)
    observation = _caller_asserted_complete_negative(raw_trace_sha256=source_range.raw_trace_sha256)

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


def test_caller_omission_is_conservatively_contradicted_when_range_candidate_contains_match():
    source_range = _range_candidate(include_matching_reentry=True)

    # The condition-aware caller copies the structural range digest but omits
    # the matching event from its own lower-level observation candidate.
    observation = _caller_asserted_complete_negative(raw_trace_sha256=source_range.raw_trace_sha256)
    assert observation.status == NO_REENTRY_OBSERVED
    assert observation.trace_complete is True

    admitted = admit_reentry_observation_with_independent_range(observation, source_range)

    assert admitted.admission_status == NEGATIVE_ABSENCE_CONTRADICTED
    assert admitted.causal_positive_credit == 0
    assert admitted.causal_negative_credit == 0
    # The range can falsify the negative candidate conservatively, but its
    # public factory origin still does not prove operational independence.
    assert admitted.independent_negative_range_authority is False
    assert admitted.blocker == "MATCHING_REENTRY_PRESENT_IN_SOURCE_RANGE_CANDIDATE"


def test_unsealed_range_object_cannot_act_as_range_candidate():
    source_range = _range_candidate(include_matching_reentry=False)
    forged = dataclasses.replace(source_range, _factory_seal=None, _factory_payload_sha256=None)

    with pytest.raises(IndependentRangeError, match="lacks recorder origin"):
        validate_independent_event_source_range(forged)

    observation = _caller_asserted_complete_negative(raw_trace_sha256=source_range.raw_trace_sha256)
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
        event_kind=SOURCE_EVENT_OTHER,
        payload_sha256="1" * 64,
    )
    with pytest.raises(IndependentRangeError, match="contiguous"):
        recorder.observe(
            source_sequence=1002,
            observed_monotonic_ns=12,
            event_kind=SOURCE_EVENT_OTHER,
            payload_sha256="2" * 64,
        )
