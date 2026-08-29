from frankenstein2.gwt_uptake import CellUptakeReceipt, summarize_uptake
from frankenstein2.gwt_workspace import BroadcastEnvelope

A64 = "a" * 64
B64 = "b" * 64
C64 = "c" * 64


def test_subset_recipient_complete_uptake_is_not_blocked_by_nonrecipients():
    broadcast = BroadcastEnvelope(
        broadcast_id="broadcast-subset",
        cycle_id="cycle-1",
        generation=1,
        selection_id="selection-1",
        selection_generation=1,
        selection_sha256=A64,
        plan_id="plan-1",
        plan_generation=1,
        plan_sha256=B64,
        recipient_cell_ids=("G1",),
        candidate_ids=("candidate-1",),
        candidate_payload_refs=("payload:1",),
    )
    observed = CellUptakeReceipt.observe(
        receipt_id="receipt-g1",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:g1",
        downstream_sha256=C64,
        provenance_refs=("review-pr-172",),
    )
    summary = summarize_uptake(
        summary_id="summary-subset",
        broadcast=broadcast,
        receipts=(observed,),
        provenance_refs=("review-pr-172",),
    )
    assert summary.recipient_cell_ids == ("G1",)
    assert summary.unknown_cell_ids == ()
    assert summary.uptaken_cell_ids == ("G1",)
    assert summary.status == "UPTAKE_OBSERVED"
