"""Policy-neutral executor interlock for Frankenstein 2.0 Stage 1.

This module is deliberately *not* an EffectGate.  It cannot derive or mint ALLOW.
It consumes a decision emitted by an external effect-authority implementation and
checks that the decision is bound to the exact PRE-dispatch ``EffectCallBinding``.
Only an exact external ALLOW may cross the executor boundary; every other decision,
authority failure, or identity mismatch stops before the executor callable is invoked.

When the PRE binding carries semantic ``EffectRequestIdentity``, both the external
authority evidence and executor observation must echo its exact SHA-256. This closes
the request-substitution gap without moving policy into Frankenstein 2.0.

The adapter also refuses to reinterpret an executor exception as a negative world
fact.  If invocation may have started and no correlated POST observation is available,
the outcome remains UNKNOWN to higher layers and must be reconciled by the canonical
EffectJournal/recovery path.  This module does not persist that journal itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from .effect_invocation_correlation import (
    EffectCallBinding,
    EffectCorrelationStage,
    EffectInvocationCorrelationError,
    observe_effect_result,
)


class ExternalGateDecision(str, Enum):
    """Transport vocabulary only; policy remains external to this module."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    DEGRADE_TO_PROPOSAL = "DEGRADE_TO_PROPOSAL"
    UNKNOWN = "UNKNOWN"


class ExecutorInterlockError(RuntimeError):
    pass


class ExecutorOutcomeUnknown(ExecutorInterlockError):
    """Invocation may have crossed the boundary but no correlated result is known."""


