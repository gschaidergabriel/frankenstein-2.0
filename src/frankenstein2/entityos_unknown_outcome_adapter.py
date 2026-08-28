"""Narrow uncertainty-type adapter for the existing canonical EntityOS EffectGate boundary.

This module is not an effect authority, journal, executor, replay authority, or source of
canonical EntityOS types.  It only translates the F2 interlock's post-dispatch
``ExecutorOutcomeUnknown`` into an already-supplied canonical unknown exception type.

The canonical exception type is validated and instantiated *before* the dispatch callable
is entered.  A bad adapter configuration therefore fails before the executor can run.
All exceptions other than ``ExecutorOutcomeUnknown`` propagate unchanged.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from .effect_executor_interlock import ExecutorOutcomeUnknown


_T = TypeVar("_T")


class EntityOSUnknownOutcomeAdapterError(RuntimeError):
    """The caller did not provide a safe canonical UNKNOWN exception contract."""


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
    dispatch: Callable[[], _T],
    *,
    canonical_unknown_type: type[BaseException],
) -> _T:
    """Translate only a post-dispatch F2 uncertainty into canonical UNKNOWN semantics.

    ``ExecutorOutcomeUnknown`` is emitted by the F2 executor interlock only after the
    executor callable has been entered or after its return cannot be safely validated.
    The adapter deliberately does not catch pre-dispatch interlock failures or arbitrary
    executor exceptions.  The canonical EffectGate remains responsible for journaling.
    """
    if not callable(dispatch):
        raise EntityOSUnknownOutcomeAdapterError("DISPATCH_NOT_CALLABLE")
    prepared_unknown = _prepared_canonical_unknown(canonical_unknown_type)
    try:
        return dispatch()
    except ExecutorOutcomeUnknown as exc:
        raise prepared_unknown from exc


__all__ = [
    "EntityOSUnknownOutcomeAdapterError",
    "translate_executor_unknown_to_canonical",
]
