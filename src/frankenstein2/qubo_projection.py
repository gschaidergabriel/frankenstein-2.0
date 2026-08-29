"""Deterministic QUBO projection adapter for Frankenstein 2.0.

F2-WP-402 generation 1. This module projects an exact noncanonical WorldSlice into a
bounded quadratic unconstrained binary-optimization (QUBO) problem using only explicit
caller-supplied coefficients. It never infers coefficients, chooses an action, invokes a
solver/model/provider/tool, mutates world state, or grants truth/effect/completion authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .sparse_world_basis import WorldSlice


QUBO_VARIABLE_SCHEMA = "FRANKENSTEIN2_QUBO_VARIABLE/v1"
QUBO_COUPLING_SCHEMA = "FRANKENSTEIN2_QUBO_COUPLING/v1"
QUBO_PROJECTION_SCHEMA = "FRANKENSTEIN2_QUBO_PROJECTION/v1"
QUBO_SCORE_SCHEMA = "FRANKENSTEIN2_QUBO_ASSIGNMENT_SCORE/v1"
COEFFICIENT_ABS_MAX = 1_000_000_000


class QuboProjectionError(ValueError):
    """Fail-closed validation error for QUBO projection/scoring."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise QuboProjectionError(f"{name} must be a non-empty trimmed string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise QuboProjectionError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise QuboProjectionError(f"{name} must be a non-negative integer")
    return value


