"""Sandbox sqlite persistence layer for the F2-WP-1207 identity schema, with
the cross-instance invariant enforced BY THE DATABASE.

F2-WP-1207, continuation of branch
`self-integration/wp1207-persistence-rebind-reentry-20260903` (Gold Test,
64/64 green). That round left two gaps explicitly open:

  GAP 1 -- the sandbox schema was never held against the real production
  `unified.db` schema. Gap 1 is closed by the ADDITIVE migration document
  `workpackages/evidence_inbox/F2-WP-1207/self_integration/
  UNIFIED_DB_SCHEMA_ABGLEICH_20260903/SCHEMA_ABGLEICH_20260903.md`
  (document + proposed CREATE statements only -- NOT applied; the real
  database was opened read-only exactly once, via `sqlite3 -readonly`,
  to dump its schema for that comparison).

  GAP 2 -- "at most one ACTIVE HostBinding per installation_id" existed only
  as Python-caller discipline. `entity_identity.py` itself says so verbatim
  (module docstring, BINDING_STATUS_ACTIVE comment block): "Not enforced
  across instances here (this module has no registry/store) ... Cross-instance
  invariants belong to whatever eventually persists these rows." THIS module
  is that persistence layer, and it closes Gap 2 by making the invariant an
  engine-level constraint instead of caller discipline:

      CREATE UNIQUE INDEX ux_host_binding_one_active_per_installation
          ON host_binding (installation_id)
          WHERE status = 'ACTIVE';

  SQLite partial indexes (3.8.0+) make this a real UNIQUE constraint over
  the ACTIVE rows only, so SUPERSEDED/REVOKED history stays unbounded while
  the "one active binding per installation" law is enforced by sqlite itself
  -- on INSERT, on UPDATE, on a raw hand-written statement, on a second
  connection, from any process that opens the file. No Python wrapper is
  load-bearing for it, and none is claimed to be: the tests in
  `tests/test_entity_identity_store.py` prove the rejection happens with the
  wrappers completely bypassed, which is the difference between "atomar
  erzwungen" and "Python-Caller-Disziplin".

SAFETY (unchanged from Schritt 3/4/5): every database this module touches in
its own tests is a `tempfile`-scoped sandbox sqlite file. It NEVER touches
`~/.local/share/agentzero/unified.db` (the real UnifiedDB) and NEVER touches
`~/frankenstein-repo` (the live checkout that resolves CLAUDE_PLUGIN_ROOT).
Nothing in this module is wired into `stern.py`, `witness_v3.py`, or any live
write path -- same SHADOW/additive discipline as the rest of WP-1207.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from frankenstein2.entity_identity import (
    BINDING_STATUS_ACTIVE,
    BINDING_STATUS_REVOKED,
    BINDING_STATUS_SUPERSEDED,
    EntityIdentityGenesisRecord,
    HostBinding,
    InstallationIdentity,
    RuntimeEpoch,
    StateRootIdentity,
)

# The one cross-instance invariant, as an engine-level partial UNIQUE index.
# Enforced by sqlite on every INSERT and every UPDATE that would leave more
# than one ACTIVE row per installation_id -- independent of any Python code.
HOST_BINDING_ONE_ACTIVE_PER_INSTALLATION_INDEX_NAME = (
    "ux_host_binding_one_active_per_installation"
)

HOST_BINDING_ONE_ACTIVE_PER_INSTALLATION_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS "
    f"{HOST_BINDING_ONE_ACTIVE_PER_INSTALLATION_INDEX_NAME} "
    "ON host_binding (installation_id) "
    f"WHERE status = '{BINDING_STATUS_ACTIVE}'"
)

# Supporting (non-unique) indexes -- lookups the wrappers and the Gold-Test
# SELECT pattern use, plus a deliberate non-unique index over
# (installation_id, status) so status history queries do not scan.
SUPPORTING_INDEX_SQL = (
    (
        "CREATE INDEX IF NOT EXISTS ix_host_binding_installation_status "
        "ON host_binding (installation_id, status)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_runtime_epoch_state_root "
        "ON runtime_epoch (state_root_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_runtime_epoch_predecessor "
        "ON runtime_epoch (predecessor_epoch_id)"
    ),
)

# Full sandbox schema, modeled on the dataclass fields of
# `frankenstein2.entity_identity` (this IS the tested sandbox layout from
# Schritt 3/5, plus two hardening additions that cost nothing and are the
# point of this module):
#   * a CHECK constraint pinning host_binding.status to the three statuses the
#     dataclass already allows (the dataclass validates this per-instance; the
#     DB now also rejects an out-of-vocabulary status arriving by raw SQL), and
#   * the partial UNIQUE index above.
SANDBOX_IDENTITY_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS entity_identity (
    entity_id       TEXT PRIMARY KEY,
    schema          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    generated_by    TEXT NOT NULL,
    entropy_bytes   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS installation_identity (
    installation_id TEXT PRIMARY KEY,
    entity_id       TEXT NOT NULL REFERENCES entity_identity(entity_id),
    schema          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS host_binding (
    binding_id      TEXT PRIMARY KEY,
    installation_id TEXT NOT NULL REFERENCES installation_identity(installation_id),
    host_id         TEXT NOT NULL,
    bound_at        TEXT NOT NULL,
    attestation     TEXT NOT NULL,
    status          TEXT NOT NULL
        CHECK (status IN ('{BINDING_STATUS_ACTIVE}',
                          '{BINDING_STATUS_SUPERSEDED}',
                          '{BINDING_STATUS_REVOKED}')),
    schema          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS state_root_identity (
    state_root_id       TEXT PRIMARY KEY,
    installation_id     TEXT NOT NULL REFERENCES installation_identity(installation_id),
    state_digest_sha256 TEXT NOT NULL,
    schema              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_epoch (
    runtime_epoch_id     TEXT PRIMARY KEY,
    state_root_id        TEXT NOT NULL REFERENCES state_root_identity(state_root_id),
    installation_id      TEXT NOT NULL REFERENCES installation_identity(installation_id),
    host_binding_id      TEXT NOT NULL REFERENCES host_binding(binding_id),
    started_at           TEXT NOT NULL,
    predecessor_epoch_id TEXT REFERENCES runtime_epoch(runtime_epoch_id),
    termination_reason   TEXT,
    schema               TEXT NOT NULL
);
"""


