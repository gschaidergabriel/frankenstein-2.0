from __future__ import annotations

import unittest

from frankenstein2.goal_lifecycle import (
    GOAL_ACTIVE,
    GOAL_CANDIDATE,
    GOAL_DROPPED,
    GOAL_HOLD,
    GOAL_PATCH_SCHEMA,
    GOAL_STATE_SCHEMA,
    GOAL_TRANSITION_SCHEMA,
    GOAL_TRIAL,
    GoalLifecycleError,
    GoalRecord,
    GoalState,
    GoalStatePatch,
    GoalStatusChange,
)


class GoalLifecycleTests(unittest.TestCase):
    def candidate(self, goal_id: str = "goal-1", *, priority: int = 500_000) -> GoalRecord:
        return GoalRecord.candidate(
            goal_id=goal_id,
            summary=f"explicit {goal_id}",
            priority_ppm=priority,
            provenance_refs=(f"agency:{goal_id}",),
        )

    def state(self, *goals: GoalRecord, generation: int = 0) -> GoalState:
        return GoalState.create(state_id="goal-state-1", generation=generation, goals=goals)

    def patch(
        self,
        state: GoalState,
        *,
        transition_id: str = "transition-1",
        transition_refs: tuple[str, ...] = ("decision:explicit",),
        add_candidates: tuple[GoalRecord, ...] = (),
        status_changes: tuple[GoalStatusChange, ...] = (),
    ) -> GoalStatePatch:
        return GoalStatePatch(
            schema=GOAL_PATCH_SCHEMA,
            transition_id=transition_id,
            expected_state_id=state.state_id,
            expected_generation=state.generation,
            expected_state_sha256=state.sha256(),
            next_generation=state.generation + 1,
            transition_refs=transition_refs,
            add_candidates=add_candidates,
            status_changes=status_changes,
        )

    def change(
        self,
        goal_id: str,
        before: str,
        after: str,
        *,
        evidence_refs: tuple[str, ...] | None = None,
        adoption_authority_ref: str | None = None,
    ) -> GoalStatusChange:
        if evidence_refs is None:
            evidence_refs = (f"evidence:{before.lower()}-to-{after.lower()}",)
        if adoption_authority_ref is None and after in {GOAL_TRIAL, GOAL_ACTIVE}:
            adoption_authority_ref = "caller:explicit-adoption"
        return GoalStatusChange(
            goal_id=goal_id,
            expected_status=before,
            next_status=after,
            evidence_refs=evidence_refs,
            adoption_authority_ref=adoption_authority_ref,
        )

    def test_new_goal_is_candidate_only(self) -> None:
        goal = self.candidate()
        self.assertEqual(goal.status, GOAL_CANDIDATE)
        state = self.state(goal)
        self.assertEqual(state.goals[0].status, GOAL_CANDIDATE)
        self.assertEqual(state.schema, GOAL_STATE_SCHEMA)

    def test_public_state_construction_rejects_pre_adopted_goal_at_every_generation(self) -> None:
        active = GoalRecord(
            goal_id="goal-1",
            summary="caller tried to pre-adopt",
            priority_ppm=1,
            provenance_refs=("source:1",),
            status=GOAL_ACTIVE,
        )
        for generation in (0, 1, 7):
            with self.subTest(generation=generation):
                with self.assertRaisesRegex(GoalLifecycleError, "CANDIDATE goals only"):
                    self.state(active, generation=generation)
                with self.assertRaisesRegex(GoalLifecycleError, "CANDIDATE goals only"):
                    GoalState(
                        schema=GOAL_STATE_SCHEMA,
                        state_id="direct-state",
                        generation=generation,
                        goals=(active,),
                    )

    def test_valid_transition_can_produce_non_candidate_successor_state(self) -> None:
        state = self.state(self.candidate())
        next_state, receipt = state.apply(
            self.patch(
                state,
                status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),),
            )
        )
        self.assertEqual(next_state.goals[0].status, GOAL_ACTIVE)
        self.assertEqual(next_state.generation, 1)
        self.assertEqual(receipt.changed_goal_ids, ("goal-1",))

    def test_candidate_to_trial_is_explicit_transition(self) -> None:
        state = self.state(self.candidate())
        next_state, receipt = state.apply(
            self.patch(state, status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_TRIAL),))
        )
        self.assertEqual(next_state.goals[0].status, GOAL_TRIAL)
        self.assertEqual(receipt.schema, GOAL_TRANSITION_SCHEMA)
        self.assertEqual(receipt.changed_goal_ids, ("goal-1",))

    def test_candidate_to_active_requires_typed_adoption_authority(self) -> None:
        state = self.state(self.candidate())
        with self.assertRaisesRegex(GoalLifecycleError, "requires explicit adoption_authority_ref"):
            GoalStatusChange(
                goal_id="goal-1",
                expected_status=GOAL_CANDIDATE,
                next_status=GOAL_ACTIVE,
                evidence_refs=("model:proposed-goal",),
            )

        for invalid in ("model:approve", "self:approve", "evidence:approve", "caller:"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(GoalLifecycleError, "typed caller:"):
                    GoalStatusChange(
                        goal_id="goal-1",
                        expected_status=GOAL_CANDIDATE,
                        next_status=GOAL_ACTIVE,
                        evidence_refs=("evidence:reviewed",),
                        adoption_authority_ref=invalid,
                    )

        next_state, _ = state.apply(
            self.patch(
                state,
                status_changes=(
                    GoalStatusChange(
                        goal_id="goal-1",
                        expected_status=GOAL_CANDIDATE,
                        next_status=GOAL_ACTIVE,
                        evidence_refs=("model:proposed-goal", "evidence:reviewed"),
                        adoption_authority_ref="control-plane:goal-adoption-42",
                    ),
                ),
            )
        )
        self.assertEqual(next_state.goals[0].status, GOAL_ACTIVE)

    def test_non_promotion_rejects_adoption_authority_ref(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "only valid for promotion"):
            GoalStatusChange(
                goal_id="goal-1",
                expected_status=GOAL_ACTIVE,
                next_status=GOAL_HOLD,
                evidence_refs=("evidence:hold",),
                adoption_authority_ref="caller:not-needed",
            )

    def test_active_can_hold(self) -> None:
        state0 = self.state(self.candidate())
        state1, _ = state0.apply(
            self.patch(state0, status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),))
        )
        state2, _ = state1.apply(
            self.patch(
                state1,
                transition_id="transition-2",
                status_changes=(self.change("goal-1", GOAL_ACTIVE, GOAL_HOLD),),
            )
        )
        self.assertEqual(state2.goals[0].status, GOAL_HOLD)

    def test_hold_can_resume_active_with_new_adoption_authority(self) -> None:
        state0 = self.state(self.candidate())
        active, _ = state0.apply(
            self.patch(state0, status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),))
        )
        held, _ = active.apply(
            self.patch(
                active,
                transition_id="transition-2",
                status_changes=(self.change("goal-1", GOAL_ACTIVE, GOAL_HOLD),),
            )
        )
        resumed, _ = held.apply(
            self.patch(
                held,
                transition_id="transition-3",
                status_changes=(self.change("goal-1", GOAL_HOLD, GOAL_ACTIVE),),
            )
        )
        self.assertEqual(resumed.goals[0].status, GOAL_ACTIVE)

    def test_dropped_is_terminal(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "illegal goal transition"):
            self.change("goal-1", GOAL_DROPPED, GOAL_ACTIVE)

    def test_no_completed_status_exists(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "unsupported goal status"):
            GoalRecord(
                goal_id="goal-1",
                summary="must not mint completion",
                priority_ppm=1,
                provenance_refs=("source:1",),
                status="COMPLETED",
            )

    def test_duplicate_provenance_refs_fail_closed(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "duplicate references"):
            GoalRecord.candidate(
                goal_id="goal-1",
                summary="duplicate provenance",
                priority_ppm=1,
                provenance_refs=("source:1", "source:1"),
            )

    def test_duplicate_transition_evidence_refs_fail_closed(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "duplicate references"):
            self.change(
                "goal-1",
                GOAL_CANDIDATE,
                GOAL_ACTIVE,
                evidence_refs=("evidence:1", "evidence:1"),
            )

    def test_duplicate_patch_transition_refs_fail_closed(self) -> None:
        state = self.state(self.candidate())
        with self.assertRaisesRegex(GoalLifecycleError, "duplicate references"):
            self.patch(
                state,
                transition_refs=("decision:1", "decision:1"),
                status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),),
            )

    def test_transition_requires_evidence_refs(self) -> None:
        with self.assertRaises(GoalLifecycleError):
            GoalStatusChange(
                goal_id="goal-1",
                expected_status=GOAL_CANDIDATE,
                next_status=GOAL_ACTIVE,
                evidence_refs=(),
                adoption_authority_ref="caller:explicit-adoption",
            )

    def test_patch_requires_transition_refs(self) -> None:
        state = self.state(self.candidate())
        with self.assertRaises(GoalLifecycleError):
            GoalStatePatch(
                schema=GOAL_PATCH_SCHEMA,
                transition_id="t",
                expected_state_id=state.state_id,
                expected_generation=state.generation,
                expected_state_sha256=state.sha256(),
                next_generation=1,
                transition_refs=(),
                status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),),
            )

    def test_empty_patch_rejected(self) -> None:
        state = self.state()
        with self.assertRaisesRegex(GoalLifecycleError, "exactly one goal"):
            self.patch(state)

    def test_add_and_transition_same_goal_in_one_patch_rejected(self) -> None:
        state = self.state()
        candidate = self.candidate()
        with self.assertRaisesRegex(GoalLifecycleError, "added and lifecycle-transitioned"):
            self.patch(
                state,
                add_candidates=(candidate,),
                status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),),
            )

    def test_cross_goal_status_changes_fail_closed(self) -> None:
        state = self.state(self.candidate("a"), self.candidate("b"))
        with self.assertRaisesRegex(GoalLifecycleError, "exactly one goal"):
            self.patch(
                state,
                status_changes=(
                    self.change("a", GOAL_CANDIDATE, GOAL_TRIAL),
                    self.change("b", GOAL_CANDIDATE, GOAL_ACTIVE),
                ),
            )

    def test_multi_candidate_addition_fail_closed(self) -> None:
        state = self.state()
        with self.assertRaisesRegex(GoalLifecycleError, "exactly one goal"):
            self.patch(state, add_candidates=(self.candidate("a"), self.candidate("b")))

    def test_stale_generation_rejected(self) -> None:
        state = self.state(self.candidate())
        patch = GoalStatePatch(
            schema=GOAL_PATCH_SCHEMA,
            transition_id="t",
            expected_state_id=state.state_id,
            expected_generation=1,
            expected_state_sha256=state.sha256(),
            next_generation=2,
            transition_refs=("decision:1",),
            status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),),
        )
        with self.assertRaisesRegex(GoalLifecycleError, "stale goal-state generation"):
            state.apply(patch)

    def test_stale_digest_rejected(self) -> None:
        state = self.state(self.candidate())
        patch = GoalStatePatch(
            schema=GOAL_PATCH_SCHEMA,
            transition_id="t",
            expected_state_id=state.state_id,
            expected_generation=state.generation,
            expected_state_sha256="0" * 64,
            next_generation=state.generation + 1,
            transition_refs=("decision:1",),
            status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),),
        )
        with self.assertRaisesRegex(GoalLifecycleError, "stale or mismatched goal-state digest"):
            state.apply(patch)

    def test_wrong_state_id_rejected(self) -> None:
        state = self.state(self.candidate())
        patch = GoalStatePatch(
            schema=GOAL_PATCH_SCHEMA,
            transition_id="t",
            expected_state_id="other-state",
            expected_generation=state.generation,
            expected_state_sha256=state.sha256(),
            next_generation=state.generation + 1,
            transition_refs=("decision:1",),
            status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),),
        )
        with self.assertRaisesRegex(GoalLifecycleError, "state_id mismatch"):
            state.apply(patch)

    def test_unknown_goal_transition_rejected(self) -> None:
        state = self.state()
        with self.assertRaisesRegex(GoalLifecycleError, "unknown goal"):
            state.apply(
                self.patch(
                    state,
                    status_changes=(self.change("missing", GOAL_CANDIDATE, GOAL_ACTIVE),),
                )
            )

    def test_expected_status_must_match_current(self) -> None:
        state = self.state(self.candidate())
        with self.assertRaisesRegex(GoalLifecycleError, "status mismatch"):
            state.apply(
                self.patch(state, status_changes=(self.change("goal-1", GOAL_TRIAL, GOAL_ACTIVE),))
            )

    def test_duplicate_goal_ids_rejected(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "duplicate goal_id"):
            self.state(self.candidate("same"), self.candidate("same"))

    def test_duplicate_status_changes_rejected(self) -> None:
        state = self.state(self.candidate())
        with self.assertRaisesRegex(GoalLifecycleError, "duplicate status change"):
            self.patch(
                state,
                status_changes=(
                    self.change("goal-1", GOAL_CANDIDATE, GOAL_TRIAL),
                    self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),
                ),
            )

    def test_digest_and_receipt_are_deterministic_under_unordered_refs(self) -> None:
        left = self.state(self.candidate("b"), self.candidate("a"))
        right = self.state(self.candidate("a"), self.candidate("b"))
        self.assertEqual(left.canonical_json(), right.canonical_json())
        self.assertEqual(left.sha256(), right.sha256())

        left_change = GoalStatusChange(
            goal_id="a",
            expected_status=GOAL_CANDIDATE,
            next_status=GOAL_ACTIVE,
            evidence_refs=("evidence:z", "evidence:a"),
            adoption_authority_ref="external:owner-decision",
        )
        right_change = GoalStatusChange(
            goal_id="a",
            expected_status=GOAL_CANDIDATE,
            next_status=GOAL_ACTIVE,
            evidence_refs=("evidence:a", "evidence:z"),
            adoption_authority_ref="external:owner-decision",
        )
        left_patch = self.patch(
            left,
            transition_refs=("decision:z", "decision:a"),
            status_changes=(left_change,),
        )
        right_patch = self.patch(
            right,
            transition_refs=("decision:a", "decision:z"),
            status_changes=(right_change,),
        )
        left_next, left_receipt = left.apply(left_patch)
        right_next, right_receipt = right.apply(right_patch)
        self.assertEqual(left_next.canonical_json(), right_next.canonical_json())
        self.assertEqual(left_receipt.canonical_json(), right_receipt.canonical_json())
        self.assertEqual(left_receipt.sha256(), right_receipt.sha256())
        self.assertEqual(left_receipt.changed_goal_ids, ("a",))
        self.assertEqual(left_receipt.added_goal_ids, ())
        self.assertEqual(
            left_receipt.classification,
            "PURE_GOAL_LIFECYCLE_TRANSITION_NOT_EFFECT_OR_COMPLETION",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
