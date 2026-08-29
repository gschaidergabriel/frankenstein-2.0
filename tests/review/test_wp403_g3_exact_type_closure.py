#!/usr/bin/env python3
"""Independent executable closure review for F2-WP-403 generation 3.

The generation-2 boundary was falsified by polymorphic WorldSlice and
PhysicsProjection self-attestation. Generation 3 claims exact concrete type boundaries.
This review changes no WP403 implementation authority; it checks that the known attack
classes now fail closed before caller-provided attestation methods can be used.
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


FORGED_DIGEST = "f" * 64


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


class DigestForgingWorldSlice(WorldSlice):
    def sha256(self) -> str:
        return FORGED_DIGEST


class DigestForgingWorldAtom(WorldAtom):
    def sha256(self) -> str:
        return FORGED_DIGEST


class SelfAttestingPhysicsProjection(PhysicsProjection):
    attested_json = ""
    attested_sha256 = ""

    def canonical_json(self) -> str:
        return type(self).attested_json

    def sha256(self) -> str:
        return type(self).attested_sha256


class WP403G3ExactTypeClosure(unittest.TestCase):
    def test_worldslice_subclass_is_rejected_before_polymorphic_digest(self) -> None:
        base = world_slice()
        forged = DigestForgingWorldSlice(**{
            name: getattr(base, name)
            for name in (
                "slice_id", "need_id", "cycle_id", "generation", "vector_space_version",
                "selected_atom_ids", "selected_operator_ids", "unresolved_target_atom_ids",
                "tainted_atom_ids", "depth_reached", "stopped_reason", "evidence_refs",
                "provenance_digest",
            )
        })
        self.assertEqual(forged.sha256(), FORGED_DIGEST)
        with self.assertRaisesRegex(PhysicsProjectionError, "exact WorldSlice"):
            project_rudimentary_kinematics(
                world_slice=forged,
                position_atom=atom("pos", (0, 0)),
                velocity_atom=atom("vel", (1, 2)),
                acceleration_atom=atom("acc", (1, -1)),
                dt_ticks=2,
                steps=2,
            )

    def test_worldatom_subclass_is_rejected_before_polymorphic_digest(self) -> None:
        base = atom("pos", (0, 0))
        forged = DigestForgingWorldAtom(**{
            name: getattr(base, name)
            for name in (
                "atom_id", "generation", "vector_space_version", "vector",
                "epistemic_origin", "knowledge_state", "provenance_refs", "evidence_refs",
                "confidence_micros",
            )
        })
        self.assertEqual(forged.sha256(), FORGED_DIGEST)
        with self.assertRaisesRegex(PhysicsProjectionError, "position must be exact WorldAtom"):
            project_rudimentary_kinematics(
                world_slice=world_slice(),
                position_atom=forged,
                velocity_atom=atom("vel", (1, 2)),
                acceleration_atom=atom("acc", (1, -1)),
                dt_ticks=2,
                steps=2,
            )

    def test_projection_subclass_cannot_self_attest_revalidation(self) -> None:
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
        with self.assertRaisesRegex(PhysicsProjectionError, "exact PhysicsProjection"):
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
