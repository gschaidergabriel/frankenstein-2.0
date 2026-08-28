"""Canonical EffectGate/EffectJournal identity bridge for Frankenstein 2.0 Stage 1.

This module closes one specific authority gap: Frankenstein must not invent an
``effect_id`` before the canonical effect authority has admitted/journaled the
request.  A caller first constructs an :class:`EffectCallIntent`, which contains
only the already-bound WP-102/WP-104 invocation identity.  An external canonical
authority port then returns :class:`CanonicalEffectAuthorityEvidence`.

Only an exact canonical ``ALLOW`` with a canonically minted ``effect_id`` in
``PENDING`` journal state is converted into the existing immutable
``EffectCallBinding`` and allowed to reach the policy-neutral executor interlock.
Every other decision remains non-dispatching.  In particular, a pending/unknown
restart outcome is never replayed automatically.

This is an adapter contract, not a second EffectGate and not runtime proof that the
current EntityOS EffectGate has been wired to this port.  Policy, canonical state,
EffectJournal transitions and recovery authority remain external.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .effect_executor_interlock import (
    EffectExecutor,
    ExternalGateDecision,
    ExternalGateEvidence,
    InterlockResult,
    dispatch_through_external_gate,
)
from .effect_invocation_correlation import EffectCallBinding, EffectCorrelationStage


class CanonicalEffectAuthorityBridgeError(RuntimeError):
    """Fail-closed error at the canonical-authority/Frankenstein boundary."""


class CanonicalEffectAuthorityIdentityError(CanonicalEffectAuthorityBridgeError):
    """The authority response is incomplete or belongs to another call."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CanonicalEffectAuthorityIdentityError(f"INVALID_{name.upper()}")
    if len(value) > 512 or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CanonicalEffectAuthorityIdentityError(f"INVALID_{name.upper()}")
    return value


@dataclass(frozen=True, slots=True)
class EffectCallIntent:
    """Pre-authority call identity.  Deliberately has no ``effect_id`` field."""

    return_id: str
    binding_id: str
    invocation_id: str
    tool_use_id: str
    delegation_id: str
    child_identity_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "return_id",
            "binding_id",
            "invocation_id",
            "tool_use_id",
            "delegation_id",
            "child_identity_sha256",
        ):
            _token(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class CanonicalEffectAuthorityEvidence:
    """Typed result emitted by the canonical effect-authority adapter.

    ``effect_id`` is optional for non-ALLOW decisions.  For ALLOW it is mandatory
    and must refer to an already-created canonical ``PENDING`` EffectJournal row.
    The correlation envelope is echoed by the authority adapter and checked before
    an executor callable can be reached.
    """

    authority_ref: str
    decision_id: str
    decision: ExternalGateDecision
    journal_state: str
    effect_id: str | None
    return_id: str
    binding_id: str
    invocation_id: str
    tool_use_id: str
    delegation_id: str
    child_identity_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "authority_ref",
            "decision_id",
            "journal_state",
            "return_id",
            "binding_id",
            "invocation_id",
            "tool_use_id",
            "delegation_id",
            "child_identity_sha256",
        ):
            _token(name, getattr(self, name))
        if not isinstance(self.decision, ExternalGateDecision):
            raise CanonicalEffectAuthorityIdentityError("INVALID_DECISION")
        if self.effect_id is not None:
            _token("effect_id", self.effect_id)
        if self.decision is ExternalGateDecision.ALLOW:
            if self.effect_id is None:
                raise CanonicalEffectAuthorityIdentityError(
                    "CANONICAL_ALLOW_REQUIRES_EFFECT_ID"
                )
            if self.journal_state != "PENDING":
                raise CanonicalEffectAuthorityIdentityError(
                    "CANONICAL_ALLOW_REQUIRES_PENDING_JOURNAL"
                )


class CanonicalEffectAuthorityPort(Protocol):
    """Production implementation must be backed by canonical EffectGate/Journal."""

    def __call__(self, intent: EffectCallIntent) -> CanonicalEffectAuthorityEvidence: ...


@dataclass(frozen=True, slots=True)
class CanonicalEffectBinding:
    """Result of validating canonical authority against one exact intent."""

    authority: CanonicalEffectAuthorityEvidence
    prepared: EffectCallBinding | None
    gate: ExternalGateEvidence | None

    @property
    def dispatchable(self) -> bool:
        return self.prepared is not None and self.gate is not None


@dataclass(frozen=True, slots=True)
class CanonicalDispatchResult:
    """One authority evaluation plus an optional executor-interlock result."""

    authority: CanonicalEffectAuthorityEvidence
    interlock: InterlockResult | None

    @property
    def dispatched(self) -> bool:
        return bool(self.interlock is not None and self.interlock.dispatched)


def intent_from_prepared_candidate(prepared: EffectCallBinding) -> EffectCallIntent:
    """Migrate an existing call envelope while discarding its caller effect id.

    The old/pre-canonical ``effect_id`` is intentionally not copied.  This permits
    incremental migration of WP-105 call sites without granting the old value any
    authority at the canonical boundary.
    """
    if not isinstance(prepared, EffectCallBinding):
        raise CanonicalEffectAuthorityIdentityError(
            "prepared must be an EffectCallBinding"
        )
    if prepared.stage is not EffectCorrelationStage.PREPARED:
        raise CanonicalEffectAuthorityIdentityError("INTENT_REQUIRES_PREPARED_CALL")
    return EffectCallIntent(
        return_id=prepared.return_id,
        binding_id=prepared.binding_id,
        invocation_id=prepared.invocation_id,
        tool_use_id=prepared.tool_use_id,
        delegation_id=prepared.delegation_id,
        child_identity_sha256=prepared.child_identity_sha256,
    )


