#!/usr/bin/env python3
"""Repository-component integration falsifiers for WP900 -> WP206 persistence."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest

from frankenstein2.persistent_agency_kernel import CanonicalPersistentAgencyStore, PersistentAgencyError
from frankenstein2.whole_loop_persistence_integration import (
    WholeLoopPersistenceIntegrationError,
    persist_sealed_successor_and_readback,
)
from frankenstein2.whole_persistent_loop import seal_whole_persistent_loop
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path
from tests.test_whole_persistent_loop import fixture_components


class WholeLoopPersistenceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.db = self.root / "canonical" / "unified.db"
        self.db.parent.mkdir()
        connection = sqlite3.connect(self.db)
        try:
            connection.execute("CREATE TABLE f2_bootstrap(id INTEGER PRIMARY KEY)")
            connection.commit()
        finally:
            connection.close()
        env = {"FRANKENSTEIN2_DB": str(self.db)}
        resolution = resolve_unifieddb_path(env=env, home=self.home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        self.store = CanonicalPersistentAgencyStore.open(
            resolution=resolution,
            fingerprint=fingerprint,
        )
        self.store.initialize_schema()

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    @staticmethod
    def _sealed_fixture():
        (
            current,
            frame,
            contract,
            plan,
            gwt,
            gwt_evidence,
            decision,
            outcome,
            successor,
        ) = fixture_components()
        seal = seal_whole_persistent_loop(
            seal_id="whole-loop-persist-integration",
            generation=0,
            current_checkpoint=current,
            frame=frame,
            contract=contract,
            plan=plan,
            gwt_seal=gwt,
            gwt_evidence=gwt_evidence,
            decision=decision,
            outcome=outcome,
            next_checkpoint=successor,
            provenance_refs=("test:wp900-wp206:integration",),
        )
        return current, successor, seal

    def test_sealed_successor_is_written_by_wp206_and_typed_read_back(self) -> None:
        current, successor, seal = self._sealed_fixture()
        self.store.write_checkpoint(current)

        evidence = persist_sealed_successor_and_readback(
            self.store,
            seal=seal,
            next_checkpoint=successor,
        )

        readback = self.store.load_checkpoint(successor.checkpoint_id)
        self.assertEqual(readback.sha256(), successor.sha256())
        self.assertEqual(evidence.whole_loop_seal_sha256, seal.sha256())
        self.assertEqual(evidence.next_checkpoint_sha256, successor.sha256())
        payload = evidence.as_dict()
        self.assertEqual(
            payload["canonical_persistence_authority"],
            "WP206_CANONICAL_PERSISTENT_AGENCY_STORE",
        )
        self.assertTrue(payload["write_observed"])
        self.assertTrue(payload["typed_readback_observed"])
        self.assertEqual(payload["runtime_credit"], 0)
        self.assertFalse(payload["whole_system_acceptance"])

    def test_replay_is_idempotent_for_exact_same_successor_bytes(self) -> None:
        current, successor, seal = self._sealed_fixture()
        self.store.write_checkpoint(current)
        first = persist_sealed_successor_and_readback(
            self.store, seal=seal, next_checkpoint=successor
        )
        second = persist_sealed_successor_and_readback(
            self.store, seal=seal, next_checkpoint=successor
        )
        self.assertEqual(first.sha256(), second.sha256())

    def test_forged_successor_digest_fails_before_store_write(self) -> None:
        current, successor, seal = self._sealed_fixture()
        self.store.write_checkpoint(current)
        forged = replace(seal, next_checkpoint_sha256="f" * 64)
        with self.assertRaisesRegex(
            WholeLoopPersistenceIntegrationError, "SEALED_SUCCESSOR_DIGEST_MISMATCH"
        ):
            persist_sealed_successor_and_readback(
                self.store, seal=forged, next_checkpoint=successor
            )
        with self.assertRaisesRegex(PersistentAgencyError, "CHECKPOINT_NOT_FOUND"):
            self.store.load_checkpoint(successor.checkpoint_id)

    def test_unpersisted_parent_fails_before_successor_write(self) -> None:
        _, successor, seal = self._sealed_fixture()
        with self.assertRaisesRegex(
            WholeLoopPersistenceIntegrationError, "SEALED_PARENT_READBACK_FAILED"
        ):
            persist_sealed_successor_and_readback(
                self.store, seal=seal, next_checkpoint=successor
            )
        with self.assertRaisesRegex(PersistentAgencyError, "CHECKPOINT_NOT_FOUND"):
            self.store.load_checkpoint(successor.checkpoint_id)

    def test_stored_parent_digest_must_match_seal(self) -> None:
        current, successor, seal = self._sealed_fixture()
        self.store.write_checkpoint(current)
        forged = replace(seal, current_checkpoint_sha256="e" * 64)
        with self.assertRaisesRegex(
            WholeLoopPersistenceIntegrationError, "SEALED_PARENT_DIGEST_MISMATCH"
        ):
            persist_sealed_successor_and_readback(
                self.store, seal=forged, next_checkpoint=successor
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
