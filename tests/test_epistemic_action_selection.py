#!/usr/bin/env python3
"""Deterministic falsification suite for F2-WP-504 epistemic action selection."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from frankenstein2.epistemic_action_selection import (
    EpistemicActionCandidate,
    EpistemicActionSelectionError,
    select_epistemic_action,
)
from frankenstein2.grid10_interface import CellBudget, Grid10Plan
from frankenstein2.hyperposition import (
    Alternative,
    EpistemicStatus,
    create_discriminator_candidate,
    create_hyperposition,
)


FRAME_SHA = "1" * 64
POLICY_SHA = "2" * 64


def hyperposition():
    return create_hyperposition(
        hyperposition_id="hyper:selection",
        generation=4,
        alternatives=(
            Alternative(
                alternative_id="alt:a",
                proposition_ref="hypothesis:a",
                generation=4,
                epistemic_status=EpistemicStatus.INFERRED,
                provenance_refs=("source:test",),
                support_refs=("evidence:a",),
                score_micros=500_000,
                uncertainty_micros=500_000,
            ),
            Alternative(
                alternative_id="alt:b",
                proposition_ref="hypothesis:b",
                generation=4,
                epistemic_status=EpistemicStatus.UNKNOWN,
                provenance_refs=("source:test",),
                support_refs=(),
                score_micros=None,
                uncertainty_micros=800_000,
            ),
        ),
        provenance_refs=("source:test",),
        situation_frame_ref="frame:4",
        policy_ref="policy:4",
    )


def grid_plan(*, cell_work: int = 20, total_work: int = 100):
    cells = tuple(
        CellBudget(
            cell_id=f"G{i}",
            role_label=f"role:{i}",
            max_input_refs=8,
            max_output_refs=8,
            max_work_units=cell_work,
            max_reentry_depth=2,
        )
        for i in range(1, 11)
    )
    return Grid10Plan.create(
        plan_id="grid:plan:4",
        cycle_id="cycle:4",
        generation=4,
        frame_id="frame:4",
        frame_generation=4,
        frame_sha256=FRAME_SHA,
        policy_id="policy:4",
        policy_generation=4,
        policy_sha256=POLICY_SHA,
        cells=cells,
        max_total_work_units=total_work,
        provenance_refs=("source:test",),
    )


def discriminator(
    hp,
    discriminator_id: str,
    *,
    gain: int,
    cost: int,
    targets=("alt:a", "alt:b"),
):
    return create_discriminator_candidate(
        state=hp,
        expected_generation=hp.generation,
        expected_state_sha256=hp.sha256(),
        discriminator_id=discriminator_id,
        target_alternative_ids=tuple(targets),
        evidence_need_ref=f"need:{discriminator_id}",
        expected_information_gain_micros=gain,
        estimated_cost_micros=cost,
        provenance_refs=("source:test",),
    )


def candidate(
    hp,
    candidate_id: str,
    *,
    gain: int,
    cost: int,
    work: int = 5,
    cell_id: str = "G1",
):
    return EpistemicActionCandidate(
        candidate_id=candidate_id,
        action_ref=f"action:{candidate_id}",
        cell_id=cell_id,
        work_units_requested=work,
        discriminator=discriminator(
            hp,
            f"disc:{candidate_id}",
            gain=gain,
            cost=cost,
        ),
        provenance_refs=("source:test",),
    )


def select(hp, plan, candidates):
    return select_epistemic_action(
        proposal_id="proposal:1",
        state=hp,
        expected_hyperposition_generation=hp.generation,
        expected_hyperposition_sha256=hp.sha256(),
        plan=plan,
        expected_plan_generation=plan.generation,
        expected_plan_sha256=plan.sha256(),
        candidates=tuple(candidates),
        provenance_refs=("source:test",),
    )


class EpistemicActionSelectionTests(unittest.TestCase):
    def test_max_information_gain_wins_as_proposal_only(self):
        hp = hyperposition()
        plan = grid_plan()
        proposal = select(
            hp,
            plan,
            (
                candidate(hp, "candidate:low", gain=400_000, cost=10_000),
                candidate(hp, "candidate:high", gain=900_000, cost=900_000),
            ),
        )
        self.assertEqual(proposal.selected_candidate_id, "candidate:high")
        self.assertEqual(proposal.status, "SELECTED_PROPOSAL")
        self.assertEqual(proposal.as_dict()["execution_authority"], "NONE")
        self.assertEqual(proposal.as_dict()["effect_authority"], "NONE")
        self.assertIn("NOT_ACTION_EFFECT", proposal.classification)

    def test_lower_cost_breaks_equal_information_gain(self):
        hp = hyperposition()
        proposal = select(
            hp,
            grid_plan(),
            (
                candidate(hp, "candidate:expensive", gain=700_000, cost=400_000),
                candidate(hp, "candidate:cheap", gain=700_000, cost=100_000),
            ),
        )
        self.assertEqual(proposal.selected_candidate_id, "candidate:cheap")

    def test_lower_work_breaks_equal_gain_and_cost(self):
        hp = hyperposition()
        proposal = select(
            hp,
            grid_plan(),
            (
                candidate(hp, "candidate:more-work", gain=700_000, cost=100_000, work=9),
                candidate(hp, "candidate:less-work", gain=700_000, cost=100_000, work=4),
            ),
        )
        self.assertEqual(proposal.selected_candidate_id, "candidate:less-work")

    def test_exact_ties_are_preserved_and_lexicographic_id_is_deterministic(self):
        hp = hyperposition()
        proposal = select(
            hp,
            grid_plan(),
            (
                candidate(hp, "candidate:z", gain=700_000, cost=100_000, work=4),
                candidate(hp, "candidate:a", gain=700_000, cost=100_000, work=4),
            ),
        )
        self.assertEqual(proposal.tied_candidate_ids, ("candidate:a", "candidate:z"))
        self.assertEqual(proposal.selected_candidate_id, "candidate:a")

    def test_proposal_digest_is_independent_of_candidate_input_order(self):
        hp = hyperposition()
        plan = grid_plan()
        a = candidate(hp, "candidate:a", gain=700_000, cost=100_000)
        b = candidate(hp, "candidate:b", gain=600_000, cost=50_000)
        left = select(hp, plan, (a, b))
        right = select(hp, plan, (b, a))
        self.assertEqual(left.canonical_json(), right.canonical_json())
        self.assertEqual(left.sha256(), right.sha256())

    def test_stale_hyperposition_generation_fails_closed(self):
        hp = hyperposition()
        plan = grid_plan()
        with self.assertRaisesRegex(EpistemicActionSelectionError, "generation mismatch"):
            select_epistemic_action(
                proposal_id="proposal:stale",
                state=hp,
                expected_hyperposition_generation=3,
                expected_hyperposition_sha256=hp.sha256(),
                plan=plan,
                expected_plan_generation=plan.generation,
                expected_plan_sha256=plan.sha256(),
                candidates=(),
                provenance_refs=("source:test",),
            )

    def test_stale_grid_digest_fails_closed(self):
        hp = hyperposition()
        plan = grid_plan()
        with self.assertRaisesRegex(EpistemicActionSelectionError, "GRID10 plan digest mismatch"):
            select_epistemic_action(
                proposal_id="proposal:stale-grid",
                state=hp,
                expected_hyperposition_generation=hp.generation,
                expected_hyperposition_sha256=hp.sha256(),
                plan=plan,
                expected_plan_generation=plan.generation,
                expected_plan_sha256="0" * 64,
                candidates=(),
                provenance_refs=("source:test",),
            )

    def test_discriminator_bound_to_other_hyperposition_fails_closed(self):
        hp = hyperposition()
        plan = grid_plan()
        other = create_hyperposition(
            hyperposition_id="hyper:other",
            generation=4,
            alternatives=hp.alternatives,
            provenance_refs=("source:other",),
        )
        bad = EpistemicActionCandidate(
            candidate_id="candidate:bad",
            action_ref="action:bad",
            cell_id="G1",
            work_units_requested=1,
            discriminator=discriminator(other, "disc:other", gain=500_000, cost=100_000),
            provenance_refs=("source:test",),
        )
        with self.assertRaisesRegex(EpistemicActionSelectionError, "Hyperposition id mismatch"):
            select(hp, plan, (bad,))

    def test_unknown_discriminator_target_fails_closed(self):
        hp = hyperposition()
        plan = grid_plan()
        disc = discriminator(hp, "disc:mutated", gain=500_000, cost=100_000)
        object.__setattr__(disc, "target_alternative_ids", ("alt:a", "alt:missing"))
        bad = EpistemicActionCandidate(
            candidate_id="candidate:bad-target",
            action_ref="action:bad-target",
            cell_id="G1",
            work_units_requested=1,
            discriminator=disc,
            provenance_refs=("source:test",),
        )
        with self.assertRaisesRegex(EpistemicActionSelectionError, "unknown Hyperposition alternatives"):
            select(hp, plan, (bad,))

    def test_duplicate_action_candidate_identity_fails_closed(self):
        hp = hyperposition()
        first = candidate(hp, "candidate:dup", gain=500_000, cost=100_000)
        second = candidate(hp, "candidate:dup", gain=600_000, cost=100_000)
        with self.assertRaisesRegex(EpistemicActionSelectionError, "duplicate epistemic action"):
            select(hp, grid_plan(), (first, second))

    def test_cell_work_budget_excess_rejects_high_gain_candidate(self):
        hp = hyperposition()
        proposal = select(
            hp,
            grid_plan(cell_work=10, total_work=100),
            (
                candidate(hp, "candidate:too-large", gain=900_000, cost=10_000, work=11),
                candidate(hp, "candidate:fits", gain=600_000, cost=10_000, work=5),
            ),
        )
        self.assertEqual(proposal.selected_candidate_id, "candidate:fits")
        reasons = {item.candidate_id: item.reason for item in proposal.assessments}
        self.assertEqual(reasons["candidate:too-large"], "CELL_WORK_BUDGET_EXCEEDED")

    def test_plan_total_work_budget_excess_rejects_candidate(self):
        hp = hyperposition()
        proposal = select(
            hp,
            grid_plan(cell_work=20, total_work=6),
            (candidate(hp, "candidate:too-large", gain=900_000, cost=10_000, work=7),),
        )
        self.assertIsNone(proposal.selected_candidate_id)
        self.assertEqual(
            proposal.assessments[0].reason,
            "PLAN_TOTAL_WORK_BUDGET_EXCEEDED",
        )

    def test_zero_plan_work_budget_is_unavailable_even_for_zero_work_candidate(self):
        hp = hyperposition()
        proposal = select(
            hp,
            grid_plan(cell_work=20, total_work=0),
            (candidate(hp, "candidate:zero-plan", gain=1_000_000, cost=0, work=0),),
        )
        self.assertEqual(proposal.status, "NO_ELIGIBLE_CANDIDATE")
        self.assertIsNone(proposal.selected_candidate_id)
        self.assertEqual(
            proposal.assessments[0].reason,
            "PLAN_TOTAL_WORK_BUDGET_UNAVAILABLE",
        )

    def test_zero_cell_work_budget_is_unavailable_even_for_zero_work_candidate(self):
        hp = hyperposition()
        proposal = select(
            hp,
            grid_plan(cell_work=0, total_work=100),
            (candidate(hp, "candidate:zero-cell", gain=1_000_000, cost=0, work=0),),
        )
        self.assertEqual(proposal.status, "NO_ELIGIBLE_CANDIDATE")
        self.assertIsNone(proposal.selected_candidate_id)
        self.assertEqual(
            proposal.assessments[0].reason,
            "CELL_WORK_BUDGET_UNAVAILABLE",
        )

    def test_all_ineligible_returns_no_eligible_candidate_without_effect_authority(self):
        hp = hyperposition()
        proposal = select(
            hp,
            grid_plan(cell_work=2, total_work=2),
            (candidate(hp, "candidate:nope", gain=1_000_000, cost=0, work=3),),
        )
        self.assertEqual(proposal.status, "NO_ELIGIBLE_CANDIDATE")
        self.assertIsNone(proposal.selected_candidate_id)
        self.assertIsNone(proposal.selected_action_ref)
        self.assertEqual(proposal.tied_candidate_ids, ())
        self.assertEqual(proposal.as_dict()["effect_authority"], "NONE")

    def test_proposal_is_frozen(self):
        hp = hyperposition()
        proposal = select(
            hp,
            grid_plan(),
            (candidate(hp, "candidate:a", gain=500_000, cost=100_000),),
        )
        with self.assertRaises(FrozenInstanceError):
            proposal.selected_candidate_id = "candidate:other"


if __name__ == "__main__":
    unittest.main()
