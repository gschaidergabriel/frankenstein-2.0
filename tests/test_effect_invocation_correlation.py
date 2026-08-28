from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.deferred_causal_return import DeferredCausalReturn
from frankenstein2.deferred_execution_verification import DeferredExecutionVerificationTarget
from frankenstein2.effect_invocation_correlation import (
    EffectCorrelationStage,
    EffectInvocationCorrelationError,
    apply_effect_bound_verification,
    bind_effect_return,
    observe_effect_result,
    prepare_effect_call,
)
from frankenstein2.native_child_binding import NativeChildBinding
from state.execution_completion import (
    VERIFICATION_RECEIPT_SCHEMA,
    AdmitExecution,
    ExecutionLineage,
    ExecutionOutcome,
    ExecutionStage,
    RecordExecution,
    VerificationEvidenceKind,
    VerificationOutcome,
    VerificationReceipt,
    VerifyExecution,
    apply_execution_transition,
)


SAME_RESULT_ID = "same-result-id"
SAME_RESULT_DIGEST = "a" * 64
VERIFICATION_DIGEST = "b" * 64


def make_pending_call(
    *, suffix: str, task_id: str, turn_id: str
) -> tuple[NativeChildBinding, CausalIdentity, ExecutionLineage]:
    parent = CausalIdentity(
        session_id="shared-session",
        agent_id="parent-agent",
        task_id=task_id,
        turn_id=turn_id,
        causal_id="shared-parent-causal",
        generation=4,
    )
    child = parent.derive(
        causal_id="shared-child-causal",
        generation=5,
        agent_id="child-agent",
        task_id=f"child-task-{suffix}",
        turn_id=f"child-turn-{suffix}",
    )
    pending = NativeChildBinding(
        workpackage_id="F2-WP-102",
        workpackage_generation=1,
        claim_id="claim-wp102-g1",
        parent=parent,
        invocation_id=f"invocation-{suffix}",
        tool_use_id=f"tool-use-{suffix}",
        delegation_id=f"delegation-{suffix}",
        child=child,
    )
    lineage = ExecutionLineage.requested(
        causal_id=child.causal_id,
        generation=child.generation,
        request_id="shared-request-id",
    )
    lineage = apply_execution_transition(
        lineage,
        AdmitExecution(
            transition_id="shared-admit-transition",
            causal_id=lineage.causal_id,
            generation=lineage.generation,
            request_id=lineage.request_id,
            admission_id="shared-admission-id",
        ),
    )
    return pending, child, lineage


def make_target(*, suffix: str, task_id: str, turn_id: str) -> DeferredExecutionVerificationTarget:
    pending, child, lineage = make_pending_call(
        suffix=suffix,
        task_id=task_id,
        turn_id=turn_id,
    )
    bound = pending.bind_result(
        invocation_id=pending.invocation_id,
        delegation_id=pending.delegation_id,
        child_causal_id=child.causal_id,
        result_id=SAME_RESULT_ID,
        result_sha256=SAME_RESULT_DIGEST,
    )
    resume = child.derive(
        causal_id=f"resume-{suffix}",
        generation=6,
        agent_id=pending.parent.agent_id,
        task_id=pending.parent.task_id,
        turn_id=f"resume-turn-{suffix}",
    )
    returned = DeferredCausalReturn(
        return_id=f"return-{suffix}",
        binding=bound,
        resume=resume,
    )
    lineage = apply_execution_transition(
        lineage,
        RecordExecution(
            transition_id="shared-execution-transition",
            causal_id=lineage.causal_id,
            generation=lineage.generation,
            request_id=lineage.request_id,
            admission_id=lineage.admission_id,
            execution_attempt_id="shared-execution-attempt",
            outcome=ExecutionOutcome.REPORTED_SUCCESS,
        ),
    )
    return DeferredExecutionVerificationTarget(returned=returned, lineage=lineage)


def verification(target: DeferredExecutionVerificationTarget) -> VerifyExecution:
    record = target.lineage
    attempt = "shared-verification-attempt"
    return VerifyExecution(
        transition_id="shared-verification-transition",
        causal_id=record.causal_id,
        generation=record.generation,
        request_id=record.request_id,
        admission_id=record.admission_id,
        execution_attempt_id=record.execution_attempt_id,
        verification_attempt_id=attempt,
        outcome=VerificationOutcome.APPLIED,
        receipt=VerificationReceipt(
            schema=VERIFICATION_RECEIPT_SCHEMA,
            receipt_id="shared-verification-receipt",
            verification_attempt_id=attempt,
            execution_attempt_id=record.execution_attempt_id,
            execution_outcome=record.execution_outcome,
            outcome=VerificationOutcome.APPLIED,
            evidence_kind=VerificationEvidenceKind.EFFECT_JOURNAL_VERIFIED,
            evidence_ref="evidence/shared-effect-journal.json",
            evidence_sha256=VERIFICATION_DIGEST,
        ),
    )


