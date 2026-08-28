from __future__ import annotations

import unittest

from frankenstein2.goal_lifecycle import (
    GOAL_ACTIVE,
    GOAL_STATE_SCHEMA,
    GoalRecord,
    GoalState,
)


class GoalAdoptionBoundaryCounterexample(unittest.TestCase):
    """Negative-control probe for F2-WP-204 generation 1.

    IMPORTANT: a PASS here means the counterexample is reproducible. It is NOT
    acceptance evidence for Goal lifecycle.
    """

    @staticmethod
    def _active_goal() -> GoalRecord:
        return GoalRecord(
            goal_id="goal:counterexample",
            summary="Explicit candidate should require an adoption transition",
            priority_ppm=500_000,
            provenance_refs=("owner-input:counterexample",),
            status=GOAL_ACTIVE,
        )

    def test_create_can_mint_active_goal_without_adoption_transition_evidence(self) -> None:
        goal = self._active_goal()

        state = GoalState.create(
            state_id="goal-state:counterexample:create",
            generation=1,
            goals=(goal,),
        )

        self.assertEqual(state.generation, 1)
        self.assertEqual(state.goals[0].status, GOAL_ACTIVE)

    def test_public_constructor_can_mint_generation_zero_active_goal(self) -> None:
        goal = self._active_goal()

        state = GoalState(
            schema=GOAL_STATE_SCHEMA,
            state_id="goal-state:counterexample:constructor",
            generation=0,
            goals=(goal,),
        )

        self.assertEqual(state.generation, 0)
        self.assertEqual(state.goals[0].status, GOAL_ACTIVE)


if __name__ == "__main__":
    unittest.main()
