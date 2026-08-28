"""Independent F2-WP-204 generation-bypass falsifier.

CANDIDATE_FALSIFIER only. This does not own or mutate the canonical WP-204
implementation. It tests whether a nonzero-generation GoalState can be constructed
already ACTIVE without traversing the explicit lifecycle transition/receipt path.
"""
from __future__ import annotations

import unittest

from frankenstein2.goal_lifecycle import (
    GOAL_ACTIVE,
    GOAL_CANDIDATE,
    GOAL_PATCH_SCHEMA,
    GoalLifecycleError,
    GoalRecord,
    GoalState,
    GoalStatePatch,
    GoalStatusChange,
)


class GoalLifecycleGenerationFalsifier(unittest.TestCase):
    def _goal(self, *, status: str = GOAL_CANDIDATE) -> GoalRecord:
        return GoalRecord(
            goal_id="goal-1",
            summary="Explicit test goal",
            priority_ppm=500_000,
            provenance_refs=("owner:test",),
            status=status,
        )

    def test_generation_zero_rejects_non_candidate_bootstrap(self) -> None:
        with self.assertRaises(GoalLifecycleError):
            GoalState.create(
                state_id="goal-state",
                generation=0,
                goals=(self._goal(status=GOAL_ACTIVE),),
            )

    def test_nonzero_generation_cannot_bootstrap_active_without_transition_receipt(self) -> None:
        """Claimed lifecycle semantics require explicit adoption transitions.

        If persistence rehydration is intended, it needs a distinct identity-bound
        rehydration contract. Generic create() must not become an unchecked shortcut
        around GoalStatusChange + GoalStateTransition lineage.
        """
        with self.assertRaises(GoalLifecycleError):
            GoalState.create(
                state_id="goal-state",
                generation=1,
                goals=(self._goal(status=GOAL_ACTIVE),),
            )

    def test_explicit_candidate_to_active_transition_remains_valid_control(self) -> None:
        state = GoalState.create(
            state_id="goal-state",
            generation=0,
            goals=(self._goal(),),
        )
        patch = GoalStatePatch(
            schema=GOAL_PATCH_SCHEMA,
            transition_id="transition-1",
            expected_state_id=state.state_id,
            expected_generation=state.generation,
            expected_state_sha256=state.sha256(),
            next_generation=1,
            transition_refs=("owner:explicit-adoption",),
            status_changes=(
                GoalStatusChange(
                    goal_id="goal-1",
                    expected_status=GOAL_CANDIDATE,
                    next_status=GOAL_ACTIVE,
                    evidence_refs=("owner:explicit-adoption",),
                ),
            ),
        )

        next_state, receipt = state.apply(patch)

        self.assertEqual(next_state.generation, 1)
        self.assertEqual(next_state.goals[0].status, GOAL_ACTIVE)
        self.assertEqual(receipt.changed_goal_ids, ("goal-1",))
        self.assertEqual(
            receipt.classification,
            "PURE_GOAL_LIFECYCLE_TRANSITION_NOT_EFFECT_OR_COMPLETION",
        )


if __name__ == "__main__":
    unittest.main()