def _assert_same_call(
    intent: EffectCallIntent,
    evidence: CanonicalEffectAuthorityEvidence,
) -> None:
    expected = {
        "RETURN_ID": intent.return_id,
        "BINDING_ID": intent.binding_id,
        "INVOCATION_ID": intent.invocation_id,
        "TOOL_USE_ID": intent.tool_use_id,
        "DELEGATION_ID": intent.delegation_id,
        "CHILD_IDENTITY_SHA256": intent.child_identity_sha256,
    }
    actual = {
        "RETURN_ID": evidence.return_id,
        "BINDING_ID": evidence.binding_id,
        "INVOCATION_ID": evidence.invocation_id,
        "TOOL_USE_ID": evidence.tool_use_id,
        "DELEGATION_ID": evidence.delegation_id,
        "CHILD_IDENTITY_SHA256": evidence.child_identity_sha256,
    }
    for name, value in actual.items():
        if value != expected[name]:
            raise CanonicalEffectAuthorityIdentityError(f"{name}_MISMATCH")


def bind_canonical_effect(
    intent: EffectCallIntent,
    evidence: CanonicalEffectAuthorityEvidence,
) -> CanonicalEffectBinding:
    """Bind only a canonically minted ALLOW effect id to the exact call intent."""
    if not isinstance(intent, EffectCallIntent):
        raise CanonicalEffectAuthorityIdentityError("INVALID_EFFECT_CALL_INTENT")
    if not isinstance(evidence, CanonicalEffectAuthorityEvidence):
        raise CanonicalEffectAuthorityIdentityError("INVALID_CANONICAL_AUTHORITY_EVIDENCE")
    _assert_same_call(intent, evidence)

    if evidence.decision is not ExternalGateDecision.ALLOW:
        return CanonicalEffectBinding(authority=evidence, prepared=None, gate=None)

    assert evidence.effect_id is not None  # enforced by dataclass validation
    prepared = EffectCallBinding(
        effect_id=evidence.effect_id,
        return_id=intent.return_id,
        binding_id=intent.binding_id,
        invocation_id=intent.invocation_id,
        tool_use_id=intent.tool_use_id,
        delegation_id=intent.delegation_id,
        child_identity_sha256=intent.child_identity_sha256,
        stage=EffectCorrelationStage.PREPARED,
    )
    gate = ExternalGateEvidence(
        authority_ref=evidence.authority_ref,
        decision_id=evidence.decision_id,
        decision=evidence.decision,
        effect_id=evidence.effect_id,
        binding_id=intent.binding_id,
        invocation_id=intent.invocation_id,
        tool_use_id=intent.tool_use_id,
        delegation_id=intent.delegation_id,
        child_identity_sha256=intent.child_identity_sha256,
    )
    return CanonicalEffectBinding(authority=evidence, prepared=prepared, gate=gate)


def dispatch_with_canonical_authority(
    intent: EffectCallIntent,
    *,
    authorize: Callable[[EffectCallIntent], CanonicalEffectAuthorityEvidence],
    executor: EffectExecutor,
) -> CanonicalDispatchResult:
    """Evaluate canonical authority once and dispatch only its exact pending ALLOW.

    The canonical adapter is called exactly once.  DENY, REQUIRE_CONFIRMATION,
    DEGRADE_TO_PROPOSAL and UNKNOWN never invoke ``executor``.  For ALLOW, the
    existing policy-neutral interlock performs the final identity check and POST
    correlation.  Executor exceptions retain the existing UNKNOWN/no-replay law.
    """
    if not isinstance(intent, EffectCallIntent):
        raise CanonicalEffectAuthorityIdentityError("INVALID_EFFECT_CALL_INTENT")
    if not callable(authorize):
        raise CanonicalEffectAuthorityBridgeError("CANONICAL_AUTHORITY_NOT_CALLABLE")
    if not callable(executor):
        raise CanonicalEffectAuthorityBridgeError("EXECUTOR_NOT_CALLABLE")
    try:
        evidence = authorize(intent)
    except Exception as exc:
        raise CanonicalEffectAuthorityBridgeError(
            "CANONICAL_EFFECT_AUTHORITY_FAILED"
        ) from exc
    binding = bind_canonical_effect(intent, evidence)
    if not binding.dispatchable:
        return CanonicalDispatchResult(authority=evidence, interlock=None)
    assert binding.prepared is not None and binding.gate is not None
    interlock = dispatch_through_external_gate(
        binding.prepared,
        authorize=lambda _prepared: binding.gate,
        executor=executor,
    )
    return CanonicalDispatchResult(authority=evidence, interlock=interlock)


__all__ = [
    "CanonicalDispatchResult",
    "CanonicalEffectAuthorityBridgeError",
    "CanonicalEffectAuthorityEvidence",
    "CanonicalEffectAuthorityIdentityError",
    "CanonicalEffectAuthorityPort",
    "CanonicalEffectBinding",
    "EffectCallIntent",
    "bind_canonical_effect",
    "dispatch_with_canonical_authority",
    "intent_from_prepared_candidate",
]
