"""Deterministic Familiarity / prediction-error binding for Frankenstein 2.0.

F2-WP-302 generation 1.

This module binds an explicit caller-supplied familiarity signal to an exact
F2-WP-202 :class:`PredictionResidual`.  It does not infer familiarity, facts,
semantics, relevance, actions, completion, or authority.

Authority boundaries::

    FAMILIARITY_SIGNAL != OBSERVATION
    PREDICTION_RESIDUAL != WORLD_TRUTH
    BINDING_CLASSIFICATION != EFFECT_OR_COMPLETION_AUTHORITY

The primitive is persistence-agnostic and deterministic.  It performs no clock,
UnifiedDB, provider, model, tool, network, or effect operation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterable

from .prediction_contract import (
    PREDICTION_RESIDUAL_SCHEMA,
    PredictionResidual,
)

FAMILIARITY_SIGNAL_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_SIGNAL/v1"
FAMILIARITY_POLICY_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_BINDING_POLICY/v1"
FAMILIARITY_BINDING_SCHEMA = "FRANKENSTEIN2_FAMILIARITY_PREDICTION_ERROR_BINDING/v1"

FAMILIARITY_KNOWN = "KNOWN"
FAMILIARITY_UNKNOWN = "UNKNOWN"
_ALLOWED_SIGNAL_STATES = frozenset({FAMILIARITY_KNOWN, FAMILIARITY_UNKNOWN})

CLASS_FAMILIAR_MATCH = "FAMILIAR_EXACT_MATCH_CANDIDATE"
CLASS_LOW_FAMILIARITY_MATCH = "LOW_FAMILIARITY_EXACT_MATCH_CANDIDATE"
CLASS_FAMILIAR_CONTRADICTION = "FAMILIAR_PREDICTION_ERROR_CONTRADICTION"
CLASS_HIGH_ERROR_LOW_FAMILIARITY = "HIGH_PREDICTION_ERROR_LOW_FAMILIARITY"
CLASS_BOUNDED_MISMATCH = "BOUNDED_PREDICTION_MISMATCH"
CLASS_UNKNOWN_FAMILIARITY = "UNKNOWN_FAMILIARITY_WITH_EXPLICIT_RESIDUAL"

BINDING_CLASSIFICATION = (
    "CANDIDATE_CALIBRATION_SIGNAL_NOT_OBSERVATION_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"
)

MAX_BASIS_POINTS = 10_000
_MAX_IDENTIFIER_LENGTH = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FamiliarityPredictionError(ValueError):
    """Fail-closed familiarity/prediction-error contract error."""


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


def _positive_generation(value: Any) -> int:
    if type(value) is not int or value < 1:
        raise FamiliarityPredictionError("generation must be a positive integer")
    return value


def _basis_points(name: str, value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or value > MAX_BASIS_POINTS:
        raise FamiliarityPredictionError(
            f"{name} must be an integer in [{minimum}, {MAX_BASIS_POINTS}]"
        )
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise FamiliarityPredictionError(f"{name} must be an iterable of references")
    refs = tuple(_identifier(name, value) for value in values)
    if not refs:
        raise FamiliarityPredictionError(f"{name} must contain at least one reference")
    if len(set(refs)) != len(refs):
        raise FamiliarityPredictionError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_residual(residual: PredictionResidual) -> None:
    if not isinstance(residual, PredictionResidual):
        raise FamiliarityPredictionError("residual must be a PredictionResidual")
    if residual.schema != PREDICTION_RESIDUAL_SCHEMA:
        raise FamiliarityPredictionError("prediction residual schema mismatch")
    _identifier("prediction_id", residual.prediction_id)
    _identifier("observation_id", residual.observation_id)
    _identifier("target_id", residual.target_id)
    _positive_generation(residual.generation)
    _sha256("basis_fingerprint_sha256", residual.basis_fingerprint_sha256)
    _sha256("observation_fingerprint_sha256", residual.observation_fingerprint_sha256)
    _sha256("expected_projection_sha256", residual.expected_projection_sha256)
    _sha256("observed_projection_sha256", residual.observed_projection_sha256)

    count_fields = (
        residual.mismatch_count,
        residual.expected_leaf_count,
        residual.observed_leaf_count,
        residual.compared_leaf_count,
    )
    if any(type(value) is not int or value < 0 for value in count_fields):
        raise FamiliarityPredictionError("residual count fields must be non-negative integers")
    if not isinstance(residual.exact_match, bool):
        raise FamiliarityPredictionError("residual exact_match must be boolean")
    if not isinstance(residual.mismatch_fraction, float) or not math.isfinite(
        residual.mismatch_fraction
    ):
        raise FamiliarityPredictionError("residual mismatch_fraction must be finite float")
    if residual.mismatch_fraction < 0.0 or residual.mismatch_fraction > 1.0:
        raise FamiliarityPredictionError("residual mismatch_fraction outside [0, 1]")

    path_groups = (
        residual.changed_paths,
        residual.missing_paths,
        residual.unexpected_paths,
        residual.type_mismatch_paths,
    )
    for paths in path_groups:
        if not isinstance(paths, tuple) or any(not isinstance(path, str) for path in paths):
            raise FamiliarityPredictionError("residual paths must be tuples of strings")
        if len(paths) != len(set(paths)):
            raise FamiliarityPredictionError("residual path lists must not contain duplicates")
    if not set(residual.type_mismatch_paths).issubset(set(residual.changed_paths)):
        raise FamiliarityPredictionError("type mismatch paths must be changed paths")

    expected_mismatch_count = (
        len(residual.changed_paths)
        + len(residual.missing_paths)
        + len(residual.unexpected_paths)
    )
    if residual.mismatch_count != expected_mismatch_count:
        raise FamiliarityPredictionError("residual mismatch_count is internally inconsistent")
    if residual.exact_match != (residual.mismatch_count == 0):
        raise FamiliarityPredictionError("residual exact_match is internally inconsistent")

    denominator = max(
        residual.compared_leaf_count
        + len(residual.missing_paths)
        + len(residual.unexpected_paths),
        1,
    )
    if residual.mismatch_count > denominator:
        raise FamiliarityPredictionError("residual mismatch_count exceeds comparison opportunities")
    expected_fraction = residual.mismatch_count / denominator
    if not math.isclose(
        residual.mismatch_fraction,
        expected_fraction,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise FamiliarityPredictionError("residual mismatch_fraction is internally inconsistent")

    if type(residual.numeric_l1) is not float or not math.isfinite(residual.numeric_l1):
        raise FamiliarityPredictionError("residual numeric_l1 must be finite float")
    if residual.numeric_l1 < 0.0:
        raise FamiliarityPredictionError("residual numeric_l1 must be non-negative")
    numeric_sum = 0.0
    seen_numeric_paths: set[str] = set()
    for pair in residual.numeric_absolute_residuals:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise FamiliarityPredictionError("numeric residual entries must be (path, magnitude)")
        path, magnitude = pair
        if not isinstance(path, str) or path in seen_numeric_paths:
            raise FamiliarityPredictionError("numeric residual paths must be unique strings")
        if type(magnitude) is not float or not math.isfinite(magnitude) or magnitude < 0.0:
            raise FamiliarityPredictionError("numeric residual magnitudes must be finite non-negative floats")
        seen_numeric_paths.add(path)
        numeric_sum += magnitude
    if not math.isclose(residual.numeric_l1, numeric_sum, rel_tol=0.0, abs_tol=1e-12):
        raise FamiliarityPredictionError("residual numeric_l1 is internally inconsistent")


@dataclass(frozen=True, slots=True)
class FamiliaritySignal:
    schema: str
    signal_id: str
    target_id: str
    generation: int
    state: str
    score_bp: int | None
    evidence_refs: tuple[str, ...]
    classification: str = "EXPLICIT_FAMILIARITY_SIGNAL_NOT_OBSERVATION_OR_TRUTH"

    def __post_init__(self) -> None:
        if self.schema != FAMILIARITY_SIGNAL_SCHEMA:
            raise FamiliarityPredictionError("familiarity signal schema mismatch")
        _identifier("signal_id", self.signal_id)
        _identifier("target_id", self.target_id)
        _positive_generation(self.generation)
        if self.state not in _ALLOWED_SIGNAL_STATES:
            raise FamiliarityPredictionError("unsupported familiarity state")
        if self.state == FAMILIARITY_KNOWN:
            _basis_points("score_bp", self.score_bp)
        elif self.score_bp is not None:
            raise FamiliarityPredictionError("UNKNOWN familiarity must not carry a score")
        object.__setattr__(self, "evidence_refs", _refs("familiarity evidence_ref", self.evidence_refs))

    @classmethod
    def known(
        cls,
        *,
        signal_id: str,
        target_id: str,
        generation: int,
        score_bp: int,
        evidence_refs: Iterable[str],
    ) -> "FamiliaritySignal":
        return cls(
            schema=FAMILIARITY_SIGNAL_SCHEMA,
            signal_id=signal_id,
            target_id=target_id,
            generation=generation,
            state=FAMILIARITY_KNOWN,
            score_bp=score_bp,
            evidence_refs=tuple(evidence_refs),
        )

    @classmethod
    def unknown(
        cls,
        *,
        signal_id: str,
        target_id: str,
        generation: int,
        evidence_refs: Iterable[str],
    ) -> "FamiliaritySignal":
        return cls(
            schema=FAMILIARITY_SIGNAL_SCHEMA,
            signal_id=signal_id,
            target_id=target_id,
            generation=generation,
            state=FAMILIARITY_UNKNOWN,
            score_bp=None,
            evidence_refs=tuple(evidence_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class FamiliarityBindingPolicy:
    schema: str
    familiar_threshold_bp: int
    high_prediction_error_threshold_bp: int

    def __post_init__(self) -> None:
        if self.schema != FAMILIARITY_POLICY_SCHEMA:
            raise FamiliarityPredictionError("familiarity policy schema mismatch")
        _basis_points("familiar_threshold_bp", self.familiar_threshold_bp, minimum=1)
        _basis_points(
            "high_prediction_error_threshold_bp",
            self.high_prediction_error_threshold_bp,
            minimum=1,
        )

    @classmethod
    def create(
        cls,
        *,
        familiar_threshold_bp: int = 7000,
        high_prediction_error_threshold_bp: int = 2500,
    ) -> "FamiliarityBindingPolicy":
        return cls(
            schema=FAMILIARITY_POLICY_SCHEMA,
            familiar_threshold_bp=familiar_threshold_bp,
            high_prediction_error_threshold_bp=high_prediction_error_threshold_bp,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class FamiliarityPredictionBinding:
    schema: str
    binding_id: str
    prediction_id: str
    observation_id: str
    target_id: str
    generation: int
    familiarity_signal_id: str
    familiarity_signal_sha256: str
    familiarity_state: str
    familiarity_score_bp: int | None
    prediction_residual_sha256: str
    residual_evidence_refs: tuple[str, ...]
    mismatch_bp: int
    exact_match: bool
    contradiction_preserved: bool
    calibration_class: str
    policy_sha256: str
    classification: str = BINDING_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_familiarity_to_prediction_error(
    *,
    binding_id: str,
    signal: FamiliaritySignal,
    residual: PredictionResidual,
    expected_residual_sha256: str,
    residual_evidence_refs: Iterable[str],
    policy: FamiliarityBindingPolicy,
) -> FamiliarityPredictionBinding:
    """Bind explicit familiarity evidence to one exact prediction residual.

    The result is a candidate calibration/contradiction signal.  It never promotes
    either input to observation, truth, retrieval authority, effect authority, or
    completion authority.
    """

    binding_id = _identifier("binding_id", binding_id)
    if not isinstance(signal, FamiliaritySignal):
        raise FamiliarityPredictionError("signal must be a FamiliaritySignal")
    if not isinstance(policy, FamiliarityBindingPolicy):
        raise FamiliarityPredictionError("policy must be a FamiliarityBindingPolicy")
    _validate_residual(residual)
    expected_residual_sha256 = _sha256(
        "expected_residual_sha256", expected_residual_sha256
    )
    observed_residual_sha256 = residual.sha256()
    if observed_residual_sha256 != expected_residual_sha256:
        raise FamiliarityPredictionError("prediction residual digest mismatch")
    evidence_refs = _refs("residual evidence_ref", residual_evidence_refs)

    if signal.target_id != residual.target_id:
        raise FamiliarityPredictionError("familiarity target does not match residual target")
    if signal.generation != residual.generation:
        raise FamiliarityPredictionError("familiarity generation does not match residual generation")

    denominator = max(
        residual.compared_leaf_count
        + len(residual.missing_paths)
        + len(residual.unexpected_paths),
        1,
    )
    mismatch_bp = min(
        MAX_BASIS_POINTS,
        (residual.mismatch_count * MAX_BASIS_POINTS) // denominator,
    )

    contradiction_preserved = False
    if signal.state == FAMILIARITY_UNKNOWN:
        calibration_class = CLASS_UNKNOWN_FAMILIARITY
    else:
        assert signal.score_bp is not None
        familiar = signal.score_bp >= policy.familiar_threshold_bp
        high_error = mismatch_bp >= policy.high_prediction_error_threshold_bp
        if residual.exact_match:
            calibration_class = (
                CLASS_FAMILIAR_MATCH if familiar else CLASS_LOW_FAMILIARITY_MATCH
            )
        elif familiar and high_error:
            calibration_class = CLASS_FAMILIAR_CONTRADICTION
            contradiction_preserved = True
        elif high_error:
            calibration_class = CLASS_HIGH_ERROR_LOW_FAMILIARITY
        else:
            calibration_class = CLASS_BOUNDED_MISMATCH

    return FamiliarityPredictionBinding(
        schema=FAMILIARITY_BINDING_SCHEMA,
        binding_id=binding_id,
        prediction_id=residual.prediction_id,
        observation_id=residual.observation_id,
        target_id=residual.target_id,
        generation=residual.generation,
        familiarity_signal_id=signal.signal_id,
        familiarity_signal_sha256=signal.sha256(),
        familiarity_state=signal.state,
        familiarity_score_bp=signal.score_bp,
        prediction_residual_sha256=observed_residual_sha256,
        residual_evidence_refs=evidence_refs,
        mismatch_bp=mismatch_bp,
        exact_match=residual.exact_match,
        contradiction_preserved=contradiction_preserved,
        calibration_class=calibration_class,
        policy_sha256=policy.sha256(),
    )


__all__ = [
    "BINDING_CLASSIFICATION",
    "CLASS_BOUNDED_MISMATCH",
    "CLASS_FAMILIAR_CONTRADICTION",
    "CLASS_FAMILIAR_MATCH",
    "CLASS_HIGH_ERROR_LOW_FAMILIARITY",
    "CLASS_LOW_FAMILIARITY_MATCH",
    "CLASS_UNKNOWN_FAMILIARITY",
    "FAMILIARITY_BINDING_SCHEMA",
    "FAMILIARITY_KNOWN",
    "FAMILIARITY_POLICY_SCHEMA",
    "FAMILIARITY_SIGNAL_SCHEMA",
    "FAMILIARITY_UNKNOWN",
    "FamiliarityBindingPolicy",
    "FamiliarityPredictionBinding",
    "FamiliarityPredictionError",
    "FamiliaritySignal",
    "bind_familiarity_to_prediction_error",
]