def _sha256_token(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ExecutorInterlockError(f"INVALID_{name.upper()}")
    if any(ch not in "0123456789abcdef" for ch in value):
        raise ExecutorInterlockError(f"INVALID_{name.upper()}")
    return value


@dataclass(frozen=True, slots=True)
class ExternalGateEvidence:
    """Decision evidence produced outside Frankenstein 2.0 policy code.

    ``authority_ref`` and ``decision_id`` are provenance handles.  They are not proof
    by themselves; the production integration must obtain this object from the current
    canonical EffectGate/EffectJournal boundary rather than caller-authored model text.
    ``request_sha256`` is mandatory when the prepared call carries semantic request
    identity and must identify exactly the request evaluated by that external authority.
    """

    authority_ref: str
    decision_id: str
    decision: ExternalGateDecision
    effect_id: str
    binding_id: str
    invocation_id: str
    tool_use_id: str
    delegation_id: str
    child_identity_sha256: str
    request_sha256: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "authority_ref",
            "decision_id",
            "effect_id",
            "binding_id",
            "invocation_id",
            "tool_use_id",
            "delegation_id",
            "child_identity_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ExecutorInterlockError(f"INVALID_{name.upper()}")
        if self.request_sha256 is not None:
            _sha256_token("request_sha256", self.request_sha256)
        if not isinstance(self.decision, ExternalGateDecision):
            raise ExecutorInterlockError("INVALID_EXTERNAL_GATE_DECISION")


@dataclass(frozen=True, slots=True)
class ExecutorObservation:
    """Typed POST observation returned by an executor implementation."""

    effect_id: str
    binding_id: str
    invocation_id: str
    tool_use_id: str
    delegation_id: str
    child_identity_sha256: str
    result_id: str
    result_sha256: str
    request_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.request_sha256 is not None:
            _sha256_token("request_sha256", self.request_sha256)


@dataclass(frozen=True, slots=True)
class InterlockResult:
    dispatched: bool
    gate_decision: ExternalGateDecision
    gate_decision_id: str
    authority_ref: str
    observed: EffectCallBinding | None = None
    block_reason: str | None = None


class ExternalAuthorizer(Protocol):
    def __call__(self, prepared: EffectCallBinding) -> ExternalGateEvidence: ...


class EffectExecutor(Protocol):
    def __call__(self, prepared: EffectCallBinding) -> ExecutorObservation: ...


def _match(name: str, observed: str, expected: str) -> None:
    if observed != expected:
        raise ExecutorInterlockError(f"{name}_MISMATCH")


def _validate_gate_binding(
    prepared: EffectCallBinding,
    gate: ExternalGateEvidence,
) -> None:
    expected = {
        "EFFECT_ID": prepared.effect_id,
        "BINDING_ID": prepared.binding_id,
        "INVOCATION_ID": prepared.invocation_id,
        "TOOL_USE_ID": prepared.tool_use_id,
        "DELEGATION_ID": prepared.delegation_id,
        "CHILD_IDENTITY_SHA256": prepared.child_identity_sha256,
    }
    actual = {
        "EFFECT_ID": gate.effect_id,
        "BINDING_ID": gate.binding_id,
        "INVOCATION_ID": gate.invocation_id,
        "TOOL_USE_ID": gate.tool_use_id,
        "DELEGATION_ID": gate.delegation_id,
        "CHILD_IDENTITY_SHA256": gate.child_identity_sha256,
    }
    if prepared.request is not None:
        expected["REQUEST_SHA256"] = prepared.request.sha256()
        actual["REQUEST_SHA256"] = _sha256_token(
            "request_sha256", gate.request_sha256
        )
    for name, value in actual.items():
        _match(name, value, expected[name])


def dispatch_through_external_gate(
    prepared: EffectCallBinding,
    *,
    authorize: Callable[[EffectCallBinding], ExternalGateEvidence],
    executor: Callable[[EffectCallBinding], ExecutorObservation],
) -> InterlockResult:
    """Cross the executor boundary only after an exact externally-issued ALLOW.

    This function never retries.  An exception after entering ``executor`` is surfaced
    as ``ExecutorOutcomeUnknown`` because the external effect may or may not have
    occurred; only canonical recovery/world verification may resolve that uncertainty.
    """
    if not isinstance(prepared, EffectCallBinding):
        raise ExecutorInterlockError("prepared must be an EffectCallBinding")
    if prepared.stage is not EffectCorrelationStage.PREPARED:
        raise ExecutorInterlockError("DISPATCH_REQUIRES_PREPARED_EFFECT_CALL")
    if not callable(authorize):
        raise ExecutorInterlockError("AUTHORIZE_NOT_CALLABLE")
    if not callable(executor):
        raise ExecutorInterlockError("EXECUTOR_NOT_CALLABLE")

    try:
        gate = authorize(prepared)
    except Exception as exc:
        raise ExecutorInterlockError("EXTERNAL_EFFECT_AUTHORITY_FAILED") from exc
    if not isinstance(gate, ExternalGateEvidence):
        raise ExecutorInterlockError("EXTERNAL_EFFECT_AUTHORITY_RETURNED_INVALID_EVIDENCE")

    # Identity validation is deliberately before the decision check and before dispatch.
    # A valid ALLOW for call/request B can never authorize call/request A.
    _validate_gate_binding(prepared, gate)

    if gate.decision is not ExternalGateDecision.ALLOW:
        return InterlockResult(
            dispatched=False,
            gate_decision=gate.decision,
            gate_decision_id=gate.decision_id,
            authority_ref=gate.authority_ref,
            observed=None,
            block_reason=f"EXTERNAL_GATE_{gate.decision.value}",
        )

    try:
        observation = executor(prepared)
    except Exception as exc:
        raise ExecutorOutcomeUnknown(
            "EXECUTOR_RETURN_UNKNOWN_NO_AUTOMATIC_REPLAY"
        ) from exc
    if not isinstance(observation, ExecutorObservation):
        raise ExecutorOutcomeUnknown(
            "EXECUTOR_OBSERVATION_INVALID_OUTCOME_UNKNOWN_NO_AUTOMATIC_REPLAY"
        )

    # POST correlation cannot undo an already-attempted effect.  Therefore any mismatch
    # is surfaced as UNKNOWN rather than DENY/FAILED and must be reconciled externally.
    try:
        _match("POST_EFFECT_ID", observation.effect_id, prepared.effect_id)
        _match("POST_BINDING_ID", observation.binding_id, prepared.binding_id)
        _match("POST_INVOCATION_ID", observation.invocation_id, prepared.invocation_id)
        _match("POST_TOOL_USE_ID", observation.tool_use_id, prepared.tool_use_id)
        _match("POST_DELEGATION_ID", observation.delegation_id, prepared.delegation_id)
        _match(
            "POST_CHILD_IDENTITY_SHA256",
            observation.child_identity_sha256,
            prepared.child_identity_sha256,
        )
        if prepared.request is not None:
            _match(
                "POST_REQUEST_SHA256",
                _sha256_token("request_sha256", observation.request_sha256),
                prepared.request.sha256(),
            )
        observed = observe_effect_result(
            prepared,
            effect_id=observation.effect_id,
            observed_invocation_id=observation.invocation_id,
            observed_tool_use_id=observation.tool_use_id,
            observed_delegation_id=observation.delegation_id,
            observed_binding_id=observation.binding_id,
            observed_child_identity_sha256=observation.child_identity_sha256,
            result_id=observation.result_id,
            result_sha256=observation.result_sha256,
            observed_request_sha256=observation.request_sha256,
        )
    except (ExecutorInterlockError, EffectInvocationCorrelationError) as exc:
        raise ExecutorOutcomeUnknown(
            "EXECUTOR_POST_CORRELATION_FAILED_OUTCOME_UNKNOWN_NO_AUTOMATIC_REPLAY"
        ) from exc

    return InterlockResult(
        dispatched=True,
        gate_decision=gate.decision,
        gate_decision_id=gate.decision_id,
        authority_ref=gate.authority_ref,
        observed=observed,
        block_reason=None,
    )


__all__ = [
    "EffectExecutor",
    "ExecutorInterlockError",
    "ExecutorObservation",
    "ExecutorOutcomeUnknown",
    "ExternalAuthorizer",
    "ExternalGateDecision",
    "ExternalGateEvidence",
    "InterlockResult",
    "dispatch_through_external_gate",
]
