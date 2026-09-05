"""Real-hardware gold test + contrasts for CORTEX-P2 "percept candidate into the canary"
(F2-WP-1207 self-integration, 2026-09-05) -- capture half.

Tests the PRODUCER half: frankenstein2.cortex_p2_capture, i.e. the unchanged P1 chain
(HostCaptureAdapter -> RetinaCaptureBroker -> RetinaFrameSignal -> RetinaAssessment ->
RuntimePolicyAdapter -> TypedPerceptEvent) ending in ONE canonical candidate record.
Uses the REAL Rapoo camera (/dev/video0). Not mocked. Skips (not fails) when
/dev/video0 is absent, so this file stays CI-safe while still being a real test here.

The GRID10/competition half lives in frankenstein-repo/scripts/
(f2wp1207_cortex_p2_percept_candidate.py + f2wp1207_cortex_p2_gold_test.py) and is
deliberately NOT imported here: that repo has its own test convention and its own
branch/merge discipline.

Degraded-frame contrast: as in the P1 test, no actuator exists on this host, so the
"bad capture" case is exercised by feeding a deliberately degraded copy of a REAL
captured frame through the very functions the capture module calls
(build_retina_frame_signal + assess_retina_transition + measure_quality) -- disclosed,
not hidden, and it proves the refusal path is the real code path, not a mock.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frankenstein2.cortex_p2_capture import (  # noqa: E402
    CANDIDATE_SCHEMA,
    P2_DELTA_WEIGHT,
    P2_FRESHNESS_MAX_AGE_NS,
    P2_QUALITY_WEIGHT,
    capture_percept_candidate,
    percept_signal_from_micros,
)
from frankenstein2.host_capture_adapter import (  # noqa: E402
    REAL_CAMERA_DEVICE,
    HostCaptureAdapter,
    build_retina_frame_signal,
    measure_quality,
)
from frankenstein2.perception_capture_broker import (  # noqa: E402
    CaptureBrokerPolicy,
    RetinaCaptureBroker,
)
from frankenstein2.retina_pipeline import RetinaPolicy, assess_retina_transition  # noqa: E402

REFS = ("test:cortex-p2-percept-capture",)
HAS_CAMERA = pathlib.Path(REAL_CAMERA_DEVICE).exists()
skip_no_camera = pytest.mark.skipif(not HAS_CAMERA, reason=f"{REAL_CAMERA_DEVICE} not present on this host")


def _child_env() -> dict:
    return {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def _lsof_clean(device: str) -> bool:
    result = subprocess.run(["lsof", device], capture_output=True, text=True)
    return result.returncode != 0 or not result.stdout.strip()


def _contract(record: dict) -> None:
    """The candidate-record contract both halves of P2 depend on."""
    assert record["schema"] == CANDIDATE_SCHEMA
    assert record["ok"] is True
    assert record["device"] == REAL_CAMERA_DEVICE
    assert record["frames_captured"] >= 2
    assert len(record["frame_sha256"]) == 64
    # signal recomputes from the two REAL micros -- the GRID10 side refuses otherwise
    expected = percept_signal_from_micros(record["quality_micros"], record["delta_micros"])
    assert record["percept_signal"] == expected
    assert 0.0 <= record["percept_signal"] <= 1.0
    assert record["freshness_max_age_ns"] == P2_FRESHNESS_MAX_AGE_NS
    assert record["capture_monotonic_ns"] > 0
    assert record["capture_ms"] > 0
    # salience discipline: a real TypedPerceptEvent exists ONLY when the retina policy
    # called the frame salient, and never otherwise (P1's no-false-event rule).
    salient = bool(record["assessment"]["percept_event_candidate"])
    assert record["salient"] == salient
    if salient:
        assert isinstance(record["event"], dict) and len(record["event_sha256"]) == 64
    else:
        assert record["event"] is None and record["event_sha256"] is None
    # no raw pixel material anywhere in the record
    blob = json.dumps(record)
    assert "raw_payload" not in blob or '"raw_payload":null' in blob.replace(" ", "")
    for key in ("frame_b64", "pixels", "data_url"):
        assert key not in record


@skip_no_camera
def test_gold_real_camera_candidate_record_in_process():
    assert _lsof_clean(REAL_CAMERA_DEVICE)
    record, reason = capture_percept_candidate()
    assert record is not None, f"real capture produced no candidate: {reason}"
    _contract(record)
    print("GOLD real candidate:", {k: record[k] for k in (
        "quality_micros", "delta_micros", "percept_signal", "salient",
        "event_sha256", "capture_ms", "frames_captured")})
    print("GOLD assessment:", {k: record["assessment"][k] for k in (
        "quality_status", "delta_status", "continuity_status", "event_reason")})
    assert _lsof_clean(REAL_CAMERA_DEVICE), "camera not released after in-process capture"


@skip_no_camera
def test_gold_real_camera_candidate_record_via_subprocess_cli():
    """The exact invocation the GRID10 half uses: an isolated subprocess."""
    assert _lsof_clean(REAL_CAMERA_DEVICE)
    proc = subprocess.run(
        [sys.executable, "-m", "frankenstein2.cortex_p2_capture"],
        capture_output=True, text=True, timeout=25, env=_child_env(),
    )
    print("CLI exit:", proc.returncode, "stderr tail:", proc.stderr[-300:])
    assert proc.returncode == 0, f"CLI exit={proc.returncode}: {proc.stdout[-400:]}"
    record = json.loads(proc.stdout.strip().splitlines()[-1])
    _contract(record)
    assert _lsof_clean(REAL_CAMERA_DEVICE)


@skip_no_camera
def test_contrast_device_busy_fails_closed_with_exit_3():
    """Real single-owner proof through the CLI: while THIS process owns /dev/video0, the
    capture subprocess must refuse (exit 3, ownership reason) and must not wait/hang."""
    broker = RetinaCaptureBroker(policy=CaptureBrokerPolicy(
        policy_id="cortex-p2-busy-contrast", generation=1, max_frames_per_source=4,
        max_frame_age_ns=10_000_000_000, max_read_window_frames=4, provenance_refs=REFS,
    ))
    adapter = HostCaptureAdapter(broker=broker, owner_id="cortex-p2-busy-holder").open()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "frankenstein2.cortex_p2_capture"],
            capture_output=True, text=True, timeout=25, env=_child_env(),
        )
        assert proc.returncode == 3, f"expected exit 3, got {proc.returncode}: {proc.stdout[-300:]}"
        record = json.loads(proc.stdout.strip().splitlines()[-1])
        assert record["ok"] is False
        # Cross-process contention surfaces as a plain open failure inside the child
        # (the in-process single-owner HostCaptureOwnershipError case is P1's own
        # contrast 7); either way the CLI must fail CLOSED with an explicit reason.
        assert "/dev/video0" in record["reason"], record["reason"]
        assert "event" not in record and "event_sha256" not in record
        print("CONTRAST busy-device reason:", record["reason"])
    finally:
        adapter.close()
    assert _lsof_clean(REAL_CAMERA_DEVICE)


@skip_no_camera
def test_contrast_degraded_real_frame_is_refused_by_the_same_functions():
    """Disclosed degraded real capture (near-total darkness on a REAL frame), run through
    the identical signal/assessment functions the capture module uses -> the candidate
    path must refuse it (QUALITY_REJECTED, no event), i.e. a lens-cap/dark scene can
    never enter the GRID10 competition as a healthy percept."""
    broker = RetinaCaptureBroker(policy=CaptureBrokerPolicy(
        policy_id="cortex-p2-degraded-contrast", generation=1, max_frames_per_source=8,
        max_frame_age_ns=10_000_000_000, max_read_window_frames=8, provenance_refs=REFS,
    ))
    retina_policy = RetinaPolicy(
        policy_id="cortex-p2-retina-policy", generation=1, min_quality_micros=400_000,
        salient_delta_micros=100_000, max_interframe_gap_ns=5_000_000_000, provenance_refs=REFS,
    )
    with HostCaptureAdapter(broker=broker, owner_id="cortex-p2-degraded",
                            frame_size=(640, 480), prefer_v4l2=True) as adapter:
        ref_good = adapter.capture_and_publish()
        frame_good = adapter.pixel_buffer_frame(ref_good.frame_ref_id)
        q_good, _ = measure_quality(frame_good)
        degraded = (frame_good.astype(np.float64) * 0.01).astype(np.uint8)
        ref_bad = adapter.inject_frame_for_test(degraded)
        frame_bad = adapter.pixel_buffer_frame(ref_bad.frame_ref_id)
        q_bad, diag_bad = measure_quality(frame_bad)

    signal_bad, _ = build_retina_frame_signal(
        frame_ref=ref_bad, frame=frame_bad, previous_frame_ref=None, previous_frame=None,
        stream_id="camera:cortex-p2-degraded", continuity_epoch="cortex-p2-degraded-epoch",
        provenance_refs=REFS,
    )
    assessment_bad = assess_retina_transition(
        assessment_id="cortex-p2-assess-degraded", current=signal_bad,
        expected_current_signal_sha256=signal_bad.sha256(), policy=retina_policy,
        expected_policy_sha256=retina_policy.sha256(), provenance_refs=REFS,
    )
    print("CONTRAST degraded: q_good:", q_good, "q_bad:", q_bad, diag_bad["combined_score"])
    assert q_bad < q_good
    assert q_bad < 400_000, "degraded real frame must fall below the retina quality floor"
    assert assessment_bad.quality_status == "QUALITY_REJECTED"
    assert assessment_bad.percept_event_candidate is False
    # and the shared formula gives it a near-zero competing signal
    assert percept_signal_from_micros(q_bad, None) < 0.05


def test_formula_is_symmetric_and_bounded():
    """Pure check of the one formula both halves share (no camera needed)."""
    assert percept_signal_from_micros(1_000_000, None) == P2_QUALITY_WEIGHT
    assert percept_signal_from_micros(0, 1_000_000) == P2_DELTA_WEIGHT
    assert percept_signal_from_micros(1_000_000, 1_000_000) == round(
        P2_QUALITY_WEIGHT + P2_DELTA_WEIGHT, 6)
    assert percept_signal_from_micros(-5, None) == 0.0
    assert percept_signal_from_micros(2_000_000, 9_999_999) == 0.5 + P2_DELTA_WEIGHT
    with pytest.raises((TypeError, ValueError)):
        percept_signal_from_micros("high", None)  # type: ignore[arg-type]


# ══════════════════════════════════════════════════════════════════════════
#  Structural discipline, same style as the P1 test file.
# ══════════════════════════════════════════════════════════════════════════

def test_no_pixel_or_db_write_construct_in_capture_module():
    forbidden = ("cv2.imwrite", "INSERT INTO", "UPDATE ", "DELETE FROM", "executescript",
                 "np.save(", "np.savez(", ".tofile(", "pickle.dump", "json.dump(",
                 "conn.commit", "sqlite3.connect", "open(")
    text = (ROOT / "src" / "frankenstein2" / "cortex_p2_capture.py").read_text()
    for construct in forbidden:
        assert construct not in text, f"capture module contains forbidden construct: {construct}"


def test_no_grid10_or_effects_or_star_import_in_capture_module():
    import re

    text = (ROOT / "src" / "frankenstein2" / "cortex_p2_capture.py").read_text()
    for banned in ("grid10", "f2wp1207", "effect_journal", "capture_worker", "frame_quality",
                   "motion_gate", "star", "stern"):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not re.match(r"^\s*(import|from)\s+", line):
                continue
            assert banned not in line, f"cortex_p2_capture.py:{lineno} imports banned module: {line!r}"


# -- helpers kept at the bottom so the test bodies above read top-down -------------

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
