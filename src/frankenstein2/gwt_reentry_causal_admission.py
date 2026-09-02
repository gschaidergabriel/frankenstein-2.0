"""Fail-closed causal admission fence for F2-WP-900 generation 8.

The lower-level G8 observation receipt intentionally preserves caller-supplied
trace-completeness metadata as a candidate. Positive REENTRY is recorder-origin
bound. A separately sealed event-source range can contradict a caller-negative
candidate, but repository construction of that range does *not* prove that its
recorder was operationally independent from the condition-aware caller.

Therefore this repository module never mints causal-negative credit from a
range receipt alone. A future target-runtime promotion must bind the exact range
recorder to an independently controlled upstream event source through external
runtime evidence/reconciliation. FACTORY_ORIGIN != INDEPENDENT_SOURCE_PROVENANCE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.gwt_reentry_observation_window import (
    NO_REENTRY_OBSERVED,
    REENTRY_OBSERVATION_UNKNOWN,
    REENTRY_OBSERVED,
    ReentryObservationWindowReceipt,
    validate_reentry_observation_window,
)

CAUSAL_REENTRY_ADMISSION_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_REENTRY_ADMISSION/v3"
INDEPENDENT_EVENT_SOURCE_RANGE_SCHEMA = "FRANKENSTEIN2_GWT_INDEPENDENT_EVENT_SOURCE_RANGE/v1"

ADMITTED_POSITIVE_REENTRY = "ADMITTED_POSITIVE_REENTRY"
# Historical compatibility constant. Repository-only APIs intentionally do not
# emit this status after the G8 self-minted-range falsifier.
ADMITTED_NEGATIVE_REENTRY_ABSENCE = "ADMITTED_NEGATIVE_REENTRY_ABSENCE"
NEGATIVE_ABSENCE_UNPROVEN = "NEGATIVE_ABSENCE_UNPROVEN_SOURCE_AUTHORITY_MISSING"
NEGATIVE_ABSENCE_CONTRADICTED = "NEGATIVE_ABSENCE_CONTRADICTED_BY_SOURCE_RANGE"
NEGATIVE_RANGE_MISMATCH = "NEGATIVE_RANGE_DOES_NOT_BIND_OBSERVATION"
OBSERVATION_UNKNOWN = "OBSERVATION_UNKNOWN"

SOURCE_EVENT_OTHER = "OTHER"
SOURCE_EVENT_GWT_REENTRY = "GWT_REENTRY"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_SOURCE_EVENT_FACTORY = object()
_SOURCE_RANGE_FACTORY = object()


class IndependentRangeError(ValueError):
    """Fail-closed independent source-range validation error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise IndependentRangeError(f"{name} must be non-empty trimmed text")
    if len(value) > _MAX_TEXT:
        raise IndependentRangeError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise IndependentRangeError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise IndependentRangeError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 1:
        raise IndependentRangeError(f"{name} must be a positive integer")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise IndependentRangeError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise IndependentRangeError("provenance_refs must not be empty")
    if len(set(refs)) != len(refs):
        raise IndependentRangeError("provenance_refs must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise IndependentRangeError("value is not canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class IndependentEventSourceEvent:
    source_sequence: int
    observed_monotonic_ns: int
    event_kind: str
    payload_sha256: str
    canonical_reentry_key_sha256: str | None = None
    binding_sha256: str | None = None
    recipient_cell_id: str | None = None
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        _positive_int("source_sequence", self.source_sequence)
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        if self.event_kind not in {SOURCE_EVENT_OTHER, SOURCE_EVENT_GWT_REENTRY}:
            raise IndependentRangeError("unsupported independent source event kind")
        object.__setattr__(self, "payload_sha256", _sha256("payload_sha256", self.payload_sha256))
        if self.event_kind == SOURCE_EVENT_GWT_REENTRY:
            if self.canonical_reentry_key_sha256 is None or self.binding_sha256 is None or self.recipient_cell_id is None:
                raise IndependentRangeError("GWT_REENTRY event requires key, binding and recipient")
            object.__setattr__(
                self,
                "canonical_reentry_key_sha256",
                _sha256("canonical_reentry_key_sha256", self.canonical_reentry_key_sha256),
            )
            object.__setattr__(self, "binding_sha256", _sha256("binding_sha256", self.binding_sha256))
            object.__setattr__(self, "recipient_cell_id", _text("recipient_cell_id", self.recipient_cell_id))
        elif any(
            value is not None
            for value in (self.canonical_reentry_key_sha256, self.binding_sha256, self.recipient_cell_id)
        ):
            raise IndependentRangeError("OTHER event cannot carry reentry identity fields")

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_sequence": self.source_sequence,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "event_kind": self.event_kind,
            "payload_sha256": self.payload_sha256,
            "canonical_reentry_key_sha256": self.canonical_reentry_key_sha256,
            "binding_sha256": self.binding_sha256,
            "recipient_cell_id": self.recipient_cell_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class IndependentEventSourceRangeReceipt:
    trace_source_sha256: str
    filter_schema_sha256: str
    clock_domain: str
    clock_mapping_sha256: str
    observer_identity: str
    observer_started_monotonic_ns: int
    window_start_monotonic_ns: int
    window_end_monotonic_ns: int
    observer_finalized_monotonic_ns: int
    source_sequence_start: int
    source_sequence_end: int
    events: tuple[IndependentEventSourceEvent, ...]
    raw_trace_sha256: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = INDEPENDENT_EVENT_SOURCE_RANGE_SCHEMA
    evidence_scope = "EVENT_SOURCE_RANGE_CANDIDATE_REQUIRES_TARGET_INDEPENDENCE_BINDING"
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
        for name in ("trace_source_sha256", "filter_schema_sha256", "clock_mapping_sha256", "raw_trace_sha256"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        object.__setattr__(self, "clock_domain", _text("clock_domain", self.clock_domain))
        object.__setattr__(self, "observer_identity", _text("observer_identity", self.observer_identity))
        for name in (
            "observer_started_monotonic_ns",
            "window_start_monotonic_ns",
            "window_end_monotonic_ns",
            "observer_finalized_monotonic_ns",
            "source_sequence_start",
            "source_sequence_end",
        ):
            _positive_int(name, getattr(self, name))
        if type(self.events) is not tuple or not self.events:
            raise IndependentRangeError("events must be a non-empty tuple")
        if any(
            type(event) is not IndependentEventSourceEvent or event._factory_seal is not _SOURCE_EVENT_FACTORY
            for event in self.events
        ):
            raise IndependentRangeError("event lacks source-range recorder origin")
        expected_sequences = tuple(range(self.source_sequence_start, self.source_sequence_end + 1))
        actual_sequences = tuple(event.source_sequence for event in self.events)
        if actual_sequences != expected_sequences:
            raise IndependentRangeError("source range must contain every claimed sequence exactly once")
        times = tuple(event.observed_monotonic_ns for event in self.events)
        if any(later <= earlier for earlier, later in zip(times, times[1:])):
            raise IndependentRangeError("source event times must be strictly increasing")
        if not (
            self.observer_started_monotonic_ns < self.window_start_monotonic_ns
            <= times[0]
            <= times[-1]
            <= self.window_end_monotonic_ns
            < self.observer_finalized_monotonic_ns
        ):
            raise IndependentRangeError("source range does not close the requested observation window")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))
        expected_raw = _digest(
            {
                "trace_source_sha256": self.trace_source_sha256,
                "filter_schema_sha256": self.filter_schema_sha256,
                "clock_domain": self.clock_domain,
                "clock_mapping_sha256": self.clock_mapping_sha256,
                "source_sequence_start": self.source_sequence_start,
                "source_sequence_end": self.source_sequence_end,
                "events": [event.as_dict() for event in self.events],
            }
        )
        if self.raw_trace_sha256 != expected_raw:
            raise IndependentRangeError("raw_trace_sha256 does not match canonical source range")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evidence_scope": self.evidence_scope,
            "trace_source_sha256": self.trace_source_sha256,
            "filter_schema_sha256": self.filter_schema_sha256,
            "clock_domain": self.clock_domain,
            "clock_mapping_sha256": self.clock_mapping_sha256,
            "observer_identity": self.observer_identity,
            "observer_started_monotonic_ns": self.observer_started_monotonic_ns,
            "window_start_monotonic_ns": self.window_start_monotonic_ns,
            "window_end_monotonic_ns": self.window_end_monotonic_ns,
            "observer_finalized_monotonic_ns": self.observer_finalized_monotonic_ns,
            "source_sequence_start": self.source_sequence_start,
            "source_sequence_end": self.source_sequence_end,
            "events": [event.as_dict() for event in self.events],
            "raw_trace_sha256": self.raw_trace_sha256,
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


