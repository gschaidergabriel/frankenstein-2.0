"""Deterministic Familiarity / prediction-error binding for Frankenstein 2.0.

F2-WP-302 generation 1.

The component combines an exact caller-supplied PredictionResidual with an explicit,
bounded familiarity signal. It does not infer familiarity, read memory payloads, query
UnifiedDB, call models/tools/providers, authorize effects, or mint completion.

Authority invariants:
    FAMILIARITY != OBSERVATION
    PREDICTION_MATCH != WORLD_TRUTH
    PREDICTION_MISMATCH != EFFECT_AUTHORITY
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from .prediction_contract import PredictionResidual

FAMILIARITY_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_EVIDENCE/v1"
BINDING_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_PREDICTION_BINDING/v1"

FAMILIARITY_KNOWN = "KNOWN"
FAMILIARITY_UNKNOWN = "UNKNOWN"
STATUS_MATCH = "MATCH"
STATUS_MISMATCH = "MISMATCH"
STATUS_UNKNOWN = "UNKNOWN"
CLASSIFICATION = "CANDIDATE_CALIBRATION_SIGNAL_NOT_OBSERVATION_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"

MAX_BASIS_POINTS = 10_000
_MAX_ID_LEN = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FamiliarityPredictionBindingError(ValueError):
    """Fail-closed WP302 contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FamiliarityPredictionBindingError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_ID_LEN or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise FamiliarityPredictionBindingError(f"{name} is invalid")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 1:
        raise FamiliarityPredictionBindingError("generation must be a positive integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FamiliarityPredictionBindingError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise FamiliarityPredictionBindingError(f"{name} must be an iterable")
    refs = tuple(_identifier(name, value) for value in values)
    if not refs:
        raise FamiliarityPredictionBindingError(f"{name} must contain evidence")
    if len(refs) != len(set(refs)):
        raise FamiliarityPredictionBindingError(f"{name} contains duplicates")
    return tuple(sorted(refs))


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _error_bp(residual: PredictionResidual) -> int:
    denominator = max(
        residual.compared_leaf_count + len(residual.missing_paths) + len(residual.unexpected_paths),
        1,
    )
    return min(MAX_BASIS_POINTS, residual.mismatch_count * MAX_BASIS_POINTS // denominator)


@dataclass(frozen=True, slots=True)
class FamiliarityEvidence:
    schema: str
    evidence_id: str
    target_id: str
    generation: int
    state: str
    score_bp: int | None
    evidence_refs: tuple[str, ...]
    classification: str = "EXPLICIT_FAMILIARITY_EVIDENCE_NOT_OBSERVATION_OR_TRUTH"

    def __post_init__(self) -> None:
        if self.schema != FAMILIARITY_SCHEMA:
            raise FamiliarityPredictionBindingError("familiarity schema mismatch")
        _identifier("evidence_id", self.evidence_id)
        _identifier("target_id", self.target_id)
        _generation(self.generation)
        if self.state not in {FAMILIARITY_KNOWN, FAMILIARITY_UNKNOWN}:
            raise FamiliarityPredictionBindingError("unsupported familiarity state")
        if self.state == FAMILIARITY_KNOWN:
            if type(self.score_bp) is not int or not 0 <= self.score_bp <= MAX_BASIS_POINTS:
                raise FamiliarityPredictionBindingError("KNOWN familiarity requires integer score_bp in [0, 10000]")
        elif self.score_bp is not None:
            raise FamiliarityPredictionBindingError("UNKNOWN familiarity must not carry score_bp")
        object.__setattr__(self, "evidence_refs", _refs("familiarity evidence_ref", self.evidence_refs))

    @classmethod
    def known(cls, *, evidence_id: str, target_id: str, generation: int, score_bp: int,
              evidence_refs: Iterable[str]) -> "FamiliarityEvidence":
        return cls(FAMILIARITY_SCHEMA, evidence_id, target_id, generation,
                   FAMILIARITY_KNOWN, score_bp, tuple(evidence_refs))

    @classmethod
    def unknown(cls, *, evidence_id: str, target_id: str, generation: int,
                evidence_refs: Iterable[str]) -> "FamiliarityEvidence":
        return cls(FAMILIARITY_SCHEMA, evidence_id, target_id, generation,
                   FAMILIARITY_UNKNOWN, None, tuple(evidence_refs))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class FamiliarityPredictionSignal:
    schema: str
    prediction_id: str
    observation_id: str | None
    target_id: str
    generation: int
    status: str
    residual_sha256: str | None
    observation_fingerprint_sha256: str | None
    familiarity_evidence_sha256: str
    familiarity_state: str
    familiarity_bp: int | None
    prediction_error_bp: int | None
    contradiction_preserved: bool
    attention_priority_bp: int
    evidence_refs: tuple[str, ...]
    classification: str = CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_familiarity_to_prediction(
    *,
    prediction_id: str,
    target_id: str,
    generation: int,
    familiarity: FamiliarityEvidence,
    residual: PredictionResidual | None,
    expected_residual_sha256: str | None,
    evidence_refs: Iterable[str],
) -> FamiliarityPredictionSignal:
    prediction_id = _identifier("prediction_id", prediction_id)
    target_id = _identifier("target_id", target_id)
    generation = _generation(generation)
    refs = _refs("binding evidence_ref", evidence_refs)
    if not isinstance(familiarity, FamiliarityEvidence):
        raise FamiliarityPredictionBindingError("familiarity must be FamiliarityEvidence")
    if familiarity.target_id != target_id or familiarity.generation != generation:
        raise FamiliarityPredictionBindingError("familiarity target/generation mismatch")

    familiarity_bp = familiarity.score_bp
    familiarity_priority = familiarity_bp if familiarity_bp is not None else 0

    if residual is None:
        if expected_residual_sha256 is not None:
            _sha256("expected_residual_sha256", expected_residual_sha256)
            raise FamiliarityPredictionBindingError("expected residual is unavailable")
        return FamiliarityPredictionSignal(
            BINDING_SCHEMA, prediction_id, None, target_id, generation, STATUS_UNKNOWN,
            None, None, familiarity.sha256(), familiarity.state, familiarity_bp, None,
            False, familiarity_priority, refs,
        )

    if not isinstance(residual, PredictionResidual):
        raise FamiliarityPredictionBindingError("residual must be PredictionResidual or None")
    if expected_residual_sha256 is None:
        raise FamiliarityPredictionBindingError("present residual requires expected_residual_sha256")
    expected_residual_sha256 = _sha256("expected_residual_sha256", expected_residual_sha256)
    if residual.prediction_id != prediction_id or residual.target_id != target_id:
        raise FamiliarityPredictionBindingError("prediction/target identity mismatch")
    if residual.generation != generation:
        raise FamiliarityPredictionBindingError("prediction generation mismatch")
    residual_sha = residual.sha256()
    if residual_sha != expected_residual_sha256:
        raise FamiliarityPredictionBindingError("residual digest mismatch")
    _identifier("observation_id", residual.observation_id)
    _sha256("observation_fingerprint_sha256", residual.observation_fingerprint_sha256)

    error_bp = _error_bp(residual)
    status = STATUS_MATCH if residual.exact_match else STATUS_MISMATCH
    contradiction = not residual.exact_match
    return FamiliarityPredictionSignal(
        BINDING_SCHEMA, prediction_id, residual.observation_id, target_id, generation, status,
        residual_sha, residual.observation_fingerprint_sha256, familiarity.sha256(),
        familiarity.state, familiarity_bp, error_bp, contradiction,
        max(familiarity_priority, error_bp), refs,
    )


__all__ = [
    "BINDING_SCHEMA", "FAMILIARITY_SCHEMA", "FAMILIARITY_KNOWN", "FAMILIARITY_UNKNOWN",
    "STATUS_MATCH", "STATUS_MISMATCH", "STATUS_UNKNOWN", "CLASSIFICATION",
    "FamiliarityEvidence", "FamiliarityPredictionBindingError", "FamiliarityPredictionSignal",
    "bind_familiarity_to_prediction",
]
