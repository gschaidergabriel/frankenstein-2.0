import pytest

from frankenstein2.grid10_interface import CellBudget, CellInput, CellOutput, Grid10Plan
from frankenstein2.hyperposition import Alternative, EpistemicStatus, create_hyperposition
from frankenstein2.gwt_workspace import (
    BroadcastEnvelope,
    CandidateProducerAdmission,
    GwtWorkspaceError,
    SelectedCandidate,
    SelectionPolicy,
    WorkspaceCandidate,
    WorkspaceSelection,
    build_workspace_selection,
    create_broadcast,
    verify_selection_binding,
)

D = "a" * 64
F = "c" * 64
G = "e" * 64
FORGED_SELECTION_SHA256 = "f" * 64


class SelfAttestingWorkspaceSelection(WorkspaceSelection):
    """Adversarial subtype that overrides the public digest method."""

    def sha256(self) -> str:
        return FORGED_SELECTION_SHA256


def make_grid_plan(*, plan_id="grid-plan-1", generation=3):
    cells = tuple(
        CellBudget(
            cell_id=f"G{i}",
            role_label=f"role-{i}",
            max_input_refs=8,
            max_output_refs=8,
            max_work_units=8,
            max_reentry_depth=2,
        )
        for i in range(1, 11)
    )
    return Grid10Plan.create(
        plan_id=plan_id,
        cycle_id="cycle-1",
        generation=generation,
        frame_id="frame-1",
        frame_generation=4,
        frame_sha256=D,
        policy_id="grid-policy-1",
        policy_generation=1,
        policy_sha256=G,
        cells=cells,
        max_total_work_units=80,
        provenance_refs=(f"prov:{plan_id}",),
    )


GRID_PLAN = make_grid_plan()


def producer_admission(
    producer_id,
    *,
    payload_ref=None,
    plan=GRID_PLAN,
    cell_id="G1",
    output_refs=None,
):
    payload = payload_ref or f"payload:{producer_id}"
    cell_input = CellInput.for_plan(
        plan,
        cell_id=cell_id,
        work_units_requested=2,
        input_refs=(f"input:{producer_id}",),
        provenance_refs=(f"input-prov:{producer_id}",),
    )
    cell_output = CellOutput.for_input(
        plan,
        cell_input,
        status="COMPLETE",
        work_units_used=1,
        output_refs=tuple(output_refs) if output_refs is not None else (payload,),
        evidence_refs=(f"evidence:{producer_id}",),
        provenance_refs=(f"output-prov:{producer_id}",),
    )
    return CandidateProducerAdmission(
        plan=plan,
        cell_input=cell_input,
        cell_output=cell_output,
    )


def candidate(
    candidate_id,
    *,
    epistemic="INFERRED",
    salience=500_000,
    goal=500_000,
    uncertainty=100_000,
    info=500_000,
    cost=1,
    alternatives=(),
    payload_ref=None,
    admission=None,
):
    payload = payload_ref or f"payload:{candidate_id}"
    producer = admission or producer_admission(candidate_id, payload_ref=payload)
    return WorkspaceCandidate(
        candidate_id=candidate_id,
        payload_ref=payload,
        epistemic_class=epistemic,
        provenance_refs=(f"prov:{candidate_id}",),
        salience_micros=salience,
        goal_relevance_micros=goal,
        uncertainty_micros=uncertainty,
        information_gain_micros=info,
        estimated_cost_units=cost,
        alternative_refs=alternatives,
        producer_admission=producer,
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
        grid_plan_id=GRID_PLAN.plan_id,
        grid_plan_generation=GRID_PLAN.generation,
        grid_plan_sha256=GRID_PLAN.sha256(),
        policy=p or policy(),
        candidates=tuple(candidates),
    )


