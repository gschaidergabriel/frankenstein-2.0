"""Deterministic source-bound Cognitive Micro-Lab for Frankenstein 2.0.

F2-WP-404 generation 1 composes already-admitted Stage-4 candidate projections into one
small counterfactual measurement surface.  It compares one explicit QUBO assignment with
one explicit single-bit perturbation while independently revalidating both the QUBO and
rudimentary-physics projections against the exact caller-supplied WorldSlice and physics
source atoms.

The lab is noncanonical.  It does not infer a world fact, choose a winner/action, invoke a
solver/model/provider/tool, mutate UnifiedDB/world state, collapse alternatives, authorize
an effect/completion, or mint runtime/GWT/J-Space/training credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, ClassVar

from .physics_projection import (
    PhysicsProjection,
    PhysicsProjectionError,
    validate_physics_projection_binding,
)
from .qubo_projection import (
    QuboAssignmentScore,
    QuboProjection,
    QuboProjectionError,
    score_assignment,
)
from .sparse_world_basis import WorldAtom, WorldSlice


COGNITIVE_MICRO_LAB_SCHEMA = "FRANKENSTEIN2_COGNITIVE_MICRO_LAB_RESULT/v1"
QUBO_BIT_PERTURBATION_SCHEMA = "FRANKENSTEIN2_QUBO_BIT_PERTURBATION/v1"


class CognitiveMicroLabError(ValueError):
    """Fail-closed validation error for the WP404 micro-lab."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CognitiveMicroLabError(f"{name} must be a non-empty trimmed string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise CognitiveMicroLabError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise CognitiveMicroLabError(f"{name} must be lowercase 64-hex SHA-256")
    return value


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
        raise CognitiveMicroLabError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _assignment(value: Any) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, tuple) or not value:
        raise CognitiveMicroLabError("baseline_assignment must be a non-empty immutable tuple")
    normalized: list[tuple[str, int]] = []
    ids: list[str] = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise CognitiveMicroLabError(
                "baseline_assignment items must be (variable_id, bit) tuples"
            )
        variable_id = _text("baseline_assignment variable_id", item[0])
        bit = item[1]
        if type(bit) is not int or bit not in (0, 1):
            raise CognitiveMicroLabError("baseline_assignment bits must be integer 0 or 1")
        ids.append(variable_id)
        normalized.append((variable_id, bit))
    if len(set(ids)) != len(ids):
        raise CognitiveMicroLabError("baseline_assignment contains duplicate variable_id")
    if tuple(ids) != tuple(sorted(ids)):
        raise CognitiveMicroLabError("baseline_assignment must be canonicalized by variable_id")
    return tuple(normalized)


