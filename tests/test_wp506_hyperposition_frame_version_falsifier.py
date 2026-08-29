"""Review-only falsifier for exact Hyperposition -> SituationFrame version binding.

This file does not mutate WP506 implementation authority.  It tests a dependency
required by the repaired WP506 boundary: a Hyperposition that names a SituationFrame
must carry enough immutable identity to distinguish two generations/digests that reuse
the same frame_id.

A failing test is the expected pre-repair result and is bounded repository-component
negative evidence only.  It grants no runtime, physical GRID10, GWT uptake, effect,
training, completion, EntityOS/HCU, or whole-system credit.
"""

from frankenstein2.hyperposition import Alternative, EpistemicStatus, create_hyperposition


STALE_FRAME_SHA256 = "b" * 64
STALE_FRAME_GENERATION = 3


def _hyperposition_from_stale_same_id_frame():
    """Construct the strongest stale witness representable by the current WP502 ABI.

    The external witness says this Hyperposition came from frame-1 generation 3 with
    STALE_FRAME_SHA256.  The current constructor only accepts situation_frame_ref, so
    this provenance cannot be encoded into the canonical Hyperposition identity unless
    the ABI exposes explicit version/digest fields.
    """

    return create_hyperposition(
        hyperposition_id="hyper-stale-same-frame-id",
        generation=2,
        alternatives=(
            Alternative(
                alternative_id="alt-a",
                proposition_ref="prop:a",
                generation=2,
                epistemic_status=EpistemicStatus.UNKNOWN,
                provenance_refs=("prov:hp:a",),
            ),
            Alternative(
                alternative_id="alt-b",
                proposition_ref="prop:b",
                generation=2,
                epistemic_status=EpistemicStatus.UNKNOWN,
                provenance_refs=("prov:hp:b",),
            ),
        ),
        provenance_refs=("prov:hp:stale-frame-generation-3",),
        situation_frame_ref="frame-1",
    )


def test_hyperposition_carries_exact_situation_frame_generation_and_digest():
    """Same frame_id must not collapse distinct SituationFrame versions.

    WP506 now checks Hyperposition.situation_frame_ref == WorkspaceSelection.frame_id.
    That closes cross-frame-id substitution, but it cannot reject an object derived from
    an older generation/digest when the frame_id is reused unless the Hyperposition's
    canonical identity also carries those exact frame-version fields.
    """

    hyperposition = _hyperposition_from_stale_same_id_frame()
    payload = hyperposition.as_dict()

    assert payload.get("situation_frame_ref") == "frame-1"
    assert payload.get("situation_frame_generation") == STALE_FRAME_GENERATION
    assert payload.get("situation_frame_sha256") == STALE_FRAME_SHA256
