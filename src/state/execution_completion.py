#!/usr/bin/env python3
"""Typed request -> execution -> verified-completion lineage for Frankenstein 2.0.

F2-WP-105 generation 1.

This module is deliberately persistence- and executor-agnostic.  It does not execute
an effect, write UnifiedDB, infer success from transport, or authorize a retry.  It
only validates immutable lineage transitions so that these claims remain distinct:

    request != admission != execution observation != verified completion

An observed/reported execution result is not completion.  In particular, an UNKNOWN
external outcome remains UNKNOWN until a separate verification transition establishes
APPLIED or NOT_APPLIED.  Until that happens blind replay is forbidden.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
from typing import Tuple


EXECUTION_LINEAGE_SCHEMA = "FRANKENSTEIN2_EXECUTION_COMPLETION_LINEAGE/v1"


class ExecutionLineageError(RuntimeError):
    """Fail-closed execution/completion lineage error."""


class ExecutionStage(str, Enum):
    REQUESTED = "REQUESTED"
    ADMITTED = "ADMITTED"
    EXECUTION_RECORDED = "EXECUTION_RECORDED"
    VERIFIED_APPLIED = "VERIFIED_APPLIED"
    VERIFIED_NOT_APPLIED = "VERIFIED_NOT_APPLIED"


class ExecutionOutcome(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"
    REPORTED_SUCCESS = "REPORTED_SUCCESS"
    REPORTED_FAILURE = "REPORTED_FAILURE"
    UNKNOWN = "UNKNOWN"


class VerificationOutcome(str, Enum):
    INDETERMINATE = "INDETERMINATE"
    APPLIED = "APPLIED"
    NOT_APPLIED = "NOT_APPLIED"


class ReplayDisposition(str, Enum):
    NOT_APPLICABLE_PRE_EXECUTION = "NOT_APPLICABLE_PRE_EXECUTION"
    FORBIDDEN_UNVERIFIED_OUTCOME = "FORBIDDEN_UNVERIFIED_OUTCOME"
    FORBIDDEN_ALREADY_APPLIED = "FORBIDDEN_ALREADY_APPLIED"
    ELIGIBLE_NEW_EXPLICIT_REQUEST = "ELIGIBLE_NEW_EXPLICIT_REQUEST"


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ExecutionLineageError(f"INVALID_{name.upper()}")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ExecutionLineageError(f"INVALID_{name.upper()}")
    if len(value) > 512:
        raise ExecutionLineageError(f"INVALID_{name.upper()}")
    return value


def _generation(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ExecutionLineageError("INVALID_GENERATION")
    return value


def _all_distinct(named: dict[str, str | None]) -> None:
    present = [(name, value) for name, value in named.items() if value is not None]
    values = [value for _, value in present]
    if len(values) == len(set(values)):
        return
    duplicates = sorted({value for value in values if values.count(value) > 1})
    raise ExecutionLineageError(
        "IDENTITY_ROLE_COLLISION:" + ",".join(duplicates)
    )


def _fingerprint_token(value: object) -> str:
    token = _token("transition_fingerprint", value)
    if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
        raise ExecutionLineageError("INVALID_TRANSITION_FINGERPRINT")
    return token


@dataclass(frozen=True)
class ExecutionLineage:
    schema: str
    causal_id: str
    generation: int
    request_id: str
    stage: ExecutionStage
    admission_id: str | None = None
    execution_attempt_id: str | None = None
    execution_outcome: ExecutionOutcome = ExecutionOutcome.NOT_EXECUTED
    verification_attempt_ids: Tuple[str, ...] = ()
    verification_outcome: VerificationOutcome | None = None
    applied_transition_ids: Tuple[str, ...] = ()
    applied_transition_fingerprints: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema != EXECUTION_LINEAGE_SCHEMA:
            raise ExecutionLineageError("SCHEMA_MISMATCH")
        _token("causal_id", self.causal_id)
        _token("request_id", self.request_id)
        _generation(self.generation)
        if self.admission_id is not None:
            _token("admission_id", self.admission_id)
        if self.execution_attempt_id is not None:
            _token("execution_attempt_id", self.execution_attempt_id)
        for attempt in self.verification_attempt_ids:
            _token("verification_attempt_id", attempt)
        for transition in self.applied_transition_ids:
            _token("transition_id", transition)
        for fingerprint in self.applied_transition_fingerprints:
            _fingerprint_token(fingerprint)
        _all_distinct(
            {
                "causal_id": self.causal_id,
                "request_id": self.request_id,
                "admission_id": self.admission_id,
                "execution_attempt_id": self.execution_attempt_id,
            }
        )
        if len(self.verification_attempt_ids) != len(set(self.verification_attempt_ids)):
            raise ExecutionLineageError("DUPLICATE_VERIFICATION_ATTEMPT_ID")
        if len(self.applied_transition_ids) != len(set(self.applied_transition_ids)):
            raise ExecutionLineageError("DUPLICATE_TRANSITION_ID")
        if len(self.applied_transition_ids) != len(self.applied_transition_fingerprints):
            raise ExecutionLineageError("TRANSITION_RECEIPT_CARDINALITY_MISMATCH")
        if self.stage == ExecutionStage.REQUESTED:
            if self.admission_id is not None or self.execution_attempt_id is not None:
                raise ExecutionLineageError("REQUESTED_HAS_LATER_IDENTITY")
            if self.execution_outcome != ExecutionOutcome.NOT_EXECUTED:
                raise ExecutionLineageError("REQUESTED_HAS_EXECUTION_OUTCOME")
        elif self.stage == ExecutionStage.ADMITTED:
            if self.admission_id is None or self.execution_attempt_id is not None:
                raise ExecutionLineageError("ADMITTED_IDENTITY_INVALID")
            if self.execution_outcome != ExecutionOutcome.NOT_EXECUTED:
                raise ExecutionLineageError("ADMITTED_HAS_EXECUTION_OUTCOME")
        else:
            if self.admission_id is None or self.execution_attempt_id is None:
                raise ExecutionLineageError("EXECUTION_IDENTITY_INCOMPLETE")
            if self.execution_outcome == ExecutionOutcome.NOT_EXECUTED:
                raise ExecutionLineageError("EXECUTION_OUTCOME_MISSING")
        if self.stage == ExecutionStage.VERIFIED_APPLIED:
            if self.verification_outcome != VerificationOutcome.APPLIED:
                raise ExecutionLineageError("VERIFIED_APPLIED_WITHOUT_APPLIED_EVIDENCE")
        elif self.stage == ExecutionStage.VERIFIED_NOT_APPLIED:
            if self.verification_outcome != VerificationOutcome.NOT_APPLIED:
                raise ExecutionLineageError("VERIFIED_NOT_APPLIED_WITHOUT_EVIDENCE")
        elif self.verification_outcome in (
            VerificationOutcome.APPLIED,
            VerificationOutcome.NOT_APPLIED,
        ):
            raise ExecutionLineageError("FINAL_VERIFICATION_WITHOUT_FINAL_STAGE")

    @classmethod
    def requested(
        cls,
        *,
        causal_id: str,
        generation: int,
        request_id: str,
    ) -> "ExecutionLineage":
        return cls(
            schema=EXECUTION_LINEAGE_SCHEMA,
            causal_id=_token("causal_id", causal_id),
            generation=_generation(generation),
            request_id=_token("request_id", request_id),
            stage=ExecutionStage.REQUESTED,
        )

    @property
    def is_verified_complete(self) -> bool:
        return self.stage in (
            ExecutionStage.VERIFIED_APPLIED,
            ExecutionStage.VERIFIED_NOT_APPLIED,
        )

    @property
    def replay_disposition(self) -> ReplayDisposition:
        if self.stage in (ExecutionStage.REQUESTED, ExecutionStage.ADMITTED):
            return ReplayDisposition.NOT_APPLICABLE_PRE_EXECUTION
        if self.stage == ExecutionStage.EXECUTION_RECORDED:
            return ReplayDisposition.FORBIDDEN_UNVERIFIED_OUTCOME
        if self.stage == ExecutionStage.VERIFIED_APPLIED:
            return ReplayDisposition.FORBIDDEN_ALREADY_APPLIED
        if self.stage == ExecutionStage.VERIFIED_NOT_APPLIED:
            return ReplayDisposition.ELIGIBLE_NEW_EXPLICIT_REQUEST
        raise ExecutionLineageError("UNKNOWN_STAGE")


@dataclass(frozen=True)
class ExecutionTransition:
    transition_id: str
    causal_id: str
    generation: int
    request_id: str


@dataclass(frozen=True)
class AdmitExecution(ExecutionTransition):
    admission_id: str


@dataclass(frozen=True)
class RecordExecution(ExecutionTransition):
    admission_id: str
    execution_attempt_id: str
    outcome: ExecutionOutcome


@dataclass(frozen=True)
class VerifyExecution(ExecutionTransition):
    admission_id: str
    execution_attempt_id: str
    verification_attempt_id: str
    outcome: VerificationOutcome


def _transition_payload(transition: ExecutionTransition) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": type(transition).__name__,
        "transition_id": transition.transition_id,
        "causal_id": transition.causal_id,
        "generation": transition.generation,
        "request_id": transition.request_id,
    }
    if isinstance(transition, AdmitExecution):
        payload["admission_id"] = transition.admission_id
    elif isinstance(transition, RecordExecution):
        payload.update(
            {
                "admission_id": transition.admission_id,
                "execution_attempt_id": transition.execution_attempt_id,
                "outcome": transition.outcome.value
                if isinstance(transition.outcome, ExecutionOutcome)
                else str(transition.outcome),
            }
        )
    elif isinstance(transition, VerifyExecution):
        payload.update(
            {
                "admission_id": transition.admission_id,
                "execution_attempt_id": transition.execution_attempt_id,
                "verification_attempt_id": transition.verification_attempt_id,
                "outcome": transition.outcome.value
                if isinstance(transition.outcome, VerificationOutcome)
                else str(transition.outcome),
            }
        )
    else:
        raise ExecutionLineageError("UNKNOWN_TRANSITION_TYPE")
    return payload


def _transition_fingerprint(transition: ExecutionTransition) -> str:
    canonical = json.dumps(
        _transition_payload(transition),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate_base(
    record: ExecutionLineage,
    transition: ExecutionTransition,
) -> tuple[str, str, bool]:
    transition_id = _token("transition_id", transition.transition_id)
    if transition.causal_id != record.causal_id:
        raise ExecutionLineageError("CAUSAL_ID_MISMATCH")
    if _generation(transition.generation) != record.generation:
        raise ExecutionLineageError("STALE_GENERATION")
    if transition.request_id != record.request_id:
        raise ExecutionLineageError("REQUEST_ID_MISMATCH")
    fingerprint = _transition_fingerprint(transition)
    if transition_id not in record.applied_transition_ids:
        return transition_id, fingerprint, False
    index = record.applied_transition_ids.index(transition_id)
    if record.applied_transition_fingerprints[index] != fingerprint:
        raise ExecutionLineageError("TRANSITION_ID_PAYLOAD_MISMATCH")
    return transition_id, fingerprint, True


def apply_execution_transition(
    record: ExecutionLineage,
    transition: ExecutionTransition,
) -> ExecutionLineage:
    """Apply one immutable transition; only exact payload replay is idempotent."""
    if not isinstance(record, ExecutionLineage):
        raise ExecutionLineageError("INVALID_RECORD")
    if not isinstance(transition, ExecutionTransition):
        raise ExecutionLineageError("INVALID_TRANSITION")
    transition_id, fingerprint, replayed = _validate_base(record, transition)
    if replayed:
        return record
    applied = record.applied_transition_ids + (transition_id,)
    fingerprints = record.applied_transition_fingerprints + (fingerprint,)

    if isinstance(transition, AdmitExecution):
        if record.stage != ExecutionStage.REQUESTED:
            raise ExecutionLineageError("ADMISSION_OUT_OF_ORDER")
        admission_id = _token("admission_id", transition.admission_id)
        return replace(
            record,
            stage=ExecutionStage.ADMITTED,
            admission_id=admission_id,
            applied_transition_ids=applied,
            applied_transition_fingerprints=fingerprints,
        )

    if isinstance(transition, RecordExecution):
        if record.stage != ExecutionStage.ADMITTED:
            raise ExecutionLineageError("EXECUTION_OUT_OF_ORDER")
        if transition.admission_id != record.admission_id:
            raise ExecutionLineageError("ADMISSION_ID_MISMATCH")
        attempt_id = _token("execution_attempt_id", transition.execution_attempt_id)
        if transition.outcome == ExecutionOutcome.NOT_EXECUTED:
            raise ExecutionLineageError("EXECUTION_OUTCOME_NOT_OBSERVED")
        if not isinstance(transition.outcome, ExecutionOutcome):
            raise ExecutionLineageError("INVALID_EXECUTION_OUTCOME")
        return replace(
            record,
            stage=ExecutionStage.EXECUTION_RECORDED,
            execution_attempt_id=attempt_id,
            execution_outcome=transition.outcome,
            applied_transition_ids=applied,
            applied_transition_fingerprints=fingerprints,
        )

    if isinstance(transition, VerifyExecution):
        if record.stage != ExecutionStage.EXECUTION_RECORDED:
            raise ExecutionLineageError("VERIFICATION_OUT_OF_ORDER")
        if transition.admission_id != record.admission_id:
            raise ExecutionLineageError("ADMISSION_ID_MISMATCH")
        if transition.execution_attempt_id != record.execution_attempt_id:
            raise ExecutionLineageError("EXECUTION_ATTEMPT_ID_MISMATCH")
        verification_attempt_id = _token(
            "verification_attempt_id", transition.verification_attempt_id
        )
        if verification_attempt_id in record.verification_attempt_ids:
            raise ExecutionLineageError("VERIFICATION_ATTEMPT_REUSED")
        if not isinstance(transition.outcome, VerificationOutcome):
            raise ExecutionLineageError("INVALID_VERIFICATION_OUTCOME")
        attempts = record.verification_attempt_ids + (verification_attempt_id,)
        if transition.outcome == VerificationOutcome.INDETERMINATE:
            return replace(
                record,
                verification_attempt_ids=attempts,
                verification_outcome=VerificationOutcome.INDETERMINATE,
                applied_transition_ids=applied,
                applied_transition_fingerprints=fingerprints,
            )
        if transition.outcome == VerificationOutcome.APPLIED:
            return replace(
                record,
                stage=ExecutionStage.VERIFIED_APPLIED,
                verification_attempt_ids=attempts,
                verification_outcome=VerificationOutcome.APPLIED,
                applied_transition_ids=applied,
                applied_transition_fingerprints=fingerprints,
            )
        if transition.outcome == VerificationOutcome.NOT_APPLIED:
            return replace(
                record,
                stage=ExecutionStage.VERIFIED_NOT_APPLIED,
                verification_attempt_ids=attempts,
                verification_outcome=VerificationOutcome.NOT_APPLIED,
                applied_transition_ids=applied,
                applied_transition_fingerprints=fingerprints,
            )
        raise ExecutionLineageError("UNKNOWN_VERIFICATION_OUTCOME")

    raise ExecutionLineageError("UNKNOWN_TRANSITION_TYPE")


__all__ = [
    "EXECUTION_LINEAGE_SCHEMA",
    "AdmitExecution",
    "ExecutionLineage",
    "ExecutionLineageError",
    "ExecutionOutcome",
    "ExecutionStage",
    "ExecutionTransition",
    "RecordExecution",
    "ReplayDisposition",
    "VerificationOutcome",
    "VerifyExecution",
    "apply_execution_transition",
]
