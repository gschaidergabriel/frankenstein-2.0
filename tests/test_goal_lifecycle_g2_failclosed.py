from __future__ import annotations

import unittest

import frankenstein2.goal_lifecycle as lifecycle
from frankenstein2.goal_lifecycle import (
    GOAL_ACTIVE,
    GOAL_CANDIDATE,
    GOAL_PATCH_SCHEMA,
    GOAL_TRIAL,
    GoalLifecycleError,
    GoalRecord,
    GoalState,
    GoalStatePatch,
    GoalStatusChange,
)


class GoalLifecycleG2FailClosedTests(unittest.TestCase):
    def candidate(self, goal_id: str = "goal-1") -> GoalRecord:
        return GoalRecord.candidate(
            goal_id=goal_id,
            summary=f"explicit {goal_id}",
            priority_ppm=500_000,
            provenance_refs=(f"agency:{goal_id}",),
        )

    def change(
        self,
        goal_id: str,
        before: str,
        after: str,
        *refs: str,
    ) -> GoalStatusChange:
        return GoalStatusChange(
            goal_id=goal_id,
            expected_status=before,
            next_status=after,
            evidence_refs=refs,
        )

    def test_duplicate_provenance_refs_fail_closed(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "duplicate references"):
            GoalRecord.candidate(
                goal_id="goal-1",
                summary="duplicate provenance must not normalize away",
                priority_ppm=1,
                provenance_refs=("agency:1", "agency:1"),
            )

    def test_duplicate_transition_evidence_refs_fail_closed(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "duplicate references"):
            self.change(
                "goal-1",
                GOAL_CANDIDATE,
                GOAL_ACTIVE,
                "owner:adopt-1",
                "owner:adopt-1",
            )

    def test_model_or_untyped_evidence_cannot_adopt_goal(self) -> None:
        for evidence_ref in ("model:proposal", "self:reflection", "evidence:generic"):
            with self.subTest(evidence_ref=evidence_ref):
                with self.assertRaisesRegex(GoalLifecycleError, "adoption-authority"):
                    self.change(
                        "goal-1",
                        GOAL_CANDIDATE,
                        GOAL_ACTIVE,
                        evidence_ref,
                    )

    def test_explicit_external_adoption_authority_is_admitted(self) -> None:
        change = self.change(
            "goal-1",
            GOAL_CANDIDATE,
            GOAL_TRIAL,
            "control:adopt-1",
        )
        self.assertEqual(change.evidence_refs, ("control:adopt-1",))

    def test_cross_goal_patch_receipt_fails_closed(self) -> None:
        state = GoalState.create(
            state_id="goal-state-1",
            goals=(self.candidate("a"), self.candidate("b")),
        )
        with self.assertRaisesRegex(GoalLifecycleError, "exactly one goal"):
            GoalStatePatch(
                schema=GOAL_PATCH_SCHEMA,
                transition_id="cross-goal",
                expected_state_id=state.state_id,
                expected_generation=state.generation,
                expected_state_sha256=state.sha256(),
                next_generation=1,
                transition_refs=("decision:explicit",),
                status_changes=(
                    self.change("a", GOAL_CANDIDATE, GOAL_TRIAL, "owner:a"),
                    self.change("b", GOAL_CANDIDATE, GOAL_ACTIVE, "owner:b"),
                ),
            )

    def test_public_noncandidate_rehydration_fails_closed(self) -> None:
        active = GoalRecord(
            goal_id="goal-1",
            summary="must not rehydrate active through public constructor",
            priority_ppm=1,
            provenance_refs=("agency:1",),
            status=GOAL_ACTIVE,
        )
        with self.assertRaisesRegex(GoalLifecycleError, "non-candidate state"):
            GoalState(
                schema=lifecycle.GOAL_STATE_SCHEMA,
                state_id="goal-state-1",
                generation=1,
                goals=(active,),
            )

    def test_internal_evolution_token_is_not_a_public_constructor_capability(self) -> None:
        active = GoalRecord(
            goal_id="goal-1",
            summary="private token must not become caller capability",
            priority_ppm=1,
            provenance_refs=("agency:1",),
            status=GOAL_ACTIVE,
        )
        with self.assertRaises((TypeError, GoalLifecycleError)):
            GoalState(
                schema=lifecycle.GOAL_STATE_SCHEMA,
                state_id="goal-state-1",
                generation=1,
                goals=(active,),
                _construction_token=lifecycle._EVOLUTION_TOKEN,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
