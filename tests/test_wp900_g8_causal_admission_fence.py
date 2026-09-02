from frankenstein2.gwt_reentry_causal_admission import (
    NEGATIVE_ABSENCE_UNPROVEN,
    admit_reentry_observation,
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


def _caller_asserted_complete_negative():
    ticks = iter((10, 30))
    identity = ReentryObservationIdentity(
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
    recorder = ReentryObservationWindowRecorder(
        window_id="window:caller-asserted-control",
        identity=identity,
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
        raw_trace_sha256=RAW_TRACE,
        filter_schema_sha256=FILTER,
        clock_domain="CLOCK_MONOTONIC_RAW",
        clock_mapping_sha256=CLOCK_MAP,
        finalized=True,
        provenance_refs=("prov:caller-asserted-complete",),
    )


def test_structurally_perfect_caller_trace_cannot_mint_causal_negative_absence():
    observation = _caller_asserted_complete_negative()

    # The lower-level candidate preserves what the caller said structurally.
    assert observation.status == NO_REENTRY_OBSERVED
    assert observation.trace_complete is True

    # The causal admission boundary refuses to turn that self-attested absence
    # into negative causal evidence without an independent range authority.
    admitted = admit_reentry_observation(observation)
    assert admitted.admission_status == NEGATIVE_ABSENCE_UNPROVEN
    assert admitted.causal_positive_credit == 0
    assert admitted.causal_negative_credit == 0
    assert admitted.independent_negative_range_authority is False
    assert admitted.blocker == "INDEPENDENT_NEGATIVE_COMPLETE_RANGE_AUTHORITY_MISSING"
    assert admitted.semantic_gwt_runtime_credit == 0
    assert admitted.jspace_runtime_credit == 0
    assert admitted.whole_system_acceptance is False


def test_no_boolean_or_metadata_escape_hatch_exists_on_admission_api():
    import inspect

    parameters = set(inspect.signature(admit_reentry_observation).parameters)
    assert parameters == {"observation"}
