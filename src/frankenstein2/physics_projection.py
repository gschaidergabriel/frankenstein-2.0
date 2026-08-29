"""Deterministic rudimentary physics projection for Frankenstein 2.0.

F2-WP-403 is deliberately narrow: it projects caller-admitted, exact WorldSlice
state with a bounded integer semi-implicit Euler rule.  The result is a
noncanonical candidate projection.  It does not infer a physical law, observe the
world, select an action, authorize an effect, or mint completion/truth authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, ClassVar

from frankenstein2.sparse_world_basis import (
    KnowledgeState,
    WorldAtom,
    WorldSlice,
)


PHYSICS_PROJECTION_SCHEMA = "FRANKENSTEIN2_RUDIMENTARY_PHYSICS_PROJECTION/v1"
INTEGRATION_RULE = "BOUNDED_INTEGER_SEMI_IMPLICIT_EULER/v1"
MAX_DIMENSIONS = 3
MAX_DT_TICKS = 10_000
MAX_STEPS = 128
MAX_ABS_STATE = 1_000_000_000_000_000


class PhysicsProjectionError(ValueError):
    """Fail-closed validation error for the WP403 projection adapter."""


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
        raise PhysicsProjectionError("value must be canonical-JSON encodable") from exc


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_positive_bounded_int(name: str, value: Any, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise PhysicsProjectionError(f"{name} must be an integer in [1, {maximum}]")
    return value


def _bounded_state_value(value: int, *, role: str) -> int:
    if abs(value) > MAX_ABS_STATE:
        raise PhysicsProjectionError(f"{role} arithmetic exceeds bounded state range")
    return value


def _validate_source_atom(
    *,
    atom: WorldAtom,
    role: str,
    world_slice: WorldSlice,
) -> None:
    if not isinstance(atom, WorldAtom):
        raise PhysicsProjectionError(f"{role} must be a WorldAtom")
    if atom.atom_id not in world_slice.selected_atom_ids:
        raise PhysicsProjectionError(f"{role} atom must be selected by the exact WorldSlice")
    if atom.atom_id in world_slice.tainted_atom_ids:
        raise PhysicsProjectionError(f"{role} atom is tainted by NOT_COMPUTED dependency")
    if atom.knowledge_state is not KnowledgeState.KNOWN:
        raise PhysicsProjectionError(f"{role} atom must have KNOWN knowledge_state")
    if atom.generation != world_slice.generation:
        raise PhysicsProjectionError(f"{role} generation mismatch with WorldSlice")
    if atom.vector_space_version != world_slice.vector_space_version:
        raise PhysicsProjectionError(f"{role} vector_space_version mismatch with WorldSlice")


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicsProjection:
    projection_id: str
    slice_id: str
    slice_digest: str
    need_id: str
    cycle_id: str
    generation: int
    vector_space_version: str
    position_atom_id: str
    velocity_atom_id: str
    acceleration_atom_id: str
    source_atom_digests: tuple[str, ...]
    dt_ticks: int
    steps: int
    position_trajectory: tuple[tuple[int, ...], ...]
    velocity_trajectory: tuple[tuple[int, ...], ...]

    schema: ClassVar[str] = PHYSICS_PROJECTION_SCHEMA
    classification: ClassVar[str] = "NONCANONICAL_RUDIMENTARY_PHYSICS_PROJECTION"
    integration_rule: ClassVar[str] = INTEGRATION_RULE

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "projection_id": self.projection_id,
            "slice_id": self.slice_id,
            "slice_digest": self.slice_digest,
            "need_id": self.need_id,
            "cycle_id": self.cycle_id,
            "generation": self.generation,
            "vector_space_version": self.vector_space_version,
            "position_atom_id": self.position_atom_id,
            "velocity_atom_id": self.velocity_atom_id,
            "acceleration_atom_id": self.acceleration_atom_id,
            "source_atom_digests": list(self.source_atom_digests),
            "dt_ticks": self.dt_ticks,
            "steps": self.steps,
            "integration_rule": self.integration_rule,
            "position_trajectory": [list(vector) for vector in self.position_trajectory],
            "velocity_trajectory": [list(vector) for vector in self.velocity_trajectory],
            "epistemic_scope": "CANDIDATE_PROJECTION_ONLY",
            "truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _sha256_text(self.canonical_json())


def project_rudimentary_kinematics(
    *,
    world_slice: WorldSlice,
    position_atom: WorldAtom,
    velocity_atom: WorldAtom,
    acceleration_atom: WorldAtom,
    dt_ticks: int,
    steps: int,
) -> PhysicsProjection:
    """Project bounded discrete kinematics from exact selected WorldAtom inputs.

    The numerical rule is intentionally explicit and primitive:

        velocity[t+1] = velocity[t] + acceleration * dt_ticks
        position[t+1] = position[t] + velocity[t+1] * dt_ticks

    All quantities are opaque integer units.  No unit conversion, learned law,
    parameter inference, external observation, or action semantics are implied.
    """

    if not isinstance(world_slice, WorldSlice):
        raise PhysicsProjectionError("world_slice must be a WorldSlice")

    _validate_source_atom(atom=position_atom, role="position", world_slice=world_slice)
    _validate_source_atom(atom=velocity_atom, role="velocity", world_slice=world_slice)
    _validate_source_atom(atom=acceleration_atom, role="acceleration", world_slice=world_slice)

    role_ids = (
        position_atom.atom_id,
        velocity_atom.atom_id,
        acceleration_atom.atom_id,
    )
    if len(set(role_ids)) != len(role_ids):
        raise PhysicsProjectionError("position, velocity and acceleration atoms must be distinct")

    dimensions = len(position_atom.vector)
    if not 1 <= dimensions <= MAX_DIMENSIONS:
        raise PhysicsProjectionError(
            f"position vector dimensions must be in [1, {MAX_DIMENSIONS}]"
        )
    if len(velocity_atom.vector) != dimensions or len(acceleration_atom.vector) != dimensions:
        raise PhysicsProjectionError("position, velocity and acceleration dimensions must match")

    dt_ticks = _require_positive_bounded_int("dt_ticks", dt_ticks, maximum=MAX_DT_TICKS)
    steps = _require_positive_bounded_int("steps", steps, maximum=MAX_STEPS)

    position = tuple(position_atom.vector)
    velocity = tuple(velocity_atom.vector)
    acceleration = tuple(acceleration_atom.vector)
    position_trajectory: list[tuple[int, ...]] = [position]
    velocity_trajectory: list[tuple[int, ...]] = [velocity]

    for _ in range(steps):
        next_velocity = tuple(
            _bounded_state_value(
                velocity[index] + acceleration[index] * dt_ticks,
                role="velocity",
            )
            for index in range(dimensions)
        )
        next_position = tuple(
            _bounded_state_value(
                position[index] + next_velocity[index] * dt_ticks,
                role="position",
            )
            for index in range(dimensions)
        )
        velocity = next_velocity
        position = next_position
        velocity_trajectory.append(velocity)
        position_trajectory.append(position)

    slice_digest = world_slice.sha256()
    source_atom_digests = (
        position_atom.sha256(),
        velocity_atom.sha256(),
        acceleration_atom.sha256(),
    )
    binding = {
        "schema": PHYSICS_PROJECTION_SCHEMA,
        "slice_id": world_slice.slice_id,
        "slice_digest": slice_digest,
        "need_id": world_slice.need_id,
        "cycle_id": world_slice.cycle_id,
        "generation": world_slice.generation,
        "vector_space_version": world_slice.vector_space_version,
        "position_atom_id": position_atom.atom_id,
        "velocity_atom_id": velocity_atom.atom_id,
        "acceleration_atom_id": acceleration_atom.atom_id,
        "source_atom_digests": list(source_atom_digests),
        "dt_ticks": dt_ticks,
        "steps": steps,
        "integration_rule": INTEGRATION_RULE,
    }
    projection_id = f"physics:{_sha256_text(_canonical_json(binding))}"

    return PhysicsProjection(
        projection_id=projection_id,
        slice_id=world_slice.slice_id,
        slice_digest=slice_digest,
        need_id=world_slice.need_id,
        cycle_id=world_slice.cycle_id,
        generation=world_slice.generation,
        vector_space_version=world_slice.vector_space_version,
        position_atom_id=position_atom.atom_id,
        velocity_atom_id=velocity_atom.atom_id,
        acceleration_atom_id=acceleration_atom.atom_id,
        source_atom_digests=source_atom_digests,
        dt_ticks=dt_ticks,
        steps=steps,
        position_trajectory=tuple(position_trajectory),
        velocity_trajectory=tuple(velocity_trajectory),
    )

def _require_sha256_hex(name: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise PhysicsProjectionError(f"{name} must be lowercase sha256 hex")
    return value


def validate_physics_projection_binding(
    *,
    projection: PhysicsProjection,
    world_slice: WorldSlice,
    position_atom: WorldAtom,
    velocity_atom: WorldAtom,
    acceleration_atom: WorldAtom,
    expected_projection_sha256: str,
) -> PhysicsProjection:
    """Fail closed unless a projection exactly replays from its claimed sources.

    A projection self-hash is only an integrity digest over caller-visible data;
    it is not evidence that the object crossed the validated builder.  This
    boundary therefore requires the exact WorldSlice and source WorldAtoms and
    independently rebuilds the candidate before admitting equality.
    """
    if not isinstance(projection, PhysicsProjection):
        raise PhysicsProjectionError("projection must be a PhysicsProjection")
    expected_projection_sha256 = _require_sha256_hex(
        "expected_projection_sha256", expected_projection_sha256
    )
    if projection.sha256() != expected_projection_sha256:
        raise PhysicsProjectionError("projection sha256 does not match expected digest")

    rebuilt = project_rudimentary_kinematics(
        world_slice=world_slice,
        position_atom=position_atom,
        velocity_atom=velocity_atom,
        acceleration_atom=acceleration_atom,
        dt_ticks=projection.dt_ticks,
        steps=projection.steps,
    )
    if projection.canonical_json() != rebuilt.canonical_json():
        raise PhysicsProjectionError(
            "projection does not match independently rebuilt exact WorldSlice/source binding"
        )
    return projection