def observe(prepared):
    return observe_effect_result(
        prepared,
        effect_id=prepared.effect_id,
        observed_invocation_id=prepared.invocation_id,
        observed_tool_use_id=prepared.tool_use_id,
        observed_delegation_id=prepared.delegation_id,
        observed_binding_id=prepared.binding_id,
        observed_child_identity_sha256=prepared.child_identity_sha256,
        result_id=SAME_RESULT_ID,
        result_sha256=SAME_RESULT_DIGEST,
    )


class EffectInvocationCorrelationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target_a = make_target(suffix="A", task_id="task-A", turn_id="turn-A")
        self.target_b = make_target(suffix="B", task_id="task-B", turn_id="turn-B")
        self.pre_a = prepare_effect_call(self.target_a, effect_id="effect-A")
        self.pre_b = prepare_effect_call(self.target_b, effect_id="effect-B")
        self.post_a = observe(self.pre_a)
        self.post_b = observe(self.pre_b)

    def test_true_pre_dispatch_binding_exists_before_result_and_record_execution(self) -> None:
        pending, child, admitted = make_pending_call(
            suffix="PRE",
            task_id="task-PRE",
            turn_id="turn-PRE",
        )
        self.assertFalse(pending.has_result)
        self.assertEqual(admitted.stage, ExecutionStage.ADMITTED)
        self.assertIsNone(admitted.execution_attempt_id)

        prepared = prepare_effect_call(pending, effect_id="effect-PRE")
        self.assertEqual(prepared.stage, EffectCorrelationStage.PREPARED)
        self.assertIsNone(prepared.return_id)
        self.assertEqual(prepared.binding_id, pending.binding_id())

        observed = observe(prepared)
        self.assertEqual(observed.stage, EffectCorrelationStage.RESULT_OBSERVED)
        self.assertIsNone(observed.return_id)

        bound = pending.bind_result(
            invocation_id=pending.invocation_id,
            delegation_id=pending.delegation_id,
            child_causal_id=child.causal_id,
            result_id=observed.result_id or "",
            result_sha256=observed.result_sha256 or "",
        )
        resume = child.derive(
            causal_id="resume-PRE",
            generation=6,
            agent_id=pending.parent.agent_id,
            task_id=pending.parent.task_id,
            turn_id="resume-turn-PRE",
        )
        returned = DeferredCausalReturn(
            return_id="return-PRE",
            binding=bound,
            resume=resume,
        )
        recorded = apply_execution_transition(
            admitted,
            RecordExecution(
                transition_id="pre-execution-transition",
                causal_id=admitted.causal_id,
                generation=admitted.generation,
                request_id=admitted.request_id,
                admission_id=admitted.admission_id,
                execution_attempt_id="pre-execution-attempt",
                outcome=ExecutionOutcome.REPORTED_SUCCESS,
            ),
        )
        target = DeferredExecutionVerificationTarget(returned=returned, lineage=recorded)

        with self.assertRaisesRegex(
            EffectInvocationCorrelationError,
            "VERIFICATION_REQUIRES_RETURN_BINDING",
        ):
            apply_effect_bound_verification(target, observed, verification(target))

        return_bound = bind_effect_return(observed, target)
        self.assertEqual(return_bound.return_id, returned.return_id)
        verified = apply_effect_bound_verification(
            target,
            return_bound,
            verification(target),
        )
        self.assertEqual(verified.lineage.stage, ExecutionStage.VERIFIED_APPLIED)

    def test_true_pre_dispatch_path_rejects_already_result_bound_binding(self) -> None:
        with self.assertRaisesRegex(
            EffectInvocationCorrelationError,
            "PRE_DISPATCH_BINDING_MUST_BE_RESULT_FREE",
        ):
            prepare_effect_call(
                self.target_a.returned.binding,
                effect_id="effect-too-late",
            )

    def test_test_fixture_defeats_session_and_digest_only_correlation(self) -> None:
        self.assertEqual(self.target_a.lineage, self.target_b.lineage)
        self.assertEqual(
            self.target_a.returned.binding.result_sha256,
            self.target_b.returned.binding.result_sha256,
        )
        self.assertEqual(
            self.target_a.returned.binding.result_id,
            self.target_b.returned.binding.result_id,
        )
        self.assertNotEqual(self.pre_a.effect_id, self.pre_b.effect_id)
        self.assertNotEqual(self.pre_a.invocation_id, self.pre_b.invocation_id)
        self.assertNotEqual(self.pre_a.binding_id, self.pre_b.binding_id)

    def test_effect_id_mismatch_rejected_at_post_before_state_change(self) -> None:
        before = self.pre_a
        with self.assertRaisesRegex(EffectInvocationCorrelationError, "EFFECT_ID_MISMATCH"):
            observe_effect_result(
                self.pre_a,
                effect_id="effect-B",
                observed_invocation_id=self.pre_a.invocation_id,
                observed_tool_use_id=self.pre_a.tool_use_id,
                observed_delegation_id=self.pre_a.delegation_id,
                observed_binding_id=self.pre_a.binding_id,
                observed_child_identity_sha256=self.pre_a.child_identity_sha256,
                result_id=SAME_RESULT_ID,
                result_sha256=SAME_RESULT_DIGEST,
            )
        self.assertEqual(self.pre_a, before)
        self.assertEqual(self.pre_a.stage, EffectCorrelationStage.PREPARED)

    def test_call_b_post_cannot_verify_call_a(self) -> None:
        before = self.target_a
        with self.assertRaises(EffectInvocationCorrelationError):
            apply_effect_bound_verification(
                self.target_a,
                self.post_b,
                verification(self.target_a),
            )
        self.assertEqual(self.target_a, before)
        self.assertEqual(self.target_a.lineage.stage, ExecutionStage.EXECUTION_RECORDED)
        self.assertFalse(self.target_a.lineage.is_verified_complete)

    def test_same_session_interleaving_b_then_a_preserves_call_lineage(self) -> None:
        # Explicit overlapping-call falsifier: both calls share the same session and
        # deliberately identical generic execution/result identities, then complete in
        # reverse order. Exact call identity must still keep B from contaminating A.
        verified_b = apply_effect_bound_verification(
            self.target_b,
            self.post_b,
            verification(self.target_b),
        )
        with self.assertRaises(EffectInvocationCorrelationError):
            apply_effect_bound_verification(
                self.target_a,
                self.post_b,
                verification(self.target_a),
            )
        verified_a = apply_effect_bound_verification(
            self.target_a,
            self.post_a,
            verification(self.target_a),
        )
        self.assertEqual(verified_b.lineage.stage, ExecutionStage.VERIFIED_APPLIED)
        self.assertEqual(verified_a.lineage.stage, ExecutionStage.VERIFIED_APPLIED)
        self.assertNotEqual(self.post_a.effect_id, self.post_b.effect_id)
        self.assertNotEqual(self.post_a.tool_use_id, self.post_b.tool_use_id)

    def test_prepared_only_cannot_verify(self) -> None:
        with self.assertRaisesRegex(
            EffectInvocationCorrelationError, "VERIFICATION_REQUIRES_POST_RESULT"
        ):
            apply_effect_bound_verification(
                self.target_a,
                self.pre_a,
                verification(self.target_a),
            )

    def test_exact_post_observation_replay_is_idempotent(self) -> None:
        replay = observe(self.post_a)
        self.assertIs(replay, self.post_a)

    def test_matched_pre_post_calls_verify_independently(self) -> None:
        verified_a = apply_effect_bound_verification(
            self.target_a,
            self.post_a,
            verification(self.target_a),
        )
        verified_b = apply_effect_bound_verification(
            self.target_b,
            self.post_b,
            verification(self.target_b),
        )
        self.assertEqual(verified_a.lineage.stage, ExecutionStage.VERIFIED_APPLIED)
        self.assertEqual(verified_b.lineage.stage, ExecutionStage.VERIFIED_APPLIED)

    def test_exact_verified_transition_replay_remains_idempotent(self) -> None:
        once = apply_effect_bound_verification(
            self.target_a,
            self.post_a,
            verification(self.target_a),
        )
        twice = apply_effect_bound_verification(
            once,
            self.post_a,
            verification(self.target_a),
        )
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main(verbosity=2)
