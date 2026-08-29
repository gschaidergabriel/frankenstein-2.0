"""Deterministic single-owner/multiple-reader capture broker for Frankenstein 2.0.

F2-WP-709 generation 1.

This module provides the hardware-independent ownership, bounded FrameRef ring, fan-out,
eviction and source-generation semantics required by the Perception Fabric. It deliberately
does not open cameras/displays/browser transports, retain raw frame bytes, perform perception,
persist state, execute bridge/network I/O, call a model/provider, or mint world/effect/
completion authority. Local host adapters later bind real OS/device capture handles to this
prebuilt contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, ClassVar

from .perception_fabric import PerceptionSource

BROKER_POLICY_SCHEMA = "FRANKENSTEIN2_CAPTURE_BROKER_POLICY/v1"
OWNER_LEASE_SCHEMA = "FRANKENSTEIN2_CAPTURE_OWNER_LEASE/v1"
FRAME_REF_SCHEMA = "FRANKENSTEIN2_CAPTURE_FRAME_REF/v1"
READ_WINDOW_SCHEMA = "FRANKENSTEIN2_CAPTURE_READ_WINDOW/v1"
SOURCE_SNAPSHOT_SCHEMA = "FRANKENSTEIN2_CAPTURE_SOURCE_SNAPSHOT/v1"
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


def _positive(name: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise CaptureBrokerError(f"{name} must be an integer > 0")
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


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CaptureBrokerError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureBrokerPolicy:
    policy_id: str
    generation: int
    max_frames_per_source: int
    max_frame_age_ns: int
    max_read_window_frames: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = BROKER_POLICY_SCHEMA
    classification: ClassVar[str] = "CAPTURE_BROKER_BOUND_POLICY_NOT_DEVICE_OR_WORLD_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _nonnegative("generation", self.generation)
        if type(self.max_frames_per_source) is not int or not 1 <= self.max_frames_per_source <= 4096:
            raise CaptureBrokerError("max_frames_per_source must be an integer in [1, 4096]")
        _positive("max_frame_age_ns", self.max_frame_age_ns)
        if (
            type(self.max_read_window_frames) is not int
            or not 1 <= self.max_read_window_frames <= self.max_frames_per_source
        ):
            raise CaptureBrokerError(
                "max_read_window_frames must be in [1, max_frames_per_source]"
            )
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "max_frames_per_source": self.max_frames_per_source,
            "max_frame_age_ns": self.max_frame_age_ns,
            "max_read_window_frames": self.max_read_window_frames,
            "device_execution_authority": "NONE",
            "world_truth_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureOwnerLease:
    lease_id: str
    source_id: str
    source_generation: int
    capture_owner_id: str
    opened_monotonic_ns: int
    source_sha256: str
    policy_sha256: str
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = OWNER_LEASE_SCHEMA
    classification: ClassVar[str] = "LOGICAL_CAPTURE_OWNERSHIP_LEASE_NOT_PHYSICAL_DEVICE_HANDLE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "lease_id", _text("lease_id", self.lease_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative("source_generation", self.source_generation)
        object.__setattr__(
            self, "capture_owner_id", _text("capture_owner_id", self.capture_owner_id)
        )
        _nonnegative("opened_monotonic_ns", self.opened_monotonic_ns)
        _sha256("source_sha256", self.source_sha256)
        _sha256("policy_sha256", self.policy_sha256)
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "lease_id": self.lease_id,
            "source_id": self.source_id,
            "source_generation": self.source_generation,
            "capture_owner_id": self.capture_owner_id,
            "opened_monotonic_ns": self.opened_monotonic_ns,
            "source_sha256": self.source_sha256,
            "policy_sha256": self.policy_sha256,
            "physical_device_handle": None,
            "opens_physical_device": False,
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureFrameRef:
    frame_ref_id: str
    source_id: str
    source_generation: int
    capture_owner_id: str
    lease_id: str
    source_sequence: int
    capture_monotonic_ns: int
    frame_sha256: str
    payload_size_bytes: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = FRAME_REF_SCHEMA
    classification: ClassVar[str] = "RAM_FRAME_REFERENCE_METADATA_NOT_OBSERVATION_OR_WORLD_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_ref_id", _text("frame_ref_id", self.frame_ref_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative("source_generation", self.source_generation)
        object.__setattr__(
            self, "capture_owner_id", _text("capture_owner_id", self.capture_owner_id)
        )
        object.__setattr__(self, "lease_id", _text("lease_id", self.lease_id))
        _positive("source_sequence", self.source_sequence)
        _nonnegative("capture_monotonic_ns", self.capture_monotonic_ns)
        _sha256("frame_sha256", self.frame_sha256)
        _nonnegative("payload_size_bytes", self.payload_size_bytes)
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("provenance_refs", self.provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "frame_ref_id": self.frame_ref_id,
            "source_id": self.source_id,
            "source_generation": self.source_generation,
            "capture_owner_id": self.capture_owner_id,
            "lease_id": self.lease_id,
            "source_sequence": self.source_sequence,
            "capture_monotonic_ns": self.capture_monotonic_ns,
            "frame_sha256": self.frame_sha256,
            "payload_size_bytes": self.payload_size_bytes,
            "raw_payload": None,
            "persistence": "RAM_REFERENCE_ONLY",
            "observation_authority": "NONE",
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureReadWindow:
    consumer_id: str
    source_id: str
    source_generation: int
    after_sequence: int
    frame_refs: tuple[CaptureFrameRef, ...]
    missed_before_sequence: int | None
    latest_sequence: int

    schema: ClassVar[str] = READ_WINDOW_SCHEMA
    classification: ClassVar[str] = "READ_ONLY_CAPTURE_FANOUT_WINDOW_NOT_CAPTURE_OWNER"

    def __post_init__(self) -> None:
        object.__setattr__(self, "consumer_id", _text("consumer_id", self.consumer_id))
        object.__setattr__(self, "source_id", _text("source_id", self.source_id))
        _nonnegative("source_generation", self.source_generation)
        _nonnegative("after_sequence", self.after_sequence)
        if type(self.frame_refs) is not tuple or any(
            type(item) is not CaptureFrameRef for item in self.frame_refs
        ):
            raise CaptureBrokerError(
                "frame_refs must be an immutable tuple of concrete CaptureFrameRef values"
            )
        sequences = [item.source_sequence for item in self.frame_refs]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise CaptureBrokerError("frame_refs must be strictly sequence-ordered")
        if any(
            item.source_id != self.source_id
            or item.source_generation != self.source_generation
            for item in self.frame_refs
        ):
            raise CaptureBrokerError("frame_refs source/generation mismatch")
        if self.missed_before_sequence is not None:
            _positive("missed_before_sequence", self.missed_before_sequence)
        _nonnegative("latest_sequence", self.latest_sequence)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "consumer_id": self.consumer_id,
            "source_id": self.source_id,
            "source_generation": self.source_generation,
            "after_sequence": self.after_sequence,
            "frame_refs": [item.as_dict() for item in self.frame_refs],
            "missed_before_sequence": self.missed_before_sequence,
            "latest_sequence": self.latest_sequence,
            "opens_capture_device": False,
            "capture_owner_authority": "NONE",
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureSourceSnapshot:
    source_id: str
    source_generation: int
    source_sha256: str
    active_capture_owner_id: str | None
    active_lease_id: str | None
    retained_frame_ref_ids: tuple[str, ...]
    oldest_sequence: int | None
    newest_sequence: int | None
    evicted_frame_count: int

    schema: ClassVar[str] = SOURCE_SNAPSHOT_SCHEMA
    classification: ClassVar[str] = "CAPTURE_BROKER_STATE_SNAPSHOT_NOT_SENSOR_OR_WORLD_AUTHORITY"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "source_id": self.source_id,
            "source_generation": self.source_generation,
            "source_sha256": self.source_sha256,
            "active_capture_owner_id": self.active_capture_owner_id,
            "active_lease_id": self.active_lease_id,
            "retained_frame_ref_ids": list(self.retained_frame_ref_ids),
            "oldest_sequence": self.oldest_sequence,
            "newest_sequence": self.newest_sequence,
            "evicted_frame_count": self.evicted_frame_count,
            "raw_frame_count": 0,
            "persistence": "NONE",
            "world_truth_authority": "NONE",
        }


@dataclass(slots=True)
class _SourceState:
    source: PerceptionSource
    generation: int
    active_lease: CaptureOwnerLease | None = None
    frames: list[CaptureFrameRef] = field(default_factory=list)
    next_sequence: int = 1
    last_capture_monotonic_ns: int | None = None
    evicted_frame_count: int = 0


class RetinaCaptureBroker:
    """Hardware-independent capture ownership and bounded FrameRef fan-out."""

    def __init__(self, *, policy: CaptureBrokerPolicy) -> None:
        if type(policy) is not CaptureBrokerPolicy:
            raise CaptureBrokerError("policy must be a concrete CaptureBrokerPolicy")
        self._policy = policy
        self._sources: dict[str, _SourceState] = {}

    @property
    def policy(self) -> CaptureBrokerPolicy:
        return self._policy

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._sources))

    def register_source(self, *, source: PerceptionSource, generation: int) -> None:
        if type(source) is not PerceptionSource:
            raise CaptureBrokerError("source must be a concrete PerceptionSource")
        _nonnegative("generation", generation)
        if source.source_id in self._sources:
            raise CaptureBrokerError("source_id is already registered")
        self._sources[source.source_id] = _SourceState(source=source, generation=generation)

    def acquire_owner(
        self,
        *,
        source_id: str,
        source_generation: int,
        capture_owner_id: str,
        opened_monotonic_ns: int,
        provenance_refs: tuple[str, ...],
    ) -> CaptureOwnerLease:
        state = self._state(source_id, source_generation)
        capture_owner_id = _text("capture_owner_id", capture_owner_id)
        _nonnegative("opened_monotonic_ns", opened_monotonic_ns)
        provenance = _refs("provenance_refs", provenance_refs)
        if capture_owner_id != state.source.capture_owner_id:
            raise CaptureBrokerError(
                "capture_owner_id must match the canonical PerceptionSource capture_owner_id"
            )
        if state.active_lease is not None:
            if state.active_lease.capture_owner_id == capture_owner_id:
                return state.active_lease
            raise CaptureBrokerError("source already has a different active capture owner")
        payload = {
            "source_id": state.source.source_id,
            "source_generation": state.generation,
            "capture_owner_id": capture_owner_id,
            "opened_monotonic_ns": opened_monotonic_ns,
            "source_sha256": state.source.sha256(),
            "policy_sha256": self._policy.sha256(),
        }
        lease = CaptureOwnerLease(
            lease_id="capture-lease:" + _digest(payload)[:24],
            source_id=state.source.source_id,
            source_generation=state.generation,
            capture_owner_id=capture_owner_id,
            opened_monotonic_ns=opened_monotonic_ns,
            source_sha256=state.source.sha256(),
            policy_sha256=self._policy.sha256(),
            provenance_refs=tuple(
                sorted(
                    set(
                        provenance
                        + state.source.provenance_refs
                        + self._policy.provenance_refs
                    )
                )
            ),
        )
        state.active_lease = lease
        return lease

    def release_owner(
        self,
        *,
        source_id: str,
        source_generation: int,
        capture_owner_id: str,
        lease_id: str,
    ) -> None:
        state = self._state(source_id, source_generation)
        capture_owner_id = _text("capture_owner_id", capture_owner_id)
        lease_id = _text("lease_id", lease_id)
        if state.active_lease is None:
            raise CaptureBrokerError("source has no active capture owner")
        if (
            state.active_lease.capture_owner_id != capture_owner_id
            or state.active_lease.lease_id != lease_id
        ):
            raise CaptureBrokerError("release does not match the active capture owner lease")
        state.active_lease = None

    def publish_frame(
        self,
        *,
        source_id: str,
        source_generation: int,
        capture_owner_id: str,
        lease_id: str,
        capture_monotonic_ns: int,
        frame_sha256: str,
        payload_size_bytes: int,
        provenance_refs: tuple[str, ...],
    ) -> CaptureFrameRef:
        state = self._state(source_id, source_generation)
        capture_owner_id = _text("capture_owner_id", capture_owner_id)
        lease_id = _text("lease_id", lease_id)
        _nonnegative("capture_monotonic_ns", capture_monotonic_ns)
        frame_sha256 = _sha256("frame_sha256", frame_sha256)
        _nonnegative("payload_size_bytes", payload_size_bytes)
        provenance = _refs("provenance_refs", provenance_refs)
        lease = state.active_lease
        if lease is None:
            raise CaptureBrokerError("publish requires an active capture owner")
        if lease.capture_owner_id != capture_owner_id or lease.lease_id != lease_id:
            raise CaptureBrokerError("publish does not match the active capture owner lease")
        if (
            state.last_capture_monotonic_ns is not None
            and capture_monotonic_ns <= state.last_capture_monotonic_ns
        ):
            raise CaptureBrokerError("capture_monotonic_ns must strictly increase per source")

        sequence = state.next_sequence
        frame_payload = {
            "source_id": source_id,
            "source_generation": source_generation,
            "capture_owner_id": capture_owner_id,
            "lease_id": lease_id,
            "source_sequence": sequence,
            "capture_monotonic_ns": capture_monotonic_ns,
            "frame_sha256": frame_sha256,
            "payload_size_bytes": payload_size_bytes,
        }
        frame_ref = CaptureFrameRef(
            frame_ref_id="frame-ref:" + _digest(frame_payload)[:24],
            source_id=source_id,
            source_generation=source_generation,
            capture_owner_id=capture_owner_id,
            lease_id=lease_id,
            source_sequence=sequence,
            capture_monotonic_ns=capture_monotonic_ns,
            frame_sha256=frame_sha256,
            payload_size_bytes=payload_size_bytes,
            provenance_refs=tuple(sorted(set(provenance + lease.provenance_refs))),
        )
        state.frames.append(frame_ref)
        state.next_sequence += 1
        state.last_capture_monotonic_ns = capture_monotonic_ns
        self._evict(state, now_monotonic_ns=capture_monotonic_ns)
        return frame_ref

    def read_since(
        self,
        *,
        source_id: str,
        source_generation: int,
        consumer_id: str,
        after_sequence: int,
        now_monotonic_ns: int,
    ) -> CaptureReadWindow:
        state = self._state(source_id, source_generation)
        consumer_id = _text("consumer_id", consumer_id)
        _nonnegative("after_sequence", after_sequence)
        _nonnegative("now_monotonic_ns", now_monotonic_ns)
        self._evict(state, now_monotonic_ns=now_monotonic_ns)

        missed: int | None = None
        if state.frames:
            oldest = state.frames[0].source_sequence
            if after_sequence < oldest - 1:
                missed = oldest
        candidates = [item for item in state.frames if item.source_sequence > after_sequence]
        candidates = candidates[: self._policy.max_read_window_frames]
        latest = state.next_sequence - 1
        return CaptureReadWindow(
            consumer_id=consumer_id,
            source_id=source_id,
            source_generation=source_generation,
            after_sequence=after_sequence,
            frame_refs=tuple(candidates),
            missed_before_sequence=missed,
            latest_sequence=latest,
        )

    def rebind_source(
        self,
        *,
        source_id: str,
        current_generation: int,
        new_source: PerceptionSource,
        new_generation: int,
    ) -> None:
        state = self._state(source_id, current_generation)
        if type(new_source) is not PerceptionSource:
            raise CaptureBrokerError("new_source must be a concrete PerceptionSource")
        if new_source.source_id != source_id:
            raise CaptureBrokerError("new_source must preserve source_id across rebind")
        _nonnegative("new_generation", new_generation)
        if new_generation <= current_generation:
            raise CaptureBrokerError("new_generation must strictly exceed current_generation")
        if state.active_lease is not None:
            raise CaptureBrokerError("source must be released before rebind")
        state.evicted_frame_count += len(state.frames)
        state.source = new_source
        state.generation = new_generation
        state.frames.clear()
        state.next_sequence = 1
        state.last_capture_monotonic_ns = None

    def snapshot(self, *, source_id: str, source_generation: int) -> CaptureSourceSnapshot:
        state = self._state(source_id, source_generation)
        frames = tuple(state.frames)
        return CaptureSourceSnapshot(
            source_id=source_id,
            source_generation=source_generation,
            source_sha256=state.source.sha256(),
            active_capture_owner_id=(
                state.active_lease.capture_owner_id if state.active_lease is not None else None
            ),
            active_lease_id=(state.active_lease.lease_id if state.active_lease is not None else None),
            retained_frame_ref_ids=tuple(item.frame_ref_id for item in frames),
            oldest_sequence=(frames[0].source_sequence if frames else None),
            newest_sequence=(frames[-1].source_sequence if frames else None),
            evicted_frame_count=state.evicted_frame_count,
        )

    def _state(self, source_id: str, generation: int) -> _SourceState:
        source_id = _text("source_id", source_id)
        _nonnegative("source_generation", generation)
        state = self._sources.get(source_id)
        if state is None:
            raise CaptureBrokerError("source_id is not registered")
        if state.generation != generation:
            raise CaptureBrokerError("source generation is stale or mismatched")
        return state

    def _evict(self, state: _SourceState, *, now_monotonic_ns: int) -> None:
        _nonnegative("now_monotonic_ns", now_monotonic_ns)
        removed = 0
        while state.frames:
            oldest = state.frames[0]
            if now_monotonic_ns < oldest.capture_monotonic_ns:
                raise CaptureBrokerError("now_monotonic_ns regressed before retained frame time")
            age = now_monotonic_ns - oldest.capture_monotonic_ns
            over_age = age > self._policy.max_frame_age_ns
            over_capacity = len(state.frames) > self._policy.max_frames_per_source
            if not over_age and not over_capacity:
                break
            state.frames.pop(0)
            removed += 1
        state.evicted_frame_count += removed


__all__ = [
    "BROKER_POLICY_SCHEMA",
    "CaptureBrokerError",
    "CaptureBrokerPolicy",
    "CaptureFrameRef",
    "CaptureOwnerLease",
    "CaptureReadWindow",
    "CaptureSourceSnapshot",
    "FRAME_REF_SCHEMA",
    "OWNER_LEASE_SCHEMA",
    "READ_WINDOW_SCHEMA",
    "RetinaCaptureBroker",
    "SOURCE_SNAPSHOT_SCHEMA",
]
