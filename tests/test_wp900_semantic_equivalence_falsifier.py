"""REVIEW_ONLY candidate falsifier for the next semantic GWT/J-Space gate.

This does NOT invalidate accepted WP900 G4 contract-scope causal evidence.  G4 is
explicitly hash/contract scoped.  The discriminator asks a narrower promotion
question: may byte-level downstream inequality alone be promoted as a semantic
GWT effect?

Expected current-source result: the evaluator reports contract-scope causal
influence even when intervention/control downstream payloads are JSON-semantic
equivalents with different byte serializations.  Therefore semantic-GWT credit
must remain blocked until a separately admitted semantic readback/comparator is
bound to both arms.
"""

import hashlib
import json
import unittest

from frankenstein2.grid10_interface import GRID10_CELL_IDS
from frankenstein2.gwt_uptake import (
    CausalProbeArm,
    CellUptakeReceipt,
    evaluate_causal_influence,
    summarize_uptake,
)
from frankenstein2.gwt_workspace import BroadcastEnvelope

A = "a" * 64
B = "b" * 64
C = "c" * 64


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def broadcast() -> BroadcastEnvelope:
    return BroadcastEnvelope(
        broadcast_id="semantic-falsifier-broadcast",
        cycle_id="semantic-falsifier-cycle",
        generation=1,
        selection_id="semantic-falsifier-selection",
        selection_generation=1,
        selection_sha256=A,
        plan_id="semantic-falsifier-plan",
        plan_generation=1,
        plan_sha256=B,
        recipient_cell_ids=(GRID10_CELL_IDS[0],),
        candidate_ids=("candidate-1",),
        candidate_payload_refs=("payload:candidate-1",),
    )


class WP900SemanticEquivalenceCandidateFalsifier(unittest.TestCase):
    def test_semantically_equal_downstream_payloads_cannot_support_semantic_gwt_credit(self):
        b = broadcast()
        receipt = CellUptakeReceipt.observe(
            receipt_id="semantic-falsifier-receipt",
            broadcast=b,
            cell_id=GRID10_CELL_IDS[0],
            delivery_status="DELIVERED",
            uptake_status="UPTAKEN",
            downstream_ref="semantic:result",
            downstream_sha256=C,
            provenance_refs=("candidate-falsifier",),
        )
        uptake = summarize_uptake(
            summary_id="semantic-falsifier-summary",
            broadcast=b,
            receipts=(receipt,),
            provenance_refs=("candidate-falsifier",),
        )

        semantic_value = {"decision": "ABSTAIN", "reason": "insufficient-evidence"}
        intervention_bytes = json.dumps(
            semantic_value, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        control_bytes = json.dumps(
            semantic_value, sort_keys=False, indent=2
        ).encode("utf-8")

        self.assertEqual(json.loads(intervention_bytes), json.loads(control_bytes))
        self.assertNotEqual(sha256_bytes(intervention_bytes), sha256_bytes(control_bytes))

        intervention = CausalProbeArm.intervention(
            arm_id="semantic-falsifier-intervention",
            probe_id="semantic-falsifier-probe",
            broadcast=b,
            nonbroadcast_input_sha256=A,
            downstream_output_sha256=sha256_bytes(intervention_bytes),
            provenance_refs=("candidate-falsifier",),
        )
        control = CausalProbeArm.control(
            arm_id="semantic-falsifier-control",
            probe_id="semantic-falsifier-probe",
            nonbroadcast_input_sha256=A,
            downstream_output_sha256=sha256_bytes(control_bytes),
            provenance_refs=("candidate-falsifier",),
        )
        result = evaluate_causal_influence(
            result_id="semantic-falsifier-result",
            broadcast=b,
            uptake_summary=uptake,
            intervention=intervention,
            control=control,
            provenance_refs=("candidate-falsifier",),
        )

        # Current G4 is allowed to report contract-scope influence here.  This
        # assertion is intentionally the *next semantic promotion gate* and is
        # expected to fail until semantic readback is introduced.  A failure is
        # CANDIDATE_FALSIFIER evidence, not a WP900-G4 PRODUCT_NEGATIVE.
        self.assertNotEqual(
            result.status,
            "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE",
            "SEMANTIC_PROMOTION_BLOCKED: byte/hash inequality alone cannot prove a semantic GWT effect",
        )


if __name__ == "__main__":
    unittest.main()
