"""Canonical effect-authority identity bridge for Frankenstein 2.0 Stage 1.

Frankenstein must not invent an ``effect_id`` before the canonical effect authority
has admitted and journaled the request. A caller therefore starts with an
:class:`EffectCallIntent`, which deliberately has no effect id. A separately resolved
canonical authority implementation then returns typed evidence containing the
authoritative effect id and exact call identity.

Canonical dispatch additionally requires an immutable semantic
``EffectRequestIdentity``. Its digest is echoed by authority evidence, copied into the
PRE-dispatch binding, checked by the executor interlock, and checked again on the POST
observation. This prevents an ALLOW for semantic request B from authorizing call A even
when the correlation identifiers are otherwise identical.

This module does not decide which implementation is canonical. The expected
:class:`CanonicalEffectAuthorityIdentity` must come from a current-authority binding
outside Frankenstein 2.0. Merely constructing an identity object here cannot admit a
compatibility/donor implementation. The bridge only verifies that the authority
response matches that already-resolved identity and the exact result-free call/request.

Only exact ``ALLOW`` with a canonically minted ``effect_id`` in ``PENDING`` journal
state becomes a dispatchable ``EffectCallBinding``. Every other decision remains
non-dispatching, and restart uncertainty is never replayed automatically.
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
from .effect_request_identity import EffectRequestIdentity


class CanonicalEffectAuthorityBridgeError(RuntimeError):
    """Fail-closed error at the canonical-authority/Frankenstein boundary."""


class CanonicalEffectAuthorityIdentityError(CanonicalEffectAuthorityBridgeError):
    """The authority response is incomplete, stale, or belongs to another call."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CanonicalEffectAuthorityIdentityError(f"INVALID_{name.upper()}")
    if len(value) > 512 or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CanonicalEffectAuthorityIdentityError(f"INVALID_{name.upper()}")
    return value


def _git_sha(name: str, value: object) -> str:
    token = _token(name, value)
    if len(token) != 40 or any(ch not in "0123456789abcdef" for ch in token):
        raise CanonicalEffectAuthorityIdentityError(f"INVALID_{name.upper()}")
    return token


def _sha256(name: str, value: object) -> str:
    token = _token(name, value)
    if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
        raise CanonicalEffectAuthorityIdentityError(f"INVALID_{name.upper()}")
    return token


@dataclass(frozen=True, slots=True)
class CanonicalEffectAuthorityIdentity:
    """Exact executable identity resolved by current authority outside this module."""

    repository: str
    commit_sha: str
    module_path: str
    source_blob_sha: str
    state_schema: str
    api_version: str

    def __post_init__(self) -> None:
        _token("repository", self.repository)
        _git_sha("commit_sha", self.commit_sha)
        _token("module_path", self.module_path)
        _git_sha("source_blob_sha", self.source_blob_sha)
        _token("state_schema", self.state_schema)
        _token("api_version", self.api_version)

    def authority_ref(self) -> str:
        """Stable transport reference; this string does not itself grant authority."""
        return (
            f"{self.repository}@{self.commit_sha}:"
            f"{self.module_path}#{self.source_blob_sha}:"
            f"{self.state_schema}:{self.api_version}"
        )


@dataclass(frozen=True, slots=True)
class EffectCallIntent:
    """Pre-authority call plus immutable semantic request identity.

    ``request`` is optional only so old serialized/test envelopes remain constructible.
    Canonical binding and dispatch fail closed unless it is present.
    """

    return_id: str | None
    binding_id: str
    invocation_id: str
    tool_use_id: str
    delegation_id: str
    child_identity_sha256: str
    request: EffectRequestIdentity | None = None

    def __post_init__(self) -> None:
        if self.return_id is not None:
            _token("return_id", self.return_id)
        for name in (
            "binding_id",
            "invocation_id",
            "tool_use_id",
            "delegation_id",
            "child_identity_sha256",
        ):
            _token(name, getattr(self, name))
        if self.request is not None and not isinstance(self.request, EffectRequestIdentity):
            raise CanonicalEffectAuthorityIdentityError("INVALID_EFFECT_REQUEST_IDENTITY")

    @property
    def request_sha256(self) -> str | None:
        return self.request.sha256() if self.request is not None else None


