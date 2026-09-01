from dataclasses import replace

import pytest

from frankenstein2.gwt_uptake import (
    CellUptakeReceipt,
    GWTUptakeError,
    summarize_uptake,
)
from frankenstein2.gwt_workspace import BroadcastEnvelope

A = "a" * 64
B = "b" * 64
C = "c" * 64


def _broadcast() -> BroadcastEnvelope:
    return BroadcastEnvelope(
        broadcast_id="review:wp507:replace-seal",
        cycle_id="cycle:review",
        generation=1,
        selection_id="selection:review",
        selection_generation=1,
        selection_sha256=A,
        plan_id="plan:review",
        plan_generation=1,
        plan_sha256=B,
        recipient_cell_ids=("G1",),
        candidate_ids=("candidate:review",),
        candidate_payload_refs=("payload:review",),
    )


def test_replace_must_not_preserve_observation_authority_when_uptake_semantics_change():
    """REVIEW_ONLY falsifier for the accepted WP507 G4 observation boundary.

    A factory-produced NOT_UPTAKEN receipt is semantically mutated to UPTAKEN.  The
    downstream boundary must reject that mutation rather than accepting a copied private
    factory seal as fresh observation authority.
    """
    broadcast = _broadcast()
    observed_not_uptaken = CellUptakeReceipt.observe(
        receipt_id="receipt:review",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="NOT_UPTAKEN",
        downstream_ref=None,
        downstream_sha256=None,
        provenance_refs=("review:original-observation",),
    )

    forged = replace(
        observed_not_uptaken,
        uptake_status="UPTAKEN",
        downstream_ref="forged:downstream",
        downstream_sha256=C,
    )

    # dataclasses.replace currently copies init=True fields, including the private seal.
    assert forged._factory_seal is observed_not_uptaken._factory_seal

    with pytest.raises(GWTUptakeError):
        summarize_uptake(
            summary_id="summary:review",
            broadcast=broadcast,
            receipts=(forged,),
            provenance_refs=("review:summary",),
        )