class IdentityStoreError(RuntimeError):
    """Raised for store-level misuse (not for constraint violations -- those
    surface as `sqlite3.IntegrityError` on purpose, because the point of this
    module is that the ENGINE rejects them, and callers must be able to see
    the engine's own error type rather than a translated one)."""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a sandbox identity store.

    `isolation_level = None` (autocommit) so the module controls transaction
    boundaries explicitly (`bind_active_host` needs one statement sequence to
    be one atomic swap, not python-sqlite3's implicit per-statement
    transactions). `PRAGMA foreign_keys = ON` because sqlite disables foreign
    keys per connection by default -- without it the FK columns in this schema
    would be decorative, which is exactly the kind of "looks enforced but
    isn't" this module exists to eliminate.
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the sandbox schema + all indexes (idempotent)."""
    if not isinstance(conn, sqlite3.Connection):
        raise IdentityStoreError("create_schema expects a sqlite3.Connection")
    conn.executescript(SANDBOX_IDENTITY_SCHEMA_SQL)
    conn.execute(HOST_BINDING_ONE_ACTIVE_PER_INSTALLATION_INDEX_SQL)
    for statement in SUPPORTING_INDEX_SQL:
        conn.execute(statement)


def ensure_host_binding_atomicity(conn: sqlite3.Connection) -> None:
    """Add ONLY the partial UNIQUE index to an already-existing sandbox
    `host_binding` table (e.g. a Schritt-5 Gold-Test database created before
    this module existed). Idempotent.

    Raises `sqlite3.IntegrityError` if the table's current rows already
    violate the invariant -- the index cannot be created over data that
    breaks it, which is itself a useful diagnostic and not papered over.
    """
    conn.execute(HOST_BINDING_ONE_ACTIVE_PER_INSTALLATION_INDEX_SQL)


# ---------------------------------------------------------------------------
# Thin SQL wrappers. NOTE: none of these is the enforcement point. Each one
# is ordinary SQL; the invariant holds even when every wrapper is bypassed
# and raw SQL is hand-written against the file (proven by tests).
# ---------------------------------------------------------------------------


def insert_entity(conn: sqlite3.Connection, genesis: EntityIdentityGenesisRecord) -> None:
    conn.execute(
        "INSERT INTO entity_identity "
        "(entity_id, schema, created_at, generated_by, entropy_bytes) VALUES (?,?,?,?,?)",
        (
            genesis.entity_id,
            genesis.schema,
            genesis.created_at,
            genesis.generated_by,
            genesis.entropy_bytes,
        ),
    )


def insert_installation(conn: sqlite3.Connection, installation: InstallationIdentity) -> None:
    conn.execute(
        "INSERT INTO installation_identity (installation_id, entity_id, schema) VALUES (?,?,?)",
        (installation.installation_id, installation.entity_id, installation.schema),
    )


def insert_state_root(conn: sqlite3.Connection, root: StateRootIdentity) -> None:
    conn.execute(
        "INSERT INTO state_root_identity "
        "(state_root_id, installation_id, state_digest_sha256, schema) VALUES (?,?,?,?)",
        (root.state_root_id, root.installation_id, root.state_digest_sha256, root.schema),
    )


def insert_host_binding(conn: sqlite3.Connection, binding: HostBinding) -> None:
    """Convenience INSERT of an already-terminal-or-active binding row.

    For the legitimate ACTIVE->ACTIVE handover use `bind_active_host()`, which
    supersedes the previous ACTIVE row inside the SAME transaction -- inserting
    a second ACTIVE row directly is refused by the engine, not by this wrapper.
    """
    conn.execute(
        "INSERT INTO host_binding "
        "(binding_id, installation_id, host_id, bound_at, attestation, status, schema) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            binding.binding_id,
            binding.installation_id,
            binding.host_id,
            binding.bound_at,
            binding.attestation,
            binding.status,
            binding.schema,
        ),
    )


def insert_runtime_epoch(conn: sqlite3.Connection, epoch: RuntimeEpoch) -> None:
    conn.execute(
        "INSERT INTO runtime_epoch "
        "(runtime_epoch_id, state_root_id, installation_id, host_binding_id, started_at, "
        " predecessor_epoch_id, termination_reason, schema) VALUES (?,?,?,?,?,?,?,?)",
        (
            epoch.runtime_epoch_id,
            epoch.state_root_id,
            epoch.installation_id,
            epoch.host_binding_id,
            epoch.started_at,
            epoch.predecessor_epoch_id,
            epoch.termination_reason,
            epoch.schema,
        ),
    )


def set_host_binding_status(
    conn: sqlite3.Connection, *, binding_id: str, status: str
) -> None:
    """Generic status UPDATE. Raises `IdentityStoreError` for a status outside
    the three the schema knows (fail closed before the DB's CHECK would) --
    but a DB-level CHECK constraint is in place regardless, so a future
    wrapper bug cannot write an unknown status either."""
    if status not in (BINDING_STATUS_ACTIVE, BINDING_STATUS_SUPERSEDED, BINDING_STATUS_REVOKED):
        raise IdentityStoreError(f"unsupported host binding status: {status!r}")
    cur = conn.execute(
        "UPDATE host_binding SET status = ? WHERE binding_id = ?", (status, binding_id)
    )
    if cur.rowcount != 1:
        raise IdentityStoreError(f"host binding not found: {binding_id!r}")


def active_host_binding(
    conn: sqlite3.Connection, installation_id: str
) -> dict[str, Any] | None:
    """Read back the (at most one) ACTIVE binding of an installation. Returns
    None when the installation currently has no ACTIVE binding."""
    row = conn.execute(
        "SELECT binding_id, installation_id, host_id, bound_at, attestation, status, schema "
        "FROM host_binding WHERE installation_id = ? AND status = ?",
        (installation_id, BINDING_STATUS_ACTIVE),
    ).fetchall()
    if not row:
        return None
    if len(row) > 1:  # unreachable while the index exists -- guard, not enforcement
        raise IdentityStoreError(
            f"invariant violated: {len(row)} ACTIVE bindings for {installation_id!r}"
        )
    keys = ("binding_id", "installation_id", "host_id", "bound_at", "attestation", "status", "schema")
    return dict(zip(keys, row[0]))


def bind_active_host(conn: sqlite3.Connection, binding: HostBinding) -> int:
    """Atomically make `binding` the ONE ACTIVE binding of its installation.

    Runs as ONE `BEGIN IMMEDIATE` transaction:

        UPDATE host_binding SET status = 'SUPERSEDED'
            WHERE installation_id = ? AND status = 'ACTIVE';
        INSERT INTO host_binding (...) VALUES (...);

    The partial UNIQUE index makes the opposite order (insert-new-then-end-old,
    or forgetting to end the old one) impossible, so the only way to get from
    "old binding ACTIVE" to "new binding ACTIVE" without ever having two ACTIVE
    rows is this single transaction -- which also means no other connection can
    ever OBSERVE a two-ACTIVE or zero-ACTIVE intermediate state (SQLite gives
    them the pre-transaction snapshot until COMMIT).

    Returns the number of previously-ACTIVE rows it superseded (0 for the very
    first binding of a fresh installation).
    """
    if binding.status != BINDING_STATUS_ACTIVE:
        raise IdentityStoreError(
            "bind_active_host mints an ACTIVE binding; pass status != ACTIVE to "
            "insert_host_binding instead"
        )
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(
            "UPDATE host_binding SET status = ? WHERE installation_id = ? AND status = ?",
            (BINDING_STATUS_SUPERSEDED, binding.installation_id, BINDING_STATUS_ACTIVE),
        )
        superseded = cur.rowcount
        insert_host_binding(conn, binding)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return superseded