@dataclass(frozen=True, slots=True, kw_only=True)
class QuboBitPerturbation:
    """One explicit counterfactual bit flip; never a recommendation or action."""

    variable_id: str
    expected_from_bit: int
    to_bit: int
    rationale_ref: str

    schema: ClassVar[str] = QUBO_BIT_PERTURBATION_SCHEMA
    classification: ClassVar[str] = "CALLER_SUPPLIED_COUNTERFACTUAL_NOT_ACTION"

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable_id", _text("variable_id", self.variable_id))
        object.__setattr__(self, "rationale_ref", _text("rationale_ref", self.rationale_ref))
        if type(self.expected_from_bit) is not int or self.expected_from_bit not in (0, 1):
            raise CognitiveMicroLabError("expected_from_bit must be integer 0 or 1")
        if type(self.to_bit) is not int or self.to_bit not in (0, 1):
            raise CognitiveMicroLabError("to_bit must be integer 0 or 1")
        if self.expected_from_bit == self.to_bit:
            raise CognitiveMicroLabError("perturbation must change the selected bit")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "variable_id": self.variable_id,
            "expected_from_bit": self.expected_from_bit,
            "to_bit": self.to_bit,
            "rationale_ref": self.rationale_ref,
            "effect_authority": "NONE",
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class CognitiveMicroLabResult:
    lab_id: str
    slice_id: str
    slice_sha256: str
    generation: int
    qubo_projection_id: str
    qubo_projection_sha256: str
    physics_projection_id: str
    physics_projection_sha256: str
    baseline_score: QuboAssignmentScore
    perturbed_score: QuboAssignmentScore
    perturbation: QuboBitPerturbation
    objective_delta: int
    physics_endpoint_position: tuple[int, ...]
    physics_endpoint_velocity: tuple[int, ...]

    schema: ClassVar[str] = COGNITIVE_MICRO_LAB_SCHEMA
    classification: ClassVar[str] = "NONCANONICAL_COUNTERFACTUAL_MEASUREMENT_ONLY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "lab_id", _text("lab_id", self.lab_id))
        object.__setattr__(self, "slice_id", _text("slice_id", self.slice_id))
        object.__setattr__(self, "slice_sha256", _sha256("slice_sha256", self.slice_sha256))
        if type(self.generation) is not int or self.generation < 0:
            raise CognitiveMicroLabError("generation must be a non-negative integer")
        object.__setattr__(
            self, "qubo_projection_id", _text("qubo_projection_id", self.qubo_projection_id)
        )
        object.__setattr__(
            self,
            "qubo_projection_sha256",
            _sha256("qubo_projection_sha256", self.qubo_projection_sha256),
        )
        object.__setattr__(
            self,
            "physics_projection_id",
            _text("physics_projection_id", self.physics_projection_id),
        )
        object.__setattr__(
            self,
            "physics_projection_sha256",
            _sha256("physics_projection_sha256", self.physics_projection_sha256),
        )
        if type(self.baseline_score) is not QuboAssignmentScore:
            raise CognitiveMicroLabError("baseline_score must be exact QuboAssignmentScore")
        if type(self.perturbed_score) is not QuboAssignmentScore:
            raise CognitiveMicroLabError("perturbed_score must be exact QuboAssignmentScore")
        if type(self.perturbation) is not QuboBitPerturbation:
            raise CognitiveMicroLabError("perturbation must be exact QuboBitPerturbation")
        if type(self.objective_delta) is not int:
            raise CognitiveMicroLabError("objective_delta must be an integer")
        for name, vector in (
            ("physics_endpoint_position", self.physics_endpoint_position),
            ("physics_endpoint_velocity", self.physics_endpoint_velocity),
        ):
            if not isinstance(vector, tuple) or not vector:
                raise CognitiveMicroLabError(f"{name} must be a non-empty immutable tuple")
            if not all(type(item) is int for item in vector):
                raise CognitiveMicroLabError(f"{name} components must be integers")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "lab_id": self.lab_id,
            "slice_id": self.slice_id,
            "slice_sha256": self.slice_sha256,
            "generation": self.generation,
            "qubo_projection_id": self.qubo_projection_id,
            "qubo_projection_sha256": self.qubo_projection_sha256,
            "physics_projection_id": self.physics_projection_id,
            "physics_projection_sha256": self.physics_projection_sha256,
            "baseline_score": self.baseline_score.as_dict(),
            "perturbed_score": self.perturbed_score.as_dict(),
            "perturbation": self.perturbation.as_dict(),
            "objective_delta": self.objective_delta,
            "physics_endpoint_position": list(self.physics_endpoint_position),
            "physics_endpoint_velocity": list(self.physics_endpoint_velocity),
            "alternatives_preserved": ["BASELINE", "PERTURBED"],
            "resolution": "UNRESOLVED_BY_DESIGN",
            "selected_winner": None,
            "selected_action": None,
            "epistemic_scope": "CANDIDATE_MEASUREMENT_ONLY",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "world_mutation_performed": False,
            "solver_invoked": False,
            "model_or_provider_invoked": False,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def run_cognitive_micro_lab(
    *,
    world_slice: WorldSlice,
    qubo_projection: QuboProjection,
    expected_qubo_projection_sha256: str,
    baseline_assignment: tuple[tuple[str, int], ...],
    perturbation: QuboBitPerturbation,
    physics_projection: PhysicsProjection,
    expected_physics_projection_sha256: str,
    position_atom: WorldAtom,
    velocity_atom: WorldAtom,
    acceleration_atom: WorldAtom,
) -> CognitiveMicroLabResult:
    """Measure one bounded counterfactual after exact-source revalidation.

    The returned objective delta is merely a deterministic local measurement.  Lower or
    higher objective value is not interpreted as better, safer, truer, or actionable.
    """
    if type(world_slice) is not WorldSlice:
        raise CognitiveMicroLabError("world_slice must be exact WorldSlice")
    if type(qubo_projection) is not QuboProjection:
        raise CognitiveMicroLabError("qubo_projection must be exact QuboProjection")
    if type(physics_projection) is not PhysicsProjection:
        raise CognitiveMicroLabError("physics_projection must be exact PhysicsProjection")
    for name, atom in (
        ("position_atom", position_atom),
        ("velocity_atom", velocity_atom),
        ("acceleration_atom", acceleration_atom),
    ):
        if type(atom) is not WorldAtom:
            raise CognitiveMicroLabError(f"{name} must be exact WorldAtom")
    if type(perturbation) is not QuboBitPerturbation:
        raise CognitiveMicroLabError("perturbation must be exact QuboBitPerturbation")

    expected_qubo_sha = _sha256(
        "expected_qubo_projection_sha256", expected_qubo_projection_sha256
    )
    expected_physics_sha = _sha256(
        "expected_physics_projection_sha256", expected_physics_projection_sha256
    )
    baseline = _assignment(baseline_assignment)

    try:
        baseline_score = score_assignment(
            projection=qubo_projection,
            world_slice=world_slice,
            assignment=baseline,
            expected_projection_sha256=expected_qubo_sha,
        )
    except QuboProjectionError as exc:
        raise CognitiveMicroLabError(f"QUBO source binding rejected: {exc}") from exc

    try:
        validated_physics = validate_physics_projection_binding(
            projection=physics_projection,
            world_slice=world_slice,
            position_atom=position_atom,
            velocity_atom=velocity_atom,
            acceleration_atom=acceleration_atom,
            expected_projection_sha256=expected_physics_sha,
        )
    except PhysicsProjectionError as exc:
        raise CognitiveMicroLabError(f"physics source binding rejected: {exc}") from exc

    bits = dict(baseline)
    if perturbation.variable_id not in bits:
        raise CognitiveMicroLabError("perturbation variable_id is absent from baseline_assignment")
    if bits[perturbation.variable_id] != perturbation.expected_from_bit:
        raise CognitiveMicroLabError("perturbation expected_from_bit does not match baseline_assignment")
    bits[perturbation.variable_id] = perturbation.to_bit
    perturbed_assignment = tuple(sorted(bits.items()))

    try:
        perturbed_score = score_assignment(
            projection=qubo_projection,
            world_slice=world_slice,
            assignment=perturbed_assignment,
            expected_projection_sha256=expected_qubo_sha,
        )
    except QuboProjectionError as exc:
        raise CognitiveMicroLabError(f"perturbed QUBO binding rejected: {exc}") from exc

    if validated_physics.slice_id != world_slice.slice_id:
        raise CognitiveMicroLabError("physics projection slice_id differs from exact WorldSlice")
    if validated_physics.slice_digest != world_slice.sha256():
        raise CognitiveMicroLabError("physics projection slice digest differs from exact WorldSlice")
    if validated_physics.generation != world_slice.generation:
        raise CognitiveMicroLabError("physics projection generation differs from exact WorldSlice")

    binding = {
        "schema": COGNITIVE_MICRO_LAB_SCHEMA,
        "slice_sha256": world_slice.sha256(),
        "qubo_projection_sha256": expected_qubo_sha,
        "physics_projection_sha256": expected_physics_sha,
        "baseline_assignment": [[variable_id, bit] for variable_id, bit in baseline],
        "perturbation": perturbation.as_dict(),
    }
    lab_id = f"micro-lab:{_digest(binding)}"

    return CognitiveMicroLabResult(
        lab_id=lab_id,
        slice_id=world_slice.slice_id,
        slice_sha256=world_slice.sha256(),
        generation=world_slice.generation,
        qubo_projection_id=qubo_projection.projection_id,
        qubo_projection_sha256=expected_qubo_sha,
        physics_projection_id=validated_physics.projection_id,
        physics_projection_sha256=expected_physics_sha,
        baseline_score=baseline_score,
        perturbed_score=perturbed_score,
        perturbation=perturbation,
        objective_delta=perturbed_score.objective_value - baseline_score.objective_value,
        physics_endpoint_position=validated_physics.position_trajectory[-1],
        physics_endpoint_velocity=validated_physics.velocity_trajectory[-1],
    )
