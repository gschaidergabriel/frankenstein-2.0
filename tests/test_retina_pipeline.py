from dataclasses import replace

import pytest

from frankenstein2.retina_pipeline import (
    RetinaFrameSignal,
    RetinaPipelineError,
    RetinaPolicy,
    assess_retina_transition,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64


def policy(**overrides):
    values = dict(policy_id="retina-policy-1", generation=1, min_quality_micros=500_000,
        salient_delta_micros=200_000, max_interframe_gap_ns=1_000,
        provenance_refs=("policy:owner",))
    values.update(overrides)
    return RetinaPolicy(**values)


def frame(frame_id, generation, *, sha=A, at=100, quality=900_000, delta=None,
          ref_id=None, ref_sha=None, stream="camera-0", epoch="epoch-1"):
    return RetinaFrameSignal(frame_id=frame_id, stream_id=stream, generation=generation,
        captured_monotonic_ns=at, frame_sha256=sha, continuity_epoch=epoch,
        quality_micros=quality, delta_micros=delta, delta_reference_frame_id=ref_id,
        delta_reference_frame_sha256=ref_sha,
        provenance_refs=("capture:ram", "measurement:l0"))


def assess(current, *, previous=None, pol=None, aid="assessment-1"):
    pol = pol or policy()
    return assess_retina_transition(assessment_id=aid, current=current,
        expected_current_signal_sha256=current.sha256(), previous=previous,
        expected_previous_signal_sha256=previous.sha256() if previous else None,
        policy=pol, expected_policy_sha256=pol.sha256(), provenance_refs=("wp700:test",))


def test_baseline_is_not_a_percept_event():
    out = assess(frame("f0", 0))
    assert (out.delta_status, out.continuity_status, out.percept_event_candidate, out.event_reason) == (
        "BASELINE", "BASELINE", False, "BASELINE_ONLY")


def test_continuous_salient_high_quality_change_emits_candidate_only():
    prev = frame("f0", 0, sha=A, at=100)
    cur = frame("f1", 1, sha=B, at=200, delta=300_000, ref_id="f0", ref_sha=A)
    out = assess(cur, previous=prev)
    assert (out.quality_status, out.delta_status, out.continuity_status) == (
        "QUALITY_PASS", "SALIENT_DELTA", "CONTINUOUS")
    assert out.percept_event_candidate is True
    payload = out.as_dict()
    assert payload["world_truth_authority"] == payload["effect_authority"] == "NONE"
    assert payload["raw_frame_present"] is False


def test_low_quality_suppresses_even_salient_delta():
    prev = frame("f0", 0, sha=A, at=100)
    cur = frame("f1", 1, sha=B, at=200, quality=499_999, delta=900_000, ref_id="f0", ref_sha=A)
    out = assess(cur, previous=prev)
    assert out.quality_status == "QUALITY_REJECTED"
    assert out.percept_event_candidate is False
    assert out.event_reason == "SUPPRESSED_LOW_QUALITY"


def test_small_delta_suppresses_event():
    prev = frame("f0", 0, sha=A, at=100)
    cur = frame("f1", 1, sha=B, at=200, delta=199_999, ref_id="f0", ref_sha=A)
    out = assess(cur, previous=prev)
    assert out.delta_status == "NO_SALIENT_DELTA"
    assert out.percept_event_candidate is False


@pytest.mark.parametrize(("kwargs", "expected"), [
    ({"stream": "camera-1"}, "BREAK_STREAM"),
    ({"epoch": "epoch-2"}, "BREAK_EPOCH"),
])
def test_stream_or_epoch_change_breaks_continuity(kwargs, expected):
    prev = frame("f0", 0, sha=A, at=100)
    cur = frame("f1", 1, sha=B, at=200, delta=900_000, ref_id="f0", ref_sha=A, **kwargs)
    out = assess(cur, previous=prev)
    assert out.continuity_status == expected
    assert out.percept_event_candidate is False


def test_generation_gap_breaks_continuity_without_minting_event():
    prev = frame("f0", 0, sha=A, at=100)
    cur = frame("f2", 2, sha=C, at=200, delta=900_000, ref_id="f0", ref_sha=A)
    out = assess(cur, previous=prev)
    assert out.continuity_status == "BREAK_GENERATION_GAP"
    assert out.percept_event_candidate is False


def test_time_gap_breaks_continuity():
    prev = frame("f0", 0, sha=A, at=100)
    cur = frame("f1", 1, sha=B, at=1_101, delta=900_000, ref_id="f0", ref_sha=A)
    out = assess(cur, previous=prev)
    assert out.continuity_status == "BREAK_TIME_GAP"
    assert out.percept_event_candidate is False


def test_stale_or_mismatched_delta_lineage_fails_closed():
    prev = frame("f0", 1, sha=A, at=200)
    stale = frame("f1", 1, sha=B, at=201, delta=500_000, ref_id="f0", ref_sha=A)
    with pytest.raises(RetinaPipelineError, match="generation must advance"):
        assess(stale, previous=prev)
    wrong_ref = frame("f1", 2, sha=B, at=300, delta=500_000, ref_id="other", ref_sha=A)
    with pytest.raises(RetinaPipelineError, match="reference frame id mismatch"):
        assess(wrong_ref, previous=prev)


def test_exact_signal_and_policy_digest_bindings_fail_closed():
    cur = frame("f0", 0)
    pol = policy()
    with pytest.raises(RetinaPipelineError, match="current signal digest mismatch"):
        assess_retina_transition(assessment_id="a", current=cur, expected_current_signal_sha256=C,
            policy=pol, expected_policy_sha256=pol.sha256(), provenance_refs=("test",))
    with pytest.raises(RetinaPipelineError, match="policy digest mismatch"):
        assess_retina_transition(assessment_id="a", current=cur,
            expected_current_signal_sha256=cur.sha256(), policy=pol,
            expected_policy_sha256=C, provenance_refs=("test",))


def test_delta_measurement_must_be_fully_bound_and_baseline_has_no_delta():
    with pytest.raises(RetinaPipelineError, match="all present or all absent"):
        frame("f1", 1, delta=1, ref_id="f0")
    cur = frame("f0", 0, delta=1, ref_id="older", ref_sha=B)
    with pytest.raises(RetinaPipelineError, match="baseline frame must not claim a delta"):
        assess(cur)


def test_concrete_type_boundary_and_output_invariant_fail_closed():
    class ForgedSignal(RetinaFrameSignal):
        pass
    base = frame("f0", 0)
    forged = ForgedSignal(frame_id=base.frame_id, stream_id=base.stream_id,
        generation=base.generation, captured_monotonic_ns=base.captured_monotonic_ns,
        frame_sha256=base.frame_sha256, continuity_epoch=base.continuity_epoch,
        quality_micros=base.quality_micros, delta_micros=None,
        delta_reference_frame_id=None, delta_reference_frame_sha256=None,
        provenance_refs=base.provenance_refs)
    pol = policy()
    with pytest.raises(RetinaPipelineError, match="concrete RetinaFrameSignal"):
        assess_retina_transition(assessment_id="a", current=forged,
            expected_current_signal_sha256=forged.sha256(), policy=pol,
            expected_policy_sha256=pol.sha256(), provenance_refs=("test",))
    with pytest.raises(RetinaPipelineError, match="must equal"):
        replace(assess(base), percept_event_candidate=True)


def test_provenance_is_canonicalized_and_duplicates_rejected():
    cur = RetinaFrameSignal(frame_id="f0", stream_id="cam", generation=0,
        captured_monotonic_ns=1, frame_sha256=A, continuity_epoch="e",
        quality_micros=1, delta_micros=None, delta_reference_frame_id=None,
        delta_reference_frame_sha256=None, provenance_refs=("z", "a"))
    assert cur.provenance_refs == ("a", "z")
    with pytest.raises(RetinaPipelineError, match="duplicates"):
        replace(cur, provenance_refs=("a", "a"))


def test_assessment_contains_no_raw_frame_or_semantic_claim():
    payload = assess(frame("f0", 0)).as_dict()
    assert payload["raw_frame_present"] is False
    assert "object" not in payload and "person" not in payload
    assert payload["world_truth_authority"] == "NONE"
    assert payload["gwt_authority"] == "NONE"
    assert payload["completion_authority"] == "NONE"
