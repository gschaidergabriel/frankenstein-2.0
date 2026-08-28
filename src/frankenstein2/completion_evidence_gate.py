"""Current-authority admission gate for WP105 final completion evidence.

A generic ``VerificationReceipt`` is only an evidence envelope. It must not gain final
completion power merely because its caller selected a finalizing enum. This module
narrows the current path to the one authority class Frankenstein 2.0 can presently bind
explicitly: the already-admitted canonical EntityOS EffectJournal implementation.

The gate does not read the journal, verify the world, execute an effect, persist state,
or mint canonical authority. It consumes a separately verified
``CurrentEntityOSEffectAuthorityBinding`` and binds that authority identity to the exact
verification receipt and exact observed effect call. Other final evidence classes fail
closed until equivalent current-authority bindings exist for them. The existing immutable
WP105 transition remains the only completion state machine.
"""
from __future__ import annotations

from state.execution_completion import (
    VerificationEvidenceKind,
    VerificationOutcome,
    VerificationReceipt,
    VerifyExecution,
)

from .completion_evidence_types import (
    CompletionAuthorityClass,
    CompletionEvidenceAdmission,
    CompletionEvidenceAdmissionError,
    _mint_completion_evidence_admission,
)
from .current_entityos_effect_authority_binding import CurrentEntityOSEffectAuthorityBinding
from .deferred_execution_verification import (
    CorrelatedVerification,
    DeferredExecutionVerificationError,
    DeferredExecutionVerificationTarget,
    apply_correlated_verification,
)
from .effect_invocation_correlation import EffectCallBinding, EffectCorrelationStage


class CompletionEvidenceGateError(RuntimeError):
    """Final evidence is not admitted for this exact current call."""


def _effect_journal_authority_ref(binding: CurrentEntityOSEffectAuthorityBinding) -> str:
    return (
        f"{binding.binding_repository}@{binding.implementation_commit_sha}:"
        f"{binding.effect_journal_path}#{binding.effect_journal_blob_sha}:"
        f"attestation@{binding.current_epoch_attestation_commit_sha}:"
        f"epoch={binding.supervisor_epoch}:{binding.supervisor_delta}"
    )


def admit_current_effect_journal_verification(
    observed: EffectCallBinding,
    transition: VerifyExecution,
    *,
    authority_binding: CurrentEntityOSEffectAuthorityBinding,
) -> CompletionEvidenceAdmission:
    """Admit one final receipt only against the resolved current EffectJournal tuple."""
    if not isinstance(observed, EffectCallBinding):
        raise CompletionEvidenceGateError("INVALID_OBSERVED_EFFECT_CALL")
    if observed.stage is not EffectCorrelationStage.RESULT_OBSERVED:
        raise CompletionEvidenceGateError("FINAL_ADMISSION_REQUIRES_OBSERVED_RESULT")
    if not isinstance(transition, VerifyExecution):
        raise CompletionEvidenceGateError("INVALID_VERIFICATION_TRANSITION")
    if transition.outcome not in (
        VerificationOutcome.APPLIED,
        VerificationOutcome.NOT_APPLIED,
    ):
        raise CompletionEvidenceGateError("FINAL_ADMISSION_REQUIRES_FINAL_OUTCOME")
    receipt = transition.receipt
    if not isinstance(receipt, VerificationReceipt):
        raise CompletionEvidenceGateError("FINAL_ADMISSION_REQUIRES_STRUCTURED_RECEIPT")
    if not isinstance(authority_binding, CurrentEntityOSEffectAuthorityBinding):
        raise CompletionEvidenceGateError("CURRENT_EFFECT_AUTHORITY_BINDING_REQUIRED")

    # The generic state layer knows additional potentially-final evidence classes, but
    # F2 currently has an explicit current-authority binding only for the canonical
    # EntityOS EffectJournal. Fail closed rather than self-admitting the rest.
    if receipt.evidence_kind is not VerificationEvidenceKind.EFFECT_JOURNAL_VERIFIED:
        raise CompletionEvidenceGateError("FINAL_EVIDENCE_AUTHORITY_CLASS_UNADMITTED")
    if receipt.verification_attempt_id != transition.verification_attempt_id:
        raise CompletionEvidenceGateError("VERIFICATION_ATTEMPT_ID_MISMATCH")
    if receipt.execution_attempt_id != transition.execution_attempt_id:
        raise CompletionEvidenceGateError("EXECUTION_ATTEMPT_ID_MISMATCH")
    if receipt.outcome is not transition.outcome:
        raise CompletionEvidenceGateError("VERIFICATION_OUTCOME_MISMATCH")

    try:
        return _mint_completion_evidence_admission(
            authority_class=CompletionAuthorityClass.CANONICAL_EFFECT_JOURNAL,
            authority_ref=_effect_journal_authority_ref(authority_binding),
            effect_id=observed.effect_id,
            receipt=receipt,
        )
    except CompletionEvidenceAdmissionError as exc:
        raise CompletionEvidenceGateError(f"ADMISSION_REJECTED:{exc}") from exc


