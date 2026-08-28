"""Deterministic matched processing-credit / method-ablation primitive.

F2-WP-305 generation 1.

The primitive records explicit integer-valued baseline/intervention measurements and
compares them only when pair identity, experiment generation, metric schema and roles
match exactly. It may produce an improvement/regression/tie/insufficient-evidence
*credit candidate*. It never proves causality, validates a method, infers transfer
applicability, reads durable state, invokes a model/tool/provider, authorizes effects,
or mints completion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from collections.abc import Iterable
from typing import Any

from frankenstein2.typed_memory import KIND_METHOD, KIND_PROCESS, TypedMemoryRecord

PROCESSING_OUTCOME_SCHEMA = "FRANKENSTEIN2_PROCESSING_OUTCOME/v1"
PROCESSING_CREDIT_SCHEMA = "FRANKENSTEIN2_PROCESSING_CREDIT_CANDIDATE/v1"

ROLE_BASELINE = "BASELINE"
ROLE_INTERVENTION = "INTERVENTION"
DIRECTION_HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
DIRECTION_LOWER_IS_BETTER = "LOWER_IS_BETTER"

CLASS_IMPROVEMENT = "IMPROVEMENT_CREDIT_CANDIDATE_NOT_CAUSAL_PROOF"
CLASS_REGRESSION = "REGRESSION_EVIDENCE_NOT_METHOD_INVALIDATION"
CLASS_TIE = "TIE_NO_DIRECTIONAL_CREDIT"
CLASS_INSUFFICIENT = "INSUFFICIENT_MATCHED_EVIDENCE_NO_CREDIT"
OUTCOME_CLASSIFICATION = "EXPLICIT_PROCESSING_MEASUREMENT_NOT_CAUSAL_OR_COMPLETION_AUTHORITY"
CREDIT_AUTHORITY_BOUNDARY = "PROCESSING_CREDIT_CANDIDATE_NOT_WORLD_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"

_ALLOWED_ROLES = frozenset({ROLE_BASELINE, ROLE_INTERVENTION})
_ALLOWED_DIRECTIONS = frozenset({DIRECTION_HIGHER_IS_BETTER, DIRECTION_LOWER_IS_BETTER})
_MAX_ID_LEN = 512
_MAX_ABS_METRIC = 10**12
_MAX_MEASUREMENTS = 10**9
_OUTCOME_TOKEN = object()


class ProcessingCreditError(ValueError):
    """Fail-closed matched-ablation contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ProcessingCreditError(f"{name} must be a string")
    if not value or value != value.strip():
        raise ProcessingCreditError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise ProcessingCreditError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ProcessingCreditError(f"{name} contains control characters")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 1:
        raise ProcessingCreditError("experiment_generation must be a positive integer")
    return value


def _metric_value(value: Any) -> int:
    if type(value) is not int or abs(value) > _MAX_ABS_METRIC:
        raise ProcessingCreditError(
            f"metric_value must be an integer in [-{_MAX_ABS_METRIC}, {_MAX_ABS_METRIC}]"
        )
    return value


def _measurement_count(value: Any, name: str = "measurement_count") -> int:
    if type(value) is not int or value < 1 or value > _MAX_MEASUREMENTS:
        raise ProcessingCreditError(f"{name} must be an integer in [1, {_MAX_MEASUREMENTS}]")
    return value


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ProcessingCreditError(f"{name} must be an iterable of reference strings")
    normalized = tuple(_identifier(name, item) for item in values)
    if not normalized:
        raise ProcessingCreditError(f"{name} must contain at least one reference")
    if len(set(normalized)) != len(normalized):
        raise ProcessingCreditError(f"{name} contains duplicate references")
    return tuple(sorted(normalized))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, init=False)
