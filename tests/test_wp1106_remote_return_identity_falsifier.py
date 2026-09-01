#!/usr/bin/env python3
"""REVIEW_ONLY executable falsifier for F2-WP-1106 issue #503.

This file intentionally expects the current accepted G2 implementation to fail until
remote-return validation binds both the returning endpoint and a request identity sealed
to the exact attached bridge plan. It claims no mutation authority or runtime credit.
"""
from __future__ import annotations

import inspect
import unittest

from frankenstein2.optional_vps_bridge import (
    BridgeAction,
    EvidenceState,
    LocalRuntimeIdentity,
    RemoteEndpointEvidence,
    plan_optional_bridge,
    validate_remote_return,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64


def local() -> LocalRuntimeIdentity:
    return LocalRuntimeIdentity.create(
        runtime_id="local-runtime-issue503",
        release_digest=SHA_A,
        state_lineage_id="state-lineage-issue503",
        state_generation=7,
        baseline_boot_state=EvidenceState.VERIFIED,
        baseline_boot_evidence_ref="receipt:local-boot-issue503",
    )


def remote() -> RemoteEndpointEvidence:
    return RemoteEndpointEvidence.create(
        endpoint_id="remote-a",
        transport="TYPED_BRIDGE/v1",
        environment_digest=SHA_B,
        capability_report_digest=SHA_C,
        bound_local_state_lineage_id="state-lineage-issue503",
        availability_state=EvidenceState.VERIFIED,
        availability_evidence_ref="receipt:remote-a-available",
        typed_request_result_transport=True,
    )


class WP1106RemoteReturnIdentityFalsifier(unittest.TestCase):
    def test_validator_requires_returning_endpoint_identity(self) -> None:
        """A return validator cannot reject endpoint B if endpoint identity is not an input."""
        parameters = inspect.signature(validate_remote_return).parameters
        self.assertIn(
            "returned_remote_endpoint_digest",
            parameters,
            "ISSUE503_REPRODUCED: validate_remote_return has no returning-endpoint identity input",
        )

    def test_one_attached_plan_cannot_accept_two_distinct_request_identities(self) -> None:
        """The exact attached plan must seal one admitted request identity, not arbitrary SHA syntax."""
        plan = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())

        first = validate_remote_return(
            plan=plan,
            returned_state_lineage_id=plan.state_lineage_id,
            request_digest=SHA_D,
            result_digest=SHA_C,
        )
        second = validate_remote_return(
            plan=plan,
            returned_state_lineage_id=plan.state_lineage_id,
            request_digest=SHA_E,
            result_digest=SHA_C,
        )

        self.assertTrue(first["identity_binding_valid"])
        self.assertFalse(
            second["identity_binding_valid"],
            "ISSUE503_REPRODUCED: one unchanged attached plan accepted a second arbitrary request digest",
        )


if __name__ == "__main__":
    unittest.main()
