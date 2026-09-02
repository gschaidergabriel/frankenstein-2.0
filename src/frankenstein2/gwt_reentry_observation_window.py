"""Condition-blind bounded re-entry observation for F2-WP-900 generation 8.

Both experimental arms use the same observer ABI. The observer never receives an
arm label, expected boolean, broadcast-present flag, or expected result.

A negative re-entry observation is admissible only when the captured trace proves
window completeness: the observer/filter were active before the window, remained
live through finalization, the admitted filtered sequence range is contiguous,
and the dropped-event counter stayed at zero. Any missing completeness condition
yields UNKNOWN, never a negative claim.

Objects produced here are mechanism-evidence candidates only. They mint no
runtime, semantic GWT/J-Space, physical GRID10, effect, training, completion, or
whole-system credit by construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Callable, Iterable

REENTRY_OBSERVATION_WINDOW_SCHEMA = "FRANKENSTEIN2_GWT_REENTRY_OBSERVATION_WINDOW/v2"
MATCHED_REENTRY_MECHANISM_SCHEMA = "FRANKENSTEIN2_GWT_MATCHED_REENTRY_MECHANISM/v2"

REENTRY_OBSERVED = "REENTRY_OBSERVED"
NO_REENTRY_OBSERVED = "NO_REENTRY_OBSERVED_IN_COMPLETE_WINDOW"
REENTRY_OBSERVATION_UNKNOWN = "REENTRY_OBSERVATION_UNKNOWN_INCOMPLETE_WINDOW"

MECHANISM_REENTRY_DIFFERENCE = "MECHANISM_REENTRY_DIFFERENCE_CANDIDATE"
NO_MECHANISM_REENTRY_DIFFERENCE = "NO_MECHANISM_REENTRY_DIFFERENCE_OBSERVED"
MECHANISM_COMPARISON_UNKNOWN = "MECHANISM_REENTRY_COMPARISON_UNKNOWN"

TRACE_REENTRY = "REENTRY"
TRACE_OTHER = "TRACE_OTHER"
WINDOW_OPEN = "WINDOW_OPEN"
WINDOW_TERMINAL = "WINDOW_TERMINAL"
WINDOW_ABORT = "WINDOW_ABORT"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_RECEIPT_FACTORY = object()
_PAIR_FACTORY = object()


class ReentryObservationError(ValueError):
    """Fail-closed G8 observation error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ReentryObservationError(f"{name} must be non-empty trimmed text")
    if len(value) > _MAX_TEXT:
        raise ReentryObservationError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ReentryObservationError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise ReentryObservationError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 1:
        raise ReentryObservationError(f"{name} must be a positive integer")
    return value


