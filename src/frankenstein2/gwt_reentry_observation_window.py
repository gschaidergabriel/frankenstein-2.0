"""Condition-blind bounded re-entry observation for F2-WP-900 generation 8.

This module closes one mechanism-evidence defect only: both experimental arms use the
same observer ABI, and the observer never receives an arm label, expected boolean,
broadcast-present flag, or expected result. A completed observation opportunity with
no matching re-entry is distinguishable from an aborted/incomplete window.

Objects produced here are evidence candidates. They mint no runtime, semantic GWT,
J-Space, effect, training, completion, or whole-system credit by construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Callable, Iterable

REENTRY_OBSERVATION_WINDOW_SCHEMA = "FRANKENSTEIN2_GWT_REENTRY_OBSERVATION_WINDOW/v1"
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
class ReentryObservationWindowReceipt:
    window_id: str
    identity: ReentryObservationIdentity
    opportunity_sha256: str
    terminal_evidence_sha256: str | None
    post_state_sha256: str | None
    events: tuple[ReentryObservationEvent, ...]
    status: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = REENTRY_OBSERVATION_WINDOW_SCHEMA
    evidence_scope = "CONDITION_BLIND_BOUNDED_MECHANISM_REENTRY_OBSERVATION_CANDIDATE"
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
            expected = REENTRY_OBSERVATION_UNKNOWN
            if self.terminal_evidence_sha256 is not None or self.post_state_sha256 is not None:
                raise ReentryObservationError("aborted window cannot claim terminal/post-state evidence")
        else:
            if self.terminal_evidence_sha256 is None or self.post_state_sha256 is None:
                raise ReentryObservationError("complete window requires terminal and post-state evidence")
            expected = REENTRY_OBSERVED if reentry_count else NO_REENTRY_OBSERVED
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

    The API intentionally has no condition/arm/expected-result argument.
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

    def close_complete(
        self,
        *,
        terminal_ref: str,
        terminal_evidence_sha256: str,
        post_state_sha256: str,
        provenance_refs: Iterable[str] = (),
    ) -> ReentryObservationWindowReceipt:
        terminal_evidence_sha256 = _sha256("terminal_evidence_sha256", terminal_evidence_sha256)
        post_state_sha256 = _sha256("post_state_sha256", post_state_sha256)
        self._append("WINDOW_TERMINAL", terminal_ref, terminal_evidence_sha256)
        self._sealed = True
        refs = self._provenance_refs + tuple(_text("provenance_ref", ref) for ref in provenance_refs)
        receipt = ReentryObservationWindowReceipt(
            window_id=self._window_id,
            identity=self._identity,
            opportunity_sha256=self._opportunity_sha256,
            terminal_evidence_sha256=terminal_evidence_sha256,
            post_state_sha256=post_state_sha256,
            events=tuple(self._events),
            status=REENTRY_OBSERVED if any(event.phase == "REENTRY" for event in self._events) else NO_REENTRY_OBSERVED,
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
    evidence_scope = "MATCHED_CONDITION_BLIND_MECHANISM_REENTRY_COMPARISON_CANDIDATE"
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
