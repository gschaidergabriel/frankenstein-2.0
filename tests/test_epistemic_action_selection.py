#!/usr/bin/env python3
"""Deterministic falsification suite for F2-WP-504 epistemic action selection."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import unittest

from frankenstein2.epistemic_action_selection import (
    EpistemicActionSelectionError,
    RankingRule,
    SelectionPolicy,
    select_epistemic_action,
)
from frankenstein2.grid10_interface import CellBudget, Grid10Plan
from frankenstein2.hyperposition import (
    Alternative,
    EpistemicStatus,
    create_discriminator_candidate,
    create_hyperposition,
)


def hp():
    alternatives = (
        Alternative(
            alternative_id="alt:b",
            proposition_ref="hypothesis:b",
            generation=4,
            epistemic_status=EpistemicStatus.INFERRED,
            provenance_refs=("source:test",),
            support_refs=("evidence:b",),
            score_micros=500_000,
            uncertainty_micros=400_000,
        ),
        Alternative(
            alternative_id="alt:a",
            proposition_ref="hypothesis:a",
            generation=4,
            epistemic_status=EpistemicStatus.INFERRED,
            provenance_refs=("source:test",),
            support_refs=("evidence:a",),
            score_micros=500_000,
            uncertainty_micros=400_000,
        ),
    )
    return create_hyperposition(
        hyperposition_id="hyper:selection",
        generation=4,
        alternatives=alternatives,
        provenance_refs=("source:hyper",),
        situation_frame_ref="frame:1",
        policy_ref="policy:upstream",
    )


def plan(*, total_work: int = 100):
    cells = tuple(
        CellBudget(
            cell_id=f"G{i}",
            role_label=f"opaque-role-{i}",
            max_input_refs=8,
            max_output_refs=8,
            max_work_units=10 if total_work else 0,
            max_reentry_depth=2,
        )
        for i in range(1, 11)
    )
    return Grid10Plan.create(
        plan_id="grid-plan:1",
        cycle_id="cycle:1",
        generation=7,
        frame_id="frame:1",
        frame_generation=3,
        frame_sha256="1" * 64,
        policy_id="grid-policy:1",
        policy_generation=2,
        policy_sha256="2" * 64,
        cells=cells,
        max_total_work_units=total_work,
        provenance_refs=("source:grid",),
    )


def policy(
    *,
    rule: RankingRule = RankingRule.MAX_EIG_THEN_MIN_COST,
    min_eig: int = 0,
    max_cost: int = 1_000_000,
):
    return SelectionPolicy(
        policy_id="selection-policy:1",
        generation=2,
        ranking_rule=rule,
        min_expected_information_gain_micros=min_eig,
        max_estimated_cost_micros=max_cost,
        provenance_refs=("source:policy",),
    )


def candidate(state, discriminator_id: str, *, eig: int, cost: int):
    return create_discriminator_candidate(
        state=state,
        expected_generation=state.generation,
        expected_state_sha256=state.sha256(),
        discriminator_id=discriminator_id,
        target_alternative_ids=("alt:b", "alt:a"),
        evidence_need_ref=f"need:{discriminator_id}",
        expected_information_gain_micros=eig,
        estimated_cost_micros=cost,
        provenance_refs=("source:disc",),
    )


def select(state, grid, selection_policy, candidates, **overrides):
    kwargs = dict(
        proposal_id="proposal:1",
        generation=1,
        state=state,
        expected_hyperposition_generation=state.generation,
        expected_hyperposition_sha256=state.sha256(),
        grid_plan=grid,
        expected_grid_plan_id=grid.plan_id,
        expected_grid_plan_generation=grid.generation,
        expected_grid_plan_sha256=grid.sha256(),
        policy=selection_policy,
        expected_policy_generation=selection_policy.generation,
        expected_policy_sha256=selection_policy.sha256(),
        candidates=candidates,
        provenance_refs=("source:selection",),
    )
    kwargs.update(overrides)
    return select_epistemic_action(**kwargs)


class EpistemicActionSelectionTests(unittest.TestCase):
    def test_max_eig_then_min_cost_selects_deterministically(self):
        state = hp()
        grid = plan()
        p = policy()
        result = select(
            state,
            grid,
            p,
            (
                candidate(state, "disc:c", eig=800_000, cost=300_000),
                candidate(state, "disc:a", eig=900_000, cost=400_000),
                candidate(state, "disc:b", eig=900_000, cost=200_000),
            ),
        )
        self.assertEqual(result.selected_discriminator_id, "disc:b")
        self.assertEqual(result.tied_discriminator_ids, ("disc:b",))
        self.assertEqual(
            result.eligible_discriminator_ids,
            ("disc:a", "disc:b", "disc:c"),
        )
        self.assertEqual(result.preserved_alternative_ids, ("alt:a", "alt:b"))

    def test_equal_primary_rank_preserves_ties_and_uses_id_only_for_proposal(self):
        state = hp()
        grid = plan()
        p = policy()
        result = select(
            state,
            grid,
            p,
            (
                candidate(state, "disc:z", eig=700_000, cost=100_000),
                candidate(state, "disc:a", eig=700_000, cost=100_000),
            ),
        )
        self.assertEqual(result.selected_discriminator_id, "disc:a")
        self.assertEqual(result.tied_discriminator_ids, ("disc:a", "disc:z"))

    def test_ratio_rule_is_exact_and_does_not_use_floats(self):
        state = hp()
        grid = plan()
        p = policy(rule=RankingRule.MAX_EIG_PER_COST_THEN_MAX_EIG_THEN_MIN_COST)
        result = select(
            state,
            grid,
            p,
            (
                candidate(state, "disc:high-absolute", eig=900_000, cost=900_000),
                candidate(state, "disc:efficient", eig=600_000, cost=200_000),
            ),
        )
        self.assertEqual(result.selected_discriminator_id, "disc:efficient")

    def test_explicit_policy_filters_low_information_and_high_cost(self):
        state = hp()
        grid = plan()
        p = policy(min_eig=500_000, max_cost=300_000)
        result = select(
            state,
            grid,
            p,
            (
                candidate(state, "disc:low", eig=499_999, cost=1),
                candidate(state, "disc:expensive", eig=900_000, cost=300_001),
                candidate(state, "disc:eligible", eig=500_000, cost=300_000),
            ),
        )
        self.assertEqual(result.eligible_discriminator_ids, ("disc:eligible",))

    def test_no_eligible_candidate_fails_closed(self):
        state = hp()
        grid = plan()
        p = policy(min_eig=900_000, max_cost=10)
        with self.assertRaisesRegex(EpistemicActionSelectionError, "no discriminator"):
            select(
                state,
                grid,
                p,
                (candidate(state, "disc:no", eig=100_000, cost=100_000),),
            )

    def test_stale_hyperposition_generation_or_digest_fails_closed(self):
        state = hp()
        grid = plan()
        p = policy()
        values = (candidate(state, "disc:a", eig=500_000, cost=100_000),)
        with self.assertRaises(ValueError):
            select(
                state,
                grid,
                p,
                values,
                expected_hyperposition_generation=state.generation - 1,
            )
        with self.assertRaises(ValueError):
            select(
                state,
                grid,
                p,
                values,
                expected_hyperposition_sha256="0" * 64,
            )

    def test_stale_grid_identity_generation_or_digest_fails_closed(self):
        state = hp()
        grid = plan()
        p = policy()
        values = (candidate(state, "disc:a", eig=500_000, cost=100_000),)
        with self.assertRaisesRegex(EpistemicActionSelectionError, "identity mismatch"):
            select(state, grid, p, values, expected_grid_plan_id="grid-plan:stale")
        with self.assertRaisesRegex(EpistemicActionSelectionError, "generation mismatch"):
            select(
                state,
                grid,
                p,
                values,
                expected_grid_plan_generation=grid.generation + 1,
            )
        with self.assertRaisesRegex(EpistemicActionSelectionError, "digest mismatch"):
            select(state, grid, p, values, expected_grid_plan_sha256="0" * 64)

    def test_stale_policy_generation_or_digest_fails_closed(self):
        state = hp()
        grid = plan()
        p = policy()
        values = (candidate(state, "disc:a", eig=500_000, cost=100_000),)
        with self.assertRaisesRegex(EpistemicActionSelectionError, "policy generation"):
            select(
                state,
                grid,
                p,
                values,
                expected_policy_generation=p.generation + 1,
            )
        with self.assertRaisesRegex(EpistemicActionSelectionError, "policy digest"):
            select(state, grid, p, values, expected_policy_sha256="0" * 64)

    def test_candidate_binding_is_rechecked_against_current_hyperposition(self):
        state = hp()
        grid = plan()
        p = policy()
        good = candidate(state, "disc:a", eig=500_000, cost=100_000)
        stale = replace(good, hyperposition_sha256="0" * 64)
        with self.assertRaisesRegex(EpistemicActionSelectionError, "candidate Hyperposition digest"):
            select(state, grid, p, (stale,))

    def test_candidate_targeting_unknown_alternative_fails_closed(self):
        state = hp()
        grid = plan()
        p = policy()
        good = candidate(state, "disc:a", eig=500_000, cost=100_000)
        forged = replace(good, target_alternative_ids=("alt:a", "alt:unknown"))
        with self.assertRaisesRegex(EpistemicActionSelectionError, "unknown alternatives"):
            select(state, grid, p, (forged,))

    def test_duplicate_discriminator_identity_fails_closed(self):
        state = hp()
        grid = plan()
        p = policy()
        item = candidate(state, "disc:dup", eig=500_000, cost=100_000)
        with self.assertRaisesRegex(EpistemicActionSelectionError, "duplicate discriminator_id"):
            select(state, grid, p, (item, item))

    def test_unavailable_grid_work_budget_fails_closed(self):
        state = hp()
        grid = plan(total_work=0)
        p = policy()
        with self.assertRaisesRegex(EpistemicActionSelectionError, "work budget unavailable"):
            select(
                state,
                grid,
                p,
                (candidate(state, "disc:a", eig=500_000, cost=100_000),),
            )

    def test_malformed_policy_bounds_and_rule_fail_closed(self):
        with self.assertRaises(EpistemicActionSelectionError):
            SelectionPolicy(
                policy_id="selection-policy:bad",
                generation=1,
                ranking_rule=RankingRule.MAX_EIG_THEN_MIN_COST,
                min_expected_information_gain_micros=1_000_001,
                max_estimated_cost_micros=1,
                provenance_refs=("source:test",),
            )
        with self.assertRaises(EpistemicActionSelectionError):
            SelectionPolicy(
                policy_id="selection-policy:bad",
                generation=1,
                ranking_rule="MAX_EIG_THEN_MIN_COST",  # type: ignore[arg-type]
                min_expected_information_gain_micros=1,
                max_estimated_cost_micros=1,
                provenance_refs=("source:test",),
            )

    def test_proposal_is_immutable_canonical_and_has_no_effect_or_truth_authority(self):
        state = hp()
        grid = plan()
        p = policy()
        result = select(
            state,
            grid,
            p,
            (candidate(state, "disc:a", eig=500_000, cost=100_000),),
        )
        self.assertEqual(result.grid_plan_sha256, grid.sha256())
        self.assertEqual(result.hyperposition_sha256, state.sha256())
        self.assertEqual(result.policy_sha256, p.sha256())
        self.assertEqual(result.as_dict()["selection_authority"], "PROPOSAL_ONLY")
        self.assertEqual(result.as_dict()["effect_authority"], "NONE")
        self.assertEqual(result.as_dict()["completion_authority"], "NONE")
        self.assertEqual(result.as_dict()["truth_authority"], "NONE")
        self.assertEqual(len(result.sha256()), 64)
        with self.assertRaises(FrozenInstanceError):
            result.selected_discriminator_id = "disc:forged"  # type: ignore[misc]

    def test_candidate_order_and_provenance_order_do_not_change_digest(self):
        state = hp()
        grid = plan()
        p = SelectionPolicy(
            policy_id="selection-policy:1",
            generation=2,
            ranking_rule=RankingRule.MAX_EIG_THEN_MIN_COST,
            min_expected_information_gain_micros=0,
            max_estimated_cost_micros=1_000_000,
            provenance_refs=("source:z", "source:a"),
        )
        a = candidate(state, "disc:a", eig=500_000, cost=100_000)
        b = candidate(state, "disc:b", eig=400_000, cost=100_000)
        left = select(
            state,
            grid,
            p,
            (b, a),
            provenance_refs=("source:z", "source:a"),
        )
        right = select(
            state,
            grid,
            p,
            (a, b),
            provenance_refs=("source:a", "source:z"),
        )
        self.assertEqual(left.canonical_json(), right.canonical_json())
        self.assertEqual(left.sha256(), right.sha256())


if __name__ == "__main__":
    unittest.main()