def selection_subtype(value: WorkspaceSelection) -> WorkspaceSelection:
    return SelfAttestingWorkspaceSelection(
        selection_id=value.selection_id,
        cycle_id=value.cycle_id,
        generation=value.generation,
        frame_id=value.frame_id,
        frame_generation=value.frame_generation,
        frame_sha256=value.frame_sha256,
        grid_plan_id=value.grid_plan_id,
        grid_plan_generation=value.grid_plan_generation,
        grid_plan_sha256=value.grid_plan_sha256,
        policy_id=value.policy_id,
        policy_generation=value.policy_generation,
        policy_sha256=value.policy_sha256,
        selected=value.selected,
        deferred_candidate_ids=value.deferred_candidate_ids,
        hyperposition_id=value.hyperposition_id,
        hyperposition_generation=value.hyperposition_generation,
        hyperposition_sha256=value.hyperposition_sha256,
        hyperposition=value.hyperposition,
        selection_policy=value.selection_policy,
        source_candidates=value.source_candidates,
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
        grid_plan_id=GRID_PLAN.plan_id,
        grid_plan_generation=GRID_PLAN.generation,
        grid_plan_sha256=GRID_PLAN.sha256(),
    )
    with pytest.raises(GwtWorkspaceError, match="frame digest mismatch"):
        verify_selection_binding(
            value,
            expected_generation=7,
            expected_selection_sha256=value.sha256(),
            frame_id="frame-1",
            frame_generation=4,
            frame_sha256="d" * 64,
            grid_plan_id=GRID_PLAN.plan_id,
            grid_plan_generation=GRID_PLAN.generation,
            grid_plan_sha256=GRID_PLAN.sha256(),
        )


def test_verify_selection_binding_rejects_digest_self_attesting_subtype():
    canonical = selection((candidate("subtype-verify"),))
    adversarial = selection_subtype(canonical)
    assert type(adversarial) is SelfAttestingWorkspaceSelection
    assert adversarial.sha256() == FORGED_SELECTION_SHA256
    assert canonical.sha256() != FORGED_SELECTION_SHA256
    with pytest.raises(GwtWorkspaceError, match="concrete WorkspaceSelection"):
        verify_selection_binding(
            adversarial,
            expected_generation=adversarial.generation,
            expected_selection_sha256=FORGED_SELECTION_SHA256,
            frame_id=GRID_PLAN.frame_id,
            frame_generation=GRID_PLAN.frame_generation,
            frame_sha256=GRID_PLAN.frame_sha256,
            grid_plan_id=GRID_PLAN.plan_id,
            grid_plan_generation=GRID_PLAN.generation,
            grid_plan_sha256=GRID_PLAN.sha256(),
        )


