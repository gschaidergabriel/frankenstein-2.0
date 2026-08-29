#!/usr/bin/env python3
"""Deterministic falsification suite for F2-WP-403 rudimentary physics projection."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from frankenstein2.physics_projection import (
    INTEGRATION_RULE,
    MAX_STEPS,
    PhysicsProjectionError,
    project_rudimentary_kinematics,
)
from frankenstein2.sparse_world_basis import (
    EpistemicOrigin,
    KnowledgeState,
    WorldAtom,
    WorldSlice,
)


def atom(
    atom_id: str,
    vector: tuple[int, ...],
    *,
    state: KnowledgeState = KnowledgeState.KNOWN,
    vector_space: str = "vs:1",
    generation: int = 4,
) -> WorldAtom:
    return WorldAtom(
        atom_id=atom_id,
        generation=generation,
        vector_space_version=vector_space,
        vector=vector,
        epistemic_origin=EpistemicOrigin.OBSERVED,
        knowledge_state=state,
        provenance_refs=(f"source:{atom_id}",),
        evidence_refs=()
        if state in (KnowledgeState.UNKNOWN, KnowledgeState.NOT_COMPUTED)
        else (f"evidence:{atom_id}",),
        confidence_micros=None
        if state in (KnowledgeState.UNKNOWN, KnowledgeState.NOT_COMPUTED)
        else 900_000,
    )


def world_slice(
    *,
    selected: tuple[str, ...] = ("acc", "pos", "vel"),
    tainted: tuple[str, ...] = (),
    generation: int = 4,
    vector_space: str = "vs:1",
    provenance_digest: str = "0" * 64,
) -> WorldSlice:
    return WorldSlice(
        slice_id="slice:physics",
        need_id="need:physics",
        cycle_id="cycle:1",
        generation=generation,
        vector_space_version=vector_space,
        selected_atom_ids=selected,
        selected_operator_ids=(),
        unresolved_target_atom_ids=(),
        tainted_atom_ids=tainted,
        depth_reached=1,
        stopped_reason="TARGETS_REACHED",
        evidence_refs=("evidence:slice",),
        provenance_digest=provenance_digest,
    )


def project(
    *,
    slice_obj: WorldSlice | None = None,
    position: WorldAtom | None = None,
    velocity: WorldAtom | None = None,
    acceleration: WorldAtom | None = None,
    dt_ticks: int = 2,
    steps: int = 2,
):
    return project_rudimentary_kinematics(
        world_slice=slice_obj or world_slice(),
        position_atom=position or atom("pos", (0, 0)),
        velocity_atom=velocity or atom("vel", (1, 2)),
        acceleration_atom=acceleration or atom("acc", (1, -1)),
        dt_ticks=dt_ticks,
        steps=steps,
    )


class RudimentaryPhysicsProjectionTests(unittest.TestCase):
    def test_bounded_integer_kinematics_is_exact_and_candidate_only(self):
        result = project()
        self.assertEqual(result.position_trajectory, ((0, 0), (6, 0), (16, -4)))
        self.assertEqual(result.velocity_trajectory, ((1, 2), (3, 0), (5, -2)))
        self.assertEqual(result.integration_rule, INTEGRATION_RULE)
        self.assertEqual(result.as_dict()["epistemic_scope"], "CANDIDATE_PROJECTION_ONLY")
        self.assertEqual(result.as_dict()["truth_authority"], "NONE")
        self.assertEqual(result.as_dict()["effect_authority"], "NONE")
        self.assertEqual(result.as_dict()["completion_authority"], "NONE")

    def test_same_exact_inputs_are_byte_deterministic(self):
        first = project()
        second = project()
        self.assertEqual(first.projection_id, second.projection_id)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.sha256(), second.sha256())

    def test_exact_world_slice_digest_is_bound_into_projection_identity(self):
        first = project(slice_obj=world_slice(provenance_digest="0" * 64))
        second = project(slice_obj=world_slice(provenance_digest="1" * 64))
        self.assertNotEqual(first.slice_digest, second.slice_digest)
        self.assertNotEqual(first.projection_id, second.projection_id)

    def test_out_of_slice_and_tainted_inputs_fail_closed(self):
        with self.assertRaisesRegex(PhysicsProjectionError, "selected by the exact WorldSlice"):
            project(
                slice_obj=world_slice(selected=("pos", "vel")),
                acceleration=atom("acc", (1, -1)),
            )
        with self.assertRaisesRegex(PhysicsProjectionError, "tainted"):
            project(slice_obj=world_slice(tainted=("vel",)))

    def test_unknown_conflict_and_not_computed_inputs_fail_closed(self):
        with self.assertRaisesRegex(PhysicsProjectionError, "KNOWN"):
            project(position=atom("pos", (0, 0), state=KnowledgeState.UNKNOWN))
        with self.assertRaisesRegex(PhysicsProjectionError, "KNOWN"):
            project(position=atom("pos", (0, 0), state=KnowledgeState.CONFLICT))
        with self.assertRaisesRegex(PhysicsProjectionError, "tainted"):
            project(
                slice_obj=world_slice(tainted=("pos",)),
                position=atom("pos", (0, 0), state=KnowledgeState.NOT_COMPUTED),
            )

    def test_generation_and_vector_space_mismatch_fail_closed(self):
        with self.assertRaisesRegex(PhysicsProjectionError, "generation mismatch"):
            project(position=atom("pos", (0, 0), generation=3))
        with self.assertRaisesRegex(PhysicsProjectionError, "vector_space_version mismatch"):
            project(velocity=atom("vel", (1, 2), vector_space="vs:2"))

    def test_role_alias_and_dimension_mismatch_fail_closed(self):
        same = atom("pos", (0, 0))
        with self.assertRaisesRegex(PhysicsProjectionError, "must be distinct"):
            project(position=same, velocity=same)
        with self.assertRaisesRegex(PhysicsProjectionError, "dimensions must match"):
            project(velocity=atom("vel", (1, 2, 3)))
        with self.assertRaisesRegex(PhysicsProjectionError, "dimensions must be in"):
            project(
                position=atom("pos", (0, 0, 0, 0)),
                velocity=atom("vel", (0, 0, 0, 0)),
                acceleration=atom("acc", (0, 0, 0, 0)),
            )

    def test_step_and_time_bounds_reject_bool_zero_and_oversize(self):
        for bad_dt in (True, 0, 10_001):
            with self.subTest(dt_ticks=bad_dt):
                with self.assertRaises(PhysicsProjectionError):
                    project(dt_ticks=bad_dt)  # type: ignore[arg-type]
        for bad_steps in (True, 0, MAX_STEPS + 1):
            with self.subTest(steps=bad_steps):
                with self.assertRaises(PhysicsProjectionError):
                    project(steps=bad_steps)  # type: ignore[arg-type]

    def test_arithmetic_overflow_fails_closed(self):
        with self.assertRaisesRegex(PhysicsProjectionError, "bounded state range"):
            project(
                position=atom("pos", (0,)),
                velocity=atom("vel", (0,)),
                acceleration=atom("acc", (1_000_000_000,)),
                dt_ticks=10_000,
                steps=128,
            )

    def test_source_atom_digests_are_role_bound_and_output_is_frozen(self):
        p = atom("pos", (0, 0))
        v = atom("vel", (1, 2))
        a = atom("acc", (1, -1))
        result = project(position=p, velocity=v, acceleration=a)
        self.assertEqual(result.source_atom_digests, (p.sha256(), v.sha256(), a.sha256()))
        with self.assertRaises(FrozenInstanceError):
            result.steps = 3  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
