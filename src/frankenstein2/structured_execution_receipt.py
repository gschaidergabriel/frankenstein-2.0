"""Structured executor receipts for Frankenstein 2.0 WP105.

This module narrows the boundary between an executor observation and the generic
``ExecutionLineage`` state machine. Raw executor status text is never interpreted as
verified world truth. Only one exact executor status is allowlisted as a reported
success, one exact status is allowlisted as a definite pre-effect failure, and every
other syntactically valid status is translated to ``UNKNOWN``.

Even an allowlisted ``SUCCEEDED`` receipt advances only to ``EXECUTION_RECORDED`` with
``REPORTED_SUCCESS``. It does not mint ``VERIFIED_APPLIED``. Separate WP105 world
verification remains mandatory and blind replay remains forbidden until that later
transition resolves the outcome.

The receipt binds canonical effect/call identity, immutable semantic request identity
when present, causal lineage, admission, execution attempt and result digest. It is an
adapter-level observation, not a new EffectGate, EffectJournal, canonical truth store
or effect authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Final

from state.execution_completion import (
    ExecutionLineage,
    ExecutionLineageError,
    ExecutionOutcome,
    RecordExecution,
    apply_execution_transition,
)

from .effect_invocation_correlation import (
    EffectCallBinding,
    EffectCorrelationStage,
    EffectInvocationCorrelationError,
    observe_effect_result,
)


class StructuredExecutionReceiptError(RuntimeError):
    """Fail-closed error for malformed or cross-call executor receipts."""


SUCCESS_STATUS_ALLOWLIST: Final[frozenset[str]] = frozenset({"SUCCEEDED"})
DEFINITE_PRE_EFFECT_FAILURE_STATUS_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {"FAILED_BEFORE_EFFECT"}
)


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise StructuredExecutionReceiptError(f"INVALID_{name.upper()}")
    if len(value) > 512 or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise StructuredExecutionReceiptError(f"INVALID_{name.upper()}")
    return value


def _sha256_token(name: str, value: object) -> str:
    token = _token(name, value)
    if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
        raise StructuredExecutionReceiptError(f"INVALID_{name.upper()}")
    return token


def _generation(value: object) -> int:
    if type(value) is not int or value < 0:
        raise StructuredExecutionReceiptError("INVALID_GENERATION")
    return value


@dataclass(frozen=True, slots=True)
class StructuredExecutionReceipt:
    """Exact post-dispatch executor observation, still noncanonical world evidence."""

    receipt_id: str
    effect_id: str
    binding_id: str
    invocation_id: str
    tool_use_id: str
    delegation_id: str
    child_identity_sha256: str
    causal_id: str
    generation: int
    request_id: str
    admission_id: str
    execution_attempt_id: str
    raw_status: str
    result_id: str
    result_sha256: str
    request_sha256: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "receipt_id",
            "effect_id",
            "binding_id",
            "invocation_id",
            "tool_use_id",
            "delegation_id",
            "causal_id",
            "request_id",
            "admission_id",
            "execution_attempt_id",
            "raw_status",
            "result_id",
        ):
            _token(name, getattr(self, name))
        _sha256_token("child_identity_sha256", self.child_identity_sha256)
        _sha256_token("result_sha256", self.result_sha256)
        if self.request_sha256 is not None:
            _sha256_token("request_sha256", self.request_sha256)
        _generation(self.generation)

    def fingerprint(self) -> str:
        payload = asdict(self)
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def transition_id(self) -> str:
        """Bind RecordExecution idempotency to the complete receipt payload."""
        return f"structured-execution-receipt:{self.fingerprint()}"

    def execution_outcome(self) -> ExecutionOutcome:
        """Translate raw executor status through a deliberately tiny allowlist."""
        if self.raw_status in SUCCESS_STATUS_ALLOWLIST:
            return ExecutionOutcome.REPORTED_SUCCESS
        if self.raw_status in DEFINITE_PRE_EFFECT_FAILURE_STATUS_ALLOWLIST:
            return ExecutionOutcome.REPORTED_FAILURE
        return ExecutionOutcome.UNKNOWN


@dataclass(frozen=True, slots=True)
class StructuredExecutionObservation:
    receipt: StructuredExecutionReceipt
    observed_call: EffectCallBinding
    lineage: ExecutionLineage


def _match(name: str, observed: object, expected: object) -> None:
    if observed != expected:
        raise StructuredExecutionReceiptError(f"{name}_MISMATCH")


def _validate_call(
    prepared: EffectCallBinding,
    receipt: StructuredExecutionReceipt,
) -> None:
    if not isinstance(prepared, EffectCallBinding):
        raise StructuredExecutionReceiptError("INVALID_PREPARED_CALL")
    if prepared.stage is not EffectCorrelationStage.PREPARED:
        raise StructuredExecutionReceiptError("RECEIPT_REQUIRES_PREPARED_CALL")
    expected = {
        "EFFECT_ID": prepared.effect_id,
        "BINDING_ID": prepared.binding_id,
        "INVOCATION_ID": prepared.invocation_id,
        "TOOL_USE_ID": prepared.tool_use_id,
        "DELEGATION_ID": prepared.delegation_id,
        "CHILD_IDENTITY_SHA256": prepared.child_identity_sha256,
    }
    actual = {
        "EFFECT_ID": receipt.effect_id,
        "BINDING_ID": receipt.binding_id,
        "INVOCATION_ID": receipt.invocation_id,
        "TOOL_USE_ID": receipt.tool_use_id,
        "DELEGATION_ID": receipt.delegation_id,
        "CHILD_IDENTITY_SHA256": receipt.child_identity_sha256,
    }
    if prepared.request is not None:
        expected["REQUEST_SHA256"] = prepared.request.sha256()
        if receipt.request_sha256 is None:
            raise StructuredExecutionReceiptError("REQUEST_SHA256_REQUIRED")
        actual["REQUEST_SHA256"] = _sha256_token(
            "request_sha256", receipt.request_sha256
        )
    for name, value in actual.items():
        _match(name, value, expected[name])


def _validate_lineage(
    lineage: ExecutionLineage,
    receipt: StructuredExecutionReceipt,
) -> None:
    if not isinstance(lineage, ExecutionLineage):
        raise StructuredExecutionReceiptError("INVALID_EXECUTION_LINEAGE")
    expected = {
        "CAUSAL_ID": lineage.causal_id,
        "GENERATION": lineage.generation,
        "REQUEST_ID": lineage.request_id,
        "ADMISSION_ID": lineage.admission_id,
    }
    actual = {
        "CAUSAL_ID": receipt.causal_id,
        "GENERATION": receipt.generation,
        "REQUEST_ID": receipt.request_id,
        "ADMISSION_ID": receipt.admission_id,
    }
    for name, value in actual.items():
        _match(name, value, expected[name])


def apply_structured_execution_receipt(
    prepared: EffectCallBinding,
    lineage: ExecutionLineage,
    receipt: StructuredExecutionReceipt,
) -> StructuredExecutionObservation:
    """Bind one exact executor receipt and record execution without verifying the world."""
    if not isinstance(receipt, StructuredExecutionReceipt):
        raise StructuredExecutionReceiptError("INVALID_EXECUTION_RECEIPT")
    _validate_call(prepared, receipt)
    _validate_lineage(lineage, receipt)

    # Result correlation is immutable and completed before any lineage replacement.
    try:
        observed_call = observe_effect_result(
            prepared,
            effect_id=receipt.effect_id,
            observed_invocation_id=receipt.invocation_id,
            observed_tool_use_id=receipt.tool_use_id,
            observed_delegation_id=receipt.delegation_id,
            observed_binding_id=receipt.binding_id,
            observed_child_identity_sha256=receipt.child_identity_sha256,
            result_id=receipt.result_id,
            result_sha256=receipt.result_sha256,
            observed_request_sha256=receipt.request_sha256,
        )
    except EffectInvocationCorrelationError as exc:
        raise StructuredExecutionReceiptError(
            f"RESULT_CORRELATION_REJECTED:{exc}"
        ) from exc

    try:
        next_lineage = apply_execution_transition(
            lineage,
            RecordExecution(
                transition_id=receipt.transition_id(),
                causal_id=receipt.causal_id,
                generation=receipt.generation,
                request_id=receipt.request_id,
                admission_id=receipt.admission_id,
                execution_attempt_id=receipt.execution_attempt_id,
                outcome=receipt.execution_outcome(),
            ),
        )
    except ExecutionLineageError as exc:
        raise StructuredExecutionReceiptError(
            f"EXECUTION_LINEAGE_REJECTED:{exc}"
        ) from exc

    return StructuredExecutionObservation(
        receipt=receipt,
        observed_call=observed_call,
        lineage=next_lineage,
    )


__all__ = [
    "DEFINITE_PRE_EFFECT_FAILURE_STATUS_ALLOWLIST",
    "SUCCESS_STATUS_ALLOWLIST",
    "StructuredExecutionObservation",
    "StructuredExecutionReceipt",
    "StructuredExecutionReceiptError",
    "apply_structured_execution_receipt",
]
