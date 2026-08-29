"""Legacy Retina capture API adapter over the canonical F2-WP-709 broker.

This module is intentionally NOT a second CaptureBroker authority.  It exists only so
pre-convergence repository integration harnesses can keep their small functional API while
all source registration, owner leasing, frame sequencing, bounded retention, eviction and
reader fan-out are executed by :mod:`perception_capture_broker`.

No independent frame ring, owner lease table, raw payload store, world-truth authority,
effect authority or completion authority exists here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, ClassVar

from .perception_capture_broker import (
    CaptureBrokerError,
    CaptureBrokerPolicy,
    CaptureFrameRef as CanonicalCaptureFrameRef,
    RetinaCaptureBroker as CanonicalRetinaCaptureBroker,
)
from .perception_fabric import PerceptionSource, SourceKind

FRAME_REF_SCHEMA = "FRANKENSTEIN2_CAPTURE_FRAME_REF_COMPAT/v1"
BROKER_STATE_SCHEMA = "FRANKENSTEIN2_CAPTURE_BROKER_COMPAT_ADAPTER/v1"
CAPTURE_BROKER_AUTHORITY = "DELEGATES_ONLY_TO_PERCEPTION_CAPTURE_BROKER"
CANONICAL_CAPTURE_BROKER_MODULE = "src/frankenstein2/perception_capture_broker.py"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise CaptureBrokerError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise CaptureBrokerError(f"{name} must not contain control characters")
    return value


def _nonnegative(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise CaptureBrokerError(f"{name} must be an integer >= 0")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise CaptureBrokerError(f"{name} must be lowercase sha256 hex")
    return value


def _refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise CaptureBrokerError(f"{name} must be a non-empty immutable tuple")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise CaptureBrokerError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _source_kind(source_id: str) -> SourceKind:
    if source_id.startswith("camera:"):
        return SourceKind.CAMERA
    if source_id.startswith("display:"):
        return SourceKind.DISPLAY
    if source_id.startswith("browser:rendered"):
        return SourceKind.BROWSER_RENDERED
    if source_id.startswith("browser:structural"):
        return SourceKind.BROWSER_STRUCTURAL
    if source_id.startswith("user-activity:") or source_id.startswith("user_activity:"):
        return SourceKind.USER_ACTIVITY
    return SourceKind.OTHER


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureFrameRef:
    """Legacy input/reference shape; never a retained authority in this adapter."""

    frame_ref_id: str
    source_id: str
    source_sequence: int
    captured_monotonic_ns: int
    payload_sha256: str
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = FRAME_REF_SCHEMA
    classification: ClassVar[str] = "COMPAT_INPUT_REFERENCE_NOT_CAPTURE_STATE_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_ref_id", _text("frame_ref_id", self.frame_ref_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative("source_sequence", self.source_sequence)
        _nonnegative("captured_monotonic_ns", self.captured_monotonic_ns)
        _sha256("payload_sha256", self.payload_sha256)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "frame_ref_id": self.frame_ref_id,
            "source_id": self.source_id,
            "source_sequence": self.source_sequence,
            "captured_monotonic_ns": self.captured_monotonic_ns,
            "payload_sha256": self.payload_sha256,
            "contains_payload_bytes": False,
            "capture_state_authority": "NONE",
            "world_truth_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(slots=True, kw_only=True)
class CaptureBrokerState:
    """Compatibility handle whose only mutable capture state lives in the canonical broker."""

    broker_id: str
    source_id: str
    capture_owner_id: str
    capacity: int
    origin_provenance_refs: tuple[str, ...]
    _canonical: CanonicalRetinaCaptureBroker = field(repr=False)
    _lease_id: str = field(repr=False)
    _source_generation: int = field(default=1, repr=False)
    _last_capture_monotonic_ns: int = field(default=0, repr=False)

    schema: ClassVar[str] = BROKER_STATE_SCHEMA
    classification: ClassVar[str] = "COMPATIBILITY_HANDLE_CANONICAL_BROKER_DELEGATE_ONLY"

    @property
    def generation(self) -> int:
        snapshot = self._canonical.snapshot(
            source_id=self.source_id,
            source_generation=self._source_generation,
        )
        return snapshot.newest_sequence or 0

    @property
    def dropped_frame_count(self) -> int:
        return self._canonical.snapshot(
            source_id=self.source_id,
            source_generation=self._source_generation,
        ).evicted_frame_count

    @property
    def frame_refs(self) -> tuple[CaptureFrameRef, ...]:
        return latest_frame_refs(self, limit=self.capacity)

    @property
    def dropped_frame_ref_ids(self) -> tuple[str, ...]:
        # The canonical broker owns eviction accounting.  Legacy recent-id diagnostics were
        # never canonical and are intentionally not recreated as a parallel retained ring.
        return ()

    @property
    def provenance_refs(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                set(
                    self.origin_provenance_refs
                    + (
                        f"canonical-capture-snapshot-sha256:{_snapshot_sha256(self)}",
                        f"canonical-module:{CANONICAL_CAPTURE_BROKER_MODULE}",
                    )
                )
            )
        )

    def as_dict(self) -> dict[str, Any]:
        snapshot = self._canonical.snapshot(
            source_id=self.source_id,
            source_generation=self._source_generation,
        )
        return {
            "schema": self.schema,
            "classification": self.classification,
            "broker_id": self.broker_id,
            "source_id": self.source_id,
            "capture_owner_id": self.capture_owner_id,
            "capacity": self.capacity,
            "generation": self.generation,
            "canonical_snapshot": snapshot.as_dict(),
            "raw_frame_persistence": False,
            "capture_broker_authority": CAPTURE_BROKER_AUTHORITY,
            "canonical_capture_broker_module": CANONICAL_CAPTURE_BROKER_MODULE,
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _snapshot_sha256(state: CaptureBrokerState) -> str:
    snapshot = state._canonical.snapshot(
        source_id=state.source_id,
        source_generation=state._source_generation,
    )
    return _digest(snapshot.as_dict())


def create_capture_broker(
    *,
    broker_id: str,
    source_id: str,
    capture_owner_id: str,
    capacity: int,
    provenance_refs: tuple[str, ...],
) -> CaptureBrokerState:
    """Create a legacy handle backed by the canonical WP-709 broker."""

    broker_id = _text("broker_id", broker_id)
    source_id = _text("source_id", source_id)
    capture_owner_id = _text("capture_owner_id", capture_owner_id)
    if type(capacity) is not int or not 1 <= capacity <= 64:
        raise CaptureBrokerError("capacity must be an integer in [1, 64]")
    provenance_refs = _refs("provenance_refs", provenance_refs)

    policy = CaptureBrokerPolicy(
        policy_id=f"compat-policy:{broker_id}",
        generation=1,
        max_frames_per_source=capacity,
        max_frame_age_ns=(2**63) - 1,
        max_read_window_frames=capacity,
        provenance_refs=tuple(
            sorted(
                set(
                    provenance_refs
                    + (
                        "compat-adapter:retina-capture-broker",
                        f"canonical-module:{CANONICAL_CAPTURE_BROKER_MODULE}",
                    )
                )
            )
        ),
    )
    canonical = CanonicalRetinaCaptureBroker(policy=policy)
    source = PerceptionSource(
        source_id=source_id,
        kind=_source_kind(source_id),
        clock_domain="compat:legacy-local-monotonic",
        capture_owner_id=capture_owner_id,
        provenance_refs=provenance_refs,
    )
    canonical.register_source(source=source, generation=1)
    lease = canonical.acquire_owner(
        source_id=source_id,
        source_generation=1,
        capture_owner_id=capture_owner_id,
        opened_monotonic_ns=0,
        provenance_refs=provenance_refs,
    )
    return CaptureBrokerState(
        broker_id=broker_id,
        source_id=source_id,
        capture_owner_id=capture_owner_id,
        capacity=capacity,
        origin_provenance_refs=provenance_refs,
        _canonical=canonical,
        _lease_id=lease.lease_id,
    )


def publish_frame_ref(
    *,
    state: CaptureBrokerState,
    publisher_owner_id: str,
    frame_ref: CaptureFrameRef,
) -> CaptureBrokerState:
    """Publish through the canonical broker and return the same compatibility handle."""

    if type(state) is not CaptureBrokerState:
        raise CaptureBrokerError("state must be a concrete compatibility CaptureBrokerState")
    publisher_owner_id = _text("publisher_owner_id", publisher_owner_id)
    if publisher_owner_id != state.capture_owner_id:
        raise CaptureBrokerError("publisher_owner_id must equal the declared capture_owner_id")
    if type(frame_ref) is not CaptureFrameRef:
        raise CaptureBrokerError("frame_ref must be a concrete compatibility CaptureFrameRef")
    if frame_ref.source_id != state.source_id:
        raise CaptureBrokerError("frame_ref source_id does not match broker source_id")
    if frame_ref.source_sequence != state.generation:
        raise CaptureBrokerError("legacy frame source_sequence must strictly increase from zero")

    state._canonical.publish_frame(
        source_id=state.source_id,
        source_generation=state._source_generation,
        capture_owner_id=state.capture_owner_id,
        lease_id=state._lease_id,
        capture_monotonic_ns=frame_ref.captured_monotonic_ns,
        frame_sha256=frame_ref.payload_sha256,
        payload_size_bytes=0,
        provenance_refs=tuple(
            sorted(
                set(
                    frame_ref.provenance_refs
                    + (
                        f"compat-frame-ref-id:{frame_ref.frame_ref_id}",
                        f"compat-source-sequence:{frame_ref.source_sequence}",
                        f"compat-input-sha256:{frame_ref.sha256()}",
                    )
                )
            )
        ),
    )
    state._last_capture_monotonic_ns = frame_ref.captured_monotonic_ns
    return state


def _legacy_from_canonical(frame: CanonicalCaptureFrameRef) -> CaptureFrameRef:
    compat_id = next(
        (
            ref.removeprefix("compat-frame-ref-id:")
            for ref in frame.provenance_refs
            if ref.startswith("compat-frame-ref-id:")
        ),
        frame.frame_ref_id,
    )
    compat_sequence_text = next(
        (
            ref.removeprefix("compat-source-sequence:")
            for ref in frame.provenance_refs
            if ref.startswith("compat-source-sequence:")
        ),
        str(frame.source_sequence - 1),
    )
    try:
        compat_sequence = int(compat_sequence_text)
    except ValueError as exc:
        raise CaptureBrokerError("invalid compatibility source sequence provenance") from exc
    return CaptureFrameRef(
        frame_ref_id=compat_id,
        source_id=frame.source_id,
        source_sequence=compat_sequence,
        captured_monotonic_ns=frame.capture_monotonic_ns,
        payload_sha256=frame.frame_sha256,
        provenance_refs=tuple(
            sorted(
                set(
                    frame.provenance_refs
                    + (f"canonical-frame-ref-sha256:{frame.sha256()}",)
                )
            )
        ),
    )


def latest_frame_refs(state: CaptureBrokerState, *, limit: int) -> tuple[CaptureFrameRef, ...]:
    """Read retained references through the canonical broker's read-only fan-out API."""

    if type(state) is not CaptureBrokerState:
        raise CaptureBrokerError("state must be a concrete compatibility CaptureBrokerState")
    if type(limit) is not int or not 1 <= limit <= state.capacity:
        raise CaptureBrokerError("limit must be in [1, capacity]")
    if state.generation == 0:
        return ()
    window = state._canonical.read_since(
        source_id=state.source_id,
        source_generation=state._source_generation,
        consumer_id=f"compat-reader:{state.broker_id}",
        after_sequence=0,
        now_monotonic_ns=state._last_capture_monotonic_ns,
    )
    translated = tuple(_legacy_from_canonical(item) for item in window.frame_refs)
    return translated[-limit:]


__all__ = [
    "BROKER_STATE_SCHEMA",
    "CANONICAL_CAPTURE_BROKER_MODULE",
    "CAPTURE_BROKER_AUTHORITY",
    "CaptureBrokerError",
    "CaptureBrokerState",
    "CaptureFrameRef",
    "FRAME_REF_SCHEMA",
    "create_capture_broker",
    "latest_frame_refs",
    "publish_frame_ref",
]
