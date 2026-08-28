"""Candidate WP105 topology for one canonical real-effect authority call.

This module is intentionally a candidate integration surface, not a new EffectGate.
It addresses a concrete topology mismatch: the currently bound EntityOS
``EffectGate.execute`` owns policy, journal-before-effect ordering, lease custody,
execution, and journal finalization in one call. Treating that call as a mere
pre-dispatch authorizer and then invoking a second Frankenstein executor would risk
executing the same logical effect twice.

The function below therefore has *no executor parameter*. It invokes an already-bound
canonical transaction port exactly once, verifies that the returned evidence belongs
to the exact current authority and F2 call intent, and accepts only a terminal
canonical journal state. Any exception is outcome-unknown and never grants replay.

Source/deterministic-test scope only. This module does not itself execute a real effect,
read/write UnifiedDB, mint canonical authority, or establish runtime acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Final, Protocol

from .canonical_effect_authority_bridge import (
    CanonicalEffectAuthorityIdentity,
    EffectCallIntent,
)


class CanonicalSingleAuthorityError(RuntimeError):
    """Fail-closed error at the single-authority transaction boundary."""


class CanonicalAuthorityOutcomeUnknown(CanonicalSingleAuthorityError):
    """The authority call may have crossed the effect boundary; replay is forbidden."""

    replay_permitted: Final[bool] = False


class CanonicalTerminalDisposition(str, Enum):
    VERIFIED = "CANONICAL_VERIFIED"
    DENIED = "CANONICAL_DENIED"
    FAILED = "CANONICAL_FAILED"
    STALE = "CANONICAL_STALE_OUTCOME"
    UNKNOWN = "CANONICAL_UNKNOWN_AFTER_RESTART"


_TERMINAL_JOURNAL_STATES: Final[dict[str, CanonicalTerminalDisposition]] = {
    "VERIFIED": CanonicalTerminalDisposition.VERIFIED,
    "DENIED": CanonicalTerminalDisposition.DENIED,
    "FAILED": CanonicalTerminalDisposition.FAILED,
    "STALE_OUTCOME": CanonicalTerminalDisposition.STALE,
    "UNKNOWN_AFTER_RESTART": CanonicalTerminalDisposition.UNKNOWN,
}


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CanonicalSingleAuthorityError(f"INVALID_{name.upper()}")
    if len(value) > 512 or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CanonicalSingleAuthorityError(f"INVALID_{name.upper()}")
    return value


def _sha256(name: str, value: object) -> str:
    token = _token(name, value)
    if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
        raise CanonicalSingleAuthorityError(f"INVALID_{name.upper()}")
    return token


@dataclass(frozen=True, slots=True)
class CanonicalEffectTransactionEvidence:
    """Post-return evidence from the already-admitted canonical authority adapter.

    The adapter must obtain ``final_journal_state`` from the same canonical
    EffectGate/EffectJournal transaction. The F2 call identity fields provide exact
    wrapper correlation; they do not become canonical authority by being repeated here.
    """

    authority: CanonicalEffectAuthorityIdentity
    effect_id: str
    final_journal_state: str
    outcome_sha256: str
    return_id: str | None
    binding_id: str
    invocation_id: str
    tool_use_id: str
    delegation_id: str
    child_identity_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.authority, CanonicalEffectAuthorityIdentity):
            raise CanonicalSingleAuthorityError("INVALID_AUTHORITY_IDENTITY")
        _token("effect_id", self.effect_id)
        _token("final_journal_state", self.final_journal_state)
        _sha256("outcome_sha256", self.outcome_sha256)
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


class CanonicalEffectTransactionPort(Protocol):
    """One complete canonical EffectGate-owned transaction, never authorize-only."""

    def __call__(self, intent: EffectCallIntent) -> CanonicalEffectTransactionEvidence: ...


@dataclass(frozen=True, slots=True)
class CanonicalSingleAuthorityResult:
    authority_ref: str
    effect_id: str
    final_journal_state: str
    disposition: CanonicalTerminalDisposition
    outcome_sha256: str
    authority_calls: int = 1
    second_executor_dispatch_permitted: bool = False
    automatic_replay_permitted: bool = False


def _assert_same_call(
    intent: EffectCallIntent,
    evidence: CanonicalEffectTransactionEvidence,
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
            raise CanonicalSingleAuthorityError(f"{name}_MISMATCH")


def execute_once_through_canonical_authority(
    intent: EffectCallIntent,
    *,
    expected_authority: CanonicalEffectAuthorityIdentity,
    execute_transaction: Callable[[EffectCallIntent], CanonicalEffectTransactionEvidence],
) -> CanonicalSingleAuthorityResult:
    """Invoke one complete canonical authority transaction and never dispatch again.

    ``PENDING`` is deliberately rejected after a normal return. Under the bound
    ``ENTITYOS_EFFECT_AUTHORITY_PY_API/v1`` contract, ``EffectGate.execute`` creates
    PENDING internally, performs/denies the action, then finalizes before returning.
    A normal adapter return that still claims PENDING is therefore incompatible with
    this single-call topology and fails closed.

    Any exception from the canonical transaction is surfaced as outcome-unknown. This
    wrapper cannot prove whether the exception happened before or after the real-effect
    boundary, so it never converts such failure into replay permission.
    """
    if not isinstance(intent, EffectCallIntent):
        raise CanonicalSingleAuthorityError("INVALID_EFFECT_CALL_INTENT")
    if not isinstance(expected_authority, CanonicalEffectAuthorityIdentity):
        raise CanonicalSingleAuthorityError("EXPECTED_AUTHORITY_UNRESOLVED")
    if not callable(execute_transaction):
        raise CanonicalSingleAuthorityError("CANONICAL_TRANSACTION_NOT_CALLABLE")

    try:
        evidence = execute_transaction(intent)
    except Exception as exc:
        raise CanonicalAuthorityOutcomeUnknown(
            "CANONICAL_TRANSACTION_RETURN_UNKNOWN_NO_AUTOMATIC_REPLAY"
        ) from exc

    if not isinstance(evidence, CanonicalEffectTransactionEvidence):
        raise CanonicalSingleAuthorityError("INVALID_CANONICAL_TRANSACTION_EVIDENCE")
    if evidence.authority != expected_authority:
        raise CanonicalSingleAuthorityError("AUTHORITY_IDENTITY_MISMATCH")
    _assert_same_call(intent, evidence)

    disposition = _TERMINAL_JOURNAL_STATES.get(evidence.final_journal_state)
    if disposition is None:
        if evidence.final_journal_state == "PENDING":
            raise CanonicalSingleAuthorityError(
                "PENDING_AFTER_CANONICAL_RETURN_TOPOLOGY_MISMATCH"
            )
        raise CanonicalSingleAuthorityError("UNKNOWN_CANONICAL_JOURNAL_STATE")

    return CanonicalSingleAuthorityResult(
        authority_ref=expected_authority.authority_ref(),
        effect_id=evidence.effect_id,
        final_journal_state=evidence.final_journal_state,
        disposition=disposition,
        outcome_sha256=evidence.outcome_sha256,
    )


__all__ = [
    "CanonicalAuthorityOutcomeUnknown",
    "CanonicalEffectTransactionEvidence",
    "CanonicalEffectTransactionPort",
    "CanonicalSingleAuthorityError",
    "CanonicalSingleAuthorityResult",
    "CanonicalTerminalDisposition",
    "execute_once_through_canonical_authority",
]