@dataclass(frozen=True, slots=True)
class CanonicalEffectAuthorityEvidence:
    """Typed response from an already-resolved canonical effect-authority adapter.

    ``effect_id`` is optional for non-ALLOW decisions. For ALLOW it is mandatory and
    must refer to a canonical ``PENDING`` journal row created before dispatch.
    ``authority`` is checked against a separately supplied expected identity; a
    caller-authored identity cannot self-grant canonical status. ``request_sha256``
    must echo the exact immutable semantic request evaluated by the authority.
    """

    authority: CanonicalEffectAuthorityIdentity
    decision_id: str
    decision: ExternalGateDecision
    journal_state: str
    effect_id: str | None
    return_id: str | None
    binding_id: str
    invocation_id: str
    tool_use_id: str
    delegation_id: str
    child_identity_sha256: str
    request_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.authority, CanonicalEffectAuthorityIdentity):
            raise CanonicalEffectAuthorityIdentityError("INVALID_AUTHORITY_IDENTITY")
        for name in (
            "decision_id",
            "journal_state",
            "binding_id",
            "invocation_id",
            "tool_use_id",
            "delegation_id",
            "child_identity_sha256",
        ):
            _token(name, getattr(self, name))
        if self.return_id is not None:
            _token("return_id", self.return_id)
        if self.request_sha256 is not None:
            _sha256("request_sha256", self.request_sha256)
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
    """Production implementation must be backed by the admitted canonical authority."""

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
    """Migrate a PRE envelope while discarding its caller-authored effect id.

    Canonical migration requires the PRE envelope already to carry immutable semantic
    request identity. A legacy correlation-only envelope is deliberately rejected.
    """
    if not isinstance(prepared, EffectCallBinding):
        raise CanonicalEffectAuthorityIdentityError(
            "prepared must be an EffectCallBinding"
        )
    if prepared.stage is not EffectCorrelationStage.PREPARED:
        raise CanonicalEffectAuthorityIdentityError("INTENT_REQUIRES_PREPARED_CALL")
    if prepared.request is None:
        raise CanonicalEffectAuthorityIdentityError(
            "SEMANTIC_EFFECT_REQUEST_UNRESOLVED"
        )
    return EffectCallIntent(
        return_id=prepared.return_id,
        binding_id=prepared.binding_id,
        invocation_id=prepared.invocation_id,
        tool_use_id=prepared.tool_use_id,
        delegation_id=prepared.delegation_id,
        child_identity_sha256=prepared.child_identity_sha256,
        request=prepared.request,
    )


def _assert_same_call(
    intent: EffectCallIntent,
    evidence: CanonicalEffectAuthorityEvidence,
) -> None:
    if intent.request is None:
        raise CanonicalEffectAuthorityIdentityError(
            "SEMANTIC_EFFECT_REQUEST_UNRESOLVED"
        )
    expected = {
        "RETURN_ID": intent.return_id,
        "BINDING_ID": intent.binding_id,
        "INVOCATION_ID": intent.invocation_id,
        "TOOL_USE_ID": intent.tool_use_id,
        "DELEGATION_ID": intent.delegation_id,
        "CHILD_IDENTITY_SHA256": intent.child_identity_sha256,
        "REQUEST_SHA256": intent.request.sha256(),
    }
    actual = {
        "RETURN_ID": evidence.return_id,
        "BINDING_ID": evidence.binding_id,
        "INVOCATION_ID": evidence.invocation_id,
        "TOOL_USE_ID": evidence.tool_use_id,
        "DELEGATION_ID": evidence.delegation_id,
        "CHILD_IDENTITY_SHA256": evidence.child_identity_sha256,
        "REQUEST_SHA256": _sha256("request_sha256", evidence.request_sha256),
    }
    for name, value in actual.items():
        if value != expected[name]:
            raise CanonicalEffectAuthorityIdentityError(f"{name}_MISMATCH")


