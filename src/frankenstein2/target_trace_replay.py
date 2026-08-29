"""Privacy-bounded target trace normalization and deterministic T3 replay.

F2-WP-1205 generation 1.

This module accepts only a small, typed allow-list of technical topology/lifecycle
facts. It intentionally has no arbitrary payload/content field. Physical-only and
explicitly unknown events are preserved as fidelity gaps and are never converted into
replay steps or T4 physical-host credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

TARGET_TRACE_SCHEMA = "FRANKENSTEIN2_SANITIZED_TARGET_TRACE/v1"
REPLAY_PLAN_SCHEMA = "FRANKENSTEIN2_TARGET_TRACE_REPLAY_PLAN/v1"
IMPLEMENTATION_VERSION = "F2-WP-1205-G1"
T3_FIDELITY = "T3_TARGET_TRACE_REPLAY"
T4_FIDELITY = "T4_PHYSICAL"
UNKNOWN_FIDELITY = "UNKNOWN"

EVENT_KINDS = frozenset(
    {
        "DEVICE_GENERATION",
        "DEVICE_ROUTE",
        "SERVICE_STATE",
        "DBUS_OWNER",
        "MULTIMEDIA_TOPOLOGY",
        "SESSION_EPOCH",
        "PERMISSION_STATE",
        "UNKNOWN",
    }
)

PHYSICAL_GAP_REASONS = frozenset(
    {
        "HARDWARE_TIMING",
        "FIRMWARE_ONLY",
        "PHYSICAL_DEVICE_BEHAVIOR",
        "KERNEL_DRIVER_BEHAVIOR",
        "OTHER_PHYSICAL_ONLY_UNKNOWN",
    }
)

_ALLOWED_RAW_KEYS = frozenset(
    {
        "event_id",
        "sequence",
        "generation",
        "kind",
        "subject_id",
        "observed_state",
        "source",
        "offset_ns",
        "physical_only",
        "physical_gap_reason",
    }
)
_FORBIDDEN_KEY_TOKENS = (
    "credential",
    "secret",
    "password",
    "token",
    "cookie",
    "clipboard",
    "document",
    "message",
    "body",
    "content",
    "payload",
    "camera_frame",
    "microphone_audio",
    "raw_audio",
    "raw_video",
)
_TECHNICAL_ATOM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+,-]{0,255}$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


class TargetTraceReplayError(ValueError):
    """Fail-closed target trace contract error."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_int(name: str, value: Any, *, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise TargetTraceReplayError(f"{name} must be an integer >= {minimum}")
    return value


def _require_atom(name: str, value: Any) -> str:
    if not isinstance(value, str) or _TECHNICAL_ATOM.fullmatch(value) is None:
        raise TargetTraceReplayError(
            f"{name} must be a bounded technical atom without free-form content"
        )
    return value


def _validate_raw_keys(record: Mapping[str, Any]) -> None:
    keys = set(record)
    unexpected = keys - _ALLOWED_RAW_KEYS
    if unexpected:
        raise TargetTraceReplayError(
            f"raw trace record contains non-allowlisted fields: {sorted(unexpected)!r}"
        )
    lowered = tuple(key.lower() for key in keys)
    for key in lowered:
        if any(token in key for token in _FORBIDDEN_KEY_TOKENS):
            raise TargetTraceReplayError(f"privacy-forbidden trace field: {key}")


@dataclass(frozen=True, slots=True)
class SanitizedTraceEvent:
    event_id: str
    sequence: int
    generation: int
    kind: str
    subject_id: str
    observed_state: str
    source: str
    offset_ns: int = 0
    physical_only: bool = False
    physical_gap_reason: str | None = None

    def __post_init__(self) -> None:
        _require_atom("event_id", self.event_id)
        _require_int("sequence", self.sequence, minimum=0)
        _require_int("generation", self.generation, minimum=1)
        _require_int("offset_ns", self.offset_ns, minimum=0)
        if self.kind not in EVENT_KINDS:
            raise TargetTraceReplayError(f"unsupported event kind: {self.kind}")
        _require_atom("subject_id", self.subject_id)
        _require_atom("observed_state", self.observed_state)
        _require_atom("source", self.source)
        if type(self.physical_only) is not bool:
            raise TargetTraceReplayError("physical_only must be a bool")
        if self.physical_only:
            if self.physical_gap_reason not in PHYSICAL_GAP_REASONS:
                raise TargetTraceReplayError(
                    "physical-only events require an allowlisted physical_gap_reason"
                )
        elif self.physical_gap_reason is not None:
            raise TargetTraceReplayError(
                "non-physical events cannot carry physical_gap_reason"
            )

    @property
    def replayable(self) -> bool:
        return not self.physical_only and self.kind != "UNKNOWN"

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "generation": self.generation,
            "kind": self.kind,
            "subject_id": self.subject_id,
            "observed_state": self.observed_state,
            "source": self.source,
            "offset_ns": self.offset_ns,
            "physical_only": self.physical_only,
            "physical_gap_reason": self.physical_gap_reason,
        }


