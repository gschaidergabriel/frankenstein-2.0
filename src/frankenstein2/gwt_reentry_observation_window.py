"""Condition-blind, trace-complete re-entry observation for F2-WP-900 G8.

The same observer ABI is used for every arm. It never accepts an arm label,
broadcast-present flag, expected re-entry boolean, or expected semantic result.
Negative absence is admitted only when a bounded raw event trace proves observer
liveness, no loss/overflow/gaps, fixed filter/clock identities, and finalization
past the window end. Incomplete evidence is UNKNOWN.

These objects are mechanism-evidence candidates only. They mint no runtime,
semantic GWT/J-Space, effect, training, completion, or whole-system credit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Callable, Iterable

REENTRY_OBSERVATION_WINDOW_SCHEMA = "FRANKENSTEIN2_GWT_REENTRY_OBSERVATION_WINDOW/v2"
TRACE_COMPLETENESS_SCHEMA = "FRANKENSTEIN2_GWT_TRACE_COMPLETENESS/v1"
MATCHED_REENTRY_MECHANISM_SCHEMA = "FRANKENSTEIN2_GWT_MATCHED_REENTRY_MECHANISM/v1"

REENTRY_OBSERVED = "REENTRY_OBSERVED"
NO_REENTRY_OBSERVED = "NO_REENTRY_OBSERVED_IN_COMPLETE_TRACE"
REENTRY_OBSERVATION_UNKNOWN = "REENTRY_OBSERVATION_UNKNOWN_INCOMPLETE_TRACE"

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
    trace_source_sha256: str
    filter_schema_sha256: str
    clock_domain: str
    clock_mapping_sha256: str
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
            "trace_source_sha256",
            "filter_schema_sha256",
            "clock_mapping_sha256",
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
            "trace_source_sha256": self.trace_source_sha256,
            "filter_schema_sha256": self.filter_schema_sha256,
            "clock_domain": self.clock_domain,
            "clock_mapping_sha256": self.clock_mapping_sha256,
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

    def __post_init__(self) -> None:
        if self.phase not in {"WINDOW_OPEN", "REENTRY", "WINDOW_TERMINAL", "WINDOW_ABORT"}:
            raise ReentryObservationError("unsupported observation phase")
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        object.__setattr__(self, "evidence_ref", _text("evidence_ref", self.evidence_ref))
        object.__setattr__(self, "evidence_sha256", _sha256("evidence_sha256", self.evidence_sha256))

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "evidence_ref": self.evidence_ref,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class TraceCompletenessEvidence:
    observer_started_monotonic_ns: int
    window_start_monotonic_ns: int
    window_end_monotonic_ns: int
    observer_finalized_monotonic_ns: int
    source_sequence_start: int
    source_sequence_end: int
    captured_sequence_start: int
    captured_sequence_end: int
    sequence_gap_count: int
    dropped_event_count: int
    overflow_count: int
    raw_trace_sha256: str
    filter_schema_sha256: str
    clock_domain: str
    clock_mapping_sha256: str
    finalized: bool
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = TRACE_COMPLETENESS_SCHEMA

    def __post_init__(self) -> None:
        for name in (
            "observer_started_monotonic_ns",
            "window_start_monotonic_ns",
            "window_end_monotonic_ns",
            "observer_finalized_monotonic_ns",
            "source_sequence_start",
            "source_sequence_end",
            "captured_sequence_start",
            "captured_sequence_end",
        ):
            _positive_int(name, getattr(self, name))
        for name in ("sequence_gap_count", "dropped_event_count", "overflow_count"):
            _nonnegative_int(name, getattr(self, name))
        object.__setattr__(self, "raw_trace_sha256", _sha256("raw_trace_sha256", self.raw_trace_sha256))
        object.__setattr__(self, "filter_schema_sha256", _sha256("filter_schema_sha256", self.filter_schema_sha256))
        object.__setattr__(self, "clock_domain", _text("clock_domain", self.clock_domain))
        object.__setattr__(self, "clock_mapping_sha256", _sha256("clock_mapping_sha256", self.clock_mapping_sha256))
        if type(self.finalized) is not bool:
            raise ReentryObservationError("finalized must be boolean")

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
            "observer_started_monotonic_ns": self.observer_started_monotonic_ns,
            "window_start_monotonic_ns": self.window_start_monotonic_ns,
            "window_end_monotonic_ns": self.window_end_monotonic_ns,
            "observer_finalized_monotonic_ns": self.observer_finalized_monotonic_ns,
            "source_sequence_start": self.source_sequence_start,
            "source_sequence_end": self.source_sequence_end,
            "captured_sequence_start": self.captured_sequence_start,
            "captured_sequence_end": self.captured_sequence_end,
            "sequence_gap_count": self.sequence_gap_count,
            "dropped_event_count": self.dropped_event_count,
            "overflow_count": self.overflow_count,
            "raw_trace_sha256": self.raw_trace_sha256,
            "filter_schema_sha256": self.filter_schema_sha256,
            "clock_domain": self.clock_domain,
            "clock_mapping_sha256": self.clock_mapping_sha256,
            "finalized": self.finalized,
            "complete": self.complete,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _validate_trace(value: TraceCompletenessEvidence) -> None:
    if type(value) is not TraceCompletenessEvidence or value._factory_seal is not _TRACE_FACTORY:
        raise ReentryObservationError("trace completeness evidence lacks recorder origin")
    if value._factory_payload_sha256 != _digest(value.as_dict()):
        raise ReentryObservationError("trace completeness evidence changed after seal")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReentryObservationWindowReceipt:
    window_id: str
    identity: ReentryObservationIdentity
    opportunity_sha256: str
    terminal_evidence_sha256: str | None
    post_state_sha256: str | None
    trace_completeness: TraceCompletenessEvidence | None
    events: tuple[ReentryObservationEvent, ...]
    status: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = REENTRY_OBSERVATION_WINDOW_SCHEMA
    evidence_scope = "CONDITION_BLIND_TRACE_COMPLETE_MECHANISM_REENTRY_OBSERVATION_CANDIDATE"
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
        reentry_count = sum(event.phase == "REENTRY" for event in self.events)
        if terminal_phases[0] == "WINDOW_ABORT":
            if self.trace_completeness is not None:
                raise ReentryObservationError("aborted window cannot claim trace completeness")
            if self.terminal_evidence_sha256 is not None or self.post_state_sha256 is not None:
                raise ReentryObservationError("aborted window cannot claim terminal/post-state evidence")
            expected = REENTRY_OBSERVATION_UNKNOWN
        else:
            if self.terminal_evidence_sha256 is None or self.post_state_sha256 is None:
                raise ReentryObservationError("terminal window requires terminal and post-state evidence")
            if type(self.trace_completeness) is not TraceCompletenessEvidence:
                raise ReentryObservationError("terminal window requires trace completeness evidence")
            _validate_trace(self.trace_completeness)
            if self.trace_completeness.window_start_monotonic_ns != self.events[0].observed_monotonic_ns:
                raise ReentryObservationError("trace/window start mismatch")
            if self.trace_completeness.window_end_monotonic_ns != self.events[-1].observed_monotonic_ns:
                raise ReentryObservationError("trace/window end mismatch")
            if self.trace_completeness.filter_schema_sha256 != self.identity.filter_schema_sha256:
                raise ReentryObservationError("trace filter identity mismatch")
            if self.trace_completeness.clock_domain != self.identity.clock_domain:
                raise ReentryObservationError("trace clock domain mismatch")
            if self.trace_completeness.clock_mapping_sha256 != self.identity.clock_mapping_sha256:
                raise ReentryObservationError("trace clock mapping mismatch")
            if reentry_count:
                expected = REENTRY_OBSERVED
            elif self.trace_completeness.complete:
                expected = NO_REENTRY_OBSERVED
            else:
                expected = REENTRY_OBSERVATION_UNKNOWN
        if self.status != expected:
            raise ReentryObservationError("receipt status does not match observed trace")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @property
    def trace_complete(self) -> bool:
        return self.trace_completeness is not None and self.trace_completeness.complete

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evidence_scope": self.evidence_scope,
            "window_id": self.window_id,
            "identity": self.identity.as_dict(),
            "opportunity_sha256": self.opportunity_sha256,
            "terminal_evidence_sha256": self.terminal_evidence_sha256,
            "post_state_sha256": self.post_state_sha256,
            "trace_completeness": None if self.trace_completeness is None else self.trace_completeness.as_dict(),
            "trace_complete": self.trace_complete,
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
    """One condition-blind observation window with explicit trace finalization."""

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

    def _append(self, phase: str, evidence_ref: str, evidence_sha256: str) -> None:
        if self._sealed:
            raise ReentryObservationError("observation window already sealed")
        event = ReentryObservationEvent(
            phase=phase,
            observed_monotonic_ns=_positive_int("monotonic_ns", self._clock()),
            evidence_ref=evidence_ref,
            evidence_sha256=evidence_sha256,
        )
        if self._events and event.observed_monotonic_ns <= self._events[-1].observed_monotonic_ns:
            raise ReentryObservationError("runtime clock did not advance monotonically")
        self._events.append(event)

    def observe_reentry(self, *, reentry_ref: str, reentry_sha256: str) -> None:
        self._append("REENTRY", reentry_ref, reentry_sha256)

    def close_with_trace(
        self,
        *,
        terminal_ref: str,
        terminal_evidence_sha256: str,
        post_state_sha256: str,
        observer_started_monotonic_ns: int,
        observer_finalized_monotonic_ns: int,
        source_sequence_start: int,
        source_sequence_end: int,
        captured_sequence_start: int,
        captured_sequence_end: int,
        sequence_gap_count: int,
        dropped_event_count: int,
        overflow_count: int,
        raw_trace_sha256: str,
        filter_schema_sha256: str,
        clock_domain: str,
        clock_mapping_sha256: str,
        finalized: bool,
        provenance_refs: Iterable[str] = (),
    ) -> ReentryObservationWindowReceipt:
        terminal_evidence_sha256 = _sha256("terminal_evidence_sha256", terminal_evidence_sha256)
        post_state_sha256 = _sha256("post_state_sha256", post_state_sha256)
        filter_schema_sha256 = _sha256("filter_schema_sha256", filter_schema_sha256)
        clock_domain = _text("clock_domain", clock_domain)
        clock_mapping_sha256 = _sha256("clock_mapping_sha256", clock_mapping_sha256)
        if filter_schema_sha256 != self._identity.filter_schema_sha256:
            raise ReentryObservationError("filter schema does not match observer identity")
        if clock_domain != self._identity.clock_domain:
            raise ReentryObservationError("clock domain does not match observer identity")
        if clock_mapping_sha256 != self._identity.clock_mapping_sha256:
            raise ReentryObservationError("clock mapping does not match observer identity")

        window_start = self._events[0].observed_monotonic_ns
        self._append("WINDOW_TERMINAL", terminal_ref, terminal_evidence_sha256)
        window_end = self._events[-1].observed_monotonic_ns
        self._sealed = True

        trace = TraceCompletenessEvidence(
            observer_started_monotonic_ns=observer_started_monotonic_ns,
            window_start_monotonic_ns=window_start,
            window_end_monotonic_ns=window_end,
            observer_finalized_monotonic_ns=observer_finalized_monotonic_ns,
            source_sequence_start=source_sequence_start,
            source_sequence_end=source_sequence_end,
            captured_sequence_start=captured_sequence_start,
            captured_sequence_end=captured_sequence_end,
            sequence_gap_count=sequence_gap_count,
            dropped_event_count=dropped_event_count,
            overflow_count=overflow_count,
            raw_trace_sha256=raw_trace_sha256,
            filter_schema_sha256=filter_schema_sha256,
            clock_domain=clock_domain,
            clock_mapping_sha256=clock_mapping_sha256,
            finalized=finalized,
            _factory_seal=_TRACE_FACTORY,
        )
        object.__setattr__(trace, "_factory_payload_sha256", _digest(trace.as_dict()))

        reentry_seen = any(event.phase == "REENTRY" for event in self._events)
        status = REENTRY_OBSERVED if reentry_seen else NO_REENTRY_OBSERVED if trace.complete else REENTRY_OBSERVATION_UNKNOWN
        refs = self._provenance_refs + tuple(_text("provenance_ref", ref) for ref in provenance_refs)
        receipt = ReentryObservationWindowReceipt(
            window_id=self._window_id,
            identity=self._identity,
            opportunity_sha256=self._opportunity_sha256,
            terminal_evidence_sha256=terminal_evidence_sha256,
            post_state_sha256=post_state_sha256,
            trace_completeness=trace,
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
    evidence_scope = "MATCHED_CONDITION_BLIND_TRACE_COMPLETE_MECHANISM_REENTRY_COMPARISON_CANDIDATE"
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
        if self.classification not in {
            MECHANISM_REENTRY_DIFFERENCE,
            NO_MECHANISM_REENTRY_DIFFERENCE,
            MECHANISM_COMPARISON_UNKNOWN,
        }:
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
    if not arm_a.trace_complete or not arm_b.trace_complete:
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
]