class IndependentEventSourceRangeRecorder:
    """Append-only structural range recorder.

    Important: possession of this public recorder is *not* proof of operational
    independence. Its receipts are candidate evidence only until target-runtime
    wiring proves the recorder is upstream of condition-aware logic.
    """

    def __init__(
        self,
        *,
        trace_source_sha256: str,
        filter_schema_sha256: str,
        clock_domain: str,
        clock_mapping_sha256: str,
        observer_identity: str,
        observer_started_monotonic_ns: int,
        window_start_monotonic_ns: int,
        provenance_refs: Iterable[str],
    ) -> None:
        self._trace_source_sha256 = _sha256("trace_source_sha256", trace_source_sha256)
        self._filter_schema_sha256 = _sha256("filter_schema_sha256", filter_schema_sha256)
        self._clock_domain = _text("clock_domain", clock_domain)
        self._clock_mapping_sha256 = _sha256("clock_mapping_sha256", clock_mapping_sha256)
        self._observer_identity = _text("observer_identity", observer_identity)
        self._observer_started_monotonic_ns = _positive_int(
            "observer_started_monotonic_ns", observer_started_monotonic_ns
        )
        self._window_start_monotonic_ns = _positive_int("window_start_monotonic_ns", window_start_monotonic_ns)
        if self._observer_started_monotonic_ns >= self._window_start_monotonic_ns:
            raise IndependentRangeError("source observer must start before window")
        self._provenance_refs = _refs(provenance_refs)
        self._events: list[IndependentEventSourceEvent] = []
        self._sealed = False

    def observe(
        self,
        *,
        source_sequence: int,
        observed_monotonic_ns: int,
        event_kind: str,
        payload_sha256: str,
        canonical_reentry_key_sha256: str | None = None,
        binding_sha256: str | None = None,
        recipient_cell_id: str | None = None,
    ) -> None:
        if self._sealed:
            raise IndependentRangeError("source range recorder is sealed")
        event = IndependentEventSourceEvent(
            source_sequence=source_sequence,
            observed_monotonic_ns=observed_monotonic_ns,
            event_kind=event_kind,
            payload_sha256=payload_sha256,
            canonical_reentry_key_sha256=canonical_reentry_key_sha256,
            binding_sha256=binding_sha256,
            recipient_cell_id=recipient_cell_id,
            _factory_seal=_SOURCE_EVENT_FACTORY,
        )
        if event.observed_monotonic_ns < self._window_start_monotonic_ns:
            raise IndependentRangeError("source event predates observation window")
        if self._events:
            if event.source_sequence != self._events[-1].source_sequence + 1:
                raise IndependentRangeError("source sequence must be contiguous")
            if event.observed_monotonic_ns <= self._events[-1].observed_monotonic_ns:
                raise IndependentRangeError("source event clock must advance monotonically")
        self._events.append(event)

    def seal(
        self,
        *,
        window_end_monotonic_ns: int,
        observer_finalized_monotonic_ns: int,
        provenance_refs: Iterable[str] = (),
    ) -> IndependentEventSourceRangeReceipt:
        if self._sealed:
            raise IndependentRangeError("source range recorder is sealed")
        if not self._events:
            raise IndependentRangeError("cannot seal an empty source range")
        window_end_monotonic_ns = _positive_int("window_end_monotonic_ns", window_end_monotonic_ns)
        observer_finalized_monotonic_ns = _positive_int(
            "observer_finalized_monotonic_ns", observer_finalized_monotonic_ns
        )
        if self._events[-1].observed_monotonic_ns > window_end_monotonic_ns:
            raise IndependentRangeError("last source event lies after window end")
        if observer_finalized_monotonic_ns <= window_end_monotonic_ns:
            raise IndependentRangeError("source observer must finalize after window end")
        self._sealed = True
        raw_trace_sha256 = _digest(
            {
                "trace_source_sha256": self._trace_source_sha256,
                "filter_schema_sha256": self._filter_schema_sha256,
                "clock_domain": self._clock_domain,
                "clock_mapping_sha256": self._clock_mapping_sha256,
                "source_sequence_start": self._events[0].source_sequence,
                "source_sequence_end": self._events[-1].source_sequence,
                "events": [event.as_dict() for event in self._events],
            }
        )
        refs = self._provenance_refs + tuple(_text("provenance_ref", ref) for ref in provenance_refs)
        receipt = IndependentEventSourceRangeReceipt(
            trace_source_sha256=self._trace_source_sha256,
            filter_schema_sha256=self._filter_schema_sha256,
            clock_domain=self._clock_domain,
            clock_mapping_sha256=self._clock_mapping_sha256,
            observer_identity=self._observer_identity,
            observer_started_monotonic_ns=self._observer_started_monotonic_ns,
            window_start_monotonic_ns=self._window_start_monotonic_ns,
            window_end_monotonic_ns=window_end_monotonic_ns,
            observer_finalized_monotonic_ns=observer_finalized_monotonic_ns,
            source_sequence_start=self._events[0].source_sequence,
            source_sequence_end=self._events[-1].source_sequence,
            events=tuple(self._events),
            raw_trace_sha256=raw_trace_sha256,
            provenance_refs=refs,
            _factory_seal=_SOURCE_RANGE_FACTORY,
        )
        object.__setattr__(receipt, "_factory_payload_sha256", _digest(receipt.as_dict()))
        return receipt


