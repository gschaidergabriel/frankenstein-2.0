import pytest

from frankenstein2.qubo_projection import (
    QuboProjectionError,
    QuboVariable,
    compile_qubo_projection,
)
from frankenstein2.sparse_world_basis import WorldSlice


class ForgedWorldSlice(WorldSlice):
    """Adversarial subtype that forges the slice digest method."""

    def sha256(self) -> str:
        return "0" * 64


def test_wp402_rejects_worldslice_subclass_with_forged_digest() -> None:
    """Exact-source identity must not be forgeable through a WorldSlice subtype."""

    source_slice = ForgedWorldSlice(
        slice_id="slice:exact-type-falsifier",
        need_id="need:exact-type-falsifier",
        cycle_id="cycle:exact-type-falsifier",
        generation=7,
        vector_space_version="world-v1",
        selected_atom_ids=("atom:a",),
        selected_operator_ids=(),
        unresolved_target_atom_ids=(),
        tainted_atom_ids=(),
        depth_reached=0,
        stopped_reason="BOUNDED_FALSIFIER",
        evidence_refs=("evidence:exact-type-falsifier",),
        provenance_digest="1" * 64,
    )

    with pytest.raises(QuboProjectionError, match="exact WorldSlice"):
        compile_qubo_projection(
            source_slice=source_slice,
            projection_id="qubo:exact-type-falsifier",
            variables=(
                QuboVariable(
                    variable_id="x",
                    atom_id="atom:a",
                    linear_bias=1,
                ),
            ),
            couplings=(),
            provenance_refs=("review:wp402-exact-worldslice",),
        )
