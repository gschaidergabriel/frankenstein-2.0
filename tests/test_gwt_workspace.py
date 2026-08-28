import pytest

from frankenstein2.gwt_workspace import (
    BroadcastEnvelope,
    GwtWorkspaceError,
    SelectionPolicy,
    WorkspaceCandidate,
    build_workspace_selection,
    create_broadcast,
    verify_selection_binding,
)

D = "a" * 64
E = "b" * 64
F = "c" * 64


def candidate(candidate_id, *, epistemic="INFERRED", salience=500_000, goal=500_000, uncertainty=100_000, info=500_000, cost=1, alternatives=()):
    return WorkspaceCandidate(
        candidate_id=candidate_id,
        payload_ref=f"payload:{candidate_id}",
        epistemic_class=epistemic,
        provenance_refs=(f"prov:{candidate_id}",),
        salience_micros=salience,
        goal_relevance_micros=goal,
        uncertainty_micros=uncertainty,
        information_gain_micros=info,
        estimated_cost_units=cost,
        alternative_refs=alternatives,
    )


def policy(**kw):
    values = dict(
        policy_id="gwt-policy-1",
        generation=1,
        max_selected_candidates=3,
        max_total_cost_units=5,
        salience_weight=1,
        goal_relevance_weight=1,
        uncertainty_weight=1,
        information_gain_weight=1,
        cost_weight=1,
    )
    values.update(kw)
    return SelectionPolicy(**values)


def selection(candidates, *, p=None):
    return build_workspace_selection(
        selection_id="sel-1",
        cycle_id="cycle-1",
        generation=7,
        frame_id="frame-1",
        frame_generation=4,
        frame_sha256=D,
        grid_plan_id="grid-plan-1",
        grid_plan_generation=3,
        grid_plan_sha256=E,
        hyperposition_id="hyper-1",
        hyperposition_generation=2,
        hyperposition_sha256=F,
        policy=p or policy(),
        candidates=tuple(candidates),
    )


def test_selection_is_deterministic_and_ties_break_by_candidate_id():
    a = candidate("a")
    b = candidate("b")
    first = selection((b, a))
    second = selection((a, b))
    assert [x.candidate_id for x in first.selected] == ["a", "b"]
    assert first.sha256() == second.sha256()


def test_duplicate_candidate_identity_fails_closed():
    a = candidate("a")
    with pytest.raises(GwtWorkspaceError, match="duplicate candidate_id"):
        selection((a, a))


def test_unsupported_epistemic_class_fails_closed():
    with pytest.raises(GwtWorkspaceError, match="unsupported epistemic_class"):
        candidate("bad", epistemic="TRUTH")


def test_unknown_and_conflict_are_preserved_not_promoted():
    unknown = candidate("u", epistemic="UNKNOWN")
    conflict = candidate("c", epistemic="CONFLICT", alternatives=("alt:a", "alt:b"))
    value = selection((unknown, conflict))
    by_id = {item.candidate_id: item for item in value.selected}
    assert by_id["u"].epistemic_class == "UNKNOWN"
    assert by_id["c"].epistemic_class == "CONFLICT"
    assert by_id["c"].alternative_refs == ("alt:a", "alt:b")
    assert value.as_dict()["truth_authority"] == "NONE"


def test_not_computed_cannot_carry_computed_scores():
    with pytest.raises(GwtWorkspaceError, match="NOT_COMPUTED"):
        candidate("nc", epistemic="NOT_COMPUTED")


def test_total_budget_defers_lower_ranked_candidate_without_overrun():
    p = policy(max_selected_candidates=3, max_total_cost_units=3, cost_weight=0)
    high = candidate("high", salience=900_000, cost=2)
    low = candidate("low", salience=100_000, cost=2)
    value = selection((low, high), p=p)
    assert [x.candidate_id for x in value.selected] == ["high"]
    assert value.deferred_candidate_ids == ("low",)
    assert sum(x.estimated_cost_units for x in value.selected) <= 3


