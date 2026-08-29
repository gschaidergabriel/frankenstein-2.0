import unittest

from src.frankenstein2.epistemic_perception import EpistemicPerceptClaim
from src.frankenstein2.perception_temporal import (
    ClockAlignmentWitness,
    PerceptionTemporalError,
    bind_observed_claim,
    build_observation_window,
)


P = ("test:temporal",)
EVIDENCE_SHA = "1" * 64


def claim(
    claim_id="c1",
    source_time_ns=100,
    epistemic_type="OBSERVED",
    source_generation=1,
):
    return EpistemicPerceptClaim(
        claim_id=claim_id,
        semantic_key="screen.app",
        modality="visual",
        epistemic_type=epistemic_type,
        value="Firefox",
        confidence_micros=900_000,
        source_generation=source_generation,
        source_time_ns=source_time_ns,
        provenance_refs=P,
    )


def bind(
    c,
    *,
    ref_id,
    source_id,
    sequence,
    offset=0,
    uncertainty=0,
    freshness=100,
    clock_domain=None,
):
    return bind_observed_claim(
        claim=c,
        expected_claim_sha256=c.sha256(),
        ref_id=ref_id,
        source_id=source_id,
        source_sequence=sequence,
        clock_domain=clock_domain or f"clock:{source_id}",
        reference_offset_ns=offset,
        clock_uncertainty_ns=uncertainty,
        max_freshness_ns=freshness,
        provenance_refs=P,
    )


def witness(
    left,
    right,
    *,
    alignment_id="alignment:1",
    left_offset=None,
    right_offset=None,
    left_uncertainty=None,
    right_uncertainty=None,
    valid_from=0,
    valid_through=2_000,
):
    return ClockAlignmentWitness(
        alignment_id=alignment_id,
        alignment_generation=1,
        left_clock_domain=left.clock_domain,
        left_source_generation=left.source_generation,
        left_reference_offset_ns=(
            left.reference_offset_ns if left_offset is None else left_offset
        ),
        left_max_uncertainty_ns=(
            left.clock_uncertainty_ns if left_uncertainty is None else left_uncertainty
        ),
        right_clock_domain=right.clock_domain,
        right_source_generation=right.source_generation,
        right_reference_offset_ns=(
            right.reference_offset_ns if right_offset is None else right_offset
        ),
        right_max_uncertainty_ns=(
            right.clock_uncertainty_ns if right_uncertainty is None else right_uncertainty
        ),
        valid_from_reference_ns=valid_from,
        valid_through_reference_ns=valid_through,
        evidence_sha256=EVIDENCE_SHA,
        provenance_refs=("test:clock-alignment-evidence",),
    )


def admission(w, admission_id="admission:clock-alignment:1"):
    return ((admission_id, w.sha256()),)