class ProcessingOutcome:
    schema: str
    outcome_id: str
    pair_id: str
    experiment_generation: int
    role: str
    memory_kind: str
    memory_id: str
    lifecycle_generation: int
    typed_memory_sha256: str
    metric_id: str
    metric_unit: str
    metric_direction: str
    metric_value: int
    measurement_count: int
    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    classification: str

    def __init__(
        self,
        *,
        schema: str,
        outcome_id: str,
        pair_id: str,
        experiment_generation: int,
        role: str,
        memory_kind: str,
        memory_id: str,
        lifecycle_generation: int,
        typed_memory_sha256: str,
        metric_id: str,
        metric_unit: str,
        metric_direction: str,
        metric_value: int,
        measurement_count: int,
        evidence_refs: Iterable[str],
        provenance_refs: Iterable[str],
        classification: str,
        _token: object | None = None,
    ) -> None:
        if _token is not _OUTCOME_TOKEN:
            raise ProcessingCreditError("ProcessingOutcome must be created through create_processing_outcome")
        if schema != PROCESSING_OUTCOME_SCHEMA:
            raise ProcessingCreditError("processing outcome schema mismatch")
        outcome_id = _identifier("outcome_id", outcome_id)
        pair_id = _identifier("pair_id", pair_id)
        experiment_generation = _generation(experiment_generation)
        if role not in _ALLOWED_ROLES:
            raise ProcessingCreditError(f"unsupported outcome role: {role!r}")
        if memory_kind not in {KIND_METHOD, KIND_PROCESS}:
            raise ProcessingCreditError("processing outcome requires METHOD or PROCESS typed memory")
        memory_id = _identifier("memory_id", memory_id)
        if type(lifecycle_generation) is not int or lifecycle_generation < 0:
            raise ProcessingCreditError("lifecycle_generation must be a non-negative integer")
        typed_memory_sha256 = _identifier("typed_memory_sha256", typed_memory_sha256)
        if len(typed_memory_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in typed_memory_sha256):
            raise ProcessingCreditError("typed_memory_sha256 must be lowercase 64-hex SHA-256")
        metric_id = _identifier("metric_id", metric_id)
        metric_unit = _identifier("metric_unit", metric_unit)
        if metric_direction not in _ALLOWED_DIRECTIONS:
            raise ProcessingCreditError(f"unsupported metric_direction: {metric_direction!r}")
        metric_value = _metric_value(metric_value)
        measurement_count = _measurement_count(measurement_count)
        evidence_refs = _refs("evidence_ref", evidence_refs)
        provenance_refs = _refs("provenance_ref", provenance_refs)
        if classification != OUTCOME_CLASSIFICATION:
            raise ProcessingCreditError("processing outcome classification mismatch")

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "outcome_id", outcome_id)
        object.__setattr__(self, "pair_id", pair_id)
        object.__setattr__(self, "experiment_generation", experiment_generation)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "memory_kind", memory_kind)
        object.__setattr__(self, "memory_id", memory_id)
        object.__setattr__(self, "lifecycle_generation", lifecycle_generation)
        object.__setattr__(self, "typed_memory_sha256", typed_memory_sha256)
        object.__setattr__(self, "metric_id", metric_id)
        object.__setattr__(self, "metric_unit", metric_unit)
        object.__setattr__(self, "metric_direction", metric_direction)
        object.__setattr__(self, "metric_value", metric_value)
        object.__setattr__(self, "measurement_count", measurement_count)
        object.__setattr__(self, "evidence_refs", evidence_refs)
        object.__setattr__(self, "provenance_refs", provenance_refs)
        object.__setattr__(self, "classification", classification)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ProcessingCreditCandidate:
    schema: str
    pair_id: str
    experiment_generation: int
    metric_id: str
    metric_unit: str
    metric_direction: str
    baseline_outcome_id: str
    intervention_outcome_id: str
    baseline_outcome_sha256: str
    intervention_outcome_sha256: str
    baseline_metric_value: int
    intervention_metric_value: int
    oriented_delta: int
    baseline_measurement_count: int
    intervention_measurement_count: int
    required_min_measurements: int
    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    classification: str
    credit_allowed: bool
    authority_boundary: str = CREDIT_AUTHORITY_BOUNDARY

    def __post_init__(self) -> None:
        if self.schema != PROCESSING_CREDIT_SCHEMA:
            raise ProcessingCreditError("processing credit schema mismatch")
        if self.classification not in {CLASS_IMPROVEMENT, CLASS_REGRESSION, CLASS_TIE, CLASS_INSUFFICIENT}:
            raise ProcessingCreditError("processing credit classification mismatch")
        expected_credit = self.classification == CLASS_IMPROVEMENT
        if self.credit_allowed is not expected_credit:
            raise ProcessingCreditError("credit_allowed/classification mismatch")
        if self.authority_boundary != CREDIT_AUTHORITY_BOUNDARY:
            raise ProcessingCreditError("processing credit authority boundary mismatch")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def create_processing_outcome(
    *,
    typed_memory: TypedMemoryRecord,
    outcome_id: str,
    pair_id: str,
    experiment_generation: int,
    role: str,
    metric_id: str,
    metric_unit: str,
    metric_direction: str,
    metric_value: int,
    measurement_count: int,
    evidence_refs: Iterable[str],
    provenance_refs: Iterable[str],
) -> ProcessingOutcome:
    """Freeze one explicit measurement against one exact METHOD/PROCESS memory record."""
    if not isinstance(typed_memory, TypedMemoryRecord):
        raise ProcessingCreditError("typed_memory must be a TypedMemoryRecord")
    if typed_memory.memory_kind not in {KIND_METHOD, KIND_PROCESS}:
        raise ProcessingCreditError("processing outcome requires METHOD or PROCESS typed memory")
    return ProcessingOutcome(
        schema=PROCESSING_OUTCOME_SCHEMA,
        outcome_id=outcome_id,
        pair_id=pair_id,
        experiment_generation=experiment_generation,
        role=role,
        memory_kind=typed_memory.memory_kind,
        memory_id=typed_memory.memory_id,
        lifecycle_generation=typed_memory.lifecycle_generation,
        typed_memory_sha256=typed_memory.sha256(),
        metric_id=metric_id,
        metric_unit=metric_unit,
        metric_direction=metric_direction,
        metric_value=metric_value,
        measurement_count=measurement_count,
        evidence_refs=evidence_refs,
        provenance_refs=provenance_refs,
        classification=OUTCOME_CLASSIFICATION,
        _token=_OUTCOME_TOKEN,
    )


