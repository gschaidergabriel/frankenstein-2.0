from __future__ import annotations

from dataclasses import replace

import pytest

from frankenstein2.grid10_interface import GRID10_CELL_IDS
from frankenstein2.gwt_uptake import (
    CAUSAL_INFLUENCE_RESULT_SCHEMA,
    UPTAKE_SUMMARY_SCHEMA,
    CausalProbeArm,
    CellUptakeReceipt,
    GWTUptakeError,
    UptakeSummary,
    evaluate_causal_influence,
    summarize_uptake,
)
from frankenstein2.gwt_workspace import BroadcastEnvelope

A64 = "a" * 64
B64 = "b" * 64
C64 = "c" * 64
D64 = "d" * 64
E64 = "e" * 64


def make_broadcast(
    *,
    broadcast_id: str = "broadcast-1",
    recipients: tuple[str, ...] = GRID10_CELL_IDS,
) -> BroadcastEnvelope:
    return BroadcastEnvelope(
        broadcast_id=broadcast_id,
        cycle_id="cycle-1",
        generation=4,
        selection_id="selection-1",
        selection_generation=3,
        selection_sha256=A64,
        plan_id="plan-1",
        plan_generation=2,
        plan_sha256=B64,
        recipient_cell_ids=recipients,
        candidate_ids=("candidate-1",),
        candidate_payload_refs=("payload:1",),
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
        for cell_id in broadcast.recipient_cell_ids
    )


def arms(broadcast: BroadcastEnvelope, *, matched: bool = True, changed: bool = True):
    intervention = CausalProbeArm.intervention(
        arm_id="intervention",
        broadcast=broadcast,
        nonbroadcast_input_sha256=A64,
        downstream_output_sha256=D64,
        provenance_refs=("intervention-source",),
    )
    control = CausalProbeArm.control(
        arm_id="control",
        nonbroadcast_input_sha256=A64 if matched else B64,
        downstream_output_sha256=E64 if changed else D64,
        provenance_refs=("control-source",),
    )
    return intervention, control


def evaluate(
    broadcast: BroadcastEnvelope,
    summary: UptakeSummary,
    receipts: tuple[CellUptakeReceipt, ...],
    *,
    matched: bool = True,
    changed: bool = True,
):
    intervention, control = arms(broadcast, matched=matched, changed=changed)
    return evaluate_causal_influence(
        result_id="result-1",
        broadcast=broadcast,
        uptake_summary=summary,
        receipts=receipts,
        intervention=intervention,
        control=control,
        provenance_refs=("probe-source",),
    )


def test_receipt_binds_exact_broadcast_selection_and_plan():
    broadcast = make_broadcast()
    observed = receipt(broadcast, "G1", uptake="UPTAKEN")
    assert observed.broadcast_id == broadcast.broadcast_id
    assert observed.broadcast_sha256 == broadcast.sha256()
    assert observed.selection_id == broadcast.selection_id
    assert observed.plan_id == broadcast.plan_id
    assert observed.plan_generation == broadcast.plan_generation
    assert observed.plan_sha256 == broadcast.plan_sha256
    assert "NOT_RUNTIME_ATTESTATION" in observed.classification


def test_nonrecipient_cell_fails_closed():
    broadcast = make_broadcast(recipients=("G1",))
    with pytest.raises(GWTUptakeError, match="recipient"):
        receipt(broadcast, "G2")


def test_delivery_not_observed_forces_unknown_uptake():
    with pytest.raises(GWTUptakeError, match="must remain UNKNOWN"):
        receipt(
            make_broadcast(),
            "G1",
            delivery="NOT_OBSERVED",
            uptake="NOT_UPTAKEN",
        )


def test_uptaken_requires_downstream_evidence():
    with pytest.raises(GWTUptakeError, match="requires explicit downstream evidence"):
        CellUptakeReceipt.observe(
            receipt_id="receipt-g1",
            broadcast=make_broadcast(),
            cell_id="G1",
            delivery_status="DELIVERED",
            uptake_status="UPTAKEN",
            provenance_refs=("source",),
        )


def test_stale_broadcast_digest_fails_closed():
    broadcast = make_broadcast()
    observed = receipt(broadcast, "G1")
    stale = replace(observed, broadcast_sha256=D64)
    with pytest.raises(GWTUptakeError, match="binding mismatch"):
        stale.assert_broadcast_binding(broadcast)


def test_partial_recipient_receipts_are_unknown_not_no_uptake():
    broadcast = make_broadcast(recipients=("G1", "G2"))
    summary = summarize_uptake(
        summary_id="summary-partial",
        broadcast=broadcast,
        receipts=(receipt(broadcast, "G1"),),
        provenance_refs=("summary-source",),
    )
    assert summary.status == "UNKNOWN_INCOMPLETE_RECEIPTS"
    assert summary.unknown_cell_ids == ("G2",)


def test_duplicate_logical_cell_receipt_fails_closed():
    broadcast = make_broadcast()
    first = receipt(broadcast, "G1")
    second = replace(first, receipt_id="receipt-g1-second")
    with pytest.raises(GWTUptakeError, match="duplicate logical cell receipt"):
        summarize_uptake(
            summary_id="summary-dup",
            broadcast=broadcast,
            receipts=(first, second),
            provenance_refs=("summary-source",),
        )


