"""Deterministic solver-neutral QUBO projection for Frankenstein 2.0.

This module projects an exact noncanonical ``WorldSlice`` into an immutable binary
quadratic objective supplied by the caller. It does not invent an objective, run a
solver, infer world truth, authorize effects, or mint completion.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, ClassVar

from frankenstein2.sparse_world_basis import WorldSlice


QUBO_VARIABLE_SCHEMA = "FRANKENSTEIN2_QUBO_VARIABLE/v1"
QUBO_COUPLING_SCHEMA = "FRANKENSTEIN2_QUBO_COUPLING/v1"
QUBO_PROJECTION_SCHEMA = "FRANKENSTEIN2_QUBO_PROJECTION/v1"
QUBO_EVALUATION_SCHEMA = "FRANKENSTEIN2_QUBO_EVALUATION/v1"

_MAX_BIAS_ABS = 1_000_000_000
_MAX_VARIABLES = 4096
_MAX_COUPLINGS = 100_000


class QuboProjectionError(ValueError):
    """Fail-closed validation error for the QUBO projection boundary."""


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QuboProjectionError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise QuboProjectionError(f"{name} must not contain leading or trailing whitespace")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise QuboProjectionError(f"{name} must not contain control characters")
    return value


def _require_bias(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise QuboProjectionError(f"{name} must be an integer")
    if not -_MAX_BIAS_ABS <= value <= _MAX_BIAS_ABS:
        raise QuboProjectionError(
            f"{name} must be in [-{_MAX_BIAS_ABS}, {_MAX_BIAS_ABS}]"
        )
    return value


def _require_refs(name: str, value: Any, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise QuboProjectionError(f"{name} must be an immutable tuple")
    if not allow_empty and not value:
        raise QuboProjectionError(f"{name} must not be empty")
    refs = tuple(_require_text(f"{name} item", item) for item in value)
    if len(set(refs)) != len(refs):
        raise QuboProjectionError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise QuboProjectionError("value must be canonical-JSON encodable") from exc


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_sha256(name: str, value: Any) -> str:
    text = _require_text(name, value)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise QuboProjectionError(f"{name} must be lowercase sha256 hex")
    return text


@dataclass(frozen=True, slots=True, kw_only=True)
class QuboVariable:
    """One explicit binary decision variable bound to one selected world atom."""

    variable_id: str
    atom_id: str
    linear_bias: int

    schema: ClassVar[str] = QUBO_VARIABLE_SCHEMA
    classification: ClassVar[str] = "CALLER_SUPPLIED_BINARY_DECISION_VARIABLE_NOT_TRUTH"

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable_id", _require_text("variable_id", self.variable_id))
        object.__setattr__(self, "atom_id", _require_text("atom_id", self.atom_id))
        _require_bias("linear_bias", self.linear_bias)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "variable_id": self.variable_id,
            "atom_id": self.atom_id,
            "linear_bias": self.linear_bias,
            "domain": [0, 1],
            "truth_authority": "NONE",
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class QuboCoupling:
    """One caller-supplied quadratic interaction between distinct variables."""

    left_variable_id: str
    right_variable_id: str
    quadratic_bias: int

    schema: ClassVar[str] = QUBO_COUPLING_SCHEMA
    classification: ClassVar[str] = "CALLER_SUPPLIED_QUBO_COUPLING_NOT_CAUSAL_FACT"

    def __post_init__(self) -> None:
        left = _require_text("left_variable_id", self.left_variable_id)
        right = _require_text("right_variable_id", self.right_variable_id)
        if left == right:
            raise QuboProjectionError("QUBO coupling must reference two distinct variables")
        left, right = sorted((left, right))
        object.__setattr__(self, "left_variable_id", left)
        object.__setattr__(self, "right_variable_id", right)
        _require_bias("quadratic_bias", self.quadratic_bias)

    @property
    def pair(self) -> tuple[str, str]:
        return (self.left_variable_id, self.right_variable_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "left_variable_id": self.left_variable_id,
            "right_variable_id": self.right_variable_id,
            "quadratic_bias": self.quadratic_bias,
            "truth_authority": "NONE",
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class QuboProjection:
    """Immutable QUBO objective bound to one exact source ``WorldSlice`` object."""

    projection_id: str
    source_slice: WorldSlice
    variables: tuple[QuboVariable, ...]
    couplings: tuple[QuboCoupling, ...]
    offset_bias: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = QUBO_PROJECTION_SCHEMA
    classification: ClassVar[str] = "NONCANONICAL_SOLVER_NEUTRAL_QUBO_PROJECTION"

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_id", _require_text("projection_id", self.projection_id))
        if type(self.source_slice) is not WorldSlice:
            raise QuboProjectionError("source_slice must be an exact WorldSlice")
        if not isinstance(self.variables, tuple) or not self.variables:
            raise QuboProjectionError("variables must be a non-empty immutable tuple")
        if len(self.variables) > _MAX_VARIABLES:
            raise QuboProjectionError(f"variables exceed bounded maximum {_MAX_VARIABLES}")
        if not all(type(item) is QuboVariable for item in self.variables):
            raise QuboProjectionError("variables must contain only exact QuboVariable objects")
        if tuple(sorted(self.variables, key=lambda item: item.variable_id)) != self.variables:
            raise QuboProjectionError("variables must be in canonical variable_id order")
        variable_ids = tuple(item.variable_id for item in self.variables)
        atom_ids = tuple(item.atom_id for item in self.variables)
        if len(set(variable_ids)) != len(variable_ids):
            raise QuboProjectionError("duplicate variable_id")
        if len(set(atom_ids)) != len(atom_ids):
            raise QuboProjectionError("duplicate atom_id binding")
        selected_atoms = set(self.source_slice.selected_atom_ids)
        tainted_atoms = set(self.source_slice.tainted_atom_ids)
        for variable in self.variables:
            if variable.atom_id not in selected_atoms:
                raise QuboProjectionError("QUBO variable atom_id is not selected in source WorldSlice")
            if variable.atom_id in tainted_atoms:
                raise QuboProjectionError("QUBO variable must not bind a tainted source atom")
        if not isinstance(self.couplings, tuple):
            raise QuboProjectionError("couplings must be an immutable tuple")
        if len(self.couplings) > _MAX_COUPLINGS:
            raise QuboProjectionError(f"couplings exceed bounded maximum {_MAX_COUPLINGS}")
        if not all(type(item) is QuboCoupling for item in self.couplings):
            raise QuboProjectionError("couplings must contain only exact QuboCoupling objects")
        if tuple(sorted(self.couplings, key=lambda item: item.pair)) != self.couplings:
            raise QuboProjectionError("couplings must be in canonical pair order")
        pairs = tuple(item.pair for item in self.couplings)
        if len(set(pairs)) != len(pairs):
            raise QuboProjectionError("duplicate QUBO coupling pair")
        declared = set(variable_ids)
        for coupling in self.couplings:
            if coupling.left_variable_id not in declared or coupling.right_variable_id not in declared:
                raise QuboProjectionError("coupling references undeclared variable")
        _require_bias("offset_bias", self.offset_bias)
        object.__setattr__(
            self,
            "provenance_refs",
            _require_refs("provenance_refs", self.provenance_refs, allow_empty=False),
        )

    @property
    def source_slice_id(self) -> str:
        return self.source_slice.slice_id

    @property
    def source_need_id(self) -> str:
        return self.source_slice.need_id

    @property
    def source_cycle_id(self) -> str:
        return self.source_slice.cycle_id

    @property
    def source_generation(self) -> int:
        return self.source_slice.generation

    @property
    def source_vector_space_version(self) -> str:
        return self.source_slice.vector_space_version

    @property
    def source_slice_sha256(self) -> str:
        return self.source_slice.sha256()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "projection_id": self.projection_id,
            "source_slice_id": self.source_slice_id,
            "source_need_id": self.source_need_id,
            "source_cycle_id": self.source_cycle_id,
            "source_generation": self.source_generation,
            "source_vector_space_version": self.source_vector_space_version,
            "source_slice_sha256": self.source_slice_sha256,
            "variables": [item.as_dict() for item in self.variables],
            "couplings": [item.as_dict() for item in self.couplings],
            "offset_bias": self.offset_bias,
            "provenance_refs": list(self.provenance_refs),
            "solver_authority": "NONE",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())


@dataclass(frozen=True, slots=True, kw_only=True)
class QuboEvaluation:
    """Deterministic energy calculation for one complete explicit binary assignment."""

    projection_id: str
    projection_sha256: str
    assignment: tuple[tuple[str, int], ...]
    energy: int

    schema: ClassVar[str] = QUBO_EVALUATION_SCHEMA
    classification: ClassVar[str] = "QUBO_ASSIGNMENT_ENERGY_MEASUREMENT_NOT_WORLD_FACT"

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_id", _require_text("projection_id", self.projection_id))
        object.__setattr__(self, "projection_sha256", _require_sha256("projection_sha256", self.projection_sha256))
        if not isinstance(self.assignment, tuple) or not self.assignment:
            raise QuboProjectionError("assignment must be a non-empty immutable tuple")
        if not all(isinstance(item, tuple) and len(item) == 2 for item in self.assignment):
            raise QuboProjectionError("assignment entries must be immutable (variable_id, bit) tuples")
        canonical: list[tuple[str, int]] = []
        for variable_id, bit in self.assignment:
            variable_id = _require_text("assignment variable_id", variable_id)
            if isinstance(bit, bool) or not isinstance(bit, int) or bit not in (0, 1):
                raise QuboProjectionError("assignment values must be integer bits 0 or 1")
            canonical.append((variable_id, bit))
        if len({item[0] for item in canonical}) != len(canonical):
            raise QuboProjectionError("assignment must not contain duplicate variable_id")
        if tuple(sorted(canonical)) != self.assignment:
            raise QuboProjectionError("assignment must be in canonical variable_id order")
        if isinstance(self.energy, bool) or not isinstance(self.energy, int):
            raise QuboProjectionError("energy must be an integer")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "projection_id": self.projection_id,
            "projection_sha256": self.projection_sha256,
            "assignment": [[variable_id, bit] for variable_id, bit in self.assignment],
            "energy": self.energy,
            "optimality_claim": "NONE",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())


def compile_qubo_projection(
    *,
    source_slice: WorldSlice,
    projection_id: str,
    variables: tuple[QuboVariable, ...],
    couplings: tuple[QuboCoupling, ...],
    provenance_refs: tuple[str, ...],
    offset_bias: int = 0,
) -> QuboProjection:
    """Compile caller-supplied QUBO terms against one exact ``WorldSlice`` identity."""

    if type(source_slice) is not WorldSlice:
        raise QuboProjectionError("source_slice must be an exact WorldSlice")
    projection_id = _require_text("projection_id", projection_id)
    if not isinstance(variables, tuple) or not variables:
        raise QuboProjectionError("variables must be a non-empty immutable tuple")
    if not isinstance(couplings, tuple):
        raise QuboProjectionError("couplings must be an immutable tuple")
    if len(variables) > _MAX_VARIABLES:
        raise QuboProjectionError(f"variables exceed bounded maximum {_MAX_VARIABLES}")
    if len(couplings) > _MAX_COUPLINGS:
        raise QuboProjectionError(f"couplings exceed bounded maximum {_MAX_COUPLINGS}")
    if not all(type(item) is QuboVariable for item in variables):
        raise QuboProjectionError("variables must contain only exact QuboVariable objects")
    if not all(type(item) is QuboCoupling for item in couplings):
        raise QuboProjectionError("couplings must contain only exact QuboCoupling objects")
    provenance_refs = _require_refs("provenance_refs", provenance_refs, allow_empty=False)
    offset_bias = _require_bias("offset_bias", offset_bias)

    selected_atoms = set(source_slice.selected_atom_ids)
    tainted_atoms = set(source_slice.tainted_atom_ids)
    for variable in variables:
        if variable.atom_id not in selected_atoms:
            raise QuboProjectionError("QUBO variable atom_id is not selected in source WorldSlice")
        if variable.atom_id in tainted_atoms:
            raise QuboProjectionError("QUBO variable must not bind a tainted source atom")

    canonical_variables = tuple(sorted(variables, key=lambda item: item.variable_id))
    variable_ids = tuple(item.variable_id for item in canonical_variables)
    atom_ids = tuple(item.atom_id for item in canonical_variables)
    if len(set(variable_ids)) != len(variable_ids):
        raise QuboProjectionError("duplicate variable_id")
    if len(set(atom_ids)) != len(atom_ids):
        raise QuboProjectionError("duplicate atom_id binding")

    canonical_couplings = tuple(sorted(couplings, key=lambda item: item.pair))
    pairs = tuple(item.pair for item in canonical_couplings)
    if len(set(pairs)) != len(pairs):
        raise QuboProjectionError("duplicate QUBO coupling pair")
    declared = set(variable_ids)
    for coupling in canonical_couplings:
        if coupling.left_variable_id not in declared or coupling.right_variable_id not in declared:
            raise QuboProjectionError("coupling references undeclared variable")

    return QuboProjection(
        projection_id=projection_id,
        source_slice=source_slice,
        variables=canonical_variables,
        couplings=canonical_couplings,
        offset_bias=offset_bias,
        provenance_refs=provenance_refs,
    )


def evaluate_qubo_assignment(
    *,
    projection: QuboProjection,
    assignment: tuple[tuple[str, int], ...],
) -> QuboEvaluation:
    """Evaluate ``offset + linear + quadratic`` for one complete binary assignment."""

    if type(projection) is not QuboProjection:
        raise QuboProjectionError("projection must be an exact QuboProjection")
    if not isinstance(assignment, tuple):
        raise QuboProjectionError("assignment must be an immutable tuple")
    parsed: list[tuple[str, int]] = []
    for item in assignment:
        if not isinstance(item, tuple) or len(item) != 2:
            raise QuboProjectionError("assignment entries must be immutable (variable_id, bit) tuples")
        variable_id = _require_text("assignment variable_id", item[0])
        bit = item[1]
        if isinstance(bit, bool) or not isinstance(bit, int) or bit not in (0, 1):
            raise QuboProjectionError("assignment values must be integer bits 0 or 1")
        parsed.append((variable_id, bit))
    if len({variable_id for variable_id, _ in parsed}) != len(parsed):
        raise QuboProjectionError("assignment must not contain duplicate variable_id")

    expected = {variable.variable_id for variable in projection.variables}
    observed = {variable_id for variable_id, _ in parsed}
    if observed != expected:
        missing = sorted(expected - observed)
        unknown = sorted(observed - expected)
        raise QuboProjectionError(
            f"assignment must cover exactly declared variables; missing={missing}, unknown={unknown}"
        )

    canonical_assignment = tuple(sorted(parsed))
    values = dict(canonical_assignment)
    energy = projection.offset_bias
    for variable in projection.variables:
        energy += variable.linear_bias * values[variable.variable_id]
    for coupling in projection.couplings:
        energy += (
            coupling.quadratic_bias
            * values[coupling.left_variable_id]
            * values[coupling.right_variable_id]
        )

    return QuboEvaluation(
        projection_id=projection.projection_id,
        projection_sha256=projection.sha256(),
        assignment=canonical_assignment,
        energy=energy,
    )
