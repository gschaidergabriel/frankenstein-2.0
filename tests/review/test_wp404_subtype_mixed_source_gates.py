#!/usr/bin/env python3
"""Review-only trust-boundary falsifiers for F2-WP-404.

These tests exercise the already-merged Cognitive Micro-Lab consumer boundary without
modifying WP404-owned production or canonical test paths. Passing means the reviewed
consumer fails closed for these specific subtype/mixed-source cases only.
"""
from __future__ import annotations

import unittest

from frankenstein2.cognitive_micro_lab import (
    CognitiveMicroLabError,
    QuboBitPerturbation,
    run_cognitive_micro_lab,
)
from frankenstein2.physics_projection import (
    PhysicsProjection,
    project_rudimentary_kinematics,
)
from frankenstein2.qubo_projection import (
    QuboCoupling,
    QuboProjection,
    QuboVariable,
    build_qubo_projection,
)
from frankenstein2.sparse_world_basis import (
    EpistemicOrigin,
    KnowledgeState,
    WorldAtom,
    WorldSlice,
)


class ForgedQuboProjection(QuboProjection):
    """Subtype probe; exact-type consumer admission must reject it."""


class ForgedPhysicsProjection(PhysicsProjection):
    """Subtype probe; exact-type consumer admission must reject it."""


class ForgedWorldAtom(WorldAtom):
    """Subtype probe; exact-type consumer admission must reject it."""


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
        slice_id="slice:wp404-review",
        need_id="need:wp404-review",
        cycle_id="cycle:wp404-review",
        generation=4,
        vector_space_version="vs:1",
        selected_atom_ids=("acc", "choice:a", "choice:b", "pos", "vel"),
        selected_operator_ids=(),
        unresolved_target_atom_ids=("target:unknown",),
        tainted_atom_ids=(),
        depth_reached=1,
        stopped_reason="BOUNDED_REVIEW",
        evidence_refs=("evidence:slice",),
        provenance_digest="0" * 64,
    )


def exact_inputs():
    ws = world_slice()
    position = atom("pos", (0, 0))
    velocity = atom("vel", (1, 2))
    acceleration = atom("acc", (1, -1))
    physics = project_rudimentary_kinematics(
        world_slice=ws,
        position_atom=position,
        velocity_atom=velocity,
        acceleration_atom=acceleration,
        dt_ticks=2,
        steps=2,
    )
    qubo = build_qubo_projection(
        projection_id="qubo:wp404-review",
        world_slice=ws,
        expected_slice_sha256=ws.sha256(),
        expected_generation=4,
        variables=(
            QuboVariable(
                variable_id="x:a",
                source_ref="choice:a",
                linear_bias=3,
                provenance_refs=("source:x:a",),
            ),
            QuboVariable(
                variable_id="x:b",
                source_ref="choice:b",
                linear_bias=-2,
                provenance_refs=("source:x:b",),
            ),
        ),
        couplings=(
            QuboCoupling(
                left_variable_id="x:a",
                right_variable_id="x:b",
                weight=5,
                provenance_refs=("source:coupling",),
            ),
        ),
        provenance_refs=("projection:wp404-review",),
    )
    return ws, position, velocity, acceleration, physics, qubo


def kwargs_for(ws, position, velocity, acceleration, physics, qubo):
    return {
        "world_slice": ws,
        "qubo_projection": qubo,
        "expected_qubo_projection_sha256": qubo.sha256(),
        "baseline_assignment": (("x:a", 0), ("x:b", 1)),
        "perturbation": QuboBitPerturbation(
            variable_id="x:a",
            expected_from_bit=0,
            to_bit=1,
            rationale_ref="review:single-bit",
        ),
        "physics_projection": physics,
        "expected_physics_projection_sha256": physics.sha256(),
        "position_atom": position,
        "velocity_atom": velocity,
        "acceleration_atom": acceleration,
    }


class WP404SubtypeMixedSourceReview(unittest.TestCase):
    def test_qubo_projection_subclass_fails_closed(self):
        ws, position, velocity, acceleration, physics, qubo = exact_inputs()
        forged = ForgedQuboProjection(
            projection_id=qubo.projection_id,
            slice_id=qubo.slice_id,
            slice_sha256=qubo.slice_sha256,
            cycle_id=qubo.cycle_id,
            generation=qubo.generation,
            vector_space_version=qubo.vector_space_version,
            variables=qubo.variables,
            couplings=qubo.couplings,
            offset=qubo.offset,
            provenance_refs=qubo.provenance_refs,
        )
        args = kwargs_for(ws, position, velocity, acceleration, physics, qubo)
        args["qubo_projection"] = forged
        args["expected_qubo_projection_sha256"] = forged.sha256()
        with self.assertRaisesRegex(CognitiveMicroLabError, "exact QuboProjection"):
            run_cognitive_micro_lab(**args)

    def test_physics_projection_subclass_fails_closed(self):
        ws, position, velocity, acceleration, physics, qubo = exact_inputs()
        forged = ForgedPhysicsProjection(
            projection_id=physics.projection_id,
            slice_id=physics.slice_id,
            slice_digest=physics.slice_digest,
            need_id=physics.need_id,
            cycle_id=physics.cycle_id,
            generation=physics.generation,
            vector_space_version=physics.vector_space_version,
            position_atom_id=physics.position_atom_id,
            velocity_atom_id=physics.velocity_atom_id,
            acceleration_atom_id=physics.acceleration_atom_id,
            source_atom_digests=physics.source_atom_digests,
            dt_ticks=physics.dt_ticks,
            steps=physics.steps,
            position_trajectory=physics.position_trajectory,
            velocity_trajectory=physics.velocity_trajectory,
        )
        args = kwargs_for(ws, position, velocity, acceleration, physics, qubo)
        args["physics_projection"] = forged
        args["expected_physics_projection_sha256"] = forged.sha256()
        with self.assertRaisesRegex(CognitiveMicroLabError, "exact PhysicsProjection"):
            run_cognitive_micro_lab(**args)

    def test_world_atom_subclass_fails_closed(self):
        ws, position, velocity, acceleration, physics, qubo = exact_inputs()
        forged = ForgedWorldAtom(
            atom_id=position.atom_id,
            generation=position.generation,
            vector_space_version=position.vector_space_version,
            vector=position.vector,
            epistemic_origin=position.epistemic_origin,
            knowledge_state=position.knowledge_state,
            provenance_refs=position.provenance_refs,
            evidence_refs=position.evidence_refs,
            confidence_micros=position.confidence_micros,
        )
        args = kwargs_for(ws, position, velocity, acceleration, physics, qubo)
        args["position_atom"] = forged
        with self.assertRaisesRegex(CognitiveMicroLabError, "position_atom must be exact WorldAtom"):
            run_cognitive_micro_lab(**args)

    def test_exact_type_but_changed_source_content_fails_replay(self):
        ws, position, velocity, acceleration, physics, qubo = exact_inputs()
        changed_acceleration = atom("acc", (999, -999))
        args = kwargs_for(ws, position, velocity, acceleration, physics, qubo)
        args["acceleration_atom"] = changed_acceleration
        with self.assertRaisesRegex(CognitiveMicroLabError, "physics source binding rejected"):
            run_cognitive_micro_lab(**args)


if __name__ == "__main__":
    unittest.main()
