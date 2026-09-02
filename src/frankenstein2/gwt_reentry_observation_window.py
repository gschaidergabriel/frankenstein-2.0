"""Condition-blind, completeness-bound re-entry observation for F2-WP-900 G8.

This module closes one mechanism-evidence defect only: both experimental arms use the
same observer ABI, and the observer never receives an arm label, expected boolean,
broadcast-present flag, or expected result. A completed observation opportunity with
no matching re-entry is admissible as negative evidence only when a factory-sealed
trace-completeness witness proves that the observer covered the whole admitted window
without drops, overflow, sequence gaps, filter drift, clock drift, late start, early
stop, or premature finalization.

Objects produced here are evidence candidates. They mint no runtime, semantic GWT,
J-Space, effect, training, completion, or whole-system credit by construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Callable, Iterable

REENTRY_OBSERVATION_WINDOW_SCHEMA = "FRANKENSTEIN2_GWT_REENTRY_OBSERVATION_WINDOW/v2"
TRACE_COMPLETENESS_SCHEMA = "FRANKENSTEIN2_GWT_REENTRY_TRACE_COMPLETENESS/v1"
MATCHED_REENTRY_MECHANISM_SCHEMA = "FRANKENSTEIN2_GWT_MATCHED_REENTRY_MECHANISM/v1"

REENTRY_OBSERVED = "REENTRY_OBSERVED"
NO_REENTRY_OBSERVED = "NO_REENTRY_OBSERVED_IN_COMPLETE_WINDOW"
REENTRY_OBSERVATION_UNKNOWN = "REENTRY_OBSERVATION_UNKNOWN_INCOMPLETE_WINDOW"

MECHANISM_REENTRY_DIFFERENCE = "MECHANISM_REENTRY_DIFFERENCE_CANDIDATE"
NO_MECHANISM_REENTRY_DIFFERENCE = "NO_MECHANISM_REENTRY_DIFFERENCE_OBSERVED"
MECHANISM_COMPARISON_UNKNOWN = "MECHANISM_REENTRY_COMPARISON_UNKNOWN"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_RECEIPT_FACTORY = object()
_TRACE_FACTORY = object()
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
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
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
    trace_filter_sha256: str
    clock_domain_sha256: str
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
            "trace_filter_sha256",
            "clock_domain_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        for name in ("task_id", "observer_identity", "runtime_instance_id", "process_identity"):
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
            "trace_filter_sha256": self.trace_filter_sha256,
            "clock_domain_sha256": self.clock_domain_sha256,
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
    task_id: str | None = None
    task_input_sha256: str | None = None
    pre_state_sha256: str | None = None
    task_executor_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.phase not in {"WINDOW_OPEN", "REENTRY", "WINDOW_TERMINAL", "WINDOW_ABORT"}:
            raise ReentryObservationError("unsupported observation phase")
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        object.__setattr__(self, "evidence_ref", _text("evidence_ref", self.evidence_ref))
        object.__setattr__(self, "evidence_sha256", _sha256("evidence_sha256", self.evidence_sha256))
        if self.phase == "REENTRY":
            if self.source_sequence is None:
                raise ReentryObservationError("reentry event requires source_sequence")
            _positive_int("source_sequence", self.source_sequence)
            if self.task_id is None:
                raise ReentryObservationError("reentry event requires task_id")
            object.__setattr__(self, "task_id", _text("task_id", self.task_id))
            for name in ("task_input_sha256", "pre_state_sha256", "task_executor_sha256"):
                value = getattr(self, name)
                if value is None:
                    raise ReentryObservationError(f"reentry event requires {name}")
                object.__setattr__(self, name, _sha256(name, value))
        else:
            if any(
                value is not None
                for value in (
                    self.source_sequence,
                    self.task_id,
                    self.task_input_sha256,
                    self.pre_state_sha256,
                    self.task_executor_sha256,
                )
            ):
                raise ReentryObservationError("only REENTRY events may carry source/task binding")

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "evidence_ref": self.evidence_ref,
            "evidence_sha256": self.evidence_sha256,
            "source_sequence": self.source_sequence,
            "task_id": self.task_id,
            "task_input_sha256": self.task_input_sha256,
            "pre_state_sha256": self.pre_state_sha256,
            "task_executor_sha256": self.task_executor_sha256,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class TraceCompletenessEvidence:
    observer_started_monotonic_ns: int
    observer_live_through_monotonic_ns: int
    trace_finalized_monotonic_ns: int
    source_first_sequence: int
    source_last_sequence: int
    source_event_count: int
    captured_first_sequence: int
    captured_last_sequence: int
    captured_event_count: int
    dropped_event_count: int
    overflow_event_count: int
    raw_trace_sha256: str
    filter_sha256: str
    clock_domain_sha256: str
    finalization_ref: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = TRACE_COMPLETENESS_SCHEMA

    def __post_init__(self) -> None:
        for name in (
            "observer_started_monotonic_ns",
            "observer_live_through_monotonic_ns",
            "trace_finalized_monotonic_ns",
            "source_first_sequence",
            "source_last_sequence",
            "source_event_count",
            "captured_first_sequence",
            "captured_last_sequence",
            "captured_event_count",
        ):
            _positive_int(name, getattr(self, name))
        for name in ("dropped_event_count", "overflow_event_count"):
            _nonnegative_int(name, getattr(self, name))
        for name in ("raw_trace_sha256", "filter_sha256", "clock_domain_sha256"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        object.__setattr__(self, "finalization_ref", _text("finalization_ref", self.finalization_ref))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def record(
        cls,
        *,
        observer_started_monotonic_ns: int,
        observer_live_through_monotonic_ns: int,
        trace_finalized_monotonic_ns: int,
        source_first_sequence: int,
        source_last_sequence: int,
        source_event_count: int,
        captured_first_sequence: int,
        captured_last_sequence: int,
        captured_event_count: int,
        dropped_event_count: int,
        overflow_event_count: int,
        raw_trace_sha256: str,
        filter_sha256: str,
        clock_domain_sha256: str,
        finalization_ref: str,
        provenance_refs: Iterable[str],
    ) -> "TraceCompletenessEvidence":
        value = cls(
            observer_started_monotonic_ns=observer_started_monotonic_ns,
            observer_live_through_monotonic_ns=observer_live_through_monotonic_ns,
            trace_finalized_monotonic_ns=trace_finalized_monotonic_ns,
            source_first_sequence=source_first_sequence,
            source_last_sequence=source_last_sequence,
            source_event_count=source_event_count,
            captured_first_sequence=captured_first_sequence,
            captured_last_sequence=captured_last_sequence,
            captured_event_count=captured_event_count,
            dropped_event_count=dropped_event_count,
            overflow_event_count=overflow_event_count,
            raw_trace_sha256=raw_trace_sha256,
            filter_sha256=filter_sha256,
            clock_domain_sha256=clock_domain_sha256,
            finalization_ref=finalization_ref,
            provenance_refs=tuple(provenance_refs),
        )
        object.__setattr__(value, "_factory_seal", _TRACE_FACTORY)
        object.__setattr__(value, "_factory_payload_sha256", _digest(value.as_dict()))
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "observer_started_monotonic_ns": self.observer_started_monotonic_ns,
            "observer_live_through_monotonic_ns": self.observer_live_through_monotonic_ns,
            "trace_finalized_monotonic_ns": self.trace_finalized_monotonic_ns,
            "source_first_sequence": self.source_first_sequence,
            "source_last_sequence": self.source_last_sequence,
            "source_event_count": self.source_event_count,
            "captured_first_sequence": self.captured_first_sequence,
            "captured_last_sequence": self.captured_last_sequence,
            "captured_event_count": self.captured_event_count,
            "dropped_event_count": self.dropped_event_count,
            "overflow_event_count": self.overflow_event_count,
            "raw_trace_sha256": self.raw_trace_sha256,
            "filter_sha256": self.filter_sha256,
            "clock_domain_sha256": self.clock_domain_sha256,
            "finalization_ref": self.finalization_ref,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_trace_completeness(value: TraceCompletenessEvidence) -> None:
    if type(value) is not TraceCompletenessEvidence or value._factory_seal is not _TRACE_FACTORY:
        raise ReentryObservationError("trace completeness lacks recorder origin")
    if value._factory_payload_sha256 != _digest(value.as_dict()):
        raise ReentryObservationError("trace completeness changed after record")


def _trace_incompleteness_reasons(
    *,
    trace: TraceCompletenessEvidence,
    identity: ReentryObservationIdentity,
    window_open_ns: int,
    window_terminal_ns: int,
) -> tuple[str, ...]:
    validate_trace_completeness(trace)
    reasons: list[str] = []
    if trace.observer_started_monotonic_ns > window_open_ns:
        reasons.append("OBSERVER_STARTED_AFTER_WINDOW_OPEN")
    if trace.observer_live_through_monotonic_ns < window_terminal_ns:
        reasons.append("OBSERVER_NOT_LIVE_THROUGH_WINDOW_TERMINAL")
    if trace.trace_finalized_monotonic_ns < window_terminal_ns:
        reasons.append("TRACE_FINALIZED_BEFORE_WINDOW_TERMINAL")
    if trace.filter_sha256 != identity.trace_filter_sha256:
        reasons.append("TRACE_FILTER_IDENTITY_MISMATCH")
    if trace.clock_domain_sha256 != identity.clock_domain_sha256:
        reasons.append("TRACE_CLOCK_DOMAIN_MISMATCH")
    if trace.dropped_event_count != 0:
        reasons.append("DROPPED_EVENTS_NONZERO")
    if trace.overflow_event_count != 0:
        reasons.append("OVERFLOW_EVENTS_NONZERO")
    source_expected_count = trace.source_last_sequence - trace.source_first_sequence + 1
    if source_expected_count != trace.source_event_count:
        reasons.append("SOURCE_SEQUENCE_RANGE_NOT_CONTIGUOUS")
    if (
        trace.captured_first_sequence != trace.source_first_sequence
        or trace.captured_last_sequence != trace.source_last_sequence
    ):
        reasons.append("CAPTURED_SEQUENCE_RANGE_MISMATCH")
    if trace.captured_event_count != trace.source_event_count:
        reasons.append("CAPTURED_EVENT_COUNT_MISMATCH")
    return tuple(reasons)


@dataclass(frozen=True, slots=True, kw_only=True)
class ReentryObservationWindowReceipt:
    window_id: str
    identity: ReentryObservationIdentity
    opportunity_sha256: str
    terminal_evidence_sha256: str | None
    post_state_sha256: str | None
    trace_completeness: TraceCompletenessEvidence | None
    trace_complete: bool
    trace_incompleteness_reasons: tuple[str, ...]
    events: tuple[ReentryObservationEvent, ...]
    status: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = REENTRY_OBSERVATION_WINDOW_SCHEMA
    evidence_scope = "CONDITION_BLIND_COMPLETENESS_BOUND_MECHANISM_REENTRY_OBSERVATION_CANDIDATE"
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
                self, "terminal_evidence_sha256", _sha256("terminal_evidence_sha256", self.terminal_evidence_sha256)
            )
        if self.post_state_sha256 is not None:
            object.__setattr__(self, "post_state_sha256", _sha256("post_state_sha256", self.post_state_sha256))
        if type(self.events) is not tuple or not self.events:
            raise ReentryObservationError("events must be a non-empty tuple")
        if any(type(event) is not ReentryObservationEvent for event in self.events):
            raise ReentryObservationError("events contain unsupported values")
        if self.events[0].phase != "WINDOW_OPEN":
            raise ReentryObservationError("first event must be WINDOW_OPEN")
        times = tuple(event.observed_monotonic_ns for event in self.events)
        if any(later <= earlier for earlier, later in zip(times, times[1:])):
            raise ReentryObservationError("observation event times must be strictly increasing")
        terminal_phases = [event.phase for event in self.events if event.phase in {"WINDOW_TERMINAL", "WINDOW_ABORT"}]
        if len(terminal_phases) != 1 or self.events[-1].phase != terminal_phases[0]:
            raise ReentryObservationError("window must end in exactly one terminal or abort event")
        if type(self.trace_complete) is not bool:
            raise ReentryObservationError("trace_complete must be boolean")
        if type(self.trace_incompleteness_reasons) is not tuple or any(
            type(reason) is not str or not reason for reason in self.trace_incompleteness_reasons
        ):
            raise ReentryObservationError("trace_incompleteness_reasons must be a tuple of strings")
        reentry_events = tuple(event for event in self.events if event.phase == "REENTRY")
        if terminal_phases[0] == "WINDOW_ABORT":
            if self.trace_completeness is not None:
                raise ReentryObservationError("aborted window cannot claim trace completeness")
            if self.trace_complete:
                raise ReentryObservationError("aborted window cannot claim complete trace")
            if self.trace_incompleteness_reasons != ("WINDOW_ABORTED",):
                raise ReentryObservationError("aborted window must record WINDOW_ABORTED")
            expected = REENTRY_OBSERVATION_UNKNOWN
            if self.terminal_evidence_sha256 is not None or self.post_state_sha256 is not None:
                raise ReentryObservationError("aborted window cannot claim terminal/post-state evidence")
        else:
            if self.terminal_evidence_sha256 is None or self.post_state_sha256 is None:
                raise ReentryObservationError("terminal window requires terminal and post-state evidence")
            if type(self.trace_completeness) is not TraceCompletenessEvidence:
                raise ReentryObservationError("terminal window requires trace completeness evidence")
            reasons = _trace_incompleteness_reasons(
                trace=self.trace_completeness,
                identity=self.identity,
                window_open_ns=self.events[0].observed_monotonic_ns,
                window_terminal_ns=self.events[-1].observed_monotonic_ns,
            )
            if self.trace_complete != (not reasons):
                raise ReentryObservationError("trace_complete does not match completeness evidence")
            if self.trace_incompleteness_reasons != reasons:
                raise ReentryObservationError("trace incompleteness reasons do not match evidence")
            for event in reentry_events:
                if not (
                    self.trace_completeness.captured_first_sequence
                    <= event.source_sequence
                    <= self.trace_completeness.captured_last_sequence
                ):
                    raise ReentryObservationError("reentry source sequence lies outside captured trace range")
            if reentry_events:
                expected = REENTRY_OBSERVED
            elif reasons:
                expected = REENTRY_OBSERVATION_UNKNOWN
            else:
                expected = NO_REENTRY_OBSERVED
        if self.status != expected:
            raise ReentryObservationError("receipt status does not match observed event window")
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
            "trace_completeness": self.trace_completeness.as_dict() if self.trace_completeness is not None else None,
            "trace_complete": self.trace_complete,
            "trace_incompleteness_reasons": list(self.trace_incompleteness_reasons),
            "events": [event.as_dict() for event in self.events],
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
    """One condition-blind observation window.

    The API intentionally has no condition/arm/expected-result argument. Re-entry
    observations must carry task and pre-state bindings so a caller cannot inject a
    foreign event into an otherwise matched window.
    """

    def __init__(
        self,
        *,
        window_id: str,
        identity: ReentryObservationIdentity,
        opportunity_ref: str,
        opportunity_sha256: str,
        monotonic_ns: MonotonicNs,
        provenance_refs: Iterable[str],
    ) -> None:
        self._window_id = _text("window_id", window_id)
        if type(identity) is not ReentryObservationIdentity:
            raise ReentryObservationError("identity must be exact ReentryObservationIdentity")
        self._identity = identity
        self._opportunity_ref = _text("opportunity_ref", opportunity_ref)
        self._opportunity_sha256 = _sha256("opportunity_sha256", opportunity_sha256)
        if not callable(monotonic_ns):
            raise ReentryObservationError("monotonic_ns must be callable")
        self._clock = monotonic_ns
        self._provenance_refs = _refs(provenance_refs)
        self._events: list[ReentryObservationEvent] = []
        self._sealed = False
        self._append("WINDOW_OPEN", self._opportunity_ref, self._opportunity_sha256)

    def _append(
        self,
        phase: str,
        evidence_ref: str,
        evidence_sha256: str,
        *,
        source_sequence: int | None = None,
        task_id: str | None = None,
        task_input_sha256: str | None = None,
        pre_state_sha256: str | None = None,
        task_executor_sha256: str | None = None,
    ) -> None:
        if self._sealed:
            raise ReentryObservationError("observation window already sealed")
        event = ReentryObservationEvent(
            phase=phase,
            observed_monotonic_ns=_positive_int("monotonic_ns", self._clock()),
            evidence_ref=evidence_ref,
            evidence_sha256=evidence_sha256,
            source_sequence=source_sequence,
            task_id=task_id,
            task_input_sha256=task_input_sha256,
            pre_state_sha256=pre_state_sha256,
            task_executor_sha256=task_executor_sha256,
        )
        if self._events and event.observed_monotonic_ns <= self._events[-1].observed_monotonic_ns:
            raise ReentryObservationError("runtime clock did not advance monotonically")
        self._events.append(event)

    def observe_reentry(
        self,
        *,
        reentry_ref: str,
        reentry_sha256: str,
        source_sequence: int,
        task_id: str,
        task_input_sha256: str,
        pre_state_sha256: str,
        task_executor_sha256: str,
    ) -> None:
        task_id = _text("task_id", task_id)
        task_input_sha256 = _sha256("task_input_sha256", task_input_sha256)
        pre_state_sha256 = _sha256("pre_state_sha256", pre_state_sha256)
        task_executor_sha256 = _sha256("task_executor_sha256", task_executor_sha256)
        if task_id != self._identity.task_id:
            raise ReentryObservationError("reentry task_id mismatch")
        if task_input_sha256 != self._identity.task_input_sha256:
            raise ReentryObservationError("reentry task_input_sha256 mismatch")
        if pre_state_sha256 != self._identity.pre_state_sha256:
            raise ReentryObservationError("reentry pre_state_sha256 mismatch")
        if task_executor_sha256 != self._identity.task_executor_sha256:
            raise ReentryObservationError("reentry task_executor_sha256 mismatch")
        self._append(
            "REENTRY",
            reentry_ref,
            reentry_sha256,
            source_sequence=source_sequence,
            task_id=task_id,
            task_input_sha256=task_input_sha256,
            pre_state_sha256=pre_state_sha256,
            task_executor_sha256=task_executor_sha256,
        )

    def close_complete(
        self,
        *,
        terminal_ref: str,
        terminal_evidence_sha256: str,
        post_state_sha256: str,
        trace_completeness: TraceCompletenessEvidence,
        provenance_refs: Iterable[str] = (),
    ) -> ReentryObservationWindowReceipt:
        terminal_evidence_sha256 = _sha256("terminal_evidence_sha256", terminal_evidence_sha256)
        post_state_sha256 = _sha256("post_state_sha256", post_state_sha256)
        validate_trace_completeness(trace_completeness)
        self._append("WINDOW_TERMINAL", terminal_ref, terminal_evidence_sha256)
        self._sealed = True
        refs = self._provenance_refs + tuple(_text("provenance_ref", ref) for ref in provenance_refs)
        reasons = _trace_incompleteness_reasons(
            trace=trace_completeness,
            identity=self._identity,
            window_open_ns=self._events[0].observed_monotonic_ns,
            window_terminal_ns=self._events[-1].observed_monotonic_ns,
        )
        has_reentry = any(event.phase == "REENTRY" for event in self._events)
        status = (
            REENTRY_OBSERVED
            if has_reentry
            else REENTRY_OBSERVATION_UNKNOWN
            if reasons
            else NO_REENTRY_OBSERVED
        )
        receipt = ReentryObservationWindowReceipt(
            window_id=self._window_id,
            identity=self._identity,
            opportunity_sha256=self._opportunity_sha256,
            terminal_evidence_sha256=terminal_evidence_sha256,
            post_state_sha256=post_state_sha256,
            trace_completeness=trace_completeness,
            trace_complete=not reasons,
            trace_incompleteness_reasons=reasons,
            events=tuple(self._events),
            status=status,
            provenance_refs=refs,
            _factory_seal=_RECEIPT_FACTORY,
        )
        object.__setattr__(receipt, "_factory_payload_sha256", _digest(receipt.as_dict()))
        return receipt

    def abort(
        self,
        *,
        reason_ref: str,
        reason_sha256: str,
        provenance_refs: Iterable[str] = (),
    ) -> ReentryObservationWindowReceipt:
        self._append("WINDOW_ABORT", reason_ref, reason_sha256)
        self._sealed = True
        refs = self._provenance_refs + tuple(_text("provenance_ref", ref) for ref in provenance_refs)
        receipt = ReentryObservationWindowReceipt(
            window_id=self._window_id,
            identity=self._identity,
            opportunity_sha256=self._opportunity_sha256,
            terminal_evidence_sha256=None,
            post_state_sha256=None,
            trace_completeness=None,
            trace_complete=False,
            trace_incompleteness_reasons=("WINDOW_ABORTED",),
            events=tuple(self._events),
            status=REENTRY_OBSERVATION_UNKNOWN,
            provenance_refs=refs,
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
    evidence_scope = "MATCHED_CONDITION_BLIND_COMPLETENESS_BOUND_MECHANISM_REENTRY_COMPARISON_CANDIDATE"
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
    "TRACE_COMPLETENESS_SCHEMA",
    "MatchedReentryMechanismCandidate",
    "ReentryObservationError",
    "ReentryObservationEvent",
    "ReentryObservationIdentity",
    "ReentryObservationWindowReceipt",
    "ReentryObservationWindowRecorder",
    "TraceCompletenessEvidence",
    "bind_matched_reentry_mechanism",
    "validate_matched_reentry_mechanism",
    "validate_reentry_observation_window",
    "validate_trace_completeness",
]
