from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.completion_evidence_gate import (
    CompletionEvidenceGateError,
    EffectJournalSuccessEvidence,
    admit_current_effect_journal_verification,
    apply_admitted_effect_bound_verification,
)
from frankenstein2.current_entityos_effect_authority_binding import (
    CurrentEntityOSEffectAuthorityBinding,
)
from frankenstein2.deferred_return import DeferredReturnEnvelope
from frankenstein2.deferred_execution_verification import (
    CorrelatedVerification,
    DeferredExecutionVerificationError,
    DeferredExecutionVerificationTarget,
    apply_correlated_verification,
)
from frankenstein2.effect_invocation_correlation import (
    EffectCallBinding,
    EffectCorrelationStage,
)
from frankenstein2.native_child_binding import NativeChildBinding
from frankenstein2.structured_execution_receipt import (
    StructuredExecutionReceipt,
    apply_structured_execution_receipt,
)
from state.execution_completion import (
    VERIFICATION_RECEIPT_SCHEMA,
    AdmitExecution,
    ExecutionLineage,
    ExecutionStage,
    VerificationEvidenceKind,
    VerificationOutcome,
    VerificationReceipt,
    VerifyExecution,
    apply_execution_transition,
)


RESULT_SHA = "a" * 64
EVIDENCE_SHA = "b" * 64


def build_target_and_observed() -> tuple[
    DeferredExecutionVerificationTarget, EffectCallBinding
]:
    parent = CausalIdentity(
        session_id="session-A",
        agent_id="parent-A",
        task_id="task-A",
        turn_id="turn-A",
        causal_id="parent-causal-A",
        generation=4,
    )
    child = parent.derive(
        causal_id="child-causal-A",
        generation=5,
        agent_id="child-A",
        task_id="child-task-A",
        turn_id="child-turn-A",
    )
    pending = NativeChildBinding(
        workpackage_id="F2-WP-102",
        workpackage_generation=1,
        claim_id="claim-wp102-g1",
        parent=parent,
        invocation_id="invocation-A",
        tool_use_id="tool-A",
        delegation_id="delegation-A",
        child=child,
    )
    bound = pending.bind_result(
        invocation_id=pending.invocation_id,
        delegation_id=pending.delegation_id,
        child_causal_id=child.causal_id,
        result_id="result-A",
        result_sha256=RESULT_SHA,
    )
    returned = DeferredReturnEnvelope(
        return_id="return-A",
        binding=bound,
        resume=child.derive(
            causal_id="resume-A",
            generation=6,
            agent_id=parent.agent_id,
            task_id=parent.task_id,
            turn_id="resume-turn-A",
        ),
    )

    lineage = ExecutionLineage.requested(
        causal_id=child.causal_id,
        generation=child.generation,
        request_id="request-A",
    )
    lineage = apply_execution_transition(
        lineage,
        AdmitExecution(
            transition_id="admit-A",
            causal_id=lineage.causal_id,
            generation=lineage.generation,
            request_id=lineage.request_id,
            admission_id="admission-A",
        ),
    )
    prepared = EffectCallBinding(
        effect_id="canonical-effect-A",
        return_id=returned.return_id,
        binding_id=bound.binding_id(),
        invocation_id=bound.invocation_id,
        tool_use_id=bound.tool_use_id,
        delegation_id=bound.delegation_id,
        child_identity_sha256=child.sha256(),
        stage=EffectCorrelationStage.PREPARED,
    )
    execution_receipt = StructuredExecutionReceipt(
        receipt_id="executor-receipt-A",
        effect_id=prepared.effect_id,
        binding_id=prepared.binding_id,
        invocation_id=prepared.invocation_id,
        tool_use_id=prepared.tool_use_id,
        delegation_id=prepared.delegation_id,
        child_identity_sha256=prepared.child_identity_sha256,
        causal_id=lineage.causal_id,
        generation=lineage.generation,
        request_id=lineage.request_id,
        admission_id=lineage.admission_id or "",
        execution_attempt_id="execution-attempt-A",
        raw_status="SUCCEEDED",
        result_id="result-A",
        result_sha256=RESULT_SHA,
    )
    execution = apply_structured_execution_receipt(
        prepared,
        lineage,
        execution_receipt,
    )
    target = DeferredExecutionVerificationTarget(
        returned=returned,
        lineage=execution.lineage,
    )
    return target, execution.observed_call


