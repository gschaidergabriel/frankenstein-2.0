"""Independent complete-range event-source authority for F2-WP-900 G8.

This module closes the repository-scope *origin* hole in negative re-entry
observation.  The condition-aware observation caller must not be able to mint a
causal negative by supplying its own sequence bounds, gap/drop counters or trace
digest.  Instead, an independent source adapter records the source sequence and
factory-origin GWT runtime witnesses, seals one bounded range, and hands the
immutable receipt to causal admission.

Repository construction/tests prove only the typed/fail-closed boundary.  They
do not prove that a real target runtime used an actually independent source.
That remains an external execution/readback obligation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.gwt_reentry_observation_window import ReentryObservationIdentity
from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessError,
    GwtRuntimeWitnessReceipt,
    validate_gwt_runtime_witness_receipt,
)

INDEPENDENT_REENTRY_SOURCE_RANGE_SCHEMA = "FRANKENSTEIN2_GWT_INDEPENDENT_REENTRY_SOURCE_RANGE/v1"
INDEPENDENT_REENTRY_SOURCE_EVENT_SCHEMA = "FRANKENSTEIN2_GWT_INDEPENDENT_REENTRY_SOURCE_EVENT/v1"

_RANGE_FACTORY = object()
_EVENT_FACTORY = object()
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512


class IndependentReentrySourceRangeError(ValueError):
    """Fail-closed G8 independent-source range validation error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise IndependentReentrySourceRangeError(f"{name} must be non-empty trimmed text")
    if len(value) > _MAX_TEXT:
        raise IndependentReentrySourceRangeError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise IndependentReentrySourceRangeError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise IndependentReentrySourceRangeError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 1:
        raise IndependentReentrySourceRangeError(f"{name} must be a positive integer")
    return value


