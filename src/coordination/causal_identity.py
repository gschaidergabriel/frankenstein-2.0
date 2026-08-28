#!/usr/bin/env python3
"""Deterministic causal identity primitives for Frankenstein 2.0.

F2-WP-101 generation 1.

This module separates replay-stable real/event identity from concrete handling identity:

    lineage context
      -> causal event (replay-stable)
      -> admission (concrete observation/handling attempt)
      -> invocation (concrete execution attempt)
      -> effect (concrete requested external effect)

It does not write UnifiedDB, execute effects, infer missing parents, or create canonical
facts.  Callers must supply explicit semantic keys/nonces.  Reusing a nonce is therefore
idempotent; changing a nonce creates a distinct concrete attempt while retaining the same
causal event identity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Mapping, Optional


SCHEMA = "FRANKENSTEIN2_CAUSAL_IDENTITY/v1"
DOMAIN = "frankenstein-2.0/causal-identity/v1"
MAX_ID_LEN = 256
KINDS = ("LINEAGE", "CAUSAL_EVENT", "ADMISSION", "INVOCATION", "EFFECT")


class CausalIdentityError(ValueError):
    """Raised when causal identity input is ambiguous or violates lineage invariants."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CausalIdentityError(f"{label}_REQUIRED")
    if len(value) > MAX_ID_LEN:
        raise CausalIdentityError(f"{label}_TOO_LONG")
    return value


def _optional_text(value: object, label: str) -> Optional[str]:
    if value is None:
        return None
    return _text(value, label)