def _coefficient(name: str, value: Any) -> int:
    if type(value) is not int or not -COEFFICIENT_ABS_MAX <= value <= COEFFICIENT_ABS_MAX:
        raise QuboProjectionError(
            f"{name} must be an integer in [-{COEFFICIENT_ABS_MAX}, {COEFFICIENT_ABS_MAX}]"
        )
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise QuboProjectionError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise QuboProjectionError(f"{name} must be an immutable tuple")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if not allow_empty and not refs:
        raise QuboProjectionError(f"{name} must not be empty")
    if len(set(refs)) != len(refs):
        raise QuboProjectionError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise QuboProjectionError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class QuboVariable:
    variable_id: str
    source_ref: str
    linear_bias: int
    provenance_refs: tuple[str, ...]

    schema = QUBO_VARIABLE_SCHEMA
    classification = "CALLER_SUPPLIED_OPTIMIZATION_TERM_NOT_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable_id", _text("variable_id", self.variable_id))
        object.__setattr__(self, "source_ref", _text("source_ref", self.source_ref))
        _coefficient("linear_bias", self.linear_bias)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "variable_id": self.variable_id,
            "source_ref": self.source_ref,
            "linear_bias": self.linear_bias,
            "provenance_refs": list(self.provenance_refs),
            "truth_authority": "NONE",
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class QuboCoupling:
    left_variable_id: str
    right_variable_id: str
    weight: int
    provenance_refs: tuple[str, ...]

    schema = QUBO_COUPLING_SCHEMA
    classification = "CALLER_SUPPLIED_OPTIMIZATION_TERM_NOT_CAUSAL_PROOF"

    def __post_init__(self) -> None:
        left = _text("left_variable_id", self.left_variable_id)
        right = _text("right_variable_id", self.right_variable_id)
        if left == right:
            raise QuboProjectionError("QUBO coupling must reference two distinct variables")
        if right < left:
            left, right = right, left
        object.__setattr__(self, "left_variable_id", left)
        object.__setattr__(self, "right_variable_id", right)
        _coefficient("weight", self.weight)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    @property
    def pair(self) -> tuple[str, str]:
        return (self.left_variable_id, self.right_variable_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "left_variable_id": self.left_variable_id,
            "right_variable_id": self.right_variable_id,
            "weight": self.weight,
            "provenance_refs": list(self.provenance_refs),
            "causal_authority": "NONE",
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class QuboProjection:
    projection_id: str
    slice_id: str
    slice_sha256: str
    cycle_id: str
    generation: int
    vector_space_version: str
    variables: tuple[QuboVariable, ...]
    couplings: tuple[QuboCoupling, ...]
    offset: int
    provenance_refs: tuple[str, ...]

    schema = QUBO_PROJECTION_SCHEMA
    classification = "NONCANONICAL_OPTIMIZATION_PROJECTION"

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_id", _text("projection_id", self.projection_id))
        object.__setattr__(self, "slice_id", _text("slice_id", self.slice_id))
        object.__setattr__(self, "slice_sha256", _sha256("slice_sha256", self.slice_sha256))
        object.__setattr__(self, "cycle_id", _text("cycle_id", self.cycle_id))
        _generation("generation", self.generation)
        object.__setattr__(self, "vector_space_version", _text("vector_space_version", self.vector_space_version))
        if not isinstance(self.variables, tuple) or not self.variables or not all(isinstance(v, QuboVariable) for v in self.variables):
            raise QuboProjectionError("variables must be a non-empty immutable tuple of QuboVariable")
        if not isinstance(self.couplings, tuple) or not all(isinstance(c, QuboCoupling) for c in self.couplings):
            raise QuboProjectionError("couplings must be an immutable tuple of QuboCoupling")
        variable_ids = tuple(v.variable_id for v in self.variables)
        if len(set(variable_ids)) != len(variable_ids):
            raise QuboProjectionError("duplicate variable_id")
        if variable_ids != tuple(sorted(variable_ids)):
            raise QuboProjectionError("variables must be canonicalized by variable_id")
        pairs = tuple(c.pair for c in self.couplings)
        if len(set(pairs)) != len(pairs):
            raise QuboProjectionError("duplicate QUBO coupling pair")
        if pairs != tuple(sorted(pairs)):
            raise QuboProjectionError("couplings must be canonicalized by variable pair")
        known = set(variable_ids)
        if any(left not in known or right not in known for left, right in pairs):
            raise QuboProjectionError("QUBO coupling references unknown variable")
        _coefficient("offset", self.offset)
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "projection_id": self.projection_id,
            "slice_id": self.slice_id,
            "slice_sha256": self.slice_sha256,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "vector_space_version": self.vector_space_version,
            "variables": [v.as_dict() for v in self.variables],
            "couplings": [c.as_dict() for c in self.couplings],
            "offset": self.offset,
            "provenance_refs": list(self.provenance_refs),
            "solver_invoked": False,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class QuboAssignmentScore:
    projection_id: str
    projection_sha256: str
    assignment: tuple[tuple[str, int], ...]
    objective_value: int

    schema = QUBO_SCORE_SCHEMA
    classification = "DETERMINISTIC_SCORE_NOT_DECISION_OR_EFFECT"

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_id", _text("projection_id", self.projection_id))
        object.__setattr__(self, "projection_sha256", _sha256("projection_sha256", self.projection_sha256))
        if not isinstance(self.assignment, tuple) or not self.assignment:
            raise QuboProjectionError("assignment must be a non-empty immutable tuple")
        ids: list[str] = []
        normalized: list[tuple[str, int]] = []
        for item in self.assignment:
            if not isinstance(item, tuple) or len(item) != 2:
                raise QuboProjectionError("assignment items must be (variable_id, bit) tuples")
            variable_id = _text("assignment variable_id", item[0])
            bit = item[1]
            if type(bit) is not int or bit not in (0, 1):
                raise QuboProjectionError("assignment bits must be integer 0 or 1")
            ids.append(variable_id)
            normalized.append((variable_id, bit))
        if len(set(ids)) != len(ids):
            raise QuboProjectionError("assignment contains duplicate variable_id")
        if tuple(ids) != tuple(sorted(ids)):
            raise QuboProjectionError("assignment must be canonicalized by variable_id")
        object.__setattr__(self, "assignment", tuple(normalized))
        if type(self.objective_value) is not int:
            raise QuboProjectionError("objective_value must be an integer")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "projection_id": self.projection_id,
            "projection_sha256": self.projection_sha256,
            "assignment": [[variable_id, bit] for variable_id, bit in self.assignment],
            "objective_value": self.objective_value,
            "selected_as_action": False,
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def build_qubo_projection(
    *,
    projection_id: str,
    world_slice: WorldSlice,
    expected_slice_sha256: str,
    expected_generation: int,
    variables: tuple[QuboVariable, ...],
    couplings: tuple[QuboCoupling, ...],
    offset: int = 0,
    provenance_refs: tuple[str, ...],
) -> QuboProjection:
    """Bind explicit QUBO terms to one exact bounded WorldSlice."""
    if not isinstance(world_slice, WorldSlice):
        raise QuboProjectionError("world_slice must be WorldSlice")
    expected_sha = _sha256("expected_slice_sha256", expected_slice_sha256)
    generation = _generation("expected_generation", expected_generation)
    if world_slice.sha256() != expected_sha:
        raise QuboProjectionError("world_slice digest mismatch")
    if world_slice.generation != generation:
        raise QuboProjectionError("world_slice generation mismatch")
    if not isinstance(variables, tuple) or not variables or not all(isinstance(v, QuboVariable) for v in variables):
        raise QuboProjectionError("variables must be a non-empty immutable tuple of QuboVariable")
    if not isinstance(couplings, tuple) or not all(isinstance(c, QuboCoupling) for c in couplings):
        raise QuboProjectionError("couplings must be an immutable tuple of QuboCoupling")

    variable_ids = tuple(v.variable_id for v in variables)
    if len(set(variable_ids)) != len(variable_ids):
        raise QuboProjectionError("duplicate variable_id")
    selected_refs = set(world_slice.selected_atom_ids) | set(world_slice.selected_operator_ids)
    tainted_refs = set(world_slice.tainted_atom_ids)
    for variable in variables:
        if variable.source_ref not in selected_refs:
            raise QuboProjectionError("QUBO variable source_ref is outside selected WorldSlice")
        if variable.source_ref in tainted_refs:
            raise QuboProjectionError("QUBO variable source_ref is tainted/NOT_COMPUTED")

    canonical_variables = tuple(sorted(variables, key=lambda item: item.variable_id))
    canonical_couplings = tuple(sorted(couplings, key=lambda item: item.pair))
    pairs = tuple(item.pair for item in canonical_couplings)
    if len(set(pairs)) != len(pairs):
        raise QuboProjectionError("duplicate QUBO coupling pair")
    known = set(variable_ids)
    if any(left not in known or right not in known for left, right in pairs):
        raise QuboProjectionError("QUBO coupling references unknown variable")

    refs = set(_refs("provenance_refs", provenance_refs))
    refs.update(world_slice.evidence_refs)
    for variable in canonical_variables:
        refs.update(variable.provenance_refs)
    for coupling in canonical_couplings:
        refs.update(coupling.provenance_refs)

    return QuboProjection(
        projection_id=projection_id,
        slice_id=world_slice.slice_id,
        slice_sha256=expected_sha,
        cycle_id=world_slice.cycle_id,
        generation=generation,
        vector_space_version=world_slice.vector_space_version,
        variables=canonical_variables,
        couplings=canonical_couplings,
        offset=offset,
        provenance_refs=tuple(sorted(refs)),
    )


def score_assignment(
    *,
    projection: QuboProjection,
    assignment: tuple[tuple[str, int], ...],
    expected_projection_sha256: str,
) -> QuboAssignmentScore:
    """Score one complete explicit binary assignment; never selects or executes it."""
    if not isinstance(projection, QuboProjection):
        raise QuboProjectionError("projection must be QuboProjection")
    expected_sha = _sha256("expected_projection_sha256", expected_projection_sha256)
    if projection.sha256() != expected_sha:
        raise QuboProjectionError("projection digest mismatch")
    if not isinstance(assignment, tuple) or not assignment:
        raise QuboProjectionError("assignment must be a non-empty immutable tuple")

    bits: dict[str, int] = {}
    for item in assignment:
        if not isinstance(item, tuple) or len(item) != 2:
            raise QuboProjectionError("assignment items must be (variable_id, bit) tuples")
        variable_id = _text("assignment variable_id", item[0])
        bit = item[1]
        if type(bit) is not int or bit not in (0, 1):
            raise QuboProjectionError("assignment bits must be integer 0 or 1")
        if variable_id in bits:
            raise QuboProjectionError("assignment contains duplicate variable_id")
        bits[variable_id] = bit

    required = {variable.variable_id for variable in projection.variables}
    supplied = set(bits)
    if supplied != required:
        missing = sorted(required - supplied)
        extra = sorted(supplied - required)
        raise QuboProjectionError(f"assignment variable set mismatch missing={missing} extra={extra}")

    total = projection.offset
    for variable in projection.variables:
        total += variable.linear_bias * bits[variable.variable_id]
    for coupling in projection.couplings:
        total += coupling.weight * bits[coupling.left_variable_id] * bits[coupling.right_variable_id]

    canonical_assignment = tuple(sorted(bits.items()))
    return QuboAssignmentScore(
        projection_id=projection.projection_id,
        projection_sha256=expected_sha,
        assignment=canonical_assignment,
        objective_value=total,
    )
