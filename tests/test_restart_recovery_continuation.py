#!/usr/bin/env python3
"""Repository-CI falsifiers for F2-WP-901 restart/recovery continuation."""
from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.agency_state import AgencyState, DeferredIntent, Interest, OpenLoop
from frankenstein2.effect_invocation_correlation import EffectCallBinding, EffectCorrelationStage
from frankenstein2.goal_lifecycle import GoalRecord, GoalState
from frankenstein2.persistent_agency_kernel import (
    CHANGE_POLICY_PROJECTION,
    GoalReplayEnvelope,
    advance_checkpoint,
    create_checkpoint,
)
from frankenstein2.restart_recovery_continuation import (
    DISPOSITION_HELD_UNKNOWN,
    MODE_CANDIDATES_PRESENT,
    MODE_HOLD_UNKNOWN_EFFECT,
    MODE_NO_UNFINISHED_WORK,
    RestartRecoveryError,
    plan_restart_recovery,
)
from frankenstein2.whole_persistent_loop import (
    EFFECT_OUTCOME_UNKNOWN,
    NO_EFFECT,
    LoopOutcomeEvidence,
    WholePersistentLoopSeal,
    outcome_ref,
)
from frankenstein2.wake_hold import OP_EQUALS, WAKE_ANY, WakeCondition


