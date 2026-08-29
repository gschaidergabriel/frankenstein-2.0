"""Provenance-bound uncertainty adapter for the canonical EntityOS EffectGate boundary.

F2-WP-105 generation 4.

This module is not an effect authority, journal, executor, replay authority, or source of
canonical EntityOS types. It translates only uncertainty emitted by the real F2
``dispatch_through_external_gate`` path that this adapter invokes itself.

The previous generation accepted an arbitrary zero-argument ``dispatch`` callable and
therefore could not distinguish a genuine post-dispatch ``ExecutorOutcomeUnknown`` from
the same public exception class raised directly by caller code. Generation 4 removes
that nominal-type-only boundary. Callers must supply an exact prepared EffectCallBinding,
authorizer, and executor; the adapter enters the F2 interlock itself. Pre-dispatch errors
remain definite interlock errors. Only an ``ExecutorOutcomeUnknown`` emitted from inside
that structural path is translated to the already-supplied canonical UNKNOWN type.
"""
from __future__ import annotations

from collections.abc import Callable

from .effect_executor_interlock import (
    ExecutorObservation,
    ExecutorOutcomeUnknown,
    ExternalGateEvidence,
    InterlockResult,
    dispatch_through_external_gate,
)
from .effect_invocation_correlation import EffectCallBinding


class EntityOSUnknownOutcomeAdapterError(RuntimeError):
    """Fail-closed adapter configuration or boundary error."""


def _prepared_canonical_unknown(canonical_unknown_type: object) -> BaseException:
    if not isinstance(canonical_unknown_type, type) or not issubclass(
        canonical_unknown_type, BaseException
    ):
        raise EntityOSUnknownOutcomeAdapterError("CANONICAL_UNKNOWN_TYPE_INVALID")
    if getattr(canonical_unknown_type, "replay_permitted", None) is not False:
        raise EntityOSUnknownOutcomeAdapterError(
            "CANONICAL_UNKNOWN_MUST_FORBID_REPLAY"
        )
    try:
        prepared = canonical_unknown_type(
            "F2 executor return unknown after dispatch; automatic replay forbidden"
        )
    except Exception as exc:
        raise EntityOSUnknownOutcomeAdapterError(
            "CANONICAL_UNKNOWN_CONSTRUCTION_FAILED"
        ) from exc
    if not isinstance(prepared, BaseException):
        raise EntityOSUnknownOutcomeAdapterError("CANONICAL_UNKNOWN_INSTANCE_INVALID")
    if getattr(prepared, "replay_permitted", None) is not False:
        raise EntityOSUnknownOutcomeAdapterError(
            "CANONICAL_UNKNOWN_INSTANCE_MUST_FORBID_REPLAY"
        )
    return prepared


def translate_executor_unknown_to_canonical(
    prepared: EffectCallBinding,
    *,
    authorize: Callable[[EffectCallBinding], ExternalGateEvidence],
    executor: Callable[[EffectCallBinding], ExecutorObservation],
    canonical_unknown_type: type[BaseException],
) -> InterlockResult:
    """Run the exact F2 interlock and translate only its post-dispatch UNKNOWN result.

    An arbitrary callable is deliberately not accepted. This makes the provenance of the
    translated uncertainty structural: ``dispatch_through_external_gate`` validates the
    PRE binding and gate identity before it invokes ``executor``; it emits
    ``ExecutorOutcomeUnknown`` only after executor entry or when a returned POST
    observation cannot be safely correlated. Its pre-dispatch failures remain
    ``ExecutorInterlockError`` and are not translated here.
    """
    if not isinstance(prepared, EffectCallBinding):
        raise EntityOSUnknownOutcomeAdapterError("PREPARED_EFFECT_CALL_REQUIRED")
    if not callable(authorize):
        raise EntityOSUnknownOutcomeAdapterError("AUTHORIZE_NOT_CALLABLE")
    if not callable(executor):
        raise EntityOSUnknownOutcomeAdapterError("EXECUTOR_NOT_CALLABLE")

    # Validate the target canonical UNKNOWN contract before crossing the interlock so a
    # malformed adapter configuration cannot turn an attempted effect into uncertainty.
    prepared_unknown = _prepared_canonical_unknown(canonical_unknown_type)
    try:
        return dispatch_through_external_gate(
            prepared,
            authorize=authorize,
            executor=executor,
        )
    except ExecutorOutcomeUnknown as exc:
        raise prepared_unknown from exc


__all__ = [
    "EntityOSUnknownOutcomeAdapterError",
    "translate_executor_unknown_to_canonical",
]
