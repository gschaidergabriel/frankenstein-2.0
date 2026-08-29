#!/usr/bin/env python3
"""Independent exact-current WP402 G2 exact-WorldSlice falsifiers."""
from __future__ import annotations

import unittest

from frankenstein2.qubo_projection import (
    QuboProjectionError,
    QuboVariable,
    build_qubo_projection,
    score_assignment,
)
from frankenstein2.sparse_world_basis import WorldSlice


class ForgedWorldSlice(WorldSlice):
    """Adversarial subtype whose digest is caller-controlled via provenance_digest."""

    def sha256(self) -> str:
        return self.provenance_digest


def make_slice(*, evidence: tuple[str, ...], provenance_digest: str) -> WorldSlice:
    return WorldSlice(
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
        evidence_refs=evidence,
        provenance_digest=provenance_digest,
    )


def make_variable() -> QuboVariable:
    return QuboVariable(
        variable_id="x:a",
        source_ref="atom:a",
        linear_bias=1,
        provenance_refs=("source:g2-exact-type-falsifier",),
    )


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
            evidence_refs=("evidence:forged",),
            provenance_digest="0" * 64,
        )

        with self.assertRaisesRegex(QuboProjectionError, "WorldSlice"):
            build_qubo_projection(
                projection_id="qubo:g2-build-exact-type-falsifier",
                world_slice=world_slice,
                expected_slice_sha256="0" * 64,
                expected_generation=7,
                variables=(make_variable(),),
                couplings=(),
                provenance_refs=("review:wp402-g2-build-exact-worldslice",),
            )

    def test_score_revalidation_rejects_subclass_that_forges_source_slice_digest(self) -> None:
        canonical_slice = make_slice(
            evidence=("evidence:canonical",),
            provenance_digest="1" * 64,
        )
        projection = build_qubo_projection(
            projection_id="qubo:g2-score-exact-type-falsifier",
            world_slice=canonical_slice,
            expected_slice_sha256=canonical_slice.sha256(),
            expected_generation=7,
            variables=(make_variable(),),
            couplings=(),
            provenance_refs=("review:wp402-g2-score-exact-worldslice",),
        )

        forged = ForgedWorldSlice(
            slice_id=canonical_slice.slice_id,
            need_id=canonical_slice.need_id,
            cycle_id=canonical_slice.cycle_id,
            generation=canonical_slice.generation,
            vector_space_version=canonical_slice.vector_space_version,
            selected_atom_ids=canonical_slice.selected_atom_ids,
            selected_operator_ids=canonical_slice.selected_operator_ids,
            unresolved_target_atom_ids=canonical_slice.unresolved_target_atom_ids,
            tainted_atom_ids=canonical_slice.tainted_atom_ids,
            depth_reached=canonical_slice.depth_reached,
            stopped_reason=canonical_slice.stopped_reason,
            evidence_refs=("evidence:forged-different-from-canonical",),
            provenance_digest=projection.slice_sha256,
        )

        self.assertNotEqual(WorldSlice.sha256(forged), projection.slice_sha256)
        self.assertEqual(forged.sha256(), projection.slice_sha256)

        with self.assertRaisesRegex(QuboProjectionError, "WorldSlice"):
            score_assignment(
                projection=projection,
                world_slice=forged,
                assignment=(("x:a", 1),),
                expected_projection_sha256=projection.sha256(),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
