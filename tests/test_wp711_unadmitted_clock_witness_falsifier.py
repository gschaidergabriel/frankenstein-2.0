import unittest

from src.frankenstein2.perception_temporal import (
    ClockAlignmentWitness,
    TemporalPerceptRef,
    build_observation_window,
)

PROVENANCE = ("review:wp711-unadmitted-witness",)


def temporal_ref(*, ref_id: str, source_id: str, clock_domain: str) -> TemporalPerceptRef:
    return TemporalPerceptRef(
        ref_id=ref_id,
        source_id=source_id,
        source_sequence=1,
        source_generation=1,
        clock_domain=clock_domain,
        source_time_ns=980,
        reference_offset_ns=0,
        clock_uncertainty_ns=0,
        max_freshness_ns=100,
        observed_claim_sha256=("1" if ref_id == "left" else "2") * 64,
        provenance_refs=PROVENANCE,
    )


class WP711UnadmittedClockWitnessFalsifier(unittest.TestCase):
    def test_matching_witness_must_not_be_its_own_admission_authority(self):
        left = temporal_ref(
            ref_id="left",
            source_id="display:primary",
            clock_domain="clock:host-a",
        )
        right = temporal_ref(
            ref_id="right",
            source_id="camera:primary",
            clock_domain="clock:host-b",
        )
        caller_supplied = ClockAlignmentWitness(
            alignment_id="alignment:caller-supplied",
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
            evidence_sha256="3" * 64,
            provenance_refs=("caller:asserted-clock-evidence",),
        )

        window = build_observation_window(
            refs=(left, right),
            reference_now_ns=1_000,
            max_join_skew_ns=20,
            max_clock_uncertainty_ns=5,
            provenance_refs=PROVENANCE,
            alignment_witnesses=(caller_supplied,),
        )

        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"left", "right"})
        self.assertEqual(window.alignment_witness_refs, ())
        self.assertEqual(window.alignment_admission_refs, ())
        self.assertEqual(window.alignment_status, "UNALIGNED")


if __name__ == "__main__":
    unittest.main()
