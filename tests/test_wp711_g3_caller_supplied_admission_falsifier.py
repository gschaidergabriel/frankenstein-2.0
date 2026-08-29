"""REVIEW_ONLY executable falsifier for F2-WP-711 generation 3.

The candidate G3 API accepts ``admitted_alignment_witness_sha256s`` directly from the
same caller that supplies ``alignment_witnesses``. This test requires that simply
supplying a freshly fabricated witness and its own digest must NOT constitute an
independent admission authority.

Expected against the reviewed candidate branch: RED. Do not merge this file as an
implementation fix; absorb the counterevidence into the canonical WP711 owner lane.
"""
import unittest

from src.frankenstein2.epistemic_perception import EpistemicPerceptClaim
from src.frankenstein2.perception_temporal import (
    ClockAlignmentWitness,
    bind_observed_claim,
    build_observation_window,
)


PROVENANCE = ("review:wp711-g3-caller-admission",)


def _claim(claim_id: str, source_time_ns: int) -> EpistemicPerceptClaim:
    return EpistemicPerceptClaim(
        claim_id=claim_id,
        semantic_key="screen.app",
        modality="visual",
        epistemic_type="OBSERVED",
        value="Firefox",
        confidence_micros=900_000,
        source_generation=1,
        source_time_ns=source_time_ns,
        provenance_refs=PROVENANCE,
    )


def _bind(
    claim: EpistemicPerceptClaim,
    *,
    ref_id: str,
    source_id: str,
    clock_domain: str,
    offset_ns: int,
):
    return bind_observed_claim(
        claim=claim,
        expected_claim_sha256=claim.sha256(),
        ref_id=ref_id,
        source_id=source_id,
        source_sequence=1,
        clock_domain=clock_domain,
        reference_offset_ns=offset_ns,
        clock_uncertainty_ns=0,
        max_freshness_ns=100,
        provenance_refs=PROVENANCE,
    )


class WP711G3CallerSuppliedAdmissionFalsifier(unittest.TestCase):
    def test_witness_digest_supplied_by_same_caller_is_not_independent_admission(self):
        left = _bind(
            _claim("left-claim", 980),
            ref_id="left-ref",
            source_id="screen:local",
            clock_domain="clock:local",
            offset_ns=0,
        )
        right = _bind(
            _claim("right-claim", 480),
            ref_id="right-ref",
            source_id="camera:remote",
            clock_domain="clock:remote",
            offset_ns=500,
        )

        fabricated = ClockAlignmentWitness(
            alignment_id="caller-fabricated-alignment",
            alignment_generation=1,
            left_clock_domain=left.clock_domain,
            left_source_generation=left.source_generation,
            left_reference_offset_ns=left.reference_offset_ns,
            left_max_uncertainty_ns=0,
            right_clock_domain=right.clock_domain,
            right_source_generation=right.source_generation,
            right_reference_offset_ns=right.reference_offset_ns,
            right_max_uncertainty_ns=0,
            valid_from_reference_ns=0,
            valid_through_reference_ns=2_000,
            evidence_sha256="a" * 64,
            provenance_refs=("caller:fabricated-evidence",),
        )

        # The same untrusted caller can compute this value. Therefore this tuple cannot,
        # by itself, prove that a separate admission authority accepted the witness.
        caller_minted_admission = fabricated.sha256()
        window = build_observation_window(
            refs=(left, right),
            reference_now_ns=1_000,
            max_join_skew_ns=20,
            max_clock_uncertainty_ns=5,
            provenance_refs=PROVENANCE,
            alignment_witnesses=(fabricated,),
            admitted_alignment_witness_sha256s=(caller_minted_admission,),
        )

        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"left-ref", "right-ref"})
        self.assertEqual(window.alignment_witness_refs, ())
        self.assertEqual(window.alignment_admission_sha256s, ())


if __name__ == "__main__":
    unittest.main()
