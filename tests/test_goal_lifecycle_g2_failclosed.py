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
        adoption_authority_ref: str | None = None,
    ) -> GoalStatusChange:
        return GoalStatusChange(
            goal_id=goal_id,
            expected_status=before,
            next_status=after,
            evidence_refs=refs,
            adoption_authority_ref=adoption_authority_ref,
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
                "evidence:adopt-1",
                "evidence:adopt-1",
                adoption_authority_ref="caller-adoption:adopt-1",
            )

    def test_missing_or_untyped_authority_cannot_adopt_goal(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "requires adoption_authority_ref"):
            self.change(
                "goal-1",
                GOAL_CANDIDATE,
                GOAL_ACTIVE,
                "evidence:proposal",
            )
        for authority_ref in (
            "model:proposal",
            "self:reflection",
            "evidence:generic",
            "caller:untyped",
        ):
            with self.subTest(authority_ref=authority_ref):
                with self.assertRaisesRegex(GoalLifecycleError, "must be typed"):
                    self.change(
                        "goal-1",
                        GOAL_CANDIDATE,
                        GOAL_ACTIVE,
                        "evidence:proposal",
                        adoption_authority_ref=authority_ref,
                    )

    def test_explicit_control_plane_adoption_authority_is_admitted(self) -> None:
        change = self.change(
            "goal-1",
            GOAL_CANDIDATE,
            GOAL_TRIAL,
            "evidence:proposal",
            adoption_authority_ref="control-plane-adoption:adopt-1",
        )
        self.assertEqual(change.evidence_refs, ("evidence:proposal",))
        self.assertEqual(
            change.adoption_authority_ref,
            "control-plane-adoption:adopt-1",
        )

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
                    self.change(
                        "a",
                        GOAL_CANDIDATE,
                        GOAL_TRIAL,
                        "evidence:a",
                        adoption_authority_ref="caller-adoption:a",
                    ),
                    self.change(
                        "b",
                        GOAL_CANDIDATE,
                        GOAL_ACTIVE,
                        "evidence:b",
                        adoption_authority_ref="caller-adoption:b",
                    ),
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
        with self.assertRaisesRegex(GoalLifecycleError, "genesis-only"):
            GoalState(
                schema=lifecycle.GOAL_STATE_SCHEMA,
                state_id="goal-state-1",
                generation=1,
                goals=(active,),
            )

    def test_internal_evolution_token_is_not_a_public_constructor_capability(self) -> None:
        self.assertFalse(hasattr(lifecycle, "_EVOLUTION_TOKEN"))
        active = GoalRecord(
            goal_id="goal-1",
            summary="caller token must not be part of constructor ABI",
            priority_ppm=1,
            provenance_refs=("agency:1",),
            status=GOAL_ACTIVE,
        )
        with self.assertRaises(TypeError):
            GoalState(
                schema=lifecycle.GOAL_STATE_SCHEMA,
                state_id="goal-state-1",
                generation=1,
                goals=(active,),
                _construction_token=object(),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
