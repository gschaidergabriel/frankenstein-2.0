#!/usr/bin/env python3
"""REVIEW_ONLY fail-closed ControlSnapshot falsifiers for current F2-WP-505."""
from __future__ import annotations

import unittest

from frankenstein2.adaptive_compute import AdaptiveComputeError, build_allocation_candidate
from frankenstein2.cognitive_envelope import ControlSnapshot, DISPOSITION_WITHIN
from test_adaptive_compute import make_plan, make_policy


def forged_snapshot(*, schema="FRANKENSTEIN2_CONTROL_SNAPSHOT/v1") -> ControlSnapshot:
    plan = make_plan()
    return ControlSnapshot(
        schema=schema,
        policy_id=plan.policy_id,
        policy_generation=plan.policy_generation,
        policy_sha256=plan.policy_sha256,
        readout_set_sha256="c" * 64,
        signal_results=(),
        disposition=DISPOSITION_WITHIN,
        regulation_candidate="NO_REGULATION_CHANGE_CANDIDATE",
    )


class WP505CurrentMainControlSnapshotFalsifiers(unittest.TestCase):
    def test_invalid_snapshot_schema_fails_closed(self):
        with self.assertRaises(AdaptiveComputeError):
            build_allocation_candidate(
                make_plan(),
                forged_snapshot(schema="FORGED_CONTROL_SNAPSHOT/v0"),
                make_policy(),
            )

    def test_structurally_empty_snapshot_fails_closed(self):
        # The canonical WP501 policy used by make_plan has one required band. A valid
        # evaluated WITHIN_ENVELOPE snapshot therefore cannot have zero signal results.
        with self.assertRaises(AdaptiveComputeError):
            build_allocation_candidate(make_plan(), forged_snapshot(), make_policy())


if __name__ == "__main__":
    unittest.main()