def current_binding() -> CurrentEntityOSEffectAuthorityBinding:
    return CurrentEntityOSEffectAuthorityBinding(
        binding_repository="gschaidergabriel/clay-global-research-entity",
        binding_record_path="research_entity/runtime/ENTITYOS_EFFECT_AUTHORITY_BINDING.json",
        binding_record_blob_sha="1" * 40,
        binding_record_commit_sha="2" * 40,
        current_epoch_attestation_path="research_entity/runtime/ENTITYOS_EFFECT_AUTHORITY_ATTESTATION.json",
        current_epoch_attestation_commit_sha="3" * 40,
        implementation_commit_sha="4" * 40,
        effect_gate_path="clayverse/effects.py",
        effect_gate_blob_sha="5" * 40,
        effect_journal_path="clayverse/effect_journal.py",
        effect_journal_blob_sha="6" * 40,
        unifieddb_path="clayverse/store.py",
        unifieddb_blob_sha="7" * 40,
        unifieddb_schema_version="13",
        api_version="ENTITYOS_EFFECT_AUTHORITY_PY_API/v1",
        supervisor_epoch="9.13",
        supervisor_delta="CURRENT_ADMITTED_STEERING_AUTHORITY",
    )


def final_transition(
    target: DeferredExecutionVerificationTarget,
    *,
    evidence_kind: VerificationEvidenceKind = VerificationEvidenceKind.EFFECT_JOURNAL_VERIFIED,
    outcome: VerificationOutcome = VerificationOutcome.APPLIED,
    evidence_sha256: str = EVIDENCE_SHA,
) -> VerifyExecution:
    line = target.lineage
    receipt = VerificationReceipt(
        schema=VERIFICATION_RECEIPT_SCHEMA,
        receipt_id="verification-receipt-A",
        verification_attempt_id="verification-attempt-A",
        execution_attempt_id=line.execution_attempt_id or "",
        execution_outcome=line.execution_outcome,
        outcome=outcome,
        evidence_kind=evidence_kind,
        evidence_ref="journal/effect-A/verified",
        evidence_sha256=evidence_sha256,
    )
    return VerifyExecution(
        transition_id="verify-A",
        causal_id=line.causal_id,
        generation=line.generation,
        request_id=line.request_id,
        admission_id=line.admission_id or "",
        execution_attempt_id=line.execution_attempt_id or "",
        verification_attempt_id=receipt.verification_attempt_id,
        outcome=outcome,
        receipt=receipt,
    )


def journal_evidence(
    target: DeferredExecutionVerificationTarget,
    observed: EffectCallBinding,
    transition: VerifyExecution,
) -> EffectJournalSuccessEvidence:
    assert transition.receipt is not None
    return EffectJournalSuccessEvidence(
        effect_id=observed.effect_id,
        journal_status="VERIFIED",
        execution_attempt_id=target.lineage.execution_attempt_id or "",
        verification_attempt_id=transition.verification_attempt_id,
        evidence_ref=transition.receipt.evidence_ref,
        evidence_sha256=transition.receipt.evidence_sha256,
    )


class CompletionEvidenceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target, self.observed = build_target_and_observed()
        self.transition = final_transition(self.target)
        self.journal = journal_evidence(self.target, self.observed, self.transition)

    def test_structured_executor_success_is_still_nonfinal(self) -> None:
        self.assertEqual(self.target.lineage.stage, ExecutionStage.EXECUTION_RECORDED)
        self.assertFalse(self.target.lineage.is_verified_complete)

    def test_self_classified_final_receipt_without_admission_fails_closed(self) -> None:
        correlated = CorrelatedVerification(
            return_id=self.target.returned.return_id,
            binding_id=self.observed.binding_id,
            invocation_id=self.observed.invocation_id,
            tool_use_id=self.observed.tool_use_id,
            delegation_id=self.observed.delegation_id,
            child_identity_sha256=self.observed.child_identity_sha256,
            result_id=self.observed.result_id or "",
            result_sha256=self.observed.result_sha256 or "",
            transition=self.transition,
        )
        with self.assertRaisesRegex(
            DeferredExecutionVerificationError,
            "FINAL_VERIFICATION_AUTHORITY_ADMISSION_REQUIRED",
        ):
            apply_correlated_verification(self.target, correlated)
        self.assertFalse(self.target.lineage.is_verified_complete)

    def test_current_effect_journal_verified_bijection_can_finalize_applied(self) -> None:
        admission = admit_current_effect_journal_verification(
            self.observed,
            self.transition,
            authority_binding=current_binding(),
            journal_evidence=self.journal,
        )
        verified = apply_admitted_effect_bound_verification(
            self.target,
            self.observed,
            self.transition,
            admission=admission,
        )
        self.assertEqual(verified.lineage.stage, ExecutionStage.VERIFIED_APPLIED)
        self.assertTrue(verified.lineage.is_verified_complete)
        replay = apply_admitted_effect_bound_verification(
            verified,
            self.observed,
            self.transition,
            admission=admission,
        )
        self.assertEqual(verified, replay)

    def test_non_journal_final_evidence_classes_are_not_currently_admitted(self) -> None:
        for kind in (
            VerificationEvidenceKind.EXTERNAL_OBSERVATION_VERIFIED,
            VerificationEvidenceKind.DETERMINISTIC_STATE_VERIFIED,
            VerificationEvidenceKind.EXECUTOR_REPORT,
            VerificationEvidenceKind.TRANSPORT_STATUS,
        ):
            with self.subTest(kind=kind):
                transition = final_transition(self.target, evidence_kind=kind)
                journal = journal_evidence(self.target, self.observed, transition)
                with self.assertRaisesRegex(
                    CompletionEvidenceGateError,
                    "FINAL_EVIDENCE_AUTHORITY_CLASS_UNADMITTED",
                ):
                    admit_current_effect_journal_verification(
                        self.observed,
                        transition,
                        authority_binding=current_binding(),
                        journal_evidence=journal,
                    )

    def test_not_applied_is_not_silently_inferred_from_success_journal(self) -> None:
        transition = final_transition(
            self.target,
            outcome=VerificationOutcome.NOT_APPLIED,
        )
        journal = journal_evidence(self.target, self.observed, transition)
        with self.assertRaisesRegex(
            CompletionEvidenceGateError,
            "ONLY_VERIFIED_APPLIED_SUCCESS_IS_CURRENTLY_ADMITTED",
        ):
            admit_current_effect_journal_verification(
                self.observed,
                transition,
                authority_binding=current_binding(),
                journal_evidence=journal,
            )

    def test_journal_effect_identity_mismatch_fails_before_state_change(self) -> None:
        wrong = replace(self.journal, effect_id="canonical-effect-B")
        with self.assertRaisesRegex(
            CompletionEvidenceGateError,
            "JOURNAL_EFFECT_ID_MISMATCH",
        ):
            admit_current_effect_journal_verification(
                self.observed,
                self.transition,
                authority_binding=current_binding(),
                journal_evidence=wrong,
            )
        self.assertFalse(self.target.lineage.is_verified_complete)

    def test_journal_evidence_digest_mismatch_fails_before_state_change(self) -> None:
        wrong = replace(self.journal, evidence_sha256="c" * 64)
        with self.assertRaisesRegex(
            CompletionEvidenceGateError,
            "JOURNAL_EVIDENCE_SHA256_MISMATCH",
        ):
            admit_current_effect_journal_verification(
                self.observed,
                self.transition,
                authority_binding=current_binding(),
                journal_evidence=wrong,
            )
        self.assertFalse(self.target.lineage.is_verified_complete)

    def test_nonverified_journal_status_cannot_be_constructed_as_success(self) -> None:
        with self.assertRaisesRegex(
            CompletionEvidenceGateError,
            "JOURNAL_SUCCESS_REQUIRES_VERIFIED_STATUS",
        ):
            EffectJournalSuccessEvidence(
                effect_id=self.observed.effect_id,
                journal_status="PENDING",
                execution_attempt_id=self.target.lineage.execution_attempt_id or "",
                verification_attempt_id=self.transition.verification_attempt_id,
                evidence_ref="journal/effect-A/pending",
                evidence_sha256=EVIDENCE_SHA,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
