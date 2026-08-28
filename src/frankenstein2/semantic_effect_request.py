"""Semantic effect-request binding for Frankenstein 2.0 WP105.

The generic Stage-1 effect bridge already correlates effect/call identity and keeps
policy authority outside Frankenstein 2.0. This module closes a different boundary:
the canonical EntityOS EffectGate authorizes semantic request fields
(user/session/capability/target/argv/generation), so the same immutable request identity
must be present before authority evaluation, echoed by authority evidence, and consumed
at the executor boundary.

This module is policy-neutral. It does not decide ALLOW, mint canonical effect ids,
persist EffectJournal state, execute external effects, infer world outcomes, or mint
completion. It only makes semantic request substitution fail closed before dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable, Protocol

from .canonical_effect_authority_bridge import (
    CanonicalEffectAuthorityEvidence,
    CanonicalEffectAuthorityIdentity,
    EffectCallIntent,
    bind_canonical_effect,
)
from .effect_executor_interlock import (
    ExecutorObservation,
    InterlockResult,
    dispatch_through_external_gate,
)
from .effect_invocation_correlation import EffectCallBinding


REQUEST_IDENTITY_SCHEMA = "ENTITYOS_EFFECT_REQUEST_IDENTITY/v1"


class SemanticEffectRequestError(RuntimeError):
    """Fail-closed error at the semantic request / authority / executor boundary."""


def _token(name: str, value: object, *, max_len: int = 8192) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SemanticEffectRequestError(f"INVALID_{name.upper()}")
    if len(value) > max_len:
        raise SemanticEffectRequestError(f"INVALID_{name.upper()}")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise SemanticEffectRequestError(f"INVALID_{name.upper()}")
    return value


def _sha256(name: str, value: object) -> str:
    token = _token(name, value, max_len=64)
    if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
        raise SemanticEffectRequestError(f"INVALID_{name.upper()}")
    return token


@dataclass(frozen=True, slots=True)
class SemanticEffectRequest:
    """Immutable typed identity for the inputs consumed by EntityOS EffectGate.

    These fields mirror the currently admitted ``clayverse.effects.EffectRequest``
    semantic payload without importing that implementation into Frankenstein 2.0.
    ``request_sha256`` is derived from a canonical JSON representation and is never
    caller-selectable independently.
    """

    user_id: str
    session_id: str
    capability: str
    target: str
    argv: tuple[str, ...] | None = None
    expected_generation: int | None = None

    def __post_init__(self) -> None:
        _token("user_id", self.user_id, max_len=512)
        _token("session_id", self.session_id, max_len=512)
        _token("capability", self.capability, max_len=512)
        _token("target", self.target)
        if self.argv is not None:
            if not isinstance(self.argv, tuple):
                raise SemanticEffectRequestError("INVALID_ARGV")
            for index, value in enumerate(self.argv):
                _token(f"argv_{index}", value)
        if self.expected_generation is not None:
            if type(self.expected_generation) is not int or self.expected_generation < 0:
                raise SemanticEffectRequestError("INVALID_EXPECTED_GENERATION")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "schema": REQUEST_IDENTITY_SCHEMA,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "capability": self.capability,
            "target": self.target,
            "argv": list(self.argv) if self.argv is not None else None,
            "expected_generation": self.expected_generation,
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    def request_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class SemanticEffectCallIntent:
    """Pre-authority call plus the exact semantic request being authorized."""

    call: EffectCallIntent
    request: SemanticEffectRequest

    def __post_init__(self) -> None:
        if not isinstance(self.call, EffectCallIntent):
            raise SemanticEffectRequestError("INVALID_EFFECT_CALL_INTENT")
        if not isinstance(self.request, SemanticEffectRequest):
            raise SemanticEffectRequestError("INVALID_SEMANTIC_EFFECT_REQUEST")

    @property
    def request_sha256(self) -> str:
        return self.request.request_sha256()


@dataclass(frozen=True, slots=True)
class SemanticCanonicalEffectAuthorityEvidence:
    """Canonical authority evidence bound to one immutable semantic request digest."""

    authority: CanonicalEffectAuthorityEvidence
    effect_request_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.authority, CanonicalEffectAuthorityEvidence):
            raise SemanticEffectRequestError("INVALID_CANONICAL_AUTHORITY_EVIDENCE")
        _sha256("effect_request_sha256", self.effect_request_sha256)


@dataclass(frozen=True, slots=True)
class SemanticExecutorRequest:
    """Exact executor input: prepared effect call plus the authorized request semantics."""

    prepared: EffectCallBinding
    request: SemanticEffectRequest
    effect_request_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.prepared, EffectCallBinding):
            raise SemanticEffectRequestError("INVALID_PREPARED_EFFECT_CALL")
        if not isinstance(self.request, SemanticEffectRequest):
            raise SemanticEffectRequestError("INVALID_SEMANTIC_EFFECT_REQUEST")
        digest = _sha256("effect_request_sha256", self.effect_request_sha256)
        if digest != self.request.request_sha256():
            raise SemanticEffectRequestError("EXECUTOR_EFFECT_REQUEST_SHA256_MISMATCH")


class SemanticCanonicalAuthorizer(Protocol):
    def __call__(
        self, intent: SemanticEffectCallIntent
    ) -> SemanticCanonicalEffectAuthorityEvidence: ...


class SemanticEffectExecutor(Protocol):
    def __call__(self, request: SemanticExecutorRequest) -> ExecutorObservation: ...


@dataclass(frozen=True, slots=True)
class SemanticCanonicalDispatchResult:
    """One semantic authority evaluation plus optional exact executor dispatch."""

    authority: SemanticCanonicalEffectAuthorityEvidence
    interlock: InterlockResult | None

    @property
    def dispatched(self) -> bool:
        return bool(self.interlock is not None and self.interlock.dispatched)


def dispatch_semantic_with_canonical_authority(
    intent: SemanticEffectCallIntent,
    *,
    expected_authority: CanonicalEffectAuthorityIdentity,
    authorize: Callable[
        [SemanticEffectCallIntent], SemanticCanonicalEffectAuthorityEvidence
    ],
    executor: Callable[[SemanticExecutorRequest], ExecutorObservation],
) -> SemanticCanonicalDispatchResult:
    """Dispatch only when authority and executor bind the same semantic request.

    The function never retries. Policy remains in the external canonical authority.
    A semantic digest mismatch is rejected before the generic executor interlock is
    entered, so no executor invocation can occur on a substituted request.
    """
    if not isinstance(intent, SemanticEffectCallIntent):
        raise SemanticEffectRequestError("INVALID_SEMANTIC_EFFECT_CALL_INTENT")
    if not isinstance(expected_authority, CanonicalEffectAuthorityIdentity):
        raise SemanticEffectRequestError("EXPECTED_AUTHORITY_UNRESOLVED")
    if not callable(authorize):
        raise SemanticEffectRequestError("SEMANTIC_AUTHORITY_NOT_CALLABLE")
    if not callable(executor):
        raise SemanticEffectRequestError("SEMANTIC_EXECUTOR_NOT_CALLABLE")

    try:
        evidence = authorize(intent)
    except Exception as exc:
        raise SemanticEffectRequestError("CANONICAL_EFFECT_AUTHORITY_FAILED") from exc
    if not isinstance(evidence, SemanticCanonicalEffectAuthorityEvidence):
        raise SemanticEffectRequestError(
            "CANONICAL_EFFECT_AUTHORITY_RETURNED_UNBOUND_SEMANTIC_EVIDENCE"
        )
    if evidence.effect_request_sha256 != intent.request_sha256:
        raise SemanticEffectRequestError("EFFECT_REQUEST_SHA256_MISMATCH")

    binding = bind_canonical_effect(
        intent.call,
        evidence.authority,
        expected_authority=expected_authority,
    )
    if not binding.dispatchable:
        return SemanticCanonicalDispatchResult(authority=evidence, interlock=None)

    assert binding.prepared is not None and binding.gate is not None

    def dispatch_exact_request(prepared: EffectCallBinding) -> ExecutorObservation:
        return executor(
            SemanticExecutorRequest(
                prepared=prepared,
                request=intent.request,
                effect_request_sha256=intent.request_sha256,
            )
        )

    interlock = dispatch_through_external_gate(
        binding.prepared,
        authorize=lambda _prepared: binding.gate,
        executor=dispatch_exact_request,
    )
    return SemanticCanonicalDispatchResult(authority=evidence, interlock=interlock)


__all__ = [
    "REQUEST_IDENTITY_SCHEMA",
    "SemanticCanonicalAuthorizer",
    "SemanticCanonicalDispatchResult",
    "SemanticCanonicalEffectAuthorityEvidence",
    "SemanticEffectCallIntent",
    "SemanticEffectExecutor",
    "SemanticEffectRequest",
    "SemanticEffectRequestError",
    "SemanticExecutorRequest",
    "dispatch_semantic_with_canonical_authority",
]
