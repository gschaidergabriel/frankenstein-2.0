#!/usr/bin/env python3
"""Exact regression for the F2-WP-504 zero-GRID-budget counterexample."""
from __future__ import annotations

import unittest

from test_epistemic_action_selection import candidate, grid_plan, hyperposition, select


class WP504ZeroBudgetRegressionTests(unittest.TestCase):
    def test_zero_total_and_cell_budget_cannot_select_zero_work_candidate(self):
        hp = hyperposition()
        proposal = select(
            hp,
            grid_plan(cell_work=0, total_work=0),
            (candidate(hp, "candidate:zero-budget", gain=900_000, cost=0, work=0),),
        )
        self.assertEqual(proposal.status, "NO_ELIGIBLE_CANDIDATE")
        self.assertIsNone(proposal.selected_candidate_id)
        self.assertEqual(
            proposal.assessments[0].reason,
            "PLAN_TOTAL_WORK_BUDGET_UNAVAILABLE",
        )

    def test_zero_cell_budget_cannot_select_even_when_global_budget_exists(self):
        hp = hyperposition()
        proposal = select(
            hp,
            grid_plan(cell_work=0, total_work=100),
            (candidate(hp, "candidate:zero-cell", gain=900_000, cost=0, work=0),),
        )
        self.assertEqual(proposal.status, "NO_ELIGIBLE_CANDIDATE")
        self.assertIsNone(proposal.selected_candidate_id)
        self.assertEqual(
            proposal.assessments[0].reason,
            "CELL_WORK_BUDGET_UNAVAILABLE",
        )


if __name__ == "__main__":
    unittest.main()
