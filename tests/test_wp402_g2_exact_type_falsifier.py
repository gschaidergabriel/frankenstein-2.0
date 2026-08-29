import unittest

from frankenstein2.qubo_projection import (
    QuboProjectionError,
    QuboVariable,
    build_qubo_projection,
    score_assignment,
)
from frankenstein2.sparse_world_basis import WorldSlice


class ForgedWorldSlice(WorldSlice):
    """Adversarial subtype that returns an attacker-selected digest."""

    def sha256(self) -> str:
        return "0" * 64


class WP402Generation2ExactTypeFalsifier(unittest.TestCase):
    def test_worldslice_subtype_cannot_self_attest_through_build_and_score(self) -> None:
        forged = ForgedWorldSlice(
            slice_id="slice:g2-exact-type-falsifier",
            need_id="need:g2-exact-type-falsifier",
            cycle_id="cycle:g2-exact-type-falsifier",
            generation=7,
            vector_space_version="vs:1",
            selected_atom_ids=("atom:a",),
            selected_operator_ids=(),
            unresolved_target_atom_ids=(),
            tainted_atom_ids=(),
            depth_reached=0,
            stopped_reason="BOUNDED_FALSIFIER",
            evidence_refs=("evidence:g2-exact-type-falsifier",),
            provenance_digest="1" * 64,
        )
        self.assertEqual(forged.sha256(), "0" * 64)
        variable = QuboVariable(
            variable_id="x:a",
            source_ref="atom:a",
            linear_bias=1,
            provenance_refs=("review:g2-exact-type-falsifier",),
        )

        with self.assertRaisesRegex(QuboProjectionError, "exact WorldSlice"):
            projection = build_qubo_projection(
                projection_id="qubo:g2-exact-type-falsifier",
                world_slice=forged,
                expected_slice_sha256="0" * 64,
                expected_generation=7,
                variables=(variable,),
                couplings=(),
                offset=0,
                provenance_refs=("review:g2-exact-type-falsifier",),
            )
            score_assignment(
                projection=projection,
                world_slice=forged,
                assignment=(("x:a", 1),),
                expected_projection_sha256=projection.sha256(),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