class RestartRecoveryContinuationTests(unittest.TestCase):
    def _checkpoint(self, *, checkpoint_id: str = "checkpoint-0", unfinished: bool = True):
        loops = ()
        intents = ()
        if unfinished:
            loops = (
                OpenLoop(
                    loop_id="loop-open",
                    summary="Continue explicitly unfinished work",
                    state="OPEN",
                    priority_ppm=900_000,
                    provenance_refs=("owner:open-loop",),
                ),
                OpenLoop(
                    loop_id="loop-blocked",
                    summary="Keep blocked work blocked",
                    state="BLOCKED",
                    priority_ppm=700_000,
                    provenance_refs=("owner:blocked-loop",),
                    blocked_on_refs=("evidence:blocker",),
                ),
            )
            intents = (
                DeferredIntent(
                    intent_id="intent-deferred",
                    summary="Revisit only under explicit condition",
                    priority_ppm=800_000,
                    revisit_condition_ref="condition:revisit",
                    provenance_refs=("owner:deferred-intent",),
                ),
            )
        agency = AgencyState.create(
            state_id="agency-state-901",
            generation=0,
            interests=(
                Interest(
                    interest_id="interest-not-work",
                    label="An interest must never be synthesized as unfinished work",
                    salience_ppm=950_000,
                    provenance_refs=("owner:interest",),
                ),
            ),
            open_loops=loops,
            deferred_intents=intents,
        )
        goal_state = GoalState.create(
            state_id="goal-state-901",
            generation=0,
            goals=(
                GoalRecord.candidate(
                    goal_id="goal-candidate-not-recovery-work",
                    summary="Goal state is not implicitly unfinished work",
                    priority_ppm=500_000,
                    provenance_refs=("owner:goal",),
                ),
            ),
        )
        replay = GoalReplayEnvelope.create(genesis=goal_state, patches=())
        wake_condition = WakeCondition(
            condition_id="wake-explicit",
            observation_key="ready",
            operator=OP_EQUALS,
            expected_value="yes",
            provenance_refs=("condition:explicit",),
        )
        return create_checkpoint(
            checkpoint_id=checkpoint_id,
            previous_checkpoint_id=None,
            kernel_state_id="kernel-901",
            generation=0,
            change_policy=CHANGE_POLICY_PROJECTION,
            agency_state=agency,
            goal_replay=replay,
            hold_id="hold-901",
            wake_policy=WAKE_ANY,
            wake_conditions=(wake_condition,),
            hold_provenance_refs=("hold:explicit",),
            pulse_id="pulse-901-0",
            observation_id="observation-901-0",
            act_candidate_ref="candidate:act-existing",
            wait_condition_ref="wait:existing",
            hold_reason_ref="hold:existing",
            provenance_refs=("checkpoint:wp901-fixture",),
        )

    @staticmethod
    def _advance(previous):
        return advance_checkpoint(
            previous,
            checkpoint_id="checkpoint-1",
            pulse_id="pulse-901-1",
            observation_id="observation-901-1",
            provenance_refs=("checkpoint:wp901-successor",),
        )

    @staticmethod
    def _unknown_outcome() -> LoopOutcomeEvidence:
        prepared = EffectCallBinding(
            effect_id="effect-unknown",
            return_id=None,
            binding_id="binding-unknown",
            invocation_id="invocation-unknown",
            tool_use_id="tool-use-unknown",
            delegation_id="delegation-unknown",
            child_identity_sha256="b" * 64,
            stage=EffectCorrelationStage.PREPARED,
        )
        return LoopOutcomeEvidence(
            outcome_id="outcome-unknown",
            status=EFFECT_OUTCOME_UNKNOWN,
            effect_call=prepared,
            unknown_reason_ref="transport:outcome-not-observed",
            provenance_refs=("evidence:unknown-outcome",),
        )

    @staticmethod
    def _no_effect_outcome() -> LoopOutcomeEvidence:
        return LoopOutcomeEvidence(
            outcome_id="outcome-no-effect",
            status=NO_EFFECT,
            provenance_refs=("evidence:no-effect",),
        )

    @staticmethod
    def _seal(previous, current, outcome: LoopOutcomeEvidence) -> WholePersistentLoopSeal:
        return WholePersistentLoopSeal(
            seal_id="whole-loop-seal-901",
            generation=previous.generation,
            current_checkpoint_id=previous.checkpoint_id,
            current_checkpoint_sha256=previous.sha256(),
            frame_id="frame-901",
            frame_sha256="1" * 64,
            contract_id="contract-901",
            contract_sha256="2" * 64,
            grid_plan_id="grid-plan-901",
            grid_plan_sha256="3" * 64,
            gwt_seal_id="gwt-seal-901",
            gwt_seal_sha256="4" * 64,
            decision_kind="ROUTE",
            decision_id="decision-901",
            decision_sha256="5" * 64,
            outcome_id=outcome.outcome_id,
            outcome_sha256=outcome.sha256(),
            next_checkpoint_id=current.checkpoint_id,
            next_checkpoint_sha256=current.sha256(),
            reentry_refs=(outcome_ref(outcome),),
            provenance_refs=("evidence:whole-loop-seal",),
        )

    def test_genesis_recovery_only_projects_explicit_unfinished_items(self) -> None:
        checkpoint = self._checkpoint()
        plan = plan_restart_recovery(
            plan_id="recovery-plan-genesis",
            checkpoint=checkpoint,
            provenance_refs=("restart:explicit",),
        )
        self.assertEqual(plan.mode, MODE_CANDIDATES_PRESENT)
        self.assertEqual(plan.parent_generation, 0)
        self.assertEqual(plan.next_generation, 1)
        self.assertEqual(
            [item.source_item_id for item in plan.candidates],
            ["loop-open", "intent-deferred", "loop-blocked"],
        )
        serialized = plan.as_dict()
        self.assertEqual(serialized["effect_replay_policy"], "NEVER_AUTOMATIC")
        self.assertEqual(serialized["scheduler_authority"], "NONE")
        self.assertNotIn("interest-not-work", plan.canonical_json())
        self.assertNotIn("goal-candidate-not-recovery-work", plan.canonical_json())

    def test_absent_closed_or_cancelled_work_is_not_reconstructed(self) -> None:
        checkpoint = self._checkpoint(unfinished=False)
        plan = plan_restart_recovery(plan_id="recovery-plan-empty", checkpoint=checkpoint)
        self.assertEqual(plan.mode, MODE_NO_UNFINISHED_WORK)
        self.assertEqual(plan.candidates, ())
        self.assertNotIn("interest-not-work", plan.canonical_json())

    def test_non_genesis_recovery_requires_exact_predecessor_evidence(self) -> None:
        previous = self._checkpoint()
        current = self._advance(previous)
        with self.assertRaisesRegex(RestartRecoveryError, "requires exact previous checkpoint"):
            plan_restart_recovery(plan_id="recovery-missing-parent", checkpoint=current)

    def test_wrong_parent_identity_fails_closed(self) -> None:
        previous = self._checkpoint()
        current = self._advance(previous)
        wrong_previous = self._checkpoint(checkpoint_id="checkpoint-other")
        with self.assertRaisesRegex(RestartRecoveryError, "direct-successor lineage rejected"):
            plan_restart_recovery(
                plan_id="recovery-wrong-parent",
                checkpoint=current,
                previous_checkpoint=wrong_previous,
            )

    def test_unknown_effect_holds_candidates_and_never_exposes_replay_material(self) -> None:
        previous = self._checkpoint()
        current = self._advance(previous)
        outcome = self._unknown_outcome()
        seal = self._seal(previous, current, outcome)
        plan = plan_restart_recovery(
            plan_id="recovery-unknown-effect",
            checkpoint=current,
            previous_checkpoint=previous,
            last_loop_seal=seal,
            last_outcome=outcome,
        )
        self.assertEqual(plan.mode, MODE_HOLD_UNKNOWN_EFFECT)
        self.assertTrue(plan.candidates)
        self.assertTrue(
            all(item.disposition == DISPOSITION_HELD_UNKNOWN for item in plan.candidates)
        )
        serialized = plan.canonical_json()
        self.assertIn('"effect_replay_policy":"NEVER_AUTOMATIC"', serialized)
        self.assertIn('"unknown_effect_policy":"HOLD_UNTIL_EXPLICIT_VERIFICATION_OR_NEW_OBSERVATION"', serialized)
        self.assertNotIn("effect-unknown", serialized)
        self.assertNotIn("invocation-unknown", serialized)

    def test_no_effect_evidence_preserves_candidates_without_completion_authority(self) -> None:
        previous = self._checkpoint()
        current = self._advance(previous)
        outcome = self._no_effect_outcome()
        seal = self._seal(previous, current, outcome)
        plan = plan_restart_recovery(
            plan_id="recovery-no-effect",
            checkpoint=current,
            previous_checkpoint=previous,
            last_loop_seal=seal,
            last_outcome=outcome,
        )
        self.assertEqual(plan.mode, MODE_CANDIDATES_PRESENT)
        self.assertEqual(plan.outcome_status, NO_EFFECT)
        self.assertEqual(plan.as_dict()["completion_authority"], "NONE")
        self.assertFalse(plan.as_dict()["whole_system_acceptance"])

    def test_loop_seal_checkpoint_digest_mismatch_fails_closed(self) -> None:
        previous = self._checkpoint()
        current = self._advance(previous)
        outcome = self._no_effect_outcome()
        seal = self._seal(previous, current, outcome)
        tampered = replace(seal, next_checkpoint_sha256="f" * 64)
        with self.assertRaisesRegex(RestartRecoveryError, "seal next checkpoint digest mismatch"):
            plan_restart_recovery(
                plan_id="recovery-tampered-seal",
                checkpoint=current,
                previous_checkpoint=previous,
                last_loop_seal=tampered,
                last_outcome=outcome,
            )

    def test_loop_seal_and_outcome_must_be_supplied_as_exact_pair(self) -> None:
        previous = self._checkpoint()
        current = self._advance(previous)
        outcome = self._no_effect_outcome()
        seal = self._seal(previous, current, outcome)
        with self.assertRaisesRegex(RestartRecoveryError, "supplied together"):
            plan_restart_recovery(
                plan_id="recovery-unpaired-seal",
                checkpoint=current,
                previous_checkpoint=previous,
                last_loop_seal=seal,
            )

    def test_same_exact_evidence_produces_same_digest(self) -> None:
        checkpoint = self._checkpoint()
        first = plan_restart_recovery(
            plan_id="recovery-deterministic",
            checkpoint=checkpoint,
            provenance_refs=("restart:explicit", "checkpoint:caller"),
        )
        second = plan_restart_recovery(
            plan_id="recovery-deterministic",
            checkpoint=checkpoint,
            provenance_refs=("checkpoint:caller", "restart:explicit"),
        )
        self.assertEqual(first.as_dict(), second.as_dict())
        self.assertEqual(first.sha256(), second.sha256())


if __name__ == "__main__":
    unittest.main()
