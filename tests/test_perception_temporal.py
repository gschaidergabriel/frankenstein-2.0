import unittest

from src.frankenstein2.epistemic_perception import EpistemicPerceptClaim
from src.frankenstein2.perception_temporal import (
    PerceptionTemporalError,
    bind_observed_claim,
    build_observation_window,
)


P = ("test:temporal",)


def claim(claim_id="c1", source_time_ns=100, epistemic_type="OBSERVED"):
    return EpistemicPerceptClaim(
        claim_id=claim_id,
        semantic_key="screen.app",
        modality="visual",
        epistemic_type=epistemic_type,
        value="Firefox",
        confidence_micros=900_000,
        source_generation=1,
        source_time_ns=source_time_ns,
        provenance_refs=P,
    )


def bind(c, *, ref_id, source_id, sequence, offset=0, uncertainty=0, freshness=100):
    return bind_observed_claim(
        claim=c,
        expected_claim_sha256=c.sha256(),
        ref_id=ref_id,
        source_id=source_id,
        source_sequence=sequence,
        clock_domain=f"clock:{source_id}",
        reference_offset_ns=offset,
        clock_uncertainty_ns=uncertainty,
        max_freshness_ns=freshness,
        provenance_refs=P,
    )


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

    def test_fresh_and_stale_are_partitioned(self):
        fresh = bind(claim("c1", 950), ref_id="fresh", source_id="screen:1", sequence=1, freshness=100)
        stale = bind(claim("c2", 700), ref_id="stale", source_id="screen:2", sequence=1, freshness=100)
        window = build_observation_window(
            refs=(fresh, stale),
            reference_now_ns=1_000,
            max_join_skew_ns=100,
            max_clock_uncertainty_ns=20,
            provenance_refs=P,
        )
        self.assertEqual(window.current_ref_ids, ("fresh",))
        self.assertEqual(window.stale_ref_ids, ("stale",))
        self.assertFalse(window.as_dict()["arrival_order_is_event_time"])

    def test_clock_uncertainty_can_make_observation_stale(self):
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
        self.assertEqual(window.stale_ref_ids, ("uncertain",))

    def test_cross_source_join_skew_fails_closed(self):
        a = bind(claim("c1", 900), ref_id="a", source_id="screen:1", sequence=1, freshness=500)
        b = bind(claim("c2", 990), ref_id="b", source_id="camera:1", sequence=1, freshness=500)
        with self.assertRaisesRegex(PerceptionTemporalError, "max_join_skew_ns"):
            build_observation_window(
                refs=(a, b),
                reference_now_ns=1_000,
                max_join_skew_ns=50,
                max_clock_uncertainty_ns=10,
                provenance_refs=P,
            )

    def test_reference_clock_offset_enables_bounded_cross_host_join(self):
        local = bind(claim("c1", 980), ref_id="local", source_id="screen:1", sequence=1, freshness=100)
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:remote",
            sequence=1,
            offset=500,
            uncertainty=5,
            freshness=100,
        )
        window = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=20,
            max_clock_uncertainty_ns=10,
            provenance_refs=P,
        )
        self.assertEqual(set(window.current_ref_ids), {"local", "remote"})

    def test_source_time_regression_fails_closed(self):
        newer_sequence_older_time = bind(claim("c2", 90), ref_id="r2", source_id="screen:1", sequence=2, freshness=100)
        first = bind(claim("c1", 100), ref_id="r1", source_id="screen:1", sequence=1, freshness=100)
        with self.assertRaisesRegex(PerceptionTemporalError, "source time regressed"):
            build_observation_window(
                refs=(newer_sequence_older_time, first),
                reference_now_ns=150,
                max_join_skew_ns=100,
                max_clock_uncertainty_ns=10,
                provenance_refs=P,
            )


if __name__ == "__main__":
    unittest.main()
