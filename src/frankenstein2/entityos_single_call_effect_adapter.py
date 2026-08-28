"""Single-authority EntityOS effect transaction observer for Frankenstein 2.0 WP105.

The bound EntityOS ``EffectGate.execute()`` owns the complete canonical transaction:
validation, canonical effect-id allocation, EffectJournal PENDING admission, the actual
execution boundary, and journal finalization. Frankenstein therefore MUST NOT call a
second executor for the same EntityOS-backed logical effect.

This adapter performs exactly one runtime transaction call, then observes only the
returned canonical ``effect_id``. It binds that result to the immutable semantic
``EffectRequestIdentity`` and F2 call lineage. It does not implement policy, mint an
``effect_id``, scan for a "latest" journal row, retry UNKNOWN outcomes, or promote an
executor return directly to verified world completion.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Mapping, Protocol

from .canonical_effect_authority_bridge import (
    CanonicalEffectAuthorityIdentity,
    EffectCallIntent,
)
from .effect_request_identity import EffectRequestIdentity


class EntityOSSingleCallAdapterError(RuntimeError):
    """Fail-closed error at the F2 -> canonical EntityOS transaction boundary."""


FINAL_JOURNAL_STATUSES = frozenset(
    {"VERIFIED", "DENIED", "FAILED", "STALE_OUTCOME", "UNKNOWN_AFTER_RESTART"}
)


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EntityOSSingleCallAdapterError(f"INVALID_{name.upper()}")
    if len(value) > 4096 or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise EntityOSSingleCallAdapterError(f"INVALID_{name.upper()}")
    return value


def _sha256(name: str, value: object) -> str:
    token = _token(name, value)
    if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
        raise EntityOSSingleCallAdapterError(f"INVALID_{name.upper()}")
    return token


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EntityOSSingleCallAdapterError("OUTCOME_NOT_CANONICAL_JSON") from exc
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ExactJournalObservation:
    """Read-only observation of exactly one canonical journal row by ``effect_id``."""

    effect_id: str
    status: str
    evidence_ref: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        _token("effect_id", self.effect_id)
        _token("status", self.status)
        if self.status not in FINAL_JOURNAL_STATUSES and self.status != "PENDING":
            raise EntityOSSingleCallAdapterError("UNKNOWN_JOURNAL_STATUS")
        _token("evidence_ref", self.evidence_ref)
        _sha256("evidence_sha256", self.evidence_sha256)


class BoundEntityOSTransactionPort(Protocol):
    """Runtime port supplied by exact-source integration code.

    Implementations must construct the exact bound EntityOS ``EffectRequest`` and call
    the exact bound ``EffectGate.execute()`` once. The adapter intentionally does not
    import/copy the private canonical implementation into this repository.
    """

    @property
    def authority_identity(self) -> CanonicalEffectAuthorityIdentity: ...

    def execute_once(
        self, request: EffectRequestIdentity
    ) -> tuple[str, Mapping[str, object]]: ...

    def observe_exact(self, effect_id: str) -> ExactJournalObservation: ...


@dataclass(frozen=True, slots=True)
class EntityOSTransactionSubmission:
    """Immutable correlation record produced after the one canonical transaction call."""

    effect_id: str
    request_sha256: str
    binding_id: str
    invocation_id: str
    tool_use_id: str
    delegation_id: str
    child_identity_sha256: str
    outcome_sha256: str

    def __post_init__(self) -> None:
        _token("effect_id", self.effect_id)
        _sha256("request_sha256", self.request_sha256)
        for name in (
            "binding_id",
            "invocation_id",
            "tool_use_id",
            "delegation_id",
        ):
            _token(name, getattr(self, name))
        _sha256("child_identity_sha256", self.child_identity_sha256)
        _sha256("outcome_sha256", self.outcome_sha256)


@dataclass(frozen=True, slots=True)
class EntityOSTransactionObservation:
    submission: EntityOSTransactionSubmission
    journal: ExactJournalObservation

    def __post_init__(self) -> None:
        if self.journal.effect_id != self.submission.effect_id:
            raise EntityOSSingleCallAdapterError("JOURNAL_EFFECT_ID_MISMATCH")

    @property
    def final(self) -> bool:
        return self.journal.status in FINAL_JOURNAL_STATUSES

    @property
    def verified(self) -> bool:
        return self.journal.status == "VERIFIED"

    @property
    def replay_forbidden(self) -> bool:
        return self.journal.status in {"PENDING", "UNKNOWN_AFTER_RESTART", "VERIFIED"}


def _validate_intent(intent: EffectCallIntent) -> EffectRequestIdentity:
    if not isinstance(intent, EffectCallIntent):
        raise EntityOSSingleCallAdapterError("INVALID_EFFECT_CALL_INTENT")
    if intent.request is None:
        raise EntityOSSingleCallAdapterError("SEMANTIC_EFFECT_REQUEST_UNRESOLVED")
    return intent.request


def submit_single_call_entityos_transaction(
    intent: EffectCallIntent,
    *,
    expected_authority: CanonicalEffectAuthorityIdentity,
    port: BoundEntityOSTransactionPort,
) -> EntityOSTransactionSubmission:
    """Execute exactly one canonical EntityOS effect transaction.

    No authorization callback and no second executor callback exist in this API. If the
    canonical call raises after it may have started, this adapter does not retry and does
    not guess an ``effect_id``; recovery must re-enter through canonical journal evidence.
    """
    request = _validate_intent(intent)
    if not isinstance(expected_authority, CanonicalEffectAuthorityIdentity):
        raise EntityOSSingleCallAdapterError("EXPECTED_AUTHORITY_UNRESOLVED")
    observed_authority = getattr(port, "authority_identity", None)
    if observed_authority != expected_authority:
        raise EntityOSSingleCallAdapterError("AUTHORITY_IDENTITY_MISMATCH")
    execute_once = getattr(port, "execute_once", None)
    if not callable(execute_once):
        raise EntityOSSingleCallAdapterError("ENTITYOS_EXECUTE_ONCE_UNAVAILABLE")

    # Critical single-authority invariant: this is the sole transaction invocation.
    try:
        result = execute_once(request)
    except Exception as exc:
        raise EntityOSSingleCallAdapterError(
            "ENTITYOS_TRANSACTION_RETURN_UNKNOWN_NO_AUTOMATIC_REPLAY"
        ) from exc
    if not isinstance(result, tuple) or len(result) != 2:
        raise EntityOSSingleCallAdapterError("INVALID_ENTITYOS_TRANSACTION_RESULT")
    effect_id, outcome = result
    effect_id = _token("effect_id", effect_id)
    if not isinstance(outcome, Mapping):
        raise EntityOSSingleCallAdapterError("INVALID_ENTITYOS_TRANSACTION_OUTCOME")

    return EntityOSTransactionSubmission(
        effect_id=effect_id,
        request_sha256=request.sha256(),
        binding_id=intent.binding_id,
        invocation_id=intent.invocation_id,
        tool_use_id=intent.tool_use_id,
        delegation_id=intent.delegation_id,
        child_identity_sha256=intent.child_identity_sha256,
        outcome_sha256=_canonical_sha256(dict(outcome)),
    )


def observe_single_call_entityos_transaction(
    submission: EntityOSTransactionSubmission,
    *,
    request: EffectRequestIdentity,
    port: BoundEntityOSTransactionPort,
) -> EntityOSTransactionObservation:
    """Observe only the exact returned ``effect_id``; never infer by row order/time."""
    if not isinstance(submission, EntityOSTransactionSubmission):
        raise EntityOSSingleCallAdapterError("INVALID_TRANSACTION_SUBMISSION")
    if not isinstance(request, EffectRequestIdentity):
        raise EntityOSSingleCallAdapterError("INVALID_EFFECT_REQUEST_IDENTITY")
    if request.sha256() != submission.request_sha256:
        raise EntityOSSingleCallAdapterError("REQUEST_SHA256_MISMATCH")
    observe_exact = getattr(port, "observe_exact", None)
    if not callable(observe_exact):
        raise EntityOSSingleCallAdapterError("EXACT_JOURNAL_OBSERVER_UNAVAILABLE")
    journal = observe_exact(submission.effect_id)
    if not isinstance(journal, ExactJournalObservation):
        raise EntityOSSingleCallAdapterError("INVALID_EXACT_JOURNAL_OBSERVATION")
    if journal.effect_id != submission.effect_id:
        raise EntityOSSingleCallAdapterError("JOURNAL_EFFECT_ID_MISMATCH")
    return EntityOSTransactionObservation(submission=submission, journal=journal)


def run_and_observe_single_call_entityos_transaction(
    intent: EffectCallIntent,
    *,
    expected_authority: CanonicalEffectAuthorityIdentity,
    port: BoundEntityOSTransactionPort,
) -> EntityOSTransactionObservation:
    """Convenience path for synchronous EffectGate.execute() integrations."""
    request = _validate_intent(intent)
    submission = submit_single_call_entityos_transaction(
        intent,
        expected_authority=expected_authority,
        port=port,
    )
    return observe_single_call_entityos_transaction(
        submission,
        request=request,
        port=port,
    )


__all__ = [
    "BoundEntityOSTransactionPort",
    "EntityOSSingleCallAdapterError",
    "EntityOSTransactionObservation",
    "EntityOSTransactionSubmission",
    "ExactJournalObservation",
    "FINAL_JOURNAL_STATUSES",
    "observe_single_call_entityos_transaction",
    "run_and_observe_single_call_entityos_transaction",
    "submit_single_call_entityos_transaction",
]
