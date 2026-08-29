"""REVIEW_ONLY / CANDIDATE_FALSIFIER for F2-WP-510.

This test intentionally does not modify WP510-owned implementation.  It demonstrates
that the accepted bounded WP508 binding can preserve an arbitrary caller-supplied
WP507 downstream artifact reference/digest while all broadcast, recipient and re-entry
identities are otherwise exact.  That behavior is valid at the existing WP507/WP508
component scopes; WP510's broader causal-path seal is the place to decide whether an
exact typed downstream lineage object is required.
"""
from pathlib import Path
import sys

# Reuse the accepted WP508 fixture without copying a second test implementation.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gwt_reentry_uptake_binding import bind, make_fixture  # noqa: E402

from frankenstein2.gwt_uptake import CellUptakeReceipt  # noqa: E402


def test_wp508_component_binding_preserves_unresolved_downstream_evidence():
    plan, selection, broadcast, cell_input, witness = make_fixture(
        recipients=("G1",), cell_id="G1"
    )

    unrelated_digest = "f" * 64
    receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:wp510-review-unresolved-downstream",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="artifact:unrelated-to-reentry-lineage",
        downstream_sha256=unrelated_digest,
        provenance_refs=("prov:wp510-review-falsifier",),
    )

    observed = bind(witness, receipt, plan, selection, broadcast, cell_input)

    # Current bounded WP508 behavior: the exact re-entry identity is bound, while
    # downstream evidence is preserved from WP507 rather than independently resolved.
    assert observed.canonical_reentry_key == witness.canonical_reentry_key()
    assert observed.reentry_witness_sha256 == witness.sha256()
    assert observed.uptake_status == "UPTAKEN"
    assert observed.downstream_ref == "artifact:unrelated-to-reentry-lineage"
    assert observed.downstream_sha256 == unrelated_digest

    # This test grants no causal/runtime credit.  A future WP510 seal should decide
    # whether to require a concrete downstream artifact (e.g. CellOutput) whose
    # input_sha256 closes exactly to cell_input.sha256().
    payload = observed.as_dict()
    assert payload["causal_influence_claim"] == "NOT_ESTABLISHED_BY_BINDING"
    assert payload["runtime_credit"] == 0
    assert payload["gwt_runtime_credit"] == 0
    assert payload["whole_system_acceptance"] is False
