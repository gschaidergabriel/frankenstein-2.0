from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.grid10_interface import CellBudget, Grid10Plan
from frankenstein2.gwt_workspace import (
    GWTWorkspaceError,
    SelectionPolicy,
    WorkspaceCandidate,
    create_broadcast,
    select_workspace,
)
from frankenstein2.hyperposition import Alternative, EpistemicStatus, create_hyperposition
from frankenstein2.situation_frame import EpistemicRef, SituationFrame


H64 = "a" * 64
P64 = "b" * 64


def make_frame(*, generation: int = 1, frame_id: str = "frame-1") -> SituationFrame:
    return SituationFrame.create(
        frame_id=frame_id,
        cycle_id="cycle-1",
        generation=generation,
        situation_epoch=3,
        agency_state_ref="agency-state-1",
        agency_state_generation=4,
        agency_state_sha256=H64,
        epistemic_refs=(EpistemicRef(kind="UNKNOWN", ref="unknown-1"),),
        unresolved_alternative_refs=("alt-a", "alt-b"),
        authority_scope_refs=("candidate-only",),
        provenance_refs=("frame-source",),
    )


def make_plan(frame: SituationFrame, *, max_total_work_units: int = 100) -> Grid10Plan:
    cells = tuple(
        CellBudget(
            cell_id=f"G{i}",
            role_label=f"role-{i}",
            max_input_refs=8,
            max_output_refs=8,
            max_work_units=20,
            max_reentry_depth=2,
        )
        for i in range(1, 11)
    )
    return Grid10Plan.create(
        plan_id="grid-plan-1",
        cycle_id=frame.cycle_id,
        generation=2,
        frame_id=frame.frame_id,
        frame_generation=frame.generation,
        frame_sha256=frame.sha256(),
        policy_id="grid-policy-1",
        policy_generation=1,
        policy_sha256=P64,
        cells=cells,
        max_total_work_units=max_total_work_units,
        provenance_refs=("grid-plan-source",),
    )


def make_policy(*, max_selected: int = 2, max_total_cost_units: int = 20) -> SelectionPolicy:
    return SelectionPolicy.create(
        policy_id="gwt-policy-1",
        generation=1,
        salience_weight=3,
        goal_relevance_weight=2,
        uncertainty_weight=1,
        information_gain_weight=4,
        cost_weight=1,
        max_selected=max_selected,
        max_total_cost_units=max_total_cost_units,
        provenance_refs=("policy-source",),
    )


def candidate(
    candidate_id: str,
    *,
    epistemic_class: str = "OBSERVATION",
    salience: int = 100,
    goal: int = 100,
    uncertainty: int = 100,
    info: int = 100,
    cost: int = 4,
) -> WorkspaceCandidate:
    return WorkspaceCandidate.create(
        candidate_id=candidate_id,
        payload_ref=f"payload:{candidate_id}",
        epistemic_class=epistemic_class,
        salience_micros=salience,
        goal_relevance_micros=goal,
        uncertainty_micros=uncertainty,
        information_gain_micros=info,
        cost_units=cost,
        provenance_refs=(f"source:{candidate_id}",),
    )


