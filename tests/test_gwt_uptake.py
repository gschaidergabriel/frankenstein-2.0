from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.grid10_interface import GRID10_CELL_IDS
from frankenstein2.gwt_uptake import (
    CausalProbeArm,
    CellUptakeReceipt,
    GWTUptakeError,
    evaluate_causal_influence,
    summarize_uptake,
)
from frankenstein2.gwt_workspace import BROADCAST_ENVELOPE_SCHEMA, BroadcastEnvelope


A64 = "a" * 64
B64 = "b" * 64
C64 = "c" * 64
D64 = "d" * 64
E64 = "e" * 64


def make_broadcast(*, broadcast_id: str = "broadcast-1") -> BroadcastEnvelope:
    return BroadcastEnvelope(
        schema=BROADCAST_ENVELOPE_SCHEMA,
        broadcast_id=broadcast_id,
        selection_id="selection-1",
        selection_sha256=A64,
        plan_id="plan-1",
        plan_generation=2,
        plan_sha256=B64,
        recipient_cell_ids=GRID10_CELL_IDS,
        provenance_refs=("broadcast-source",),
    )


def receipt(
    broadcast: BroadcastEnvelope,
    cell_id: str,
    *,
    delivery: str = "DELIVERED",
    uptake: str = "NOT_UPTAKEN",
) -> CellUptakeReceipt:
    return CellUptakeReceipt.observe(
        receipt_id=f"receipt-{cell_id}",
        broadcast=broadcast,
        cell_id=cell_id,
        delivery_status=delivery,
        uptake_status=uptake,
        downstream_ref=f"downstream:{cell_id}" if uptake == "UPTAKEN" else None,
        downstream_sha256=C64 if uptake == "UPTAKEN" else None,
        provenance_refs=(f"receipt-source:{cell_id}",),
    )


def complete_receipts(
    broadcast: BroadcastEnvelope,
    *,
    uptaken_cell: str | None = None,
) -> tuple[CellUptakeReceipt, ...]:
    return tuple(
        receipt(
            broadcast,
            cell_id,
            uptake="UPTAKEN" if cell_id == uptaken_cell else "NOT_UPTAKEN",
        )
        for cell_id in GRID10_CELL_IDS
    )


