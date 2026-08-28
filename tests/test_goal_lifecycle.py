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

    def state(self, *goals: GoalRecord) -> GoalState:
        return GoalState.create(state_id="goal-state-1", goals=goals)

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
        if after in {GOAL_TRIAL, GOAL_ACTIVE} and adoption_authority_ref is None:
            adoption_authority_ref = f"caller-adoption:{goal_id}:{after.lower()}"
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

    def test_public_constructor_rejects_pre_adopted_goal_at_generation_zero(self) -> None:
        active = GoalRecord(
            goal_id="goal-1",
            summary="caller tried to pre-adopt",
            priority_ppm=1,
            provenance_refs=("source:1",),
            status=GOAL_ACTIVE,
        )
        with self.assertRaisesRegex(GoalLifecycleError, "CANDIDATE goals only"):
            self.state(active)

    def test_public_create_rejects_nonzero_generation_even_with_candidate(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "genesis-only"):
            GoalState.create(
                state_id="goal-state-1",
                generation=1,
                goals=(self.candidate(),),
            )

    def test_direct_public_constructor_rejects_nonzero_active_rehydration(self) -> None:
        active = GoalRecord(
            goal_id="goal-1",
            summary="direct nonzero active rehydration",
            priority_ppm=1,
            provenance_refs=("source:1",),
            status=GOAL_ACTIVE,
        )
        with self.assertRaisesRegex(GoalLifecycleError, "genesis-only"):
            GoalState(
                schema=GOAL_STATE_SCHEMA,
                state_id="goal-state-1",
                generation=2,
                goals=(active,),
            )

    def test_candidate_to_trial_is_explicit_transition(self) -> None:
        state = self.state(self.candidate())
        next_state, receipt = state.apply(
            self.patch(state, status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_TRIAL),))
        )
        self.assertEqual(next_state.goals[0].status, GOAL_TRIAL)
        self.assertEqual(receipt.schema, GOAL_TRANSITION_SCHEMA)
        self.assertEqual(receipt.changed_goal_ids, ("goal-1",))
        self.assertEqual(len(receipt.added_goal_ids) + len(receipt.changed_goal_ids), 1)

    def test_candidate_to_active_is_explicit_adoption(self) -> None:
        state = self.state(self.candidate())
        next_state, _ = state.apply(
            self.patch(state, status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),))
        )
        self.assertEqual(next_state.goals[0].status, GOAL_ACTIVE)

    def test_promotion_requires_typed_adoption_authority(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "requires adoption_authority_ref"):
            GoalStatusChange(
                goal_id="goal-1",
                expected_status=GOAL_CANDIDATE,
                next_status=GOAL_ACTIVE,
                evidence_refs=("evidence:proposal",),
            )
        for bad_ref in ("model:approve", "self:approve", "evidence:approve", "caller:approve"):
            with self.subTest(bad_ref=bad_ref):
                with self.assertRaisesRegex(GoalLifecycleError, "must be typed"):
                    GoalStatusChange(
                        goal_id="goal-1",
                        expected_status=GOAL_CANDIDATE,
                        next_status=GOAL_ACTIVE,
                        evidence_refs=("evidence:proposal",),
                        adoption_authority_ref=bad_ref,
                    )

    def test_typed_adoption_authority_classes_are_accepted(self) -> None:
        for authority_ref in (
            "caller-adoption:user-confirmation-1",
            "control-plane-adoption:policy-7",
            "external-adoption:ticket-9",
        ):
            with self.subTest(authority_ref=authority_ref):
                change = GoalStatusChange(
                    goal_id="goal-1",
                    expected_status=GOAL_CANDIDATE,
                    next_status=GOAL_TRIAL,
                    evidence_refs=("evidence:proposal",),
                    adoption_authority_ref=authority_ref,
                )
                self.assertEqual(change.adoption_authority_ref, authority_ref)

    def test_nonpromotion_rejects_adoption_authority_ref(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "only valid for promotion"):
            GoalStatusChange(
                goal_id="goal-1",
                expected_status=GOAL_ACTIVE,
                next_status=GOAL_HOLD,
                evidence_refs=("evidence:pause",),
                adoption_authority_ref="caller-adoption:unused",
            )

    def test_active_can_hold_and_resume_via_lineage(self) -> None:
        state0 = self.state(self.candidate())
        state1, _ = state0.apply(
            self.patch(state0, status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),))
        )
        state2, hold_receipt = state1.apply(
            self.patch(
                state1,
                transition_id="transition-2",
                status_changes=(self.change("goal-1", GOAL_ACTIVE, GOAL_HOLD),),
            )
        )
        self.assertEqual(state2.goals[0].status, GOAL_HOLD)
        self.assertEqual(hold_receipt.changed_goal_ids, ("goal-1",))
        state3, resume_receipt = state2.apply(
            self.patch(
                state2,
                transition_id="transition-3",
                status_changes=(self.change("goal-1", GOAL_HOLD, GOAL_ACTIVE),),
            )
        )
        self.assertEqual(state3.goals[0].status, GOAL_ACTIVE)
        self.assertEqual(resume_receipt.changed_goal_ids, ("goal-1",))
        self.assertEqual(state3.generation, 3)

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

    def test_transition_requires_evidence_refs(self) -> None:
        with self.assertRaises(GoalLifecycleError):
            GoalStatusChange(
                goal_id="goal-1",
                expected_status=GOAL_CANDIDATE,
                next_status=GOAL_ACTIVE,
                evidence_refs=(),
                adoption_authority_ref="caller-adoption:1",
            )

    def test_duplicate_provenance_refs_fail_closed(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "duplicate references"):
            GoalRecord.candidate(
                goal_id="goal-1",
                summary="duplicate provenance",
                priority_ppm=1,
                provenance_refs=("source:1", "source:1"),
            )

    def test_duplicate_evidence_refs_fail_closed(self) -> None:
        with self.assertRaisesRegex(GoalLifecycleError, "duplicate references"):
            GoalStatusChange(
                goal_id="goal-1",
                expected_status=GOAL_CANDIDATE,
                next_status=GOAL_ACTIVE,
                evidence_refs=("evidence:1", "evidence:1"),
                adoption_authority_ref="caller-adoption:1",
            )

    def test_duplicate_transition_refs_fail_closed(self) -> None:
        state = self.state(self.candidate())
        with self.assertRaisesRegex(GoalLifecycleError, "duplicate references"):
            self.patch(
                state,
                transition_refs=("decision:1", "decision:1"),
                status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),),
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
        with self.assertRaisesRegex(GoalLifecycleError, "at least one explicit change"):
            self.patch(state)

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

    def test_multiple_candidate_additions_fail_closed(self) -> None:
        state = self.state()
        with self.assertRaisesRegex(GoalLifecycleError, "exactly one goal"):
            self.patch(state, add_candidates=(self.candidate("a"), self.candidate("b")))

    def test_add_and_transition_same_goal_in_one_patch_rejected(self) -> None:
        state = self.state()
        candidate = self.candidate()
        with self.assertRaisesRegex(GoalLifecycleError, "added and lifecycle-transitioned"):
            self.patch(
                state,
                add_candidates=(candidate,),
                status_changes=(self.change("goal-1", GOAL_CANDIDATE, GOAL_ACTIVE),),
            )

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

    def test_digest_and_receipt_are_deterministic_for_unordered_reference_sets(self) -> None:
        left = GoalRecord.candidate(
            goal_id="goal-1",
            summary="explicit goal-1",
            priority_ppm=500_000,
            provenance_refs=("agency:b", "agency:a"),
        )
        right = GoalRecord.candidate(
            goal_id="goal-1",
            summary="explicit goal-1",
            priority_ppm=500_000,
            provenance_refs=("agency:a", "agency:b"),
        )
        left_state = self.state(left)
        right_state = self.state(right)
        self.assertEqual(left_state.canonical_json(), right_state.canonical_json())
        self.assertEqual(left_state.sha256(), right_state.sha256())

        left_patch = self.patch(
            left_state,
            transition_refs=("decision:b", "decision:a"),
            status_changes=(
                self.change(
                    "goal-1",
                    GOAL_CANDIDATE,
                    GOAL_ACTIVE,
                    evidence_refs=("evidence:b", "evidence:a"),
                    adoption_authority_ref="caller-adoption:goal-1",
                ),
            ),
        )
        right_patch = self.patch(
            right_state,
            transition_refs=("decision:a", "decision:b"),
            status_changes=(
                self.change(
                    "goal-1",
                    GOAL_CANDIDATE,
                    GOAL_ACTIVE,
                    evidence_refs=("evidence:a", "evidence:b"),
                    adoption_authority_ref="caller-adoption:goal-1",
                ),
            ),
        )
        left_next, left_receipt = left_state.apply(left_patch)
        right_next, right_receipt = right_state.apply(right_patch)
        self.assertEqual(left_next.canonical_json(), right_next.canonical_json())
        self.assertEqual(left_receipt.canonical_json(), right_receipt.canonical_json())
        self.assertEqual(left_receipt.sha256(), right_receipt.sha256())
        self.assertEqual(
            left_receipt.classification,
            "PURE_GOAL_LIFECYCLE_TRANSITION_NOT_EFFECT_OR_COMPLETION",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
