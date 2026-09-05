"""cortex_p3_frame_file.py -- CORTEX-P3 real-camera frame -> ONE temporary JPEG file.

Position in the chain (P1 chain REUSED, nothing below it changed):

  REAL CAMERA (/dev/video0)
    -> frankenstein2.host_capture_adapter.HostCaptureAdapter   (P1, UNCHANGED)
    -> frankenstein2.perception_capture_broker.RetinaCaptureBroker (canonical, UNCHANGED)
    -> frankenstein2.retina_pipeline.RetinaFrameSignal / assess_retina_transition (UNCHANGED)
    -> frankenstein2.runtime_policy_adapter.RuntimePolicyAdapter (UNCHANGED, reads the
       PRODUCTION unified.db read-only: ~/.local/share/agentzero/unified.db)
    -> THIS module: the LAST captured frame is encoded to a JPEG at a caller-chosen
       path INSIDE THE SYSTEM TEMP DIRECTORY and one canonical JSON line goes to stdout.

Why this module exists at all (CORTEX-P3 work order paket-1788615221510-d28c99):
the P2 capture half deliberately never lets a pixel out of its own process ("No pixel
ever reaches stdout, disk or a database here"). P3 needs exactly one exception -- the
frame has to reach ``visual_cortex.vision_beschreibung_holen()`` as a file, because that
is the ONE allowed cloud-vision entry point in the whole stack and it takes a path. This
module is that narrow bridge. It is the ONLY new code in frankenstein-2.0 for P3 and it
adds no policy of its own:

- The camera acquisition is byte-for-byte the P2 ``Beschaffungsmuster``
  (``cortex_p2_capture.capture_percept_candidate``): same broker policy, same
  ``frame_size=(640, 480)`` / ``prefer_v4l2`` negotiation, same single-owner rule, same
  staleness window, same retina quality gate. Only the tail differs -- instead of
  building a TypedPerceptEvent, the last frame is written to temp disk.
- The retina policy (``min_quality_micros``) is applied unchanged, so a black/blinded
  frame is REJECTED here and never reaches the vision API. ``delta_micros`` is measured
  but NOT gated on: P3 describes the scene, it is not a motion detector, so a static
  room must still produce a frame (the P2 salience verdict travels in the record instead).
- ``retina.global`` is consulted through the unchanged RuntimePolicyAdapter exactly like
  P2 does. If that head is COMPUTE_OFF, no frame is produced at all -- fail-closed, the
  caller gets exit 3 and a reason. P3 does not open a second, gate-free camera path.
- Temp-file discipline: the output path is refused unless it resolves inside
  ``tempfile.gettempdir()`` (i.e. /tmp). No pixel is ever written anywhere else, no
  pixel reaches stdout or a database, and deleting the file is the CALLER's job
  (the P3 CLI owns the file lifetime and unlinks it in a ``finally``).
- Exit codes follow the P2 convention: 0 = JSON record printed (even when the frame was
  not salient), 3 = no frame (device absent/busy, quality rejected, stale, egress
  blocked -- ``reason`` says which), 2 = usage error (including a temp-dir violation).
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

import cv2

from .host_capture_adapter import (
    REAL_CAMERA_DEVICE,
    HostCaptureAdapter,
    HostCaptureAdapterError,
    HostCaptureOwnershipError,
    build_retina_frame_signal,
)
from .perception_capture_broker import CaptureBrokerPolicy, RetinaCaptureBroker
from .retina_pipeline import RetinaPolicy, assess_retina_transition
from .runtime_policy_adapter import RuntimePolicyAdapter

FRAME_SCHEMA = "CORTEX_P3_FRAME_FILE/v1"

PROVENANCE_REFS = ("cortex_p3_frame_file:cortex-p3-temp-frame:20260905",)

JPEG_QUALITY = 85

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_FRAME = 3


def tempdir_root() -> str:
    """The only directory this module will ever write a frame into."""
    return tempfile.gettempdir()


def _inside_tempdir(pfad: Path) -> bool:
    try:
        return pfad.resolve().is_relative_to(Path(tempdir_root()).resolve())
    except (OSError, ValueError):
        return False


def capture_frame_to_file(
    *,
    out_path: str,
    device: str = REAL_CAMERA_DEVICE,
    frames: int = 3,
    owner_id: str = "cortex-p3-frame-file",
    stream_id: str = "camera:cortex-p3-describe",
    continuity_epoch: str = "cortex-p3-describe-epoch",
    head_id: str = "retina.global",
    unified_db: Optional[str] = None,
    min_quality_micros: int = 400_000,
    salient_delta_micros: int = 100_000,
    max_interframe_gap_ns: int = 5_000_000_000,
) -> tuple[Optional[dict[str, Any]], str]:
    """Run the real P1 chain once and write the last frame as a JPEG. Returns
    (record_or_None, reason). Never raises; on any failure no file is left behind."""
    ziel = Path(out_path)
    if not _inside_tempdir(ziel):
        return None, (f"out_path {out_path!r} is not inside the system temp directory "
                      f"({tempdir_root()}) -- pixel files are tmp-only, refusing")
    frames = max(2, min(8, int(frames)))
    t0 = time.monotonic_ns()

    policy = CaptureBrokerPolicy(
        policy_id="cortex-p3-frame-file", generation=1,
        max_frames_per_source=32, max_frame_age_ns=10_000_000_000,
        max_read_window_frames=16, provenance_refs=PROVENANCE_REFS,
    )
    retina_policy = RetinaPolicy(
        policy_id="cortex-p3-retina-policy", generation=1,
        min_quality_micros=min_quality_micros, salient_delta_micros=salient_delta_micros,
        max_interframe_gap_ns=max_interframe_gap_ns, provenance_refs=PROVENANCE_REFS,
    )
    broker = RetinaCaptureBroker(policy=policy)

    refs: list[Any] = []
    frames_data: list[Any] = []
    try:
        # Same size/transport negotiation the P2 capture half measured on this host
        # (2026-09-05): driver default costs ~2.6 s of device-open alone, 640x480 over
        # CAP_V4L2 costs ~0.05-0.3 s. Real delivered shape is whatever the driver gives.
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
                      "no frame produced, fail-closed")
    except HostCaptureAdapterError as exc:
        return None, f"capture failed on {device}: {exc}"

    last_ref, last_frame = refs[-1], frames_data[-1]
    prev_ref, prev_frame = (refs[-2], frames_data[-2]) if len(refs) > 1 else (None, None)

    signal, diagnostics = build_retina_frame_signal(
        frame_ref=last_ref, frame=last_frame,
        previous_frame_ref=prev_ref, previous_frame=prev_frame,
        stream_id=stream_id, continuity_epoch=continuity_epoch, provenance_refs=PROVENANCE_REFS,
    )
    if prev_ref is None:
        assessment = assess_retina_transition(
            assessment_id=f"cortex-p3-assess-{last_ref.frame_ref_id[:16]}",
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
            assessment_id=f"cortex-p3-assess-{last_ref.frame_ref_id[:16]}",
            current=signal, expected_current_signal_sha256=signal.sha256(),
            policy=retina_policy, expected_policy_sha256=retina_policy.sha256(),
            previous=prev_signal, expected_previous_signal_sha256=prev_signal.sha256(),
            provenance_refs=PROVENANCE_REFS,
        )

    if assessment.quality_status != "QUALITY_PASS":
        return None, (f"quality rejected by retina policy ({assessment.quality_status}: "
                      f"{assessment.event_reason}) -- no frame written, no vision call possible")
    if stale.get("stale"):
        return None, f"frozen-feed/stale capture window -- no frame ({stale})"

    # Canonical policy gate, exactly the P2 shape: the production unified.db row for this
    # head decides whether the perception head may hand anything outward at all.
    # `unified_db` is a test-isolation override only: default is the real production
    # database, read strictly read-only (mode=ro), exactly like P2. The policy ROW is
    # read from wherever this points; the decision logic is unchanged.
    rpa = (RuntimePolicyAdapter(head_id=head_id) if not unified_db
           else RuntimePolicyAdapter(head_id=head_id, db_path=unified_db))
    control = rpa.evaluate(
        evaluation_id=f"cortex-p3-eval-{last_ref.frame_ref_id[:16]}",
        compute_fn=lambda: (assessment.as_dict(), signal.quality_micros),
        provenance_refs=PROVENANCE_REFS,
    )
    if not control.egress_allowed:
        return None, f"perception head gate blocked egress ({control.status})"

    ok, encoded = cv2.imencode(".jpg", last_frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    if not ok or encoded is None or encoded.size == 0:
        return None, "cv2.imencode produced no JPEG bytes for the captured frame"
    try:
        ziel.write_bytes(encoded.tobytes())
    except OSError as exc:
        return None, f"could not write temp frame {str(ziel)!r}: {exc}"

    height, width = last_frame.shape[:2]
    record: dict[str, Any] = {
        "schema": FRAME_SCHEMA,
        "ok": True,
        "device": device,
        "out_path": str(ziel),
        "frame_sha256": last_ref.frame_sha256,
        "frame_ref_id": last_ref.frame_ref_id,
        "source_id": last_ref.source_id,
        "source_sequence": last_ref.source_sequence,
        "frames_captured": len(refs),
        "width": int(width),
        "height": int(height),
        "jpeg_bytes": int(encoded.size),
        "jpeg_quality": JPEG_QUALITY,
        # Real P1 measurements -- carried through so the P3 visual_event row has an
        # honest sensor_quality instead of a guess. Not a motion verdict.
        "quality_micros": int(signal.quality_micros),
        "delta_micros": None if signal.delta_micros is None else int(signal.delta_micros),
        "salient": bool(assessment.percept_event_candidate),
        "quality_status": assessment.quality_status,
        "egress_allowed": True,
        "head_id": head_id,
        "clock_domain": "cortex_p3_monotonic_ns",
        "capture_monotonic_ns": last_ref.capture_monotonic_ns,
        "capture_wall_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "capture_ms": round((time.monotonic_ns() - t0) / 1_000_000, 1),
        "provenance_refs": list(PROVENANCE_REFS),
        "diagnostics": diagnostics,
    }
    return record, ""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m frankenstein2.cortex_p3_frame_file",
        description=("CORTEX-P3: one real camera capture -> one temporary JPEG inside the "
                     "system temp dir + one JSON record on stdout (never pixels on stdout)."),
    )
    parser.add_argument("--out", required=True, help="JPEG target path, MUST be inside the system temp dir")
    parser.add_argument("--device", default=os.environ.get("CORTEX_P3_DEVICE", REAL_CAMERA_DEVICE))
    parser.add_argument("--frames", type=int, default=3)
    parser.add_argument("--head-id", default="retina.global")
    parser.add_argument("--unified-db", default=None,
                        help="test isolation only: read the retina policy row from this copy")
    args = parser.parse_args(argv)

    record, reason = capture_frame_to_file(out_path=args.out, device=args.device,
                                           frames=args.frames, head_id=args.head_id,
                                           unified_db=args.unified_db)
    if record is None:
        print(_canonical({"schema": FRAME_SCHEMA, "ok": False, "device": args.device,
                          "out_path": args.out, "reason": reason,
                          "capture_wall_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
        return EXIT_NO_FRAME
    print(_canonical(record))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