def validate_independent_event_source_range(value: IndependentEventSourceRangeReceipt) -> None:
    if type(value) is not IndependentEventSourceRangeReceipt or value._factory_seal is not _SOURCE_RANGE_FACTORY:
        raise IndependentRangeError("independent source range lacks recorder origin")
    if value._factory_payload_sha256 != _digest(value.as_dict()):
        raise IndependentRangeError("independent source range changed after seal")


@dataclass(frozen=True, slots=True, kw_only=True)
class CausalReentryAdmission:
    observation_sha256: str
    observation_status: str
    admission_status: str
    causal_positive_credit: int
    causal_negative_credit: int
    independent_negative_range_authority: bool
    blocker: str | None
    independent_range_sha256: str | None = None

    schema = CAUSAL_REENTRY_ADMISSION_SCHEMA
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    physical_grid10_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "observation_sha256": self.observation_sha256,
            "observation_status": self.observation_status,
            "admission_status": self.admission_status,
            "causal_positive_credit": self.causal_positive_credit,
            "causal_negative_credit": self.causal_negative_credit,
            "independent_negative_range_authority": self.independent_negative_range_authority,
            "independent_range_sha256": self.independent_range_sha256,
            "blocker": self.blocker,
            "semantic_gwt_runtime_credit": self.semantic_gwt_runtime_credit,
            "jspace_runtime_credit": self.jspace_runtime_credit,
            "physical_grid10_credit": self.physical_grid10_credit,
            "effect_credit": self.effect_credit,
            "training_credit": self.training_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }


