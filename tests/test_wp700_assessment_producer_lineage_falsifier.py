"""REVIEW_ONLY executable falsifier for F2-WP-700 generation 1.

This test changes no production source and takes no WP700 mutation authority. It asks
whether a downstream consumer can distinguish the deterministic assess_retina_transition()
result from a directly constructed RetinaAssessment that reuses exact current signal/policy
identities but rewrites the measured outcome into a percept-event candidate.
"""

import pytest

from frankenstein2.retina_pipeline import (
    RetinaAssessment,
    RetinaFrameSignal,
    RetinaPipelineError,
    RetinaPolicy,
    assess_retina_transition,
)

A = "a" * 64
B = "b" * 64


def test_direct_assessment_cannot_turn_rejected_frame_into_percept_candidate():
    previous = RetinaFrameSignal(
        frame_id="f0",
        stream_id="camera-0",
        generation=0,
        captured_monotonic_ns=100,
        frame_sha256=A,
        continuity_epoch="epoch-1",
        quality_micros=900_000,
        delta_micros=None,
        delta_reference_frame_id=None,
        delta_reference_frame_sha256=None,
        provenance_refs=("capture:f0",),
    )
    current = RetinaFrameSignal(
        frame_id="f1",
        stream_id="camera-0",
        generation=1,
        captured_monotonic_ns=200,
        frame_sha256=B,
        continuity_epoch="epoch-1",
        quality_micros=1,
        delta_micros=900_000,
        delta_reference_frame_id=previous.frame_id,
        delta_reference_frame_sha256=previous.frame_sha256,
        provenance_refs=("capture:f1", "measurement:l0"),
    )
    policy = RetinaPolicy(
        policy_id="retina-policy-1",
        generation=1,
        min_quality_micros=500_000,
        salient_delta_micros=200_000,
        max_interframe_gap_ns=1_000,
        provenance_refs=("policy:owner",),
    )

    canonical = assess_retina_transition(
        assessment_id="canonical",
        current=current,
        expected_current_signal_sha256=current.sha256(),
        previous=previous,
        expected_previous_signal_sha256=previous.sha256(),
        policy=policy,
        expected_policy_sha256=policy.sha256(),
        provenance_refs=("producer:assess_retina_transition",),
    )
    assert canonical.quality_status == "QUALITY_REJECTED"
    assert canonical.percept_event_candidate is False

    # Same exact signal and policy identities, but a direct constructor claims the
    # opposite measured result. The WP700 output boundary should fail closed rather
    # than allow this object to self-attest producer/evaluator lineage.
    with pytest.raises(RetinaPipelineError, match="producer|lineage|assessment"):
        RetinaAssessment(
            assessment_id="forged-direct-constructor",
            current_frame_id=current.frame_id,
            current_frame_sha256=current.frame_sha256,
            current_signal_sha256=current.sha256(),
            previous_frame_id=previous.frame_id,
            previous_frame_sha256=previous.frame_sha256,
            previous_signal_sha256=previous.sha256(),
            policy_id=policy.policy_id,
            policy_generation=policy.generation,
            policy_sha256=policy.sha256(),
            quality_status="QUALITY_PASS",
            delta_status="SALIENT_DELTA",
            continuity_status="CONTINUOUS",
            percept_event_candidate=True,
            event_reason="QUALITY_PASS_SALIENT_DELTA_CONTINUOUS",
            provenance_refs=("forged:direct-constructor",),
        )
