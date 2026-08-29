"""F2-WP-510 G3 regression for the post-G2 downstream-status falsifier.

This test absorbs only the preregistered REVIEW_ONLY PR #496 NOT_COMPUTED case.
The adjacent PARTIAL/ABSTAIN/UNKNOWN/ERROR characterization remains outside this
successor's semantic repair scope.
"""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gwt_causal_path import make_fixture, seal  # noqa: E402

from frankenstein2.grid10_interface import CellOutput  # noqa: E402
from frankenstein2.gwt_causal_path import GwtCausalPathError, ReentryEvidenceBundle  # noqa: E402
from frankenstein2.gwt_reentry_uptake_binding import bind_reentry_to_uptake  # noqa: E402
from frankenstein2.gwt_uptake import (  # noqa: E402
    CausalProbeArm,
    CellUptakeReceipt,
    evaluate_causal_influence,
    summarize_uptake,
)

D = "d" * 64
F = "f" * 64


def _not_computed_positive_fixture():
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
        evidence_refs=("evidence:downstream-status-not-computed",),
        provenance_refs=("prov:downstream-status-not-computed",),
    )
    receipt = CellUptakeReceipt.observe(
        receipt_id="receipt:G1:wp510:downstream-status-not-computed",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:wp510",
        downstream_sha256=downstream_output.sha256(),
        provenance_refs=("prov:wp507-downstream-status-not-computed",),
    )
    summary = summarize_uptake(
        summary_id="summary:wp510:downstream-status-not-computed",
        broadcast=broadcast,
        receipts=(receipt,),
        provenance_refs=("prov:summary-downstream-status-not-computed",),
    )
    intervention = CausalProbeArm.intervention(
        arm_id="arm:intervention:wp510:downstream-status-not-computed",
        probe_id="probe:wp510:downstream-status-not-computed",
        broadcast=broadcast,
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=downstream_output.sha256(),
        provenance_refs=("prov:intervention-downstream-status-not-computed",),
    )
    control = CausalProbeArm.control(
        arm_id="arm:control:wp510:downstream-status-not-computed",
        probe_id="probe:wp510:downstream-status-not-computed",
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=F,
        provenance_refs=("prov:control-downstream-status-not-computed",),
    )
    causal_result = evaluate_causal_influence(
        result_id="causal:wp510:downstream-status-not-computed",
        broadcast=broadcast,
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        provenance_refs=("prov:causal-downstream-status-not-computed",),
    )
    binding = bind_reentry_to_uptake(
        binding_id="binding:wp510:downstream-status-not-computed",
        witness=witness,
        uptake_receipt=receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=("prov:binding-downstream-status-not-computed",),
    )
    bundle = ReentryEvidenceBundle(
        binding=binding,
        witness=witness,
        uptake_receipt=receipt,
        cell_input=cell_input,
        downstream_output=downstream_output,
    )
    return fx, receipt, summary, intervention, control, causal_result, bundle


def test_not_computed_downstream_cannot_seal_positive_causal_path():
    fx, receipt, summary, intervention, control, causal_result, bundle = (
        _not_computed_positive_fixture()
    )

    assert bundle.downstream_output is not None
    assert bundle.downstream_output.status == "NOT_COMPUTED"
    assert receipt.uptake_status == "UPTAKEN"
    assert causal_result.status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"

    with pytest.raises(GwtCausalPathError, match="NOT_COMPUTED"):
        seal(
            fx,
            receipts=(receipt,),
            uptake_summary=summary,
            intervention=intervention,
            control=control,
            causal_result=causal_result,
            reentry_bundles=(bundle,),
        )
