"""cortex_p2_capture.py -- CORTEX-P2 real-camera percept-candidate producer.

Position in the chain (P1 chain REUSED, nothing below it changed):

  REAL CAMERA (/dev/video0)
    -> frankenstein2.host_capture_adapter.HostCaptureAdapter   (P1, UNCHANGED except
       the two strictly-optional kwargs `frame_size`/`prefer_v4l2` this round added so
       the capture fits the LIVE hook's own 4 s subprocess budget; see its docstring)
    -> frankenstein2.perception_capture_broker.RetinaCaptureBroker (canonical, UNCHANGED)
    -> frankenstein2.retina_pipeline.RetinaFrameSignal / assess_retina_transition (UNCHANGED)
    -> frankenstein2.runtime_policy_adapter.RuntimePolicyAdapter (UNCHANGED, reads the
       PRODUCTION unified.db read-only: ~/.local/share/agentzero/unified.db)
    -> frankenstein2.perception_world_bridge.TypedPerceptEvent (canonical type, UNCHANGED)
    -> THIS module: one canonical JSON line on stdout = the CORTEX-P2 candidate record.

What this module adds -- and what it deliberately does NOT do:

- It is a PRODUCER only. It never talks to GRID10, never writes a DB row, never
  touches the effects/journal tables, never opens a second camera handle. The GRID10
  half of P2 (candidate -> competition -> uptake -> evidence) lives in the WP1207
  self-integration repo (frankenstein-repo/scripts/f2wp1207_cortex_p2_percept_candidate.py),
  which runs this file as an isolated, time-limited subprocess -- the exact same
  isolation pattern the LIVE hook already uses against frankenstein-repo/scripts/stern.py.
- No pixel ever reaches stdout, disk or a database here: the record carries the frame's
  sha256 identity and the cheap real measurements only, matching the repo-wide
  "IDs/short text only, never full rows" discipline (asserted structurally by the
  P2 test via the same forbidden-construct grep the P1 test uses).
- `event_id` is derived from real capture content (`cortex-p2-` + first 24 hex of the
  captured frame's sha256): identical pixels yield an identical event identity, no
  clock-based minting, so a reviewer can re-derive it from the recorded frame_sha256.

Candidate percept_signal (the number that competes in the GRID10 competition):

    percept_signal = P2_QUALITY_WEIGHT * quality_micros/1e6
                   + P2_DELTA_WEIGHT   * delta_micros/1e6

Both inputs are REAL measured quantities produced by P1's own
`measure_quality()` / `measure_delta()` (block-diff with exposure-jump veto); nothing is
modelled, randomised or scaled to win. The 0.5/0.5 weighting is a first-cut P2
parameterisation, recorded here and in every evidence line, NOT a preregistered sweep --
with the retina policy shipped in the P1 test (min_quality 400k, salient_delta 100k) an
accepted+salient real percept lands around 0.2-0.9, i.e. the same order of magnitude as
P7's own cell proposal scores (uniform hash signal in [0,1) plus kappa*tanh(state)), so
the candidate can win or lose on real content. The GRID10 side independently RECOMPUTES
this value from the two micros and refuses the candidate on mismatch, so the two halves
cannot drift apart silently.

Exit codes: 0 = candidate record printed (even when the scene was not salient -- the
record itself says so); 3 = no candidate (device absent, busy, read failure, quality
rejected, egress blocked -- `reason` says which); 2 = usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any, Optional

from .host_capture_adapter import (
    REAL_CAMERA_DEVICE,
    HostCaptureAdapter,
    HostCaptureAdapterError,
    HostCaptureOwnershipError,
    build_percept_event_candidate,
    build_retina_frame_signal,
    local_capability_digest,
)
from .perception_capture_broker import CaptureBrokerPolicy, RetinaCaptureBroker
from .retina_pipeline import RetinaPolicy, assess_retina_transition
from .runtime_policy_adapter import RuntimePolicyAdapter

CANDIDATE_SCHEMA = "CORTEX_P2_PERCEPT_CAPTURE/v1"

P2_QUALITY_WEIGHT = 0.5
P2_DELTA_WEIGHT = 0.5

# Freshness fence the GRID10 side enforces: a candidate older than this (as measured by
# the host CLOCK_MONOTONIC, which is system-wide on Linux, so the capturing subprocess
# and the consuming canary process compare against the same clock) is stale and is not
# admitted into a competition.
P2_FRESHNESS_MAX_AGE_NS = 2_000_000_000

PROVENANCE_REFS = ("cortex_p2_capture:cortex-p2-percept-candidate:20260905",)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_CANDIDATE = 3


def percept_signal_from_micros(quality_micros: int, delta_micros: Optional[int]) -> float:
    """The one formula both halves of P2 share. `delta_micros=None` (baseline frame, no
    previous frame) contributes 0 -- a first frame after open cannot claim motion."""
    q = max(0, min(1_000_000, int(quality_micros))) / 1_000_000.0
    d = (max(0, min(1_000_000, int(delta_micros))) / 1_000_000.0) if delta_micros is not None else 0.0
    return round(P2_QUALITY_WEIGHT * q + P2_DELTA_WEIGHT * d, 6)


def capture_percept_candidate(
    *,
    device: str = REAL_CAMERA_DEVICE,
    frames: int = 3,
    owner_id: str = "cortex-p2-percept-candidate",
    stream_id: str = "camera:cortex-p2-percept-candidate",
    continuity_epoch: str = "cortex-p2-percept-candidate-epoch",
    head_id: str = "retina.global",
    min_quality_micros: int = 400_000,
    salient_delta_micros: int = 100_000,
    max_interframe_gap_ns: int = 5_000_000_000,
) -> tuple[Optional[dict[str, Any]], str]:
    """Run the real P1 chain once and return (candidate_record_or_None, reason).

    Real capture only -- no synthetic frame is ever published here (P1's
    `inject_frame_for_test` exists for the disclosed degraded-frame contrasts and stays
    test-only). A static room therefore honestly yields delta_micros ~ 0 and a
    non-salient candidate; that is a correct result, not a failure.
    """
    frames = max(2, min(8, int(frames)))
    t0 = time.monotonic_ns()

    policy = CaptureBrokerPolicy(
        policy_id="cortex-p2-percept-capture", generation=1,
        max_frames_per_source=32, max_frame_age_ns=10_000_000_000,
        max_read_window_frames=16, provenance_refs=PROVENANCE_REFS,
    )
    retina_policy = RetinaPolicy(
        policy_id="cortex-p2-retina-policy", generation=1,
        min_quality_micros=min_quality_micros, salient_delta_micros=salient_delta_micros,
        max_interframe_gap_ns=max_interframe_gap_ns, provenance_refs=PROVENANCE_REFS,
    )
    broker = RetinaCaptureBroker(policy=policy)

    refs: list[Any] = []
    frames_data: list[Any] = []
    try:
        # frame_size/prefer_v4l2: measured on this host (2026-09-05) the driver default
        # costs ~2.6 s of device-open alone; 640x480 over CAP_V4L2 costs ~0.05-0.3 s. The
        # LIVE hook bounds the whole canary turn (this capture included) at 4 s, so P2
        # negotiates the small size. Real delivered shape is whatever the driver gives.
        with HostCaptureAdapter(broker=broker, owner_id=owner_id, device=device,
                                frame_size=(640, 480), prefer_v4l2=True) as adapter:
            for _ in range(frames):
                ref = adapter.capture_and_publish()
                frame = adapter.pixel_buffer_frame(ref.frame_ref_id)
                if frame is None or frame.size == 0:
                    return None, f"published frame {ref.frame_ref_id} has no readable pixel buffer"
                refs.append(ref)
                frames_data.append(frame)
            stale = adapter.is_recently_stale()
    except HostCaptureOwnershipError:
        return None, (f"{device} is owned by another capture process (single-owner rule) -- "
                      "no candidate produced, fail-closed")
    except HostCaptureAdapterError as exc:
        return None, f"capture failed on {device}: {exc}"

    last_ref, last_frame = refs[-1], frames_data[-1]
    prev_ref, prev_frame = (refs[-2], frames_data[-2]) if len(refs) > 1 else (None, None)

    signal, diagnostics = build_retina_frame_signal(
        frame_ref=last_ref, frame=last_frame,
        previous_frame_ref=prev_ref, previous_frame=prev_frame,
        stream_id=stream_id, continuity_epoch=continuity_epoch, provenance_refs=PROVENANCE_REFS,
    )
    # assess_retina_transition with/without a previous signal are different call shapes;
    # build exactly one of them (mirrors the P1 gold test's two branches).
    if prev_ref is None:
        assessment = assess_retina_transition(
            assessment_id=f"cortex-p2-assess-{last_ref.frame_ref_id[:16]}",
            current=signal, expected_current_signal_sha256=signal.sha256(),
            policy=retina_policy, expected_policy_sha256=retina_policy.sha256(),
            provenance_refs=PROVENANCE_REFS,
        )
    else:
        prev_signal, _ = build_retina_frame_signal(
            frame_ref=prev_ref, frame=prev_frame, previous_frame_ref=None, previous_frame=None,
            stream_id=stream_id, continuity_epoch=continuity_epoch, provenance_refs=PROVENANCE_REFS,
        )
        assessment = assess_retina_transition(
            assessment_id=f"cortex-p2-assess-{last_ref.frame_ref_id[:16]}",
            current=signal, expected_current_signal_sha256=signal.sha256(),
            policy=retina_policy, expected_policy_sha256=retina_policy.sha256(),
            previous=prev_signal, expected_previous_signal_sha256=prev_signal.sha256(),
            provenance_refs=PROVENANCE_REFS,
        )

    if assessment.quality_status != "QUALITY_PASS":
        return None, f"quality rejected by retina policy ({assessment.quality_status}: {assessment.event_reason})"
    if stale.get("stale"):
        return None, f"frozen-feed/stale capture window -- no candidate ({stale})"

    # Canonical policy gate: the production unified.db row for this head decides whether
    # the measurement may leave the perception head at all (read-only, unchanged code).
    rpa = RuntimePolicyAdapter(head_id=head_id)
    control = rpa.evaluate(
        evaluation_id=f"cortex-p2-eval-{last_ref.frame_ref_id[:16]}",
        compute_fn=lambda: (assessment.as_dict(), signal.quality_micros),
        provenance_refs=PROVENANCE_REFS,
    )
    if not control.egress_allowed:
        return None, f"perception head gate blocked egress ({control.status})"

    salient = bool(assessment.percept_event_candidate)
    quality_micros = int(signal.quality_micros)
    delta_micros = None if signal.delta_micros is None else int(signal.delta_micros)
    event = None
    if salient:
        event = build_percept_event_candidate(
            frame_ref=last_ref,
            event_id=f"cortex-p2-{last_ref.frame_sha256[:24]}",
            permission_snapshot_sha256=local_capability_digest(source_id=last_ref.source_id),
            bridge_generation=1,
            freshness_max_age_ns=P2_FRESHNESS_MAX_AGE_NS,
            clock_domain="cortex_p2_monotonic_ns",
            observed_monotonic_ns=last_ref.capture_monotonic_ns,
            provenance_refs=PROVENANCE_REFS,
        )

    record = {
        "schema": CANDIDATE_SCHEMA,
        "ok": True,
        "device": device,
        "source_id": last_ref.source_id,
        "frames_captured": len(refs),
        "frame_ref_id": last_ref.frame_ref_id,
        "frame_sha256": last_ref.frame_sha256,
        "source_sequence": last_ref.source_sequence,
        "quality_micros": quality_micros,
        "delta_micros": delta_micros,
        "salient": salient,
        "egress_allowed": True,
        "percept_signal": percept_signal_from_micros(quality_micros, delta_micros),
        "percept_signal_formula": (f"{P2_QUALITY_WEIGHT}*quality_micros/1e6 + "
                                   f"{P2_DELTA_WEIGHT}*delta_micros/1e6"),
        "assessment": assessment.as_dict(),
        "event": None if event is None else event.as_dict(),
        "event_sha256": None if event is None else event.sha256(),
        "clock_domain": "cortex_p2_monotonic_ns",
        "capture_monotonic_ns": last_ref.capture_monotonic_ns,
        "capture_wall_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "freshness_max_age_ns": P2_FRESHNESS_MAX_AGE_NS,
        "stale_window": stale,
        "capture_ms": round((time.monotonic_ns() - t0) / 1_000_000, 1),
        "provenance_refs": list(PROVENANCE_REFS),
        # Real measurement diagnostics (numbers only, never pixels) -- same shape the P1
        # gold test prints, kept for the evidence line so a reviewer can see WHY a
        # candidate scored what it scored.
        "diagnostics": diagnostics,
    }
    return record, ""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m frankenstein2.cortex_p2_capture",
        description="CORTEX-P2: one real camera capture -> one typed percept-candidate record (JSON on stdout).",
    )
    parser.add_argument("--device", default=os.environ.get("CORTEX_P2_DEVICE", REAL_CAMERA_DEVICE))
    parser.add_argument("--frames", type=int, default=3)
    parser.add_argument("--head-id", default="retina.global")
    args = parser.parse_args(argv)

    record, reason = capture_percept_candidate(device=args.device, frames=args.frames, head_id=args.head_id)
    if record is None:
        print(_canonical({"schema": CANDIDATE_SCHEMA, "ok": False, "device": args.device,
                          "reason": reason, "capture_wall_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
        return EXIT_NO_CANDIDATE
    print(_canonical(record))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
