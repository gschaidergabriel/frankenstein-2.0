"""Persistent regression for F2-WP-507 generation 3 OFFERED state.

The active G3 contract requires the uptake contract to distinguish OFFERED from DELIVERED
from semantic UPTAKEN. This regression preserves the hosted falsifier that exposed the
missing OFFERED state: an observed offer must be representable while uptake stays UNKNOWN
and no downstream evidence is minted.

This is deterministic repository component evidence only. It does not assert runtime/GWT
causal credit, truth authority, effect authority, completion, training, or whole-system credit.
"""
from __future__ import annotations

import unittest

from frankenstein2.gwt_uptake import CellUptakeReceipt
from frankenstein2.gwt_workspace import BroadcastEnvelope

A = "a" * 64
B = "b" * 64


def broadcast() -> BroadcastEnvelope:
    return BroadcastEnvelope(
        broadcast_id="review-broadcast-1",
        cycle_id="review-cycle-1",
        generation=3,
        selection_id="review-selection-1",
        selection_generation=2,
        selection_sha256=A,
        plan_id="review-plan-1",
        plan_generation=4,
        plan_sha256=B,
        recipient_cell_ids=("G1",),
        candidate_ids=("candidate-1",),
        candidate_payload_refs=("payload-1",),
    )


class WP507G3OfferedStateFalsifier(unittest.TestCase):
    def test_offered_is_representable_without_claiming_delivery_or_uptake(self) -> None:
        observed = CellUptakeReceipt.observe(
            receipt_id="review-offered-receipt-1",
            broadcast=broadcast(),
            cell_id="G1",
            delivery_status="OFFERED",
            uptake_status="UNKNOWN",
            provenance_refs=("review:wp507-g3-offered-state",),
        )
        self.assertEqual(observed.delivery_status, "OFFERED")
        self.assertEqual(observed.uptake_status, "UNKNOWN")
        self.assertIsNone(observed.downstream_ref)
        self.assertIsNone(observed.downstream_sha256)


if __name__ == "__main__":
    unittest.main()
