#!/usr/bin/env python3
"""Deterministic falsification suite for F2-WP-404 Cognitive Micro-Lab."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
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
    QuboVariable,
    build_qubo_projection,
)
from frankenstein2.sparse_world_basis import (
    EpistemicOrigin,
    KnowledgeState,
    WorldAtom,
    WorldSlice,
)


class ForgedWorldSlice(WorldSlice):
    """Subtype trust-boundary probe; exact-type consumers must reject it."""


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


def world_slice(*, provenance_digest: str = "0" * 64) -> WorldSlice:
    return WorldSlice(
        slice_id="slice:micro-lab",
        need_id="need:micro-lab",
        cycle_id="cycle:1",
        generation=4,
        vector_space_version="vs:1",
        selected_atom_ids=("acc", "choice:a", "choice:b", "pos", "vel"),
        selected_operator_ids=(),
        unresolved_target_atom_ids=("target:unknown",),
        tainted_atom_ids=(),
        depth_reached=1,
        stopped_reason="BOUNDED_COGNITIVE_USE",
        evidence_refs=("evidence:slice",),
        provenance_digest=provenance_digest,
    )


def world_slice_subtype() -> ForgedWorldSlice:
    return ForgedWorldSlice(
        slice_id="slice:micro-lab",
        need_id="need:micro-lab",
        cycle_id="cycle:1",
        generation=4,
        vector_space_version="vs:1",
        selected_atom_ids=("acc", "choice:a", "choice:b", "pos", "vel"),
        selected_operator_ids=(),
        unresolved_target_atom_ids=("target:unknown",),
        tainted_atom_ids=(),
        depth_reached=1,
        stopped_reason="BOUNDED_COGNITIVE_USE",
        evidence_refs=("evidence:slice",),
        provenance_digest="0" * 64,
    )


def inputs(*, slice_obj: WorldSlice | None = None):
    ws = slice_obj or world_slice()
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
        projection_id="qubo:micro-lab",
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
        offset=0,
        provenance_refs=("projection:micro-lab",),
    )
    return ws, position, velocity, acceleration, physics, qubo


def run_lab(**overrides):
    ws, position, velocity, acceleration, physics, qubo = inputs()
    kwargs = {
        "world_slice": ws,
        "qubo_projection": qubo,
        "expected_qubo_projection_sha256": qubo.sha256(),
        "baseline_assignment": (("x:a", 0), ("x:b", 1)),
        "perturbation": QuboBitPerturbation(
            variable_id="x:a",
            expected_from_bit=0,
            to_bit=1,
            rationale_ref="probe:single-bit",
        ),
        "physics_projection": physics,
        "expected_physics_projection_sha256": physics.sha256(),
        "position_atom": position,
        "velocity_atom": velocity,
        "acceleration_atom": acceleration,
    }
    kwargs.update(overrides)
    return run_cognitive_micro_lab(**kwargs)


class CognitiveMicroLabTests(unittest.TestCase):
    def test_single_bit_counterfactual_is_exact_and_preserves_alternatives(self):
        result = run_lab()
        self.assertEqual(result.baseline_score.objective_value, -2)
        self.assertEqual(result.perturbed_score.objective_value, 6)
        self.assertEqual(result.objective_delta, 8)
        self.assertEqual(result.physics_endpoint_position, (16, -4))
        self.assertEqual(result.physics_endpoint_velocity, (5, -2))
        payload = result.as_dict()
        self.assertEqual(payload["alternatives_preserved"], ["BASELINE", "PERTURBED"])
        self.assertEqual(payload["resolution"], "UNRESOLVED_BY_DESIGN")
        self.assertIsNone(payload["selected_winner"])
        self.assertIsNone(payload["selected_action"])

    def test_same_exact_inputs_are_byte_deterministic(self):
        first = run_lab()
        second = run_lab()
        self.assertEqual(first.lab_id, second.lab_id)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.sha256(), second.sha256())

    def test_result_is_frozen_and_has_no_truth_effect_or_completion_authority(self):
        result = run_lab()
        payload = result.as_dict()
        self.assertEqual(payload["epistemic_scope"], "CANDIDATE_MEASUREMENT_ONLY")
        self.assertEqual(payload["truth_authority"], "NONE")
        self.assertEqual(payload["effect_authority"], "NONE")
        self.assertEqual(payload["completion_authority"], "NONE")
        self.assertFalse(payload["world_mutation_performed"])
        self.assertFalse(payload["solver_invoked"])
        self.assertFalse(payload["model_or_provider_invoked"])
        with self.assertRaises(FrozenInstanceError):
            result.objective_delta = 0  # type: ignore[misc]

    def test_world_slice_subtype_is_rejected_at_micro_lab_boundary(self):
        forged = world_slice_subtype()
        with self.assertRaisesRegex(CognitiveMicroLabError, "exact WorldSlice"):
            run_lab(world_slice=forged)

    def test_qubo_projection_is_revalidated_against_exact_world_slice(self):
        ws, position, velocity, acceleration, physics, qubo = inputs()
        changed_slice = world_slice(provenance_digest="1" * 64)
        with self.assertRaisesRegex(CognitiveMicroLabError, "QUBO source binding rejected"):
            run_cognitive_micro_lab(
                world_slice=changed_slice,
                qubo_projection=qubo,
                expected_qubo_projection_sha256=qubo.sha256(),
                baseline_assignment=(("x:a", 0), ("x:b", 1)),
                perturbation=QuboBitPerturbation(
                    variable_id="x:a", expected_from_bit=0, to_bit=1,
                    rationale_ref="probe:binding",
                ),
                physics_projection=physics,
                expected_physics_projection_sha256=physics.sha256(),
                position_atom=position,
                velocity_atom=velocity,
                acceleration_atom=acceleration,
            )

    def test_direct_constructor_physics_self_hash_does_not_bypass_exact_source_replay(self):
        ws, position, velocity, acceleration, physics, qubo = inputs()
        forged = replace(
            physics,
            position_trajectory=physics.position_trajectory[:-1] + ((999, 999),),
        )
        self.assertIs(type(forged), PhysicsProjection)
        with self.assertRaisesRegex(CognitiveMicroLabError, "physics source binding rejected"):
            run_cognitive_micro_lab(
                world_slice=ws,
                qubo_projection=qubo,
                expected_qubo_projection_sha256=qubo.sha256(),
                baseline_assignment=(("x:a", 0), ("x:b", 1)),
                perturbation=QuboBitPerturbation(
                    variable_id="x:a", expected_from_bit=0, to_bit=1,
                    rationale_ref="probe:forged-physics",
                ),
                physics_projection=forged,
                expected_physics_projection_sha256=forged.sha256(),
                position_atom=position,
                velocity_atom=velocity,
                acceleration_atom=acceleration,
            )

    def test_unknown_or_stale_perturbation_fails_closed(self):
        with self.assertRaisesRegex(CognitiveMicroLabError, "absent from baseline_assignment"):
            run_lab(
                perturbation=QuboBitPerturbation(
                    variable_id="x:missing", expected_from_bit=0, to_bit=1,
                    rationale_ref="probe:missing",
                )
            )
        with self.assertRaisesRegex(CognitiveMicroLabError, "expected_from_bit"):
            run_lab(
                perturbation=QuboBitPerturbation(
                    variable_id="x:a", expected_from_bit=1, to_bit=0,
                    rationale_ref="probe:stale",
                )
            )

    def test_assignment_and_perturbation_validation_reject_ambiguous_inputs(self):
        with self.assertRaisesRegex(CognitiveMicroLabError, "canonicalized"):
            run_lab(baseline_assignment=(("x:b", 1), ("x:a", 0)))
        with self.assertRaisesRegex(CognitiveMicroLabError, "must change"):
            QuboBitPerturbation(
                variable_id="x:a", expected_from_bit=0, to_bit=0,
                rationale_ref="probe:no-op",
            )


if __name__ == "__main__":
    unittest.main()
