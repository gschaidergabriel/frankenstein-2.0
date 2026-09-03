"""F2-WP-1207 Schritt 3: prove EntityIdentity + InstallationIdentity persist
via REAL SQL (INSERT + SELECT readback), not an in-memory Python simulation.

SAFETY (see task directive + CLAUDE.md): this test NEVER touches
`~/.local/share/agentzero/unified.db` (the real UnifiedDB) and NEVER touches
`~/frankenstein-repo` (the live checkout). Every database here is a
`tempfile.TemporaryDirectory()`-scoped sqlite file, created and destroyed
within a single test method. The schema below is a SANDBOX schema modeled on
this module's own dataclass fields -- it is NOT a verified copy of the real
production UnifiedDB schema (that schema was never inspected in this round,
per the safety instruction to stay out of `~/frankenstein-repo`). "Real"
here means "real SQL INSERT/SELECT/FK mechanics", not "matches production
table layout byte-for-byte".
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from frankenstein2.entity_identity import (
    EntityIdentityGenesisRecord,
    InstallationIdentity,
    generate_entity_identity,
)

SANDBOX_SCHEMA_SQL = """
CREATE TABLE entity_identity (
    entity_id       TEXT PRIMARY KEY,
    schema          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    generated_by    TEXT NOT NULL,
    entropy_bytes   INTEGER NOT NULL
);

CREATE TABLE installation_identity (
    installation_id TEXT PRIMARY KEY,
    entity_id       TEXT NOT NULL REFERENCES entity_identity(entity_id),
    schema          TEXT NOT NULL
);
"""


class Step3SandboxPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "F2-WP-1207-step3-sandbox.db"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript(SANDBOX_SCHEMA_SQL)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self._tmpdir.cleanup()

    def test_real_insert_and_select_readback_entity_and_installation(self) -> None:
        genesis = generate_entity_identity(
            now="2026-09-03T12:00:00+00:00",
            generated_by="F2-WP-1207-step3-sandbox",
        )
        entity = genesis.identity()
        installation = InstallationIdentity.create(
            installation_id="i1-sandbox", entity_id=entity.entity_id
        )

        self.conn.execute(
            "INSERT INTO entity_identity "
            "(entity_id, schema, created_at, generated_by, entropy_bytes) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                genesis.entity_id,
                genesis.schema,
                genesis.created_at,
                genesis.generated_by,
                genesis.entropy_bytes,
            ),
        )
        self.conn.execute(
            "INSERT INTO installation_identity (installation_id, entity_id, schema) "
            "VALUES (?, ?, ?)",
            (installation.installation_id, installation.entity_id, installation.schema),
        )
        self.conn.commit()

        # Close and REOPEN the connection to the same file -- proves this is
        # durable sqlite state, not just visible within the same connection.
        self.conn.close()
        self.conn = sqlite3.connect(self.db_path)

        row_e = self.conn.execute(
            "SELECT entity_id, schema, created_at, generated_by, entropy_bytes "
            "FROM entity_identity WHERE entity_id = ?",
            (entity.entity_id,),
        ).fetchone()
        row_i = self.conn.execute(
            "SELECT installation_id, entity_id, schema FROM installation_identity "
            "WHERE installation_id = ?",
            (installation.installation_id,),
        ).fetchone()

        self.assertIsNotNone(row_e)
        self.assertIsNotNone(row_i)
        self.assertEqual(row_e[0], entity.entity_id)
        self.assertEqual(row_i[0], installation.installation_id)
        self.assertEqual(row_i[1], entity.entity_id)  # real FK-shaped linkage, from disk

        # Rebuild the dataclass FROM the SELECT row (not from the in-memory
        # `genesis` object) -- proves the readback path, digest-for-digest.
        reloaded = EntityIdentityGenesisRecord.from_dict(
            {
                "schema": row_e[1],
                "entity_id": row_e[0],
                "created_at": row_e[2],
                "generated_by": row_e[3],
                "entropy_bytes": row_e[4],
            }
        )
        self.assertEqual(reloaded.sha256(), genesis.sha256())
        self.assertEqual(reloaded.identity().entity_id, entity.entity_id)

    def test_installation_row_count_is_exactly_one_after_one_insert(self) -> None:
        """Minimal record only, per directive: two base rows, no ontology."""
        genesis = generate_entity_identity()
        installation = InstallationIdentity.create(
            installation_id="i2-sandbox", entity_id=genesis.entity_id
        )
        self.conn.execute(
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
        self.conn.execute(
            "INSERT INTO installation_identity (installation_id, entity_id, schema) "
            "VALUES (?, ?, ?)",
            (installation.installation_id, installation.entity_id, installation.schema),
        )
        self.conn.commit()
        (count,) = self.conn.execute("SELECT COUNT(*) FROM installation_identity").fetchone()
        self.assertEqual(count, 1)

    def test_foreign_key_integrity_is_really_enforced_by_sqlite(self) -> None:
        """Proves the FK is a real, engine-enforced constraint (PRAGMA
        foreign_keys=ON), not a decorative column -- inserting an
        installation row pointing at a non-existent entity_id must fail."""
        self.conn.execute("PRAGMA foreign_keys = ON")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO installation_identity (installation_id, entity_id, schema) "
                "VALUES (?, ?, ?)",
                ("orphan-installation", "no-such-entity-id", "FRANKENSTEIN2_INSTALLATION_IDENTITY/v1"),
            )


if __name__ == "__main__":
    unittest.main()