def _generation(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CausalIdentityError("GENERATION_MUST_BE_NONNEGATIVE_INTEGER")
    return value


def _canon(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _digest(label: str, payload: Mapping[str, object]) -> str:
    raw = {
        "domain": DOMAIN,
        "label": label,
        "payload": dict(payload),
    }
    return hashlib.sha256(_canon(raw)).hexdigest()


def _derived_id(kind: str, payload: Mapping[str, object]) -> str:
    if kind not in KINDS:
        raise CausalIdentityError(f"UNKNOWN_IDENTITY_KIND:{kind}")
    prefix = {
        "LINEAGE": "lin",
        "CAUSAL_EVENT": "cev",
        "ADMISSION": "adm",
        "INVOCATION": "inv",
        "EFFECT": "eff",
    }[kind]
    return f"{prefix}_{_digest(kind, payload)}"


@dataclass(frozen=True)
class LineageContext:
    """Stable context shared by event/attempt identities within one generation."""

    session_id: str
    agent_id: str
    task_id: Optional[str]
    turn_id: Optional[str]
    generation: int
    lineage_id: str
    schema: str = SCHEMA

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        agent_id: str,
        task_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        generation: int = 0,
    ) -> "LineageContext":
        session = _text(session_id, "SESSION_ID")
        agent = _text(agent_id, "AGENT_ID")
        task = _optional_text(task_id, "TASK_ID")
        turn = _optional_text(turn_id, "TURN_ID")
        gen = _generation(generation)
        if turn is not None and task is None:
            raise CausalIdentityError("TURN_ID_REQUIRES_TASK_ID")
        payload = {
            "session_id": session,
            "agent_id": agent,
            "task_id": task,
            "turn_id": turn,
            "generation": gen,
        }
        return cls(
            session_id=session,
            agent_id=agent,
            task_id=task,
            turn_id=turn,
            generation=gen,
            lineage_id=_derived_id("LINEAGE", payload),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CausalEvent:
    """Replay-stable identity for one semantic causal event."""

    context: LineageContext
    causal_event_id: str
    event_key_digest: str
    schema: str = SCHEMA
    kind: str = "CAUSAL_EVENT"

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["context"] = self.context.to_dict()
        return data


@dataclass(frozen=True)
class Admission:
    """Concrete admission/observation of a replay-stable causal event."""

    event: CausalEvent
    admission_id: str
    admission_nonce_digest: str
    schema: str = SCHEMA
    kind: str = "ADMISSION"

    @property
    def causal_event_id(self) -> str:
        return self.event.causal_event_id


@dataclass(frozen=True)
class Invocation:
    """Concrete execution attempt bound to exactly one admission."""

    admission: Admission
    invocation_id: str
    invocation_key_digest: str
    tool_use_id: Optional[str] = None
    schema: str = SCHEMA
    kind: str = "INVOCATION"

    @property
    def causal_event_id(self) -> str:
        return self.admission.causal_event_id


@dataclass(frozen=True)
class Effect:
    """Concrete effect-request identity. This is not completion evidence."""

    invocation: Invocation
    effect_id: str
    effect_key_digest: str
    schema: str = SCHEMA
    kind: str = "EFFECT"

    @property
    def causal_event_id(self) -> str:
        return self.invocation.causal_event_id


def causal_event(context: LineageContext, *, event_key: str) -> CausalEvent:
    if not isinstance(context, LineageContext):
        raise CausalIdentityError("CAUSAL_EVENT_REQUIRES_LINEAGE_CONTEXT")
    key = _text(event_key, "EVENT_KEY")
    key_digest = _digest("EVENT_KEY", {"value": key})
    payload = {
        "lineage_id": context.lineage_id,
        "generation": context.generation,
        "event_key_digest": key_digest,
    }
    return CausalEvent(
        context=context,
        causal_event_id=_derived_id("CAUSAL_EVENT", payload),
        event_key_digest=key_digest,
    )


def admit(event: CausalEvent, *, admission_nonce: str) -> Admission:
    if not isinstance(event, CausalEvent):
        raise CausalIdentityError("ADMISSION_REQUIRES_CAUSAL_EVENT")
    nonce = _text(admission_nonce, "ADMISSION_NONCE")
    nonce_digest = _digest("ADMISSION_NONCE", {"value": nonce})
    payload = {
        "causal_event_id": event.causal_event_id,
        "generation": event.context.generation,
        "admission_nonce_digest": nonce_digest,
    }
    return Admission(
        event=event,
        admission_id=_derived_id("ADMISSION", payload),
        admission_nonce_digest=nonce_digest,
    )


def invoke(
    admission: Admission,
    *,
    invocation_key: str,
    tool_use_id: Optional[str] = None,
) -> Invocation:
    if not isinstance(admission, Admission):
        raise CausalIdentityError("INVOCATION_REQUIRES_ADMISSION")
    key = _text(invocation_key, "INVOCATION_KEY")
    tool = _optional_text(tool_use_id, "TOOL_USE_ID")
    key_digest = _digest("INVOCATION_KEY", {"value": key})
    payload = {
        "admission_id": admission.admission_id,
        "causal_event_id": admission.causal_event_id,
        "generation": admission.event.context.generation,
        "invocation_key_digest": key_digest,
        "tool_use_id": tool,
    }
    return Invocation(
        admission=admission,
        invocation_id=_derived_id("INVOCATION", payload),
        invocation_key_digest=key_digest,
        tool_use_id=tool,
    )


def effect(invocation: Invocation, *, effect_key: str) -> Effect:
    if not isinstance(invocation, Invocation):
        raise CausalIdentityError("EFFECT_REQUIRES_INVOCATION")
    key = _text(effect_key, "EFFECT_KEY")
    key_digest = _digest("EFFECT_KEY", {"value": key})
    payload = {
        "invocation_id": invocation.invocation_id,
        "causal_event_id": invocation.causal_event_id,
        "generation": invocation.admission.event.context.generation,
        "effect_key_digest": key_digest,
    }
    return Effect(
        invocation=invocation,
        effect_id=_derived_id("EFFECT", payload),
        effect_key_digest=key_digest,
    )


def telemetry_identity(
    node: CausalEvent | Admission | Invocation | Effect,
) -> dict[str, object]:
    """Project a typed identity node into the existing telemetry identity envelope.

    `causal_id` is always the replay-stable causal event id. Concrete admission and
    invocation ids are returned separately and are never substituted for `causal_id`.
    """
    if isinstance(node, CausalEvent):
        event = node
        admission_id = None
        invocation_id = None
        tool_use_id = None
        effect_id = None
    elif isinstance(node, Admission):
        event = node.event
        admission_id = node.admission_id
        invocation_id = None
        tool_use_id = None
        effect_id = None
    elif isinstance(node, Invocation):
        event = node.admission.event
        admission_id = node.admission.admission_id
        invocation_id = node.invocation_id
        tool_use_id = node.tool_use_id
        effect_id = None
    elif isinstance(node, Effect):
        event = node.invocation.admission.event
        admission_id = node.invocation.admission.admission_id
        invocation_id = node.invocation.invocation_id
        tool_use_id = node.invocation.tool_use_id
        effect_id = node.effect_id
    else:
        raise CausalIdentityError("UNSUPPORTED_IDENTITY_NODE")

    context = event.context
    return {
        "session_id": context.session_id,
        "agent_id": context.agent_id,
        "task_id": context.task_id,
        "turn_id": context.turn_id,
        "causal_id": event.causal_event_id,
        "causal_event_id": event.causal_event_id,
        "admission_id": admission_id,
        "invocation_id": invocation_id,
        "tool_use_id": tool_use_id,
        "effect_id": effect_id,
        "generation": context.generation,
        "lineage_id": context.lineage_id,
    }


def assert_same_causal_event(*nodes: CausalEvent | Admission | Invocation | Effect) -> str:
    """Fail closed unless all supplied nodes descend from one causal event."""
    if not nodes:
        raise CausalIdentityError("NO_IDENTITY_NODES")
    ids = {telemetry_identity(node)["causal_event_id"] for node in nodes}
    if len(ids) != 1:
        raise CausalIdentityError("CAUSAL_EVENT_MISMATCH")
    return next(iter(ids))


__all__ = [
    "Admission",
    "CausalEvent",
    "CausalIdentityError",
    "Effect",
    "Invocation",
    "LineageContext",
    "SCHEMA",
    "admit",
    "assert_same_causal_event",
    "causal_event",
    "effect",
    "invoke",
    "telemetry_identity",
]