def _nonnegative_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ReentryObservationError(f"{name} must be a non-negative integer")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ReentryObservationError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise ReentryObservationError("provenance_refs must not be empty")
    if len(set(refs)) != len(refs):
        raise ReentryObservationError("provenance_refs must not contain duplicates")
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
        raise ReentryObservationError("value is not canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class ReentryObservationIdentity:
    exact_source_sha256: str
    boot_id_sha256: str
    execution_context_sha256: str
    task_id: str
    task_input_sha256: str
    pre_state_sha256: str
    task_executor_sha256: str
    observation_protocol_sha256: str
    filter_sha256: str
    clock_domain: str
    observer_identity: str
    runtime_instance_id: str
    process_identity: str
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "exact_source_sha256",
            "boot_id_sha256",
            "execution_context_sha256",
            "task_input_sha256",
            "pre_state_sha256",
            "task_executor_sha256",
            "observation_protocol_sha256",
            "filter_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        for name in (
            "task_id",
            "clock_domain",
            "observer_identity",
            "runtime_instance_id",
            "process_identity",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def matched_context_dict(self) -> dict[str, str]:
        return {
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "execution_context_sha256": self.execution_context_sha256,
            "task_id": self.task_id,
            "task_input_sha256": self.task_input_sha256,
            "pre_state_sha256": self.pre_state_sha256,
            "task_executor_sha256": self.task_executor_sha256,
            "observation_protocol_sha256": self.observation_protocol_sha256,
            "filter_sha256": self.filter_sha256,
            "clock_domain": self.clock_domain,
            "observer_identity": self.observer_identity,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.matched_context_dict(),
            "runtime_instance_id": self.runtime_instance_id,
            "process_identity": self.process_identity,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class ReentryObservationEvent:
    phase: str
    observed_monotonic_ns: int
    evidence_ref: str
    evidence_sha256: str
    source_sequence: int | None = None

    def __post_init__(self) -> None:
        allowed = {WINDOW_OPEN, TRACE_REENTRY, TRACE_OTHER, WINDOW_TERMINAL, WINDOW_ABORT}
        if self.phase not in allowed:
            raise ReentryObservationError("unsupported observation phase")
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        object.__setattr__(self, "evidence_ref", _text("evidence_ref", self.evidence_ref))
        object.__setattr__(self, "evidence_sha256", _sha256("evidence_sha256", self.evidence_sha256))
        if self.phase in {TRACE_REENTRY, TRACE_OTHER}:
            if self.source_sequence is None:
                raise ReentryObservationError("trace event requires source_sequence")
            _nonnegative_int("source_sequence", self.source_sequence)
        elif self.source_sequence is not None:
            raise ReentryObservationError("window boundary event cannot carry source_sequence")

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "evidence_ref": self.evidence_ref,
            "evidence_sha256": self.evidence_sha256,
            "source_sequence": self.source_sequence,
        }


def _trace_events(events: tuple[ReentryObservationEvent, ...]) -> tuple[ReentryObservationEvent, ...]:
    return tuple(event for event in events if event.phase in {TRACE_REENTRY, TRACE_OTHER})


def _trace_digest(
    *,
    events: tuple[ReentryObservationEvent, ...],
    source_sequence_at_open: int,
    source_sequence_at_close: int | None,
    dropped_event_count_at_open: int,
    dropped_event_count_at_close: int | None,
) -> str:
    return _digest(
        {
            "filtered_trace_events": [event.as_dict() for event in _trace_events(events)],
            "source_sequence_at_open": source_sequence_at_open,
            "source_sequence_at_close": source_sequence_at_close,
            "dropped_event_count_at_open": dropped_event_count_at_open,
            "dropped_event_count_at_close": dropped_event_count_at_close,
        }
    )


def _completeness_reasons(
    *,
    events: tuple[ReentryObservationEvent, ...],
    observer_started_monotonic_ns: int,
    filter_bound_monotonic_ns: int,
    window_start_monotonic_ns: int,
    window_end_monotonic_ns: int | None,
    observer_live_through_monotonic_ns: int | None,
    trace_finalized_monotonic_ns: int | None,
    source_sequence_at_open: int,
    source_sequence_at_close: int | None,
    dropped_event_count_at_open: int,
    dropped_event_count_at_close: int | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if observer_started_monotonic_ns > window_start_monotonic_ns:
        reasons.append("OBSERVER_STARTED_AFTER_WINDOW_OPEN")
    if filter_bound_monotonic_ns > window_start_monotonic_ns:
        reasons.append("FILTER_BOUND_AFTER_WINDOW_OPEN")
    if window_end_monotonic_ns is None:
        reasons.append("WINDOW_NOT_CLOSED")
    else:
        if observer_live_through_monotonic_ns is None or observer_live_through_monotonic_ns < window_end_monotonic_ns:
            reasons.append("OBSERVER_NOT_LIVE_THROUGH_WINDOW_END")
        if trace_finalized_monotonic_ns is None or trace_finalized_monotonic_ns < window_end_monotonic_ns:
            reasons.append("TRACE_NOT_FINALIZED_THROUGH_WINDOW_END")
    if dropped_event_count_at_open != 0 or dropped_event_count_at_close != 0:
        reasons.append("DROPPED_EVENT_COUNTER_NONZERO")
    if source_sequence_at_close is None:
        reasons.append("SOURCE_SEQUENCE_RANGE_NOT_CLOSED")
    elif source_sequence_at_close < source_sequence_at_open:
        reasons.append("SOURCE_SEQUENCE_REGRESSED")
    else:
        captured = tuple(event.source_sequence for event in _trace_events(events))
        expected = tuple(range(source_sequence_at_open + 1, source_sequence_at_close + 1))
        if captured != expected:
            reasons.append("FILTERED_TRACE_SEQUENCE_GAP")
    return tuple(sorted(set(reasons)))


@dataclass(frozen=True, slots=True, kw_only=True)
class ReentryObservationWindowReceipt:
    window_id: str
    identity: ReentryObservationIdentity
    opportunity_sha256: str
    terminal_evidence_sha256: str | None
    post_state_sha256: str | None
    observer_started_monotonic_ns: int
    filter_bound_monotonic_ns: int
    window_start_monotonic_ns: int
    window_end_monotonic_ns: int | None
    observer_live_through_monotonic_ns: int | None
    trace_finalized_monotonic_ns: int | None
    source_sequence_at_open: int
    source_sequence_at_close: int | None
    dropped_event_count_at_open: int
    dropped_event_count_at_close: int | None
    trace_sha256: str
    events: tuple[ReentryObservationEvent, ...]
    unknown_reasons: tuple[str, ...]
    status: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = REENTRY_OBSERVATION_WINDOW_SCHEMA
    evidence_scope = "CONDITION_BLIND_COMPLETE_TRACE_MECHANISM_REENTRY_OBSERVATION_CANDIDATE"
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    runtime_credit = 0
    gwt_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    physical_grid10_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_id", _text("window_id", self.window_id))
        if type(self.identity) is not ReentryObservationIdentity:
            raise ReentryObservationError("identity must be exact ReentryObservationIdentity")
        object.__setattr__(self, "opportunity_sha256", _sha256("opportunity_sha256", self.opportunity_sha256))
        if self.terminal_evidence_sha256 is not None:
            object.__setattr__(
                self,
                "terminal_evidence_sha256",
                _sha256("terminal_evidence_sha256", self.terminal_evidence_sha256),
            )
        if self.post_state_sha256 is not None:
            object.__setattr__(self, "post_state_sha256", _sha256("post_state_sha256", self.post_state_sha256))
        for name in ("observer_started_monotonic_ns", "filter_bound_monotonic_ns", "window_start_monotonic_ns"):
            _positive_int(name, getattr(self, name))
        for name in ("window_end_monotonic_ns", "observer_live_through_monotonic_ns", "trace_finalized_monotonic_ns"):
            value = getattr(self, name)
            if value is not None:
                _positive_int(name, value)
        _nonnegative_int("source_sequence_at_open", self.source_sequence_at_open)
        _nonnegative_int("dropped_event_count_at_open", self.dropped_event_count_at_open)
        if self.source_sequence_at_close is not None:
            _nonnegative_int("source_sequence_at_close", self.source_sequence_at_close)
        if self.dropped_event_count_at_close is not None:
            _nonnegative_int("dropped_event_count_at_close", self.dropped_event_count_at_close)
        object.__setattr__(self, "trace_sha256", _sha256("trace_sha256", self.trace_sha256))

        if type(self.events) is not tuple or not self.events:
            raise ReentryObservationError("events must be a non-empty tuple")
        if any(type(event) is not ReentryObservationEvent for event in self.events):
            raise ReentryObservationError("events contain unsupported values")
        if self.events[0].phase != WINDOW_OPEN:
            raise ReentryObservationError("first event must be WINDOW_OPEN")
        if self.events[0].observed_monotonic_ns != self.window_start_monotonic_ns:
            raise ReentryObservationError("window start does not bind WINDOW_OPEN event")
        times = tuple(event.observed_monotonic_ns for event in self.events)
        if any(later <= earlier for earlier, later in zip(times, times[1:])):
            raise ReentryObservationError("observation event times must be strictly increasing")
        trace_sequences = tuple(event.source_sequence for event in _trace_events(self.events))
        if any(
            later is None or earlier is None or later <= earlier
            for earlier, later in zip(trace_sequences, trace_sequences[1:])
        ):
            raise ReentryObservationError("trace source sequences must be strictly increasing")

        terminal_phases = [
            event.phase
            for event in self.events
            if event.phase in {WINDOW_TERMINAL, WINDOW_ABORT}
        ]
        if len(terminal_phases) != 1 or self.events[-1].phase != terminal_phases[0]:
            raise ReentryObservationError("window must end in exactly one terminal or abort event")

        computed_trace_sha256 = _trace_digest(
            events=self.events,
            source_sequence_at_open=self.source_sequence_at_open,
            source_sequence_at_close=self.source_sequence_at_close,
            dropped_event_count_at_open=self.dropped_event_count_at_open,
            dropped_event_count_at_close=self.dropped_event_count_at_close,
        )
        if self.trace_sha256 != computed_trace_sha256:
            raise ReentryObservationError("trace_sha256 does not bind captured trace and completeness counters")

        computed_reasons = _completeness_reasons(
            events=self.events,
            observer_started_monotonic_ns=self.observer_started_monotonic_ns,
            filter_bound_monotonic_ns=self.filter_bound_monotonic_ns,
            window_start_monotonic_ns=self.window_start_monotonic_ns,
            window_end_monotonic_ns=self.window_end_monotonic_ns,
            observer_live_through_monotonic_ns=self.observer_live_through_monotonic_ns,
            trace_finalized_monotonic_ns=self.trace_finalized_monotonic_ns,
            source_sequence_at_open=self.source_sequence_at_open,
            source_sequence_at_close=self.source_sequence_at_close,
            dropped_event_count_at_open=self.dropped_event_count_at_open,
            dropped_event_count_at_close=self.dropped_event_count_at_close,
        )
        if terminal_phases[0] == WINDOW_ABORT:
            computed_reasons = tuple(sorted(set((*computed_reasons, "WINDOW_ABORTED"))))
            if self.terminal_evidence_sha256 is not None or self.post_state_sha256 is not None:
                raise ReentryObservationError("aborted window cannot claim terminal/post-state evidence")
        else:
            if self.window_end_monotonic_ns != self.events[-1].observed_monotonic_ns:
                raise ReentryObservationError("window end does not bind terminal event")
            if self.terminal_evidence_sha256 is None or self.post_state_sha256 is None:
                computed_reasons = tuple(sorted(set((*computed_reasons, "MISSING_TERMINAL_OR_POST_STATE_EVIDENCE"))))
        if tuple(self.unknown_reasons) != computed_reasons:
            raise ReentryObservationError("unknown_reasons do not match completeness proof")

        if computed_reasons:
            expected = REENTRY_OBSERVATION_UNKNOWN
        else:
            reentry_count = sum(event.phase == TRACE_REENTRY for event in self.events)
            expected = REENTRY_OBSERVED if reentry_count else NO_REENTRY_OBSERVED
        if self.status != expected:
            raise ReentryObservationError("receipt status does not match complete observation evidence")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evidence_scope": self.evidence_scope,
            "window_id": self.window_id,
            "identity": self.identity.as_dict(),
            "opportunity_sha256": self.opportunity_sha256,
            "terminal_evidence_sha256": self.terminal_evidence_sha256,
            "post_state_sha256": self.post_state_sha256,
            "observer_started_monotonic_ns": self.observer_started_monotonic_ns,
            "filter_bound_monotonic_ns": self.filter_bound_monotonic_ns,
            "window_start_monotonic_ns": self.window_start_monotonic_ns,
            "window_end_monotonic_ns": self.window_end_monotonic_ns,
            "observer_live_through_monotonic_ns": self.observer_live_through_monotonic_ns,
            "trace_finalized_monotonic_ns": self.trace_finalized_monotonic_ns,
            "source_sequence_at_open": self.source_sequence_at_open,
            "source_sequence_at_close": self.source_sequence_at_close,
            "dropped_event_count_at_open": self.dropped_event_count_at_open,
            "dropped_event_count_at_close": self.dropped_event_count_at_close,
            "trace_sha256": self.trace_sha256,
            "events": [event.as_dict() for event in self.events],
            "unknown_reasons": list(self.unknown_reasons),
            "status": self.status,
            "provenance_refs": list(self.provenance_refs),
            "repository_ci_credit": self.repository_ci_credit,
            "target_environment_component_runtime_credit": self.target_environment_component_runtime_credit,
            "runtime_credit": self.runtime_credit,
            "gwt_runtime_credit": self.gwt_runtime_credit,
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


MonotonicNs = Callable[[], int]


class ReentryObservationWindowRecorder:
    """Condition-blind recorder for one admitted filtered trace window."""

    def __init__(
        self,
        *,
        window_id: str,
        identity: ReentryObservationIdentity,
        opportunity_ref: str,
        opportunity_sha256: str,
        observer_started_monotonic_ns: int,
        filter_bound_monotonic_ns: int,
        source_sequence_at_open: int,
        dropped_event_count_at_open: int,
        monotonic_ns: MonotonicNs,
        provenance_refs: Iterable[str],
    ) -> None:
        self._window_id = _text("window_id", window_id)
        if type(identity) is not ReentryObservationIdentity:
            raise ReentryObservationError("identity must be exact ReentryObservationIdentity")
        self._identity = identity
        self._opportunity_ref = _text("opportunity_ref", opportunity_ref)
        self._opportunity_sha256 = _sha256("opportunity_sha256", opportunity_sha256)
        self._observer_started_monotonic_ns = _positive_int(
            "observer_started_monotonic_ns", observer_started_monotonic_ns
        )
        self._filter_bound_monotonic_ns = _positive_int(
            "filter_bound_monotonic_ns", filter_bound_monotonic_ns
        )
        self._source_sequence_at_open = _nonnegative_int(
            "source_sequence_at_open", source_sequence_at_open
        )
        self._dropped_event_count_at_open = _nonnegative_int(
            "dropped_event_count_at_open", dropped_event_count_at_open
        )
        if not callable(monotonic_ns):
            raise ReentryObservationError("monotonic_ns must be callable")
        self._clock = monotonic_ns
        self._provenance_refs = _refs(provenance_refs)
        self._events: list[ReentryObservationEvent] = []
        self._sealed = False
        self._append_boundary(WINDOW_OPEN, self._opportunity_ref, self._opportunity_sha256)
        self._window_start_monotonic_ns = self._events[0].observed_monotonic_ns

    def _next_time(self) -> int:
        timestamp = _positive_int("monotonic_ns", self._clock())
        if self._events and timestamp <= self._events[-1].observed_monotonic_ns:
            raise ReentryObservationError("runtime clock did not advance monotonically")
        return timestamp

    def _append_boundary(self, phase: str, evidence_ref: str, evidence_sha256: str) -> None:
        if self._sealed:
            raise ReentryObservationError("observation window already sealed")
        self._events.append(
            ReentryObservationEvent(
                phase=phase,
                observed_monotonic_ns=self._next_time(),
                evidence_ref=evidence_ref,
                evidence_sha256=evidence_sha256,
                source_sequence=None,
            )
        )

    def observe_trace_event(
        self,
        *,
        source_sequence: int,
        event_kind: str,
        evidence_ref: str,
        evidence_sha256: str,
    ) -> None:
        if self._sealed:
            raise ReentryObservationError("observation window already sealed")
        if event_kind not in {TRACE_REENTRY, TRACE_OTHER}:
            raise ReentryObservationError("event_kind must be REENTRY or TRACE_OTHER")
        source_sequence = _nonnegative_int("source_sequence", source_sequence)
        previous = _trace_events(tuple(self._events))
        if previous and previous[-1].source_sequence is not None and source_sequence <= previous[-1].source_sequence:
            raise ReentryObservationError("trace source sequence did not advance")
        self._events.append(
            ReentryObservationEvent(
                phase=event_kind,
                observed_monotonic_ns=self._next_time(),
                evidence_ref=evidence_ref,
                evidence_sha256=evidence_sha256,
                source_sequence=source_sequence,
            )
        )

    def observe_reentry(
        self,
        *,
        source_sequence: int,
        reentry_ref: str,
        reentry_sha256: str,
    ) -> None:
        self.observe_trace_event(
            source_sequence=source_sequence,
            event_kind=TRACE_REENTRY,
            evidence_ref=reentry_ref,
            evidence_sha256=reentry_sha256,
        )

    def observe_other(
        self,
        *,
        source_sequence: int,
        evidence_ref: str,
        evidence_sha256: str,
    ) -> None:
        self.observe_trace_event(
            source_sequence=source_sequence,
            event_kind=TRACE_OTHER,
            evidence_ref=evidence_ref,
            evidence_sha256=evidence_sha256,
        )

    def close_complete(
        self,
        *,
        terminal_ref: str,
        terminal_evidence_sha256: str,
        post_state_sha256: str,
        source_sequence_at_close: int,
        dropped_event_count_at_close: int,
        observer_live_through_monotonic_ns: int,
        trace_finalized_monotonic_ns: int,
        provenance_refs: Iterable[str] = (),
    ) -> ReentryObservationWindowReceipt:
        terminal_evidence_sha256 = _sha256("terminal_evidence_sha256", terminal_evidence_sha256)
        post_state_sha256 = _sha256("post_state_sha256", post_state_sha256)
        source_sequence_at_close = _nonnegative_int("source_sequence_at_close", source_sequence_at_close)
        dropped_event_count_at_close = _nonnegative_int(
            "dropped_event_count_at_close", dropped_event_count_at_close
        )
        observer_live_through_monotonic_ns = _positive_int(
            "observer_live_through_monotonic_ns", observer_live_through_monotonic_ns
        )
        trace_finalized_monotonic_ns = _positive_int(
            "trace_finalized_monotonic_ns", trace_finalized_monotonic_ns
        )
        self._append_boundary(WINDOW_TERMINAL, terminal_ref, terminal_evidence_sha256)
        self._sealed = True
        events = tuple(self._events)
        window_end = events[-1].observed_monotonic_ns
        reasons = _completeness_reasons(
            events=events,
            observer_started_monotonic_ns=self._observer_started_monotonic_ns,
            filter_bound_monotonic_ns=self._filter_bound_monotonic_ns,
            window_start_monotonic_ns=self._window_start_monotonic_ns,
            window_end_monotonic_ns=window_end,
            observer_live_through_monotonic_ns=observer_live_through_monotonic_ns,
            trace_finalized_monotonic_ns=trace_finalized_monotonic_ns,
            source_sequence_at_open=self._source_sequence_at_open,
            source_sequence_at_close=source_sequence_at_close,
            dropped_event_count_at_open=self._dropped_event_count_at_open,
            dropped_event_count_at_close=dropped_event_count_at_close,
        )
        if reasons:
            status = REENTRY_OBSERVATION_UNKNOWN
        else:
            status = (
                REENTRY_OBSERVED
                if any(event.phase == TRACE_REENTRY for event in events)
                else NO_REENTRY_OBSERVED
            )
        refs = self._combined_refs(provenance_refs)
        trace_sha256 = _trace_digest(
            events=events,
            source_sequence_at_open=self._source_sequence_at_open,
            source_sequence_at_close=source_sequence_at_close,
            dropped_event_count_at_open=self._dropped_event_count_at_open,
            dropped_event_count_at_close=dropped_event_count_at_close,
        )
        return self._seal_receipt(
            terminal_evidence_sha256=terminal_evidence_sha256,
            post_state_sha256=post_state_sha256,
            window_end_monotonic_ns=window_end,
            observer_live_through_monotonic_ns=observer_live_through_monotonic_ns,
            trace_finalized_monotonic_ns=trace_finalized_monotonic_ns,
            source_sequence_at_close=source_sequence_at_close,
            dropped_event_count_at_close=dropped_event_count_at_close,
            trace_sha256=trace_sha256,
            unknown_reasons=reasons,
            status=status,
            provenance_refs=refs,
        )

    def abort(
        self,
        *,
        reason_ref: str,
        reason_sha256: str,
        source_sequence_at_close: int | None = None,
        dropped_event_count_at_close: int | None = None,
        provenance_refs: Iterable[str] = (),
    ) -> ReentryObservationWindowReceipt:
        if source_sequence_at_close is not None:
            source_sequence_at_close = _nonnegative_int("source_sequence_at_close", source_sequence_at_close)
        if dropped_event_count_at_close is not None:
            dropped_event_count_at_close = _nonnegative_int(
                "dropped_event_count_at_close", dropped_event_count_at_close
            )
        self._append_boundary(WINDOW_ABORT, reason_ref, reason_sha256)
        self._sealed = True
        events = tuple(self._events)
        reasons = _completeness_reasons(
            events=events,
            observer_started_monotonic_ns=self._observer_started_monotonic_ns,
            filter_bound_monotonic_ns=self._filter_bound_monotonic_ns,
            window_start_monotonic_ns=self._window_start_monotonic_ns,
            window_end_monotonic_ns=None,
            observer_live_through_monotonic_ns=None,
            trace_finalized_monotonic_ns=None,
            source_sequence_at_open=self._source_sequence_at_open,
            source_sequence_at_close=source_sequence_at_close,
            dropped_event_count_at_open=self._dropped_event_count_at_open,
            dropped_event_count_at_close=dropped_event_count_at_close,
        )
        reasons = tuple(sorted(set((*reasons, "WINDOW_ABORTED"))))
        trace_sha256 = _trace_digest(
            events=events,
            source_sequence_at_open=self._source_sequence_at_open,
            source_sequence_at_close=source_sequence_at_close,
            dropped_event_count_at_open=self._dropped_event_count_at_open,
            dropped_event_count_at_close=dropped_event_count_at_close,
        )
        return self._seal_receipt(
            terminal_evidence_sha256=None,
            post_state_sha256=None,
            window_end_monotonic_ns=None,
            observer_live_through_monotonic_ns=None,
            trace_finalized_monotonic_ns=None,
            source_sequence_at_close=source_sequence_at_close,
            dropped_event_count_at_close=dropped_event_count_at_close,
            trace_sha256=trace_sha256,
            unknown_reasons=reasons,
            status=REENTRY_OBSERVATION_UNKNOWN,
            provenance_refs=self._combined_refs(provenance_refs),
        )

    def _combined_refs(self, values: Iterable[str]) -> tuple[str, ...]:
        added = tuple(_text("provenance_ref", ref) for ref in values)
        combined = self._provenance_refs + added
        return _refs(combined)

    def _seal_receipt(
        self,
        *,
        terminal_evidence_sha256: str | None,
        post_state_sha256: str | None,
        window_end_monotonic_ns: int | None,
        observer_live_through_monotonic_ns: int | None,
        trace_finalized_monotonic_ns: int | None,
        source_sequence_at_close: int | None,
        dropped_event_count_at_close: int | None,
        trace_sha256: str,
        unknown_reasons: tuple[str, ...],
        status: str,
        provenance_refs: tuple[str, ...],
    ) -> ReentryObservationWindowReceipt:
        receipt = ReentryObservationWindowReceipt(
            window_id=self._window_id,
            identity=self._identity,
            opportunity_sha256=self._opportunity_sha256,
            terminal_evidence_sha256=terminal_evidence_sha256,
            post_state_sha256=post_state_sha256,
            observer_started_monotonic_ns=self._observer_started_monotonic_ns,
            filter_bound_monotonic_ns=self._filter_bound_monotonic_ns,
            window_start_monotonic_ns=self._window_start_monotonic_ns,
            window_end_monotonic_ns=window_end_monotonic_ns,
            observer_live_through_monotonic_ns=observer_live_through_monotonic_ns,
            trace_finalized_monotonic_ns=trace_finalized_monotonic_ns,
            source_sequence_at_open=self._source_sequence_at_open,
            source_sequence_at_close=source_sequence_at_close,
            dropped_event_count_at_open=self._dropped_event_count_at_open,
            dropped_event_count_at_close=dropped_event_count_at_close,
            trace_sha256=trace_sha256,
            events=tuple(self._events),
            unknown_reasons=unknown_reasons,
            status=status,
            provenance_refs=provenance_refs,
            _factory_seal=_RECEIPT_FACTORY,
        )
        object.__setattr__(receipt, "_factory_payload_sha256", _digest(receipt.as_dict()))
        return receipt


def validate_reentry_observation_window(value: ReentryObservationWindowReceipt) -> None:
    if type(value) is not ReentryObservationWindowReceipt or value._factory_seal is not _RECEIPT_FACTORY:
        raise ReentryObservationError("observation receipt lacks recorder origin")
    if value._factory_payload_sha256 != _digest(value.as_dict()):
        raise ReentryObservationError("observation receipt payload changed after seal")


@dataclass(frozen=True, slots=True, kw_only=True)
class MatchedReentryMechanismCandidate:
    arm_a_sha256: str
    arm_b_sha256: str
    matched_context_sha256: str
    arm_a_status: str
    arm_b_status: str
    classification: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = MATCHED_REENTRY_MECHANISM_SCHEMA
    evidence_scope = "MATCHED_CONDITION_BLIND_COMPLETE_TRACE_MECHANISM_REENTRY_COMPARISON_CANDIDATE"
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    runtime_credit = 0
    gwt_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    physical_grid10_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        for name in ("arm_a_sha256", "arm_b_sha256", "matched_context_sha256"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        allowed_status = {REENTRY_OBSERVED, NO_REENTRY_OBSERVED, REENTRY_OBSERVATION_UNKNOWN}
        if self.arm_a_status not in allowed_status or self.arm_b_status not in allowed_status:
            raise ReentryObservationError("unsupported arm status")
        allowed_classification = {
            MECHANISM_REENTRY_DIFFERENCE,
            NO_MECHANISM_REENTRY_DIFFERENCE,
            MECHANISM_COMPARISON_UNKNOWN,
        }
        if self.classification not in allowed_classification:
            raise ReentryObservationError("unsupported mechanism classification")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evidence_scope": self.evidence_scope,
            "arm_a_sha256": self.arm_a_sha256,
            "arm_b_sha256": self.arm_b_sha256,
            "matched_context_sha256": self.matched_context_sha256,
            "arm_a_status": self.arm_a_status,
            "arm_b_status": self.arm_b_status,
            "classification": self.classification,
            "provenance_refs": list(self.provenance_refs),
            "repository_ci_credit": self.repository_ci_credit,
            "target_environment_component_runtime_credit": self.target_environment_component_runtime_credit,
            "runtime_credit": self.runtime_credit,
            "gwt_runtime_credit": self.gwt_runtime_credit,
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


def bind_matched_reentry_mechanism(
    *,
    arm_a: ReentryObservationWindowReceipt,
    arm_b: ReentryObservationWindowReceipt,
    provenance_refs: Iterable[str],
) -> MatchedReentryMechanismCandidate:
    validate_reentry_observation_window(arm_a)
    validate_reentry_observation_window(arm_b)
    a_context = arm_a.identity.matched_context_dict()
    b_context = arm_b.identity.matched_context_dict()
    if a_context != b_context:
        mismatches = sorted(key for key in a_context if a_context[key] != b_context[key])
        raise ReentryObservationError("matched observation context mismatch: " + ",".join(mismatches))
    if arm_a.opportunity_sha256 != arm_b.opportunity_sha256:
        raise ReentryObservationError("observation opportunity mismatch")
    if REENTRY_OBSERVATION_UNKNOWN in {arm_a.status, arm_b.status}:
        classification = MECHANISM_COMPARISON_UNKNOWN
    elif arm_a.status == arm_b.status:
        classification = NO_MECHANISM_REENTRY_DIFFERENCE
    else:
        classification = MECHANISM_REENTRY_DIFFERENCE
    candidate = MatchedReentryMechanismCandidate(
        arm_a_sha256=arm_a.sha256(),
        arm_b_sha256=arm_b.sha256(),
        matched_context_sha256=_digest(a_context),
        arm_a_status=arm_a.status,
        arm_b_status=arm_b.status,
        classification=classification,
        provenance_refs=_refs(provenance_refs),
        _factory_seal=_PAIR_FACTORY,
    )
    object.__setattr__(candidate, "_factory_payload_sha256", _digest(candidate.as_dict()))
    return candidate


def validate_matched_reentry_mechanism(value: MatchedReentryMechanismCandidate) -> None:
    if type(value) is not MatchedReentryMechanismCandidate or value._factory_seal is not _PAIR_FACTORY:
        raise ReentryObservationError("matched mechanism candidate lacks binder origin")
    if value._factory_payload_sha256 != _digest(value.as_dict()):
        raise ReentryObservationError("matched mechanism candidate changed after bind")


__all__ = [
    "MATCHED_REENTRY_MECHANISM_SCHEMA",
    "MECHANISM_COMPARISON_UNKNOWN",
    "MECHANISM_REENTRY_DIFFERENCE",
    "NO_MECHANISM_REENTRY_DIFFERENCE",
    "NO_REENTRY_OBSERVED",
    "REENTRY_OBSERVATION_UNKNOWN",
    "REENTRY_OBSERVATION_WINDOW_SCHEMA",
    "REENTRY_OBSERVED",
    "TRACE_OTHER",
    "TRACE_REENTRY",
    "MatchedReentryMechanismCandidate",
    "ReentryObservationError",
    "ReentryObservationEvent",
    "ReentryObservationIdentity",
    "ReentryObservationWindowReceipt",
    "ReentryObservationWindowRecorder",
    "bind_matched_reentry_mechanism",
    "validate_matched_reentry_mechanism",
    "validate_reentry_observation_window",
]