def _admission(
    observation: ReentryObservationWindowReceipt,
    *,
    status: str,
    positive: int,
    negative: int,
    independent: bool,
    blocker: str | None,
    source_range: IndependentEventSourceRangeReceipt | None = None,
) -> CausalReentryAdmission:
    return CausalReentryAdmission(
        observation_sha256=observation.sha256(),
        observation_status=observation.status,
        admission_status=status,
        causal_positive_credit=positive,
        causal_negative_credit=negative,
        independent_negative_range_authority=independent,
        independent_range_sha256=None if source_range is None else source_range.sha256(),
        blocker=blocker,
    )


def admit_reentry_observation(observation: ReentryObservationWindowReceipt) -> CausalReentryAdmission:
    """Legacy G8 admission: never trusts caller-asserted negative absence."""
    validate_reentry_observation_window(observation)
    if observation.status == REENTRY_OBSERVED:
        return _admission(
            observation,
            status=ADMITTED_POSITIVE_REENTRY,
            positive=1,
            negative=0,
            independent=False,
            blocker="INDEPENDENT_NEGATIVE_COMPLETE_RANGE_AUTHORITY_MISSING",
        )
    if observation.status == NO_REENTRY_OBSERVED:
        return _admission(
            observation,
            status=NEGATIVE_ABSENCE_UNPROVEN,
            positive=0,
            negative=0,
            independent=False,
            blocker="INDEPENDENT_NEGATIVE_COMPLETE_RANGE_AUTHORITY_MISSING",
        )
    if observation.status == REENTRY_OBSERVATION_UNKNOWN:
        return _admission(
            observation,
            status=OBSERVATION_UNKNOWN,
            positive=0,
            negative=0,
            independent=False,
            blocker="OBSERVATION_INCOMPLETE_OR_NEGATIVE_SOURCE_AUTHORITY_MISSING",
        )
    raise ValueError(f"unsupported G8 observation status: {observation.status}")


