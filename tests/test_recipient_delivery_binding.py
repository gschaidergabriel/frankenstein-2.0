from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from frankenstein2.recipient_delivery_binding import (
    RecipientDeliveryBindingError,
    bind_recipient_delivery_to_canonical_unifieddb,
)


class RecipientDeliveryCanonicalBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.config = self.root / "config"
        self.config.mkdir()
        self.pointer = self.config / "db_pfad.txt"

    def tearDown(self) -> None:
        self.td.cleanup()

    def make_db(self, name: str = "unified.db") -> Path:
        path = self.root / name
        con = sqlite3.connect(path)
        try:
            con.execute("CREATE TABLE canonical_seed(id INTEGER PRIMARY KEY, value TEXT)")
            con.execute("INSERT INTO canonical_seed(value) VALUES('preserve-me')")
            con.commit()
        finally:
            con.close()
        return path

    def env_for(self, db: Path) -> dict[str, str]:
        return {
            "FRANKENSTEIN2_DB": str(db),
            "XDG_CONFIG_HOME": str(self.root / "xdg-config"),
            "XDG_DATA_HOME": str(self.root / "xdg-data"),
        }

    def bind(self, db: Path):
        return bind_recipient_delivery_to_canonical_unifieddb(
            env=self.env_for(db),
            home=self.home,
            pointer_path=self.pointer,
        )

    def test_binding_uses_same_canonical_sqlite_inode_and_preserves_existing_state(self) -> None:
        db = self.make_db()
        before_stat = db.stat()
        bound = self.bind(db)
        receipt = bound.binding
        after_stat = db.stat()

        self.assertEqual(receipt.resolution["path"], str(db.resolve()))
        self.assertEqual(receipt.resolution["source"], "EXPLICIT_FRANKENSTEIN2_DB")
        self.assertTrue(receipt.same_real_path)
        self.assertTrue(receipt.same_device)
        self.assertTrue(receipt.same_inode)
        self.assertEqual(before_stat.st_ino, after_stat.st_ino)
        self.assertTrue(receipt.required_tables_present)
        self.assertEqual(receipt.quick_check.lower(), "ok")
        self.assertEqual(
            receipt.classification,
            "CANONICAL_UNIFIEDDB_COORDINATION_COMPONENT_BINDING_ONLY",
        )

        con = sqlite3.connect(db)
        try:
            self.assertEqual(
                con.execute("SELECT value FROM canonical_seed").fetchone()[0],
                "preserve-me",
            )
            names = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("coordination_events", names)
            self.assertIn("coordination_deliveries", names)
        finally:
            con.close()

    def test_bound_store_performs_delivery_in_that_exact_unifieddb(self) -> None:
        db = self.make_db()
        bound = self.bind(db)
        bound.store.register(
            event_id="evt-bound",
            generation=4,
            payload={"result": "child-complete"},
            recipients=["parent-agent"],
            created_at=1.0,
        )
        offer = bound.store.offer(
            recipient_id="parent-agent",
            generation=4,
            lease_seconds=5.0,
            now=10.0,
        )[0]
        ack = bound.store.ack(
            event_id="evt-bound",
            recipient_id="parent-agent",
            generation=4,
            offer_token=offer.offer_token or "",
            now=11.0,
        )
        self.assertEqual(ack.state, "ACKED")

        con = sqlite3.connect(db)
        try:
            row = con.execute(
                "SELECT state,generation,attempt_count FROM coordination_deliveries "
                "WHERE event_id='evt-bound' AND recipient_id='parent-agent'"
            ).fetchone()
            self.assertEqual(row, ("ACKED", 4, 1))
        finally:
            con.close()

    def test_missing_explicit_target_cannot_be_minted_by_wp103_adapter(self) -> None:
        missing = self.root / "missing.db"
        with self.assertRaisesRegex(
            RecipientDeliveryBindingError,
            "MUST_EXIST_BEFORE_WP103_ADMISSION",
        ):
            self.bind(missing)
        self.assertFalse(missing.exists())

    def test_conflicting_explicit_db_authorities_fail_before_any_mutation(self) -> None:
        primary = self.make_db("primary.db")
        other = self.make_db("other.db")
        env = self.env_for(primary)
        env["AGENTZERO_DB"] = str(other)

        with self.assertRaisesRegex(
            RecipientDeliveryBindingError,
            "UNIFIEDDB_AUTHORITY_REJECTED.*AUTHORITY_CONFLICT",
        ):
            bind_recipient_delivery_to_canonical_unifieddb(
                env=env,
                home=self.home,
                pointer_path=self.pointer,
            )

        for db in (primary, other):
            con = sqlite3.connect(db)
            try:
                names = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertNotIn("coordination_events", names)
                self.assertNotIn("coordination_deliveries", names)
            finally:
                con.close()

    def test_pointer_and_env_must_resolve_to_same_file(self) -> None:
        db = self.make_db()
        self.pointer.write_text(str(db), encoding="utf-8")
        bound = self.bind(db)
        self.assertEqual(
            bound.binding.resolution["explicit_sources"],
            ("POINTER", "FRANKENSTEIN2_DB"),
        )

    def test_binding_receipt_is_deterministically_serializable(self) -> None:
        db = self.make_db()
        bound = self.bind(db)
        first = bound.binding.canonical_json()
        second = bound.binding.canonical_json()
        self.assertEqual(first, second)
        self.assertIn('"same_inode":true', first)
        self.assertIn('"quick_check":"ok"', first.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
