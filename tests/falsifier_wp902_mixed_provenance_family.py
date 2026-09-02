#!/usr/bin/env python3
"""REVIEW_ONLY candidate falsifier for F2-WP-902 provenance-family admission.

This file does not claim WP902 mutation authority. It tests one narrow contract question:
can samples with identical source/loop/environment/metric identities but no shared provenance
anchor be aggregated into one characterization family despite the WP902 prohibition on
mixed-provenance aggregation?

Expected pre-repair result: FAILURE because characterize_measurements currently admits the
family. A failure is negative repository-component evidence only, not target-runtime or
whole-system evidence.
"""
from __future__ import annotations

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


def sample(sample_id: str, provenance_refs: tuple[str, ...]) -> CharacterizationSample:
    return CharacterizationSample(
        sample_id=sample_id,
        source_bundle_sha256=SOURCE,
        whole_loop_seal_sha256=LOOP,
        environment_fingerprint_sha256=ENV,
        metric_schema_id=DEFAULT_METRIC_SCHEMA,
        latency_ns=100,
        peak_rss_bytes=1000,
        quality_micros=900_000,
        provenance_refs=provenance_refs,
    )


class MixedProvenanceFamilyFalsifier(unittest.TestCase):
    def test_disjoint_provenance_families_fail_closed(self) -> None:
        family = (
            sample("sample-a", ("campaign:A", "run:A/1", "observer:A")),
            sample("sample-b", ("campaign:B", "run:B/1", "observer:B")),
        )
        with self.assertRaises(WholeSystemCharacterizationError):
            characterize_measurements(
                family,
                expected_source_bundle_sha256=SOURCE,
                expected_whole_loop_seal_sha256=LOOP,
                expected_environment_fingerprint_sha256=ENV,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
