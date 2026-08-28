"""Deterministic read-only cognitive envelope evaluation for Frankenstein 2.0.

This component is intentionally persistence-agnostic and authority-free.  It turns
explicit caller-supplied signal readouts plus an explicit policy into an immutable
ControlSnapshot and a *candidate* regulation recommendation.  It never performs a
write, invokes a provider/tool, authorizes an effect, or claims completion.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Iterable


class EnvelopeState(str, Enum):
    IN_ENVELOPE = "IN_ENVELOPE"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"
    HARD_LIMIT = "HARD_LIMIT"


class RegulationCandidate(str, Enum):
    MAINTAIN_CURRENT_LIMITS = "MAINTAIN_CURRENT_LIMITS"
    REQUEST_DEGRADED_MODE = "REQUEST_DEGRADED_MODE"
    FAIL_CLOSED_HOLD = "FAIL_CLOSED_HOLD"
    REQUEST_CONTAINMENT = "REQUEST_CONTAINMENT"


@dataclass(frozen=True, slots=True)
class SignalBand:
    signal_id: str
    hard_min: float
    soft_min: float
    soft_max: float
    hard_max: float
    required: bool = True

    def __post_init__(self) -> None:
        _require_identifier("signal_id", self.signal_id)
        limits = (self.hard_min, self.soft_min, self.soft_max, self.hard_max)
        if not all(_finite_number(value) for value in limits):
            raise ValueError("signal band limits must be finite numbers")
        if not (self.hard_min <= self.soft_min <= self.soft_max <= self.hard_max):
            raise ValueError("signal band must satisfy hard_min <= soft_min <= soft_max <= hard_max")


@dataclass(frozen=True, slots=True)
class EnvelopePolicy:
    policy_id: str
    generation: int
    bands: tuple[SignalBand, ...]
    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_identifier("policy_id", self.policy_id)
        _require_generation(self.generation)
        _require_unique_nonempty_refs("policy evidence_refs", self.evidence_refs)
        _require_unique_nonempty_refs("policy provenance_refs", self.provenance_refs)
        if not self.bands:
            raise ValueError("policy must contain at least one signal band")
        signal_ids = [band.signal_id for band in self.bands]
        if len(set(signal_ids)) != len(signal_ids):
            raise ValueError("policy contains duplicate signal_id bands")


@dataclass(frozen=True, slots=True)
class SignalReadout:
    signal_id: str
    generation: int
    value: float | None
    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_identifier("signal_id", self.signal_id)
        _require_generation(self.generation)


@dataclass(frozen=True, slots=True)
class SignalAssessment:
    signal_id: str
    generation: int | None
    state: EnvelopeState
    value: float | None
    reason: str
    readout_digest: str | None
    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ControlSnapshot:
    policy_id: str
    policy_generation: int
    policy_digest: str
    state: EnvelopeState
    regulation_candidate: RegulationCandidate
    assessments: tuple[SignalAssessment, ...]
    snapshot_digest: str
    fail_closed: bool
    effect_authority: bool = False
    completion_authority: bool = False
    state_mutation_authority: bool = False


def evaluate_cognitive_envelope(
    policy: EnvelopePolicy,
    readouts: Iterable[SignalReadout],
) -> ControlSnapshot:
    """Evaluate explicit readouts against explicit policy, without side effects.

    Readout order is deliberately ignored: the canonical snapshot is sorted by
    ``signal_id`` and digests therefore bind semantic identity rather than caller order.
    Malformed/ambiguous duplicate readouts are rejected. Missing required signals,
    absent evidence/provenance, and non-finite values become UNKNOWN and fail closed.
    """
    readout_by_id: dict[str, SignalReadout] = {}
    for readout in readouts:
        if readout.signal_id in readout_by_id:
            raise ValueError(f"duplicate readout for signal_id {readout.signal_id!r}")
        readout_by_id[readout.signal_id] = readout

    policy_ids = {band.signal_id for band in policy.bands}
    unexpected = sorted(set(readout_by_id) - policy_ids)
    if unexpected:
        raise ValueError(f"readouts contain signals absent from policy: {unexpected}")

    assessments: list[SignalAssessment] = []
    for band in sorted(policy.bands, key=lambda item: item.signal_id):
        readout = readout_by_id.get(band.signal_id)
        assessments.append(_assess_signal(band, readout))

    aggregate_state = _aggregate_state(tuple(assessments))
    candidate = _candidate_for(aggregate_state)
    policy_digest = _digest(_policy_payload(policy))

    pre_digest = {
        "schema": "FRANKENSTEIN2_CONTROL_SNAPSHOT/v1",
        "policy_id": policy.policy_id,
        "policy_generation": policy.generation,
        "policy_digest": policy_digest,
        "state": aggregate_state.value,
        "regulation_candidate": candidate.value,
        "fail_closed": aggregate_state in {EnvelopeState.UNKNOWN, EnvelopeState.HARD_LIMIT},
        "effect_authority": False,
        "completion_authority": False,
        "state_mutation_authority": False,
        "assessments": [_assessment_payload(item) for item in assessments],
    }
    snapshot_digest = _digest(pre_digest)
    return ControlSnapshot(
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_digest=policy_digest,
        state=aggregate_state,
        regulation_candidate=candidate,
        assessments=tuple(assessments),
        snapshot_digest=snapshot_digest,
        fail_closed=pre_digest["fail_closed"],
    )


def _assess_signal(band: SignalBand, readout: SignalReadout | None) -> SignalAssessment:
    if readout is None:
        if band.required:
            return SignalAssessment(
                signal_id=band.signal_id,
                generation=None,
                state=EnvelopeState.UNKNOWN,
                value=None,
                reason="REQUIRED_READOUT_MISSING",
                readout_digest=None,
                evidence_refs=(),
                provenance_refs=(),
            )
        return SignalAssessment(
            signal_id=band.signal_id,
            generation=None,
            state=EnvelopeState.IN_ENVELOPE,
            value=None,
            reason="OPTIONAL_READOUT_ABSENT",
            readout_digest=None,
            evidence_refs=(),
            provenance_refs=(),
        )

    digest = _digest(_readout_payload(readout))
    if not readout.evidence_refs:
        return _unknown(readout, digest, "EVIDENCE_MISSING")
    if not readout.provenance_refs:
        return _unknown(readout, digest, "PROVENANCE_MISSING")
    if len(set(readout.evidence_refs)) != len(readout.evidence_refs):
        return _unknown(readout, digest, "EVIDENCE_AMBIGUOUS_DUPLICATE_REF")
    if len(set(readout.provenance_refs)) != len(readout.provenance_refs):
        return _unknown(readout, digest, "PROVENANCE_AMBIGUOUS_DUPLICATE_REF")
    if any(not isinstance(ref, str) or not ref.strip() for ref in readout.evidence_refs):
        return _unknown(readout, digest, "EVIDENCE_INVALID_REF")
    if any(not isinstance(ref, str) or not ref.strip() for ref in readout.provenance_refs):
        return _unknown(readout, digest, "PROVENANCE_INVALID_REF")
    if readout.value is None or not _finite_number(readout.value):
        return _unknown(readout, digest, "VALUE_UNKNOWN_OR_NONFINITE")

    value = float(readout.value)
    if value < band.hard_min or value > band.hard_max:
        state = EnvelopeState.HARD_LIMIT
        reason = "HARD_LIMIT_EXCEEDED"
    elif value < band.soft_min or value > band.soft_max:
        state = EnvelopeState.DEGRADED
        reason = "SOFT_BAND_EXCEEDED"
    else:
        state = EnvelopeState.IN_ENVELOPE
        reason = "WITHIN_SOFT_BAND"

    return SignalAssessment(
        signal_id=readout.signal_id,
        generation=readout.generation,
        state=state,
        value=value,
        reason=reason,
        readout_digest=digest,
        evidence_refs=tuple(sorted(readout.evidence_refs)),
        provenance_refs=tuple(sorted(readout.provenance_refs)),
    )


def _unknown(readout: SignalReadout, digest: str, reason: str) -> SignalAssessment:
    return SignalAssessment(
        signal_id=readout.signal_id,
        generation=readout.generation,
        state=EnvelopeState.UNKNOWN,
        value=readout.value if _finite_number(readout.value) else None,
        reason=reason,
        readout_digest=digest,
        evidence_refs=tuple(sorted(ref for ref in readout.evidence_refs if isinstance(ref, str))),
        provenance_refs=tuple(sorted(ref for ref in readout.provenance_refs if isinstance(ref, str))),
    )


def _aggregate_state(assessments: tuple[SignalAssessment, ...]) -> EnvelopeState:
    states = {item.state for item in assessments}
    if EnvelopeState.HARD_LIMIT in states:
        return EnvelopeState.HARD_LIMIT
    if EnvelopeState.UNKNOWN in states:
        return EnvelopeState.UNKNOWN
    if EnvelopeState.DEGRADED in states:
        return EnvelopeState.DEGRADED
    return EnvelopeState.IN_ENVELOPE


def _candidate_for(state: EnvelopeState) -> RegulationCandidate:
    return {
        EnvelopeState.IN_ENVELOPE: RegulationCandidate.MAINTAIN_CURRENT_LIMITS,
        EnvelopeState.DEGRADED: RegulationCandidate.REQUEST_DEGRADED_MODE,
        EnvelopeState.UNKNOWN: RegulationCandidate.FAIL_CLOSED_HOLD,
        EnvelopeState.HARD_LIMIT: RegulationCandidate.REQUEST_CONTAINMENT,
    }[state]


def _policy_payload(policy: EnvelopePolicy) -> dict[str, object]:
    return {
        "schema": "FRANKENSTEIN2_COGNITIVE_ENVELOPE_POLICY/v1",
        "policy_id": policy.policy_id,
        "generation": policy.generation,
        "evidence_refs": sorted(policy.evidence_refs),
        "provenance_refs": sorted(policy.provenance_refs),
        "bands": [
            {
                "signal_id": band.signal_id,
                "hard_min": band.hard_min,
                "soft_min": band.soft_min,
                "soft_max": band.soft_max,
                "hard_max": band.hard_max,
                "required": band.required,
            }
            for band in sorted(policy.bands, key=lambda item: item.signal_id)
        ],
    }


def _readout_payload(readout: SignalReadout) -> dict[str, object]:
    value: float | None
    if readout.value is None or not _finite_number(readout.value):
        value = None
    else:
        value = float(readout.value)
    return {
        "schema": "FRANKENSTEIN2_COGNITIVE_SIGNAL_READOUT/v1",
        "signal_id": readout.signal_id,
        "generation": readout.generation,
        "value": value,
        "evidence_refs": sorted(ref for ref in readout.evidence_refs if isinstance(ref, str)),
        "provenance_refs": sorted(ref for ref in readout.provenance_refs if isinstance(ref, str)),
    }


def _assessment_payload(item: SignalAssessment) -> dict[str, object]:
    return {
        "signal_id": item.signal_id,
        "generation": item.generation,
        "state": item.state.value,
        "value": item.value,
        "reason": item.reason,
        "readout_digest": item.readout_digest,
        "evidence_refs": list(item.evidence_refs),
        "provenance_refs": list(item.provenance_refs),
    }


def _digest(payload: dict[str, object]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _require_identifier(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_generation(value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("generation must be a non-negative integer")


def _require_unique_nonempty_refs(field_name: str, refs: tuple[str, ...]) -> None:
    if not refs:
        raise ValueError(f"{field_name} must not be empty")
    if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
        raise ValueError(f"{field_name} contains an invalid reference")
    if len(set(refs)) != len(refs):
        raise ValueError(f"{field_name} contains duplicate references")