@dataclass(frozen=True, slots=True)
class FidelityGap:
    event_id: str
    sequence: int
    kind: str
    reason: str
    required_fidelity: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "kind": self.kind,
            "reason": self.reason,
            "required_fidelity": self.required_fidelity,
        }


@dataclass(frozen=True, slots=True)
class ReplayStep:
    event_id: str
    sequence: int
    generation: int
    kind: str
    subject_id: str
    observed_state: str
    source: str
    offset_ns: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "generation": self.generation,
            "kind": self.kind,
            "subject_id": self.subject_id,
            "observed_state": self.observed_state,
            "source": self.source,
            "offset_ns": self.offset_ns,
        }


@dataclass(frozen=True, slots=True)
class SanitizedTargetTrace:
    schema: str
    implementation_version: str
    trace_generation: int
    target_profile_digest_sha256: str
    events: tuple[SanitizedTraceEvent, ...]
    trace_digest_sha256: str

    def __post_init__(self) -> None:
        if self.schema != TARGET_TRACE_SCHEMA:
            raise TargetTraceReplayError("target trace schema mismatch")
        if self.implementation_version != IMPLEMENTATION_VERSION:
            raise TargetTraceReplayError("target trace implementation version mismatch")
        _require_int("trace_generation", self.trace_generation, minimum=1)
        if _SHA256_HEX.fullmatch(self.target_profile_digest_sha256) is None:
            raise TargetTraceReplayError("target profile digest must be lowercase SHA-256 hex")
        _validate_event_chain(self.events)
        if self.trace_digest_sha256 != self._calculate_digest():
            raise TargetTraceReplayError("target trace digest mismatch")

    def _payload_without_digest(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "implementation_version": self.implementation_version,
            "trace_generation": self.trace_generation,
            "target_profile_digest_sha256": self.target_profile_digest_sha256,
            "events": [event.as_dict() for event in self.events],
        }

    def _calculate_digest(self) -> str:
        return _sha256(self._payload_without_digest())

    def as_dict(self) -> dict[str, Any]:
        value = self._payload_without_digest()
        value["trace_digest_sha256"] = self.trace_digest_sha256
        value["epistemic_scope"] = "SANITIZED_T3_TRACE_NOT_PHYSICAL_COMPLETION_EVIDENCE"
        return value

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class TargetTraceReplayPlan:
    schema: str
    implementation_version: str
    trace_digest_sha256: str
    replay_steps: tuple[ReplayStep, ...]
    fidelity_gaps: tuple[FidelityGap, ...]
    plan_digest_sha256: str

    def __post_init__(self) -> None:
        if self.schema != REPLAY_PLAN_SCHEMA:
            raise TargetTraceReplayError("replay plan schema mismatch")
        if self.implementation_version != IMPLEMENTATION_VERSION:
            raise TargetTraceReplayError("replay plan implementation version mismatch")
        if _SHA256_HEX.fullmatch(self.trace_digest_sha256) is None:
            raise TargetTraceReplayError("trace digest must be lowercase SHA-256 hex")
        sequences = [step.sequence for step in self.replay_steps]
        if sequences != sorted(sequences):
            raise TargetTraceReplayError("replay steps must be sequence ordered")
        if self.plan_digest_sha256 != self._calculate_digest():
            raise TargetTraceReplayError("replay plan digest mismatch")

    @property
    def physical_host_credit(self) -> bool:
        return False

    @property
    def max_fidelity(self) -> str:
        return T3_FIDELITY

    def _payload_without_digest(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "implementation_version": self.implementation_version,
            "trace_digest_sha256": self.trace_digest_sha256,
            "replay_steps": [step.as_dict() for step in self.replay_steps],
            "fidelity_gaps": [gap.as_dict() for gap in self.fidelity_gaps],
            "max_fidelity": self.max_fidelity,
            "physical_host_credit": self.physical_host_credit,
        }

    def _calculate_digest(self) -> str:
        return _sha256(self._payload_without_digest())

    def as_dict(self) -> dict[str, Any]:
        value = self._payload_without_digest()
        value["plan_digest_sha256"] = self.plan_digest_sha256
        return value

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())


