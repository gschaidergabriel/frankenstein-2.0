"""REVIEW_ONLY executable falsifier for F2-WP-510 generation 2.

Preregistered negative hypothesis:
WP510 closes a positive UPTAKEN path to an exact typed GRID10 CellOutput identity,
but does not require that output to represent executed downstream computation.
Because the accepted GRID10 ABI permits NOT_COMPUTED as a CellOutput status, a
caller may be able to build internally self-consistent WP507/WP508 evidence around
a NOT_COMPUTED output and still obtain CONTRACT_SCOPE_CAUSAL_PATH_SEALED.

After the preregistered NOT_COMPUTED reproducer passed, this review also characterizes
the adjacent non-COMPLETE statuses using the same exact construction. That follow-up
matrix is characterization, not independent replication and not a contract decision.

This file intentionally changes no WP510-owned production path. Passing tests are
repository-contract evidence only, not runtime/GWT/J-Space or whole-system credit.
"""
from pathlib import Path
import sys

import pytest

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


def _seal_positive_path_with_downstream_status(status: str, work_units_used: int):
    fx = make_fixture()
    seed_bundle = fx["reentry_bundles"][0]
    plan = fx["plan"]
    selection = fx["selection"]
    broadcast = fx["broadcast"]
    cell_input = seed_bundle.cell_input
    witness = seed_bundle.witness
    suffix = status.lower().replace("_", "-")

    downstream_output = CellOutput.for_input(
        plan,
        cell_input,
        status=status,
        work_units_used=work_units_used,
        output_refs=("downstream:wp510",),
        evidence_refs=(f"evidence:downstream-status-{suffix}",),
        provenance_refs=(f"prov:downstream-status-{suffix}",),
    )
    receipt = CellUptakeReceipt.observe(
        receipt_id=f"receipt:G1:wp510:downstream-status-{suffix}",
        broadcast=broadcast,
        cell_id="G1",
        delivery_status="DELIVERED",
        uptake_status="UPTAKEN",
        downstream_ref="downstream:wp510",
        downstream_sha256=downstream_output.sha256(),
        provenance_refs=(f"prov:wp507-downstream-status-{suffix}",),
    )
    summary = summarize_uptake(
        summary_id=f"summary:wp510:downstream-status-{suffix}",
        broadcast=broadcast,
        receipts=(receipt,),
        provenance_refs=(f"prov:summary-downstream-status-{suffix}",),
    )
    intervention = CausalProbeArm.intervention(
        arm_id=f"arm:intervention:wp510:downstream-status-{suffix}",
        probe_id=f"probe:wp510:downstream-status-{suffix}",
        broadcast=broadcast,
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=downstream_output.sha256(),
        provenance_refs=(f"prov:intervention-downstream-status-{suffix}",),
    )
    control = CausalProbeArm.control(
        arm_id=f"arm:control:wp510:downstream-status-{suffix}",
        probe_id=f"probe:wp510:downstream-status-{suffix}",
        nonbroadcast_input_sha256=D,
        downstream_output_sha256=F,
        provenance_refs=(f"prov:control-downstream-status-{suffix}",),
    )
    causal_result = evaluate_causal_influence(
        result_id=f"causal:wp510:downstream-status-{suffix}",
        broadcast=broadcast,
        uptake_summary=summary,
        intervention=intervention,
        control=control,
        provenance_refs=(f"prov:causal-downstream-status-{suffix}",),
    )
    binding = bind_reentry_to_uptake(
        binding_id=f"binding:wp510:downstream-status-{suffix}",
        witness=witness,
        uptake_receipt=receipt,
        plan=plan,
        selection=selection,
        broadcast=broadcast,
        cell_input=cell_input,
        provenance_refs=(f"prov:binding-downstream-status-{suffix}",),
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
    return downstream_output, receipt, causal_result, observed


def test_preregistered_not_computed_downstream_can_still_seal_positive_path():
    downstream_output, receipt, causal_result, observed = (
        _seal_positive_path_with_downstream_status("NOT_COMPUTED", 0)
    )

    assert downstream_output.status == "NOT_COMPUTED"
    assert receipt.uptake_status == "UPTAKEN"
    assert causal_result.status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    assert observed.path_status == "CONTRACT_SCOPE_CAUSAL_PATH_SEALED"
    assert observed.as_dict()["runtime_credit"] == 0


@pytest.mark.parametrize(
    ("status", "work_units_used"),
    (
        ("PARTIAL", 1),
        ("ABSTAIN", 0),
        ("UNKNOWN", 0),
        ("ERROR", 0),
    ),
)
def test_followup_characterization_noncomplete_statuses_also_reach_positive_seal(
    status: str,
    work_units_used: int,
):
    downstream_output, receipt, causal_result, observed = (
        _seal_positive_path_with_downstream_status(status, work_units_used)
    )

    assert downstream_output.status == status
    assert receipt.uptake_status == "UPTAKEN"
    assert causal_result.status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    assert observed.path_status == "CONTRACT_SCOPE_CAUSAL_PATH_SEALED"
    assert observed.as_dict()["runtime_credit"] == 0
