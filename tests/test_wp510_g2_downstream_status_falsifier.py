"""REVIEW_ONLY executable falsifier for F2-WP-510 generation 2.

Hypothesis under test:
WP510 closes a positive UPTAKEN path to an exact typed GRID10 CellOutput identity,
but does not require that output to represent executed downstream computation.
Because the accepted GRID10 ABI permits NOT_COMPUTED as a CellOutput status, a
caller may be able to build internally self-consistent WP507/WP508 evidence around
a NOT_COMPUTED output and still obtain CONTRACT_SCOPE_CAUSAL_PATH_SEALED.

This file intentionally changes no WP510-owned production path. A passing test is
negative evidence for the reviewed contract surface, not runtime/GWT/J-Space or
whole-system credit.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gwt_causal_path import make_fixture, seal  # noqa: E402

from frankenstein2.grid10_interface import CellOutput  # noqa: E402
from frankenstein2.gwt_causal_path import ReentryEvidenceBundle  # noqa: E402
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake  # noqa: E402
from frankenstein2.gwt_uptake import (  # noqa: E402
    CausalProbeArm,
    CellUptakeReceipt,
    evaluate_causal_influence,
    summarize_uptake,
)

D = "d" * 64
F = "f" * 64


def test_wp510_g2_seals_positive_path_with_not_computed_downstream_output():
    fx = make_fixture()
    seed_bundle = fx["reentry_bundles"][0]
    plan = fx["plan"]
    selection = fx["selection"]
    broadcast = fx["broadcast"]
    cell_input = seed_bundle.cell_input
    witness = seed_bundle.witness

    downstream_output = CellOutput.for_input(
        plan,
        cell_input,
        status="NOT_COMPUTED",
        work_units_used=0,
        output_refs=("downstream:wp510",),
        evidence_refs=("evidence:downstream-status-falsifier",),
        provenance_refs=("prov:downstream-status-falsifier",),
    )
    receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:G1:wp510:downstream-status-falsifier",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:wp510",
        downstream_sha256=downstream_output.sha256(),
        provenance_refs=("prov:wp507-downstream-status-falsifier",),
    )
    summary = summarize_uptake(
        summary_id="summary:wp510:downstream-status-falsifier",
        broadcast=broadcast,
        receipts=(receipt,),
        provenance_refs=("prov:summary-downstream-status-falsifier",),
    )
    intervention = CausalProbeArm.intervention(
        arm_id="arm:intervention:wp510:downstream-status-falsifier",
        probe_id="probe:wp510:downstream-status-falsifier",
        broadcast=broadcast,
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=downstream_output.sha256(),
        provenance_refs=("prov:intervention-downstream-status-falsifier",),
    )
    control = CausalProbeArm.control(
        arm_id="arm:control:wp510:downstream-status-falsifier",
        probe_id="probe:wp510:downstream-status-falsifier",
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=F,
        provenance_refs=("prov:control-downstream-status-falsifier",),
    )
    causal_result = evaluate_causal_influence(
        result_id="causal:wp510:downstream-status-falsifier",
        broadcast=broadcast,
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        provenance_refs=("prov:causal-downstream-status-falsifier",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:wp510:downstream-status-falsifier",
        witness=witness,
        uptake_receipt=receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:binding-downstream-status-falsifier",),
    )
    bundle = ReentryEvidenceBundle(
        binding=binding,
        witness=witness,
        uptake_receipt=receipt,
        cell_input=cell_input,
        downstream_output=downstream_output,
    )

    observed = seal(
        fx,
        receipts=(receipt,),
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        causal_result=causal_result,
        reentry_bundles=(bundle,),
    )

    assert downstream_output.status == "NOT_COMPUTED"
    assert receipt.uptake_status == "UPTAKEN"
    assert causal_result.status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    assert observed.path_status == "CONTRACT_SCOPE_CAUSAL_PATH_SEALED"
    assert observed.runtime_credit == 0 if hasattr(observed, "runtime_credit") else observed.as_dict()["runtime_credit"] == 0
