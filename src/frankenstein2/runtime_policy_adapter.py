"""RuntimePolicyAdapter for CORTEX-P1 (F2-WP-1207 self-integration, real-retina-bridge round).

Read-only translation layer: `unified.db` tables `perception_head_policy` /
`perception_head_status` (Codebase A schema, produced by the older
`~/.claude/star/perception_control.py` head registry) -> a canonical F2
`frankenstein2.perception_control.PerceptionPolicyRegistry` snapshot.

This module intentionally contains NO enforcement logic of its own. It reads
configuration rows and constructs plain F2 dataclasses; every actual OFF/taint/
tier decision is made by the canonical `evaluate_perception_head()` function in
`frankenstein2.perception_control`. That keeps exactly one enforcement authority
in the codebase (see CORTEX_INVENTORY.md's canonicalization-candidate #1 --
`perception_control.py` existed twice, structurally different; this adapter is
how the older DB-backed config feeds the single remaining canonical evaluator
instead of re-implementing a second evaluator against it).

Never imports anything from `~/.claude/star/` -- only reads its SQLite database,
read-only (`mode=ro` URI connection, so a write attempt fails at the OS/sqlite
level, not just by convention).
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any, Callable

from .perception_control import (
    PerceptionControlResult,
    PerceptionDependency,
    PerceptionHeadPolicy,
    PerceptionPolicyRegistry,
    evaluate_perception_head,
)

# Coordinator fix, 2026-09-05: the original default pointed at
# ~/.claude/star/unified.db -- a stale legacy copy (perception_head_status
# had 7 rows there vs. 10 in the real production file at the time this was
# caught), not the actual, currently-written database. This is the same
# "two unified.db" trap documented elsewhere in this project's history
# (~/.claude/star/stern.py's _db_pfad_aufloesen() resolves the real,
# current path via a pointer file / XDG data dir, not this hardcoded
# constant) -- callers who need the authoritative path should prefer that
# resolution chain over this default where possible. Fixed here to at
# least point at the real file, not the legacy one.
DEFAULT_UNIFIED_DB_PATH = os.path.expanduser("~/.local/share/agentzero/unified.db")

_VALID_TIERS = frozenset({"ON", "COMPUTE_OFF", "OUTPUT_OFF", "MEMORY_OFF"})


class RuntimePolicyAdapterError(ValueError):
    """Fail-closed error for the unified.db -> PerceptionPolicyRegistry translation."""


def _read_head_policy_row(db_path: str, head_id: str) -> dict[str, Any]:
    """Read-only single-row fetch. URI mode=ro means sqlite3 itself refuses writes."""
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError as exc:
        raise RuntimePolicyAdapterError(f"cannot open unified.db read-only at {db_path}: {exc}") from exc
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT head_id, enabled, tier, memory_allowed, updated_at, updated_by, provenance "
            "FROM perception_head_policy WHERE head_id = ?",
            (head_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise RuntimePolicyAdapterError(f"no perception_head_policy row for head_id={head_id!r}")
    return dict(row)


def _read_head_status_row(db_path: str, head_id: str) -> dict[str, Any] | None:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT head_id, last_run_at, last_latency_ms, confidence, status, reason, provenance "
            "FROM perception_head_status WHERE head_id = ?",
            (head_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    return dict(row) if row is not None else None


class RuntimePolicyAdapter:
    """Snapshot builder: unified.db config row -> one-head PerceptionPolicyRegistry.

    Deliberately narrow: one adapter instance is bound to exactly one head_id and one
    db_path, mirroring the P1 scope (single real-retina head, no head-dependency graph
    beyond the trivial single-node case). A later round can widen this to multiple heads
    without changing the read-only DB contract or the canonical evaluator call below.
    """

    def __init__(self, *, db_path: str = DEFAULT_UNIFIED_DB_PATH, head_id: str) -> None:
        if not os.path.isfile(db_path):
            raise RuntimePolicyAdapterError(f"unified.db not found at {db_path}")
        self._db_path = db_path
        self._head_id = head_id

    @property
    def db_path(self) -> str:
        return self._db_path

    @property
    def head_id(self) -> str:
        return self._head_id

    def read_raw_policy_row(self) -> dict[str, Any]:
        """Exposed for provenance/reporting -- the exact row this snapshot was built from."""
        return _read_head_policy_row(self._db_path, self._head_id)

    def read_raw_status_row(self) -> dict[str, Any] | None:
        return _read_head_status_row(self._db_path, self._head_id)

    def build_registry(self, *, registry_generation: int = 1,
                        provenance_refs: tuple[str, ...] | None = None) -> PerceptionPolicyRegistry:
        """Construct a fresh canonical PerceptionPolicyRegistry from the current DB row.

        `generation` on PerceptionHeadPolicy is synthesized as 1 -- the Codebase A
        `perception_head_policy` table (schema read directly, see module docstring) has
        no generation column; F2's dataclass requires one. This is an honest
        translation gap, not a hidden default: callers needing real cross-write
        generational tracking must add it to the DB schema in a later round, not here.
        """
        row = _read_head_policy_row(self._db_path, self._head_id)
        tier = row["tier"]
        if tier not in _VALID_TIERS:
            raise RuntimePolicyAdapterError(f"unified.db tier {tier!r} is not a valid F2 tier")
        refs = provenance_refs or (
            f"unified_db:perception_head_policy:{self._head_id}:updated_by={row['updated_by']}",
        )
        policy = PerceptionHeadPolicy(
            head_id=self._head_id,
            generation=1,
            tier=tier,
            enabled=bool(row["enabled"]),
            memory_allowed=bool(row["memory_allowed"]),
            provenance_refs=refs,
        )
        dependency = PerceptionDependency(head_id=self._head_id, depends_on=())
        return PerceptionPolicyRegistry(
            registry_id=f"cortex-p1-runtime-policy:{self._head_id}",
            generation=registry_generation,
            heads=(policy,),
            dependencies=(dependency,),
            provenance_refs=refs,
        )

    def evaluate(self, *, evaluation_id: str, compute_fn: Callable[[], tuple[Any, int]],
                 provenance_refs: tuple[str, ...] | None = None) -> PerceptionControlResult:
        """Build the current registry snapshot and delegate to the canonical F2 evaluator.

        No enforcement decision is made in this method -- it only assembles inputs
        (registry + its own digest) and calls `evaluate_perception_head()`, exactly once.
        """
        registry = self.build_registry()
        refs = provenance_refs or (f"unified_db:{self._db_path}:{self._head_id}",)
        return evaluate_perception_head(
            evaluation_id=evaluation_id,
            registry=registry,
            expected_registry_sha256=registry.sha256(),
            head_id=self._head_id,
            compute_fn=compute_fn,
            provenance_refs=refs,
        )


__all__ = [
    "DEFAULT_UNIFIED_DB_PATH",
    "RuntimePolicyAdapter",
    "RuntimePolicyAdapterError",
]
