#!/usr/bin/env python3
"""Repository-component falsifiers for F2-WP-901 restart/recovery continuation."""
from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.agency_state import AgencyState, Interest, OpenLoop
from frankenstein2.effect_invocation_correlation import (
    EffectCallBinding,
    EffectCorrelationStage,
)
from frankenstein2.goal_lifecycle import GoalRecord, GoalState
from frankenstein2.persistent_agency_kernel import (
    CHANGE_POLICY_PROJECTION,
    GoalReplayEnvelope,
    advance_checkpoint,
    create_checkpoint,
)
from frankenstein2.restart_recovery_continuation import (
    REPLAY_FORBIDDEN_UNVERIFIED,
    REPLAY_NOT_APPLICABLE,
    RestartRecoveryError,
    TRANSITION_HOLD,
    TRANSITION_OBSERVE,
    TRANSITION_RESUME,
    plan_restart_recovery,
)
from frankenstein2.wake_hold import OP_EQUALS, WAKE_ANY, WakeCondition
from frankenstein2.whole_persistent_loop import (
    EFFECT_OUTCOME_UNKNOWN,
    EFFECT_RESULT_OBSERVED,
    LoopOutcomeEvidence,
    NO_EFFECT,
    WholePersistentLoopSeal,
    checkpoint_ref,
    outcome_ref,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64


def fixture_checkpoint(*, unfinished: bool = True):
    loops = ()
    if unfinished:
        loops = (
            OpenLoop(
                loop_id="loop-wp901",
                summary="Resume explicit unfinished work after restart",
                state="OPEN",
                priority_ppm=900_000,
                provenance_refs=("test:wp901:loop",),
            ),
        )
    agency = AgencyState.create(
        state_id="agency-state-wp901",
        generation=4,
        interests=(
            Interest(
                interest_id="interest-wp901",
                label="Preserve restart lineage",
                salience_ppm=800_000,
                provenance_refs=("test:wp901:interest",),
            ),
        ),
        open_loops=loops,
    )
    genesis = GoalState.create(
        state_id="goal-state-wp901",
        generation=0,
        goals=(
            GoalRecord.candidate(
                goal_id="goal-wp901",
                summary="Test bounded restart continuation",
                priority_ppm=900_000,
                provenance_refs=("test:wp901:goal",),
            ),
        ),
    )
    replay = GoalReplayEnvelope.create(genesis=genesis, patches=())
    condition = WakeCondition(
        condition_id="wake-wp901",
        observation_key="ready",
        operator=OP_EQUALS,
        expected_value="yes",
        provenance_refs=("test:wp901:wake",),
    )
    return create_checkpoint(
        checkpoint_id="checkpoint-wp901-0",
        previous_checkpoint_id=None,
        kernel_state_id="kernel-wp901",
        generation=0,
        change_policy=CHANGE_POLICY_PROJECTION,
        agency_state=agency,
        goal_replay=replay,
        hold_id="hold-wp901",
        wake_policy=WAKE_ANY,
        wake_conditions=(condition,),
        hold_provenance_refs=("test:wp901:hold",),
        pulse_id="pulse-wp901-0",
        observation_id="observation-wp901-0",
        act_candidate_ref="candidate:act-wp901",
        provenance_refs=("test:wp901:checkpoint",),
    )


def no_effect_outcome(*, outcome_id: str = "outcome-wp901") -> LoopOutcomeEvidence:
    return LoopOutcomeEvidence(
        outcome_id=outcome_id,
        status=NO_EFFECT,
        provenance_refs=("test:wp901:no-effect",),
    )


def unknown_outcome() -> LoopOutcomeEvidence:
    prepared = EffectCallBinding(
        effect_id="effect-wp901-unknown",
        return_id=None,
        binding_id="binding-wp901-unknown",
        invocation_id="invocation-wp901-unknown",
        tool_use_id="tool-wp901-unknown",
        delegation_id="delegation-wp901-unknown",
        child_identity_sha256=SHA_A,
        stage=EffectCorrelationStage.PREPARED,
    )
    return LoopOutcomeEvidence(
        outcome_id="outcome-wp901-unknown",
        status=EFFECT_OUTCOME_UNKNOWN,
        effect_call=prepared,
        unknown_reason_ref="transport:outcome-unknown",
        provenance_refs=("test:wp901:unknown",),
    )


def result_observed_outcome() -> LoopOutcomeEvidence:
    observed = EffectCallBinding(
        effect_id="effect-wp901-observed",
        return_id=None,
        binding_id="binding-wp901-observed",
        invocation_id="invocation-wp901-observed",
        tool_use_id="tool-wp901-observed",
        delegation_id="delegation-wp901-observed",
        child_identity_sha256=SHA_B,
        stage=EffectCorrelationStage.RESULT_OBSERVED,
        result_id="result-wp901-observed",
        result_sha256=SHA_C,
    )
    return LoopOutcomeEvidence(
        outcome_id="outcome-wp901-observed",
        status=EFFECT_RESULT_OBSERVED,
        effect_call=observed,
        provenance_refs=("test:wp901:observed",),
    )


def fixture_case(*, unfinished: bool = True, outcome: LoopOutcomeEvidence | None = None):
    previous = fixture_checkpoint(unfinished=unfinished)
    outcome = outcome or no_effect_outcome()
    reentry_refs = tuple(
        sorted(
            (
                checkpoint_ref(previous),
                outcome_ref(outcome),
                "wp900:test:reentry:wp901",
            )
        )
    )
    persisted = advance_checkpoint(
        previous,
        checkpoint_id="checkpoint-wp901-1",
        pulse_id="pulse-wp901-1",
        observation_id="observation-wp901-1",
        provenance_refs=reentry_refs,
    )
    seal = WholePersistentLoopSeal(
        seal_id="seal-wp901",
        generation=0,
        current_checkpoint_id=previous.checkpoint_id,
        current_checkpoint_sha256=previous.sha256(),
        frame_id="frame-wp901",
        frame_sha256=SHA_A,
        contract_id="contract-wp901",
        contract_sha256=SHA_B,
        grid_plan_id="grid-wp901",
        grid_plan_sha256=SHA_C,
        gwt_seal_id="gwt-wp901",
        gwt_seal_sha256=SHA_D,
        decision_kind="ROUTE",
        decision_id="decision-wp901",
        decision_sha256=SHA_E,
        outcome_id=outcome.outcome_id,
        outcome_sha256=outcome.sha256(),
        next_checkpoint_id=persisted.checkpoint_id,
        next_checkpoint_sha256=persisted.sha256(),
        reentry_refs=reentry_refs,
        provenance_refs=("test:wp901:seal",),
    )
    return previous, persisted, seal, outcome


class RestartRecoveryContinuationTests(unittest.TestCase):
    def test_explicit_unfinished_work_resumes_without_effect_replay_authority(self):
        previous, persisted, seal, outcome = fixture_case(unfinished=True)
        candidate = plan_restart_recovery(
            candidate_id="recovery-wp901-resume",
            previous_checkpoint=previous,
            persisted_checkpoint=persisted,
            loop_seal=seal,
            outcome=outcome,
            provenance_refs=("test:wp901:resume",),
        )
        self.assertEqual(candidate.transition, TRANSITION_RESUME)
        self.assertEqual(candidate.replay_disposition, REPLAY_NOT_APPLICABLE)
        self.assertEqual(len(candidate.unfinished_work_refs), 1)
        projection = candidate.as_dict()
        self.assertEqual(projection["scheduler_authority"], "NONE")
        self.assertEqual(projection["effect_authority"], "NONE")
        self.assertEqual(projection["completion_authority"], "NONE")
        self.assertEqual(projection["runtime_credit"], 0)
        self.assertFalse(projection["whole_system_acceptance"])

    def test_no_explicit_unfinished_work_holds(self):
        previous, persisted, seal, outcome = fixture_case(unfinished=False)
        candidate = plan_restart_recovery(
            candidate_id="recovery-wp901-hold",
            previous_checkpoint=previous,
            persisted_checkpoint=persisted,
            loop_seal=seal,
            outcome=outcome,
            provenance_refs=("test:wp901:hold",),
        )
        self.assertEqual(candidate.transition, TRANSITION_HOLD)
        self.assertEqual(candidate.unfinished_work_refs, ())

    def test_unknown_external_effect_forces_observe_and_forbids_replay(self):
        previous, persisted, seal, outcome = fixture_case(outcome=unknown_outcome())
        candidate = plan_restart_recovery(
            candidate_id="recovery-wp901-unknown",
            previous_checkpoint=previous,
            persisted_checkpoint=persisted,
            loop_seal=seal,
            outcome=outcome,
            provenance_refs=("test:wp901:unknown-plan",),
        )
        self.assertEqual(candidate.transition, TRANSITION_OBSERVE)
        self.assertEqual(candidate.replay_disposition, REPLAY_FORBIDDEN_UNVERIFIED)
        self.assertIn("UNKNOWN_EXTERNAL_EFFECT", candidate.reason)

    def test_observed_but_unverified_result_forces_observe(self):
        previous, persisted, seal, outcome = fixture_case(
            outcome=result_observed_outcome()
        )
        candidate = plan_restart_recovery(
            candidate_id="recovery-wp901-observed",
            previous_checkpoint=previous,
            persisted_checkpoint=persisted,
            loop_seal=seal,
            outcome=outcome,
            provenance_refs=("test:wp901:observed-plan",),
        )
        self.assertEqual(candidate.transition, TRANSITION_OBSERVE)
        self.assertEqual(candidate.replay_disposition, REPLAY_FORBIDDEN_UNVERIFIED)

    def test_mismatched_outcome_digest_fails_closed(self):
        previous, persisted, seal, outcome = fixture_case()
        other = no_effect_outcome(outcome_id="different-outcome")
        with self.assertRaisesRegex(RestartRecoveryError, "outcome id mismatch"):
            plan_restart_recovery(
                candidate_id="recovery-wp901-bad-outcome",
                previous_checkpoint=previous,
                persisted_checkpoint=persisted,
                loop_seal=seal,
                outcome=other,
                provenance_refs=("test:wp901:bad-outcome",),
            )

    def test_non_direct_successor_fails_closed(self):
        previous, persisted, seal, outcome = fixture_case()
        wrong_parent = replace(persisted, previous_checkpoint_id="wrong-parent")
        with self.assertRaisesRegex(RestartRecoveryError, "not an exact direct successor"):
            plan_restart_recovery(
                candidate_id="recovery-wp901-wrong-parent",
                previous_checkpoint=previous,
                persisted_checkpoint=wrong_parent,
                loop_seal=seal,
                outcome=outcome,
                provenance_refs=("test:wp901:wrong-parent",),
            )

    def test_missing_persisted_reentry_evidence_fails_closed(self):
        previous, persisted, seal, outcome = fixture_case()
        stripped = replace(persisted, provenance_refs=(checkpoint_ref(previous),))
        # Rebind the seal to the exact stripped checkpoint so the failure discriminator
        # reaches the persisted re-entry subset check rather than the checkpoint digest fence.
        stripped_seal = replace(
            seal,
            next_checkpoint_sha256=stripped.sha256(),
        )
        with self.assertRaisesRegex(RestartRecoveryError, "lacks exact WP900 loop re-entry evidence"):
            plan_restart_recovery(
                candidate_id="recovery-wp901-missing-reentry",
                previous_checkpoint=previous,
                persisted_checkpoint=stripped,
                loop_seal=stripped_seal,
                outcome=outcome,
                provenance_refs=("test:wp901:missing-reentry",),
            )

    def test_same_inputs_produce_same_candidate_digest(self):
        previous, persisted, seal, outcome = fixture_case()
        kwargs = dict(
            candidate_id="recovery-wp901-deterministic",
            previous_checkpoint=previous,
            persisted_checkpoint=persisted,
            loop_seal=seal,
            outcome=outcome,
            provenance_refs=("test:wp901:deterministic",),
        )
        first = plan_restart_recovery(**kwargs)
        second = plan_restart_recovery(**kwargs)
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(first.as_dict(), second.as_dict())


if __name__ == "__main__":
    unittest.main()
