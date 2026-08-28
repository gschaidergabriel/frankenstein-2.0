from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.deferred_return import DeferredReturnEnvelope
from frankenstein2.deferred_execution_verification import (
    CorrelatedVerification,
    DeferredExecutionVerificationError,
    DeferredExecutionVerificationTarget,
    apply_correlated_verification,
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


RESULT_DIGEST = "a" * 64
VERIFICATION_DIGEST = "b" * 64


def make_return(*, suffix: str, task_id: str, turn_id: str) -> DeferredReturnEnvelope:
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
    bound = pending.bind_result(
        invocation_id=pending.invocation_id,
        delegation_id=pending.delegation_id,
        child_causal_id=child.causal_id,
        result_id="same-result-id",
        result_sha256=RESULT_DIGEST,
    )
    resume = child.derive(
        causal_id=f"resume-{suffix}",
        generation=6,
        agent_id=parent.agent_id,
        task_id=parent.task_id,
        turn_id=f"resume-turn-{suffix}",
    )
    return DeferredReturnEnvelope(
        return_id=f"return-{suffix}",
        binding=bound,
        resume=resume,
    )


def execution_record(returned: DeferredReturnEnvelope) -> ExecutionLineage:
    child = returned.binding.child
    record = ExecutionLineage.requested(
        causal_id=child.causal_id,
        generation=child.generation,
        request_id="shared-request-id",
    )
    record = apply_execution_transition(
        record,
        AdmitExecution(
            transition_id="shared-admit-transition",
            causal_id=record.causal_id,
            generation=record.generation,
            request_id=record.request_id,
            admission_id="shared-admission-id",
        ),
    )
    return apply_execution_transition(
        record,
        RecordExecution(
            transition_id="shared-execution-transition",
            causal_id=record.causal_id,
            generation=record.generation,
            request_id=record.request_id,
            admission_id=record.admission_id,
            execution_attempt_id="shared-execution-attempt",
            outcome=ExecutionOutcome.REPORTED_SUCCESS,
        ),
    )


def final_verification(record: ExecutionLineage) -> VerifyExecution:
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
            evidence_ref="evidence/self-claimed-effect-journal.json",
            evidence_sha256=VERIFICATION_DIGEST,
        ),
    )


def indeterminate_verification(record: ExecutionLineage) -> VerifyExecution:
    return VerifyExecution(
        transition_id="shared-indeterminate-transition",
        causal_id=record.causal_id,
        generation=record.generation,
        request_id=record.request_id,
        admission_id=record.admission_id,
        execution_attempt_id=record.execution_attempt_id,
        verification_attempt_id="shared-indeterminate-attempt",
        outcome=VerificationOutcome.INDETERMINATE,
        receipt=None,
    )


class DeferredExecutionVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.return_a = make_return(suffix="A", task_id="task-A", turn_id="turn-A")
        self.return_b = make_return(suffix="B", task_id="task-B", turn_id="turn-B")
        self.target_a = DeferredExecutionVerificationTarget(
            returned=self.return_a,
            lineage=execution_record(self.return_a),
        )
        self.target_b = DeferredExecutionVerificationTarget(
            returned=self.return_b,
            lineage=execution_record(self.return_b),
        )
        self.final_a = CorrelatedVerification.for_target(
            self.target_a, final_verification(self.target_a.lineage)
        )
        self.final_b = CorrelatedVerification.for_target(
            self.target_b, final_verification(self.target_b.lineage)
        )

    def test_generic_wp105_records_are_deliberately_identical(self) -> None:
        self.assertEqual(self.target_a.lineage, self.target_b.lineage)
        self.assertEqual(
            self.return_a.binding.result_sha256,
            self.return_b.binding.result_sha256,
        )
        self.assertEqual(self.return_a.binding.result_id, self.return_b.binding.result_id)
        self.assertNotEqual(
            self.return_a.binding.binding_id(),
            self.return_b.binding.binding_id(),
        )
        self.assertNotEqual(
            self.return_a.binding.child.sha256(),
            self.return_b.binding.child.sha256(),
        )

    def test_call_b_observation_cannot_mutate_call_a(self) -> None:
        before = self.target_a
        with self.assertRaises(DeferredExecutionVerificationError):
            apply_correlated_verification(self.target_a, self.final_b)
        self.assertEqual(self.target_a, before)
        self.assertEqual(self.target_a.lineage.stage, ExecutionStage.EXECUTION_RECORDED)
        self.assertFalse(self.target_a.lineage.is_verified_complete)

    def test_self_classified_final_receipt_cannot_mint_completion(self) -> None:
        before = self.target_a
        with self.assertRaisesRegex(
            DeferredExecutionVerificationError,
            "FINAL_VERIFICATION_AUTHORITY_ADMISSION_REQUIRED",
        ):
            apply_correlated_verification(self.target_a, self.final_a)
        self.assertEqual(self.target_a, before)
        self.assertEqual(self.target_a.lineage.stage, ExecutionStage.EXECUTION_RECORDED)
        self.assertFalse(self.target_a.lineage.is_verified_complete)

    def test_indeterminate_verification_remains_nonfinal_and_idempotent(self) -> None:
        observed = CorrelatedVerification.for_target(
            self.target_a, indeterminate_verification(self.target_a.lineage)
        )
        once = apply_correlated_verification(self.target_a, observed)
        twice = apply_correlated_verification(once, observed)
        self.assertEqual(once, twice)
        self.assertEqual(once.lineage.stage, ExecutionStage.EXECUTION_RECORDED)
        self.assertFalse(once.lineage.is_verified_complete)

    def test_copied_return_id_still_cannot_hide_binding_mismatch(self) -> None:
        forged = CorrelatedVerification(
            return_id=self.final_a.return_id,
            binding_id=self.final_b.binding_id,
            invocation_id=self.final_b.invocation_id,
            tool_use_id=self.final_b.tool_use_id,
            delegation_id=self.final_b.delegation_id,
            child_identity_sha256=self.final_b.child_identity_sha256,
            result_id=self.final_b.result_id,
            result_sha256=self.final_b.result_sha256,
            transition=self.final_b.transition,
        )
        with self.assertRaisesRegex(
            DeferredExecutionVerificationError, "BINDING_ID_MISMATCH"
        ):
            apply_correlated_verification(self.target_a, forged)

    def test_target_rejects_wrong_child_generation_before_verification(self) -> None:
        wrong = ExecutionLineage.requested(
            causal_id=self.return_a.binding.child.causal_id,
            generation=self.return_a.binding.child.generation + 1,
            request_id="wrong-generation-request",
        )
        with self.assertRaisesRegex(
            DeferredExecutionVerificationError, "lineage generation"
        ):
            DeferredExecutionVerificationTarget(returned=self.return_a, lineage=wrong)


if __name__ == "__main__":
    unittest.main(verbosity=2)
