#!/usr/bin/env python3
"""Deterministic falsification suite for F2-WP-402 QUBO projection adapter."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from frankenstein2.qubo_projection import (
    COEFFICIENT_ABS_MAX,
    QuboCoupling,
    QuboProjectionError,
    QuboVariable,
    build_qubo_projection,
    score_assignment,
)
from frankenstein2.sparse_world_basis import WorldSlice


PROVENANCE_DIGEST = "0" * 64


def world_slice(*, tainted: tuple[str, ...] = ()) -> WorldSlice:
    return WorldSlice(
        slice_id="slice:1",
        need_id="need:1",
        cycle_id="cycle:1",
        generation=7,
        vector_space_version="vs:1",
        selected_atom_ids=("atom:a", "atom:b", "atom:c"),
        selected_operator_ids=("op:ab",),
        unresolved_target_atom_ids=("atom:target",),
        tainted_atom_ids=tainted,
        depth_reached=1,
        stopped_reason="MAX_DEPTH_REACHED",
        evidence_refs=("evidence:slice",),
        provenance_digest=PROVENANCE_DIGEST,
    )


def variable(variable_id: str, source_ref: str, bias: int) -> QuboVariable:
    return QuboVariable(
        variable_id=variable_id,
        source_ref=source_ref,
        linear_bias=bias,
        provenance_refs=(f"source:{variable_id}",),
    )


def coupling(left: str, right: str, weight: int) -> QuboCoupling:
    return QuboCoupling(
        left_variable_id=left,
        right_variable_id=right,
        weight=weight,
        provenance_refs=(f"source:{left}:{right}",),
    )


def projection(*, reverse: bool = False):
    ws = world_slice()
    variables = (
        variable("x:a", "atom:a", -3),
        variable("x:b", "atom:b", 5),
        variable("x:op", "op:ab", 2),
    )
    couplings = (
        coupling("x:b", "x:a", 7),
        coupling("x:op", "x:b", -4),
    )
    if reverse:
        variables = tuple(reversed(variables))
        couplings = tuple(reversed(couplings))
    return build_qubo_projection(
        projection_id="qubo:1",
        world_slice=ws,
        expected_slice_sha256=ws.sha256(),
        expected_generation=7,
        variables=variables,
        couplings=couplings,
        offset=11,
        provenance_refs=("projection:test",),
    )


class QuboProjectionTests(unittest.TestCase):
    def test_projection_is_order_invariant_and_exactly_bound_to_world_slice(self):
        first = projection()
        second = projection(reverse=True)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(first.slice_id, "slice:1")
        self.assertEqual(first.cycle_id, "cycle:1")
        self.assertEqual(first.generation, 7)
        self.assertEqual(first.vector_space_version, "vs:1")
        self.assertEqual(tuple(v.variable_id for v in first.variables), ("x:a", "x:b", "x:op"))
        self.assertEqual(tuple(c.pair for c in first.couplings), (("x:a", "x:b"), ("x:b", "x:op")))
        self.assertIn("evidence:slice", first.provenance_refs)

    def test_slice_digest_and_generation_mismatch_fail_closed(self):
        ws = world_slice()
        with self.assertRaisesRegex(QuboProjectionError, "digest mismatch"):
            build_qubo_projection(
                projection_id="q",
                world_slice=ws,
                expected_slice_sha256="1" * 64,
                expected_generation=7,
                variables=(variable("x", "atom:a", 1),),
                couplings=(),
                provenance_refs=("p",),
            )
        with self.assertRaisesRegex(QuboProjectionError, "generation mismatch"):
            build_qubo_projection(
                projection_id="q",
                world_slice=ws,
                expected_slice_sha256=ws.sha256(),
                expected_generation=8,
                variables=(variable("x", "atom:a", 1),),
                couplings=(),
                provenance_refs=("p",),
            )

    def test_variable_must_reference_selected_non_tainted_local_slice_item(self):
        ws = world_slice()
        with self.assertRaisesRegex(QuboProjectionError, "outside selected WorldSlice"):
            build_qubo_projection(
                projection_id="q",
                world_slice=ws,
                expected_slice_sha256=ws.sha256(),
                expected_generation=7,
                variables=(variable("x", "atom:not-selected", 1),),
                couplings=(),
                provenance_refs=("p",),
            )
        tainted_ws = world_slice(tainted=("atom:b",))
        with self.assertRaisesRegex(QuboProjectionError, "tainted/NOT_COMPUTED"):
            build_qubo_projection(
                projection_id="q",
                world_slice=tainted_ws,
                expected_slice_sha256=tainted_ws.sha256(),
                expected_generation=7,
                variables=(variable("x", "atom:b", 1),),
                couplings=(),
                provenance_refs=("p",),
            )

    def test_duplicate_variable_coupling_self_pair_and_unknown_variable_fail_closed(self):
        ws = world_slice()
        with self.assertRaisesRegex(QuboProjectionError, "duplicate variable_id"):
            build_qubo_projection(
                projection_id="q",
                world_slice=ws,
                expected_slice_sha256=ws.sha256(),
                expected_generation=7,
                variables=(variable("x", "atom:a", 1), variable("x", "atom:b", 2)),
                couplings=(),
                provenance_refs=("p",),
            )
        with self.assertRaisesRegex(QuboProjectionError, "distinct variables"):
            coupling("x", "x", 1)
        with self.assertRaisesRegex(QuboProjectionError, "unknown variable"):
            build_qubo_projection(
                projection_id="q",
                world_slice=ws,
                expected_slice_sha256=ws.sha256(),
                expected_generation=7,
                variables=(variable("x:a", "atom:a", 1),),
                couplings=(coupling("x:a", "x:missing", 1),),
                provenance_refs=("p",),
            )
        with self.assertRaisesRegex(QuboProjectionError, "duplicate QUBO coupling pair"):
            build_qubo_projection(
                projection_id="q",
                world_slice=ws,
                expected_slice_sha256=ws.sha256(),
                expected_generation=7,
                variables=(variable("x:a", "atom:a", 1), variable("x:b", "atom:b", 2)),
                couplings=(coupling("x:a", "x:b", 1), coupling("x:b", "x:a", 2)),
                provenance_refs=("p",),
            )

    def test_coefficients_are_bounded_integers(self):
        self.assertEqual(variable("x", "atom:a", COEFFICIENT_ABS_MAX).linear_bias, COEFFICIENT_ABS_MAX)
        with self.assertRaisesRegex(QuboProjectionError, "linear_bias"):
            variable("x", "atom:a", COEFFICIENT_ABS_MAX + 1)
        with self.assertRaisesRegex(QuboProjectionError, "weight"):
            coupling("x", "y", -(COEFFICIENT_ABS_MAX + 1))
        with self.assertRaisesRegex(QuboProjectionError, "linear_bias"):
            variable("x", "atom:a", True)

    def test_explicit_complete_assignment_is_scored_without_selection(self):
        item = projection()
        scored = score_assignment(
            projection=item,
            assignment=(("x:op", 0), ("x:b", 1), ("x:a", 1)),
            expected_projection_sha256=item.sha256(),
        )
        self.assertEqual(scored.assignment, (("x:a", 1), ("x:b", 1), ("x:op", 0)))
        self.assertEqual(scored.objective_value, 20)
        self.assertEqual(scored.as_dict()["selected_as_action"], False)
        self.assertEqual(scored.as_dict()["effect_authority"], "NONE")

    def test_assignment_fails_closed_on_digest_bit_duplicates_missing_or_extra(self):
        item = projection()
        with self.assertRaisesRegex(QuboProjectionError, "projection digest mismatch"):
            score_assignment(
                projection=item,
                assignment=(("x:a", 1), ("x:b", 1), ("x:op", 0)),
                expected_projection_sha256="1" * 64,
            )
        with self.assertRaisesRegex(QuboProjectionError, "integer 0 or 1"):
            score_assignment(
                projection=item,
                assignment=(("x:a", 2), ("x:b", 1), ("x:op", 0)),
                expected_projection_sha256=item.sha256(),
            )
        with self.assertRaisesRegex(QuboProjectionError, "duplicate variable_id"):
            score_assignment(
                projection=item,
                assignment=(("x:a", 1), ("x:a", 0), ("x:op", 0)),
                expected_projection_sha256=item.sha256(),
            )
        with self.assertRaisesRegex(QuboProjectionError, "variable set mismatch"):
            score_assignment(
                projection=item,
                assignment=(("x:a", 1), ("x:b", 1)),
                expected_projection_sha256=item.sha256(),
            )
        with self.assertRaisesRegex(QuboProjectionError, "variable set mismatch"):
            score_assignment(
                projection=item,
                assignment=(("x:a", 1), ("x:b", 1), ("x:op", 0), ("x:extra", 0)),
                expected_projection_sha256=item.sha256(),
            )

    def test_structures_are_frozen_and_authority_is_explicitly_none(self):
        item = projection()
        with self.assertRaises(FrozenInstanceError):
            item.projection_id = "mutated"  # type: ignore[misc]
        payload = item.as_dict()
        self.assertEqual(payload["truth_authority"], "NONE")
        self.assertEqual(payload["effect_authority"], "NONE")
        self.assertEqual(payload["completion_authority"], "NONE")
        self.assertFalse(payload["solver_invoked"])


if __name__ == "__main__":
    unittest.main()
