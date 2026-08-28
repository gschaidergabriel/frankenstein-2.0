#!/usr/bin/env python3
from __future__ import annotations

import multiprocessing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frankenstein2.causal_identity import CausalIdentity
from state.delivery_lifecycle import (
    DeliveryLifecycleError,
    DeliveryOperation,
    DeliveryState,
    DeliveryTransition,
    derive_delivery_id,
)
from state.delivery_store import CanonicalDeliveryStore, DeliveryStoreError
from state.unifieddb_identity import fingerprint_unifieddb, resolve_unifieddb_path


def _authority(db_path: str, home: str):
    resolution = resolve_unifieddb_path(
        env={"FRANKENSTEIN2_DB": db_path},
        home=home,
    )
    fingerprint = fingerprint_unifieddb(resolution.path)
    return resolution, fingerprint


def _open_store(db_path: str, home: str) -> CanonicalDeliveryStore:
    resolution, fingerprint = _authority(db_path, home)
    return CanonicalDeliveryStore.open(
        resolution=resolution,
        fingerprint=fingerprint,
        timeout=5.0,
    )


def _identity(task_id: str = "task:1", generation: int = 7) -> CausalIdentity:
    return CausalIdentity(
        session_id="session:1",
        agent_id="agent:root",
        task_id=task_id,
        turn_id="turn:1",
        causal_id="causal:event-1",
        generation=generation,
    )


def _transition(
    transition_id: str,
    operation: DeliveryOperation,
    *,
    attempt: str = "attempt:1",
    generation: int = 7,
) -> DeliveryTransition:
    return DeliveryTransition(
        transition_id=transition_id,
        delivery_id=derive_delivery_id("causal:event-1", "recipient:alpha"),
        causal_event_id="causal:event-1",
        recipient_id="recipient:alpha",
        generation=generation,
        operation=operation,
        transport_attempt_id=attempt,
    )


def _process_apply(db_path, home, barrier, queue, transition):
    store = None
    try:
        store = _open_store(db_path, home)
        barrier.wait(timeout=10)
        result = store.apply(_identity(), transition)
        queue.put(("OK", result.state.value, result.transport_attempt_ids))
    except (DeliveryLifecycleError, DeliveryStoreError) as exc:
        queue.put(("FAIL_CLOSED", type(exc).__name__, str(exc)))
    except Exception as exc:  # test harness must surface unexpected failures exactly
        queue.put(("UNEXPECTED", type(exc).__name__, str(exc)))
    finally:
        if store is not None:
            store.close()


class CanonicalDeliveryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = str(Path(self.tmp.name) / "home")
        Path(self.home).mkdir(parents=True)
        self.db_path = str(Path(self.tmp.name) / "unified.db")
        connection = sqlite3.connect(self.db_path)
        connection.execute("CREATE TABLE bootstrap_identity(seed INTEGER NOT NULL)")
        connection.commit()
        connection.close()

        store = _open_store(self.db_path, self.home)
        store.initialize_schema()
        store.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_writer_is_bound_to_fingerprinted_canonical_file(self):
        resolution, fingerprint = _authority(self.db_path, self.home)
        other_path = str(Path(self.tmp.name) / "other.db")
        other = sqlite3.connect(other_path)
        other.execute("CREATE TABLE other_state(x INTEGER)")
        other.commit()
        with self.assertRaisesRegex(
            DeliveryStoreError,
            "SQLITE_CONNECTION_NOT_BOUND_TO_FINGERPRINTED_UNIFIEDDB",
        ):
            CanonicalDeliveryStore(
                other,
                resolution=resolution,
                fingerprint=fingerprint,
            )
        other.close()

    def test_offer_ack_persists_across_reopen(self):
        store = _open_store(self.db_path, self.home)
        offered = store.apply(
            _identity(), _transition("transition:offer-1", DeliveryOperation.OFFER)
        )
        self.assertEqual(offered.state, DeliveryState.OFFERED)
        store.close()

        store = _open_store(self.db_path, self.home)
        acked = store.apply(
            _identity(), _transition("transition:ack-1", DeliveryOperation.ACK)
        )
        self.assertEqual(acked.state, DeliveryState.ACKED)
        self.assertEqual(acked.acknowledged_attempt_id, "attempt:1")
        store.close()

    def test_exact_replay_across_reopen_is_one_transition(self):
        offer = _transition("transition:offer-1", DeliveryOperation.OFFER)
        store = _open_store(self.db_path, self.home)
        once = store.apply(_identity(), offer)
        store.close()

        store = _open_store(self.db_path, self.home)
        twice = store.apply(_identity(), offer)
        self.assertEqual(twice, once)
        self.assertEqual(store.transition_count(once.delivery_id), 1)
        store.close()

    def test_transition_id_reuse_with_changed_payload_fails_closed(self):
        store = _open_store(self.db_path, self.home)
        store.apply(
            _identity(), _transition("transition:offer-1", DeliveryOperation.OFFER)
        )
        with self.assertRaisesRegex(
            DeliveryStoreError, "TRANSITION_ID_REUSED_WITH_CHANGED_PAYLOAD"
        ):
            store.apply(
                _identity(),
                _transition(
                    "transition:offer-1",
                    DeliveryOperation.OFFER,
                    attempt="attempt:changed",
                ),
            )
        store.close()

    def test_same_causal_id_with_context_drift_fails_closed(self):
        store = _open_store(self.db_path, self.home)
        store.apply(
            _identity(), _transition("transition:offer-1", DeliveryOperation.OFFER)
        )
        with self.assertRaisesRegex(
            DeliveryStoreError, "CAUSAL_IDENTITY_DRIFT_FOR_EXISTING_DELIVERY"
        ):
            store.apply(
                _identity(task_id="task:other"),
                _transition("transition:ack-1", DeliveryOperation.ACK),
            )
        store.close()

    def test_stale_transition_generation_is_rejected_before_insert(self):
        store = _open_store(self.db_path, self.home)
        with self.assertRaisesRegex(
            DeliveryStoreError, "TRANSITION_GENERATION_NOT_BOUND_TO_CAUSAL_IDENTITY"
        ):
            store.apply(
                _identity(generation=7),
                _transition(
                    "transition:offer-stale",
                    DeliveryOperation.OFFER,
                    generation=6,
                ),
            )
        self.assertIsNone(
            store.get_delivery(
                causal_event_id="causal:event-1", recipient_id="recipient:alpha"
            )
        )
        store.close()

    def test_two_processes_replaying_same_offer_converge_to_one_transition(self):
        ctx = multiprocessing.get_context("spawn")
        barrier = ctx.Barrier(2)
        queue = ctx.Queue()
        offer = _transition("transition:offer-1", DeliveryOperation.OFFER)
        processes = [
            ctx.Process(
                target=_process_apply,
                args=(self.db_path, self.home, barrier, queue, offer),
            )
            for _ in range(2)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(15)
            self.assertEqual(process.exitcode, 0)

        results = [queue.get(timeout=5) for _ in processes]
        self.assertEqual([item[0] for item in results], ["OK", "OK"])
        store = _open_store(self.db_path, self.home)
        record = store.get_delivery(
            causal_event_id="causal:event-1", recipient_id="recipient:alpha"
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.transport_attempt_ids, ("attempt:1",))
        self.assertEqual(store.transition_count(record.delivery_id), 1)
        store.close()

    def test_two_process_retry_vs_ack_cannot_lose_ack(self):
        store = _open_store(self.db_path, self.home)
        store.apply(
            _identity(), _transition("transition:offer-1", DeliveryOperation.OFFER)
        )
        store.close()

        ctx = multiprocessing.get_context("spawn")
        barrier = ctx.Barrier(2)
        queue = ctx.Queue()
        retry = _transition(
            "transition:retry-2", DeliveryOperation.OFFER, attempt="attempt:2"
        )
        ack = _transition("transition:ack-1", DeliveryOperation.ACK)
        processes = [
            ctx.Process(
                target=_process_apply,
                args=(self.db_path, self.home, barrier, queue, transition),
            )
            for transition in (retry, ack)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(15)
            self.assertEqual(process.exitcode, 0)

        results = [queue.get(timeout=5) for _ in processes]
        self.assertNotIn("UNEXPECTED", [item[0] for item in results])
        store = _open_store(self.db_path, self.home)
        record = store.get_delivery(
            causal_event_id="causal:event-1", recipient_id="recipient:alpha"
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.state, DeliveryState.ACKED)
        self.assertEqual(record.acknowledged_attempt_id, "attempt:1")
        self.assertIn(len(record.transport_attempt_ids), (1, 2))
        store.close()


if __name__ == "__main__":
    unittest.main()
