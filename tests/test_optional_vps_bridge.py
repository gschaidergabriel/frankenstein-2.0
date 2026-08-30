#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.optional_vps_bridge import (
    BridgeAction,
    BridgeDisposition,
    BridgeValidationError,
    EvidenceState,
    LocalRuntimeIdentity,
    RemoteEndpointEvidence,
    RemoteRequestBinding,
    bind_remote_request,
    plan_optional_bridge,
    validate_remote_return,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64


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
    endpoint_id: str = "clay-direct-dev",
    environment_digest: str = SHA_B,
    availability: EvidenceState = EvidenceState.VERIFIED,
    lineage: str = "state-lineage-1",
    typed: bool = True,
) -> RemoteEndpointEvidence:
    return RemoteEndpointEvidence.create(
        endpoint_id=endpoint_id,
        transport="TYPED_BRIDGE/v1",
        environment_digest=environment_digest,
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
        for state in (EvidenceState.DECLARED_ONLY, EvidenceState.UNKNOWN, EvidenceState.CONFLICT):
            with self.subTest(state=state):
                plan = plan_optional_bridge(
                    local=local(boot_state=state),
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

    def test_detach_is_not_blocked_by_unverified_baseline_boot(self) -> None:
        for state in (EvidenceState.DECLARED_ONLY, EvidenceState.UNKNOWN, EvidenceState.CONFLICT):
            with self.subTest(state=state):
                plan = plan_optional_bridge(local=local(boot_state=state), action=BridgeAction.DETACH)
                self.assertEqual(plan.disposition, BridgeDisposition.DETACHED)
                self.assertFalse(plan.baseline_local_boot_independent)
                self.assertEqual(plan.blockers, ())
                self.assertIn("DETACH_BASELINE_LOCAL_BOOT_NOT_VERIFIED", plan.limitations)
                self.assertEqual(plan.state_lineage_id, "state-lineage-1")

    def test_detach_ignores_mismatched_remote_lineage_but_records_limitation(self) -> None:
        plan = plan_optional_bridge(
            local=local(boot_state=EvidenceState.UNKNOWN),
            action=BridgeAction.DETACH,
            remote=remote(lineage="stale-remote-lineage"),
        )
        self.assertEqual(plan.disposition, BridgeDisposition.DETACHED)
        self.assertIn("DETACH_IGNORES_MISMATCHED_REMOTE_LINEAGE_AND_PRESERVES_LOCAL", plan.limitations)
        self.assertEqual(plan.state_lineage_id, "state-lineage-1")

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

    def test_remote_request_binding_is_exact_and_non_authoritative(self) -> None:
        plan = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        binding = bind_remote_request(plan=plan, request_digest=SHA_C)
        self.assertEqual(binding.bridge_plan_digest, plan.plan_digest())
        self.assertEqual(binding.remote_endpoint_digest, plan.remote_endpoint_digest)
        self.assertEqual(binding.state_lineage_id, plan.state_lineage_id)
        self.assertEqual(binding.request_digest, SHA_C)
        self.assertTrue(binding.candidate_transport_only)
        self.assertEqual(binding.canonical_truth_credit, 0)
        self.assertEqual(binding.effect_completion_credit, 0)
        self.assertEqual(binding.target_runtime_credit, 0)
        self.assertFalse(binding.whole_system_acceptance)

    def test_remote_request_cannot_bind_to_detached_or_blocked_plan(self) -> None:
        detached = plan_optional_bridge(local=local(), action=BridgeAction.DETACH)
        blocked = plan_optional_bridge(local=local(boot_state=EvidenceState.UNKNOWN), action=BridgeAction.ATTACH, remote=remote())
        for plan in (detached, blocked):
            with self.subTest(disposition=plan.disposition):
                with self.assertRaisesRegex(BridgeValidationError, "WITHOUT_ATTACHED_PLAN"):
                    bind_remote_request(plan=plan, request_digest=SHA_C)

    def test_remote_return_is_endpoint_request_and_lineage_bound_but_never_truth_or_effect_credit(self) -> None:
        plan = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        binding = bind_remote_request(plan=plan, request_digest=SHA_C)
        result = validate_remote_return(
            plan=plan,
            request_binding=binding,
            returned_remote_endpoint_digest=plan.remote_endpoint_digest,
            returned_state_lineage_id="state-lineage-1",
            result_digest=SHA_D,
        )
        self.assertTrue(result["identity_binding_valid"])
        self.assertEqual(result["request_digest"], SHA_C)
        self.assertEqual(result["remote_endpoint_digest"], plan.remote_endpoint_digest)
        self.assertEqual(result["remote_request_binding_digest"], binding.binding_digest())
        self.assertTrue(result["candidate_or_projection_only"])
        self.assertEqual(result["canonical_truth_credit"], 0)
        self.assertEqual(result["effect_completion_credit"], 0)
        self.assertEqual(result["target_runtime_credit"], 0)
        self.assertFalse(result["whole_system_acceptance"])

    def test_remote_return_wrong_endpoint_fails_closed(self) -> None:
        plan = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        binding = bind_remote_request(plan=plan, request_digest=SHA_C)
        with self.assertRaisesRegex(BridgeValidationError, "RETURN_ENDPOINT_MISMATCH"):
            validate_remote_return(
                plan=plan,
                request_binding=binding,
                returned_remote_endpoint_digest=SHA_E,
                returned_state_lineage_id="state-lineage-1",
                result_digest=SHA_D,
            )

    def test_remote_return_binding_from_other_plan_fails_closed(self) -> None:
        plan_a = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        plan_b = plan_optional_bridge(
            local=local(),
            action=BridgeAction.ATTACH,
            remote=remote(endpoint_id="other-remote", environment_digest=SHA_E),
        )
        binding_a = bind_remote_request(plan=plan_a, request_digest=SHA_C)
        with self.assertRaisesRegex(BridgeValidationError, "REQUEST_BINDING_PLAN_MISMATCH"):
            validate_remote_return(
                plan=plan_b,
                request_binding=binding_a,
                returned_remote_endpoint_digest=plan_b.remote_endpoint_digest,
                returned_state_lineage_id="state-lineage-1",
                result_digest=SHA_D,
            )

    def test_remote_return_tampered_bound_request_fails_closed(self) -> None:
        plan = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        binding = bind_remote_request(plan=plan, request_digest=SHA_C)
        tampered = replace(binding, request_digest="not-a-sha")
        with self.assertRaisesRegex(BridgeValidationError, "BOUND_REQUEST_DIGEST_INVALID_SHA256"):
            validate_remote_return(
                plan=plan,
                request_binding=tampered,
                returned_remote_endpoint_digest=plan.remote_endpoint_digest,
                returned_state_lineage_id="state-lineage-1",
                result_digest=SHA_D,
            )

    def test_remote_return_wrong_lineage_fails_closed(self) -> None:
        plan = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        binding = bind_remote_request(plan=plan, request_digest=SHA_C)
        with self.assertRaisesRegex(BridgeValidationError, "STATE_LINEAGE_MISMATCH"):
            validate_remote_return(
                plan=plan,
                request_binding=binding,
                returned_remote_endpoint_digest=plan.remote_endpoint_digest,
                returned_state_lineage_id="other-lineage",
                result_digest=SHA_D,
            )

    def test_plan_and_request_binding_digests_are_deterministic(self) -> None:
        left = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        right = plan_optional_bridge(local=local(), action=BridgeAction.ATTACH, remote=remote())
        self.assertEqual(left.canonical_json(), right.canonical_json())
        self.assertEqual(left.plan_digest(), right.plan_digest())
        self.assertEqual(
            bind_remote_request(plan=left, request_digest=SHA_C).binding_digest(),
            bind_remote_request(plan=right, request_digest=SHA_C).binding_digest(),
        )


if __name__ == "__main__":
    unittest.main()
