import hashlib
import json
import runpy
from pathlib import Path

import pytest

from frankenstein2.gwt_independent_reentry_evidence import (
    ConditionBlindReentryObservation,
    GwtIndependentReentryEvidenceError,
    IndependentReentryOutcomeReadback,
    REENTRY_NOT_OBSERVED,
    REENTRY_OBSERVATION_UNKNOWN,
    REENTRY_OBSERVED,
)
from frankenstein2.gwt_semantic_runtime_readback import (
    SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE,
    SEMANTIC_DIFFERENCE_OBSERVED,
    WP900_MATCHED_TASK_SCHEMA,
    bind_semantic_causal_readback,
)

_G6 = runpy.run_path(
    str(Path(__file__).with_name("test_wp900_g6_semantic_runtime_readback.py"))
)
make_contract = _G6["make_contract"]
sha256_bytes = _G6["sha256_bytes"]
D = _G6["D"]
E = _G6["E"]

OBSERVER_SOURCE = "4" * 64
OPEN_SHA = "5" * 64
REENTRY_SHA = "6" * 64
CLOSE_SHA = "7" * 64


def canonical_stream(events):
    return json.dumps(
        events,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def event(kind, ns, digest):
    return {
        "kind": kind,
        "observed_monotonic_ns": ns,
        "event_sha256": digest,
    }


def contract():
    intervention_payload = b'{"cell_id":"G1","status":"COMPLETE"}'
    control_payload = b'{"probe_id":"probe:wp900-g8","status":"QUIET"}'
    return make_contract(
        sha256_bytes(intervention_payload),
        sha256_bytes(control_payload),
    )


def observe(contract_candidate, events, *, runtime_id="runtime:wp900:g8:observer"):
    return ConditionBlindReentryObservation.observe_event_stream(
        raw_event_stream=canonical_stream(events),
        observer_identity="observer:wp900:g8:condition-blind",
        observer_source_sha256=OBSERVER_SOURCE,
        runtime_instance_id=runtime_id,
        exact_source_sha256=contract_candidate.exact_source_sha256,
        boot_id_sha256=contract_candidate.boot_id_sha256,
        execution_context_sha256=contract_candidate.execution_context_sha256,
        provenance_refs=("prov:wp900:g8:condition-blind-observer",),
    )


def bind(contract_candidate, observation, condition):
    return IndependentReentryOutcomeReadback.bind_to_contract(
        contract_candidate=contract_candidate,
        observation=observation,
        condition=condition,
        task_id="task:wp900:g8:matched-reentry",
        task_schema=WP900_MATCHED_TASK_SCHEMA,
        provenance_refs=("prov:wp900:g8:late-arm-bind",),
    )


def test_g8_same_raw_observation_has_same_result_under_later_arm_label_swap():
    candidate = contract()
    raw_events = [
        event("WINDOW_OPEN", 100, OPEN_SHA),
        event("REENTRY", 110, REENTRY_SHA),
        event("WINDOW_CLOSE", 120, CLOSE_SHA),
    ]
    observation = observe(candidate, raw_events)

    intervention = bind(candidate, observation, "INTERVENTION_BROADCAST")
    control = bind(candidate, observation, "CONTROL_NO_BROADCAST")

    assert observation.status == REENTRY_OBSERVED
    assert observation.derived_reentry_observed is True
    assert intervention.reentry_observed is True
    assert control.reentry_observed is True
    assert intervention.semantic_value() == control.semantic_value()
    assert intervention.semantic_value() == {
        "predicate": "REENTRY_OBSERVED",
        "observed": True,
    }
    assert intervention.observation_sha256 == observation.sha256()
    assert control.observation_sha256 == observation.sha256()


def test_g8_control_false_without_complete_observation_window_remains_unknown():
    candidate = contract()
    observation = observe(
        candidate,
        [event("WINDOW_OPEN", 100, OPEN_SHA)],
    )

    assert observation.status == REENTRY_OBSERVATION_UNKNOWN
    assert observation.derived_reentry_observed is None
    with pytest.raises(GwtIndependentReentryEvidenceError, match="UNKNOWN"):
        bind(candidate, observation, "CONTROL_NO_BROADCAST")


def test_g8_intervention_label_cannot_force_true_without_reentry_event():
    candidate = contract()
    observation = observe(
        candidate,
        [
            event("WINDOW_OPEN", 100, OPEN_SHA),
            event("WINDOW_CLOSE", 120, CLOSE_SHA),
        ],
    )

    outcome = bind(candidate, observation, "INTERVENTION_BROADCAST")

    assert observation.status == REENTRY_NOT_OBSERVED
    assert observation.derived_reentry_observed is False
    assert outcome.reentry_observed is False


def test_g8_control_label_cannot_suppress_observed_reentry_event():
    candidate = contract()
    observation = observe(
        candidate,
        [
            event("WINDOW_OPEN", 100, OPEN_SHA),
            event("REENTRY", 110, REENTRY_SHA),
            event("WINDOW_CLOSE", 120, CLOSE_SHA),
        ],
    )

    outcome = bind(candidate, observation, "CONTROL_NO_BROADCAST")

    assert observation.status == REENTRY_OBSERVED
    assert outcome.reentry_observed is True


def test_g8_missing_tail_coverage_cannot_be_relabelled_as_absence():
    candidate = contract()
    observation = observe(
        candidate,
        [event("WINDOW_OPEN", 100, OPEN_SHA)],
    )

    assert observation.window_end_monotonic_ns is None
    assert observation.status == REENTRY_OBSERVATION_UNKNOWN
    for condition in ("INTERVENTION_BROADCAST", "CONTROL_NO_BROADCAST"):
        with pytest.raises(GwtIndependentReentryEvidenceError, match="UNKNOWN"):
            bind(candidate, observation, condition)


def test_g8_rejects_condition_or_arm_injection_into_observer_stream():
    candidate = contract()
    raw = canonical_stream(
        [
            {
                "kind": "WINDOW_OPEN",
                "observed_monotonic_ns": 100,
                "event_sha256": OPEN_SHA,
                "condition": "CONTROL_NO_BROADCAST",
            }
        ]
    )

    with pytest.raises(GwtIndependentReentryEvidenceError, match="exactly kind"):
        ConditionBlindReentryObservation.observe_event_stream(
            raw_event_stream=raw,
            observer_identity="observer:wp900:g8:condition-blind",
            observer_source_sha256=OBSERVER_SOURCE,
            runtime_instance_id="runtime:wp900:g8:observer",
            exact_source_sha256=candidate.exact_source_sha256,
            boot_id_sha256=candidate.boot_id_sha256,
            execution_context_sha256=candidate.execution_context_sha256,
            provenance_refs=("prov:wp900:g8:injection-negative",),
        )


def test_g8_rejects_noncanonical_or_malformed_event_order():
    candidate = contract()
    noncanonical = json.dumps(
        [event("WINDOW_OPEN", 100, OPEN_SHA)],
        indent=2,
    ).encode("utf-8")

    with pytest.raises(GwtIndependentReentryEvidenceError, match="canonical JSON"):
        ConditionBlindReentryObservation.observe_event_stream(
            raw_event_stream=noncanonical,
            observer_identity="observer:wp900:g8:condition-blind",
            observer_source_sha256=OBSERVER_SOURCE,
            runtime_instance_id="runtime:wp900:g8:observer",
            exact_source_sha256=candidate.exact_source_sha256,
            boot_id_sha256=candidate.boot_id_sha256,
            execution_context_sha256=candidate.execution_context_sha256,
            provenance_refs=("prov:wp900:g8:noncanonical-negative",),
        )

    with pytest.raises(GwtIndependentReentryEvidenceError, match="first observer event"):
        observe(
            candidate,
            [event("REENTRY", 100, REENTRY_SHA)],
        )

    with pytest.raises(GwtIndependentReentryEvidenceError, match="final observer event"):
        observe(
            candidate,
            [
                event("WINDOW_OPEN", 100, OPEN_SHA),
                event("WINDOW_CLOSE", 110, CLOSE_SHA),
                event("REENTRY", 120, REENTRY_SHA),
            ],
        )


def test_g8_observation_identity_must_match_fresh_causal_contract():
    candidate = contract()
    observation = ConditionBlindReentryObservation.observe_event_stream(
        raw_event_stream=canonical_stream(
            [
                event("WINDOW_OPEN", 100, OPEN_SHA),
                event("WINDOW_CLOSE", 120, CLOSE_SHA),
            ]
        ),
        observer_identity="observer:wp900:g8:condition-blind",
        observer_source_sha256=OBSERVER_SOURCE,
        runtime_instance_id="runtime:wp900:g8:observer",
        exact_source_sha256="9" * 64,
        boot_id_sha256=candidate.boot_id_sha256,
        execution_context_sha256=candidate.execution_context_sha256,
        provenance_refs=("prov:wp900:g8:wrong-source",),
    )

    with pytest.raises(GwtIndependentReentryEvidenceError, match="exact-source"):
        bind(candidate, observation, "CONTROL_NO_BROADCAST")


def test_g8_condition_blind_pair_feeds_existing_semantic_comparator_with_zero_credit():
    candidate = contract()
    intervention_observation = observe(
        candidate,
        [
            event("WINDOW_OPEN", 100, "1" * 64),
            event("REENTRY", 110, "2" * 64),
            event("WINDOW_CLOSE", 120, "3" * 64),
        ],
        runtime_id="runtime:wp900:g8:intervention-observer",
    )
    control_observation = observe(
        candidate,
        [
            event("WINDOW_OPEN", 200, "a" * 64),
            event("WINDOW_CLOSE", 220, "b" * 64),
        ],
        runtime_id="runtime:wp900:g8:control-observer",
    )

    intervention = bind(
        candidate,
        intervention_observation,
        "INTERVENTION_BROADCAST",
    )
    control = bind(
        candidate,
        control_observation,
        "CONTROL_NO_BROADCAST",
    )
    result = bind_semantic_causal_readback(
        contract_candidate=candidate,
        intervention=intervention.to_semantic_arm(),
        control=control.to_semantic_arm(),
        provenance_refs=("prov:wp900:g8:semantic-bind",),
    )

    assert intervention.reentry_observed is True
    assert control.reentry_observed is False
    assert result.comparison_status == SEMANTIC_DIFFERENCE_OBSERVED
    assert result.classification == SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE
    assert result.repository_ci_credit == 0
    assert result.target_environment_component_runtime_credit == 0
    assert result.runtime_credit == 0
    assert result.gwt_runtime_credit == 0
    assert result.semantic_gwt_runtime_credit == 0
    assert result.jspace_runtime_credit == 0
    assert result.physical_grid10_credit == 0
    assert result.effect_credit == 0
    assert result.training_credit == 0
    assert result.completion_credit == 0
    assert result.whole_system_acceptance is False


def test_g8_stream_hash_binds_exact_canonical_bytes_without_claiming_historical_g4_identity():
    candidate = contract()
    raw = canonical_stream(
        [
            event("WINDOW_OPEN", 100, OPEN_SHA),
            event("WINDOW_CLOSE", 120, CLOSE_SHA),
        ]
    )
    observation = ConditionBlindReentryObservation.observe_event_stream(
        raw_event_stream=raw,
        observer_identity="observer:wp900:g8:condition-blind",
        observer_source_sha256=OBSERVER_SOURCE,
        runtime_instance_id="runtime:wp900:g8:fresh-observer",
        exact_source_sha256=candidate.exact_source_sha256,
        boot_id_sha256=candidate.boot_id_sha256,
        execution_context_sha256=candidate.execution_context_sha256,
        provenance_refs=("prov:wp900:g8:fresh-observation",),
    )

    assert observation.raw_event_stream_sha256 == hashlib.sha256(raw).hexdigest()
    assert observation.raw_event_stream_sha256 not in {
        candidate.runtime_witness_sha256,
        candidate.control_readback_sha256,
    }
    assert observation.repository_ci_credit == 0
    assert observation.target_environment_component_runtime_credit == 0
    assert observation.semantic_gwt_runtime_credit == 0
    assert observation.jspace_runtime_credit == 0
    assert observation.whole_system_acceptance is False