class GWTWorkspaceTests(unittest.TestCase):
    def test_selection_is_deterministic_and_ties_sort_by_candidate_id(self) -> None:
        frame = make_frame()
        plan = make_plan(frame)
        policy = make_policy(max_selected=2)
        a = candidate("a")
        b = candidate("b")
        c = candidate("c", salience=10, goal=10, uncertainty=10, info=10)

        first = select_workspace(
            selection_id="selection-1",
            frame=frame,
            plan=plan,
            policy=policy,
            candidates=(b, c, a),
            provenance_refs=("selection-source",),
        )
        second = select_workspace(
            selection_id="selection-1",
            frame=frame,
            plan=plan,
            policy=policy,
            candidates=(a, b, c),
            provenance_refs=("selection-source",),
        )

        self.assertEqual(tuple(item.candidate_id for item in first.selected), ("a", "b"))
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(first.classification, "WORKSPACE_SELECTION_CANDIDATE_COORDINATION_NOT_DECISION_OR_EFFECT_AUTHORITY")
        self.assertEqual(first.as_dict()["effect_authority"], "NONE")
        self.assertFalse(first.as_dict()["broadcast_uptake_claimed"])

    def test_unknown_and_conflict_remain_explicit_even_when_not_selected(self) -> None:
        frame = make_frame()
        plan = make_plan(frame)
        policy = make_policy(max_selected=1)
        observed = candidate("observed", salience=1_000, goal=1_000, info=1_000)
        unknown = candidate("unknown", epistemic_class="UNKNOWN", salience=1)
        conflict = candidate("conflict", epistemic_class="CONFLICT", salience=1)

        selection = select_workspace(
            selection_id="selection-unresolved",
            frame=frame,
            plan=plan,
            policy=policy,
            candidates=(conflict, observed, unknown),
            provenance_refs=("selection-source",),
        )

        self.assertEqual(selection.selected[0].candidate_id, "observed")
        self.assertEqual(selection.unresolved_candidate_ids, ("conflict", "unknown"))

    def test_duplicate_candidate_identity_fails_closed(self) -> None:
        frame = make_frame()
        plan = make_plan(frame)
        policy = make_policy()
        duplicate = candidate("dup")
        with self.assertRaisesRegex(GWTWorkspaceError, "duplicate candidate identity"):
            select_workspace(
                selection_id="selection-dup",
                frame=frame,
                plan=plan,
                policy=policy,
                candidates=(duplicate, duplicate),
                provenance_refs=("selection-source",),
            )

    def test_unsupported_epistemic_class_fails_closed(self) -> None:
        with self.assertRaisesRegex(GWTWorkspaceError, "epistemic_class"):
            candidate("bad", epistemic_class="FACT_IS_TRUE")

    def test_stale_situation_frame_binding_fails_closed(self) -> None:
        frame = make_frame(generation=1)
        plan = make_plan(frame)
        stale_replacement = make_frame(generation=2)
        with self.assertRaises(Exception):
            select_workspace(
                selection_id="selection-stale-frame",
                frame=stale_replacement,
                plan=plan,
                policy=make_policy(),
                candidates=(candidate("a"),),
                provenance_refs=("selection-source",),
            )

    def test_selection_budget_overflow_fails_instead_of_silent_truncation(self) -> None:
        frame = make_frame()
        plan = make_plan(frame)
        policy = make_policy(max_selected=2, max_total_cost_units=10)
        a = candidate("a", salience=900, cost=6)
        b = candidate("b", salience=800, cost=6)
        with self.assertRaisesRegex(GWTWorkspaceError, "selected set exceeds"):
            select_workspace(
                selection_id="selection-budget",
                frame=frame,
                plan=plan,
                policy=policy,
                candidates=(a, b),
                provenance_refs=("selection-source",),
            )

    def test_policy_cannot_claim_more_cost_than_grid_plan_budget(self) -> None:
        frame = make_frame()
        plan = make_plan(frame, max_total_work_units=5)
        policy = make_policy(max_total_cost_units=6)
        with self.assertRaisesRegex(GWTWorkspaceError, "policy cost budget exceeds"):
            select_workspace(
                selection_id="selection-plan-budget",
                frame=frame,
                plan=plan,
                policy=policy,
                candidates=(candidate("a", cost=1),),
                provenance_refs=("selection-source",),
            )

    def test_optional_hyperposition_is_exactly_bound_and_mismatch_is_rejected(self) -> None:
        frame = make_frame()
        plan = make_plan(frame)
        hp = create_hyperposition(
            hyperposition_id="hp-1",
            generation=1,
            alternatives=(
                Alternative(
                    alternative_id="alt-a",
                    proposition_ref="proposition-a",
                    generation=1,
                    epistemic_status=EpistemicStatus.UNKNOWN,
                    provenance_refs=("hp-source-a",),
                    uncertainty_micros=800_000,
                ),
                Alternative(
                    alternative_id="alt-b",
                    proposition_ref="proposition-b",
                    generation=1,
                    epistemic_status=EpistemicStatus.UNKNOWN,
                    provenance_refs=("hp-source-b",),
                    uncertainty_micros=700_000,
                ),
            ),
            provenance_refs=("hp-source",),
            situation_frame_ref=frame.frame_id,
        )
        selection = select_workspace(
            selection_id="selection-hp",
            frame=frame,
            plan=plan,
            policy=make_policy(max_selected=1),
            candidates=(candidate("unknown", epistemic_class="UNKNOWN"),),
            hyperposition=hp,
            provenance_refs=("selection-source",),
        )
        self.assertEqual(selection.hyperposition_id, hp.hyperposition_id)
        self.assertEqual(selection.hyperposition_generation, hp.generation)
        self.assertEqual(selection.hyperposition_sha256, hp.sha256())

        wrong_hp = create_hyperposition(
            hyperposition_id="hp-wrong",
            generation=1,
            alternatives=hp.alternatives,
            provenance_refs=("hp-source",),
            situation_frame_ref="another-frame",
        )
        with self.assertRaisesRegex(GWTWorkspaceError, "Hyperposition binding mismatch|hyperposition SituationFrame binding mismatch"):
            select_workspace(
                selection_id="selection-hp-wrong",
                frame=frame,
                plan=plan,
                policy=make_policy(max_selected=1),
                candidates=(candidate("unknown", epistemic_class="UNKNOWN"),),
                hyperposition=wrong_hp,
                provenance_refs=("selection-source",),
            )

    def test_broadcast_addresses_exactly_g1_through_g10_without_uptake_claim(self) -> None:
        frame = make_frame()
        plan = make_plan(frame)
        selection = select_workspace(
            selection_id="selection-broadcast",
            frame=frame,
            plan=plan,
            policy=make_policy(max_selected=1),
            candidates=(candidate("a"),),
            provenance_refs=("selection-source",),
        )
        envelope = create_broadcast(
            broadcast_id="broadcast-1",
            selection=selection,
            plan=plan,
            provenance_refs=("broadcast-source",),
        )
        self.assertEqual(envelope.recipient_cell_ids, tuple(f"G{i}" for i in range(1, 11)))
        self.assertFalse(envelope.as_dict()["delivery_observed"])
        self.assertFalse(envelope.as_dict()["uptake_observed"])
        self.assertEqual(envelope.as_dict()["effect_authority"], "NONE")

    def test_duplicate_or_missing_broadcast_recipients_fail_closed(self) -> None:
        frame = make_frame()
        plan = make_plan(frame)
        selection = select_workspace(
            selection_id="selection-broadcast-bad",
            frame=frame,
            plan=plan,
            policy=make_policy(max_selected=1),
            candidates=(candidate("a"),),
            provenance_refs=("selection-source",),
        )
        with self.assertRaisesRegex(GWTWorkspaceError, "duplicate recipients"):
            create_broadcast(
                broadcast_id="broadcast-dup",
                selection=selection,
                plan=plan,
                recipient_cell_ids=("G1", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"),
                provenance_refs=("broadcast-source",),
            )
        with self.assertRaisesRegex(GWTWorkspaceError, "each logical GRID10 cell"):
            create_broadcast(
                broadcast_id="broadcast-missing",
                selection=selection,
                plan=plan,
                recipient_cell_ids=tuple(f"G{i}" for i in range(1, 10)),
                provenance_refs=("broadcast-source",),
            )

    def test_broadcast_rejects_stale_grid_plan_digest(self) -> None:
        frame = make_frame()
        plan = make_plan(frame)
        selection = select_workspace(
            selection_id="selection-stale-plan",
            frame=frame,
            plan=plan,
            policy=make_policy(max_selected=1),
            candidates=(candidate("a"),),
            provenance_refs=("selection-source",),
        )
        mutated_plan = replace(plan, max_total_work_units=99)
        with self.assertRaisesRegex(GWTWorkspaceError, "plan digest mismatch"):
            create_broadcast(
                broadcast_id="broadcast-stale-plan",
                selection=selection,
                plan=mutated_plan,
                provenance_refs=("broadcast-source",),
            )


if __name__ == "__main__":
    unittest.main()
