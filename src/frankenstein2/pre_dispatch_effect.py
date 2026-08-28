"""True result-free pre-dispatch effect binding for Frankenstein 2.0 WP105.

This module closes the temporal gap identified by the Triggerword-4 WP105 falsifier.
It creates an immutable effect/call envelope while the native child binding is still
result-free and the execution lineage is only ADMITTED. A typed execution receipt can
then bind the observed result and advance the generic WP105 lineage to
EXECUTION_RECORDED.

This is an identity/order component only. It does not execute an effect, grant
EffectGate authority, persist canonical state, infer an external-world outcome, mint
completion, or authorize blind replay. World verification remains a separate later
transition.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from state.execution_completion import (
    ExecutionLineage,
    ExecutionOutcome,
    ExecutionStage,
    RecordExecution,
    apply_execution_transition,
)

from .native_child_binding import NativeChildBinding, NativeChildBindingError


class PreDispatchEffectError(ValueError):
    """Raised when the result-free pre-dispatch causal contract is violated."""


def _token(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PreDispatchEffectError(f"INVALID_{name.upper()}")
    if len(value) > 512:
        raise PreDispatchEffectError(f"INVALID_{name.upper()}")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PreDispatchEffectError(f"INVALID_{name.upper()}")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PreDispatchEffectError("INVALID_GENERATION")
    return value


@dataclass(frozen=True, slots=True)
class PreDispatchEffectEnvelope:
    """Immutable call/effect identity that exists before external dispatch."""

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

    def __post_init__(self) -> None:
        for name in (
            "effect_id",
            "binding_id",
            "invocation_id",
            "tool_use_id",
            "delegation_id",
            "child_identity_sha256",
            "causal_id",
            "request_id",
            "admission_id",
        ):
            _token(name, getattr(self, name))
        _generation(self.generation)


@dataclass(frozen=True, slots=True)
class EffectExecutionReceipt:
    """Typed post-dispatch observation bound to the exact pre-dispatch envelope."""

    transition_id: str
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
    outcome: ExecutionOutcome
    result_id: str
    result_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "transition_id",
            "effect_id",
            "binding_id",
            "invocation_id",
            "tool_use_id",
            "delegation_id",
            "child_identity_sha256",
            "causal_id",
            "request_id",
            "admission_id",
            "execution_attempt_id",
            "result_id",
            "result_sha256",
        ):
            _token(name, getattr(self, name))
        _generation(self.generation)
        if not isinstance(self.outcome, ExecutionOutcome):
            raise PreDispatchEffectError("INVALID_EXECUTION_OUTCOME")
        if self.outcome is ExecutionOutcome.NOT_EXECUTED:
            raise PreDispatchEffectError("EXECUTION_OUTCOME_NOT_OBSERVED")


@dataclass(frozen=True, slots=True)
class EffectExecutionObservation:
    """Result-bound call plus generic lineage after one accepted execution receipt."""

    envelope: PreDispatchEffectEnvelope
    binding: NativeChildBinding
    lineage: ExecutionLineage

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, PreDispatchEffectEnvelope):
            raise PreDispatchEffectError("INVALID_ENVELOPE")
        if not isinstance(self.binding, NativeChildBinding):
            raise PreDispatchEffectError("INVALID_BINDING")
        if not isinstance(self.lineage, ExecutionLineage):
            raise PreDispatchEffectError("INVALID_LINEAGE")
        if not self.binding.has_result:
            raise PreDispatchEffectError("OBSERVATION_REQUIRES_RESULT_BOUND_BINDING")
        if self.lineage.stage is not ExecutionStage.EXECUTION_RECORDED:
            raise PreDispatchEffectError("OBSERVATION_REQUIRES_EXECUTION_RECORDED")


def _match(name: str, observed: str | int, expected: str | int) -> None:
    if observed != expected:
        raise PreDispatchEffectError(f"{name}_MISMATCH")


def _require_result_free_binding(binding: NativeChildBinding) -> None:
    if not isinstance(binding, NativeChildBinding):
        raise PreDispatchEffectError("binding must be a NativeChildBinding")
    if binding.has_result:
        raise PreDispatchEffectError("PRE_DISPATCH_REQUIRES_RESULT_FREE_BINDING")


def _require_admitted_lineage(
    binding: NativeChildBinding,
    lineage: ExecutionLineage,
) -> None:
    if not isinstance(lineage, ExecutionLineage):
        raise PreDispatchEffectError("lineage must be an ExecutionLineage")
    if lineage.stage is not ExecutionStage.ADMITTED:
        raise PreDispatchEffectError("PRE_DISPATCH_REQUIRES_ADMITTED_LINEAGE")
    if lineage.admission_id is None:
        raise PreDispatchEffectError("ADMITTED_LINEAGE_MISSING_ADMISSION_ID")
    _match("CAUSAL_ID", lineage.causal_id, binding.child.causal_id)
    _match("GENERATION", lineage.generation, binding.child.generation)


def prepare_pre_dispatch_effect(
    binding: NativeChildBinding,
    lineage: ExecutionLineage,
    *,
    effect_id: str,
) -> PreDispatchEffectEnvelope:
    """Bind effect identity before dispatch, result observation, or RecordExecution."""
    _require_result_free_binding(binding)
    _require_admitted_lineage(binding, lineage)
    assert lineage.admission_id is not None
    return PreDispatchEffectEnvelope(
        effect_id=_token("effect_id", effect_id),
        binding_id=binding.binding_id(),
        invocation_id=binding.invocation_id,
        tool_use_id=binding.tool_use_id,
        delegation_id=binding.delegation_id,
        child_identity_sha256=binding.child.sha256(),
        causal_id=lineage.causal_id,
        generation=lineage.generation,
        request_id=lineage.request_id,
        admission_id=lineage.admission_id,
    )


def _match_envelope_binding(
    envelope: PreDispatchEffectEnvelope,
    binding: NativeChildBinding,
) -> None:
    _require_result_free_binding(binding)
    expected = {
        "BINDING_ID": binding.binding_id(),
        "INVOCATION_ID": binding.invocation_id,
        "TOOL_USE_ID": binding.tool_use_id,
        "DELEGATION_ID": binding.delegation_id,
        "CHILD_IDENTITY_SHA256": binding.child.sha256(),
        "CAUSAL_ID": binding.child.causal_id,
        "GENERATION": binding.child.generation,
    }
    actual = {
        "BINDING_ID": envelope.binding_id,
        "INVOCATION_ID": envelope.invocation_id,
        "TOOL_USE_ID": envelope.tool_use_id,
        "DELEGATION_ID": envelope.delegation_id,
        "CHILD_IDENTITY_SHA256": envelope.child_identity_sha256,
        "CAUSAL_ID": envelope.causal_id,
        "GENERATION": envelope.generation,
    }
    for name, value in actual.items():
        _match(name, value, expected[name])


def _match_envelope_lineage(
    envelope: PreDispatchEffectEnvelope,
    lineage: ExecutionLineage,
) -> None:
    if not isinstance(lineage, ExecutionLineage):
        raise PreDispatchEffectError("lineage must be an ExecutionLineage")
    if lineage.stage is not ExecutionStage.ADMITTED:
        raise PreDispatchEffectError("EXECUTION_RECEIPT_REQUIRES_ADMITTED_LINEAGE")
    expected = {
        "CAUSAL_ID": lineage.causal_id,
        "GENERATION": lineage.generation,
        "REQUEST_ID": lineage.request_id,
        "ADMISSION_ID": lineage.admission_id or "",
    }
    actual = {
        "CAUSAL_ID": envelope.causal_id,
        "GENERATION": envelope.generation,
        "REQUEST_ID": envelope.request_id,
        "ADMISSION_ID": envelope.admission_id,
    }
    for name, value in actual.items():
        _match(name, value, expected[name])


def _match_receipt(
    envelope: PreDispatchEffectEnvelope,
    receipt: EffectExecutionReceipt,
) -> None:
    if not isinstance(receipt, EffectExecutionReceipt):
        raise PreDispatchEffectError("receipt must be an EffectExecutionReceipt")
    expected = {
        "EFFECT_ID": envelope.effect_id,
        "BINDING_ID": envelope.binding_id,
        "INVOCATION_ID": envelope.invocation_id,
        "TOOL_USE_ID": envelope.tool_use_id,
        "DELEGATION_ID": envelope.delegation_id,
        "CHILD_IDENTITY_SHA256": envelope.child_identity_sha256,
        "CAUSAL_ID": envelope.causal_id,
        "GENERATION": envelope.generation,
        "REQUEST_ID": envelope.request_id,
        "ADMISSION_ID": envelope.admission_id,
    }
    actual = {
        "EFFECT_ID": receipt.effect_id,
        "BINDING_ID": receipt.binding_id,
        "INVOCATION_ID": receipt.invocation_id,
        "TOOL_USE_ID": receipt.tool_use_id,
        "DELEGATION_ID": receipt.delegation_id,
        "CHILD_IDENTITY_SHA256": receipt.child_identity_sha256,
        "CAUSAL_ID": receipt.causal_id,
        "GENERATION": receipt.generation,
        "REQUEST_ID": receipt.request_id,
        "ADMISSION_ID": receipt.admission_id,
    }
    for name, value in actual.items():
        _match(name, value, expected[name])


def record_effect_execution(
    envelope: PreDispatchEffectEnvelope,
    binding: NativeChildBinding,
    lineage: ExecutionLineage,
    receipt: EffectExecutionReceipt,
) -> EffectExecutionObservation:
    """Consume one exact execution receipt without claiming world verification.

    Identity checks are completed before any immutable replacement is constructed.
    UNKNOWN is a valid observed transport/executor outcome and remains unverified;
    the generic lineage therefore keeps replay forbidden until a later independent
    VerifyExecution transition resolves APPLIED or NOT_APPLIED.
    """
    if not isinstance(envelope, PreDispatchEffectEnvelope):
        raise PreDispatchEffectError("envelope must be a PreDispatchEffectEnvelope")
    _match_envelope_binding(envelope, binding)
    _match_envelope_lineage(envelope, lineage)
    _match_receipt(envelope, receipt)

    try:
        bound = binding.bind_result(
            invocation_id=receipt.invocation_id,
            delegation_id=receipt.delegation_id,
            child_causal_id=binding.child.causal_id,
            result_id=receipt.result_id,
            result_sha256=receipt.result_sha256,
        )
    except NativeChildBindingError as exc:
        raise PreDispatchEffectError(f"RESULT_BIND_REJECTED:{exc}") from exc

    next_lineage = apply_execution_transition(
        lineage,
        RecordExecution(
            transition_id=receipt.transition_id,
            causal_id=receipt.causal_id,
            generation=receipt.generation,
            request_id=receipt.request_id,
            admission_id=receipt.admission_id,
            execution_attempt_id=receipt.execution_attempt_id,
            outcome=receipt.outcome,
        ),
    )
    return EffectExecutionObservation(
        envelope=envelope,
        binding=bound,
        lineage=next_lineage,
    )


__all__ = [
    "EffectExecutionObservation",
    "EffectExecutionReceipt",
    "PreDispatchEffectEnvelope",
    "PreDispatchEffectError",
    "prepare_pre_dispatch_effect",
    "record_effect_execution",
]
