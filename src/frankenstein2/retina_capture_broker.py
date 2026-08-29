"""Single-owner, bounded-reference capture broker for the F2 Perception Fabric.

The broker stores only immutable frame/sample references, never raw bytes. Host-specific
camera/display/browser capture code supplies those references. Exactly one declared owner may
publish for a source; any number of downstream readers may inspect the bounded ring state.
Live refs, retained drop diagnostics and runtime provenance are all bounded. Long history is
represented by a rolling prior-state digest rather than an ever-growing in-memory list.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

FRAME_REF_SCHEMA = "FRANKENSTEIN2_CAPTURE_FRAME_REF/v1"
BROKER_STATE_SCHEMA = "FRANKENSTEIN2_CAPTURE_BROKER_STATE/v3"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CaptureBrokerError(ValueError):
    """Fail-closed capture-broker contract error."""


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


def _refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple or (not allow_empty and not value):
        suffix = "immutable tuple" if allow_empty else "non-empty immutable tuple"
        raise CaptureBrokerError(f"{name} must be a {suffix}")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise CaptureBrokerError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _ordered_refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if type(value) is not tuple or (not allow_empty and not value):
        suffix = "immutable tuple" if allow_empty else "non-empty immutable tuple"
        raise CaptureBrokerError(f"{name} must be a {suffix}")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise CaptureBrokerError(f"{name} must not contain duplicates")
    return refs


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureFrameRef:
    frame_ref_id: str
    source_id: str
    source_sequence: int
    captured_monotonic_ns: int
    payload_sha256: str
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = FRAME_REF_SCHEMA
    classification: ClassVar[str] = "RAM_REFERENCE_ONLY_NO_RAW_FRAME_OR_WORLD_TRUTH"

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
            "world_truth_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureBrokerState:
    broker_id: str
    source_id: str
    capture_owner_id: str
    capacity: int
    generation: int
    frame_refs: tuple[CaptureFrameRef, ...]
    dropped_frame_count: int
    dropped_frame_ref_ids: tuple[str, ...]
    origin_provenance_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = BROKER_STATE_SCHEMA
    classification: ClassVar[str] = "BOUNDED_SINGLE_OWNER_CAPTURE_REFERENCE_STATE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "broker_id", _text("broker_id", self.broker_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        object.__setattr__(self, "capture_owner_id", _text("capture_owner_id", self.capture_owner_id))
        if type(self.capacity) is not int or not 1 <= self.capacity <= 64:
            raise CaptureBrokerError("capacity must be an integer in [1, 64]")
        _nonnegative("generation", self.generation)
        if type(self.frame_refs) is not tuple or any(type(item) is not CaptureFrameRef for item in self.frame_refs):
            raise CaptureBrokerError("frame_refs must be an immutable tuple of concrete CaptureFrameRef values")
        if len(self.frame_refs) > self.capacity:
            raise CaptureBrokerError("frame_refs exceed bounded broker capacity")
        ids = [item.frame_ref_id for item in self.frame_refs]
        if len(ids) != len(set(ids)):
            raise CaptureBrokerError("frame_ref_id must be unique in broker ring")
        if any(item.source_id != self.source_id for item in self.frame_refs):
            raise CaptureBrokerError("broker ring may contain only its exact source_id")
        sequences = [item.source_sequence for item in self.frame_refs]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise CaptureBrokerError("broker ring source_sequence must be unique and increasing")
        _nonnegative("dropped_frame_count", self.dropped_frame_count)
        recent_drops = _ordered_refs("dropped_frame_ref_ids", self.dropped_frame_ref_ids, allow_empty=True)
        if len(recent_drops) > self.capacity:
            raise CaptureBrokerError("retained dropped_frame_ref_ids exceed bounded broker capacity")
        if self.dropped_frame_count < len(recent_drops):
            raise CaptureBrokerError("dropped_frame_count cannot be smaller than retained drop ids")
        object.__setattr__(self, "dropped_frame_ref_ids", recent_drops)
        object.__setattr__(self, "origin_provenance_refs", _refs("origin_provenance_refs", self.origin_provenance_refs))
        current_provenance = _refs("provenance_refs", self.provenance_refs)
        # Origin + one prior-state link + one current-frame link is the intended constant-size form.
        if len(current_provenance) > len(self.origin_provenance_refs) + 2:
            raise CaptureBrokerError("runtime provenance exceeds bounded rolling-chain form")
        object.__setattr__(self, "provenance_refs", current_provenance)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "broker_id": self.broker_id,
            "source_id": self.source_id,
            "capture_owner_id": self.capture_owner_id,
            "capacity": self.capacity,
            "generation": self.generation,
            "frame_refs": [item.as_dict() for item in self.frame_refs],
            "dropped_frame_count": self.dropped_frame_count,
            "recent_dropped_frame_ref_ids": list(self.dropped_frame_ref_ids),
            "retained_drop_metadata_bound": self.capacity,
            "origin_provenance_refs": list(self.origin_provenance_refs),
            "runtime_provenance_refs": list(self.provenance_refs),
            "runtime_provenance_bound": len(self.origin_provenance_refs) + 2,
            "raw_frame_persistence": False,
            "consumer_count_limit": None,
            "world_truth_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def create_capture_broker(
    *,
    broker_id: str,
    source_id: str,
    capture_owner_id: str,
    capacity: int,
    provenance_refs: tuple[str, ...],
) -> CaptureBrokerState:
    """Create an empty bounded ring for one source and one declared capture owner."""
    origin = _refs("provenance_refs", provenance_refs)
    return CaptureBrokerState(
        broker_id=broker_id,
        source_id=source_id,
        capture_owner_id=capture_owner_id,
        capacity=capacity,
        generation=0,
        frame_refs=(),
        dropped_frame_count=0,
        dropped_frame_ref_ids=(),
        origin_provenance_refs=origin,
        provenance_refs=origin,
    )


def publish_frame_ref(
    *,
    state: CaptureBrokerState,
    publisher_owner_id: str,
    frame_ref: CaptureFrameRef,
) -> CaptureBrokerState:
    """Return the next immutable state; overflow drops oldest with bounded metadata."""
    if type(state) is not CaptureBrokerState:
        raise CaptureBrokerError("state must be a concrete CaptureBrokerState")
    publisher_owner_id = _text("publisher_owner_id", publisher_owner_id)
    if publisher_owner_id != state.capture_owner_id:
        raise CaptureBrokerError("only the exact capture_owner_id may publish to this source broker")
    if type(frame_ref) is not CaptureFrameRef:
        raise CaptureBrokerError("frame_ref must be a concrete CaptureFrameRef")
    if frame_ref.source_id != state.source_id:
        raise CaptureBrokerError("frame_ref source_id does not match broker source_id")
    if any(existing.frame_ref_id == frame_ref.frame_ref_id for existing in state.frame_refs):
        raise CaptureBrokerError("duplicate frame_ref_id")
    if state.frame_refs:
        latest = state.frame_refs[-1]
        if frame_ref.source_sequence <= latest.source_sequence:
            raise CaptureBrokerError("new frame source_sequence must strictly increase")
        if frame_ref.captured_monotonic_ns < latest.captured_monotonic_ns:
            raise CaptureBrokerError("new frame captured_monotonic_ns must not regress")
    ring = list(state.frame_refs) + [frame_ref]
    recent_drops = list(state.dropped_frame_ref_ids)
    dropped_count = state.dropped_frame_count
    while len(ring) > state.capacity:
        recent_drops.append(ring.pop(0).frame_ref_id)
        dropped_count += 1
    recent_drops = recent_drops[-state.capacity :]
    # Rolling provenance: keep immutable origin refs plus exact previous-state and new-frame digests.
    provenance = set(state.origin_provenance_refs)
    provenance.add(f"prior-broker-sha256:{state.sha256()}")
    provenance.add(f"frame-ref-sha256:{frame_ref.sha256()}")
    return CaptureBrokerState(
        broker_id=state.broker_id,
        source_id=state.source_id,
        capture_owner_id=state.capture_owner_id,
        capacity=state.capacity,
        generation=state.generation + 1,
        frame_refs=tuple(ring),
        dropped_frame_count=dropped_count,
        dropped_frame_ref_ids=tuple(recent_drops),
        origin_provenance_refs=state.origin_provenance_refs,
        provenance_refs=tuple(sorted(provenance)),
    )


def latest_frame_refs(state: CaptureBrokerState, *, limit: int) -> tuple[CaptureFrameRef, ...]:
    """Read references without acquiring/reopening the underlying capture device."""
    if type(state) is not CaptureBrokerState:
        raise CaptureBrokerError("state must be a concrete CaptureBrokerState")
    if type(limit) is not int or limit < 0:
        raise CaptureBrokerError("limit must be an integer >= 0")
    if limit == 0:
        return ()
    return state.frame_refs[-limit:]


__all__ = [
    "BROKER_STATE_SCHEMA",
    "FRAME_REF_SCHEMA",
    "CaptureBrokerError",
    "CaptureBrokerState",
    "CaptureFrameRef",
    "create_capture_broker",
    "latest_frame_refs",
    "publish_frame_ref",
]