def _range_binds_observation(
    observation: ReentryObservationWindowReceipt,
    source_range: IndependentEventSourceRangeReceipt,
) -> bool:
    trace = observation.trace_completeness
    return (
        trace is not None
        and source_range.trace_source_sha256 == observation.identity.trace_source_sha256
        and source_range.filter_schema_sha256 == observation.identity.filter_schema_sha256
        and source_range.clock_domain == observation.identity.clock_domain
        and source_range.clock_mapping_sha256 == observation.identity.clock_mapping_sha256
        and source_range.observer_started_monotonic_ns == trace.observer_started_monotonic_ns
        and source_range.window_start_monotonic_ns == trace.window_start_monotonic_ns
        and source_range.window_end_monotonic_ns == trace.window_end_monotonic_ns
        and source_range.observer_finalized_monotonic_ns == trace.observer_finalized_monotonic_ns
        and source_range.source_sequence_start == trace.source_sequence_start
        and source_range.source_sequence_end == trace.source_sequence_end
        and source_range.raw_trace_sha256 == trace.raw_trace_sha256
    )


def _range_contains_expected_reentry(
    observation: ReentryObservationWindowReceipt,
    source_range: IndependentEventSourceRangeReceipt,
) -> bool:
    identity = observation.identity
    return any(
        event.event_kind == SOURCE_EVENT_GWT_REENTRY
        and event.canonical_reentry_key_sha256 == identity.expected_reentry_key_sha256
        and event.binding_sha256 == identity.expected_reentry_binding_sha256
        and event.recipient_cell_id == identity.expected_recipient_cell_id
        for event in source_range.events
    )


def admit_reentry_observation_with_independent_range(
    observation: ReentryObservationWindowReceipt,
    source_range: IndependentEventSourceRangeReceipt,
) -> CausalReentryAdmission:
    """Cross-check a candidate range without treating its factory seal as independence.

    A matching re-entry can conservatively contradict a negative claim. Absence
    in this repository-constructible range remains unproven and earns zero
    causal-negative credit until exact target runtime evidence establishes that
    the recorder was source-owned/upstream and unavailable to condition-aware
    caller self-certification.
    """
    validate_reentry_observation_window(observation)
    validate_independent_event_source_range(source_range)

    if observation.status == REENTRY_OBSERVED:
        return _admission(
            observation,
            status=ADMITTED_POSITIVE_REENTRY,
            positive=1,
            negative=0,
            independent=False,
            blocker=None,
            source_range=source_range,
        )

    if observation.status == REENTRY_OBSERVATION_UNKNOWN:
        return _admission(
            observation,
            status=OBSERVATION_UNKNOWN,
            positive=0,
            negative=0,
            independent=False,
            blocker="OBSERVATION_INCOMPLETE",
            source_range=source_range,
        )

    if observation.status != NO_REENTRY_OBSERVED:
        raise ValueError(f"unsupported G8 observation status: {observation.status}")

    if not _range_binds_observation(observation, source_range):
        return _admission(
            observation,
            status=NEGATIVE_RANGE_MISMATCH,
            positive=0,
            negative=0,
            independent=False,
            blocker="INDEPENDENT_RANGE_IDENTITY_OR_WINDOW_MISMATCH",
            source_range=source_range,
        )

    if _range_contains_expected_reentry(observation, source_range):
        return _admission(
            observation,
            status=NEGATIVE_ABSENCE_CONTRADICTED,
            positive=0,
            negative=0,
            independent=False,
            blocker="MATCHING_REENTRY_PRESENT_IN_SOURCE_RANGE_CANDIDATE",
            source_range=source_range,
        )

    return _admission(
        observation,
        status=NEGATIVE_ABSENCE_UNPROVEN,
        positive=0,
        negative=0,
        independent=False,
        blocker="TARGET_SOURCE_INDEPENDENCE_BINDING_NOT_PROVEN",
        source_range=source_range,
    )


__all__ = [
    "ADMITTED_NEGATIVE_REENTRY_ABSENCE",
    "ADMITTED_POSITIVE_REENTRY",
    "CAUSAL_REENTRY_ADMISSION_SCHEMA",
    "CausalReentryAdmission",
    "INDEPENDENT_EVENT_SOURCE_RANGE_SCHEMA",
    "IndependentEventSourceEvent",
    "IndependentEventSourceRangeReceipt",
    "IndependentEventSourceRangeRecorder",
    "IndependentRangeError",
    "NEGATIVE_ABSENCE_CONTRADICTED",
    "NEGATIVE_ABSENCE_UNPROVEN",
    "NEGATIVE_RANGE_MISMATCH",
    "OBSERVATION_UNKNOWN",
    "SOURCE_EVENT_GWT_REENTRY",
    "SOURCE_EVENT_OTHER",
    "admit_reentry_observation",
    "admit_reentry_observation_with_independent_range",
    "validate_independent_event_source_range",
]
