"""Deterministic Familiarity / prediction-error binding for Frankenstein 2.0.

F2-WP-302 generation 1.

This component binds an already-produced :class:`PredictionResidual` to explicit,
caller-supplied familiarity evidence.  It never reads memory payloads, computes semantic
similarity, observes the world, mutates durable state, invokes a model/provider/tool, or
authorizes effects/completion.

Authority boundary::

    FAMILIARITY != OBSERVATION
    RETRIEVAL_REFERENCE != WORLD_FACT
    PREDICTION_RESIDUAL != COMPLETION

A contradictory residual always remains a contradiction regardless of familiarity.  The
binding may only emit a candidate attention/retrieval signal for downstream Hyperposition
or GWT handling.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from .prediction_contract import PredictionResidual

FAMILIARITY_EVIDENCE_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_EVIDENCE/v1"
FAMILIARITY_PREDICTION_SIGNAL_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_PREDICTION_SIGNAL/v1"

RELATION_MATCH = "MATCH"
RELATION_MISMATCH = "MISMATCH"
RELATION_UNKNOWN = "UNKNOWN"

SIGNAL_CLASSIFICATION = (
    "EPISTEMIC_ATTENTION_CANDIDATE_NOT_OBSERVATION_TRUTH_EFFECT_OR_COMPLETION"
)

MAX_BASIS_POINTS = 10_000
_MAX_IDENTIFIER_LENGTH = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FamiliarityPredictionError(ValueError):
    """Fail-closed Familiarity/prediction binding error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise FamiliarityPredictionError(f"{name} must be a string")
    if not value or value != value.strip():
        raise FamiliarityPredictionError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise FamiliarityPredictionError(
            f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters"
        )
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise FamiliarityPredictionError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FamiliarityPredictionError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 1:
        raise FamiliarityPredictionError("generation must be a positive integer")
    return value


def _basis_points(name: str, value: Any) -> int:
    if type(value) is not int:
        raise FamiliarityPredictionError(f"{name} must be an integer basis-point value")
    if value < 0 or value > MAX_BASIS_POINTS:
        raise FamiliarityPredictionError(
            f"{name} must be between 0 and {MAX_BASIS_POINTS}"
        )
    return value


