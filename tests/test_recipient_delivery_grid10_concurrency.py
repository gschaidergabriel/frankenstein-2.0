from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest

from frankenstein2.recipient_delivery import (
    DeliveryStateError,
    RecipientDeliveryStore,
)


class RecipientDeliveryGrid10ConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.db = Path(self.td.name) / "unified.db"
        self.owner = RecipientDeliveryStore(self.db)
        # Construct stores before contention so the test discriminates delivery locking,
        # not concurrent schema initialization.
        self.stores = [RecipientDeliveryStore(self.db) for _ in range(10)]

    def tearDown(self) -> None:
        self.td.cleanup()

    def concurrent_offer(self, *, recipient: str, generation: int, now: float):
        barrier = threading.Barrier(10)

        def run(store: RecipientDeliveryStore):
            barrier.wait(timeout=5.0)
            return store.offer(
                recipient_id=recipient,
                generation=generation,
                lease_seconds=30.0,
                now=now,
            )

        with ThreadPoolExecutor(max_workers=10) as pool:
            return list(pool.map(run, self.stores))

    def test_grid10_same_recipient_contention_yields_exactly_one_live_offer(self) -> None:
        self.owner.register(
            event_id="evt-grid10-one",
            generation=9,
            payload={"kind": "RESULT", "value": 1},
            recipients=["recipient-A"],
            created_at=1.0,
        )
        results = self.concurrent_offer(recipient="recipient-A", generation=9, now=100.0)
        winners = [batch[0] for batch in results if batch]
        self.assertEqual(len(winners), 1)
        self.assertEqual(sum(len(batch) for batch in results), 1)
        self.assertEqual(winners[0].attempt_count, 1)

        final = self.owner.get(event_id="evt-grid10-one", recipient_id="recipient-A")
        self.assertEqual(final.state, "OFFERED")
        self.assertEqual(final.attempt_count, 1)
        self.assertEqual(final.offer_token, winners[0].offer_token)

    def test_grid10_redelivery_after_expiry_still_has_one_winner_and_one_attempt_increment(self) -> None:
        self.owner.register(
            event_id="evt-grid10-redelivery",
            generation=9,
            payload={"kind": "RESULT", "value": 2},
            recipients=["recipient-A"],
            created_at=1.0,
        )
        first = self.concurrent_offer(recipient="recipient-A", generation=9, now=100.0)
        first_winner = [batch[0] for batch in first if batch][0]

        second = self.concurrent_offer(recipient="recipient-A", generation=9, now=130.0)
        second_winners = [batch[0] for batch in second if batch]
        self.assertEqual(len(second_winners), 1)
        self.assertEqual(second_winners[0].attempt_count, 2)
        self.assertNotEqual(first_winner.offer_token, second_winners[0].offer_token)
        self.assertEqual(
            self.owner.get(
                event_id="evt-grid10-redelivery", recipient_id="recipient-A"
            ).attempt_count,
            2,
        )

    def test_grid10_ack_contention_yields_exactly_one_success(self) -> None:
        self.owner.register(
            event_id="evt-grid10-ack",
            generation=9,
            payload={"kind": "RESULT", "value": 3},
            recipients=["recipient-A"],
            created_at=1.0,
        )
        offered = self.owner.offer(
            recipient_id="recipient-A",
            generation=9,
            lease_seconds=30.0,
            now=100.0,
        )[0]
        token = offered.offer_token or ""
        barrier = threading.Barrier(10)

        def run(store: RecipientDeliveryStore):
            barrier.wait(timeout=5.0)
            try:
                record = store.ack(
                    event_id="evt-grid10-ack",
                    recipient_id="recipient-A",
                    generation=9,
                    offer_token=token,
                    now=101.0,
                )
                return ("ACKED", record.state)
            except DeliveryStateError as exc:
                return ("REJECTED", str(exc))

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(run, self.stores))

        self.assertEqual(sum(1 for kind, _ in results if kind == "ACKED"), 1)
        self.assertEqual(sum(1 for kind, _ in results if kind == "REJECTED"), 9)
        self.assertEqual(
            self.owner.get(event_id="evt-grid10-ack", recipient_id="recipient-A").state,
            "ACKED",
        )

    def test_grid10_independent_recipients_each_receive_their_own_delivery(self) -> None:
        recipients = [f"recipient-{i}" for i in range(10)]
        self.owner.register(
            event_id="evt-grid10-fanout",
            generation=9,
            payload={"kind": "BROADCAST", "value": 4},
            recipients=recipients,
            created_at=1.0,
        )
        barrier = threading.Barrier(10)

        def run(pair):
            store, recipient = pair
            barrier.wait(timeout=5.0)
            return recipient, store.offer(
                recipient_id=recipient,
                generation=9,
                lease_seconds=30.0,
                now=100.0,
            )

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(run, zip(self.stores, recipients)))

        self.assertEqual(len(results), 10)
        for recipient, batch in results:
            self.assertEqual(len(batch), 1)
            self.assertEqual(batch[0].recipient_id, recipient)
            self.assertEqual(batch[0].attempt_count, 1)
        self.assertEqual(
            self.owner.delivery_counts(),
            {"ACKED": 0, "OFFERED": 10, "PENDING": 0},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
