"""Bijective PRE-dispatch adapter for the existing canonical effect bridge.

This module creates no effect authority. The caller supplies the already-resolved
canonical authority identity and an already-selected canonical UnifiedDB connection.
The canonical authority still mints ``effect_id`` and owns EffectJournal semantics.
This adapter only refuses ambiguous call/effect reuse and persists that relationship
before the existing executor interlock is entered.
"""
from __future__ import annotations

import sqlite3
from typing import Callable

from .canonical_effect_authority_bridge import (
    CanonicalDispatchResult,
    CanonicalEffectAuthorityBridgeError,
    CanonicalEffectAuthorityEvidence,
    CanonicalEffectAuthorityIdentity,
    CanonicalEffectAuthorityIdentityError,
    EffectCallIntent,
    bind_canonical_effect,
)
from .effect_executor_interlock import EffectExecutor, dispatch_through_external_gate
from .effect_invocation_bijection import (
    durably_bind_prepared_effect_call,
    require_effect_invocation_bijection_ready,
)


def dispatch_with_canonical_authority_bijective(
    intent: EffectCallIntent,
    *,
    expected_authority: CanonicalEffectAuthorityIdentity,
    authorize: Callable[[EffectCallIntent], CanonicalEffectAuthorityEvidence],
    executor: EffectExecutor,
    bijection_connection: sqlite3.Connection,
) -> CanonicalDispatchResult:
    """Dispatch only after durable immutable invocation <-> canonical-effect binding."""
    if not isinstance(intent, EffectCallIntent):
        raise CanonicalEffectAuthorityIdentityError("INVALID_EFFECT_CALL_INTENT")
    if intent.request is None:
        raise CanonicalEffectAuthorityIdentityError("SEMANTIC_EFFECT_REQUEST_UNRESOLVED")
    if not isinstance(expected_authority, CanonicalEffectAuthorityIdentity):
        raise CanonicalEffectAuthorityIdentityError("EXPECTED_AUTHORITY_UNRESOLVED")
    if not callable(authorize):
        raise CanonicalEffectAuthorityBridgeError("CANONICAL_AUTHORITY_NOT_CALLABLE")
    if not callable(executor):
        raise CanonicalEffectAuthorityBridgeError("EXECUTOR_NOT_CALLABLE")

    # Fail before authority evaluation if this assembly path cannot safely persist the
    # relationship. Dispatch never initializes schema implicitly.
    require_effect_invocation_bijection_ready(bijection_connection)

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
    durably_bind_prepared_effect_call(
        bijection_connection,
        binding.prepared,
        generation=intent.request.expected_generation,
    )
    interlock = dispatch_through_external_gate(
        binding.prepared,
        authorize=lambda _prepared: binding.gate,
        executor=executor,
    )
    return CanonicalDispatchResult(authority=evidence, interlock=interlock)


__all__ = ["dispatch_with_canonical_authority_bijective"]
