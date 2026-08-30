from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.whole_system_characterization import (
    DEFAULT_METRIC_SCHEMA,
    CharacterizationSample,
    WholeSystemCharacterizationError,
    characterize_measurements,
)

SOURCE = "1" * 64
LOOP = "2" * 64
ENV = "3" * 64


def _sample(sample_id: str, latency: int, rss: int, quality: int) -> CharacterizationSample:
    return CharacterizationSample(
        sample_id=sample_id,
        source_bundle_sha256=SOURCE,
        whole_loop_seal_sha256=LOOP,
        environment_fingerprint_sha256=ENV,
        metric_schema_id=DEFAULT_METRIC_SCHEMA,
        latency_ns=latency,
        peak_rss_bytes=rss,
        quality_micros=quality,
        provenance_refs=(f"run/{sample_id}", "wp900/seal"),
    )


def _family():
    return (
        _sample("s1", 100, 1000, 700_000),
        _sample("s2", 200, 2000, 800_000),
        _sample("s3", 300, 3000, 900_000),
        _sample("s4", 400, 4000, 1_000_000),
    )


class WholeSystemCharacterizationTests(unittest.TestCase):
    def test_homogeneous_measurements_produce_deterministic_nearest_rank_summary(self) -> None:
        report = characterize_measurements(
            _family(),
            expected_source_bundle_sha256=SOURCE,
            expected_whole_loop_seal_sha256=LOOP,
            expected_environment_fingerprint_sha256=ENV,
        )
        self.assertEqual(report.sample_count, 4)
        self.assertEqual((report.latency_ns_min, report.latency_ns_p50, report.latency_ns_p95, report.latency_ns_max), (100, 200, 400, 400))
        self.assertEqual((report.peak_rss_bytes_min, report.peak_rss_bytes_p50, report.peak_rss_bytes_p95, report.peak_rss_bytes_max), (1000, 2000, 4000, 4000))
        self.assertEqual((report.quality_micros_min, report.quality_micros_p50, report.quality_micros_p95, report.quality_micros_max), (700_000, 800_000, 1_000_000, 1_000_000))

    def test_input_order_cannot_change_report_identity(self) -> None:
        a = characterize_measurements(_family(), expected_source_bundle_sha256=SOURCE, expected_whole_loop_seal_sha256=LOOP, expected_environment_fingerprint_sha256=ENV)
        b = characterize_measurements(tuple(reversed(_family())), expected_source_bundle_sha256=SOURCE, expected_whole_loop_seal_sha256=LOOP, expected_environment_fingerprint_sha256=ENV)
        self.assertEqual(a.as_dict(), b.as_dict())
        self.assertEqual(a.sha256(), b.sha256())

    def test_mixed_source_family_fails_closed(self) -> None:
        family = list(_family())
        family[-1] = replace(family[-1], source_bundle_sha256="4" * 64)
        with self.assertRaisesRegex(WholeSystemCharacterizationError, "identity mismatch"):
            characterize_measurements(family, expected_source_bundle_sha256=SOURCE, expected_whole_loop_seal_sha256=LOOP, expected_environment_fingerprint_sha256=ENV)

    def test_mixed_whole_loop_seal_fails_closed(self) -> None:
        family = list(_family())
        family[-1] = replace(family[-1], whole_loop_seal_sha256="5" * 64)
        with self.assertRaisesRegex(WholeSystemCharacterizationError, "identity mismatch"):
            characterize_measurements(family, expected_source_bundle_sha256=SOURCE, expected_whole_loop_seal_sha256=LOOP, expected_environment_fingerprint_sha256=ENV)

    def test_mixed_environment_fails_closed(self) -> None:
        family = list(_family())
        family[-1] = replace(family[-1], environment_fingerprint_sha256="6" * 64)
        with self.assertRaisesRegex(WholeSystemCharacterizationError, "identity mismatch"):
            characterize_measurements(family, expected_source_bundle_sha256=SOURCE, expected_whole_loop_seal_sha256=LOOP, expected_environment_fingerprint_sha256=ENV)

    def test_metric_schema_mismatch_fails_closed(self) -> None:
        family = list(_family())
        family[-1] = replace(family[-1], metric_schema_id="metrics/v2")
        with self.assertRaisesRegex(WholeSystemCharacterizationError, "identity mismatch"):
            characterize_measurements(family, expected_source_bundle_sha256=SOURCE, expected_whole_loop_seal_sha256=LOOP, expected_environment_fingerprint_sha256=ENV)

    def test_duplicate_sample_identity_fails_closed(self) -> None:
        family = (_family()[0], replace(_family()[1], sample_id="s1"))
        with self.assertRaisesRegex(WholeSystemCharacterizationError, "duplicate sample_id"):
            characterize_measurements(family, expected_source_bundle_sha256=SOURCE, expected_whole_loop_seal_sha256=LOOP, expected_environment_fingerprint_sha256=ENV)

    def test_invalid_measurement_domains_fail_closed(self) -> None:
        with self.assertRaisesRegex(WholeSystemCharacterizationError, "latency_ns"):
            _sample("bad-latency", -1, 1, 1)
        with self.assertRaisesRegex(WholeSystemCharacterizationError, "peak_rss_bytes"):
            _sample("bad-rss", 1, -1, 1)
        with self.assertRaisesRegex(WholeSystemCharacterizationError, "quality_micros"):
            _sample("bad-quality", 1, 1, 1_000_001)

    def test_empty_family_fails_closed(self) -> None:
        with self.assertRaisesRegex(WholeSystemCharacterizationError, "must not be empty"):
            characterize_measurements((), expected_source_bundle_sha256=SOURCE, expected_whole_loop_seal_sha256=LOOP, expected_environment_fingerprint_sha256=ENV)

    def test_report_explicitly_carries_zero_authority(self) -> None:
        report = characterize_measurements(_family(), expected_source_bundle_sha256=SOURCE, expected_whole_loop_seal_sha256=LOOP, expected_environment_fingerprint_sha256=ENV)
        payload = report.as_dict()
        self.assertEqual(payload["runtime_authority"], "NONE")
        self.assertEqual(payload["truth_authority"], "NONE")
        self.assertEqual(payload["effect_authority"], "NONE")
        self.assertEqual(payload["completion_authority"], "NONE")
        self.assertFalse(payload["whole_system_acceptance"])


if __name__ == "__main__":
    unittest.main()