def _nonnegative_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise IndependentReentrySourceRangeError(f"{name} must be a non-negative integer")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise IndependentReentrySourceRangeError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise IndependentReentrySourceRangeError("provenance_refs must not be empty")
    if len(set(refs)) != len(refs):
        raise IndependentReentrySourceRangeError("provenance_refs must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise IndependentReentrySourceRangeError("value is not canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class IndependentReentrySourceIdentity:
    """Identity fixed by the event-source adapter, not by causal admission."""

    authority_id: str
    authority_build_sha256: str
    exact_source_sha256: str
    boot_id_sha256: str
    execution_context_sha256: str
    trace_source_sha256: str
    filter_schema_sha256: str
    clock_domain: str
    clock_mapping_sha256: str
    observer_identity: str
    runtime_instance_id: str
    process_identity: str
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("authority_id", "clock_domain", "observer_identity", "runtime_instance_id", "process_identity"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "authority_build_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
            "execution_context_sha256",
            "trace_source_sha256",
            "filter_schema_sha256",
            "clock_mapping_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "authority_id": self.authority_id,
            "authority_build_sha256": self.authority_build_sha256,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "execution_context_sha256": self.execution_context_sha256,
            "trace_source_sha256": self.trace_source_sha256,
            "filter_schema_sha256": self.filter_schema_sha256,
            "clock_domain": self.clock_domain,
            "clock_mapping_sha256": self.clock_mapping_sha256,
            "observer_identity": self.observer_identity,
            "runtime_instance_id": self.runtime_instance_id,
            "process_identity": self.process_identity,
            "provenance_refs": list(self.provenance_refs),
        }

    def matches_observation(self, identity: ReentryObservationIdentity) -> bool:
        if type(identity) is not ReentryObservationIdentity:
            return False
        return (
            self.exact_source_sha256 == identity.exact_source_sha256
            and self.boot_id_sha256 == identity.boot_id_sha256
            and self.execution_context_sha256 == identity.execution_context_sha256
            and self.trace_source_sha256 == identity.trace_source_sha256
            and self.filter_schema_sha256 == identity.filter_schema_sha256
            and self.clock_domain == identity.clock_domain
            and self.clock_mapping_sha256 == identity.clock_mapping_sha256
            and self.observer_identity == identity.observer_identity
            and self.runtime_instance_id == identity.runtime_instance_id
            and self.process_identity == identity.process_identity
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class IndependentReentrySourceEvent:
    sequence: int
    observed_monotonic_ns: int
    raw_event_sha256: str
    runtime_witness: GwtRuntimeWitnessReceipt | None
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = INDEPENDENT_REENTRY_SOURCE_EVENT_SCHEMA

    def __post_init__(self) -> None:
        _positive_int("sequence", self.sequence)
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        object.__setattr__(self, "raw_event_sha256", _sha256("raw_event_sha256", self.raw_event_sha256))
        if self.runtime_witness is not None and type(self.runtime_witness) is not GwtRuntimeWitnessReceipt:
            raise IndependentReentrySourceRangeError("runtime_witness must be exact GwtRuntimeWitnessReceipt or None")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "sequence": self.sequence,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "raw_event_sha256": self.raw_event_sha256,
            "runtime_witness_sha256": None if self.runtime_witness is None else self.runtime_witness.sha256(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class IndependentReentrySourceRangeReceipt:
    identity: IndependentReentrySourceIdentity
    observer_started_monotonic_ns: int
    window_start_monotonic_ns: int
    window_end_monotonic_ns: int
    observer_finalized_monotonic_ns: int
    source_sequence_start: int
    source_sequence_end: int
    events: tuple[IndependentReentrySourceEvent, ...]
    sequence_gap_count: int
    dropped_event_count: int
    overflow_count: int
    raw_trace_sha256: str
    finalized: bool
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = INDEPENDENT_REENTRY_SOURCE_RANGE_SCHEMA
    evidence_scope = "INDEPENDENT_EVENT_SOURCE_RANGE_CANDIDATE_REQUIRES_EXTERNAL_SOURCE_ADMISSION"
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    physical_grid10_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        if type(self.identity) is not IndependentReentrySourceIdentity:
            raise IndependentReentrySourceRangeError("identity must be exact IndependentReentrySourceIdentity")
        for name in (
            "observer_started_monotonic_ns", "window_start_monotonic_ns", "window_end_monotonic_ns",
            "observer_finalized_monotonic_ns", "source_sequence_start", "source_sequence_end",
        ):
            _positive_int(name, getattr(self, name))
        if type(self.events) is not tuple or not self.events:
            raise IndependentReentrySourceRangeError("events must be a non-empty tuple")
        if any(type(event) is not IndependentReentrySourceEvent for event in self.events):
            raise IndependentReentrySourceRangeError("events contain unsupported values")
        for name in ("sequence_gap_count", "dropped_event_count", "overflow_count"):
            _nonnegative_int(name, getattr(self, name))
        object.__setattr__(self, "raw_trace_sha256", _sha256("raw_trace_sha256", self.raw_trace_sha256))
        if type(self.finalized) is not bool:
            raise IndependentReentrySourceRangeError("finalized must be boolean")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @property
    def captured_sequence_start(self) -> int:
        return self.events[0].sequence

    @property
    def captured_sequence_end(self) -> int:
        return self.events[-1].sequence

    @property
    def complete(self) -> bool:
        return (
            self.finalized
            and self.observer_started_monotonic_ns < self.window_start_monotonic_ns
            and self.observer_finalized_monotonic_ns > self.window_end_monotonic_ns
            and self.window_start_monotonic_ns < self.window_end_monotonic_ns
            and self.source_sequence_start <= self.source_sequence_end
            and self.captured_sequence_start == self.source_sequence_start
            and self.captured_sequence_end == self.source_sequence_end
            and self.sequence_gap_count == 0
            and self.dropped_event_count == 0
            and self.overflow_count == 0
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evidence_scope": self.evidence_scope,
            "identity": self.identity.as_dict(),
            "observer_started_monotonic_ns": self.observer_started_monotonic_ns,
            "window_start_monotonic_ns": self.window_start_monotonic_ns,
            "window_end_monotonic_ns": self.window_end_monotonic_ns,
            "observer_finalized_monotonic_ns": self.observer_finalized_monotonic_ns,
            "source_sequence_start": self.source_sequence_start,
            "source_sequence_end": self.source_sequence_end,
            "captured_sequence_start": self.captured_sequence_start,
            "captured_sequence_end": self.captured_sequence_end,
            "events": [event.as_dict() for event in self.events],
            "sequence_gap_count": self.sequence_gap_count,
            "dropped_event_count": self.dropped_event_count,
            "overflow_count": self.overflow_count,
            "raw_trace_sha256": self.raw_trace_sha256,
            "finalized": self.finalized,
            "complete": self.complete,
            "provenance_refs": list(self.provenance_refs),
            "repository_ci_credit": self.repository_ci_credit,
            "target_environment_component_runtime_credit": self.target_environment_component_runtime_credit,
            "runtime_credit": self.runtime_credit,
            "semantic_gwt_runtime_credit": self.semantic_gwt_runtime_credit,
            "jspace_runtime_credit": self.jspace_runtime_credit,
            "physical_grid10_credit": self.physical_grid10_credit,
            "effect_credit": self.effect_credit,
            "training_credit": self.training_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def matching_runtime_witnesses(self, observation_identity: ReentryObservationIdentity) -> tuple[GwtRuntimeWitnessReceipt, ...]:
        if not self.identity.matches_observation(observation_identity):
            return ()
        matched: list[GwtRuntimeWitnessReceipt] = []
        for event in self.events:
            witness = event.runtime_witness
            if witness is None:
                continue
            identity = witness.identity
            if (
                self.window_start_monotonic_ns < event.observed_monotonic_ns < self.window_end_monotonic_ns
                and identity.exact_source_sha256 == observation_identity.exact_source_sha256
                and identity.boot_id_sha256 == observation_identity.boot_id_sha256
                and identity.runtime_instance_id == observation_identity.runtime_instance_id
                and identity.process_identity == observation_identity.process_identity
                and witness.canonical_reentry_key == observation_identity.expected_reentry_key_sha256
                and witness.binding_sha256 == observation_identity.expected_reentry_binding_sha256
                and witness.recipient_cell_id == observation_identity.expected_recipient_cell_id
            ):
                matched.append(witness)
        return tuple(matched)


class IndependentReentryEventSourceAuthority:
    """Recorder owned by the event-source side of the observation boundary."""

    def __init__(self, *, identity: IndependentReentrySourceIdentity) -> None:
        if type(identity) is not IndependentReentrySourceIdentity:
            raise IndependentReentrySourceRangeError("identity must be exact IndependentReentrySourceIdentity")
        self._identity = identity
        self._events: list[IndependentReentrySourceEvent] = []
        self._dropped_event_count = 0
        self._overflow_count = 0
        self._sealed = False

    def record_event(self, *, sequence: int, observed_monotonic_ns: int, raw_event_sha256: str,
                     runtime_witness: GwtRuntimeWitnessReceipt | None = None) -> None:
        if self._sealed:
            raise IndependentReentrySourceRangeError("source authority is already sealed")
        if runtime_witness is not None:
            try:
                validate_gwt_runtime_witness_receipt(runtime_witness)
            except GwtRuntimeWitnessError as exc:
                raise IndependentReentrySourceRangeError(f"invalid runtime witness origin: {exc}") from exc
            runtime_identity = runtime_witness.identity
            if runtime_identity.exact_source_sha256 != self._identity.exact_source_sha256:
                raise IndependentReentrySourceRangeError("runtime witness exact source mismatch")
            if runtime_identity.boot_id_sha256 != self._identity.boot_id_sha256:
                raise IndependentReentrySourceRangeError("runtime witness boot mismatch")
            if runtime_identity.runtime_instance_id != self._identity.runtime_instance_id:
                raise IndependentReentrySourceRangeError("runtime witness runtime instance mismatch")
            if runtime_identity.process_identity != self._identity.process_identity:
                raise IndependentReentrySourceRangeError("runtime witness process mismatch")
        event = IndependentReentrySourceEvent(
            sequence=_positive_int("sequence", sequence),
            observed_monotonic_ns=_positive_int("observed_monotonic_ns", observed_monotonic_ns),
            raw_event_sha256=_sha256("raw_event_sha256", raw_event_sha256),
            runtime_witness=runtime_witness,
            _factory_seal=_EVENT_FACTORY,
        )
        object.__setattr__(event, "_factory_payload_sha256", _digest(event.as_dict()))
        if self._events:
            previous = self._events[-1]
            if event.sequence <= previous.sequence:
                raise IndependentReentrySourceRangeError("source sequence must increase strictly")
            if event.observed_monotonic_ns <= previous.observed_monotonic_ns:
                raise IndependentReentrySourceRangeError("source event clock must increase strictly")
        self._events.append(event)

    def note_dropped_events(self, count: int = 1) -> None:
        if self._sealed:
            raise IndependentReentrySourceRangeError("source authority is already sealed")
        self._dropped_event_count += _positive_int("count", count)

    def note_overflow(self, count: int = 1) -> None:
        if self._sealed:
            raise IndependentReentrySourceRangeError("source authority is already sealed")
        self._overflow_count += _positive_int("count", count)

    def seal_range(self, *, observer_started_monotonic_ns: int, window_start_monotonic_ns: int,
                   window_end_monotonic_ns: int, observer_finalized_monotonic_ns: int,
                   source_sequence_start: int, source_sequence_end: int, finalized: bool,
                   provenance_refs: Iterable[str]) -> IndependentReentrySourceRangeReceipt:
        if self._sealed:
            raise IndependentReentrySourceRangeError("source authority is already sealed")
        if not self._events:
            raise IndependentReentrySourceRangeError("cannot seal a source range without captured source events")
        source_sequence_start = _positive_int("source_sequence_start", source_sequence_start)
        source_sequence_end = _positive_int("source_sequence_end", source_sequence_end)
        gaps = sum(max(0, current.sequence - previous.sequence - 1) for previous, current in zip(self._events, self._events[1:]))
        raw_trace_sha256 = _digest({
            "identity": self._identity.as_dict(),
            "source_sequence_start": source_sequence_start,
            "source_sequence_end": source_sequence_end,
            "events": [event.as_dict() for event in self._events],
        })
        receipt = IndependentReentrySourceRangeReceipt(
            identity=self._identity,
            observer_started_monotonic_ns=_positive_int("observer_started_monotonic_ns", observer_started_monotonic_ns),
            window_start_monotonic_ns=_positive_int("window_start_monotonic_ns", window_start_monotonic_ns),
            window_end_monotonic_ns=_positive_int("window_end_monotonic_ns", window_end_monotonic_ns),
            observer_finalized_monotonic_ns=_positive_int("observer_finalized_monotonic_ns", observer_finalized_monotonic_ns),
            source_sequence_start=source_sequence_start,
            source_sequence_end=source_sequence_end,
            events=tuple(self._events),
            sequence_gap_count=gaps,
            dropped_event_count=self._dropped_event_count,
            overflow_count=self._overflow_count,
            raw_trace_sha256=raw_trace_sha256,
            finalized=finalized,
            provenance_refs=_refs(provenance_refs),
            _factory_seal=_RANGE_FACTORY,
        )
        object.__setattr__(receipt, "_factory_payload_sha256", _digest(receipt.as_dict()))
        self._sealed = True
        return receipt


def validate_independent_reentry_source_range(receipt: IndependentReentrySourceRangeReceipt) -> None:
    """Verify factory origin, immutability and every embedded witness origin."""
    if type(receipt) is not IndependentReentrySourceRangeReceipt or receipt._factory_seal is not _RANGE_FACTORY:
        raise IndependentReentrySourceRangeError("source range receipt lacks authority factory origin")
    if receipt._factory_payload_sha256 != _digest(receipt.as_dict()):
        raise IndependentReentrySourceRangeError("source range receipt payload changed after seal")
    for event in receipt.events:
        if event._factory_seal is not _EVENT_FACTORY:
            raise IndependentReentrySourceRangeError("source event lacks authority factory origin")
        if event._factory_payload_sha256 != _digest(event.as_dict()):
            raise IndependentReentrySourceRangeError("source event payload changed after seal")
        if event.runtime_witness is not None:
            try:
                validate_gwt_runtime_witness_receipt(event.runtime_witness)
            except GwtRuntimeWitnessError as exc:
                raise IndependentReentrySourceRangeError(f"invalid embedded runtime witness: {exc}") from exc
    sequences = tuple(event.sequence for event in receipt.events)
    times = tuple(event.observed_monotonic_ns for event in receipt.events)
    if any(current <= previous for previous, current in zip(sequences, sequences[1:])):
        raise IndependentReentrySourceRangeError("source range sequence is not strictly increasing")
    if any(current <= previous for previous, current in zip(times, times[1:])):
        raise IndependentReentrySourceRangeError("source range event clock is not strictly increasing")
    expected_gaps = sum(max(0, current - previous - 1) for previous, current in zip(sequences, sequences[1:]))
    if expected_gaps != receipt.sequence_gap_count:
        raise IndependentReentrySourceRangeError("source range gap count mismatch")


def assert_source_range_matches_observation(receipt: IndependentReentrySourceRangeReceipt,
                                            observation_identity: ReentryObservationIdentity, *,
                                            window_start_monotonic_ns: int,
                                            window_end_monotonic_ns: int) -> None:
    validate_independent_reentry_source_range(receipt)
    if not receipt.identity.matches_observation(observation_identity):
        raise IndependentReentrySourceRangeError("source range identity does not match observation identity")
    if receipt.window_start_monotonic_ns != window_start_monotonic_ns:
        raise IndependentReentrySourceRangeError("source range/observation window start mismatch")
    if receipt.window_end_monotonic_ns != window_end_monotonic_ns:
        raise IndependentReentrySourceRangeError("source range/observation window end mismatch")


__all__ = [
    "INDEPENDENT_REENTRY_SOURCE_EVENT_SCHEMA",
    "INDEPENDENT_REENTRY_SOURCE_RANGE_SCHEMA",
    "IndependentReentryEventSourceAuthority",
    "IndependentReentrySourceEvent",
    "IndependentReentrySourceIdentity",
    "IndependentReentrySourceRangeError",
    "IndependentReentrySourceRangeReceipt",
    "assert_source_range_matches_observation",
    "validate_independent_reentry_source_range",
]
