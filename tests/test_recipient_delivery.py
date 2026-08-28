from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from frankenstein2.recipient_delivery import (
    DeliveryConflict,
    DeliveryError,
    DeliveryStateError,
    RecipientDeliveryStore,
)


class RecipientDeliveryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "unified.sqlite"
        self.store = RecipientDeliveryStore(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def register_two(self) -> None:
        self.store.register(
            event_id="evt-1",
            generation=7,
            payload={"kind": "TASK_RESULT", "value": 42},
            recipients=["parent", "observer"],
            created_at=1.0,
        )

    def test_register_is_per_recipient_and_non_destructive(self) -> None:
        self.register_two()
        parent1 = self.store.get(event_id="evt-1", recipient_id="parent")
        parent2 = self.store.get(event_id="evt-1", recipient_id="parent")
        observer = self.store.get(event_id="evt-1", recipient_id="observer")

        self.assertEqual(parent1.state, "PENDING")
        self.assertEqual(parent2.state, "PENDING")
        self.assertEqual(observer.state, "PENDING")
        self.assertEqual(parent1.attempt_count, 0)
        self.assertEqual(self.store.delivery_counts(), {"ACKED": 0, "OFFERED": 0, "PENDING": 2})

    def test_duplicate_registration_is_idempotent_for_same_immutable_event(self) -> None:
        self.store.register(
            event_id="evt-idem",
            generation=1,
            payload={"b": 2, "a": 1},
            recipients=["r1", "r1"],
            created_at=1.0,
        )
        # Reordered mapping is identical under canonical JSON; adding a recipient is allowed.
        self.store.register(
            event_id="evt-idem",
            generation=1,
            payload={"a": 1, "b": 2},
            recipients=["r1", "r2"],
            created_at=999.0,
        )
        self.assertEqual(self.store.delivery_counts(), {"ACKED": 0, "OFFERED": 0, "PENDING": 2})
        self.assertEqual(
            self.store.get(event_id="evt-idem", recipient_id="r1").payload,
            {"a": 1, "b": 2},
        )

    def test_stable_event_id_reuse_with_different_payload_or_generation_fails_closed(self) -> None:
        self.store.register(
            event_id="evt-conflict",
            generation=3,
            payload={"value": "A"},
            recipients=["r1"],
            created_at=1.0,
        )
        with self.assertRaises(DeliveryConflict):
            self.store.register(
                event_id="evt-conflict",
                generation=3,
                payload={"value": "B"},
                recipients=["r1"],
                created_at=2.0,
            )
        with self.assertRaises(DeliveryConflict):
            self.store.register(
                event_id="evt-conflict",
                generation=4,
                payload={"value": "A"},
                recipients=["r1"],
                created_at=2.0,
            )

    def test_offer_is_recipient_scoped_and_live_offer_is_not_duplicated(self) -> None:
        self.register_two()
        offered = self.store.offer(
            recipient_id="parent", generation=7, lease_seconds=10.0, now=100.0
        )
        self.assertEqual(len(offered), 1)
        self.assertEqual(offered[0].state, "OFFERED")
        self.assertEqual(offered[0].attempt_count, 1)
        self.assertIsNotNone(offered[0].offer_token)

        # The live lease prevents duplicate concurrent consumption.
        self.assertEqual(
            self.store.offer(
                recipient_id="parent", generation=7, lease_seconds=10.0, now=105.0
            ),
            [],
        )
        self.assertEqual(
            self.store.get(event_id="evt-1", recipient_id="observer").state,
            "PENDING",
        )

    def test_expired_offer_redelivers_with_new_token_and_rejects_stale_ack(self) -> None:
        self.register_two()
        first = self.store.offer(
            recipient_id="parent", generation=7, lease_seconds=5.0, now=10.0
        )[0]
        second = self.store.offer(
            recipient_id="parent", generation=7, lease_seconds=5.0, now=15.0
        )[0]

        self.assertEqual(second.attempt_count, 2)
        self.assertNotEqual(first.offer_token, second.offer_token)
        with self.assertRaises(DeliveryStateError):
            self.store.ack(
                event_id="evt-1",
                recipient_id="parent",
                generation=7,
                offer_token=first.offer_token or "",
                now=16.0,
            )

        acked = self.store.ack(
            event_id="evt-1",
            recipient_id="parent",
            generation=7,
            offer_token=second.offer_token or "",
            now=16.0,
        )
        self.assertEqual(acked.state, "ACKED")
        self.assertEqual(acked.attempt_count, 2)
        self.assertEqual(self.store.delivery_counts(recipient_id="parent")["ACKED"], 1)
        self.assertEqual(self.store.delivery_counts(recipient_id="observer")["PENDING"], 1)

    def test_expired_offer_cannot_be_acked_without_redelivery(self) -> None:
        self.register_two()
        offered = self.store.offer(
            recipient_id="parent", generation=7, lease_seconds=1.0, now=20.0
        )[0]
        with self.assertRaises(DeliveryStateError):
            self.store.ack(
                event_id="evt-1",
                recipient_id="parent",
                generation=7,
                offer_token=offered.offer_token or "",
                now=22.0,
            )
        self.assertEqual(
            self.store.get(event_id="evt-1", recipient_id="parent").state,
            "OFFERED",
        )

    def test_generation_is_hard_fence_for_offer_and_ack(self) -> None:
        self.register_two()
        self.assertEqual(
            self.store.offer(
                recipient_id="parent", generation=6, lease_seconds=10.0, now=1.0
            ),
            [],
        )
        offered = self.store.offer(
            recipient_id="parent", generation=7, lease_seconds=10.0, now=1.0
        )[0]
        with self.assertRaises(DeliveryStateError):
            self.store.ack(
                event_id="evt-1",
                recipient_id="parent",
                generation=8,
                offer_token=offered.offer_token or "",
                now=2.0,
            )

    def test_ack_is_terminal_and_does_not_reoffer(self) -> None:
        self.register_two()
        offered = self.store.offer(
            recipient_id="parent", generation=7, lease_seconds=10.0, now=30.0
        )[0]
        acked = self.store.ack(
            event_id="evt-1",
            recipient_id="parent",
            generation=7,
            offer_token=offered.offer_token or "",
            now=31.0,
        )
        self.assertEqual(acked.state, "ACKED")
        self.assertEqual(
            self.store.offer(
                recipient_id="parent", generation=7, lease_seconds=10.0, now=1000.0
            ),
            [],
        )
        with self.assertRaises(DeliveryStateError):
            self.store.ack(
                event_id="evt-1",
                recipient_id="parent",
                generation=7,
                offer_token=offered.offer_token or "",
                now=32.0,
            )

    def test_persistence_survives_store_reopen(self) -> None:
        self.register_two()
        first = self.store.offer(
            recipient_id="parent", generation=7, lease_seconds=5.0, now=50.0
        )[0]
        reopened = RecipientDeliveryStore(self.db)
        observed = reopened.get(event_id="evt-1", recipient_id="parent")
        self.assertEqual(observed.state, "OFFERED")
        self.assertEqual(observed.offer_token, first.offer_token)

        redelivered = reopened.offer(
            recipient_id="parent", generation=7, lease_seconds=5.0, now=55.0
        )[0]
        self.assertEqual(redelivered.attempt_count, 2)

    def test_two_store_instances_do_not_duplicate_live_offer(self) -> None:
        self.register_two()
        other = RecipientDeliveryStore(self.db)
        first = self.store.offer(
            recipient_id="parent", generation=7, lease_seconds=20.0, now=100.0
        )
        second = other.offer(
            recipient_id="parent", generation=7, lease_seconds=20.0, now=100.0
        )
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(
            other.get(event_id="evt-1", recipient_id="parent").attempt_count,
            1,
        )

    def test_database_constraints_reject_impossible_state(self) -> None:
        self.register_two()
        con = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "UPDATE coordination_deliveries SET state='ACKED' "
                    "WHERE event_id='evt-1' AND recipient_id='parent'"
                )
        finally:
            con.close()

    def test_input_validation(self) -> None:
        with self.assertRaises(DeliveryError):
            self.store.register(
                event_id="bad ", generation=0, payload={}, recipients=["r"], created_at=1.0
            )
        with self.assertRaises(DeliveryError):
            self.store.register(
                event_id="e", generation=True, payload={}, recipients=["r"], created_at=1.0
            )
        with self.assertRaises(DeliveryError):
            self.store.register(
                event_id="e", generation=0, payload={"x": float("nan")}, recipients=["r"]
            )
        with self.assertRaises(DeliveryError):
            self.store.register(event_id="e", generation=0, payload={}, recipients=[])
        with self.assertRaises(DeliveryError):
            self.store.offer(
                recipient_id="r", generation=0, lease_seconds=0, now=1.0
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
