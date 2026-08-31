#!/usr/bin/env python3
"""Cross-component lineage handoff: WP1105 -> WP1207 -> WP1109.

Repository integration only. This test does not install, switch a host, mutate durable
state, or mint runtime/physical/completion credit.
"""
from __future__ import annotations

import unittest

from frankenstein2.host_transition import (
    OP_SWITCH_HOST,
    ROUTE_NATIVE,
    CanonicalStateBinding,
    HostRouteEvidence,
    HostTransitionError,
    HostTransitionRequest,
    plan_host_transition,
)
from frankenstein2.portable_release_transaction import (
    LINEAGE_SCHEMA as RELEASE_LINEAGE_SCHEMA,
    RELEASE_SCHEMA,
    REQUEST_SCHEMA as RELEASE_REQUEST_SCHEMA,
    ReleaseIdentity,
    build_transaction_plan,
    record_attempt,
)
from frankenstein2.state_migration import (
    STORAGE_CANONICAL_DURABLE,
    StateLineage,
    StateRootIdentity,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64


def release(release_id: str, version: str, artifact: str, manifest: str) -> dict[str, str]:
    return {
        "schema": RELEASE_SCHEMA,
        "release_id": release_id,
        "version": version,
        "artifact_sha256": artifact,
        "manifest_sha256": manifest,
    }


class StateReleaseHostLineageHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = StateRootIdentity.create(
            root_id="canonical-root",
            path="/var/lib/frankenstein2/state",
            storage_class=STORAGE_CANONICAL_DURABLE,
            host_identity_sha256=A,
            observed_root_fingerprint_sha256=B,
        )
        self.lineage = StateLineage.create(
            lineage_id="canonical-lineage-001",
            generation=7,
            state_sha256=C,
            root=self.root,
        )
        self.r1 = release("frankenstein-2.0-r1", "2.0.0-r1", D, E)
        self.r2 = release("frankenstein-2.0-r2", "2.0.0-r2", E, F)

    def _successful_update_receipt(self):
        current_release_digest = ReleaseIdentity.from_mapping(self.r1).digest()
        plan = build_transaction_plan(
            {
                "schema": RELEASE_REQUEST_SCHEMA,
                "attempt_id": "portable-update-001",
                "operation": "UPDATE",
                "target_release": self.r2,
                "current_lineage": {
                    "schema": RELEASE_LINEAGE_SCHEMA,
                    "generation": self.lineage.generation,
                    "state_sha256": self.lineage.state_sha256,
                    "active_release_digest": current_release_digest,
                    "predecessor_generation": None,
                    "predecessor_state_sha256": None,
                    "predecessor_release_digest": None,
                },
                "expected_generation": self.lineage.generation,
                "expected_state_sha256": self.lineage.state_sha256,
                "rollback_release": None,
                "injected_failure_stage": None,
            }
        )
        receipt = record_attempt(
            plan,
            outcome="SUCCEEDED",
            observed_generation=plan.next_generation,
            observed_state_sha256=A,
        )
        return plan, receipt

    def _post_update_state(self, receipt) -> CanonicalStateBinding:
        return CanonicalStateBinding.create(
            lineage_id=self.lineage.lineage_id,
            generation=receipt.observed_generation,
            state_sha256=receipt.observed_state_sha256,
            root_path=self.lineage.root.path,
        )

    def test_same_canonical_lineage_survives_portable_update_into_host_switch_plan(self) -> None:
        release_plan, receipt = self._successful_update_receipt()
        state = self._post_update_state(receipt)
        successor = HostRouteEvidence.create(
            host_id="successor-host",
            route_id="native-route",
            route_status=ROUTE_NATIVE,
            capability_evidence_ref="capability:successor-host",
            lifecycle_firing_evidence_ref="lifecycle:successor-host",
            state_readback_evidence_ref="readback:successor-host",
            state_readback_lineage_id=state.lineage_id,
            state_readback_generation=state.generation,
            state_readback_state_sha256=state.state_sha256,
            state_readback_binding_sha256=state.sha256(),
        )
        transition = HostTransitionRequest.create(
            transition_id="switch-after-portable-update",
            operation=OP_SWITCH_HOST,
            source_host_id="source-host",
            source_route_id="source-route",
            state=state,
            permissions_before=("state.read", "runtime.execute"),
            permissions_after=("state.read", "runtime.execute"),
            successor_route=successor,
        )
        host_plan = plan_host_transition(transition)

        self.assertEqual(release_plan.source_generation, 7)
        self.assertEqual(receipt.observed_generation, 8)
        self.assertEqual(host_plan.state_lineage_id, self.lineage.lineage_id)
        self.assertEqual(host_plan.state_generation, receipt.observed_generation)
        self.assertEqual(state.state_sha256, receipt.observed_state_sha256)
        self.assertEqual(host_plan.state_binding_sha256, state.sha256())
        self.assertEqual(host_plan.target_host_id, "successor-host")
        self.assertEqual(host_plan.runtime_credit, 0)
        self.assertEqual(host_plan.physical_host_credit, 0)
        self.assertFalse(host_plan.whole_system_acceptance)

    def test_successor_readback_cannot_substitute_pre_update_state(self) -> None:
        _, receipt = self._successful_update_receipt()
        state = self._post_update_state(receipt)
        stale = HostRouteEvidence.create(
            host_id="successor-host",
            route_id="native-route",
            route_status=ROUTE_NATIVE,
            capability_evidence_ref="capability:successor-host",
            lifecycle_firing_evidence_ref="lifecycle:successor-host",
            state_readback_evidence_ref="readback:successor-host",
            state_readback_lineage_id=self.lineage.lineage_id,
            state_readback_generation=self.lineage.generation,
            state_readback_state_sha256=self.lineage.state_sha256,
            state_readback_binding_sha256=CanonicalStateBinding.create(
                lineage_id=self.lineage.lineage_id,
                generation=self.lineage.generation,
                state_sha256=self.lineage.state_sha256,
                root_path=self.lineage.root.path,
            ).sha256(),
        )
        with self.assertRaisesRegex(HostTransitionError, "generation mismatch"):
            HostTransitionRequest.create(
                transition_id="reject-stale-readback",
                operation=OP_SWITCH_HOST,
                source_host_id="source-host",
                source_route_id="source-route",
                state=state,
                permissions_before=("state.read",),
                permissions_after=("state.read",),
                successor_route=stale,
            )


if __name__ == "__main__":
    unittest.main()
