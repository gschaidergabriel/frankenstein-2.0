#!/usr/bin/env python3
"""REVIEW_ONLY executable falsifier for F2-WP-1104.

A green test means the current source still accepts a directly constructed
HostCapabilityReport that never traversed assess_host_adapter(). This is
counterevidence against treating HostCapabilityReport.report_digest() as
producer-lineage proof.

This file does not modify WP1104-owned source and mints no runtime/host credit.
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


class WP1104ForgedHostCapabilityReportFalsifier(unittest.TestCase):
    def test_direct_report_constructor_bypasses_required_lifecycle_and_capability_assessment(self) -> None:
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

        # Reproduction criterion: a report with no assessed lifecycle/capability
        # evidence is accepted as ADAPTED with no fail-closed limitation.
        self.assertIs(route.classification, AdapterClass.ADAPTED)
        self.assertEqual(route.limitations, ())
        self.assertEqual(route.capability_report_digest, forged.report_digest())


if __name__ == "__main__":
    unittest.main()
