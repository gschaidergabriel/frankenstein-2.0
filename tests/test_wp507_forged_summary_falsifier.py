from frankenstein2.gwt_uptake import (
    UPTAKE_SUMMARY_SCHEMA,
    CausalProbeArm,
    UptakeSummary,
    evaluate_causal_influence,
)
from frankenstein2.gwt_workspace import BroadcastEnvelope

A64 = "a" * 64
B64 = "b" * 64
C64 = "c" * 64
D64 = "d" * 64


def test_forged_positive_summary_without_receipt_lineage_cannot_mint_causal_credit():
    broadcast = BroadcastEnvelope(
        broadcast_id="broadcast-forged-summary",
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
    forged = UptakeSummary(
        schema=UPTAKE_SUMMARY_SCHEMA,
        summary_id="forged-summary",
        broadcast_id=broadcast.broadcast_id,
        broadcast_sha256=broadcast.sha256(),
        selection_id=broadcast.selection_id,
        plan_id=broadcast.plan_id,
        plan_generation=broadcast.plan_generation,
        plan_sha256=broadcast.plan_sha256,
        recipient_cell_ids=("G1",),
        receipt_ids=("forged-receipt",),
        delivered_cell_ids=("G1",),
        uptaken_cell_ids=("G1",),
        unknown_cell_ids=(),
        status="UPTAKE_OBSERVED",
        provenance_refs=("review-pr-169",),
    )
    intervention = CausalProbeArm.intervention(
        arm_id="intervention",
        broadcast=broadcast,
        nonbroadcast_input_sha256=C64,
        downstream_output_sha256=A64,
        provenance_refs=("review-pr-169",),
    )
    control = CausalProbeArm.control(
        arm_id="control",
        nonbroadcast_input_sha256=C64,
        downstream_output_sha256=D64,
        provenance_refs=("review-pr-169",),
    )
    result = evaluate_causal_influence(
        result_id="result-forged",
        broadcast=broadcast,
        uptake_summary=forged,
        receipts=(),
        intervention=intervention,
        control=control,
        provenance_refs=("review-pr-169",),
    )
    assert result.status == "UNKNOWN_RECEIPT_LINEAGE"
    assert result.status != "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