def _correlated_from_effect_call(
    target: DeferredExecutionVerificationTarget,
    observed: EffectCallBinding,
    transition: VerifyExecution,
) -> CorrelatedVerification:
    if not isinstance(target, DeferredExecutionVerificationTarget):
        raise CompletionEvidenceGateError("INVALID_VERIFICATION_TARGET")
    if not isinstance(observed, EffectCallBinding):
        raise CompletionEvidenceGateError("INVALID_OBSERVED_EFFECT_CALL")
    if observed.stage is not EffectCorrelationStage.RESULT_OBSERVED:
        raise CompletionEvidenceGateError("VERIFICATION_REQUIRES_POST_RESULT")
    if observed.return_id is None:
        raise CompletionEvidenceGateError("VERIFICATION_REQUIRES_RETURN_BINDING")
    if not isinstance(transition, VerifyExecution):
        raise CompletionEvidenceGateError("INVALID_VERIFICATION_TRANSITION")

    binding = target.returned.binding
    expected = {
        "RETURN_ID": target.returned.return_id,
        "BINDING_ID": binding.binding_id(),
        "INVOCATION_ID": binding.invocation_id,
        "TOOL_USE_ID": binding.tool_use_id,
        "DELEGATION_ID": binding.delegation_id,
        "CHILD_IDENTITY_SHA256": binding.child.sha256(),
        "RESULT_ID": binding.result_id or "",
        "RESULT_SHA256": binding.result_sha256 or "",
    }
    actual = {
        "RETURN_ID": observed.return_id,
        "BINDING_ID": observed.binding_id,
        "INVOCATION_ID": observed.invocation_id,
        "TOOL_USE_ID": observed.tool_use_id,
        "DELEGATION_ID": observed.delegation_id,
        "CHILD_IDENTITY_SHA256": observed.child_identity_sha256,
        "RESULT_ID": observed.result_id or "",
        "RESULT_SHA256": observed.result_sha256 or "",
    }
    for name, value in actual.items():
        if value != expected[name]:
            raise CompletionEvidenceGateError(f"{name}_MISMATCH")

    return CorrelatedVerification(
        return_id=observed.return_id,
        binding_id=observed.binding_id,
        invocation_id=observed.invocation_id,
        tool_use_id=observed.tool_use_id,
        delegation_id=observed.delegation_id,
        child_identity_sha256=observed.child_identity_sha256,
        result_id=observed.result_id or "",
        result_sha256=observed.result_sha256 or "",
        transition=transition,
    )


def apply_admitted_effect_bound_verification(
    target: DeferredExecutionVerificationTarget,
    observed: EffectCallBinding,
    transition: VerifyExecution,
    *,
    admission: CompletionEvidenceAdmission,
) -> DeferredExecutionVerificationTarget:
    """Apply final verification only after exact effect + authority admission binding."""
    if not isinstance(admission, CompletionEvidenceAdmission):
        raise CompletionEvidenceGateError("COMPLETION_EVIDENCE_ADMISSION_REQUIRED")
    if admission.authority_class is not CompletionAuthorityClass.CANONICAL_EFFECT_JOURNAL:
        raise CompletionEvidenceGateError("COMPLETION_AUTHORITY_CLASS_UNADMITTED")
    if not isinstance(observed, EffectCallBinding):
        raise CompletionEvidenceGateError("INVALID_OBSERVED_EFFECT_CALL")
    if admission.effect_id != observed.effect_id:
        raise CompletionEvidenceGateError("EFFECT_ID_MISMATCH")
    if not isinstance(transition, VerifyExecution) or not isinstance(
        transition.receipt, VerificationReceipt
    ):
        raise CompletionEvidenceGateError("STRUCTURED_VERIFICATION_RECEIPT_REQUIRED")
    try:
        admission.assert_matches_receipt(transition.receipt)
    except CompletionEvidenceAdmissionError as exc:
        raise CompletionEvidenceGateError(f"RECEIPT_ADMISSION_MISMATCH:{exc}") from exc

    correlated = _correlated_from_effect_call(target, observed, transition)
    try:
        return apply_correlated_verification(
            target,
            correlated,
            completion_admission=admission,
        )
    except DeferredExecutionVerificationError as exc:
        raise CompletionEvidenceGateError(f"WP105_VERIFICATION_REJECTED:{exc}") from exc


__all__ = [
    "CompletionEvidenceGateError",
    "admit_current_effect_journal_verification",
    "apply_admitted_effect_bound_verification",
]