class GWTUptakeTests(unittest.TestCase):
    def test_receipt_binds_exact_broadcast_selection_and_plan(self) -> None:
        broadcast = make_broadcast()
        observed = receipt(broadcast, "G1", uptake="UPTAKEN")
        self.assertEqual(observed.broadcast_id, broadcast.broadcast_id)
        self.assertEqual(observed.broadcast_sha256, broadcast.sha256())
        self.assertEqual(observed.selection_id, broadcast.selection_id)
        self.assertEqual(observed.plan_id, broadcast.plan_id)
        self.assertEqual(observed.plan_generation, broadcast.plan_generation)
        self.assertEqual(observed.plan_sha256, broadcast.plan_sha256)
        self.assertEqual(observed.classification, "OBSERVED_UPTAKE_EVIDENCE_NOT_HIDDEN_STATE_OR_TRUTH_AUTHORITY")

    def test_nonrecipient_cell_fails_closed(self) -> None:
        with self.assertRaisesRegex(GWTUptakeError, "logical GRID10|recipient"):
            CellUptakeReceipt.observe(
                receipt_id="receipt-g11",
                broadcast=make_broadcast(),
                cell_id="G11",
                delivery_status="DELIVERED",
                uptake_status="NOT_UPTAKEN",
                provenance_refs=("source",),
            )

    def test_delivery_not_observed_forces_unknown_uptake(self) -> None:
        with self.assertRaisesRegex(GWTUptakeError, "must remain UNKNOWN"):
            receipt(make_broadcast(), "G1", delivery="NOT_OBSERVED", uptake="NOT_UPTAKEN")

    def test_uptaken_requires_downstream_evidence(self) -> None:
        with self.assertRaisesRegex(GWTUptakeError, "requires explicit downstream evidence"):
            CellUptakeReceipt.observe(
                receipt_id="receipt-g1",
                broadcast=make_broadcast(),
                cell_id="G1",
                delivery_status="DELIVERED",
                uptake_status="UPTAKEN",
                provenance_refs=("source",),
            )

    def test_stale_broadcast_digest_fails_closed(self) -> None:
        broadcast = make_broadcast()
        observed = receipt(broadcast, "G1")
        stale = replace(observed, broadcast_sha256=D64)
        with self.assertRaisesRegex(GWTUptakeError, "binding mismatch"):
            stale.assert_broadcast_binding(broadcast)

    def test_partial_receipts_are_unknown_not_no_uptake(self) -> None:
        broadcast = make_broadcast()
        summary = summarize_uptake(
            summary_id="summary-partial",
            broadcast=broadcast,
            receipts=(receipt(broadcast, "G1"),),
            provenance_refs=("summary-source",),
        )
        self.assertEqual(summary.status, "UNKNOWN_INCOMPLETE_RECEIPTS")
        self.assertIn("G2", summary.unknown_cell_ids)

    def test_duplicate_logical_cell_receipt_fails_closed(self) -> None:
        broadcast = make_broadcast()
        first = receipt(broadcast, "G1")
        second = replace(first, receipt_id="receipt-g1-second")
        with self.assertRaisesRegex(GWTUptakeError, "duplicate logical cell receipt"):
            summarize_uptake(
                summary_id="summary-dup",
                broadcast=broadcast,
                receipts=(first, second),
                provenance_refs=("summary-source",),
            )

    def test_delivery_without_semantic_uptake_is_not_uptake(self) -> None:
        broadcast = make_broadcast()
        summary = summarize_uptake(
            summary_id="summary-no-uptake",
            broadcast=broadcast,
            receipts=complete_receipts(broadcast),
            provenance_refs=("summary-source",),
        )
        self.assertEqual(summary.status, "NO_UPTAKE_OBSERVED")
        self.assertEqual(summary.delivered_cell_ids, GRID10_CELL_IDS)
        self.assertEqual(summary.uptaken_cell_ids, ())
        self.assertEqual(summary.unknown_cell_ids, ())

    def test_complete_receipts_with_one_uptake_measure_uptake(self) -> None:
        broadcast = make_broadcast()
        summary = summarize_uptake(
            summary_id="summary-uptake",
            broadcast=broadcast,
            receipts=complete_receipts(broadcast, uptaken_cell="G7"),
            provenance_refs=("summary-source",),
        )
        self.assertEqual(summary.status, "UPTAKE_OBSERVED")
        self.assertEqual(summary.uptaken_cell_ids, ("G7",))
        self.assertEqual(summary.unknown_cell_ids, ())

    def test_unmatched_control_yields_unknown_not_causal_credit(self) -> None:
        broadcast = make_broadcast()
        summary = summarize_uptake(
            summary_id="summary-uptake",
            broadcast=broadcast,
            receipts=complete_receipts(broadcast, uptaken_cell="G1"),
            provenance_refs=("summary-source",),
        )
        intervention = CausalProbeArm.intervention(
            arm_id="intervention",
            broadcast=broadcast,
            nonbroadcast_input_sha256=A64,
            downstream_output_sha256=D64,
            provenance_refs=("intervention-source",),
        )
        control = CausalProbeArm.control(
            arm_id="control",
            nonbroadcast_input_sha256=B64,
            downstream_output_sha256=E64,
            provenance_refs=("control-source",),
        )
        result = evaluate_causal_influence(
            result_id="result-unmatched",
            broadcast=broadcast,
            uptake_summary=summary,
            intervention=intervention,
            control=control,
            provenance_refs=("probe-source",),
        )
        self.assertEqual(result.status, "UNKNOWN_UNMATCHED_CONTROL")

    def test_same_output_is_no_observed_causal_influence(self) -> None:
        broadcast = make_broadcast()
        summary = summarize_uptake(
            summary_id="summary-uptake",
            broadcast=broadcast,
            receipts=complete_receipts(broadcast, uptaken_cell="G1"),
            provenance_refs=("summary-source",),
        )
        intervention = CausalProbeArm.intervention(
            arm_id="intervention",
            broadcast=broadcast,
            nonbroadcast_input_sha256=A64,
            downstream_output_sha256=D64,
            provenance_refs=("intervention-source",),
        )
        control = CausalProbeArm.control(
            arm_id="control",
            nonbroadcast_input_sha256=A64,
            downstream_output_sha256=D64,
            provenance_refs=("control-source",),
        )
        result = evaluate_causal_influence(
            result_id="result-same",
            broadcast=broadcast,
            uptake_summary=summary,
            intervention=intervention,
            control=control,
            provenance_refs=("probe-source",),
        )
        self.assertEqual(result.status, "NO_CAUSAL_INFLUENCE_OBSERVED")

    def test_matched_changed_output_is_contract_scope_causal_influence(self) -> None:
        broadcast = make_broadcast()
        summary = summarize_uptake(
            summary_id="summary-uptake",
            broadcast=broadcast,
            receipts=complete_receipts(broadcast, uptaken_cell="G3"),
            provenance_refs=("summary-source",),
        )
        intervention = CausalProbeArm.intervention(
            arm_id="intervention",
            broadcast=broadcast,
            nonbroadcast_input_sha256=A64,
            downstream_output_sha256=D64,
            provenance_refs=("intervention-source",),
        )
        control = CausalProbeArm.control(
            arm_id="control",
            nonbroadcast_input_sha256=A64,
            downstream_output_sha256=E64,
            provenance_refs=("control-source",),
        )
        result = evaluate_causal_influence(
            result_id="result-positive",
            broadcast=broadcast,
            uptake_summary=summary,
            intervention=intervention,
            control=control,
            provenance_refs=("probe-source",),
        )
        self.assertEqual(result.status, "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE")
        self.assertIn("NOT_HIDDEN_STATE", result.classification)

    def test_incomplete_uptake_blocks_positive_causal_result(self) -> None:
        broadcast = make_broadcast()
        summary = summarize_uptake(
            summary_id="summary-partial",
            broadcast=broadcast,
            receipts=(receipt(broadcast, "G1", uptake="UPTAKEN"),),
            provenance_refs=("summary-source",),
        )
        intervention = CausalProbeArm.intervention(
            arm_id="intervention",
            broadcast=broadcast,
            nonbroadcast_input_sha256=A64,
            downstream_output_sha256=D64,
            provenance_refs=("intervention-source",),
        )
        control = CausalProbeArm.control(
            arm_id="control",
            nonbroadcast_input_sha256=A64,
            downstream_output_sha256=E64,
            provenance_refs=("control-source",),
        )
        result = evaluate_causal_influence(
            result_id="result-incomplete",
            broadcast=broadcast,
            uptake_summary=summary,
            intervention=intervention,
            control=control,
            provenance_refs=("probe-source",),
        )
        self.assertEqual(result.status, "UNKNOWN_INSUFFICIENT_UPTAKE")

    def test_wrong_intervention_broadcast_binding_fails_closed(self) -> None:
        broadcast = make_broadcast()
        other = make_broadcast(broadcast_id="broadcast-2")
        summary = summarize_uptake(
            summary_id="summary-uptake",
            broadcast=broadcast,
            receipts=complete_receipts(broadcast, uptaken_cell="G1"),
            provenance_refs=("summary-source",),
        )
        intervention = CausalProbeArm.intervention(
            arm_id="intervention",
            broadcast=other,
            nonbroadcast_input_sha256=A64,
            downstream_output_sha256=D64,
            provenance_refs=("intervention-source",),
        )
        control = CausalProbeArm.control(
            arm_id="control",
            nonbroadcast_input_sha256=A64,
            downstream_output_sha256=E64,
            provenance_refs=("control-source",),
        )
        with self.assertRaisesRegex(GWTUptakeError, "intervention broadcast binding mismatch"):
            evaluate_causal_influence(
                result_id="result-wrong-broadcast",
                broadcast=broadcast,
                uptake_summary=summary,
                intervention=intervention,
                control=control,
                provenance_refs=("probe-source",),
            )


if __name__ == "__main__":
    unittest.main()
