from __future__ import annotations

import unittest

from frankenstein2.host_transition import (
    CanonicalStateBinding,
    HostRouteEvidence,
    HostTransitionError,
    HostTransitionRequest,
    OP_SWITCH_HOST,
    ROUTE_NATIVE,
    plan_host_transition,
)
from frankenstein2.state_migration import (
    STORAGE_CANONICAL_DURABLE,
    StateLineage,
    StateRootIdentity,
)


class WP1105WP1109StateLineageIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = StateRootIdentity.create(
            root_id="canonical-local-state",
            path="/var/lib/frankenstein2/state",
            storage_class=STORAGE_CANONICAL_DURABLE,
            host_identity_sha256="1" * 64,
            observed_root_fingerprint_sha256="2" * 64,
        )
        self.lineage = StateLineage.create(
            lineage_id="f2-canonical-state",
            generation=7,
            state_sha256="3" * 64,
            root=self.root,
        )
        self.binding = CanonicalStateBinding.create(
            lineage_id=self.lineage.lineage_id,
            generation=self.lineage.generation,
            state_sha256=self.lineage.state_sha256,
            root_path=self.lineage.root.path,
        )

    def successor(self, **overrides) -> HostRouteEvidence:
        values = {
            "host_id": "clean-host-b",
            "route_id": "native-route-b",
            "route_status": ROUTE_NATIVE,
            "capability_evidence_ref": "receipt:capability-b",
            "lifecycle_firing_evidence_ref": "receipt:lifecycle-b",
            "state_readback_evidence_ref": "receipt:state-readback-b",
            "state_readback_lineage_id": self.lineage.lineage_id,
            "state_readback_generation": self.lineage.generation,
            "state_readback_state_sha256": self.lineage.state_sha256,
            "state_readback_binding_sha256": self.binding.sha256(),
        }
        values.update(overrides)
        return HostRouteEvidence.create(**values)

    def test_wp1105_lineage_identity_survives_wp1109_switch_plan(self) -> None:
        request = HostTransitionRequest.create(
            transition_id="wp1105-to-wp1109-clean-host-switch",
            operation=OP_SWITCH_HOST,
            source_host_id="clean-host-a",
            source_route_id="native-route-a",
            state=self.binding,
            permissions_before=("memory.read",),
            permissions_after=("memory.read",),
            successor_route=self.successor(),
        )
        plan = plan_host_transition(request)

        self.assertEqual(plan.state_lineage_id, self.lineage.lineage_id)
        self.assertEqual(plan.state_generation, self.lineage.generation)
        self.assertEqual(plan.state_binding_sha256, self.binding.sha256())
        self.assertEqual(plan.target_host_id, "clean-host-b")
        self.assertEqual(plan.target_route_id, "native-route-b")
        self.assertEqual(plan.runtime_credit, 0)
        self.assertEqual(plan.physical_host_credit, 0)
        self.assertFalse(plan.whole_system_acceptance)

    def test_stale_wp1105_generation_cannot_cross_wp1109_readback_gate(self) -> None:
        with self.assertRaisesRegex(HostTransitionError, "generation mismatch"):
            HostTransitionRequest.create(
                transition_id="reject-stale-wp1105-generation",
                operation=OP_SWITCH_HOST,
                source_host_id="clean-host-a",
                source_route_id="native-route-a",
                state=self.binding,
                permissions_before=("memory.read",),
                permissions_after=("memory.read",),
                successor_route=self.successor(
                    state_readback_generation=self.lineage.generation - 1
                ),
            )


if __name__ == "__main__":
    unittest.main()
