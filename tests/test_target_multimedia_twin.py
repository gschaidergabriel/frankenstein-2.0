from __future__ import annotations

import unittest

from frankenstein2.target_multimedia_twin import (
    EndpointKind,
    IssueCode,
    MultimediaTopologySnapshot,
    ServiceState,
    SessionContext,
    SessionType,
    SyntheticEndpoint,
    TopologyError,
    advance_session,
    evaluate_topology,
    rebind_endpoint,
)


def _healthy_snapshot(*, session_type: SessionType = SessionType.WAYLAND):
    session = SessionContext(
        generation=3,
        uid=1000,
        session_type=session_type,
        xdg_runtime_dir="/run/user/1000",
        session_dbus_available=True,
    )
    pipewire = ServiceState(
        name="pipewire",
        generation=7,
        active=True,
        usable=True,
        bus_owner="pipewire@1000",
    )
    wireplumber = ServiceState(
        name="wireplumber",
        generation=8,
        active=True,
        usable=True,
        bus_owner="wireplumber@1000",
    )
    portal = ServiceState(
        name="portal",
        generation=4,
        active=True,
        usable=True,
        bus_owner="org.freedesktop.portal.Desktop",
    )
    endpoints = (
        SyntheticEndpoint(
            endpoint_id="audio-source:default",
            kind=EndpointKind.AUDIO_SOURCE,
            generation=2,
            session_generation=3,
            owner_uid=1000,
            present=True,
            usable=True,
        ),
        SyntheticEndpoint(
            endpoint_id="display:0",
            kind=EndpointKind.DISPLAY,
            generation=5,
            session_generation=3,
            owner_uid=1000,
            present=True,
            usable=True,
            requires_portal=session_type is SessionType.WAYLAND,
        ),
        SyntheticEndpoint(
            endpoint_id="browser:primary",
            kind=EndpointKind.BROWSER,
            generation=1,
            session_generation=3,
            owner_uid=1000,
            present=True,
            usable=True,
            requires_portal=session_type is SessionType.WAYLAND,
        ),
    )
    return MultimediaTopologySnapshot(
        session=session,
        pipewire=pipewire,
        wireplumber=wireplumber,
        portal=portal,
        endpoints=endpoints,
    )


class TargetMultimediaTwinTests(unittest.TestCase):
    def test_healthy_wayland_topology_requires_real_portal_boundary(self):
        result = evaluate_topology(_healthy_snapshot())
        self.assertTrue(result.healthy)
        self.assertEqual(
            result.usable_endpoint_ids,
            ("audio-source:default", "browser:primary", "display:0"),
        )

    def test_service_active_does_not_equal_usable(self):
        snapshot = _healthy_snapshot()
        snapshot = MultimediaTopologySnapshot(
            session=snapshot.session,
            pipewire=ServiceState(
                name="pipewire",
                generation=7,
                active=True,
                usable=False,
                bus_owner="pipewire@1000",
            ),
            wireplumber=snapshot.wireplumber,
            portal=snapshot.portal,
            endpoints=snapshot.endpoints,
        )
        result = evaluate_topology(snapshot)
        codes = [issue.code for issue in result.issues]
        self.assertIn(IssueCode.SERVICE_ACTIVE_UNUSABLE, codes)
        self.assertIn(IssueCode.ENDPOINT_DEPENDENCY_UNAVAILABLE, codes)
        self.assertNotIn("audio-source:default", result.usable_endpoint_ids)

    def test_session_generation_change_stales_old_endpoints_until_explicit_rebind(self):
        snapshot = advance_session(_healthy_snapshot(), generation=4)
        result = evaluate_topology(snapshot)
        stale = [
            issue.subject
            for issue in result.issues
            if issue.code is IssueCode.STALE_SESSION_GENERATION
        ]
        self.assertEqual(stale, ["audio-source:default", "browser:primary", "display:0"])

        rebound = rebind_endpoint(snapshot, "audio-source:default", new_generation=3)
        result = evaluate_topology(rebound)
        stale = [
            issue.subject
            for issue in result.issues
            if issue.code is IssueCode.STALE_SESSION_GENERATION
        ]
        self.assertEqual(stale, ["browser:primary", "display:0"])
        self.assertIn("audio-source:default", result.usable_endpoint_ids)

    def test_wrong_session_owner_is_independent_failure_surface(self):
        snapshot = _healthy_snapshot()
        wrong = SyntheticEndpoint(
            endpoint_id="video:external",
            kind=EndpointKind.VIDEO_SOURCE,
            generation=1,
            session_generation=3,
            owner_uid=1001,
            present=True,
            usable=True,
        )
        snapshot = MultimediaTopologySnapshot(
            session=snapshot.session,
            pipewire=snapshot.pipewire,
            wireplumber=snapshot.wireplumber,
            portal=snapshot.portal,
            endpoints=(*snapshot.endpoints, wrong),
        )
        result = evaluate_topology(snapshot)
        self.assertTrue(
            any(
                issue.code is IssueCode.SESSION_OWNER_MISMATCH
                and issue.subject == "video:external"
                for issue in result.issues
            )
        )
        self.assertNotIn("video:external", result.usable_endpoint_ids)

    def test_portal_cannot_be_usable_from_wayland_when_session_bus_is_missing(self):
        snapshot = advance_session(
            _healthy_snapshot(),
            generation=4,
            session_dbus_available=False,
        )
        rebound_display = rebind_endpoint(snapshot, "display:0", new_generation=6)
        result = evaluate_topology(rebound_display)
        codes = [issue.code for issue in result.issues]
        self.assertIn(IssueCode.SESSION_DBUS_UNAVAILABLE, codes)
        self.assertIn(IssueCode.PORTAL_UNREACHABLE, codes)
        self.assertNotIn("display:0", result.usable_endpoint_ids)

    def test_wayland_capture_without_portal_requirement_is_rejected(self):
        snapshot = _healthy_snapshot()
        display = SyntheticEndpoint(
            endpoint_id="display:unsafe",
            kind=EndpointKind.DISPLAY,
            generation=1,
            session_generation=3,
            owner_uid=1000,
            present=True,
            usable=True,
            requires_portal=False,
        )
        snapshot = MultimediaTopologySnapshot(
            session=snapshot.session,
            pipewire=snapshot.pipewire,
            wireplumber=snapshot.wireplumber,
            portal=snapshot.portal,
            endpoints=(*snapshot.endpoints, display),
        )
        result = evaluate_topology(snapshot)
        self.assertTrue(
            any(
                issue.code is IssueCode.WAYLAND_PORTAL_REQUIRED
                and issue.subject == "display:unsafe"
                for issue in result.issues
            )
        )

    def test_x11_display_path_can_be_modelled_without_portal(self):
        snapshot = _healthy_snapshot(session_type=SessionType.X11)
        result = evaluate_topology(snapshot)
        self.assertTrue(result.healthy)

    def test_snapshot_digest_is_stable_across_endpoint_input_order(self):
        left = _healthy_snapshot()
        right = MultimediaTopologySnapshot(
            session=left.session,
            pipewire=left.pipewire,
            wireplumber=left.wireplumber,
            portal=left.portal,
            endpoints=tuple(reversed(left.endpoints)),
        )
        self.assertEqual(left.sha256(), right.sha256())

    def test_rebind_must_advance_endpoint_generation(self):
        snapshot = _healthy_snapshot()
        with self.assertRaisesRegex(TopologyError, "advance"):
            rebind_endpoint(snapshot, "display:0", new_generation=5)


if __name__ == "__main__":
    unittest.main()
