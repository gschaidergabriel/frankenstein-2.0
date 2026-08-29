from __future__ import annotations

import unittest

from frankenstein2.gwt_uptake import CellUptakeReceipt, summarize_uptake
from frankenstein2.gwt_workspace import BROADCAST_ENVELOPE_SCHEMA, BroadcastEnvelope

A64 = "a" * 64
B64 = "b" * 64
C64 = "c" * 64


class WP507SubsetRecipientFalsifier(unittest.TestCase):
    def test_complete_single_recipient_broadcast_can_observe_uptake(self) -> None:
        broadcast = BroadcastEnvelope(
            schema=BROADCAST_ENVELOPE_SCHEMA,
            broadcast_id="broadcast-single-recipient",
            selection_id="selection-1",
            selection_sha256=A64,
            plan_id="plan-1",
            plan_generation=2,
            plan_sha256=B64,
            recipient_cell_ids=("G1",),
            provenance_refs=("broadcast-source",),
        )
        observed = CellUptakeReceipt.observe(
            receipt_id="receipt-g1",
            broadcast=broadcast,
            cell_id="G1",
            delivery_status="DELIVERED",
            uptake_status="UPTAKEN",
            downstream_ref="downstream:G1",
            downstream_sha256=C64,
            provenance_refs=("receipt-source:G1",),
        )
        summary = summarize_uptake(
            summary_id="summary-single-recipient",
            broadcast=broadcast,
            receipts=(observed,),
            provenance_refs=("summary-source",),
        )

        self.assertEqual(summary.unknown_cell_ids, ())
        self.assertEqual(summary.uptaken_cell_ids, ("G1",))
        self.assertEqual(summary.status, "UPTAKE_OBSERVED")


if __name__ == "__main__":
    unittest.main()
