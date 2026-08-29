#!/usr/bin/env python3
"""REVIEW_ONLY successor falsifier against PR #470 candidate repair.

A green test reproduces that PR470's classification-consistency guard still
accepts an internally consistent but never-assessed HostCapabilityReport.
"""

import unittest

from frankenstein2.generic_agent_route import (
    ReleaseBinding,
    StateRootClass,
    plan_generic_agent_route,
)
from frankenstein2.host_adapter_abi import (
    AdapterClass,
    CAPABILITY_REPORT_SCHEMA,
    HostCapabilityReport,
)


class WP1104ProducerLineageVsPR470(unittest.TestCase):
    def test_pr470_consistency_guard_does_not_prove_assessment_producer_lineage(self) -> None:
        env_digest = "a" * 64
        forged = HostCapabilityReport(
            schema=CAPABILITY_REPORT_SCHEMA,
            classification=AdapterClass.ADAPTED,
            environment_binding_digest=env_digest,
            state_lineage_id="lineage-1",
            required_roles=(),
            required_capabilities=(),
            optional_roles=(),
            optional_capabilities=(),
            missing_required_roles=(),
            unverified_required_roles=(),
            missing_optional_roles=(),
            missing_required_capabilities=(),
            unverified_required_capabilities=(),
            missing_optional_capabilities=(),
            conflicts=(),
            limitations=(),
            native_surface_complete=False,
            completion_authority=False,
            physical_host_credit=False,
        )
        release = ReleaseBinding.create(
            release_id="f2-review-release",
            release_manifest_digest="b" * 64,
            source_commit="c" * 40,
            state_migration_version="v1",
        )

        route = plan_generic_agent_route(
            host_family="unknown-generic-agent",
            host_version="0",
            release=release,
            capability_report=forged,
            environment_binding_digest=env_digest,
            state_lineage_id="lineage-1",
            durable_state_root="/var/lib/frankenstein2",
            state_root_class=StateRootClass.DURABLE_USER_DATA,
        )

        self.assertIs(route.classification, AdapterClass.ADAPTED)
        self.assertEqual(route.limitations, ())
        self.assertEqual(route.capability_report_digest, forged.report_digest())


if __name__ == "__main__":
    unittest.main()
