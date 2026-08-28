"""Canonical-call/effect bijection guard for Frankenstein 2.0 Stage 1.

This module does not create a database path and does not execute effects. It operates
only on a caller-supplied SQLite connection that is expected to be the already-resolved
canonical UnifiedDB connection. The guard closes one narrow coordination invariant:
one immutable call identity maps to one canonical effect identity, and one canonical
effect identity maps back to one immutable call identity.

The low-level binder is transaction-neutral so deterministic assembly/migration code can
compose it. The PRE-dispatch durable binder is intentionally stricter: it requires the
bijection table to have been explicitly initialized already, rejects a pre-existing
transaction, persists the mapping before any executor can be called, and never creates
schema inside the dispatch path.

It is source/component logic only until repository-bound runtime evidence proves the
integration against the exact canonical UnifiedDB/effect path.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any


SCHEMA = "FRANKENSTEIN2_EFFECT_INVOCATION_BIJECTION/v1"
TABLE = "effect_invocation_bijection"


class EffectInvocationBijectionError(RuntimeError):
    """Raised when call/effect identity is incomplete, contradictory, or rebound."""


def _connection(conn: Any) -> sqlite3.Connection:
    if not isinstance(conn, sqlite3.Connection):
        raise EffectInvocationBijectionError("INVALID_SQLITE_CONNECTION")
    return conn


def _token(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EffectInvocationBijectionError(f"INVALID_{name.upper()}")
    if len(value) > 512:
        raise EffectInvocationBijectionError(f"INVALID_{name.upper()}")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise EffectInvocationBijectionError(f"INVALID_{name.upper()}")
    return value


def _generation(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EffectInvocationBijectionError("INVALID_GENERATION")
    return value


@dataclass(frozen=True, slots=True)
class EffectInvocationBijection:
    call_id: str
    effect_id: str
    binding_id: str
    generation: int

    def __post_init__(self) -> None:
        _token("call_id", self.call_id)
        _token("effect_id", self.effect_id)
        _token("binding_id", self.binding_id)
        _generation(self.generation)


def initialize_effect_invocation_bijection(conn: sqlite3.Connection) -> None:
    """Install the narrow bijection table into an already-selected canonical DB.

    Assembly/migration code must call this explicitly; dispatch code does not.
    """
    conn = _connection(conn)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            call_id TEXT PRIMARY KEY,
            effect_id TEXT NOT NULL UNIQUE,
            binding_id TEXT NOT NULL UNIQUE,
            generation INTEGER NOT NULL CHECK(generation >= 0)
        ) WITHOUT ROWID
        """
    )


def require_effect_invocation_bijection_ready(conn: sqlite3.Connection) -> None:
    """Fail closed unless the explicit schema is present at a clean transaction boundary."""
    conn = _connection(conn)
    if conn.in_transaction:
        raise EffectInvocationBijectionError("PREEXISTING_TRANSACTION_FORBIDDEN")
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (TABLE,),
    ).fetchone()
    if row is None or not isinstance(row[0], str):
        raise EffectInvocationBijectionError("BIJECTION_SCHEMA_NOT_INITIALIZED")
    normalized = " ".join(row[0].lower().split())
    required_fragments = (
        "call_id text primary key",
        "effect_id text not null unique",
        "binding_id text not null unique",
        "generation integer not null check(generation >= 0)",
        "without rowid",
    )
    if any(fragment not in normalized for fragment in required_fragments):
        raise EffectInvocationBijectionError("BIJECTION_SCHEMA_MISMATCH")


def _row_for_call(conn: sqlite3.Connection, call_id: str) -> tuple[str, str, str, int] | None:
    row = conn.execute(
        f"SELECT call_id,effect_id,binding_id,generation FROM {TABLE} WHERE call_id=?",
        (call_id,),
    ).fetchone()
    return None if row is None else (str(row[0]), str(row[1]), str(row[2]), int(row[3]))


def _row_for_effect(conn: sqlite3.Connection, effect_id: str) -> tuple[str, str, str, int] | None:
    row = conn.execute(
        f"SELECT call_id,effect_id,binding_id,generation FROM {TABLE} WHERE effect_id=?",
        (effect_id,),
    ).fetchone()
    return None if row is None else (str(row[0]), str(row[1]), str(row[2]), int(row[3]))


def _row_for_binding(conn: sqlite3.Connection, binding_id: str) -> tuple[str, str, str, int] | None:
    row = conn.execute(
        f"SELECT call_id,effect_id,binding_id,generation FROM {TABLE} WHERE binding_id=?",
        (binding_id,),
    ).fetchone()
    return None if row is None else (str(row[0]), str(row[1]), str(row[2]), int(row[3]))


