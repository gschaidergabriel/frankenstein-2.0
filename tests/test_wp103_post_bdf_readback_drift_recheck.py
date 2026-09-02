#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frankenstein2.causal_identity import CausalIdentity
from state.delivery_lifecycle import DeliveryOperation, DeliveryTransition, derive_delivery_id
from state.delivery_store import CanonicalDeliveryStore, DeliveryStoreError
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


class WP103PostBdfReadbackDriftRecheck(unittest.TestCase):
    def _open_populated_store(self, tmp: str):
        home = str(Path(tmp) / "home")
        Path(home).mkdir(parents=True, exist_ok=True)
        db_path = str(Path(tmp) / "unified.db")
        connection = sqlite3.connect(db_path)
        connection.execute("CREATE TABLE bootstrap_identity(seed INTEGER NOT NULL)")
        connection.commit()
        connection.close()

        resolution = resolve_unifieddb_path(env={"FRANKENSTEIN2_DB": db_path}, home=home)
        fingerprint = fingerprint_unifieddb(resolution.path)
        store = CanonicalDeliveryStore.open(resolution=resolution, fingerprint=fingerprint, timeout=5.0)
        store.initialize_schema()
        identity = CausalIdentity(
            session_id="session:wp103-post-bdf",
            agent_id="agent:review-only",
            task_id="task:wp103-post-bdf",
            turn_id="turn:1",
            causal_id="causal:wp103-post-bdf",
            generation=1,
        )
        delivery_id = derive_delivery_id(identity.causal_id, "recipient:alpha")
        store.apply(
            identity,
            DeliveryTransition(
                transition_id="transition:offer-before-replacement",
                delivery_id=delivery_id,
                causal_event_id=identity.causal_id,
                recipient_id="recipient:alpha",
                generation=1,
                operation=DeliveryOperation.OFFER,
                transport_attempt_id="attempt:1",
            ),
        )

        replacement_path = str(Path(tmp) / "replacement.db")
        replacement = sqlite3.connect(replacement_path)
        replacement.execute("CREATE TABLE bootstrap_identity(seed INTEGER NOT NULL)")
        replacement.commit()
        replacement.close()
        os.replace(replacement_path, db_path)
        return store, identity, delivery_id

    def test_get_delivery_rejects_replaced_canonical_inode(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, identity, _ = self._open_populated_store(tmp)
            try:
                with self.assertRaisesRegex(DeliveryStoreError, "UNIFIEDDB_LIVE_FILE_IDENTITY_DRIFT"):
                    store.get_delivery(causal_event_id=identity.causal_id, recipient_id="recipient:alpha")
            finally:
                store.close()

    def test_transition_count_rejects_replaced_canonical_inode(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, _, delivery_id = self._open_populated_store(tmp)
            try:
                with self.assertRaisesRegex(DeliveryStoreError, "UNIFIEDDB_LIVE_FILE_IDENTITY_DRIFT"):
                    store.transition_count(delivery_id)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
