#!/usr/bin/env python3
"""CANDIDATE_FALSIFIER: WP403 exact-source validator must reject self-attesting subclasses.

This test is deliberately expected to fail against the current generation-2 source if
`validate_physics_projection_binding` accepts a PhysicsProjection subclass whose overridden
`sha256()` and `canonical_json()` methods can self-attest a forged instance.
"""
from __future__ import annotations

import unittest

from frankenstein2.physics_projection import (
    PhysicsProjection,
    PhysicsProjectionError,
    project_rudimentary_kinematics,
    validate_physics_projection_binding,
)
from frankenstein2.sparse_world_basis import (
    EpistemicOrigin,
    KnowledgeState,
    WorldAtom,
    WorldSlice,
)


def atom(atom_id: str, vector: tuple[int, ...]) -> WorldAtom:
    return WorldAtom(
        atom_id=atom_id,
        generation=4,
        vector_space_version="vs:1",
        vector=vector,
        epistemic_origin=EpistemicOrigin.OBSERVED,
        knowledge_state=KnowledgeState.KNOWN,
        provenance_refs=(f"source:{atom_id}",),
        evidence_refs=(f"evidence:{atom_id}",),
        confidence_micros=900_000,
    )


def world_slice() -> WorldSlice:
    return WorldSlice(
        slice_id="slice:physics",
        need_id="need:physics",
        cycle_id="cycle:1",
        generation=4,
        vector_space_version="vs:1",
        selected_atom_ids=("acc", "pos", "vel"),
        selected_operator_ids=(),
        unresolved_target_atom_ids=(),
        tainted_atom_ids=(),
        depth_reached=1,
        stopped_reason="TARGETS_REACHED",
        evidence_refs=("evidence:slice",),
        provenance_digest="0" * 64,
    )


class SelfAttestingPhysicsProjection(PhysicsProjection):
    """Adversarial subtype that lies through the two polymorphic attestation methods."""

    attested_json = ""
    attested_sha256 = ""

    def canonical_json(self) -> str:
        return type(self).attested_json

    def sha256(self) -> str:
        return type(self).attested_sha256


class PhysicsProjectionSubclassForgeryFalsifier(unittest.TestCase):
    def test_self_attesting_projection_subclass_must_fail_closed(self) -> None:
        s = world_slice()
        p = atom("pos", (0, 0))
        v = atom("vel", (1, 2))
        a = atom("acc", (1, -1))
        valid = project_rudimentary_kinematics(
            world_slice=s,
            position_atom=p,
            velocity_atom=v,
            acceleration_atom=a,
            dt_ticks=2,
            steps=2,
        )

        SelfAttestingPhysicsProjection.attested_json = valid.canonical_json()
        SelfAttestingPhysicsProjection.attested_sha256 = valid.sha256()
        forged = SelfAttestingPhysicsProjection(
            projection_id=valid.projection_id,
            slice_id=valid.slice_id,
            slice_digest=valid.slice_digest,
            need_id=valid.need_id,
            cycle_id=valid.cycle_id,
            generation=valid.generation,
            vector_space_version=valid.vector_space_version,
            position_atom_id=valid.position_atom_id,
            velocity_atom_id=valid.velocity_atom_id,
            acceleration_atom_id="atom:not-selected",
            source_atom_digests=valid.source_atom_digests,
            dt_ticks=valid.dt_ticks,
            steps=valid.steps,
            position_trajectory=((999, 999),),
            velocity_trajectory=((999, 999),),
        )

        # Intended invariant: a subclass is not the exact projection object whose bytes
        # were independently replayed. Current G2 source uses isinstance() and polymorphic
        # methods, so this assertion should expose the bypass until the boundary is hardened.
        with self.assertRaises(PhysicsProjectionError):
            validate_physics_projection_binding(
                projection=forged,
                world_slice=s,
                position_atom=p,
                velocity_atom=v,
                acceleration_atom=a,
                expected_projection_sha256=valid.sha256(),
            )


if __name__ == "__main__":
    unittest.main()
