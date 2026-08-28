"""Call-identity handshake inside the bound canonical EntityOS EffectGate callback.

The current canonical EffectGate is monolithic: it creates an EffectJournal ``PENDING``
row and then calls its EntityOS bridge.  Frankenstein 2.0 therefore cannot safely mint
or guess the effect id before the canonical gate.  This module provides a deterministic
handshake for use *inside that bridge callback*: F2 encodes the exact result-free call
identity and request context into the EffectRequest target, then resolves the unique
canonical PENDING row whose redacted target/argv receipts match that exact request.

A PENDING row alone is not policy authority.  Production callers must reach this code
through the exact source-bound canonical EffectGate; direct ``EffectJournal.begin`` is
not an authorization path.  The returned ExternalGateEvidence is correlation evidence
for the already-crossed canonical gate boundary, not a second policy decision.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

from .canonical_effect_authority_bridge import EffectCallIntent
from .effect_executor_interlock import ExternalGateDecision, ExternalGateEvidence
from .effect_invocation_correlation import EffectCallBinding, EffectCorrelationStage
from .entityos_effect_authority_binding import (
    CURRENT_ENTITYOS_EFFECT_AUTHORITY_BINDING,
    EntityOSEffectAuthoritySourceBinding,
)


class EntityOSEffectGateCallBridgeError(RuntimeError):
    pass


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EntityOSEffectGateCallBridgeError(f"INVALID_{name.upper()}")
    if len(value) > 2048 or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise EntityOSEffectGateCallBridgeError(f"INVALID_{name.upper()}")
    return value


def _generation(value: object) -> int:
    if type(value) is not int or value < 0:
        raise EntityOSEffectGateCallBridgeError("INVALID_GENERATION")
    return value


@dataclass(frozen=True, slots=True)
class EntityOSEffectCallContext:
    user_id: str
    session_id: str
    generation: int
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        _token("user_id", self.user_id)
        _token("session_id", self.session_id)
        _generation(self.generation)
        if not isinstance(self.argv, tuple) or not self.argv:
            raise EntityOSEffectGateCallBridgeError("INVALID_ARGV")
        for index, arg in enumerate(self.argv):
            _token(f"argv_{index}", arg)
            if "\x00" in arg:
                raise EntityOSEffectGateCallBridgeError("INVALID_ARGV_NUL")


def _argv_digest(argv: Sequence[str]) -> str:
    raw = json.dumps(list(argv), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def canonical_entityos_call_target(
    intent: EffectCallIntent,
    context: EntityOSEffectCallContext,
) -> str:
    """Canonical, replay-stable request descriptor that the journal redacts by hash."""
    if not isinstance(intent, EffectCallIntent):
        raise EntityOSEffectGateCallBridgeError("INVALID_EFFECT_CALL_INTENT")
    if not isinstance(context, EntityOSEffectCallContext):
        raise EntityOSEffectGateCallBridgeError("INVALID_EFFECT_CALL_CONTEXT")
    payload = {
        "schema": "FRANKENSTEIN2_ENTITYOS_EFFECT_CALL_TARGET/v1",
        "return_id": intent.return_id,
        "binding_id": intent.binding_id,
        "invocation_id": intent.invocation_id,
        "tool_use_id": intent.tool_use_id,
        "delegation_id": intent.delegation_id,
        "child_identity_sha256": intent.child_identity_sha256,
        "user_id": context.user_id,
        "session_id": context.session_id,
        "generation": context.generation,
        "argv_sha256": _argv_digest(context.argv),
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _expected_target_receipt(target: str) -> dict[str, object]:
    raw = target.encode("utf-8")
    return {
        "audit": "redacted-target-v1",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _expected_argv_receipt(argv: Sequence[str]) -> dict[str, object]:
    raw = json.dumps(list(argv), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {
        "audit": "redacted-argv-v1",
        "argc": len(argv),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _decode_receipt(value: object, name: str) -> Mapping[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise EntityOSEffectGateCallBridgeError(f"INVALID_{name.upper()}_JSON") from exc
    if not isinstance(value, Mapping):
        raise EntityOSEffectGateCallBridgeError(f"INVALID_{name.upper()}_RECEIPT")
    return value


@dataclass(frozen=True, slots=True)
class PendingEntityOSEffectBinding:
    effect_id: str
    prepared: EffectCallBinding
    gate: ExternalGateEvidence


def bind_unique_pending_entityos_effect(
    intent: EffectCallIntent,
    context: EntityOSEffectCallContext,
    rows: Iterable[Mapping[str, Any]],
    *,
    binding: EntityOSEffectAuthoritySourceBinding = CURRENT_ENTITYOS_EFFECT_AUTHORITY_BINDING,
) -> PendingEntityOSEffectBinding:
    """Resolve one exact PENDING row while already inside the canonical gate callback."""
    if not isinstance(intent, EffectCallIntent):
        raise EntityOSEffectGateCallBridgeError("INVALID_EFFECT_CALL_INTENT")
    if not isinstance(context, EntityOSEffectCallContext):
        raise EntityOSEffectGateCallBridgeError("INVALID_EFFECT_CALL_CONTEXT")
    if not isinstance(binding, EntityOSEffectAuthoritySourceBinding):
        raise EntityOSEffectGateCallBridgeError("INVALID_AUTHORITY_BINDING")

    target = canonical_entityos_call_target(intent, context)
    expected_target = _expected_target_receipt(target)
    expected_argv = _expected_argv_receipt(context.argv)
    matches: list[Mapping[str, Any]] = []

    for row in rows:
        if not isinstance(row, Mapping):
            raise EntityOSEffectGateCallBridgeError("INVALID_EFFECT_ROW")
        if row.get("status") != "PENDING":
            continue
        if row.get("capability") != "entityos.exec":
            continue
        if row.get("user_id") != context.user_id:
            continue
        if int(row.get("requested_generation", -1)) != context.generation:
            continue
        try:
            target_receipt = _decode_receipt(row.get("target"), "target")
            argv_receipt = _decode_receipt(row.get("argv"), "argv")
        except EntityOSEffectGateCallBridgeError:
            continue
        if dict(target_receipt) != expected_target:
            continue
        if dict(argv_receipt) != expected_argv:
            continue
        matches.append(row)

    if not matches:
        raise EntityOSEffectGateCallBridgeError("NO_EXACT_PENDING_EFFECT")
    if len(matches) != 1:
        raise EntityOSEffectGateCallBridgeError("AMBIGUOUS_EXACT_PENDING_EFFECT")

    effect_id = _token("effect_id", matches[0].get("effect_id"))
    prepared = EffectCallBinding(
        effect_id=effect_id,
        return_id=intent.return_id,
        binding_id=intent.binding_id,
        invocation_id=intent.invocation_id,
        tool_use_id=intent.tool_use_id,
        delegation_id=intent.delegation_id,
        child_identity_sha256=intent.child_identity_sha256,
        stage=EffectCorrelationStage.PREPARED,
    )
    gate = ExternalGateEvidence(
        authority_ref=binding.authority_ref(),
        decision_id=f"canonical-effectgate-pending:{effect_id}",
        decision=ExternalGateDecision.ALLOW,
        effect_id=effect_id,
        binding_id=intent.binding_id,
        invocation_id=intent.invocation_id,
        tool_use_id=intent.tool_use_id,
        delegation_id=intent.delegation_id,
        child_identity_sha256=intent.child_identity_sha256,
    )
    return PendingEntityOSEffectBinding(
        effect_id=effect_id,
        prepared=prepared,
        gate=gate,
    )


__all__ = [
    "EntityOSEffectCallContext",
    "EntityOSEffectGateCallBridgeError",
    "PendingEntityOSEffectBinding",
    "bind_unique_pending_entityos_effect",
    "canonical_entityos_call_target",
]