def _require_match(baseline: ProcessingOutcome, intervention: ProcessingOutcome) -> None:
    if not isinstance(baseline, ProcessingOutcome) or not isinstance(intervention, ProcessingOutcome):
        raise ProcessingCreditError("baseline and intervention must be ProcessingOutcome values")
    if baseline.role != ROLE_BASELINE or intervention.role != ROLE_INTERVENTION:
        raise ProcessingCreditError("comparison requires BASELINE then INTERVENTION roles")
    checks = {
        "pair_id": (baseline.pair_id, intervention.pair_id),
        "experiment_generation": (baseline.experiment_generation, intervention.experiment_generation),
        "metric_id": (baseline.metric_id, intervention.metric_id),
        "metric_unit": (baseline.metric_unit, intervention.metric_unit),
        "metric_direction": (baseline.metric_direction, intervention.metric_direction),
    }
    mismatches = [name for name, (left, right) in checks.items() if left != right]
    if mismatches:
        raise ProcessingCreditError(f"matched-ablation fence mismatch: {mismatches!r}")
    if baseline.outcome_id == intervention.outcome_id:
        raise ProcessingCreditError("baseline and intervention outcome_id must differ")
    if baseline.sha256() == intervention.sha256():
        raise ProcessingCreditError("baseline and intervention outcome digests must differ")


def evaluate_processing_credit(
    baseline: ProcessingOutcome,
    intervention: ProcessingOutcome,
    *,
    min_measurements: int = 1,
) -> ProcessingCreditCandidate:
    """Compare one exact matched pair without upgrading association into causal proof."""
    _require_match(baseline, intervention)
    min_measurements = _measurement_count(min_measurements, "min_measurements")

    if baseline.metric_direction == DIRECTION_HIGHER_IS_BETTER:
        oriented_delta = intervention.metric_value - baseline.metric_value
    else:
        oriented_delta = baseline.metric_value - intervention.metric_value

    enough = baseline.measurement_count >= min_measurements and intervention.measurement_count >= min_measurements
    if not enough:
        classification = CLASS_INSUFFICIENT
        credit_allowed = False
    elif oriented_delta > 0:
        classification = CLASS_IMPROVEMENT
        credit_allowed = True
    elif oriented_delta < 0:
        classification = CLASS_REGRESSION
        credit_allowed = False
    else:
        classification = CLASS_TIE
        credit_allowed = False

    evidence_refs = tuple(sorted(set(baseline.evidence_refs + intervention.evidence_refs)))
    provenance_refs = tuple(sorted(set(baseline.provenance_refs + intervention.provenance_refs)))

    return ProcessingCreditCandidate(
        schema=PROCESSING_CREDIT_SCHEMA,
        pair_id=baseline.pair_id,
        experiment_generation=baseline.experiment_generation,
        metric_id=baseline.metric_id,
        metric_unit=baseline.metric_unit,
        metric_direction=baseline.metric_direction,
        baseline_outcome_id=baseline.outcome_id,
        intervention_outcome_id=intervention.outcome_id,
        baseline_outcome_sha256=baseline.sha256(),
        intervention_outcome_sha256=intervention.sha256(),
        baseline_metric_value=baseline.metric_value,
        intervention_metric_value=intervention.metric_value,
        oriented_delta=oriented_delta,
        baseline_measurement_count=baseline.measurement_count,
        intervention_measurement_count=intervention.measurement_count,
        required_min_measurements=min_measurements,
        evidence_refs=evidence_refs,
        provenance_refs=provenance_refs,
        classification=classification,
        credit_allowed=credit_allowed,
    )


__all__ = [
    "CLASS_IMPROVEMENT",
    "CLASS_INSUFFICIENT",
    "CLASS_REGRESSION",
    "CLASS_TIE",
    "DIRECTION_HIGHER_IS_BETTER",
    "DIRECTION_LOWER_IS_BETTER",
    "PROCESSING_CREDIT_SCHEMA",
    "PROCESSING_OUTCOME_SCHEMA",
    "ROLE_BASELINE",
    "ROLE_INTERVENTION",
    "ProcessingCreditCandidate",
    "ProcessingCreditError",
    "ProcessingOutcome",
    "create_processing_outcome",
    "evaluate_processing_credit",
]