def test_single_candidate_cost_above_policy_budget_fails_closed():
    with pytest.raises(GwtWorkspaceError, match="estimated cost exceeds"):
        selection((candidate("huge", cost=6),), p=policy(max_total_cost_units=5))


def test_binding_rejects_stale_frame_or_grid_identity():
    value = selection((candidate("a"),))
    verify_selection_binding(
        value,
        expected_generation=7,
        expected_selection_sha256=value.sha256(),
        frame_id="frame-1",
        frame_generation=4,
        frame_sha256=D,
        grid_plan_id="grid-plan-1",
        grid_plan_generation=3,
        grid_plan_sha256=E,
    )
    with pytest.raises(GwtWorkspaceError, match="frame digest mismatch"):
        verify_selection_binding(
            value,
            expected_generation=7,
            expected_selection_sha256=value.sha256(),
            frame_id="frame-1",
            frame_generation=4,
            frame_sha256="d" * 64,
            grid_plan_id="grid-plan-1",
            grid_plan_generation=3,
            grid_plan_sha256=E,
        )


def test_broadcast_rejects_duplicate_or_unknown_recipient_ids():
    value = selection((candidate("a"),))
    with pytest.raises(GwtWorkspaceError, match="must not contain duplicates"):
        create_broadcast(
            broadcast_id="b-1",
            generation=1,
            selection=value,
            expected_selection_sha256=value.sha256(),
            recipient_cell_ids=("G1", "G1"),
        )
    with pytest.raises(GwtWorkspaceError, match="logical G1..G10"):
        create_broadcast(
            broadcast_id="b-1",
            generation=1,
            selection=value,
            expected_selection_sha256=value.sha256(),
            recipient_cell_ids=("G11",),
        )


def test_broadcast_is_explicit_offer_not_uptake_or_effect_authority():
    value = selection((candidate("a"), candidate("b")))
    broadcast = create_broadcast(
        broadcast_id="b-1",
        generation=1,
        selection=value,
        expected_selection_sha256=value.sha256(),
        recipient_cell_ids=("G10", "G1"),
    )
    assert isinstance(broadcast, BroadcastEnvelope)
    assert broadcast.recipient_cell_ids == ("G1", "G10")
    payload = broadcast.as_dict()
    assert payload["delivery_state"] == "OFFERED_NOT_ACKED"
    assert payload["uptake_observed"] is False
    assert payload["causal_influence_observed"] is False
    assert payload["effect_authority"] == "NONE"


def test_broadcast_rejects_forged_selection_digest():
    value = selection((candidate("a"),))
    with pytest.raises(GwtWorkspaceError, match="selection digest mismatch"):
        create_broadcast(
            broadcast_id="b-1",
            generation=1,
            selection=value,
            expected_selection_sha256="d" * 64,
            recipient_cell_ids=("G1",),
        )


def test_broadcast_preserves_candidate_id_payload_pairing():
    first = WorkspaceCandidate(
        candidate_id="a",
        payload_ref="payload:z",
        epistemic_class="INFERRED",
        provenance_refs=("prov:a",),
        salience_micros=500_000,
        goal_relevance_micros=500_000,
        uncertainty_micros=100_000,
        information_gain_micros=500_000,
        estimated_cost_units=1,
    )
    second = WorkspaceCandidate(
        candidate_id="b",
        payload_ref="payload:y",
        epistemic_class="INFERRED",
        provenance_refs=("prov:b",),
        salience_micros=500_000,
        goal_relevance_micros=500_000,
        uncertainty_micros=100_000,
        information_gain_micros=500_000,
        estimated_cost_units=1,
    )
    value = selection((first, second))
    broadcast = create_broadcast(
        broadcast_id="pair-binding-falsifier",
        generation=1,
        selection=value,
        expected_selection_sha256=value.sha256(),
        recipient_cell_ids=("G1",),
    )
    expected_pairs = tuple((item.candidate_id, item.payload_ref) for item in value.selected)
    observed_pairs = tuple(zip(broadcast.candidate_ids, broadcast.candidate_payload_refs))
    assert observed_pairs == expected_pairs
