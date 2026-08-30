#!/usr/bin/env python3
from __future__ import annotations

import unittest

from frankenstein2.characterization_contract import (
    CharacterizationError,
    CharacterizationObservation,
    summarize_characterization,
)


SOURCE = "a" * 40
ENV = "b" * 64


def observation(
    n: int,
    *,
    source: str = SOURCE,
    env: str = ENV,
    workload: str = "whole-loop-smoke-v1",
    peak_rss_bytes: int | None = None,
    latency_ns: int | None = None,
    quality_bp: int | None = None,
) -> CharacterizationObservation:
    return CharacterizationObservation(
        observation_id=f"obs-{n}",
        trial_id=f"trial-{n}",
        source_commit_sha=source,
        environment_fingerprint_sha256=env,
        workload_id=workload,
        peak_rss_bytes=peak_rss_bytes if peak_rss_bytes is not None else n * 100,
        latency_ns=latency_ns if latency_ns is not None else n * 1000,
        quality_bp=quality_bp if quality_bp is not None else 8000 + n,
        evidence_refs=(f"run-package:{n}", f"measurement-row:{n}"),
    )


class CharacterizationContractTests(unittest.TestCase):
    def test_matching_cohort_summarizes_with_nearest_rank(self) -> None:
        summary = summarize_characterization(
            [
                observation(1, peak_rss_bytes=100, latency_ns=1000, quality_bp=7000),
                observation(2, peak_rss_bytes=300, latency_ns=3000, quality_bp=9000),
                observation(3, peak_rss_bytes=200, latency_ns=2000, quality_bp=8000),
            ],
            cohort_id="cohort-a",
        )
        self.assertEqual(summary.sample_count, 3)
        self.assertEqual(summary.peak_rss_p50_bytes, 200)
        self.assertEqual(summary.peak_rss_p95_bytes, 300)
        self.assertEqual(summary.latency_p50_ns, 2000)
        self.assertEqual(summary.latency_p95_ns, 3000)
        self.assertEqual(summary.quality_p05_bp, 7000)
        self.assertEqual(summary.quality_p50_bp, 8000)

    def test_permutation_invariant_summary_digest(self) -> None:
        items = [observation(1), observation(2), observation(3), observation(4)]
        a = summarize_characterization(items, cohort_id="cohort-a")
        b = summarize_characterization(list(reversed(items)), cohort_id="cohort-a")
        self.assertEqual(a.as_dict(), b.as_dict())
        self.assertEqual(a.sha256(), b.sha256())

    def test_observation_evidence_refs_are_canonicalized(self) -> None:
        item = CharacterizationObservation(
            observation_id="obs-x",
            trial_id="trial-x",
            source_commit_sha=SOURCE,
            environment_fingerprint_sha256=ENV,
            workload_id="w",
            peak_rss_bytes=1,
            latency_ns=2,
            quality_bp=3,
            evidence_refs=("z", "a"),
        )
        self.assertEqual(item.evidence_refs, ("a", "z"))

    def test_mixed_source_commit_fails_closed(self) -> None:
        with self.assertRaisesRegex(CharacterizationError, "mixed source_commit_sha"):
            summarize_characterization(
                [observation(1), observation(2), observation(3, source="c" * 40)],
                cohort_id="cohort-a",
            )

    def test_mixed_environment_fails_closed(self) -> None:
        with self.assertRaisesRegex(CharacterizationError, "mixed environment"):
            summarize_characterization(
                [observation(1), observation(2), observation(3, env="d" * 64)],
                cohort_id="cohort-a",
            )

    def test_mixed_workload_fails_closed(self) -> None:
        with self.assertRaisesRegex(CharacterizationError, "mixed workload_id"):
            summarize_characterization(
                [observation(1), observation(2), observation(3, workload="other")],
                cohort_id="cohort-a",
            )

    def test_duplicate_observation_id_fails_closed(self) -> None:
        duplicate = observation(3)
        object.__setattr__(duplicate, "observation_id", "obs-2")
        with self.assertRaisesRegex(CharacterizationError, "duplicate observation_id"):
            summarize_characterization(
                [observation(1), observation(2), duplicate],
                cohort_id="cohort-a",
            )

    def test_duplicate_trial_id_fails_closed(self) -> None:
        duplicate = observation(3)
        object.__setattr__(duplicate, "trial_id", "trial-2")
        with self.assertRaisesRegex(CharacterizationError, "duplicate trial_id"):
            summarize_characterization(
                [observation(1), observation(2), duplicate],
                cohort_id="cohort-a",
            )

    def test_requires_at_least_three_samples(self) -> None:
        with self.assertRaisesRegex(CharacterizationError, "length must be"):
            summarize_characterization([observation(1), observation(2)], cohort_id="cohort-a")

    def test_quality_is_basis_points_and_bool_is_rejected(self) -> None:
        with self.assertRaises(CharacterizationError):
            observation(1, quality_bp=10001)
        with self.assertRaises(CharacterizationError):
            observation(1, quality_bp=True)

    def test_resource_and_latency_must_be_positive_exact_ints(self) -> None:
        with self.assertRaises(CharacterizationError):
            observation(1, peak_rss_bytes=0)
        with self.assertRaises(CharacterizationError):
            observation(1, latency_ns=True)

    def test_missing_evidence_fails_closed(self) -> None:
        with self.assertRaisesRegex(CharacterizationError, "must not be empty"):
            CharacterizationObservation(
                observation_id="obs-x",
                trial_id="trial-x",
                source_commit_sha=SOURCE,
                environment_fingerprint_sha256=ENV,
                workload_id="w",
                peak_rss_bytes=1,
                latency_ns=2,
                quality_bp=3,
                evidence_refs=(),
            )

    def test_invalid_source_and_environment_digests_fail_closed(self) -> None:
        with self.assertRaises(CharacterizationError):
            observation(1, source="A" * 40)
        with self.assertRaises(CharacterizationError):
            observation(1, env="b" * 63)

    def test_output_never_mints_runtime_or_effect_authority(self) -> None:
        summary = summarize_characterization(
            [observation(1), observation(2), observation(3)],
            cohort_id="cohort-a",
        ).as_dict()
        self.assertEqual(summary["runtime_attestation"], "NONE")
        self.assertEqual(summary["truth_authority"], "NONE")
        self.assertEqual(summary["effect_authority"], "NONE")
        self.assertEqual(summary["completion_authority"], "NONE")
        self.assertEqual(summary["physical_grid10_credit"], 0)
        self.assertEqual(summary["whole_system_credit"], 0)

    def test_observation_digest_changes_with_evidence_identity(self) -> None:
        a = observation(1)
        b = CharacterizationObservation(
            observation_id=a.observation_id,
            trial_id=a.trial_id,
            source_commit_sha=a.source_commit_sha,
            environment_fingerprint_sha256=a.environment_fingerprint_sha256,
            workload_id=a.workload_id,
            peak_rss_bytes=a.peak_rss_bytes,
            latency_ns=a.latency_ns,
            quality_bp=a.quality_bp,
            evidence_refs=("different-evidence",),
        )
        self.assertNotEqual(a.sha256(), b.sha256())


if __name__ == "__main__":
    unittest.main()
