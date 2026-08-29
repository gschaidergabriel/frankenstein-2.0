import unittest

from src.frankenstein2.perception_dashboard_policy import (
    PerceptionDashboardError,
    capability_snapshot_from_dashboard,
    create_dashboard_state,
    set_global_pause,
    set_source_policy,
)
from src.frankenstein2.perception_fabric import PerceptionCapability


P = ("test:dashboard",)


class PerceptionDashboardPolicyTests(unittest.TestCase):
    def test_source_policy_compiles_exact_capability_snapshot(self):
        state = create_dashboard_state(
            state_id="dashboard:1",
            max_active_cortex_workers=4,
            provenance_refs=P,
        )
        state = set_source_policy(
            state=state,
            source_id="camera:front",
            enabled=True,
            capabilities=(
                PerceptionCapability.SEE,
                PerceptionCapability.ANALYZE,
                PerceptionCapability.MEMORY,
            ),
            provenance_refs=P,
        )
        snap = capability_snapshot_from_dashboard(
            state=state,
            source_id="camera:front",
            valid_from_monotonic_ns=100,
            expires_monotonic_ns=1_000,
            provenance_refs=P,
        )
        self.assertTrue(snap.allows(PerceptionCapability.SEE))
        self.assertTrue(snap.allows(PerceptionCapability.ANALYZE))
        self.assertTrue(snap.allows(PerceptionCapability.MEMORY))
        self.assertFalse(snap.allows(PerceptionCapability.REMOTE_FRAME))

    def test_global_pause_compiles_to_zero_capabilities(self):
        state = create_dashboard_state(state_id="dashboard:1", provenance_refs=P)
        state = set_source_policy(
            state=state,
            source_id="screen:1",
            enabled=True,
            capabilities=(PerceptionCapability.SEE, PerceptionCapability.ANALYZE),
            provenance_refs=P,
        )
        state = set_global_pause(state=state, paused=True, provenance_refs=P)
        snap = capability_snapshot_from_dashboard(
            state=state,
            source_id="screen:1",
            valid_from_monotonic_ns=100,
            expires_monotonic_ns=1_000,
            provenance_refs=P,
        )
        self.assertEqual(snap.capabilities, ())

    def test_disabling_source_revokes_all_caps_even_if_caller_passes_old_caps(self):
        state = create_dashboard_state(state_id="dashboard:1", provenance_refs=P)
        state = set_source_policy(
            state=state,
            source_id="browser:profile",
            enabled=True,
            capabilities=(PerceptionCapability.SEE, PerceptionCapability.ANALYZE),
            provenance_refs=P,
        )
        state = set_source_policy(
            state=state,
            source_id="browser:profile",
            enabled=False,
            capabilities=(PerceptionCapability.SEE, PerceptionCapability.ANALYZE),
            provenance_refs=P,
        )
        snap = capability_snapshot_from_dashboard(
            state=state,
            source_id="browser:profile",
            valid_from_monotonic_ns=100,
            expires_monotonic_ns=1_000,
            provenance_refs=P,
        )
        self.assertEqual(snap.capabilities, ())
        self.assertFalse(state.policy_for("browser:profile").enabled)

    def test_unknown_source_cannot_get_snapshot(self):
        state = create_dashboard_state(state_id="dashboard:1", provenance_refs=P)
        with self.assertRaisesRegex(PerceptionDashboardError, "no dashboard policy"):
            capability_snapshot_from_dashboard(
                state=state,
                source_id="camera:missing",
                valid_from_monotonic_ns=100,
                expires_monotonic_ns=1_000,
                provenance_refs=P,
            )

    def test_worker_ceiling_is_zero_to_four(self):
        with self.assertRaisesRegex(PerceptionDashboardError, "\[0, 4\]"):
            create_dashboard_state(
                state_id="dashboard:1",
                max_active_cortex_workers=5,
                provenance_refs=P,
            )

    def test_dashboard_policy_is_not_os_permission_proof(self):
        state = create_dashboard_state(state_id="dashboard:1", provenance_refs=P)
        state = set_source_policy(
            state=state,
            source_id="screen:1",
            enabled=True,
            capabilities=(PerceptionCapability.SEE,),
            provenance_refs=P,
        )
        policy = state.policy_for("screen:1")
        self.assertFalse(policy.as_dict()["os_permission_proven"])
        self.assertEqual(policy.as_dict()["sensor_execution_authority"], "NONE")


if __name__ == "__main__":
    unittest.main()