def _as_binding(row: tuple[str, str, str, int]) -> EffectInvocationBijection:
    return EffectInvocationBijection(
        call_id=row[0], effect_id=row[1], binding_id=row[2], generation=row[3]
    )


def bind_effect_invocation(
    conn: sqlite3.Connection,
    *,
    call_id: str,
    effect_id: str,
    binding_id: str,
    generation: int,
) -> EffectInvocationBijection:
    """Atomically admit one immutable call <-> canonical effect pair without commit."""
    conn = _connection(conn)
    call_id = _token("call_id", call_id)
    effect_id = _token("effect_id", effect_id)
    binding_id = _token("binding_id", binding_id)
    generation = _generation(generation)
    candidate = EffectInvocationBijection(call_id, effect_id, binding_id, generation)

    try:
        conn.execute(
            f"INSERT INTO {TABLE}(call_id,effect_id,binding_id,generation) VALUES(?,?,?,?)",
            (call_id, effect_id, binding_id, generation),
        )
        return candidate
    except sqlite3.IntegrityError:
        call_row = _row_for_call(conn, call_id)
        effect_row = _row_for_effect(conn, effect_id)
        binding_row = _row_for_binding(conn, binding_id)
        exact = (call_id, effect_id, binding_id, generation)
        if call_row == exact and effect_row == exact and binding_row == exact:
            return candidate
        if call_row is not None and call_row[1] != effect_id:
            raise EffectInvocationBijectionError("CALL_ID_REBOUND_TO_DIFFERENT_EFFECT")
        if effect_row is not None and effect_row[0] != call_id:
            raise EffectInvocationBijectionError("EFFECT_ID_REBOUND_TO_DIFFERENT_CALL")
        if binding_row is not None and binding_row[:2] != (call_id, effect_id):
            raise EffectInvocationBijectionError("BINDING_ID_REBOUND_TO_DIFFERENT_PAIR")
        raise EffectInvocationBijectionError("EXISTING_BINDING_METADATA_MISMATCH")


def verify_effect_invocation(
    conn: sqlite3.Connection,
    *,
    call_id: str,
    effect_id: str,
    binding_id: str,
    generation: int,
) -> EffectInvocationBijection:
    """Verify both directions of an already-admitted mapping without mutation."""
    conn = _connection(conn)
    call_id = _token("call_id", call_id)
    effect_id = _token("effect_id", effect_id)
    binding_id = _token("binding_id", binding_id)
    generation = _generation(generation)
    exact = (call_id, effect_id, binding_id, generation)
    call_row = _row_for_call(conn, call_id)
    effect_row = _row_for_effect(conn, effect_id)
    binding_row = _row_for_binding(conn, binding_id)
    if call_row != exact or effect_row != exact or binding_row != exact:
        raise EffectInvocationBijectionError("EFFECT_INVOCATION_BIJECTION_MISMATCH")
    return _as_binding(exact)


def bind_prepared_effect_call(
    conn: sqlite3.Connection,
    prepared: Any,
    *,
    generation: int,
) -> EffectInvocationBijection:
    """Admit a result-free PREPARED EffectCallBinding by immutable identity."""
    stage = getattr(prepared, "stage", None)
    stage_value = getattr(stage, "value", stage)
    if stage_value != "PREPARED":
        raise EffectInvocationBijectionError("CALL_BINDING_NOT_PREPARED")
    if getattr(prepared, "result_id", None) is not None or getattr(
        prepared, "result_sha256", None
    ) is not None:
        raise EffectInvocationBijectionError("PREPARED_CALL_ALREADY_HAS_RESULT")
    return bind_effect_invocation(
        conn,
        call_id=getattr(prepared, "invocation_id", None),
        effect_id=getattr(prepared, "effect_id", None),
        binding_id=getattr(prepared, "binding_id", None),
        generation=generation,
    )


def durably_bind_prepared_effect_call(
    conn: sqlite3.Connection,
    prepared: Any,
    *,
    generation: int,
) -> EffectInvocationBijection:
    """Persist one PRE-dispatch bijection before an executor can observe the call."""
    conn = _connection(conn)
    require_effect_invocation_bijection_ready(conn)
    try:
        bound = bind_prepared_effect_call(conn, prepared, generation=generation)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if conn.in_transaction:
        raise EffectInvocationBijectionError("BIJECTION_COMMIT_DID_NOT_CLOSE_TRANSACTION")
    return bound


__all__ = [
    "SCHEMA",
    "TABLE",
    "EffectInvocationBijection",
    "EffectInvocationBijectionError",
    "bind_effect_invocation",
    "bind_prepared_effect_call",
    "durably_bind_prepared_effect_call",
    "initialize_effect_invocation_bijection",
    "require_effect_invocation_bijection_ready",
    "verify_effect_invocation",
]
