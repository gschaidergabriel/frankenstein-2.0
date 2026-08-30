#!/usr/bin/env python3
"""REVIEW_ONLY falsifier for F2-WP-902 direct report construction.

Expected invariant: a public characterization report must not be constructible as if it
were a deterministic summary without binding/revalidating the concrete measurement family
that produced its sample-set digest.  A green canonical repair should make this forged
report construction fail closed (or move consumers behind an equivalent validating factory).
"""
from __future__ import annotations

import unittest

from frankenstein2.whole_system_characterization import (
    DEFAULT_METRIC_SCHEMA,
    CharacterizationReport,
    WholeSystemCharacterizationError,
)


class WP902DirectReportForgeryFalsifier(unittest.TestCase):
    def test_direct_constructor_cannot_forge_unbound_summary(self) -> None:
        with self.assertRaises(WholeSystemCharacterizationError):
            CharacterizationReport(
                source_bundle_sha256="1" * 64,
                whole_loop_seal_sha256="2" * 64,
                environment_fingerprint_sha256="3" * 64,
                metric_schema_id=DEFAULT_METRIC_SCHEMA,
                sample_count=4,
                # This digest is caller-invented; no concrete sample family is supplied.
                sample_set_sha256="4" * 64,
                # Internally monotonic but wholly caller-forged summaries.
                latency_ns_min=1,
                latency_ns_p50=2,
                latency_ns_p95=3,
                latency_ns_max=4,
                peak_rss_bytes_min=10,
                peak_rss_bytes_p50=20,
                peak_rss_bytes_p95=30,
                peak_rss_bytes_max=40,
                quality_micros_min=100,
                quality_micros_p50=200,
                quality_micros_p95=300,
                quality_micros_max=400,
            )


if __name__ == "__main__":
    unittest.main()
