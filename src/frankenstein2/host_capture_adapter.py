"""host_capture_adapter.py -- CORTEX-P1 Host Capture Adapter (F2-WP-1207 self-integration,
"real-retina-bridge" round, 2026-09-05).

Architecture decision (Gabriel, verbatim in the P1 work order): Codebase B
(`frankenstein2.perception_*`) is the canonical contract/policy/provenance core.
Codebase A (`~/.claude/star/`) is only a design reference for already-proven
hardware/runtime implementations -- NEVER imported here. Every real-world/hardware
formula in this file (blur variance, clipping fraction, near-uniformity, exposure-jump
veto, block-diff motion, stale-frame detection, single-owner device rule) is a
from-scratch reimplementation of the same measured logic Codebase A's
`capture_worker.py`/`frame_quality.py`/`motion_gate.py` already proved out, written
independently against B's typed contracts. grep this file for "claude/star" or
"capture_worker"/"frame_quality"/"motion_gate" import statements: there are none.

Chain this module implements (P1 scope, stops exactly here):
  REAL CAMERA (cv2.VideoCapture on /dev/video0)
    -> HostCaptureAdapter (this file): single real device owner, transient RAM frame
       buffer keyed by frame_ref_id, cheap real measurements
    -> frankenstein2.perception_capture_broker.RetinaCaptureBroker (canonical, UNCHANGED,
       never opens a camera itself -- receives only digests/sizes/timestamps via
       publish_frame())
    -> frankenstein2.retina_pipeline.RetinaFrameSignal / assess_retina_transition()
       (canonical, UNCHANGED)
    -> frankenstein2.perception_control.evaluate_perception_head() via
       frankenstein2.runtime_policy_adapter.RuntimePolicyAdapter (canonical, UNCHANGED)
    -> frankenstein2.perception_world_bridge.TypedPerceptEvent candidate (canonical,
       UNCHANGED type; this module only constructs an instance under caller-supplied real
       values, never a new event type)

No pixel is ever written to disk or a database anywhere in this file -- verified
structurally (grep for `open(`, `write`, `imwrite`, `sqlite3`, `.db` in this file finds
none) and by a dedicated repository test. No GRID10/GWT/cloud-VLM/OCR/pose/object-
recognition/voice/visual-memory code is imported or called here.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import deque
from typing import Any, Optional

import numpy as np

try:
    import cv2
except ImportError as exc:  # pragma: no cover -- surfaced loudly, never swallowed
    raise ImportError(
        "host_capture_adapter.py requires opencv-python (cv2) -- install with "
        "`pip install opencv-python`"
    ) from exc

from .perception_capture_broker import CaptureFrameRef, RetinaCaptureBroker
from .perception_fabric import PerceptionSource, SourceKind
from .perception_world_bridge import TypedPerceptEvent
from .retina_pipeline import RetinaFrameSignal

# Real device identity, verified via `v4l2-ctl --list-devices` on this host
# (2026-09-05): "Rapoo Camera" resolves to /dev/video0 (and /dev/video1, a second node
# from the same physical device). /dev/video2 ("Estelle Cam") is a v4l2loopback
# synthetic feed belonging to an unrelated project (~/estelle) -- never touched here.
# Same literal device path Codebase A's capture_worker.KAMERA_GERAET uses; not imported
# from there, independently verified against this host's real hardware.
REAL_CAMERA_DEVICE = "/dev/video0"


class HostCaptureAdapterError(RuntimeError):
    """Fail-closed error for the Host Capture Adapter boundary."""


class HostCaptureOwnershipError(HostCaptureAdapterError):
    """Raised when a second HostCaptureAdapter tries to own a device already held by
    another live adapter in this process.

    Concept translated from Codebase A's `capture_worker.KameraBesitzFehler` into B's
    error-class/typing convention (plain RuntimeError subclass under this module's own
    error hierarchy, not a copy-pasted class) -- same single-owner rule, independently
    implemented, no import of A.
    """


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════════════
#  Cheap real measurements -- independently reimplemented from Codebase A's
#  frame_quality.py / motion_gate.py formulas (design reference only, see module
#  docstring). Operates on RAM numpy BGR arrays only, never touches disk.
# ══════════════════════════════════════════════════════════════════════════

BLOCK_GRID = (8, 8)
BLUR_VARIANCE_THRESHOLD = 40.0
CLIPPING_SHADOW_THRESHOLD = 2
CLIPPING_HIGHLIGHT_THRESHOLD = 253
CLIPPING_WARN_FRACTION = 0.35
NEAR_UNIFORM_STD_THRESHOLD = 10.0
BLOCK_DELTA_THRESHOLD = 8.0
BLOCK_DELTA_NOISE_FLOOR = 2.0
BLOCK_CHANGED_FRACTION_THRESHOLD = 0.08
GLOBAL_UNIFORMITY_COEFF_OF_VARIATION = 0.35
DIRECTION_EXTENT_THRESHOLD = 0.6
DIRECTION_AGREEMENT_THRESHOLD = 0.85
GLOBAL_MEAN_DELTA_MINIMUM = 6.0
STALE_WINDOW_SECONDS = 3.0
STALE_MEAN_ABS_DIFF_THRESHOLD = 0.5


def to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def mean_std(frame: np.ndarray) -> tuple[float, float]:
    gray = to_gray(frame)
    return float(gray.mean()), float(gray.std())


def brightness_score(mean_brightness: float) -> float:
    """0..1 ramp between near-black and a well-lit floor, overexposure penalty above 230.

    Same calibration anchors as Codebase A's `_sensor_qualitaet_aus_helligkeit` (design
    reference, not imported): near-zero below mean=3, linear ramp to mean=63, penalty
    above mean=230.
    """
    if mean_brightness <= 3:
        return 0.02
    score = min(1.0, max(0.0, (mean_brightness - 3.0) / 60.0))
    if mean_brightness > 230:
        score *= max(0.3, (255 - mean_brightness) / 25.0)
    return round(min(1.0, max(0.0, score)), 4)


def contrast_score(std: float) -> float:
    """0..1 ramp to std=25 -- same two real calibration anchors as Codebase A's
    `_detail_qualitaet_aus_kontrast` (design reference only)."""
    return round(min(1.0, max(0.0, std / 25.0)), 4)


def blur_variance(frame: np.ndarray) -> float:
    gray = to_gray(frame)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def clipping_fraction(frame: np.ndarray) -> dict:
    gray = to_gray(frame)
    n = gray.size
    shadow = float((gray <= CLIPPING_SHADOW_THRESHOLD).sum()) / n
    highlight = float((gray >= CLIPPING_HIGHLIGHT_THRESHOLD).sum()) / n
    total = shadow + highlight
    return {"shadow_fraction": round(shadow, 4), "highlight_fraction": round(highlight, 4),
            "total_fraction": round(total, 4), "clipped": total >= CLIPPING_WARN_FRACTION}


def block_means(frame: np.ndarray, grid: tuple[int, int] = BLOCK_GRID) -> np.ndarray:
    gray = to_gray(frame).astype(np.float64)
    rows, cols = grid
    h, w = gray.shape
    h2 = (h // rows) * rows
    w2 = (w // cols) * cols
    cropped = gray[:h2, :w2]
    return cropped.reshape(rows, h2 // rows, cols, w2 // cols).mean(axis=(1, 3))


def _direction_uniformity(delta: np.ndarray) -> dict:
    above_noise = np.abs(delta) >= BLOCK_DELTA_NOISE_FLOOR
    n_above = int(above_noise.sum())
    extent = n_above / delta.size
    if n_above == 0:
        return {"extent": round(extent, 4), "agreement": None, "uniform": False}
    significant = delta[above_noise]
    dominant_sign = 1 if significant.mean() >= 0 else -1
    agreement = float((np.sign(significant) == dominant_sign).mean())
    uniform = extent >= DIRECTION_EXTENT_THRESHOLD and agreement >= DIRECTION_AGREEMENT_THRESHOLD
    return {"extent": round(extent, 4), "agreement": round(agreement, 4), "uniform": uniform}


def exposure_jump(current_blocks: np.ndarray, previous_blocks: np.ndarray) -> dict:
    """Distinguish a GLOBAL uniform brightness step (auto-exposure) from LOCAL motion.

    Ported real logic (design reference: Codebase A frame_quality.exposure_jump_erkennen,
    including its documented clipping-edge-case fix): magnitude-uniformity OR
    direction-uniformity, either is sufficient -- a clipped bright region can't step as far
    as a dark one even during a real global exposure jump, so direction agreement alone
    must also qualify.
    """
    delta = current_blocks - previous_blocks
    mean_delta = float(delta.mean())
    abs_mean_delta = abs(mean_delta)
    std_delta = float(delta.std())
    coeff_of_variation = (std_delta / abs_mean_delta) if abs_mean_delta > 1e-6 else float("inf")
    magnitude_uniform = coeff_of_variation <= GLOBAL_UNIFORMITY_COEFF_OF_VARIATION
    direction = _direction_uniformity(delta)
    global_significant = abs_mean_delta >= GLOBAL_MEAN_DELTA_MINIMUM
    uniform = magnitude_uniform or direction["uniform"]
    is_jump = global_significant and uniform
    return {"mean_delta": round(mean_delta, 3), "abs_mean_delta": round(abs_mean_delta, 3),
            "std_delta": round(std_delta, 3),
            "coeff_of_variation": (round(coeff_of_variation, 4) if coeff_of_variation != float("inf") else None),
            "magnitude_uniform": magnitude_uniform, "direction": direction,
            "global_significant": global_significant, "is_exposure_jump": is_jump}


def block_changed_fraction(current_blocks: np.ndarray, previous_blocks: np.ndarray) -> float:
    delta = current_blocks - previous_blocks
    changed = np.abs(delta) >= BLOCK_DELTA_THRESHOLD
    return float(changed.sum()) / changed.size


def stale_check(gray_history: list[tuple[np.ndarray, float]], *,
                 window_seconds: float = STALE_WINDOW_SECONDS,
                 threshold: float = STALE_MEAN_ABS_DIFF_THRESHOLD) -> dict:
    """`gray_history` -- list of (grayscale frame, monotonic_ts), oldest first."""
    if len(gray_history) < 2:
        return {"stale": False, "reason": "too few frames in window for a claim"}
    actual_window = gray_history[-1][1] - gray_history[0][1]
    if actual_window < window_seconds * 0.5:
        return {"stale": False, "reason": f"window too short ({actual_window:.2f}s)"}
    newest = gray_history[-1][0].astype(np.float64)
    max_diff = 0.0
    for gray, _ts in gray_history[:-1]:
        diff = float(np.abs(newest - gray.astype(np.float64)).mean())
        max_diff = max(max_diff, diff)
    stale = max_diff < threshold
    return {"stale": stale, "max_mean_abs_diff": round(max_diff, 4), "threshold": threshold,
            "reason": ("all frames pixel-identical in window -- frozen feed suspected" if stale
                       else "real variation present across window")}


def measure_quality(frame: np.ndarray, *, is_stale: bool = False) -> tuple[int, dict]:
    """Weakest-link combination of brightness/contrast/blur/clipping/near-uniform
    sub-scores -> quality_micros in [0, 1_000_000]. `is_stale` forces the score to 0
    (a frozen feed cannot be trusted regardless of any single frame's own signals)."""
    mean, std = mean_std(frame)
    b_score = brightness_score(mean)
    c_score = contrast_score(std)
    var = blur_variance(frame)
    blur_score = min(1.0, var / BLUR_VARIANCE_THRESHOLD)
    clip = clipping_fraction(frame)
    clip_score = max(0.0, 1.0 - (clip["total_fraction"] / CLIPPING_WARN_FRACTION))
    uniform_score = min(1.0, std / NEAR_UNIFORM_STD_THRESHOLD)
    combined = 0.0 if is_stale else min(b_score, c_score, blur_score, clip_score, uniform_score)
    diagnostics = {
        "mean_brightness": round(mean, 3), "brightness_score": b_score,
        "contrast_std": round(std, 3), "contrast_score": c_score,
        "laplacian_variance": round(var, 3), "blur_score": round(blur_score, 4),
        "clipping": clip, "clip_score": round(clip_score, 4),
        "near_uniform": std < NEAR_UNIFORM_STD_THRESHOLD, "uniform_score": round(uniform_score, 4),
        "is_stale": is_stale, "combined_score": round(combined, 4),
    }
    quality_micros = max(0, min(1_000_000, int(round(combined * 1_000_000))))
    return quality_micros, diagnostics


def measure_delta(current_frame: np.ndarray, previous_frame: np.ndarray) -> tuple[int, dict]:
    """block-diff changed-fraction -> delta_micros in [0, 1_000_000], vetoed to 0 when the
    change is classified as a global exposure jump rather than local scene content."""
    current_blocks = block_means(current_frame)
    previous_blocks = block_means(previous_frame)
    jump = exposure_jump(current_blocks, previous_blocks)
    changed_fraction = block_changed_fraction(current_blocks, previous_blocks)
    effective_fraction = 0.0 if jump["is_exposure_jump"] else changed_fraction
    delta_micros = max(0, min(1_000_000, int(round(effective_fraction * 1_000_000))))
    diagnostics = {"raw_changed_fraction": round(changed_fraction, 4), "exposure_jump": jump,
                   "effective_fraction": round(effective_fraction, 4)}
    return delta_micros, diagnostics


# ══════════════════════════════════════════════════════════════════════════
#  HostCaptureAdapter -- single real device owner, transient RAM buffer.
# ══════════════════════════════════════════════════════════════════════════

class HostCaptureAdapter:
    """Owns exactly one real `/dev/videoN` handle, publishes frame identity/digest into
    the canonical RetinaCaptureBroker, and keeps the actual pixel array in a transient
    in-process dict keyed by `frame_ref_id` -- evicted the moment the broker itself
    evicts the corresponding CaptureFrameRef. No pixel is ever written to disk/DB; the
    broker/contract layer downstream of this adapter never sees a raw pixel, only
    digests/sizes/timestamps (`CaptureFrameRef`).
    """

    _active_devices: dict[str, str] = {}
    _class_lock = threading.Lock()

    def __init__(self, *, broker: RetinaCaptureBroker, owner_id: str,
                 device: str = REAL_CAMERA_DEVICE, source_id: Optional[str] = None,
                 clock_domain: str = "host_capture_adapter_monotonic_ns",
                 warmup_frames: int = 2, stale_history_len: int = 6) -> None:
        self._broker = broker
        self._device = device
        self._owner_id = owner_id
        self._source_id = source_id or f"camera:{device}"
        self._clock_domain = clock_domain
        self._warmup_frames = warmup_frames
        self._source_generation = 1
        self._cap: Any = None
        self._lease = None
        self._opened = False
        self._pixel_buffer: dict[str, np.ndarray] = {}
        self._gray_history: deque[tuple[np.ndarray, float]] = deque(maxlen=stale_history_len)

    @property
    def device(self) -> str:
        return self._device

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def is_open(self) -> bool:
        return self._opened

    # -- Lifecycle: single-owner enforcement -------------------------------

    def open(self) -> "HostCaptureAdapter":
        with HostCaptureAdapter._class_lock:
            holder = HostCaptureAdapter._active_devices.get(self._device)
            if holder is not None and holder != self._owner_id:
                raise HostCaptureOwnershipError(
                    f"{self._device} is already owned by capture_owner_id={holder!r} in this "
                    "process -- single-owner rule. A second consumer must read frames via the "
                    "broker fan-out (read_since()), not open its own cv2.VideoCapture()."
                )
            HostCaptureAdapter._active_devices[self._device] = self._owner_id
        try:
            self._cap = cv2.VideoCapture(self._device)
            if not self._cap.isOpened():
                raise HostCaptureAdapterError(f"cv2.VideoCapture could not open {self._device}")
            for _ in range(self._warmup_frames):
                self._cap.read()
        except Exception:
            with HostCaptureAdapter._class_lock:
                if HostCaptureAdapter._active_devices.get(self._device) == self._owner_id:
                    del HostCaptureAdapter._active_devices[self._device]
            if self._cap is not None:
                self._cap.release()
            self._cap = None
            raise

        source = PerceptionSource(
            source_id=self._source_id, kind=SourceKind.CAMERA, clock_domain=self._clock_domain,
            capture_owner_id=self._owner_id,
            provenance_refs=(f"host_capture_adapter:{self._device}:cortex_p1",),
        )
        self._broker.register_source(source=source, generation=self._source_generation)
        self._lease = self._broker.acquire_owner(
            source_id=self._source_id, source_generation=self._source_generation,
            capture_owner_id=self._owner_id, opened_monotonic_ns=time.monotonic_ns(),
            provenance_refs=(f"host_capture_adapter:{self._device}:cortex_p1",),
        )
        self._opened = True
        return self

    def close(self) -> None:
        """Always safe to call, always releases the real device handle if held."""
        if self._lease is not None:
            try:
                self._broker.release_owner(
                    source_id=self._source_id, source_generation=self._source_generation,
                    capture_owner_id=self._owner_id, lease_id=self._lease.lease_id,
                )
            except Exception:
                pass  # best-effort: device release below must still happen
            self._lease = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        with HostCaptureAdapter._class_lock:
            if HostCaptureAdapter._active_devices.get(self._device) == self._owner_id:
                del HostCaptureAdapter._active_devices[self._device]
        self._pixel_buffer.clear()
        self._gray_history.clear()
        self._opened = False

    def __enter__(self) -> "HostCaptureAdapter":
        return self.open()

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- Capture + publish ---------------------------------------------------

    def capture_and_publish(self) -> CaptureFrameRef:
        """Real cv2 read from the owned device -> broker publish -> transient RAM store."""
        if not self._opened:
            raise HostCaptureAdapterError("adapter is not open")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise HostCaptureAdapterError(f"cv2 read failed on {self._device}")
        return self._publish(frame)

    def inject_frame_for_test(self, frame: np.ndarray) -> CaptureFrameRef:
        """Test-only hook: publish a caller-supplied numpy frame through the identical
        publish/measurement path a real cv2 read would use, without a second physical
        camera event. Used for degraded-frame / synthetic-scene-change contrasts where
        no physical actuator is available on this host. Still requires an open adapter
        with an active lease -- does not bypass single-owner or broker semantics, and
        does not fabricate a CaptureFrameRef outside the real broker."""
        if not self._opened:
            raise HostCaptureAdapterError("adapter is not open")
        return self._publish(frame)

    def _publish(self, frame: np.ndarray) -> CaptureFrameRef:
        raw_bytes = frame.tobytes()
        frame_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        frame_ref = self._broker.publish_frame(
            source_id=self._source_id, source_generation=self._source_generation,
            capture_owner_id=self._owner_id, lease_id=self._lease.lease_id,
            capture_monotonic_ns=time.monotonic_ns(), frame_sha256=frame_sha256,
            payload_size_bytes=len(raw_bytes),
            provenance_refs=(f"host_capture_adapter:{self._device}:cortex_p1",),
        )
        self._pixel_buffer[frame_ref.frame_ref_id] = frame
        self._gray_history.append((to_gray(frame), time.monotonic()))
        self._evict_pixel_buffer()
        return frame_ref

    def _evict_pixel_buffer(self) -> None:
        """Mirror the broker's own eviction: anything the broker no longer retains loses
        its transient pixel buffer entry too."""
        snapshot = self._broker.snapshot(source_id=self._source_id,
                                          source_generation=self._source_generation)
        retained = set(snapshot.retained_frame_ref_ids)
        for frame_ref_id in list(self._pixel_buffer):
            if frame_ref_id not in retained:
                del self._pixel_buffer[frame_ref_id]

    def pixel_buffer_frame(self, frame_ref_id: str) -> Optional[np.ndarray]:
        """Transient RAM lookup -- returns None once evicted. Callers must not persist
        the returned array anywhere; this method exists only so the measurement layer
        (in-process, same call) can read pixels the contract layer never sees."""
        return self._pixel_buffer.get(frame_ref_id)

    def is_recently_stale(self) -> dict:
        return stale_check(list(self._gray_history))


# ══════════════════════════════════════════════════════════════════════════
#  RetinaFrameSignal construction + PerceptEvent candidate assembly.
# ══════════════════════════════════════════════════════════════════════════

def build_retina_frame_signal(
    *, frame_ref: CaptureFrameRef, frame: np.ndarray,
    previous_frame_ref: Optional[CaptureFrameRef], previous_frame: Optional[np.ndarray],
    stream_id: str, continuity_epoch: str, is_stale: bool = False,
    provenance_refs: tuple[str, ...],
) -> tuple[RetinaFrameSignal, dict]:
    """Cheap real measurement -> canonical F2 RetinaFrameSignal. No pixel is retained in
    the returned signal or its diagnostics beyond the frame's own sha256 identity."""
    quality_micros, quality_diag = measure_quality(frame, is_stale=is_stale)
    if previous_frame is None:
        delta_micros = None
        delta_ref_id = None
        delta_ref_sha = None
        diagnostics = {"quality": quality_diag}
    else:
        delta_micros, delta_diag = measure_delta(frame, previous_frame)
        delta_ref_id = previous_frame_ref.frame_ref_id
        delta_ref_sha = previous_frame_ref.frame_sha256
        diagnostics = {"quality": quality_diag, "delta": delta_diag}
    signal = RetinaFrameSignal(
        frame_id=frame_ref.frame_ref_id, stream_id=stream_id,
        generation=frame_ref.source_sequence, captured_monotonic_ns=frame_ref.capture_monotonic_ns,
        frame_sha256=frame_ref.frame_sha256, continuity_epoch=continuity_epoch,
        quality_micros=quality_micros, delta_micros=delta_micros,
        delta_reference_frame_id=delta_ref_id, delta_reference_frame_sha256=delta_ref_sha,
        provenance_refs=provenance_refs,
    )
    return signal, diagnostics


def local_capability_digest(*, source_id: str) -> str:
    """Real sha256 of a canonical-json local-only capability description -- P1 never
    requests remote-frame transfer or external-VLM escalation, so both are hard-coded
    False here rather than read from any capability object. Used only as
    TypedPerceptEvent.permission_snapshot_sha256; this module never calls the WP712
    bridge's remote-admission functions (that is next-round GRID10/world-bridge scope,
    explicitly out of P1)."""
    return _digest({
        "scope": "CORTEX_P1_LOCAL_RETINA_BRIDGE", "source_id": source_id,
        "remote_frame_allowed": False, "external_vlm_allowed": False,
    })


def build_percept_event_candidate(
    *, frame_ref: CaptureFrameRef, event_id: str,
    permission_snapshot_sha256: str, bridge_generation: int, freshness_max_age_ns: int,
    clock_domain: str, observed_monotonic_ns: int, provenance_refs: tuple[str, ...],
) -> TypedPerceptEvent:
    """Construct the canonical F2 TypedPerceptEvent (perception_world_bridge.py, UNCHANGED
    type) as the P1 candidate output. `payload_ref` is the CaptureFrameRef id -- an
    identifier only, never raw pixel data (matches perception_world_bridge's own
    `raw_payload: None` invariant and the repo-wide 'IDs/short text only, never full rows'
    discipline). `source_generation` is taken directly from the frame_ref that was
    actually published through the broker, not re-supplied by the caller."""
    return TypedPerceptEvent(
        event_id=event_id, source_id=frame_ref.source_id, source_generation=frame_ref.source_generation,
        permission_snapshot_sha256=permission_snapshot_sha256, bridge_generation=bridge_generation,
        epistemic_kind="OBSERVED", payload_kind="TYPED_PERCEPT", payload_ref=frame_ref.frame_ref_id,
        source_sequence=frame_ref.source_sequence, capture_monotonic_ns=frame_ref.capture_monotonic_ns,
        observed_monotonic_ns=observed_monotonic_ns, freshness_max_age_ns=freshness_max_age_ns,
        clock_domain=clock_domain, clock_uncertainty_ns=None, provenance_refs=provenance_refs,
    )


__all__ = [
    "REAL_CAMERA_DEVICE",
    "HostCaptureAdapter",
    "HostCaptureAdapterError",
    "HostCaptureOwnershipError",
    "block_changed_fraction",
    "block_means",
    "build_percept_event_candidate",
    "build_retina_frame_signal",
    "brightness_score",
    "clipping_fraction",
    "contrast_score",
    "blur_variance",
    "exposure_jump",
    "local_capability_digest",
    "measure_delta",
    "measure_quality",
    "stale_check",
    "to_gray",
]
