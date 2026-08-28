import pytest

from frankenstein2.gwt_workspace import (
    GwtWorkspaceError,
    SelectedCandidate,
    WorkspaceSelection,
    create_broadcast,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64


def test_direct_selection_constructor_cannot_bypass_selection_policy_before_broadcast():
    """REVIEW_ONLY: broadcast must reject a selection with no proved producer/policy path."""
    forged_selected = SelectedCandidate(
        candidate_id="candidate:forged",
        candidate_sha256=D,
        payload_ref="payload:forged",
        epistemic_class="OBSERVED_EVIDENCE",
        provenance_refs=("prov:caller-only",),
        alternative_refs=(),
        score=10**18,
        estimated_cost_units=0,
    )
    forged_selection = WorkspaceSelection(
        selection_id="selection:forged",
        cycle_id="cycle:current",
        generation=7,
        frame_id="frame:current",
        frame_generation=4,
        frame_sha256=A,
        grid_plan_id="grid:current",
        grid_plan_generation=3,
        grid_plan_sha256=B,
        policy_id="policy:never-evaluated",
        policy_generation=999,
        policy_sha256=C,
        selected=(forged_selected,),
        deferred_candidate_ids=(),
    )

    # The object is shape-valid and can self-hash, but it never traversed
    # build_workspace_selection(), so no policy evaluation or candidate-origin check
    # produced it. A downstream broadcast boundary must not treat its self-digest as
    # proof of producer lineage.
    forged_digest = forged_selection.sha256()
    with pytest.raises(GwtWorkspaceError):
        create_broadcast(
            broadcast_id="broadcast:must-reject-forged-selection",
            generation=1,
            selection=forged_selection,
            expected_selection_sha256=forged_digest,
            recipient_cell_ids=("G1",),
        )
