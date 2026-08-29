#!/usr/bin/env python3
"""REVIEW_ONLY falsifiers for F2-WP-505 ControlSnapshot binding.

These tests intentionally target the candidate implementation on
chatgpt/f2-wp505-adaptive-compute-g1-20260829. They do not claim mutation authority.
"""
from __future__ import annotations

import unittest

from frankenstein2.adaptive_compute import AdaptiveComputeError, build_allocation_candidate
from test_adaptive_compute import make_plan, make_policy, snapshot


class WP505ControlSnapshotBindingFalsifiers(unittest.TestCase):
    def test_invalid_control_snapshot_schema_fails_closed(self):
        forged = snapshot(schema="FORGED_CONTROL_SNAPSHOT/v0")
        with self.assertRaises(AdaptiveComputeError):
            build_allocation_candidate(make_plan(), forged, make_policy())

    def test_structurally_empty_control_snapshot_fails_closed(self):
        # WP501 policies require at least one envelope band, so a valid evaluated
        # ControlSnapshot cannot contain an empty signal_results tuple. Accepting this
        # value would let a directly constructed dataclass bypass WP501 evaluation.
        forged = snapshot(signal_results=())
        with self.assertRaises(AdaptiveComputeError):
            build_allocation_candidate(make_plan(), forged, make_policy())


if __name__ == "__main__":
    unittest.main()
