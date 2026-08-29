#!/usr/bin/env python3
"""Review-only executable falsifier for F2-WP-403 generation 2.

This does not mutate WP403 implementation authority.  It demonstrates that the current
public builder/revalidation boundary accepts a WorldSlice subclass whose overridden
sha256() self-attests a digest different from the exact base WorldSlice canonical digest.
"""
from __future__ import annotations

import unittest

from frankenstein2.physics_projection import (
    project_rudimentary_kinematics,
    validate_physics_projection_binding,
)
from frankenstein2.sparse_world_basis import (
    EpistemicOrigin,
    KnowledgeState,
    WorldAtom,
    WorldSlice,
)


FORGED_SLICE_DIGEST = "f" * 64


class DigestForgingWorldSlice(WorldSlice):
    """Adversarial subtype: identical visible fields, attacker-controlled digest method."""

    def sha256(self) -> str:
        return FORGED_SLICE_DIGEST


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


def forged_slice() -> DigestForgingWorldSlice:
    return DigestForgingWorldSlice(
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


class WP403WorldSliceSubclassFalsifier(unittest.TestCase):
    def test_subclass_can_self_attest_slice_digest_and_pass_exact_source_revalidation(self):
        s = forged_slice()
        p = atom("pos", (0, 0))
        v = atom("vel", (1, 2))
        a = atom("acc", (1, -1))

        # Exact base-class canonical digest bypasses the adversarial override.
        exact_base_digest = WorldSlice.sha256(s)
        self.assertNotEqual(exact_base_digest, FORGED_SLICE_DIGEST)
        self.assertEqual(s.sha256(), FORGED_SLICE_DIGEST)

        projection = project_rudimentary_kinematics(
            world_slice=s,
            position_atom=p,
            velocity_atom=v,
            acceleration_atom=a,
            dt_ticks=2,
            steps=2,
        )

        # Current WP403 builder records the attacker-selected polymorphic digest.
        self.assertEqual(projection.slice_digest, FORGED_SLICE_DIGEST)
        self.assertNotEqual(projection.slice_digest, exact_base_digest)

        # Current revalidation rebuilds through the same subtype and therefore accepts it.
        admitted = validate_physics_projection_binding(
            projection=projection,
            world_slice=s,
            position_atom=p,
            velocity_atom=v,
            acceleration_atom=a,
            expected_projection_sha256=projection.sha256(),
        )
        self.assertIs(admitted, projection)


if __name__ == "__main__":
    unittest.main()