class PerceptionTemporalTests(unittest.TestCase):
    def test_only_observed_claims_enter_current_window(self):
        inferred = claim(epistemic_type="INFERRED")
        with self.assertRaisesRegex(PerceptionTemporalError, "only OBSERVED"):
            bind(inferred, ref_id="r1", source_id="screen:1", sequence=1)

    def test_claim_digest_is_exact(self):
        c = claim()
        with self.assertRaisesRegex(PerceptionTemporalError, "claim digest mismatch"):
            bind_observed_claim(
                claim=c,
                expected_claim_sha256="0" * 64,
                ref_id="r1",
                source_id="screen:1",
                source_sequence=1,
                clock_domain="clock:screen:1",
                reference_offset_ns=0,
                clock_uncertainty_ns=0,
                max_freshness_ns=100,
                provenance_refs=P,
            )

    def test_fresh_and_stale_are_partitioned_without_arrival_order_authority(self):
        fresh = bind(
            claim("c1", 950),
            ref_id="fresh",
            source_id="screen:1",
            sequence=1,
            freshness=100,
        )
        stale = bind(
            claim("c2", 700),
            ref_id="stale",
            source_id="screen:2",
            sequence=1,
            freshness=100,
        )
        window = build_observation_window(
            refs=(fresh, stale),
            reference_now_ns=1_000,
            max_join_skew_ns=100,
            max_clock_uncertainty_ns=20,
            provenance_refs=P,
        )
        self.assertEqual(window.current_ref_ids, ("fresh",))
        self.assertEqual(window.stale_ref_ids, ("stale",))
        self.assertEqual(window.unaligned_ref_ids, ())
        self.assertEqual(window.alignment_status, "ALIGNED")
        payload = window.as_dict()
        self.assertFalse(payload["arrival_order_is_event_time"])
        self.assertFalse(payload["same_grid_cycle_is_same_real_world_time"])
        self.assertTrue(payload["unknown_or_unaligned_preserved"])

    def test_clock_uncertainty_is_unaligned_not_stale(self):
        uncertain = bind(
            claim("c1", 950),
            ref_id="uncertain",
            source_id="camera:1",
            sequence=1,
            uncertainty=30,
            freshness=100,
        )
        window = build_observation_window(
            refs=(uncertain,),
            reference_now_ns=1_000,
            max_join_skew_ns=100,
            max_clock_uncertainty_ns=20,
            provenance_refs=P,
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(window.stale_ref_ids, ())
        self.assertEqual(window.unaligned_ref_ids, ("uncertain",))
        self.assertEqual(window.alignment_status, "UNALIGNED")

    def test_cross_source_join_skew_is_preserved_as_unaligned(self):
        a = bind(
            claim("c1", 900),
            ref_id="a",
            source_id="screen:1",
            sequence=1,
            freshness=500,
            clock_domain="clock:shared",
        )
        b = bind(
            claim("c2", 990),
            ref_id="b",
            source_id="camera:1",
            sequence=1,
            freshness=500,
            clock_domain="clock:shared",
        )
        window = build_observation_window(
            refs=(a, b),
            reference_now_ns=1_000,
            max_join_skew_ns=50,
            max_clock_uncertainty_ns=10,
            provenance_refs=P,
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"a", "b"})
        self.assertEqual(window.alignment_status, "UNALIGNED")

    def test_pr398_unproven_distinct_clock_domains_remain_unaligned(self):
        a = bind(
            claim("c1", 980),
            ref_id="a",
            source_id="screen:1",
            sequence=1,
            offset=0,
            uncertainty=0,
            freshness=100,
            clock_domain="clock:host-a",
        )
        b = bind(
            claim("c2", 980),
            ref_id="b",
            source_id="camera:1",
            sequence=1,
            offset=0,
            uncertainty=0,
            freshness=100,
            clock_domain="clock:host-b",
        )
        window = build_observation_window(
            refs=(a, b),
            reference_now_ns=1_000,
            max_join_skew_ns=20,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"a", "b"})
        self.assertEqual(window.alignment_witness_refs, ())
        self.assertEqual(window.alignment_status, "UNALIGNED")

    def test_reference_clock_offset_requires_and_records_admitted_alignment_witness(self):
        local = bind(
            claim("c1", 980),
            ref_id="local",
            source_id="screen:1",
            sequence=1,
            freshness=100,
            clock_domain="clock:local",
        )
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:remote",
            sequence=1,
            offset=500,
            uncertainty=5,
            freshness=100,
            clock_domain="clock:remote",
        )
        alignment = witness(
            local,
            remote,
            left_uncertainty=5,
            right_uncertainty=5,
        )
        without_witness = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=30,
            max_clock_uncertainty_ns=10,
            provenance_refs=P,
        )
        self.assertEqual(without_witness.current_ref_ids, ())
        self.assertEqual(set(without_witness.unaligned_ref_ids), {"local", "remote"})

        raw_witness_only = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=30,
            max_clock_uncertainty_ns=10,
            provenance_refs=P,
            alignment_witnesses=(alignment,),
        )
        self.assertEqual(raw_witness_only.current_ref_ids, ())
        self.assertEqual(set(raw_witness_only.unaligned_ref_ids), {"local", "remote"})
        self.assertEqual(raw_witness_only.alignment_witness_refs, ())
        self.assertEqual(raw_witness_only.alignment_witness_admission_refs, ())

        admission_ref = admission(alignment)
        window = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=30,
            max_clock_uncertainty_ns=10,
            provenance_refs=P,
            alignment_witnesses=(alignment,),
            admitted_alignment_witness_refs=admission_ref,
        )
        self.assertEqual(set(window.current_ref_ids), {"local", "remote"})
        self.assertEqual(window.unaligned_ref_ids, ())
        self.assertEqual(window.alignment_status, "ALIGNED")
        self.assertEqual(
            window.alignment_witness_refs,
            ((alignment.alignment_id, alignment.sha256()),),
        )
        self.assertEqual(window.alignment_witness_admission_refs, admission_ref)
        self.assertIn(
            f"clock-alignment-witness-sha256:{alignment.sha256()}",
            window.provenance_refs,
        )
        self.assertIn(
            f"clock-alignment-admission:{admission_ref[0][0]}:{alignment.sha256()}",
            window.provenance_refs,
        )

    def test_mismatched_or_ambiguous_admission_fails_closed(self):
        local = bind(
            claim("c1", 980),
            ref_id="local",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:local",
        )
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:remote",
            sequence=1,
            offset=500,
            clock_domain="clock:remote",
        )
        alignment = witness(local, remote)
        for refs in (
            (("admission:wrong", "f" * 64),),
            (
                ("admission:one", alignment.sha256()),
                ("admission:two", alignment.sha256()),
            ),
        ):
            with self.subTest(refs=refs):
                window = build_observation_window(
                    refs=(local, remote),
                    reference_now_ns=1_000,
                    max_join_skew_ns=30,
                    max_clock_uncertainty_ns=5,
                    provenance_refs=P,
                    alignment_witnesses=(alignment,),
                    admitted_alignment_witness_refs=refs,
                )
                self.assertEqual(window.current_ref_ids, ())
                self.assertEqual(set(window.unaligned_ref_ids), {"local", "remote"})
                self.assertEqual(window.alignment_witness_refs, ())
                self.assertEqual(window.alignment_witness_admission_refs, ())

    def test_admission_identity_changes_window_identity(self):
        local = bind(
            claim("c1", 980),
            ref_id="local",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:local",
        )
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:remote",
            sequence=1,
            offset=500,
            clock_domain="clock:remote",
        )
        alignment = witness(local, remote)
        first = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=30,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
            alignment_witnesses=(alignment,),
            admitted_alignment_witness_refs=admission(alignment, "admission:a"),
        )
        second = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=30,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
            alignment_witnesses=(alignment,),
            admitted_alignment_witness_refs=admission(alignment, "admission:b"),
        )
        self.assertNotEqual(first.window_id, second.window_id)
        self.assertNotEqual(first.sha256(), second.sha256())

    def test_wrong_offset_alignment_witness_cannot_authorize_comparison(self):
        local = bind(
            claim("c1", 980),
            ref_id="local",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:local",
        )
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:remote",
            sequence=1,
            offset=500,
            clock_domain="clock:remote",
        )
        wrong = witness(local, remote, right_offset=499)
        window = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=30,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
            alignment_witnesses=(wrong,),
            admitted_alignment_witness_refs=admission(wrong),
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"local", "remote"})
        self.assertEqual(window.alignment_witness_refs, ())

    def test_expired_alignment_witness_cannot_authorize_comparison(self):
        local = bind(
            claim("c1", 980),
            ref_id="local",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:local",
        )
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:remote",
            sequence=1,
            offset=500,
            clock_domain="clock:remote",
        )
        expired = witness(local, remote, valid_from=0, valid_through=900)
        window = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=30,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
            alignment_witnesses=(expired,),
            admitted_alignment_witness_refs=admission(expired),
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"local", "remote"})

    def test_ambiguous_multiple_alignment_witnesses_fail_closed(self):
        local = bind(
            claim("c1", 980),
            ref_id="local",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:local",
        )
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:remote",
            sequence=1,
            offset=500,
            clock_domain="clock:remote",
        )
        first = witness(local, remote, alignment_id="alignment:1")
        second = witness(local, remote, alignment_id="alignment:2")
        window = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=30,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
            alignment_witnesses=(first, second),
            admitted_alignment_witness_refs=(
                ("admission:first", first.sha256()),
                ("admission:second", second.sha256()),
            ),
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"local", "remote"})
        self.assertEqual(window.alignment_witness_refs, ())

    def test_source_generation_change_is_unaligned_without_relation(self):
        first = bind(
            claim("c1", 980, source_generation=1),
            ref_id="g1",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:screen",
        )
        rebound = bind(
            claim("c2", 985, source_generation=2),
            ref_id="g2",
            source_id="screen:1",
            sequence=2,
            clock_domain="clock:screen",
        )
        window = build_observation_window(
            refs=(first, rebound),
            reference_now_ns=1_000,
            max_join_skew_ns=20,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"g1", "g2"})

    def test_future_reference_time_is_unaligned_not_current_or_stale(self):
        future = bind(
            claim("c1", 1_010),
            ref_id="future",
            source_id="screen:1",
            sequence=1,
            freshness=100,
        )
        window = build_observation_window(
            refs=(future,),
            reference_now_ns=1_000,
            max_join_skew_ns=20,
            max_clock_uncertainty_ns=10,
            provenance_refs=P,
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(window.stale_ref_ids, ())
        self.assertEqual(window.unaligned_ref_ids, ("future",))

    def test_source_time_regression_fails_closed(self):
        newer_sequence_older_time = bind(
            claim("c2", 90),
            ref_id="r2",
            source_id="screen:1",
            sequence=2,
            freshness=100,
        )
        first = bind(
            claim("c1", 100),
            ref_id="r1",
            source_id="screen:1",
            sequence=1,
            freshness=100,
        )
        with self.assertRaisesRegex(PerceptionTemporalError, "source time regressed"):
            build_observation_window(
                refs=(newer_sequence_older_time, first),
                reference_now_ns=150,
                max_join_skew_ns=100,
                max_clock_uncertainty_ns=10,
                provenance_refs=P,
            )

    def test_arrival_permutation_does_not_change_window_identity(self):
        a = bind(
            claim("c1", 980),
            ref_id="a",
            source_id="screen:1",
            sequence=1,
            freshness=100,
            clock_domain="clock:shared",
        )
        b = bind(
            claim("c2", 985),
            ref_id="b",
            source_id="camera:1",
            sequence=1,
            freshness=100,
            clock_domain="clock:shared",
        )
        first = build_observation_window(
            refs=(a, b),
            reference_now_ns=1_000,
            max_join_skew_ns=20,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
        )
        second = build_observation_window(
            refs=(b, a),
            reference_now_ns=1_000,
            max_join_skew_ns=20,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
        )
        self.assertEqual(set(first.current_ref_ids), {"a", "b"})
        self.assertEqual(first.window_id, second.window_id)
        self.assertEqual(first.sha256(), second.sha256())

    def test_window_never_mints_truth_effect_or_completion_authority(self):
        a = bind(
            claim("c1", 980),
            ref_id="a",
            source_id="screen:1",
            sequence=1,
            freshness=100,
        )
        window = build_observation_window(
            refs=(a,),
            reference_now_ns=1_000,
            max_join_skew_ns=20,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
        )
        payload = window.as_dict()
        self.assertEqual(payload["world_truth_authority"], "NONE")
        self.assertEqual(payload["effect_authority"], "NONE")
        self.assertEqual(payload["completion_authority"], "NONE")
        self.assertFalse(payload["resolves_semantic_disagreement"])
        self.assertTrue(payload["unproven_cross_clock_is_unaligned"])
        self.assertFalse(payload["numeric_reference_offset_self_attests_alignment"])
        self.assertFalse(payload["raw_clock_witness_self_attests_admission"])


if __name__ == "__main__":
    unittest.main()
