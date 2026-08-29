import unittest

from src.frankenstein2.perception_fabric import (
    PerceptionCapability,
    PerceptionCapabilitySnapshot,
)
from src.frankenstein2.perception_host_permissions import (
    HostPermissionGrant,
    PerceptionHostPermissionError,
    is_effective_host_bound_snapshot,
    require_effective_host_bound_snapshot,
    resolve_effective_perception_snapshot,
)


P = ("test:host-permission",)


def requested(caps, source_id="screen:1"):
    return PerceptionCapabilitySnapshot(
        snapshot_id=f"requested:{source_id}",
        generation=2,
        source_id=source_id,
        capabilities=caps,
        valid_from_monotonic_ns=10,
        expires_monotonic_ns=1_000,
        provenance_refs=P,
    )


def grant(caps, source_id="screen:1", expires=900):
    return HostPermissionGrant(
        grant_id=f"grant:{source_id}",
        source_id=source_id,
        generation=3,
        granted_capabilities=caps,
        valid_from_monotonic_ns=20,
        expires_monotonic_ns=expires,
        host_adapter_id="linux-pipewire:test",
        native_permission_ref=f"portal-grant:{source_id}",
        provenance_refs=P,
    )


class PerceptionHostPermissionTests(unittest.TestCase):
    def test_dashboard_or_requested_snapshot_is_not_effective_host_permission(self):
        r = requested((PerceptionCapability.SEE,))
        self.assertFalse(is_effective_host_bound_snapshot(r))
        with self.assertRaisesRegex(PerceptionHostPermissionError, "dashboard policy alone"):
            require_effective_host_bound_snapshot(r)

    def test_effective_snapshot_is_intersection_of_user_and_host(self):
        r = requested((
            PerceptionCapability.SEE,
            PerceptionCapability.ANALYZE,
            PerceptionCapability.MEMORY,
            PerceptionCapability.REMOTE_FRAME,
        ))
        g = grant((
            PerceptionCapability.SEE,
            PerceptionCapability.ANALYZE,
            PerceptionCapability.MEMORY,
        ))
        effective = resolve_effective_perception_snapshot(
            requested_snapshot=r,
            host_grant=g,
            now_monotonic_ns=100,
            provenance_refs=P,
        )
        self.assertTrue(is_effective_host_bound_snapshot(effective))
        self.assertTrue(effective.allows(PerceptionCapability.SEE))
        self.assertTrue(effective.allows(PerceptionCapability.ANALYZE))
        self.assertTrue(effective.allows(PerceptionCapability.MEMORY))
        self.assertFalse(effective.allows(PerceptionCapability.REMOTE_FRAME))
        self.assertEqual(effective.valid_from_monotonic_ns, 20)
        self.assertEqual(effective.expires_monotonic_ns, 900)

    def test_host_revocation_to_zero_caps_removes_user_requested_capture(self):
        r = requested((PerceptionCapability.SEE, PerceptionCapability.ANALYZE))
        g = grant(())
        effective = resolve_effective_perception_snapshot(
            requested_snapshot=r,
            host_grant=g,
            now_monotonic_ns=100,
            provenance_refs=P,
        )
        self.assertEqual(effective.capabilities, ())
        self.assertTrue(is_effective_host_bound_snapshot(effective))

    def test_dependency_closure_removes_external_vlm_if_host_lacks_analyze(self):
        r = requested((
            PerceptionCapability.SEE,
            PerceptionCapability.ANALYZE,
            PerceptionCapability.EXTERNAL_VLM,
        ))
        g = grant((PerceptionCapability.SEE, PerceptionCapability.EXTERNAL_VLM))
        effective = resolve_effective_perception_snapshot(
            requested_snapshot=r,
            host_grant=g,
            now_monotonic_ns=100,
            provenance_refs=P,
        )
        self.assertEqual(effective.capabilities, (PerceptionCapability.SEE,))

    def test_mismatched_source_fails_closed(self):
        with self.assertRaisesRegex(PerceptionHostPermissionError, "source_id mismatch"):
            resolve_effective_perception_snapshot(
                requested_snapshot=requested((PerceptionCapability.SEE,), "screen:1"),
                host_grant=grant((PerceptionCapability.SEE,), "camera:1"),
                now_monotonic_ns=100,
                provenance_refs=P,
            )

    def test_expired_host_grant_fails_closed(self):
        with self.assertRaisesRegex(PerceptionHostPermissionError, "host permission grant"):
            resolve_effective_perception_snapshot(
                requested_snapshot=requested((PerceptionCapability.SEE,)),
                host_grant=grant((PerceptionCapability.SEE,), expires=50),
                now_monotonic_ns=100,
                provenance_refs=P,
            )


if __name__ == "__main__":
    unittest.main()
