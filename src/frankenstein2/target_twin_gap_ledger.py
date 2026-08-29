"""Deterministic target-twin / physical-gap correlation primitives.

F2-WP-1209 generation 1.

This module never collects or manufactures physical-host evidence. A caller may supply
references to independently observed evidence; this module only correlates those references
with predictions recorded earlier in a deterministic sequence. Outputs are repository-level,
noncanonical evidence objects and cannot mint T4, runtime, effect, completion,
GRID/GWT/J-Space, training, or whole-system credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

TWIN_PREDICTION_SCHEMA = "FRANKENSTEIN2_TWIN_PREDICTION/v1"
PHYSICAL_OBSERVATION_SCHEMA = "FRANKENSTEIN2_PHYSICAL_OBSERVATION_REF/v1"
TWIN_GAP_ENTRY_SCHEMA = "FRANKENSTEIN2_TWIN_GAP_ENTRY/v1"
TWIN_GAP_LEDGER_SCHEMA = "FRANKENSTEIN2_TWIN_GAP_LEDGER/v1"
EVIDENCE_SCOPE = "REPOSITORY_CORRELATION_ONLY_NO_T4_OR_RUNTIME_CREDIT"

FAILURE = "FAILURE"
SUCCESS = "SUCCESS"
PHYSICAL_ONLY_GAP = "PHYSICAL_ONLY_GAP"
UNKNOWN = "UNKNOWN"
MATCH = "MATCH"
SURPRISE = "SURPRISE"
PHYSICAL_ONLY = "PHYSICAL_ONLY"
OPEN_REPLAY_OBLIGATION = "OPEN_REPLAY_OBLIGATION"
EXPLICIT_NON_EMULATABLE_GAP = "EXPLICIT_NON_EMULATABLE_GAP"
NO_REPLAY_OBLIGATION = "NO_REPLAY_OBLIGATION"
EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"

_PREDICTED_OUTCOMES = frozenset({FAILURE, SUCCESS, PHYSICAL_ONLY_GAP})
_OBSERVED_OUTCOMES = frozenset({FAILURE, SUCCESS, PHYSICAL_ONLY, UNKNOWN})
_CLASSIFICATIONS = frozenset({MATCH, SURPRISE, PHYSICAL_ONLY, UNKNOWN})
_REPLAY_STATES = frozenset(
    {OPEN_REPLAY_OBLIGATION, EXPLICIT_NON_EMULATABLE_GAP, NO_REPLAY_OBLIGATION, EVIDENCE_REQUIRED}
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_SEQUENCE = 2**63 - 1
_MAX_ENTRIES = 100_000


class TargetTwinGapLedgerError(ValueError):
    """Fail-closed validation error for WP1209 correlation data."""


def _exact_string(name: str, value: Any) -> str:
    if type(value) is not str:
        raise TargetTwinGapLedgerError(f"{name} must be an exact concrete string")
    if not value or value != value.strip():
        raise TargetTwinGapLedgerError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_TEXT:
        raise TargetTwinGapLedgerError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TargetTwinGapLedgerError(f"{name} contains control characters")
    return value


def _literal(name: str, value: Any, expected: str) -> str:
    if type(value) is not str or value != expected:
        raise TargetTwinGapLedgerError(f"{name} mismatch")
    return value


def _enum(name: str, value: Any, allowed: frozenset[str]) -> str:
    value = _exact_string(name, value)
    if value not in allowed:
        raise TargetTwinGapLedgerError(f"unsupported {name}: {value}")
    return value


def _exact_int(name: str, value: Any, *, minimum: int = 0, maximum: int = _MAX_SEQUENCE) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise TargetTwinGapLedgerError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _sha256_or_unknown(name: str, value: Any) -> str:
    if type(value) is not str:
        raise TargetTwinGapLedgerError(f"{name} must be an exact concrete string")
    if value == UNKNOWN:
        return value
    if _SHA256_RE.fullmatch(value) is None:
        raise TargetTwinGapLedgerError(f"{name} must be UNKNOWN or lowercase 64-hex SHA-256 text")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _sha256_or_unknown(name, value)
    if value == UNKNOWN:
        raise TargetTwinGapLedgerError(f"{name} cannot be UNKNOWN")
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TargetTwinGapLedgerError("value is not canonical JSON-safe data") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _prediction_payload(
    *, release_digest: str, scenario_digest: str, event_key: str, predicted_outcome: str,
    fidelity: str, sequence: int,
) -> dict[str, Any]:
    return {
        "release_digest": release_digest,
        "scenario_digest": scenario_digest,
        "event_key": event_key,
        "predicted_outcome": predicted_outcome,
        "fidelity": fidelity,
        "sequence": sequence,
    }


@dataclass(frozen=True, slots=True)
class TwinPrediction:
    """Prediction created before a future physical observation."""

    schema: str
    prediction_id: str
    release_digest: str
    scenario_digest: str
    event_key: str
    predicted_outcome: str
    fidelity: str
    sequence: int

    def __post_init__(self) -> None:
        _literal("prediction schema", self.schema, TWIN_PREDICTION_SCHEMA)
        _exact_string("prediction_id", self.prediction_id)
        _sha256("release_digest", self.release_digest)
        _sha256("scenario_digest", self.scenario_digest)
        _exact_string("event_key", self.event_key)
        _enum("predicted_outcome", self.predicted_outcome, _PREDICTED_OUTCOMES)
        if self.fidelity not in {"T0", "T1", "T2", "T3"}:
            raise TargetTwinGapLedgerError("prediction fidelity must be T0, T1, T2, or T3")
        _exact_int("prediction sequence", self.sequence)
        expected = "twin-prediction:" + _digest(_prediction_payload(
            release_digest=self.release_digest,
            scenario_digest=self.scenario_digest,
            event_key=self.event_key,
            predicted_outcome=self.predicted_outcome,
            fidelity=self.fidelity,
            sequence=self.sequence,
        ))
        if self.prediction_id != expected:
            raise TargetTwinGapLedgerError("prediction_id does not bind exact prediction content")

    @classmethod
    def create(cls, *, release_digest: str, scenario_digest: str, event_key: str,
               predicted_outcome: str, fidelity: str, sequence: int) -> "TwinPrediction":
        payload = _prediction_payload(
            release_digest=release_digest, scenario_digest=scenario_digest, event_key=event_key,
            predicted_outcome=predicted_outcome, fidelity=fidelity, sequence=sequence,
        )
        return cls(schema=TWIN_PREDICTION_SCHEMA,
                   prediction_id="twin-prediction:" + _digest(payload), **payload)

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "prediction_id": self.prediction_id, **_prediction_payload(
            release_digest=self.release_digest, scenario_digest=self.scenario_digest,
            event_key=self.event_key, predicted_outcome=self.predicted_outcome,
            fidelity=self.fidelity, sequence=self.sequence,
        )}


def _observation_payload(*, release_digest: str, target_profile_digest: str, event_key: str,
                         observed_outcome: str, evidence_digest: str, sequence: int) -> dict[str, Any]:
    return {
        "release_digest": release_digest,
        "target_profile_digest": target_profile_digest,
        "event_key": event_key,
        "observed_outcome": observed_outcome,
        "evidence_digest": evidence_digest,
        "sequence": sequence,
    }


@dataclass(frozen=True, slots=True)
class PhysicalObservationRef:
    """Reference to caller-supplied physical evidence; this module does not collect it."""

    schema: str
    observation_id: str
    release_digest: str
    target_profile_digest: str
    event_key: str
    observed_outcome: str
    evidence_digest: str
    sequence: int

    def __post_init__(self) -> None:
        _literal("observation schema", self.schema, PHYSICAL_OBSERVATION_SCHEMA)
        _exact_string("observation_id", self.observation_id)
        _sha256("release_digest", self.release_digest)
        _sha256("target_profile_digest", self.target_profile_digest)
        _exact_string("event_key", self.event_key)
        _enum("observed_outcome", self.observed_outcome, _OBSERVED_OUTCOMES)
        _sha256_or_unknown("evidence_digest", self.evidence_digest)
        _exact_int("observation sequence", self.sequence)
        if self.observed_outcome == UNKNOWN and self.evidence_digest != UNKNOWN:
            raise TargetTwinGapLedgerError("UNKNOWN observation must not carry synthetic evidence")
        if self.observed_outcome != UNKNOWN and self.evidence_digest == UNKNOWN:
            raise TargetTwinGapLedgerError("concrete physical observation requires evidence_digest")
        expected = "physical-observation:" + _digest(_observation_payload(
            release_digest=self.release_digest,
            target_profile_digest=self.target_profile_digest,
            event_key=self.event_key,
            observed_outcome=self.observed_outcome,
            evidence_digest=self.evidence_digest,
            sequence=self.sequence,
        ))
        if self.observation_id != expected:
            raise TargetTwinGapLedgerError("observation_id does not bind exact observation content")

    @classmethod
    def create(cls, *, release_digest: str, target_profile_digest: str, event_key: str,
               observed_outcome: str, evidence_digest: str, sequence: int) -> "PhysicalObservationRef":
        payload = _observation_payload(
            release_digest=release_digest, target_profile_digest=target_profile_digest,
            event_key=event_key, observed_outcome=observed_outcome,
            evidence_digest=evidence_digest, sequence=sequence,
        )
        return cls(schema=PHYSICAL_OBSERVATION_SCHEMA,
                   observation_id="physical-observation:" + _digest(payload), **payload)

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "observation_id": self.observation_id, **_observation_payload(
            release_digest=self.release_digest, target_profile_digest=self.target_profile_digest,
            event_key=self.event_key, observed_outcome=self.observed_outcome,
            evidence_digest=self.evidence_digest, sequence=self.sequence,
        )}


@dataclass(frozen=True, slots=True)
class TwinGapEntry:
    schema: str
    entry_id: str
    prediction_id: str
    observation_id: str
    event_key: str
    classification: str
    replay_state: str
    prior_prediction_eligible: bool
    evidence_scope: str

    def __post_init__(self) -> None:
        _literal("entry schema", self.schema, TWIN_GAP_ENTRY_SCHEMA)
        _exact_string("entry_id", self.entry_id)
        if self.prediction_id != UNKNOWN:
            _exact_string("prediction_id", self.prediction_id)
        _exact_string("observation_id", self.observation_id)
        _exact_string("event_key", self.event_key)
        _enum("classification", self.classification, _CLASSIFICATIONS)
        _enum("replay_state", self.replay_state, _REPLAY_STATES)
        if type(self.prior_prediction_eligible) is not bool:
            raise TargetTwinGapLedgerError("prior_prediction_eligible must be bool")
        _literal("evidence_scope", self.evidence_scope, EVIDENCE_SCOPE)
        identity = {
            "prediction_id": self.prediction_id,
            "observation_id": self.observation_id,
            "event_key": self.event_key,
            "classification": self.classification,
            "replay_state": self.replay_state,
            "prior_prediction_eligible": self.prior_prediction_eligible,
        }
        if self.entry_id != "twin-gap-entry:" + _digest(identity):
            raise TargetTwinGapLedgerError("entry_id does not bind exact correlation content")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema, "entry_id": self.entry_id, "prediction_id": self.prediction_id,
            "observation_id": self.observation_id, "event_key": self.event_key,
            "classification": self.classification, "replay_state": self.replay_state,
            "prior_prediction_eligible": self.prior_prediction_eligible,
            "evidence_scope": self.evidence_scope,
        }


def correlate(prediction: TwinPrediction | None, observation: PhysicalObservationRef) -> TwinGapEntry:
    """Correlate one observation without permitting post-hoc prediction credit."""
    if not isinstance(observation, PhysicalObservationRef):
        raise TargetTwinGapLedgerError("observation must be PhysicalObservationRef")
    if prediction is not None:
        if not isinstance(prediction, TwinPrediction):
            raise TargetTwinGapLedgerError("prediction must be TwinPrediction or None")
        if prediction.release_digest != observation.release_digest:
            raise TargetTwinGapLedgerError("prediction and observation release_digest mismatch")
        if prediction.event_key != observation.event_key:
            raise TargetTwinGapLedgerError("prediction and observation event_key mismatch")

    prior_eligible = prediction is not None and prediction.sequence < observation.sequence
    if observation.observed_outcome == UNKNOWN:
        classification, replay_state = UNKNOWN, EVIDENCE_REQUIRED
    elif prediction is None or not prior_eligible:
        classification, replay_state = SURPRISE, OPEN_REPLAY_OBLIGATION
    elif prediction.predicted_outcome == PHYSICAL_ONLY_GAP:
        classification, replay_state = PHYSICAL_ONLY, EXPLICIT_NON_EMULATABLE_GAP
    elif prediction.predicted_outcome == observation.observed_outcome:
        classification, replay_state = MATCH, NO_REPLAY_OBLIGATION
    else:
        classification, replay_state = SURPRISE, OPEN_REPLAY_OBLIGATION

    prediction_id = prediction.prediction_id if prediction else UNKNOWN
    identity = {
        "prediction_id": prediction_id,
        "observation_id": observation.observation_id,
        "event_key": observation.event_key,
        "classification": classification,
        "replay_state": replay_state,
        "prior_prediction_eligible": prior_eligible,
    }
    return TwinGapEntry(
        schema=TWIN_GAP_ENTRY_SCHEMA,
        entry_id="twin-gap-entry:" + _digest(identity),
        prediction_id=prediction_id,
        observation_id=observation.observation_id,
        event_key=observation.event_key,
        classification=classification,
        replay_state=replay_state,
        prior_prediction_eligible=prior_eligible,
        evidence_scope=EVIDENCE_SCOPE,
    )


@dataclass(frozen=True, slots=True)
class TwinGapLedger:
    schema: str
    ledger_id: str
    release_digest: str
    target_profile_digest: str
    entries: tuple[TwinGapEntry, ...]
    match_count: int
    surprise_count: int
    physical_only_count: int
    unknown_count: int
    open_replay_obligation_count: int
    evidence_scope: str
    runtime_credit: int
    physical_host_credit: int
    completion_credit: int
    whole_system_acceptance: bool

    def __post_init__(self) -> None:
        _literal("ledger schema", self.schema, TWIN_GAP_LEDGER_SCHEMA)
        _sha256("release_digest", self.release_digest)
        _sha256("target_profile_digest", self.target_profile_digest)
        if type(self.entries) is not tuple or len(self.entries) > _MAX_ENTRIES:
            raise TargetTwinGapLedgerError("entries must be a bounded tuple")
        if any(not isinstance(entry, TwinGapEntry) for entry in self.entries):
            raise TargetTwinGapLedgerError("entries contain invalid type")
        if len({entry.observation_id for entry in self.entries}) != len(self.entries):
            raise TargetTwinGapLedgerError("duplicate observation_id in ledger")
        expected_counts = (
            sum(e.classification == MATCH for e in self.entries),
            sum(e.classification == SURPRISE for e in self.entries),
            sum(e.classification == PHYSICAL_ONLY for e in self.entries),
            sum(e.classification == UNKNOWN for e in self.entries),
            sum(e.replay_state == OPEN_REPLAY_OBLIGATION for e in self.entries),
        )
        actual_counts = (self.match_count, self.surprise_count, self.physical_only_count,
                         self.unknown_count, self.open_replay_obligation_count)
        if actual_counts != expected_counts:
            raise TargetTwinGapLedgerError("ledger counts do not bind exact entries")
        _literal("ledger evidence_scope", self.evidence_scope, EVIDENCE_SCOPE)
        if any(v != 0 for v in (self.runtime_credit, self.physical_host_credit, self.completion_credit)):
            raise TargetTwinGapLedgerError("repository ledger cannot carry runtime/physical/completion credit")
        if self.whole_system_acceptance is not False:
            raise TargetTwinGapLedgerError("repository ledger cannot grant whole-system acceptance")
        identity = {
            "release_digest": self.release_digest,
            "target_profile_digest": self.target_profile_digest,
            "entries": [entry.as_dict() for entry in self.entries],
        }
        if self.ledger_id != "twin-gap-ledger:" + _digest(identity):
            raise TargetTwinGapLedgerError("ledger_id does not bind exact ledger content")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema, "ledger_id": self.ledger_id,
            "release_digest": self.release_digest, "target_profile_digest": self.target_profile_digest,
            "entries": [entry.as_dict() for entry in self.entries],
            "counts": {"match": self.match_count, "surprise": self.surprise_count,
                       "physical_only": self.physical_only_count, "unknown": self.unknown_count,
                       "open_replay_obligation": self.open_replay_obligation_count},
            "evidence_scope": self.evidence_scope,
            "credits": {"runtime": self.runtime_credit, "physical_host": self.physical_host_credit,
                        "completion": self.completion_credit,
                        "whole_system_acceptance": self.whole_system_acceptance},
        }


def build_ledger(*, release_digest: str, target_profile_digest: str,
                 correlations: Iterable[tuple[TwinPrediction | None, PhysicalObservationRef]]) -> TwinGapLedger:
    """Build a deterministic ledger from caller-supplied prediction/observation pairs."""
    release_digest = _sha256("release_digest", release_digest)
    target_profile_digest = _sha256("target_profile_digest", target_profile_digest)
    normalized: list[tuple[TwinPrediction | None, PhysicalObservationRef]] = []
    for pair in correlations:
        if type(pair) is not tuple or len(pair) != 2:
            raise TargetTwinGapLedgerError("each correlation must be an exact (prediction, observation) tuple")
        prediction, observation = pair
        if not isinstance(observation, PhysicalObservationRef):
            raise TargetTwinGapLedgerError("correlation observation type mismatch")
        if observation.release_digest != release_digest:
            raise TargetTwinGapLedgerError("observation release_digest does not match ledger")
        if observation.target_profile_digest != target_profile_digest:
            raise TargetTwinGapLedgerError("observation target_profile_digest does not match ledger")
        normalized.append((prediction, observation))
    if len(normalized) > _MAX_ENTRIES:
        raise TargetTwinGapLedgerError(f"ledger exceeds {_MAX_ENTRIES} entries")
    normalized.sort(key=lambda pair: (pair[1].sequence, pair[1].observation_id))
    if len({pair[1].observation_id for pair in normalized}) != len(normalized):
        raise TargetTwinGapLedgerError("duplicate observation_id supplied")

    entries = tuple(correlate(prediction, observation) for prediction, observation in normalized)
    identity = {"release_digest": release_digest, "target_profile_digest": target_profile_digest,
                "entries": [entry.as_dict() for entry in entries]}
    return TwinGapLedger(
        schema=TWIN_GAP_LEDGER_SCHEMA,
        ledger_id="twin-gap-ledger:" + _digest(identity),
        release_digest=release_digest,
        target_profile_digest=target_profile_digest,
        entries=entries,
        match_count=sum(e.classification == MATCH for e in entries),
        surprise_count=sum(e.classification == SURPRISE for e in entries),
        physical_only_count=sum(e.classification == PHYSICAL_ONLY for e in entries),
        unknown_count=sum(e.classification == UNKNOWN for e in entries),
        open_replay_obligation_count=sum(e.replay_state == OPEN_REPLAY_OBLIGATION for e in entries),
        evidence_scope=EVIDENCE_SCOPE,
        runtime_credit=0,
        physical_host_credit=0,
        completion_credit=0,
        whole_system_acceptance=False,
    )