def _refs(name: str, values: Iterable[str], *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise FamiliarityPredictionError(f"{name} must be an iterable of references")
    refs = tuple(_identifier(name, value) for value in values)
    if not allow_empty and not refs:
        raise FamiliarityPredictionError(f"{name} must contain at least one reference")
    if len(set(refs)) != len(refs):
        raise FamiliarityPredictionError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FamiliarityEvidence:
    """Explicit bounded familiarity evidence supplied by an upstream adapter."""

    schema: str
    familiarity_score_bp: int
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != FAMILIARITY_EVIDENCE_SCHEMA:
            raise FamiliarityPredictionError("familiarity evidence schema mismatch")
        object.__setattr__(
            self,
            "familiarity_score_bp",
            _basis_points("familiarity_score_bp", self.familiarity_score_bp),
        )
        object.__setattr__(self, "evidence_refs", _refs("familiarity evidence_ref", self.evidence_refs))

    @classmethod
    def create(
        cls,
        *,
        familiarity_score_bp: int,
        evidence_refs: Iterable[str],
    ) -> "FamiliarityEvidence":
        return cls(
            schema=FAMILIARITY_EVIDENCE_SCHEMA,
            familiarity_score_bp=familiarity_score_bp,
            evidence_refs=tuple(evidence_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class FamiliarityPredictionSignal:
    schema: str
    prediction_id: str
    target_id: str
    observation_id: str
    generation: int
    residual_sha256: str
    residual_exact_match: bool
    residual_mismatch_count: int
    familiarity_score_bp: int
    familiarity_evidence_sha256: str
    relation: str
    attention_priority_bp: int
    familiarity_evidence_refs: tuple[str, ...]
    contradiction_evidence_refs: tuple[str, ...]
    classification: str = SIGNAL_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_familiarity_to_prediction_residual(
    *,
    residual: PredictionResidual,
    expected_prediction_id: str,
    expected_generation: int,
    expected_residual_sha256: str,
    familiarity: FamiliarityEvidence,
    contradiction_evidence_refs: Iterable[str] = (),
) -> FamiliarityPredictionSignal:
    """Bind exact residual identity to explicit familiarity evidence.

    Fail-closed fences prevent stale/mismatched residuals from being rebound.  A mismatch
    is never suppressed by familiarity: it is emitted as ``MISMATCH`` with maximum candidate
    attention priority and must retain explicit contradiction evidence.  An exact residual
    with positive familiarity emits ``MATCH``.  An exact residual with zero familiarity
    emits ``UNKNOWN`` rather than inventing familiarity support; the exact residual flag is
    still preserved separately.
    """

    if not isinstance(residual, PredictionResidual):
        raise FamiliarityPredictionError("residual must be a PredictionResidual")
    if not isinstance(familiarity, FamiliarityEvidence):
        raise FamiliarityPredictionError("familiarity must be FamiliarityEvidence")

    expected_prediction_id = _identifier("expected_prediction_id", expected_prediction_id)
    expected_generation = _generation(expected_generation)
    expected_residual_sha256 = _sha256(
        "expected_residual_sha256", expected_residual_sha256
    )

    actual_residual_sha256 = residual.sha256()
    if residual.prediction_id != expected_prediction_id:
        raise FamiliarityPredictionError("prediction_id fence mismatch")
    if residual.generation != expected_generation:
        raise FamiliarityPredictionError("generation fence mismatch")
    if actual_residual_sha256 != expected_residual_sha256:
        raise FamiliarityPredictionError("residual digest fence mismatch")

    contradiction_refs = _refs(
        "contradiction evidence_ref",
        contradiction_evidence_refs,
        allow_empty=True,
    )

    if residual.exact_match:
        if residual.mismatch_count != 0:
            raise FamiliarityPredictionError(
                "residual invariant violated: exact_match with nonzero mismatch_count"
            )
        relation = (
            RELATION_MATCH
            if familiarity.familiarity_score_bp > 0
            else RELATION_UNKNOWN
        )
        attention_priority_bp = familiarity.familiarity_score_bp
    else:
        if residual.mismatch_count < 1:
            raise FamiliarityPredictionError(
                "residual invariant violated: mismatch without mismatch_count"
            )
        if not contradiction_refs:
            raise FamiliarityPredictionError(
                "mismatching residual requires explicit contradiction evidence"
            )
        relation = RELATION_MISMATCH
        # A current contradiction may not be down-ranked out of attention by stale familiarity.
        attention_priority_bp = MAX_BASIS_POINTS

    return FamiliarityPredictionSignal(
        schema=FAMILIARITY_PREDICTION_SIGNAL_SCHEMA,
        prediction_id=residual.prediction_id,
        target_id=residual.target_id,
        observation_id=residual.observation_id,
        generation=residual.generation,
        residual_sha256=actual_residual_sha256,
        residual_exact_match=residual.exact_match,
        residual_mismatch_count=residual.mismatch_count,
        familiarity_score_bp=familiarity.familiarity_score_bp,
        familiarity_evidence_sha256=familiarity.sha256(),
        relation=relation,
        attention_priority_bp=attention_priority_bp,
        familiarity_evidence_refs=familiarity.evidence_refs,
        contradiction_evidence_refs=contradiction_refs,
    )


__all__ = [
    "FAMILIARITY_EVIDENCE_SCHEMA",
    "FAMILIARITY_PREDICTION_SIGNAL_SCHEMA",
    "RELATION_MATCH",
    "RELATION_MISMATCH",
    "RELATION_UNKNOWN",
    "SIGNAL_CLASSIFICATION",
    "MAX_BASIS_POINTS",
    "FamiliarityEvidence",
    "FamiliarityPredictionError",
    "FamiliarityPredictionSignal",
    "bind_familiarity_to_prediction_residual",
]