def test_create_broadcast_rejects_digest_self_attesting_selection_subtype():
    canonical = selection((candidate("subtype-broadcast"),))
    adversarial = selection_subtype(canonical)
    with pytest.raises(GwtWorkspaceError, match="concrete WorkspaceSelection"):
        create_broadcast(
            broadcast_id="b-subtype",
            generation=1,
            selection=adversarial,
            expected_selection_sha256=FORGED_SELECTION_SHA256,
            recipient_cell_ids=("G1",),
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
    assert broadcast.plan_id == GRID_PLAN.plan_id
    assert broadcast.plan_generation == GRID_PLAN.generation
    assert broadcast.plan_sha256 == GRID_PLAN.sha256()
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


def test_broadcast_preserves_candidate_to_payload_pairing_in_selection_order():
    a = candidate("z-id", payload_ref="payload:a", salience=900_000, goal=0, uncertainty=0, info=0)
    b = candidate("a-id", payload_ref="payload:z", salience=100_000, goal=0, uncertainty=0, info=0)
    value = selection(
        (b, a),
        p=policy(
            goal_relevance_weight=0,
            uncertainty_weight=0,
            information_gain_weight=0,
            cost_weight=0,
        ),
    )
    broadcast = create_broadcast(
        broadcast_id="b-pair",
        generation=1,
        selection=value,
        expected_selection_sha256=value.sha256(),
        recipient_cell_ids=("G1",),
    )
    assert list(zip(broadcast.candidate_ids, broadcast.candidate_payload_refs)) == [
        ("z-id", "payload:a"),
        ("a-id", "payload:z"),
    ]


def test_candidate_without_exact_producer_admission_fails_closed():
    foreign = WorkspaceCandidate(
        candidate_id="foreign",
        payload_ref="payload:foreign",
        epistemic_class="INFERRED",
        provenance_refs=("prov:caller-only",),
        salience_micros=500_000,
        goal_relevance_micros=500_000,
        uncertainty_micros=0,
        information_gain_micros=500_000,
        estimated_cost_units=1,
    )
    with pytest.raises(GwtWorkspaceError, match="producer_admission"):
        selection((foreign,))


def test_foreign_grid10_producer_plan_fails_closed():
    foreign_plan = make_grid_plan(plan_id="grid-plan-foreign", generation=3)
    admission = producer_admission("foreign", plan=foreign_plan)
    foreign = candidate("foreign", admission=admission)
    with pytest.raises(GwtWorkspaceError, match="producer GRID10 plan binding mismatch"):
        selection((foreign,))


def test_candidate_payload_must_be_one_of_exact_producer_output_refs():
    admission = producer_admission(
        "source-a",
        payload_ref="payload:actual",
        output_refs=("payload:actual",),
    )
    forged = candidate(
        "forged",
        payload_ref="payload:not-produced",
        admission=admission,
    )
    with pytest.raises(GwtWorkspaceError, match="not present in producer output_refs"):
        selection((forged,))


def test_alias_ids_cannot_amplify_one_producer_output_payload_pair():
    shared = producer_admission("shared", payload_ref="payload:shared")
    first = candidate("alias-a", payload_ref="payload:shared", admission=shared)
    second = candidate("alias-b", payload_ref="payload:shared", admission=shared)
    with pytest.raises(GwtWorkspaceError, match="alias amplification"):
        selection((first, second))


def test_direct_workspace_selection_constructor_cannot_bypass_builder_lineage_before_broadcast():
    forged_selected = SelectedCandidate(
        candidate_id="candidate:forged",
        candidate_sha256="d" * 64,
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
        frame_sha256=D,
        grid_plan_id=GRID_PLAN.plan_id,
        grid_plan_generation=GRID_PLAN.generation,
        grid_plan_sha256=GRID_PLAN.sha256(),
        policy_id="policy:never-evaluated",
        policy_generation=999,
        policy_sha256="b" * 64,
        selected=(forged_selected,),
        deferred_candidate_ids=(),
    )
    with pytest.raises(GwtWorkspaceError, match="builder policy/candidate lineage"):
        create_broadcast(
            broadcast_id="broadcast:must-reject-forged-selection",
            generation=1,
            selection=forged_selection,
            expected_selection_sha256=forged_selection.sha256(),
            recipient_cell_ids=("G1",),
        )


@pytest.mark.parametrize(
    ("field", "foreign_value", "message"),
    (
        ("cycle_id", "cycle-foreign", "producer cycle binding mismatch"),
        ("frame_id", "frame-foreign", "producer SituationFrame binding mismatch"),
        ("frame_generation", 999, "producer SituationFrame binding mismatch"),
        ("frame_sha256", "d" * 64, "producer SituationFrame binding mismatch"),
    ),
)
def test_selection_requires_exact_producer_cycle_and_situation_frame_binding(
    field, foreign_value, message
):
    source = candidate("bound-envelope")
    kwargs = dict(
        selection_id="sel-envelope",
        cycle_id=GRID_PLAN.cycle_id,
        generation=7,
        frame_id=GRID_PLAN.frame_id,
        frame_generation=GRID_PLAN.frame_generation,
        frame_sha256=GRID_PLAN.frame_sha256,
        grid_plan_id=GRID_PLAN.plan_id,
        grid_plan_generation=GRID_PLAN.generation,
        grid_plan_sha256=GRID_PLAN.sha256(),
        policy=policy(),
        candidates=(source,),
    )
    kwargs[field] = foreign_value
    with pytest.raises(GwtWorkspaceError, match=message):
        build_workspace_selection(**kwargs)


def test_selected_candidate_retains_exact_producer_digest_binding():
    source = candidate("bound")
    value = selection((source,))
    selected = value.selected[0]
    assert selected.producer_admission_sha256 == source.producer_admission.sha256()
    assert selected.producer_output_sha256 == source.producer_admission.output_sha256
    assert selected.producer_cell_id == source.producer_admission.cell_id


def make_hyperposition(*, frame_ref="frame-1", frame_generation=4, frame_sha256=D):
    return create_hyperposition(
        hyperposition_id="hyper-bound",
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
        provenance_refs=("prov:hp",),
        situation_frame_ref=frame_ref,
        situation_frame_generation=frame_generation,
        situation_frame_sha256=frame_sha256,
    )


def test_hyperposition_digest_triple_without_object_fails_closed():
    foreign = make_hyperposition(frame_ref="frame-foreign")
    with pytest.raises(GwtWorkspaceError, match="hyperposition object required.*frame"):
        build_workspace_selection(
            selection_id="sel-cross-frame-legacy",
            cycle_id="cycle-1",
            generation=7,
            frame_id="frame-1",
            frame_generation=4,
            frame_sha256=D,
            grid_plan_id=GRID_PLAN.plan_id,
            grid_plan_generation=GRID_PLAN.generation,
            grid_plan_sha256=GRID_PLAN.sha256(),
            hyperposition_id=foreign.hyperposition_id,
            hyperposition_generation=foreign.generation,
            hyperposition_sha256=foreign.sha256(),
            policy=policy(),
            candidates=(candidate("hp-legacy"),),
        )


def test_cross_frame_hyperposition_object_fails_closed():
    foreign = make_hyperposition(frame_ref="frame-foreign")
    with pytest.raises(GwtWorkspaceError, match="hyperposition situation frame binding mismatch"):
        build_workspace_selection(
            selection_id="sel-cross-frame-object",
            cycle_id="cycle-1",
            generation=7,
            frame_id="frame-1",
            frame_generation=4,
            frame_sha256=D,
            grid_plan_id=GRID_PLAN.plan_id,
            grid_plan_generation=GRID_PLAN.generation,
            grid_plan_sha256=GRID_PLAN.sha256(),
            hyperposition=foreign,
            policy=policy(),
            candidates=(candidate("hp-foreign"),),
        )


def test_matching_hyperposition_object_binds_exact_frame_and_digest():
    bound = make_hyperposition(frame_ref="frame-1")
    value = build_workspace_selection(
        selection_id="sel-hp-bound",
        cycle_id="cycle-1",
        generation=7,
        frame_id="frame-1",
        frame_generation=4,
        frame_sha256=D,
        grid_plan_id=GRID_PLAN.plan_id,
        grid_plan_generation=GRID_PLAN.generation,
        grid_plan_sha256=GRID_PLAN.sha256(),
        hyperposition=bound,
        policy=policy(),
        candidates=(candidate("hp-bound"),),
    )
    assert value.hyperposition_id == bound.hyperposition_id
    assert value.hyperposition_generation == bound.generation
    assert value.hyperposition_sha256 == bound.sha256()
    assert value.as_dict()["hyperposition"]["situation_frame_ref"] == "frame-1"
    create_broadcast(
        broadcast_id="b-hp-bound",
        generation=1,
        selection=value,
        expected_selection_sha256=value.sha256(),
        recipient_cell_ids=("G1",),
    )


def test_same_frame_id_stale_hyperposition_version_fails_closed():
    stale = make_hyperposition(
        frame_ref="frame-1",
        frame_generation=3,
        frame_sha256="b" * 64,
    )
    with pytest.raises(GwtWorkspaceError, match="hyperposition situation frame binding mismatch"):
        build_workspace_selection(
            selection_id="sel-stale-hp-frame-version",
            cycle_id="cycle-1",
            generation=7,
            frame_id="frame-1",
            frame_generation=4,
            frame_sha256=D,
            grid_plan_id=GRID_PLAN.plan_id,
            grid_plan_generation=GRID_PLAN.generation,
            grid_plan_sha256=GRID_PLAN.sha256(),
            hyperposition=stale,
            policy=policy(),
            candidates=(candidate("hp-stale-version"),),
        )


def test_matching_hyperposition_frame_version_survives_downstream_revalidation():
    bound = make_hyperposition(
        frame_ref="frame-1",
        frame_generation=4,
        frame_sha256=D,
    )
    value = build_workspace_selection(
        selection_id="sel-exact-hp-frame-version",
        cycle_id="cycle-1",
        generation=7,
        frame_id="frame-1",
        frame_generation=4,
        frame_sha256=D,
        grid_plan_id=GRID_PLAN.plan_id,
        grid_plan_generation=GRID_PLAN.generation,
        grid_plan_sha256=GRID_PLAN.sha256(),
        hyperposition=bound,
        policy=policy(),
        candidates=(candidate("hp-exact-version"),),
    )
    payload = value.as_dict()["hyperposition"]
    assert payload["situation_frame_ref"] == "frame-1"
    assert payload["situation_frame_generation"] == 4
    assert payload["situation_frame_sha256"] == D
    create_broadcast(
        broadcast_id="b-exact-hp-frame-version",
        generation=1,
        selection=value,
        expected_selection_sha256=value.sha256(),
        recipient_cell_ids=("G1",),
    )


def test_selected_candidate_subtype_cannot_split_serialized_and_consumed_lineage():
    canonical = selection((candidate("nested-subtype"),))
    original = canonical.selected[0]

    class ForgedSelectedCandidate(SelectedCandidate):
        def as_dict(self):
            payload = super().as_dict()
            payload["payload_ref"] = "payload:nested-subtype"
            return payload

    forged_item = ForgedSelectedCandidate(
        candidate_id=original.candidate_id,
        candidate_sha256=original.candidate_sha256,
        payload_ref="payload:forged",
        epistemic_class=original.epistemic_class,
        provenance_refs=original.provenance_refs,
        alternative_refs=original.alternative_refs,
        score=original.score,
        estimated_cost_units=original.estimated_cost_units,
        producer_admission_sha256=original.producer_admission_sha256,
        producer_cell_id=original.producer_cell_id,
        producer_output_sha256=original.producer_output_sha256,
    )
    assert forged_item.payload_ref == "payload:forged"
    assert forged_item.as_dict()["payload_ref"] == "payload:nested-subtype"
    with pytest.raises(GwtWorkspaceError, match="concrete SelectedCandidate"):
        WorkspaceSelection(
            selection_id=canonical.selection_id,
            cycle_id=canonical.cycle_id,
            generation=canonical.generation,
            frame_id=canonical.frame_id,
            frame_generation=canonical.frame_generation,
            frame_sha256=canonical.frame_sha256,
            grid_plan_id=canonical.grid_plan_id,
            grid_plan_generation=canonical.grid_plan_generation,
            grid_plan_sha256=canonical.grid_plan_sha256,
            policy_id=canonical.policy_id,
            policy_generation=canonical.policy_generation,
            policy_sha256=canonical.policy_sha256,
            selected=(forged_item,),
            deferred_candidate_ids=canonical.deferred_candidate_ids,
            hyperposition_id=canonical.hyperposition_id,
            hyperposition_generation=canonical.hyperposition_generation,
            hyperposition_sha256=canonical.hyperposition_sha256,
            hyperposition=canonical.hyperposition,
            selection_policy=canonical.selection_policy,
            source_candidates=canonical.source_candidates,
        )
