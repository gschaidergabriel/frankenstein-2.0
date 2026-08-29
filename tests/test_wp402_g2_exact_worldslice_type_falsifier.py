#!/usr/bin/env python3
"""Independent exact-current WP402 G2 source-boundary falsifier."""
from __future__ import annotations

import unittest

from frankenstein2.qubo_projection import (
    QuboProjectionError,
    QuboVariable,
    build_qubo_projection,
)
from frankenstein2.sparse_world_basis import WorldSlice


class ForgedWorldSlice(WorldSlice):
    """Adversarial subtype that forges the digest method used by the QUBO boundary."""

    def sha256(self) -> str:
        return "0" * 64


class CurrentMainExactWorldSliceTypeFalsifierTests(unittest.TestCase):
    def test_build_rejects_worldslice_subclass_with_forged_digest(self) -> None:
        world_slice = ForgedWorldSlice(
            slice_id="slice:g2-exact-type-falsifier",
            need_id="need:g2-exact-type-falsifier",
            cycle_id="cycle:g2-exact-type-falsifier",
            generation=7,
            vector_space_version="vs:g2",
            selected_atom_ids=("atom:a",),
            selected_operator_ids=(),
            unresolved_target_atom_ids=(),
            tainted_atom_ids=(),
            depth_reached=0,
            stopped_reason="BOUNDED_FALSIFIER",
            evidence_refs=("evidence:g2-exact-type-falsifier",),
            provenance_digest="1" * 64,
        )
        variable = QuboVariable(
            variable_id="x:a",
            source_ref="atom:a",
            linear_bias=1,
            provenance_refs=("source:g2-exact-type-falsifier",),
        )

        with self.assertRaisesRegex(QuboProjectionError, "WorldSlice"):
            build_qubo_projection(
                projection_id="qubo:g2-exact-type-falsifier",
                world_slice=world_slice,
                expected_slice_sha256="0" * 64,
                expected_generation=7,
                variables=(variable,),
                couplings=(),
                provenance_refs=("review:wp402-g2-exact-worldslice",),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
