from dataclasses import replace
import unittest

from frankenstein2.grid10_interface import GRID10_CELL_IDS
from frankenstein2.gwt_workspace import BroadcastEnvelope
from frankenstein2.gwt_uptake import (
    CellUptakeReceipt,
    CausalProbeArm,
    GWTUptakeError,
    evaluate_causal_influence,
    summarize_uptake,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64


def broadcast(recipients=GRID10_CELL_IDS, bid="b1"):
    return BroadcastEnvelope(
        broadcast_id=bid, cycle_id="cycle-1", generation=3,
        selection_id="sel-1", selection_generation=2, selection_sha256=A,
        plan_id="plan-1", plan_generation=4, plan_sha256=B,
        recipient_cell_ids=tuple(recipients), candidate_ids=("c1",),
        candidate_payload_refs=("p1",),
    )


def receipt(b, cell, uptake="NOT_UPTAKEN", delivery="DELIVERED"):
    return CellUptakeReceipt.observe(
        receipt_id=f"r-{cell}", broadcast=b, cell_id=cell,
        delivery_status=delivery, uptake_status=uptake,
        downstream_ref=f"d:{cell}" if uptake == "UPTAKEN" else None,
        downstream_sha256=C if uptake == "UPTAKEN" else None,
        provenance_refs=(f"s:{cell}",),
    )


def summary(b, uptaken=None):
    return summarize_uptake(
        summary_id="s1", broadcast=b,
        receipts=tuple(
            receipt(b, cell, "UPTAKEN" if cell == uptaken else "NOT_UPTAKEN")
            for cell in b.recipient_cell_ids
        ),
        provenance_refs=("summary-src",),
    )


def arms(b, same_input=True, same_output=False, probe="probe-1"):
    intervention = CausalProbeArm.intervention(
        arm_id="i", probe_id=probe, broadcast=b,
        nonbroadcast_input_sha256=A, downstream_output_sha256=D,
        provenance_refs=("i-src",),
    )
    control = CausalProbeArm.control(
        arm_id="c", probe_id=probe,
        nonbroadcast_input_sha256=A if same_input else B,
        downstream_output_sha256=D if same_output else E,
        provenance_refs=("c-src",),
    )
    return intervention, control


class GWTUptakeG2Tests(unittest.TestCase):
    def test_receipt_binds_full_broadcast_selection_plan_identity(self):
        b = broadcast(("G1", "G10"))
        observed = receipt(b, "G1", "UPTAKEN")
        self.assertEqual(observed.broadcast_sha256, b.sha256())
        self.assertEqual(observed.cycle_id, b.cycle_id)
        self.assertEqual(observed.broadcast_generation, b.generation)
        self.assertEqual(observed.selection_generation, b.selection_generation)
        self.assertEqual(observed.selection_sha256, b.selection_sha256)
        self.assertEqual(observed.plan_generation, b.plan_generation)
        self.assertEqual(observed.plan_sha256, b.plan_sha256)

    def test_subset_recipient_complete_is_complete_not_unknown(self):
        b = broadcast(("G1",))
        observed = summary(b, "G1")
        self.assertEqual(observed.unknown_cell_ids, ())
        self.assertEqual(observed.uptaken_cell_ids, ("G1",))
        self.assertEqual(observed.status, "UPTAKE_OBSERVED")

    def test_subset_recipient_missing_actual_recipient_is_unknown(self):
        b = broadcast(("G1", "G10"))
        observed = summarize_uptake(
            summary_id="s", broadcast=b, receipts=(receipt(b, "G1"),),
            provenance_refs=("p",),
        )
        self.assertEqual(observed.unknown_cell_ids, ("G10",))
        self.assertEqual(observed.status, "UNKNOWN_INCOMPLETE_RECEIPTS")

    def test_nonrecipient_receipt_fails_closed(self):
        with self.assertRaisesRegex(GWTUptakeError, "recipient"):
            receipt(broadcast(("G1",)), "G2")

    def test_duplicate_cell_receipt_fails_closed(self):
        b = broadcast(("G1",))
        first = receipt(b, "G1")
        with self.assertRaisesRegex(GWTUptakeError, "duplicate logical"):
            summarize_uptake(
                summary_id="s", broadcast=b,
                receipts=(first, replace(first, receipt_id="r2")),
                provenance_refs=("p",),
            )

    def test_direct_receipt_constructor_cannot_be_admitted(self):
        b = broadcast(("G1",))
        forged = replace(receipt(b, "G1"), _factory_seal=None)
        with self.assertRaisesRegex(GWTUptakeError, "observation factory"):
            summarize_uptake(
                summary_id="s", broadcast=b, receipts=(forged,),
                provenance_refs=("p",),
            )

    def test_stale_broadcast_binding_fails_closed(self):
        b = broadcast(("G1",))
        stale = replace(receipt(b, "G1"), selection_sha256=D)
        with self.assertRaisesRegex(GWTUptakeError, "binding mismatch"):
            summarize_uptake(
                summary_id="s", broadcast=b, receipts=(stale,),
                provenance_refs=("p",),
            )

    def test_delivery_without_uptake_is_not_uptake(self):
        b = broadcast(("G1", "G2"))
        observed = summary(b)
        self.assertEqual(observed.status, "NO_UPTAKE_OBSERVED")
        self.assertEqual(observed.delivered_cell_ids, ("G1", "G2"))
        self.assertEqual(observed.uptaken_cell_ids, ())

    def test_not_observed_delivery_forces_unknown(self):
        b = broadcast(("G1",))
        with self.assertRaisesRegex(GWTUptakeError, "must remain UNKNOWN"):
            receipt(b, "G1", "NOT_UPTAKEN", "NOT_OBSERVED")

    def test_non_uptaken_cannot_carry_downstream_evidence(self):
        b = broadcast(("G1",))
        with self.assertRaisesRegex(GWTUptakeError, "must not carry downstream"):
            CellUptakeReceipt.observe(
                receipt_id="r", broadcast=b, cell_id="G1",
                delivery_status="DELIVERED", uptake_status="NOT_UPTAKEN",
                downstream_ref="x", downstream_sha256=C,
                provenance_refs=("p",),
            )

    def test_positive_causal_result_requires_complete_uptake_and_matched_probe(self):
        b = broadcast(("G1", "G10"))
        observed = summary(b, "G10")
        intervention, control = arms(b)
        result = evaluate_causal_influence(
            result_id="res", broadcast=b, uptake_summary=observed,
            intervention=intervention, control=control,
            provenance_refs=("p",),
        )
        self.assertEqual(result.status, "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE")
        self.assertEqual(result.as_dict()["runtime_credit"], 0)

    def test_unmatched_nonbroadcast_input_is_unknown(self):
        b = broadcast(("G1",))
        observed = summary(b, "G1")
        intervention, control = arms(b, same_input=False)
        result = evaluate_causal_influence(
            result_id="r", broadcast=b, uptake_summary=observed,
            intervention=intervention, control=control,
            provenance_refs=("p",),
        )
        self.assertEqual(result.status, "UNKNOWN_UNMATCHED_CONTROL")

    def test_same_downstream_output_is_no_observed_influence(self):
        b = broadcast(("G1",))
        observed = summary(b, "G1")
        intervention, control = arms(b, same_output=True)
        result = evaluate_causal_influence(
            result_id="r", broadcast=b, uptake_summary=observed,
            intervention=intervention, control=control,
            provenance_refs=("p",),
        )
        self.assertEqual(result.status, "NO_CAUSAL_INFLUENCE_OBSERVED")

    def test_different_probe_ids_are_unmatched(self):
        b = broadcast(("G1",))
        observed = summary(b, "G1")
        intervention, _ = arms(b, probe="p1")
        _, control = arms(b, probe="p2")
        result = evaluate_causal_influence(
            result_id="r", broadcast=b, uptake_summary=observed,
            intervention=intervention, control=control,
            provenance_refs=("p",),
        )
        self.assertEqual(result.status, "UNKNOWN_UNMATCHED_CONTROL")

    def test_incomplete_uptake_blocks_causal_positive(self):
        b = broadcast(("G1", "G2"))
        observed = summarize_uptake(
            summary_id="s", broadcast=b,
            receipts=(receipt(b, "G1", "UPTAKEN"),),
            provenance_refs=("p",),
        )
        intervention, control = arms(b)
        result = evaluate_causal_influence(
            result_id="r", broadcast=b, uptake_summary=observed,
            intervention=intervention, control=control,
            provenance_refs=("p",),
        )
        self.assertEqual(result.status, "UNKNOWN_INSUFFICIENT_UPTAKE")

    def test_direct_positive_summary_constructor_bypass_rejected(self):
        b = broadcast(("G1",))
        forged = replace(summary(b, "G1"), _factory_seal=None)
        intervention, control = arms(b)
        with self.assertRaisesRegex(GWTUptakeError, "summarizer"):
            evaluate_causal_influence(
                result_id="r", broadcast=b, uptake_summary=forged,
                intervention=intervention, control=control,
                provenance_refs=("p",),
            )

    def test_summary_source_receipt_tamper_rejected(self):
        b = broadcast(("G1",))
        real = summary(b, "G1")
        forged_receipt = replace(
            real.source_receipts[0], uptake_status="NOT_UPTAKEN",
            downstream_ref=None, downstream_sha256=None,
        )
        forged = replace(real, source_receipts=(forged_receipt,))
        intervention, control = arms(b)
        with self.assertRaisesRegex(GWTUptakeError, "lineage mismatch"):
            evaluate_causal_influence(
                result_id="r", broadcast=b, uptake_summary=forged,
                intervention=intervention, control=control,
                provenance_refs=("p",),
            )

    def test_direct_probe_constructor_bypass_rejected(self):
        b = broadcast(("G1",))
        observed = summary(b, "G1")
        intervention, control = arms(b)
        forged = replace(intervention, _factory_seal=None)
        with self.assertRaisesRegex(GWTUptakeError, "arm factory"):
            evaluate_causal_influence(
                result_id="r", broadcast=b, uptake_summary=observed,
                intervention=forged, control=control,
                provenance_refs=("p",),
            )


if __name__ == "__main__":
    unittest.main()