def bind_canonical_effect(
    intent: EffectCallIntent,
    evidence: CanonicalEffectAuthorityEvidence,
    *,
    expected_authority: CanonicalEffectAuthorityIdentity,
) -> CanonicalEffectBinding:
    """Bind only an exact semantic request and pending canonical ALLOW."""
    if not isinstance(intent, EffectCallIntent):
        raise CanonicalEffectAuthorityIdentityError("INVALID_EFFECT_CALL_INTENT")
    if intent.request is None:
        raise CanonicalEffectAuthorityIdentityError(
            "SEMANTIC_EFFECT_REQUEST_UNRESOLVED"
        )
    if not isinstance(evidence, CanonicalEffectAuthorityEvidence):
        raise CanonicalEffectAuthorityIdentityError("INVALID_CANONICAL_AUTHORITY_EVIDENCE")
    if not isinstance(expected_authority, CanonicalEffectAuthorityIdentity):
        raise CanonicalEffectAuthorityIdentityError("EXPECTED_AUTHORITY_UNRESOLVED")
    if evidence.authority != expected_authority:
        raise CanonicalEffectAuthorityIdentityError("AUTHORITY_IDENTITY_MISMATCH")
    _assert_same_call(intent, evidence)

    if evidence.decision is not ExternalGateDecision.ALLOW:
        return CanonicalEffectBinding(authority=evidence, prepared=None, gate=None)

    assert evidence.effect_id is not None
    request_sha256 = intent.request.sha256()
    prepared = EffectCallBinding(
        effect_id=evidence.effect_id,
        return_id=intent.return_id,
        binding_id=intent.binding_id,
        invocation_id=intent.invocation_id,
        tool_use_id=intent.tool_use_id,
        delegation_id=intent.delegation_id,
        child_identity_sha256=intent.child_identity_sha256,
        stage=EffectCorrelationStage.PREPARED,
        request=intent.request,
    )
    gate = ExternalGateEvidence(
        authority_ref=expected_authority.authority_ref(),
        decision_id=evidence.decision_id,
        decision=evidence.decision,
        effect_id=evidence.effect_id,
        binding_id=intent.binding_id,
        invocation_id=intent.invocation_id,
        tool_use_id=intent.tool_use_id,
        delegation_id=intent.delegation_id,
        child_identity_sha256=intent.child_identity_sha256,
        request_sha256=request_sha256,
    )
    return CanonicalEffectBinding(authority=evidence, prepared=prepared, gate=gate)


def dispatch_with_canonical_authority(
    intent: EffectCallIntent,
    *,
    expected_authority: CanonicalEffectAuthorityIdentity,
    authorize: Callable[[EffectCallIntent], CanonicalEffectAuthorityEvidence],
    executor: EffectExecutor,
) -> CanonicalDispatchResult:
    """Evaluate one exact authority and dispatch only its exact pending ALLOW.

    The expected authority identity must already have been resolved by current project
    authority; this module cannot discover or admit it. DENY, REQUIRE_CONFIRMATION,
    DEGRADE_TO_PROPOSAL, UNKNOWN, authority failure, source-identity mismatch,
    call-identity mismatch, and semantic-request mismatch all stop before the executor.
    """
    if not isinstance(intent, EffectCallIntent):
        raise CanonicalEffectAuthorityIdentityError("INVALID_EFFECT_CALL_INTENT")
    if intent.request is None:
        raise CanonicalEffectAuthorityIdentityError(
            "SEMANTIC_EFFECT_REQUEST_UNRESOLVED"
        )
    if not isinstance(expected_authority, CanonicalEffectAuthorityIdentity):
        raise CanonicalEffectAuthorityIdentityError("EXPECTED_AUTHORITY_UNRESOLVED")
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
    binding = bind_canonical_effect(
        intent,
        evidence,
        expected_authority=expected_authority,
    )
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
    "CanonicalEffectAuthorityIdentity",
    "CanonicalEffectAuthorityIdentityError",
    "CanonicalEffectAuthorityPort",
    "CanonicalEffectBinding",
    "EffectCallIntent",
    "bind_canonical_effect",
    "dispatch_with_canonical_authority",
    "intent_from_prepared_candidate",
]
