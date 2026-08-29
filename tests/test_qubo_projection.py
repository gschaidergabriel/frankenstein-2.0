#!/usr/bin/env python3
"""Deterministic falsification suite for F2-WP-402 QUBO projection."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from frankenstein2.qubo_projection import (
    QuboCoupling,
    QuboProjection,
    QuboProjectionError,
    QuboVariable,
    compile_qubo_projection,
    evaluate_qubo_assignment,
)
from frankenstein2.sparse_world_basis import WorldSlice


def world_slice(
    *,
    selected: tuple[str, ...] = ("a", "b", "c"),
    tainted: tuple[str, ...] = (),
    evidence: tuple[str, ...] = ("evidence:slice",),
    provenance_digest: str = "0" * 64,
) -> WorldSlice:
    return WorldSlice(
        slice_id="slice:1",
        need_id="need:1",
        cycle_id="cycle:1",
        generation=4,
        vector_space_version="vs:1",
        selected_atom_ids=selected,
        selected_operator_ids=("op:ab",),
        unresolved_target_atom_ids=(),
        tainted_atom_ids=tainted,
        depth_reached=1,
        stopped_reason="TARGETS_REACHED",
        evidence_refs=evidence,
        provenance_digest=provenance_digest,
    )


def variable(variable_id: str, atom_id: str, bias: int) -> QuboVariable:
    return QuboVariable(variable_id=variable_id, atom_id=atom_id, linear_bias=bias)


def coupling(left: str, right: str, bias: int) -> QuboCoupling:
    return QuboCoupling(
        left_variable_id=left,
        right_variable_id=right,
        quadratic_bias=bias,
    )


def projection(*, reverse: bool = False) -> QuboProjection:
    variables = (
        variable("x:a", "a", 3),
        variable("x:b", "b", -2),
        variable("x:c", "c", 0),
    )
    couplings = (
        coupling("x:a", "x:b", 5),
        coupling("x:b", "x:c", -7),
    )
    if reverse:
        variables = tuple(reversed(variables))
        couplings = tuple(reversed(couplings))
    return compile_qubo_projection(
        source_slice=world_slice(),
        projection_id="qubo:1",
        variables=variables,
        couplings=couplings,
        provenance_refs=("objective:caller", "world-slice:exact"),
        offset_bias=11,
    )


class QuboProjectionTests(unittest.TestCase):
    def test_projection_is_deterministic_across_input_order(self):
        first = projection()
        second = projection(reverse=True)
        self.assertEqual(tuple(item.variable_id for item in first.variables), ("x:a", "x:b", "x:c"))
        self.assertEqual(tuple(item.pair for item in first.couplings), (("x:a", "x:b"), ("x:b", "x:c")))
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.sha256(), second.sha256())

    def test_projection_binds_exact_world_slice_digest(self):
        source = world_slice()
        bound = compile_qubo_projection(
            source_slice=source,
            projection_id="qubo:bind",
            variables=(variable("x:a", "a", 1),),
            couplings=(),
            provenance_refs=("objective:caller",),
        )
        self.assertIs(bound.source_slice, source)
        self.assertEqual(bound.source_slice_id, source.slice_id)
        self.assertEqual(bound.source_generation, source.generation)
        self.assertEqual(bound.source_slice_sha256, source.sha256())

        changed = world_slice(evidence=("evidence:changed",), provenance_digest="1" * 64)
        rebound = compile_qubo_projection(
            source_slice=changed,
            projection_id="qubo:bind",
            variables=(variable("x:a", "a", 1),),
            couplings=(),
            provenance_refs=("objective:caller",),
        )
        self.assertNotEqual(bound.source_slice_sha256, rebound.source_slice_sha256)
        self.assertNotEqual(bound.sha256(), rebound.sha256())

    def test_public_projection_constructor_cannot_accept_forged_slice_digest(self):
        source = world_slice()
        kwargs = {
            "projection_id": "qubo:constructor",
            "source_slice": source,
            "variables": (variable("x:a", "a", 1),),
            "couplings": (),
            "offset_bias": 0,
            "provenance_refs": ("objective:caller",),
            "source_slice_sha256": "f" * 64,
        }
        with self.assertRaises(TypeError):
            QuboProjection(**kwargs)  # type: ignore[arg-type]

        direct = QuboProjection(
            projection_id="qubo:constructor",
            source_slice=source,
            variables=(variable("x:a", "a", 1),),
            couplings=(),
            offset_bias=0,
            provenance_refs=("objective:caller",),
        )
        self.assertEqual(direct.source_slice_sha256, source.sha256())

    def test_variable_must_reference_selected_and_untainted_atom(self):
        with self.assertRaisesRegex(QuboProjectionError, "not selected"):
            compile_qubo_projection(
                source_slice=world_slice(),
                projection_id="qubo:bad",
                variables=(variable("x:z", "z", 1),),
                couplings=(),
                provenance_refs=("objective:caller",),
            )
        with self.assertRaisesRegex(QuboProjectionError, "tainted"):
            compile_qubo_projection(
                source_slice=world_slice(tainted=("b",)),
                projection_id="qubo:taint",
                variables=(variable("x:b", "b", 1),),
                couplings=(),
                provenance_refs=("objective:caller",),
            )

    def test_duplicate_variable_and_atom_bindings_fail_closed(self):
        with self.assertRaisesRegex(QuboProjectionError, "duplicate variable_id"):
            compile_qubo_projection(
                source_slice=world_slice(),
                projection_id="qubo:dup-var",
                variables=(variable("x", "a", 1), variable("x", "b", 2)),
                couplings=(),
                provenance_refs=("objective:caller",),
            )
        with self.assertRaisesRegex(QuboProjectionError, "duplicate atom_id"):
            compile_qubo_projection(
                source_slice=world_slice(),
                projection_id="qubo:dup-atom",
                variables=(variable("x:a:1", "a", 1), variable("x:a:2", "a", 2)),
                couplings=(),
                provenance_refs=("objective:caller",),
            )

    def test_duplicate_coupling_including_reversed_pair_fails_closed(self):
        with self.assertRaisesRegex(QuboProjectionError, "duplicate QUBO coupling pair"):
            compile_qubo_projection(
                source_slice=world_slice(),
                projection_id="qubo:dup-coupling",
                variables=(variable("x:a", "a", 1), variable("x:b", "b", 2)),
                couplings=(
                    coupling("x:a", "x:b", 3),
                    coupling("x:b", "x:a", 4),
                ),
                provenance_refs=("objective:caller",),
            )

    def test_coupling_requires_two_declared_distinct_variables(self):
        with self.assertRaisesRegex(QuboProjectionError, "distinct"):
            coupling("x:a", "x:a", 1)
        with self.assertRaisesRegex(QuboProjectionError, "undeclared"):
            compile_qubo_projection(
                source_slice=world_slice(),
                projection_id="qubo:unknown-var",
                variables=(variable("x:a", "a", 1),),
                couplings=(coupling("x:a", "x:b", 2),),
                provenance_refs=("objective:caller",),
            )

    def test_biases_are_bounded_integers_and_bool_is_rejected(self):
        for bad in (True, 1.5, 1_000_000_001):
            with self.subTest(bad=bad):
                with self.assertRaises(QuboProjectionError):
                    variable("x:a", "a", bad)  # type: ignore[arg-type]
        with self.assertRaises(QuboProjectionError):
            coupling("x:a", "x:b", -1_000_000_001)

    def test_mutable_containers_fail_closed(self):
        with self.assertRaisesRegex(QuboProjectionError, "variables must be a non-empty immutable tuple"):
            compile_qubo_projection(
                source_slice=world_slice(),
                projection_id="qubo:list-vars",
                variables=[variable("x:a", "a", 1)],  # type: ignore[arg-type]
                couplings=(),
                provenance_refs=("objective:caller",),
            )
        with self.assertRaisesRegex(QuboProjectionError, "couplings must be an immutable tuple"):
            compile_qubo_projection(
                source_slice=world_slice(),
                projection_id="qubo:list-couplings",
                variables=(variable("x:a", "a", 1),),
                couplings=[],  # type: ignore[arg-type]
                provenance_refs=("objective:caller",),
            )
        with self.assertRaisesRegex(QuboProjectionError, "provenance_refs must be an immutable tuple"):
            compile_qubo_projection(
                source_slice=world_slice(),
                projection_id="qubo:list-provenance",
                variables=(variable("x:a", "a", 1),),
                couplings=(),
                provenance_refs=["objective:caller"],  # type: ignore[arg-type]
            )

    def test_energy_matches_binary_quadratic_formula(self):
        item = projection()
        measured = evaluate_qubo_assignment(
            projection=item,
            assignment=(("x:c", 0), ("x:a", 1), ("x:b", 1)),
        )
        # 11 + 3*1 + (-2)*1 + 0*0 + 5*1*1 + (-7)*1*0 = 17
        self.assertEqual(measured.energy, 17)
        self.assertEqual(measured.assignment, (("x:a", 1), ("x:b", 1), ("x:c", 0)))
        self.assertEqual(measured.projection_sha256, item.sha256())
        self.assertEqual(measured.as_dict()["optimality_claim"], "NONE")

    def test_assignment_must_cover_exact_variables_with_integer_bits(self):
        item = projection()
        bad_assignments = (
            (("x:a", 1), ("x:b", 0)),
            (("x:a", 1), ("x:b", 0), ("x:c", 1), ("x:z", 0)),
            (("x:a", 1), ("x:a", 0), ("x:b", 0), ("x:c", 1)),
            (("x:a", True), ("x:b", 0), ("x:c", 1)),
            (("x:a", 2), ("x:b", 0), ("x:c", 1)),
        )
        for assignment in bad_assignments:
            with self.subTest(assignment=assignment):
                with self.assertRaises(QuboProjectionError):
                    evaluate_qubo_assignment(projection=item, assignment=assignment)  # type: ignore[arg-type]
        with self.assertRaisesRegex(QuboProjectionError, "immutable tuple"):
            evaluate_qubo_assignment(
                projection=item,
                assignment=[["x:a", 1], ["x:b", 0], ["x:c", 1]],  # type: ignore[arg-type]
            )

    def test_zero_coefficients_are_allowed_but_do_not_imply_optimality(self):
        item = compile_qubo_projection(
            source_slice=world_slice(),
            projection_id="qubo:zero",
            variables=(variable("x:a", "a", 0),),
            couplings=(),
            provenance_refs=("objective:caller",),
        )
        measured = evaluate_qubo_assignment(projection=item, assignment=(("x:a", 0),))
        self.assertEqual(measured.energy, 0)
        self.assertEqual(measured.as_dict()["optimality_claim"], "NONE")

    def test_structures_are_frozen_and_all_authorities_are_none(self):
        item = projection()
        with self.assertRaises(FrozenInstanceError):
            item.projection_id = "mutated"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            item.variables[0].linear_bias = 99  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            item.source_slice.slice_id = "mutated"  # type: ignore[misc]
        self.assertEqual(item.as_dict()["solver_authority"], "NONE")
        self.assertEqual(item.as_dict()["truth_authority"], "NONE")
        self.assertEqual(item.as_dict()["effect_authority"], "NONE")
        self.assertEqual(item.as_dict()["completion_authority"], "NONE")


if __name__ == "__main__":
    unittest.main()
