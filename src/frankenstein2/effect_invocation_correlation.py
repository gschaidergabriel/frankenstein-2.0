"""Call-scoped effect identity correlation for Frankenstein 2.0 Stage 1.

This module is an identity/order guard only. It does not execute a tool, grant
EffectGate authority, persist canonical state, infer an external-world outcome, or
mint completion. It binds an explicit ``effect_id`` at true PRE-dispatch time to the
already-authoritative result-free WP-102 call identity. After dispatch, the same
identity may gain a typed result observation, then a WP-104 deferred-return identity,
and only then participate in WP-105 verification.

The canonical path may additionally carry an immutable semantic ``EffectRequestIdentity``.
When present, its digest is part of PRE/POST correlation so an executor observation for
semantic request B cannot be attached to an ALLOW prepared for request A. Legacy callers
without semantic identity remain representable for compatibility, but they do not gain
canonical semantic-request-binding credit.

The legacy result-bound ``DeferredExecutionVerificationTarget`` constructor path is
retained for compatibility, but it is not evidence of true pre-dispatch usability.
Session context and result digests are deliberately insufficient correlation keys.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from state.execution_completion import VerifyExecution

from .deferred_execution_verification import (
    CorrelatedVerification,
    DeferredExecutionVerificationError,
    DeferredExecutionVerificationTarget,
    apply_correlated_verification,
)
from .effect_request_identity import EffectRequestIdentity
from .native_child_binding import NativeChildBinding


class EffectInvocationCorrelationError(ValueError):
    """Raised when PRE/POST effect identity is incomplete or contradictory."""


class EffectCorrelationStage(str, Enum):
    PREPARED = "PREPARED"
    RESULT_OBSERVED = "RESULT_OBSERVED"


def _token(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EffectInvocationCorrelationError(f"INVALID_{name.upper()}")
    if len(value) > 512:
        raise EffectInvocationCorrelationError(f"INVALID_{name.upper()}")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise EffectInvocationCorrelationError(f"INVALID_{name.upper()}")
    return value


@dataclass(frozen=True, slots=True)
class EffectCallBinding:
    """Immutable PRE->POST identity envelope for one candidate effect call.

    ``return_id`` is deliberately optional: a true PRE-dispatch envelope exists before
    a WP-104 return can exist. Once a result-bound deferred return is available,
    ``bind_effect_return`` attaches that identity after exact call/result correlation.

    ``request`` is optional only for legacy compatibility. The canonical EntityOS
    authority path requires it and verifies its digest before dispatch and after the
    executor observation.
    """

    effect_id: str
    return_id: str | None
    binding_id: str
    invocation_id: str
    tool_use_id: str
    delegation_id: str
    child_identity_sha256: str
    stage: EffectCorrelationStage
    request: EffectRequestIdentity | None = None
    result_id: str | None = None
    result_sha256: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "effect_id",
            "binding_id",
            "invocation_id",
            "tool_use_id",
            "delegation_id",
            "child_identity_sha256",
        ):
            _token(name, getattr(self, name))
        if self.return_id is not None:
            _token("return_id", self.return_id)
        if not isinstance(self.stage, EffectCorrelationStage):
            raise EffectInvocationCorrelationError("INVALID_STAGE")
        if self.request is not None and not isinstance(self.request, EffectRequestIdentity):
            raise EffectInvocationCorrelationError("INVALID_EFFECT_REQUEST_IDENTITY")
        if self.stage is EffectCorrelationStage.PREPARED:
            if self.result_id is not None or self.result_sha256 is not None:
                raise EffectInvocationCorrelationError("PREPARED_CANNOT_HAVE_RESULT")
        elif self.stage is EffectCorrelationStage.RESULT_OBSERVED:
            if self.result_id is None or self.result_sha256 is None:
                raise EffectInvocationCorrelationError("OBSERVED_RESULT_IDENTITY_INCOMPLETE")
            _token("result_id", self.result_id)
            _token("result_sha256", self.result_sha256)

    @property
    def request_sha256(self) -> str | None:
        return self.request.sha256() if self.request is not None else None


def prepare_effect_call(
    target: DeferredExecutionVerificationTarget | NativeChildBinding,
    *,
    effect_id: str,
    request: EffectRequestIdentity | None = None,
) -> EffectCallBinding:
    """Bind explicit PRE-dispatch effect identity to one exact Stage-1 call.

    The canonical true PRE-dispatch path consumes a result-free ``NativeChildBinding``.
    It therefore exists before ``RecordExecution`` and before any WP-104 return. The
    older ``DeferredExecutionVerificationTarget`` input remains accepted only as a
    compatibility path for already-result-bound callers and existing receipts.
    """
    if isinstance(target, NativeChildBinding):
        if target.has_result:
            raise EffectInvocationCorrelationError(
                "PRE_DISPATCH_BINDING_MUST_BE_RESULT_FREE"
            )
        binding = target
        return_id = None
    elif isinstance(target, DeferredExecutionVerificationTarget):
        binding = target.returned.binding
        return_id = target.returned.return_id
    else:
        raise EffectInvocationCorrelationError(
            "target must be a result-free NativeChildBinding or DeferredExecutionVerificationTarget"
        )
    if request is not None and not isinstance(request, EffectRequestIdentity):
        raise EffectInvocationCorrelationError("INVALID_EFFECT_REQUEST_IDENTITY")
    return EffectCallBinding(
        effect_id=_token("effect_id", effect_id),
        return_id=return_id,
        binding_id=binding.binding_id(),
        invocation_id=binding.invocation_id,
        tool_use_id=binding.tool_use_id,
        delegation_id=binding.delegation_id,
        child_identity_sha256=binding.child.sha256(),
        stage=EffectCorrelationStage.PREPARED,
        request=request,
    )


def _match(name: str, observed: str, expected: str) -> None:
    if observed != expected:
        raise EffectInvocationCorrelationError(f"{name}_MISMATCH")


def observe_effect_result(
    prepared: EffectCallBinding,
    *,
    effect_id: str,
    observed_invocation_id: str,
    observed_tool_use_id: str,
    observed_delegation_id: str,
    observed_binding_id: str,
    observed_child_identity_sha256: str,
    result_id: str,
    result_sha256: str,
    observed_request_sha256: str | None = None,
) -> EffectCallBinding:
    """Bind POST-result identity only to the exact PRE-bound call.

    Exact replay of the already-observed POST record is idempotent. Any mutation or
    cross-call substitution fails closed. When the PRE binding carries semantic request
    identity, the executor must echo that exact request digest.
    """
    if not isinstance(prepared, EffectCallBinding):
        raise EffectInvocationCorrelationError("prepared must be an EffectCallBinding")
    values = {
        "EFFECT_ID": _token("effect_id", effect_id),
        "INVOCATION_ID": _token("observed_invocation_id", observed_invocation_id),
        "TOOL_USE_ID": _token("observed_tool_use_id", observed_tool_use_id),
        "DELEGATION_ID": _token("observed_delegation_id", observed_delegation_id),
        "BINDING_ID": _token("observed_binding_id", observed_binding_id),
        "CHILD_IDENTITY_SHA256": _token(
            "observed_child_identity_sha256", observed_child_identity_sha256
        ),
    }
    expected = {
        "EFFECT_ID": prepared.effect_id,
        "INVOCATION_ID": prepared.invocation_id,
        "TOOL_USE_ID": prepared.tool_use_id,
        "DELEGATION_ID": prepared.delegation_id,
        "BINDING_ID": prepared.binding_id,
        "CHILD_IDENTITY_SHA256": prepared.child_identity_sha256,
    }
    if prepared.request is not None:
        values["REQUEST_SHA256"] = _token(
            "observed_request_sha256", observed_request_sha256
        )
        expected["REQUEST_SHA256"] = prepared.request.sha256()
    for name, value in values.items():
        _match(name, value, expected[name])
    result_id = _token("result_id", result_id)
    result_sha256 = _token("result_sha256", result_sha256)

    if prepared.stage is EffectCorrelationStage.RESULT_OBSERVED:
        _match("RESULT_ID", result_id, prepared.result_id or "")
        _match("RESULT_SHA256", result_sha256, prepared.result_sha256 or "")
        return prepared
    if prepared.stage is not EffectCorrelationStage.PREPARED:
        raise EffectInvocationCorrelationError("POST_REQUIRES_PREPARED_STAGE")
    return replace(
        prepared,
        stage=EffectCorrelationStage.RESULT_OBSERVED,
        result_id=result_id,
        result_sha256=result_sha256,
    )


def bind_effect_return(
    observed: EffectCallBinding,
    target: DeferredExecutionVerificationTarget,
) -> EffectCallBinding:
    """Attach a WP-104 return only after exact POST result correlation.

    This closes the temporal gap between a true result-free PRE-dispatch envelope and
    the later result-bound WP-104/WP-105 target. It does not verify the external world
    outcome and does not mint completion.
    """
    if not isinstance(observed, EffectCallBinding):
        raise EffectInvocationCorrelationError("observed must be an EffectCallBinding")
    if observed.stage is not EffectCorrelationStage.RESULT_OBSERVED:
        raise EffectInvocationCorrelationError("RETURN_BINDING_REQUIRES_POST_RESULT")
    if not isinstance(target, DeferredExecutionVerificationTarget):
        raise EffectInvocationCorrelationError(
            "target must be a DeferredExecutionVerificationTarget"
        )

    binding = target.returned.binding
    expected = {
        "BINDING_ID": binding.binding_id(),
        "INVOCATION_ID": binding.invocation_id,
        "TOOL_USE_ID": binding.tool_use_id,
        "DELEGATION_ID": binding.delegation_id,
        "CHILD_IDENTITY_SHA256": binding.child.sha256(),
        "RESULT_ID": binding.result_id or "",
        "RESULT_SHA256": binding.result_sha256 or "",
    }
    actual = {
        "BINDING_ID": observed.binding_id,
        "INVOCATION_ID": observed.invocation_id,
        "TOOL_USE_ID": observed.tool_use_id,
        "DELEGATION_ID": observed.delegation_id,
        "CHILD_IDENTITY_SHA256": observed.child_identity_sha256,
        "RESULT_ID": observed.result_id or "",
        "RESULT_SHA256": observed.result_sha256 or "",
    }
    for name, value in actual.items():
        _match(name, value, expected[name])

    return_id = _token("return_id", target.returned.return_id)
    if observed.return_id is not None:
        _match("RETURN_ID", observed.return_id, return_id)
        return observed
    return replace(observed, return_id=return_id)


def apply_effect_bound_verification(
    target: DeferredExecutionVerificationTarget,
    observed: EffectCallBinding,
    transition: VerifyExecution,
) -> DeferredExecutionVerificationTarget:
    """Apply WP-105 verification only after exact PRE/POST/return correlation."""
    if not isinstance(target, DeferredExecutionVerificationTarget):
        raise EffectInvocationCorrelationError(
            "target must be a DeferredExecutionVerificationTarget"
        )
    if not isinstance(observed, EffectCallBinding):
        raise EffectInvocationCorrelationError("observed must be an EffectCallBinding")
    if observed.stage is not EffectCorrelationStage.RESULT_OBSERVED:
        raise EffectInvocationCorrelationError("VERIFICATION_REQUIRES_POST_RESULT")
    if observed.return_id is None:
        raise EffectInvocationCorrelationError("VERIFICATION_REQUIRES_RETURN_BINDING")
    if not isinstance(transition, VerifyExecution):
        raise EffectInvocationCorrelationError("transition must be VerifyExecution")

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
        _match(name, value, expected[name])

    correlated = CorrelatedVerification(
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
    try:
        return apply_correlated_verification(target, correlated)
    except DeferredExecutionVerificationError as exc:
        raise EffectInvocationCorrelationError(f"WP105_CORRELATION_REJECTED:{exc}") from exc


__all__ = [
    "EffectCallBinding",
    "EffectCorrelationStage",
    "EffectInvocationCorrelationError",
    "apply_effect_bound_verification",
    "bind_effect_return",
    "observe_effect_result",
    "prepare_effect_call",
]
