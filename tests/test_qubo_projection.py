#!/usr/bin/env python3
"""Deterministic falsification suite for F2-WP-402 QUBO projection adapter."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from frankenstein2.qubo_projection import (
    COEFFICIENT_ABS_MAX,
    QuboCoupling,
    QuboProjection,
    QuboProjectionError,
    QuboVariable,
    build_qubo_projection,
    score_assignment,
)
from frankenstein2.sparse_world_basis import WorldSlice


PROVENANCE_DIGEST = "0" * 64


class ForgedWorldSlice(WorldSlice):
    """Adversarial subtype able to self-attest an attacker-selected digest."""

    def sha256(self) -> str:
        return "0" * 64


class ForgedQuboProjection(QuboProjection):
    """Adversarial subtype able to self-attest an attacker-selected projection digest."""

    def sha256(self) -> str:
        return "0" * 64


class ForgedQuboVariable(QuboVariable):
    """Adversarial subtype crossing a projection-input trust boundary."""


class ForgedQuboCoupling(QuboCoupling):
    """Adversarial subtype crossing a projection-input trust boundary."""


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


def forged_world_slice() -> ForgedWorldSlice:
    return ForgedWorldSlice(
        slice_id="slice:forged-subtype",
        need_id="need:forged-subtype",
        cycle_id="cycle:forged-subtype",
        generation=7,
        vector_space_version="vs:1",
        selected_atom_ids=("atom:a",),
        selected_operator_ids=(),
        unresolved_target_atom_ids=(),
        tainted_atom_ids=(),
        depth_reached=0,
        stopped_reason="BOUNDED_FALSIFIER",
        evidence_refs=("evidence:forged-subtype",),
        provenance_digest="1" * 64,
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
                projection_id="q", world_slice=ws, expected_slice_sha256="1" * 64,
                expected_generation=7, variables=(variable("x", "atom:a", 1),),
                couplings=(), provenance_refs=("p",),
            )
        with self.assertRaisesRegex(QuboProjectionError, "generation mismatch"):
            build_qubo_projection(
                projection_id="q", world_slice=ws, expected_slice_sha256=ws.sha256(),
                expected_generation=8, variables=(variable("x", "atom:a", 1),),
                couplings=(), provenance_refs=("p",),
            )

    def test_variable_must_reference_selected_non_tainted_local_slice_item(self):
        ws = world_slice()
        with self.assertRaisesRegex(QuboProjectionError, "outside selected WorldSlice"):
            build_qubo_projection(
                projection_id="q", world_slice=ws, expected_slice_sha256=ws.sha256(),
                expected_generation=7, variables=(variable("x", "atom:not-selected", 1),),
                couplings=(), provenance_refs=("p",),
            )
        tainted_ws = world_slice(tainted=("atom:b",))
        with self.assertRaisesRegex(QuboProjectionError, "tainted/NOT_COMPUTED"):
            build_qubo_projection(
                projection_id="q", world_slice=tainted_ws,
                expected_slice_sha256=tainted_ws.sha256(), expected_generation=7,
                variables=(variable("x", "atom:b", 1),), couplings=(), provenance_refs=("p",),
            )

    def test_duplicate_variable_coupling_self_pair_and_unknown_variable_fail_closed(self):
        ws = world_slice()
        with self.assertRaisesRegex(QuboProjectionError, "duplicate variable_id"):
            build_qubo_projection(
                projection_id="q", world_slice=ws, expected_slice_sha256=ws.sha256(),
                expected_generation=7,
                variables=(variable("x", "atom:a", 1), variable("x", "atom:b", 2)),
                couplings=(), provenance_refs=("p",),
            )
        with self.assertRaisesRegex(QuboProjectionError, "distinct variables"):
            coupling("x", "x", 1)
        with self.assertRaisesRegex(QuboProjectionError, "unknown variable"):
            build_qubo_projection(
                projection_id="q", world_slice=ws, expected_slice_sha256=ws.sha256(),
                expected_generation=7, variables=(variable("x:a", "atom:a", 1),),
                couplings=(coupling("x:a", "x:missing", 1),), provenance_refs=("p",),
            )
        with self.assertRaisesRegex(QuboProjectionError, "duplicate QUBO coupling pair"):
            build_qubo_projection(
                projection_id="q", world_slice=ws, expected_slice_sha256=ws.sha256(),
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
        ws = world_slice()
        scored = score_assignment(
            projection=item,
            world_slice=ws,
            assignment=(("x:op", 0), ("x:b", 1), ("x:a", 1)),
            expected_projection_sha256=item.sha256(),
        )
        self.assertEqual(scored.assignment, (("x:a", 1), ("x:b", 1), ("x:op", 0)))
        self.assertEqual(scored.objective_value, 20)
        self.assertEqual(scored.as_dict()["selected_as_action"], False)
        self.assertEqual(scored.as_dict()["effect_authority"], "NONE")

    def test_direct_constructor_slice_binding_forgery_is_rejected_at_scoring_boundary(self):
        ws = world_slice()
        forged = QuboProjection(
            projection_id="qubo:forged",
            slice_id=ws.slice_id,
            slice_sha256=ws.sha256(),
            cycle_id=ws.cycle_id,
            generation=ws.generation,
            vector_space_version=ws.vector_space_version,
            variables=(variable("x:forged", "atom:not-selected", 3),),
            couplings=(),
            offset=0,
            provenance_refs=("forgery:test",),
        )
        with self.assertRaisesRegex(QuboProjectionError, "outside selected WorldSlice"):
            score_assignment(
                projection=forged,
                world_slice=ws,
                assignment=(("x:forged", 1),),
                expected_projection_sha256=forged.sha256(),
            )

    def test_scoring_revalidates_exact_slice_identity_and_taint(self):
        item = projection()
        wrong_cycle = WorldSlice(
            slice_id="slice:1", need_id="need:1", cycle_id="cycle:other", generation=7,
            vector_space_version="vs:1", selected_atom_ids=("atom:a", "atom:b", "atom:c"),
            selected_operator_ids=("op:ab",), unresolved_target_atom_ids=("atom:target",),
            tainted_atom_ids=(), depth_reached=1, stopped_reason="MAX_DEPTH_REACHED",
            evidence_refs=("evidence:slice",), provenance_digest=PROVENANCE_DIGEST,
        )
        with self.assertRaisesRegex(QuboProjectionError, "digest mismatch"):
            score_assignment(
                projection=item, world_slice=wrong_cycle,
                assignment=(("x:a", 1), ("x:b", 1), ("x:op", 0)),
                expected_projection_sha256=item.sha256(),
            )

        tainted = world_slice(tainted=("atom:b",))
        forged_taint_bound = QuboProjection(
            projection_id="qubo:taint", slice_id=tainted.slice_id,
            slice_sha256=tainted.sha256(), cycle_id=tainted.cycle_id,
            generation=tainted.generation, vector_space_version=tainted.vector_space_version,
            variables=(variable("x:b", "atom:b", 1),), couplings=(), offset=0,
            provenance_refs=("forgery:taint",),
        )
        with self.assertRaisesRegex(QuboProjectionError, "tainted/NOT_COMPUTED"):
            score_assignment(
                projection=forged_taint_bound, world_slice=tainted,
                assignment=(("x:b", 1),),
                expected_projection_sha256=forged_taint_bound.sha256(),
            )

    def test_assignment_fails_closed_on_digest_bit_duplicates_missing_or_extra(self):
        item = projection()
        ws = world_slice()
        with self.assertRaisesRegex(QuboProjectionError, "projection digest mismatch"):
            score_assignment(
                projection=item, world_slice=ws,
                assignment=(("x:a", 1), ("x:b", 1), ("x:op", 0)),
                expected_projection_sha256="1" * 64,
            )
        with self.assertRaisesRegex(QuboProjectionError, "integer 0 or 1"):
            score_assignment(
                projection=item, world_slice=ws,
                assignment=(("x:a", 2), ("x:b", 1), ("x:op", 0)),
                expected_projection_sha256=item.sha256(),
            )
        with self.assertRaisesRegex(QuboProjectionError, "duplicate variable_id"):
            score_assignment(
                projection=item, world_slice=ws,
                assignment=(("x:a", 1), ("x:a", 0), ("x:op", 0)),
                expected_projection_sha256=item.sha256(),
            )
        with self.assertRaisesRegex(QuboProjectionError, "variable set mismatch"):
            score_assignment(
                projection=item, world_slice=ws, assignment=(("x:a", 1), ("x:b", 1)),
                expected_projection_sha256=item.sha256(),
            )
        with self.assertRaisesRegex(QuboProjectionError, "variable set mismatch"):
            score_assignment(
                projection=item, world_slice=ws,
                assignment=(("x:a", 1), ("x:b", 1), ("x:op", 0), ("x:extra", 0)),
                expected_projection_sha256=item.sha256(),
            )

    def test_worldslice_subtype_self_attestation_is_rejected_at_build_and_score(self):
        forged_ws = forged_world_slice()
        self.assertEqual(forged_ws.sha256(), "0" * 64)
        exact_variable = variable("x:a", "atom:a", 1)

        with self.assertRaises(QuboProjectionError):
            build_qubo_projection(
                projection_id="qubo:forged-worldslice-build",
                world_slice=forged_ws,
                expected_slice_sha256="0" * 64,
                expected_generation=7,
                variables=(exact_variable,),
                couplings=(),
                offset=0,
                provenance_refs=("g3:falsifier:worldslice-build",),
            )

        direct_projection = QuboProjection(
            projection_id="qubo:forged-worldslice-score",
            slice_id=forged_ws.slice_id,
            slice_sha256="0" * 64,
            cycle_id=forged_ws.cycle_id,
            generation=forged_ws.generation,
            vector_space_version=forged_ws.vector_space_version,
            variables=(exact_variable,),
            couplings=(),
            offset=0,
            provenance_refs=("g3:falsifier:worldslice-score",),
        )
        with self.assertRaises(QuboProjectionError):
            score_assignment(
                projection=direct_projection,
                world_slice=forged_ws,
                assignment=(("x:a", 1),),
                expected_projection_sha256=direct_projection.sha256(),
            )

    def test_projection_subtype_self_attestation_is_rejected_at_score(self):
        exact = projection()
        forged = ForgedQuboProjection(
            projection_id=exact.projection_id,
            slice_id=exact.slice_id,
            slice_sha256=exact.slice_sha256,
            cycle_id=exact.cycle_id,
            generation=exact.generation,
            vector_space_version=exact.vector_space_version,
            variables=exact.variables,
            couplings=exact.couplings,
            offset=exact.offset,
            provenance_refs=exact.provenance_refs,
        )
        self.assertEqual(forged.sha256(), "0" * 64)
        with self.assertRaises(QuboProjectionError):
            score_assignment(
                projection=forged,
                world_slice=world_slice(),
                assignment=(("x:a", 1), ("x:b", 1), ("x:op", 0)),
                expected_projection_sha256="0" * 64,
            )

    def test_variable_and_coupling_subtypes_are_rejected_at_projection_admission(self):
        ws = world_slice()
        forged_variable = ForgedQuboVariable(
            variable_id="x:forged-var",
            source_ref="atom:a",
            linear_bias=1,
            provenance_refs=("g3:falsifier:variable-subtype",),
        )
        with self.assertRaises(QuboProjectionError):
            build_qubo_projection(
                projection_id="qubo:forged-variable",
                world_slice=ws,
                expected_slice_sha256=ws.sha256(),
                expected_generation=ws.generation,
                variables=(forged_variable,),
                couplings=(),
                provenance_refs=("g3:falsifier:variable-subtype",),
            )

        left = variable("x:a", "atom:a", 1)
        right = variable("x:b", "atom:b", 2)
        forged_coupling = ForgedQuboCoupling(
            left_variable_id="x:a",
            right_variable_id="x:b",
            weight=3,
            provenance_refs=("g3:falsifier:coupling-subtype",),
        )
        with self.assertRaises(QuboProjectionError):
            build_qubo_projection(
                projection_id="qubo:forged-coupling",
                world_slice=ws,
                expected_slice_sha256=ws.sha256(),
                expected_generation=ws.generation,
                variables=(left, right),
                couplings=(forged_coupling,),
                provenance_refs=("g3:falsifier:coupling-subtype",),
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