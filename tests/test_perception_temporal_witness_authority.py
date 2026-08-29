import unittest

from src.frankenstein2.epistemic_perception import EpistemicPerceptClaim
from src.frankenstein2.perception_temporal import (
    ClockAlignmentWitness,
    bind_observed_claim,
    build_observation_window,
)


class ClockAlignmentWitnessAuthorityFalsifier(unittest.TestCase):
    def _ref(self, *, claim_id, ref_id, source_id, clock_domain, source_time_ns):
        claim = EpistemicPerceptClaim(
            claim_id=claim_id,
            semantic_key="screen.app",
            modality="visual",
            epistemic_type="OBSERVED",
            value="Firefox",
            confidence_micros=900_000,
            source_generation=1,
            source_time_ns=source_time_ns,
            provenance_refs=("review:wp711-g2-authority-falsifier",),
        )
        return bind_observed_claim(
            claim=claim,
            expected_claim_sha256=claim.sha256(),
            ref_id=ref_id,
            source_id=source_id,
            source_sequence=1,
            clock_domain=clock_domain,
            reference_offset_ns=0,
            clock_uncertainty_ns=0,
            max_freshness_ns=100,
            provenance_refs=("review:wp711-g2-authority-falsifier",),
        )

    def test_arbitrary_caller_minted_witness_does_not_authorize_cross_clock_join(self):
        left = self._ref(
            claim_id="left-claim",
            ref_id="left-ref",
            source_id="screen:1",
            clock_domain="clock:host-a",
            source_time_ns=980,
        )
        right = self._ref(
            claim_id="right-claim",
            ref_id="right-ref",
            source_id="camera:1",
            clock_domain="clock:host-b",
            source_time_ns=985,
        )

        caller_minted = ClockAlignmentWitness(
            alignment_id="caller-forged",
            alignment_generation=1,
            left_clock_domain=left.clock_domain,
            left_source_generation=left.source_generation,
            left_reference_offset_ns=left.reference_offset_ns,
            left_max_uncertainty_ns=left.clock_uncertainty_ns,
            right_clock_domain=right.clock_domain,
            right_source_generation=right.source_generation,
            right_reference_offset_ns=right.reference_offset_ns,
            right_max_uncertainty_ns=right.clock_uncertainty_ns,
            valid_from_reference_ns=0,
            valid_through_reference_ns=10_000,
            evidence_sha256="0" * 64,
            provenance_refs=("caller:self-attested",),
        )

        window = build_observation_window(
            refs=(left, right),
            reference_now_ns=1_000,
            max_join_skew_ns=20,
            max_clock_uncertainty_ns=5,
            provenance_refs=("review:wp711-g2-authority-falsifier",),
            alignment_witnesses=(caller_minted,),
        )

        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"left-ref", "right-ref"})
        self.assertEqual(window.alignment_witness_refs, ())
        self.assertEqual(window.alignment_status, "UNALIGNED")


if __name__ == "__main__":
    unittest.main()
