import unittest

from frankenstein2.gwt_uptake import (
    CellUptakeReceipt,
    CausalProbeArm,
    GWTUptakeError,
    evaluate_causal_influence,
    summarize_uptake,
)
from frankenstein2.gwt_workspace import BroadcastEnvelope

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64


class WP507SelectionLineageFalsifier(unittest.TestCase):
    def test_positive_causal_influence_rejects_direct_unverified_broadcast_envelope(self):
        """A positive causal result must not be mintable from a detached WP506 envelope."""
        broadcast = BroadcastEnvelope(
            broadcast_id="review:detached-broadcast",
            cycle_id="cycle:review-wp507",
            generation=9,
            selection_id="selection:detached",
            selection_generation=9,
            selection_sha256=A,
            plan_id="plan:detached",
            plan_generation=9,
            plan_sha256=B,
            recipient_cell_ids=("G1",),
            candidate_ids=("candidate:detached",),
            candidate_payload_refs=("payload:detached",),
        )

        receipt = CellUptakeReceipt.observe(
            receipt_id="receipt:review-wp507",
            broadcast=broadcast,
            cell_id="G1",
            delivery_status="DELIVERED",
            uptake_status="UPTAKEN",
            downstream_ref="downstream:intervention",
            downstream_sha256=C,
            provenance_refs=("review:receipt",),
        )
        uptake = summarize_uptake(
            summary_id="summary:review-wp507",
            broadcast=broadcast,
            receipts=(receipt,),
            provenance_refs=("review:summary",),
        )
        intervention = CausalProbeArm.intervention(
            arm_id="arm:intervention",
            probe_id="probe:review-wp507",
            broadcast=broadcast,
            nonbroadcast_input_sha256=A,
            downstream_output_sha256=D,
            provenance_refs=("review:intervention",),
        )
        control = CausalProbeArm.control(
            arm_id="arm:control",
            probe_id="probe:review-wp507",
            nonbroadcast_input_sha256=A,
            downstream_output_sha256=E,
            provenance_refs=("review:control",),
        )

        with self.assertRaisesRegex(
            GWTUptakeError,
            r"broadcast.*(builder|lineage|factory)|selection.*lineage",
        ):
            evaluate_causal_influence(
                result_id="result:review-wp507",
                broadcast=broadcast,
                uptake_summary=uptake,
                intervention=intervention,
                control=control,
                provenance_refs=("review:result",),
            )


if __name__ == "__main__":
    unittest.main()
