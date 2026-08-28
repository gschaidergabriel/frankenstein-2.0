#!/usr/bin/env python3
from dataclasses import replace
import importlib.util
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("delivery_lifecycle", ROOT / "src" / "state" / "delivery_lifecycle.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

DeliveryLifecycleError = MODULE.DeliveryLifecycleError
DeliveryOperation = MODULE.DeliveryOperation
DeliveryState = MODULE.DeliveryState
DeliveryTransition = MODULE.DeliveryTransition
RecipientDelivery = MODULE.RecipientDelivery
apply_delivery_transition = MODULE.apply_delivery_transition
derive_delivery_id = MODULE.derive_delivery_id


class DeliveryLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.record = RecipientDelivery.pending(
            causal_event_id="causal:event-1",
            recipient_id="recipient:alpha",
            generation=7,
        )

    def transition(self, transition_id, operation, attempt="attempt:1", **overrides):
        values = dict(
            transition_id=transition_id,
            delivery_id=self.record.delivery_id,
            causal_event_id=self.record.causal_event_id,
            recipient_id=self.record.recipient_id,
            generation=self.record.generation,
            operation=operation,
            transport_attempt_id=attempt,
        )
        values.update(overrides)
        return DeliveryTransition(**values)

    def test_stable_delivery_identity_is_recipient_scoped(self):
        same = derive_delivery_id("causal:event-1", "recipient:alpha")
        other_recipient = derive_delivery_id("causal:event-1", "recipient:beta")
        self.assertEqual(self.record.delivery_id, same)
        self.assertNotEqual(same, other_recipient)

    def test_offer_then_ack_is_monotone_and_attempt_bound(self):
        offered = apply_delivery_transition(
            self.record, self.transition("transition:offer-1", DeliveryOperation.OFFER)
        )
        self.assertEqual(offered.state, DeliveryState.OFFERED)
        ack = replace(
            self.transition("transition:ack-1", DeliveryOperation.ACK),
            delivery_id=offered.delivery_id,
        )
        acked = apply_delivery_transition(offered, ack)
        self.assertEqual(acked.state, DeliveryState.ACKED)
        self.assertEqual(acked.acknowledged_attempt_id, "attempt:1")

    def test_exact_transition_replay_is_idempotent(self):
        offer = self.transition("transition:offer-1", DeliveryOperation.OFFER)
        once = apply_delivery_transition(self.record, offer)
        twice = apply_delivery_transition(once, offer)
        self.assertIs(twice, once)
        self.assertEqual(twice.transport_attempt_ids, ("attempt:1",))

    def test_retry_is_new_attempt_same_delivery(self):
        first = apply_delivery_transition(
            self.record, self.transition("transition:offer-1", DeliveryOperation.OFFER)
        )
        retry = replace(
            self.transition("transition:offer-2", DeliveryOperation.OFFER, attempt="attempt:2"),
            delivery_id=first.delivery_id,
        )
        second = apply_delivery_transition(first, retry)
        self.assertEqual(second.delivery_id, first.delivery_id)
        self.assertEqual(second.state, DeliveryState.OFFERED)
        self.assertEqual(second.transport_attempt_ids, ("attempt:1", "attempt:2"))

    def test_same_attempt_new_transition_fails_closed(self):
        first = apply_delivery_transition(
            self.record, self.transition("transition:offer-1", DeliveryOperation.OFFER)
        )
        replay_with_changed_transition = replace(
            self.transition("transition:offer-X", DeliveryOperation.OFFER),
            delivery_id=first.delivery_id,
        )
        with self.assertRaisesRegex(DeliveryLifecycleError, "TRANSPORT_ATTEMPT_REUSED"):
            apply_delivery_transition(first, replay_with_changed_transition)

    def test_ack_before_offer_and_unknown_attempt_fail_closed(self):
        with self.assertRaisesRegex(DeliveryLifecycleError, "ACK_BEFORE_OFFER"):
            apply_delivery_transition(
                self.record, self.transition("transition:ack-early", DeliveryOperation.ACK)
            )
        offered = apply_delivery_transition(
            self.record, self.transition("transition:offer-1", DeliveryOperation.OFFER)
        )
        bad_ack = replace(
            self.transition("transition:ack-X", DeliveryOperation.ACK, attempt="attempt:other"),
            delivery_id=offered.delivery_id,
        )
        with self.assertRaisesRegex(DeliveryLifecycleError, "ACK_UNKNOWN_TRANSPORT_ATTEMPT"):
            apply_delivery_transition(offered, bad_ack)

    def test_stale_generation_and_identity_mixups_fail_closed(self):
        cases = [
            ("generation", 6, "STALE_GENERATION"),
            ("delivery_id", "delivery:wrong", "DELIVERY_ID_MISMATCH"),
            ("causal_event_id", "causal:other", "CAUSAL_EVENT_ID_MISMATCH"),
            ("recipient_id", "recipient:other", "RECIPIENT_ID_MISMATCH"),
        ]
        base = self.transition("transition:offer-1", DeliveryOperation.OFFER)
        for field, value, message in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(DeliveryLifecycleError, message):
                    apply_delivery_transition(self.record, replace(base, **{field: value}))

    def test_no_offer_after_ack_and_no_second_new_ack(self):
        offered = apply_delivery_transition(
            self.record, self.transition("transition:offer-1", DeliveryOperation.OFFER)
        )
        ack = replace(
            self.transition("transition:ack-1", DeliveryOperation.ACK),
            delivery_id=offered.delivery_id,
        )
        acked = apply_delivery_transition(offered, ack)
        with self.assertRaisesRegex(DeliveryLifecycleError, "OFFER_AFTER_ACK"):
            apply_delivery_transition(
                acked,
                replace(
                    self.transition("transition:offer-2", DeliveryOperation.OFFER, attempt="attempt:2"),
                    delivery_id=acked.delivery_id,
                ),
            )
        with self.assertRaisesRegex(DeliveryLifecycleError, "SECOND_ACK"):
            apply_delivery_transition(
                acked,
                replace(
                    self.transition("transition:ack-2", DeliveryOperation.ACK),
                    delivery_id=acked.delivery_id,
                ),
            )


if __name__ == "__main__":
    unittest.main()