def _validate_event_chain(events: Sequence[SanitizedTraceEvent]) -> None:
    seen_ids: set[str] = set()
    seen_sequences: set[int] = set()
    last_generation: dict[tuple[str, str], int] = {}
    prior_sequence = -1
    for event in events:
        if event.event_id in seen_ids:
            raise TargetTraceReplayError(f"duplicate event_id: {event.event_id}")
        if event.sequence in seen_sequences:
            raise TargetTraceReplayError(f"duplicate sequence: {event.sequence}")
        if event.sequence <= prior_sequence:
            raise TargetTraceReplayError("events must be strictly sequence ordered")
        key = (event.kind, event.subject_id)
        previous = last_generation.get(key)
        if previous is not None and event.generation < previous:
            raise TargetTraceReplayError(
                f"generation regression for {event.kind}:{event.subject_id}"
            )
        seen_ids.add(event.event_id)
        seen_sequences.add(event.sequence)
        last_generation[key] = event.generation
        prior_sequence = event.sequence


def _event_from_mapping(record: Mapping[str, Any]) -> SanitizedTraceEvent:
    _validate_raw_keys(record)
    required = {
        "event_id",
        "sequence",
        "generation",
        "kind",
        "subject_id",
        "observed_state",
        "source",
    }
    missing = required - set(record)
    if missing:
        raise TargetTraceReplayError(f"raw trace record missing fields: {sorted(missing)!r}")
    return SanitizedTraceEvent(
        event_id=record["event_id"],
        sequence=record["sequence"],
        generation=record["generation"],
        kind=record["kind"],
        subject_id=record["subject_id"],
        observed_state=record["observed_state"],
        source=record["source"],
        offset_ns=record.get("offset_ns", 0),
        physical_only=record.get("physical_only", False),
        physical_gap_reason=record.get("physical_gap_reason"),
    )


def normalize_target_trace(
    raw_events: Iterable[Mapping[str, Any]],
    *,
    target_profile_digest_sha256: str,
    trace_generation: int,
) -> SanitizedTargetTrace:
    """Normalize explicit technical event records into one deterministic trace."""
    _require_int("trace_generation", trace_generation, minimum=1)
    if _SHA256_HEX.fullmatch(target_profile_digest_sha256) is None:
        raise TargetTraceReplayError("target profile digest must be lowercase SHA-256 hex")
    events = tuple(sorted((_event_from_mapping(item) for item in raw_events), key=lambda e: e.sequence))
    _validate_event_chain(events)
    payload = {
        "schema": TARGET_TRACE_SCHEMA,
        "implementation_version": IMPLEMENTATION_VERSION,
        "trace_generation": trace_generation,
        "target_profile_digest_sha256": target_profile_digest_sha256,
        "events": [event.as_dict() for event in events],
    }
    return SanitizedTargetTrace(
        schema=TARGET_TRACE_SCHEMA,
        implementation_version=IMPLEMENTATION_VERSION,
        trace_generation=trace_generation,
        target_profile_digest_sha256=target_profile_digest_sha256,
        events=events,
        trace_digest_sha256=_sha256(payload),
    )


def compile_replay_plan(trace: SanitizedTargetTrace) -> TargetTraceReplayPlan:
    """Compile a deterministic T3 replay plan without minting physical-host credit."""
    steps: list[ReplayStep] = []
    gaps: list[FidelityGap] = []
    for event in trace.events:
        if event.physical_only:
            gaps.append(
                FidelityGap(
                    event_id=event.event_id,
                    sequence=event.sequence,
                    kind=event.kind,
                    reason=event.physical_gap_reason or "OTHER_PHYSICAL_ONLY_UNKNOWN",
                    required_fidelity=T4_FIDELITY,
                )
            )
            continue
        if event.kind == "UNKNOWN":
            gaps.append(
                FidelityGap(
                    event_id=event.event_id,
                    sequence=event.sequence,
                    kind=event.kind,
                    reason="UNKNOWN_EVENT_SEMANTICS",
                    required_fidelity=UNKNOWN_FIDELITY,
                )
            )
            continue
        steps.append(
            ReplayStep(
                event_id=event.event_id,
                sequence=event.sequence,
                generation=event.generation,
                kind=event.kind,
                subject_id=event.subject_id,
                observed_state=event.observed_state,
                source=event.source,
                offset_ns=event.offset_ns,
            )
        )
    payload = {
        "schema": REPLAY_PLAN_SCHEMA,
        "implementation_version": IMPLEMENTATION_VERSION,
        "trace_digest_sha256": trace.trace_digest_sha256,
        "replay_steps": [step.as_dict() for step in steps],
        "fidelity_gaps": [gap.as_dict() for gap in gaps],
        "max_fidelity": T3_FIDELITY,
        "physical_host_credit": False,
    }
    return TargetTraceReplayPlan(
        schema=REPLAY_PLAN_SCHEMA,
        implementation_version=IMPLEMENTATION_VERSION,
        trace_digest_sha256=trace.trace_digest_sha256,
        replay_steps=tuple(steps),
        fidelity_gaps=tuple(gaps),
        plan_digest_sha256=_sha256(payload),
    )
