#!/usr/bin/env python3
from __future__ import annotations

import unittest

from frankenstein2.optional_vps_bridge import (
    BridgeAction,
    BridgeDisposition,
    BridgeValidationError,
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


def local(*, boot_state: EvidenceState = EvidenceState.VERIFIED) -> LocalRuntimeIdentity:
    return LocalRuntimeIdentity.create(
        runtime_id="local-runtime-1",
        release_digest=SHA_A,
        state_lineage_id="state-lineage-1",
        state_generation=7,
        baseline_boot_state=boot_state,
        baseline_boot_evidence_ref="receipt:local-boot-1" if boot_state is EvidenceState.VERIFIED else None,
    )


def remote(
    *,
    availability: EvidenceState = EvidenceState.VERIFIED,
    lineage: str = "state-lineage-1",
    typed: bool = True,
) -> RemoteEndpointEvidence:
    return RemoteEndpointEvidence.create(
        endpoint_id="clay-direct-dev",
        transport="TYPED_BRIDGE/v1",
        environment_digest=SHA_B,
        capability_report_digest=SHA_C,
        bound_local_state_lineage_id=lineage,
        availability_state=availability,
        availability_evidence_ref="receipt:bridge-health-1" if availability is EvidenceState.VERIFIED else None,
        typed_request_result_transport=typed,
    )


class OptionalVPSBridgeTests(unittest.TestCase):
    def test_attach_requires_verified_local_boot_and_remote_evidence(self) -> None:
        plan = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        self.assertEqual(plan.disposition, BridgeDisposition.ATTACHED)
        self.assertTrue(plan.baseline_local_boot_independent)
        self.assertTrue(plan.remote_optional)
        self.assertTrue(plan.typed_request_result_transport)
        self.assertEqual(plan.blockers, ())
        self.assertEqual(plan.target_runtime_credit, 0)
        self.assertFalse(plan.whole_system_acceptance)

    def test_attach_without_remote_evidence_fails_closed(self) -> None:
        plan = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH)
        self.assertEqual(plan.disposition, BridgeDisposition.BLOCKED)
        self.assertIn("REMOTE_ENDPOINT_EVIDENCE_MISSING", plan.blockers)

    def test_unverified_local_boot_blocks_attach(self) -> None:
        plan = plan_optional_bridge(
            local=local(boot_state=EvidenceState.DECLARED_ONLY),
            action=BridgeAction.ATTACH,
            remote=remote(),
        )
        self.assertEqual(plan.disposition, BridgeDisposition.BLOCKED)
        self.assertIn("BASELINE_LOCAL_BOOT_NOT_VERIFIED_INDEPENDENTLY", plan.blockers)

    def test_remote_lineage_mismatch_blocks_attach(self) -> None:
        plan = plan_optional_bridge(
            local=local(),
            action=BridgeAction.ATTACH,
            remote=remote(lineage="other-lineage"),
        )
        self.assertEqual(plan.disposition, BridgeDisposition.BLOCKED)
        self.assertIn("REMOTE_STATE_LINEAGE_BINDING_MISMATCH", plan.blockers)

    def test_unverified_or_untyped_remote_blocks_attach(self) -> None:
        plan = plan_optional_bridge(
            local=local(),
            action=BridgeAction.ATTACH,
            remote=remote(availability=EvidenceState.UNKNOWN, typed=False),
        )
        self.assertEqual(plan.disposition, BridgeDisposition.BLOCKED)
        self.assertIn("REMOTE_AVAILABILITY_NOT_VERIFIED", plan.blockers)
        self.assertIn("REMOTE_TRANSPORT_NOT_TYPED_REQUEST_RESULT", plan.blockers)

    def test_detach_needs_no_remote_availability_and_preserves_local_lineage(self) -> None:
        plan = plan_optional_bridge(local=local(), action=BridgeAction.DETACH)
        self.assertEqual(plan.disposition, BridgeDisposition.DETACHED)
        self.assertEqual(plan.state_lineage_id, "state-lineage-1")
        self.assertTrue(plan.remote_optional)
        self.assertIsNone(plan.remote_endpoint_digest)
        self.assertEqual(plan.target_runtime_credit, 0)

    def test_remote_endpoint_cannot_claim_second_authority(self) -> None:
        with self.assertRaisesRegex(BridgeValidationError, "SECOND_AUTHORITY"):
            RemoteEndpointEvidence.create(
                endpoint_id="bad-remote",
                transport="typed",
                environment_digest=SHA_B,
                capability_report_digest=SHA_C,
                bound_local_state_lineage_id="state-lineage-1",
                availability_state=EvidenceState.VERIFIED,
                availability_evidence_ref="receipt:x",
                typed_request_result_transport=True,
                truth_authority=True,
            )

    def test_remote_return_is_identity_bound_but_never_truth_or_effect_credit(self) -> None:
        plan = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        result = validate_remote_return(
            plan=plan,
            returned_state_lineage_id="state-lineage-1",
            request_digest=SHA_C,
            result_digest=SHA_D,
        )
        self.assertTrue(result["identity_binding_valid"])
        self.assertTrue(result["candidate_or_projection_only"])
        self.assertEqual(result["canonical_truth_credit"], 0)
        self.assertEqual(result["effect_completion_credit"], 0)
        self.assertEqual(result["target_runtime_credit"], 0)
        self.assertFalse(result["whole_system_acceptance"])

    def test_remote_return_wrong_lineage_fails_closed(self) -> None:
        plan = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        with self.assertRaisesRegex(BridgeValidationError, "STATE_LINEAGE_MISMATCH"):
            validate_remote_return(
                plan=plan,
                returned_state_lineage_id="other-lineage",
                request_digest=SHA_C,
                result_digest=SHA_D,
            )

    def test_plan_digest_is_deterministic(self) -> None:
        left = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        right = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        self.assertEqual(left.canonical_json(), right.canonical_json())
        self.assertEqual(left.plan_digest(), right.plan_digest())


if __name__ == "__main__":
    unittest.main()
