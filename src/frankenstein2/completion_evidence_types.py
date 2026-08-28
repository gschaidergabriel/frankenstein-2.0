"""Opaque typed admission envelope for WP105 final completion evidence.

The generic execution-completion state machine intentionally knows evidence *classes*
but cannot decide which external source is currently admitted as authority.  This tiny
module carries the result of that separate admission step across the final verification
boundary without becoming a truth store, journal, effect authority, or verifier.

Admissions are minted only through the module-private factory used by the current
completion-evidence gate.  Python module privacy is not a security boundary; the seal is
an API/protocol guard against accidental caller self-classification, not a capability
system.  Canonical authority still comes from the separately verified binding consumed
by the gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from state.execution_completion import (
    VerificationEvidenceKind,
    VerificationOutcome,
    VerificationReceipt,
)


class CompletionEvidenceAdmissionError(RuntimeError):
    """Malformed or mismatched final-evidence admission."""


class CompletionAuthorityClass(str, Enum):
    CANONICAL_EFFECT_JOURNAL = "CANONICAL_EFFECT_JOURNAL"


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CompletionEvidenceAdmissionError(f"INVALID_{name.upper()}")
    if len(value) > 1024 or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CompletionEvidenceAdmissionError(f"INVALID_{name.upper()}")
    return value


def _sha256(name: str, value: object) -> str:
    token = _token(name, value)
    if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
        raise CompletionEvidenceAdmissionError(f"INVALID_{name.upper()}")
    return token


_ADMISSION_SEAL = object()


@dataclass(frozen=True, slots=True, init=False)
class CompletionEvidenceAdmission:
    authority_class: CompletionAuthorityClass
    authority_ref: str
    effect_id: str
    receipt_id: str
    execution_attempt_id: str
    verification_attempt_id: str
    outcome: VerificationOutcome
    evidence_kind: VerificationEvidenceKind
    evidence_ref: str
    evidence_sha256: str

    def __init__(
        self,
        *,
        authority_class: CompletionAuthorityClass,
        authority_ref: str,
        effect_id: str,
        receipt_id: str,
        execution_attempt_id: str,
        verification_attempt_id: str,
        outcome: VerificationOutcome,
        evidence_kind: VerificationEvidenceKind,
        evidence_ref: str,
        evidence_sha256: str,
        _seal: object,
    ) -> None:
        if _seal is not _ADMISSION_SEAL:
            raise CompletionEvidenceAdmissionError("DIRECT_ADMISSION_CONSTRUCTION_FORBIDDEN")
        if not isinstance(authority_class, CompletionAuthorityClass):
            raise CompletionEvidenceAdmissionError("INVALID_AUTHORITY_CLASS")
        if not isinstance(outcome, VerificationOutcome):
            raise CompletionEvidenceAdmissionError("INVALID_VERIFICATION_OUTCOME")
        if outcome not in (VerificationOutcome.APPLIED, VerificationOutcome.NOT_APPLIED):
            raise CompletionEvidenceAdmissionError("ADMISSION_REQUIRES_FINAL_OUTCOME")
        if not isinstance(evidence_kind, VerificationEvidenceKind):
            raise CompletionEvidenceAdmissionError("INVALID_EVIDENCE_KIND")
        object.__setattr__(self, "authority_class", authority_class)
        object.__setattr__(self, "authority_ref", _token("authority_ref", authority_ref))
        object.__setattr__(self, "effect_id", _token("effect_id", effect_id))
        object.__setattr__(self, "receipt_id", _token("receipt_id", receipt_id))
        object.__setattr__(
            self, "execution_attempt_id", _token("execution_attempt_id", execution_attempt_id)
        )
        object.__setattr__(
            self,
            "verification_attempt_id",
            _token("verification_attempt_id", verification_attempt_id),
        )
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "evidence_kind", evidence_kind)
        object.__setattr__(self, "evidence_ref", _token("evidence_ref", evidence_ref))
        object.__setattr__(
            self, "evidence_sha256", _sha256("evidence_sha256", evidence_sha256)
        )

    def assert_matches_receipt(self, receipt: VerificationReceipt) -> None:
        if not isinstance(receipt, VerificationReceipt):
            raise CompletionEvidenceAdmissionError("INVALID_VERIFICATION_RECEIPT")
        expected = {
            "RECEIPT_ID": self.receipt_id,
            "EXECUTION_ATTEMPT_ID": self.execution_attempt_id,
            "VERIFICATION_ATTEMPT_ID": self.verification_attempt_id,
            "OUTCOME": self.outcome,
            "EVIDENCE_KIND": self.evidence_kind,
            "EVIDENCE_REF": self.evidence_ref,
            "EVIDENCE_SHA256": self.evidence_sha256,
        }
        actual = {
            "RECEIPT_ID": receipt.receipt_id,
            "EXECUTION_ATTEMPT_ID": receipt.execution_attempt_id,
            "VERIFICATION_ATTEMPT_ID": receipt.verification_attempt_id,
            "OUTCOME": receipt.outcome,
            "EVIDENCE_KIND": receipt.evidence_kind,
            "EVIDENCE_REF": receipt.evidence_ref,
            "EVIDENCE_SHA256": receipt.evidence_sha256,
        }
        for name, value in actual.items():
            if value != expected[name]:
                raise CompletionEvidenceAdmissionError(f"{name}_MISMATCH")


def _mint_completion_evidence_admission(
    *,
    authority_class: CompletionAuthorityClass,
    authority_ref: str,
    effect_id: str,
    receipt: VerificationReceipt,
) -> CompletionEvidenceAdmission:
    if not isinstance(receipt, VerificationReceipt):
        raise CompletionEvidenceAdmissionError("INVALID_VERIFICATION_RECEIPT")
    return CompletionEvidenceAdmission(
        authority_class=authority_class,
        authority_ref=authority_ref,
        effect_id=effect_id,
        receipt_id=receipt.receipt_id,
        execution_attempt_id=receipt.execution_attempt_id,
        verification_attempt_id=receipt.verification_attempt_id,
        outcome=receipt.outcome,
        evidence_kind=receipt.evidence_kind,
        evidence_ref=receipt.evidence_ref,
        evidence_sha256=receipt.evidence_sha256,
        _seal=_ADMISSION_SEAL,
    )


__all__ = [
    "CompletionAuthorityClass",
    "CompletionEvidenceAdmission",
    "CompletionEvidenceAdmissionError",
]