def test_delivery_without_semantic_uptake_is_not_uptake():
    broadcast = make_broadcast()
    receipts = complete_receipts(broadcast)
    summary = summarize_uptake(
        summary_id="summary-no-uptake",
        broadcast=broadcast,
        receipts=receipts,
        provenance_refs=("summary-source",),
    )
    assert summary.status == "NO_UPTAKE_OBSERVED"
    assert summary.delivered_cell_ids == GRID10_CELL_IDS
    assert summary.uptaken_cell_ids == ()
    assert summary.unknown_cell_ids == ()


def test_complete_receipts_with_one_uptake_measure_uptake():
    broadcast = make_broadcast()
    receipts = complete_receipts(broadcast, uptaken_cell="G7")
    summary = summarize_uptake(
        summary_id="summary-uptake",
        broadcast=broadcast,
        receipts=receipts,
        provenance_refs=("summary-source",),
    )
    assert summary.status == "UPTAKE_OBSERVED"
    assert summary.uptaken_cell_ids == ("G7",)
    assert summary.unknown_cell_ids == ()


def test_recipient_order_is_grid10_canonical_not_lexical():
    broadcast = make_broadcast(recipients=("G10", "G2", "G1"))
    receipts = (
        receipt(broadcast, "G10"),
        receipt(broadcast, "G1"),
        receipt(broadcast, "G2", uptake="UPTAKEN"),
    )
    summary = summarize_uptake(
        summary_id="summary-order",
        broadcast=broadcast,
        receipts=receipts,
        provenance_refs=("summary-source",),
    )
    assert summary.recipient_cell_ids == ("G1", "G2", "G10")
    assert summary.delivered_cell_ids == ("G1", "G2", "G10")
    assert summary.uptaken_cell_ids == ("G2",)


def test_unmatched_control_yields_unknown_not_causal_credit():
    broadcast = make_broadcast()
    receipts = complete_receipts(broadcast, uptaken_cell="G1")
    summary = summarize_uptake(
        summary_id="summary-uptake",
        broadcast=broadcast,
        receipts=receipts,
        provenance_refs=("summary-source",),
    )
    result = evaluate(broadcast, summary, receipts, matched=False)
    assert result.status == "UNKNOWN_UNMATCHED_CONTROL"


def test_same_output_is_no_observed_causal_influence():
    broadcast = make_broadcast()
    receipts = complete_receipts(broadcast, uptaken_cell="G1")
    summary = summarize_uptake(
        summary_id="summary-uptake",
        broadcast=broadcast,
        receipts=receipts,
        provenance_refs=("summary-source",),
    )
    result = evaluate(broadcast, summary, receipts, changed=False)
    assert result.status == "NO_CAUSAL_INFLUENCE_OBSERVED"


def test_matched_changed_output_is_contract_scope_causal_influence():
    broadcast = make_broadcast()
    receipts = complete_receipts(broadcast, uptaken_cell="G3")
    summary = summarize_uptake(
        summary_id="summary-uptake",
        broadcast=broadcast,
        receipts=receipts,
        provenance_refs=("summary-source",),
    )
    result = evaluate(broadcast, summary, receipts)
    assert result.schema == CAUSAL_INFLUENCE_RESULT_SCHEMA
    assert result.status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    assert len(result.receipt_lineage_sha256) == 64
    assert "NOT_RUNTIME_CAUSALITY" in result.classification


def test_incomplete_uptake_blocks_positive_causal_result():
    broadcast = make_broadcast(recipients=("G1", "G2"))
    receipts = (receipt(broadcast, "G1", uptake="UPTAKEN"),)
    summary = summarize_uptake(
        summary_id="summary-partial",
        broadcast=broadcast,
        receipts=receipts,
        provenance_refs=("summary-source",),
    )
    result = evaluate(broadcast, summary, receipts)
    assert result.status == "UNKNOWN_INSUFFICIENT_UPTAKE"


def test_wrong_intervention_broadcast_binding_fails_closed():
    broadcast = make_broadcast()
    other = make_broadcast(broadcast_id="broadcast-2")
    receipts = complete_receipts(broadcast, uptaken_cell="G1")
    summary = summarize_uptake(
        summary_id="summary-uptake",
        broadcast=broadcast,
        receipts=receipts,
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
    with pytest.raises(GWTUptakeError, match="intervention broadcast binding mismatch"):
        evaluate_causal_influence(
            result_id="result-wrong-broadcast",
            broadcast=broadcast,
            uptake_summary=summary,
            receipts=receipts,
            intervention=intervention,
            control=control,
            provenance_refs=("probe-source",),
        )


def test_summary_constructor_cannot_change_recipient_set_to_nonrecipient():
    broadcast = make_broadcast(recipients=("G1",))
    summary = summarize_uptake(
        summary_id="summary",
        broadcast=broadcast,
        receipts=(receipt(broadcast, "G1"),),
        provenance_refs=("summary-source",),
    )
    forged = replace(summary, recipient_cell_ids=("G1", "G2"))
    intervention, control = arms(broadcast)
    with pytest.raises(GWTUptakeError, match="summary broadcast/selection/GRID10 binding mismatch"):
        evaluate_causal_influence(
            result_id="result",
            broadcast=broadcast,
            uptake_summary=forged,
            receipts=(receipt(broadcast, "G1"),),
            intervention=intervention,
            control=control,
            provenance_refs=("probe-source",),
        )
