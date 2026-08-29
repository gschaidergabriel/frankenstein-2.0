"""Regression for exact Hyperposition -> SituationFrame version binding.

Derived from review-only PR #207. The pre-repair executable result showed that a reused
frame_id collapsed distinct SituationFrame generations/digests. The repaired ABI requires
the external witness to be supplied explicitly and carries it in canonical identity.
"""

from frankenstein2.hyperposition import Alternative, EpistemicStatus, create_hyperposition


STALE_FRAME_SHA256 = "b" * 64
STALE_FRAME_GENERATION = 3


def _hyperposition_from_stale_same_id_frame():
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
        situation_frame_generation=STALE_FRAME_GENERATION,
        situation_frame_sha256=STALE_FRAME_SHA256,
    )


def test_hyperposition_carries_exact_situation_frame_generation_and_digest():
    hyperposition = _hyperposition_from_stale_same_id_frame()
    payload = hyperposition.as_dict()
    assert payload.get("situation_frame_ref") == "frame-1"
    assert payload.get("situation_frame_generation") == STALE_FRAME_GENERATION
    assert payload.get("situation_frame_sha256") == STALE_FRAME_SHA256
