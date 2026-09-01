from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.target_multimedia_twin import (
    MultimediaTopologySnapshot,
    ServiceState,
    SessionContext,
    SessionType,
)


class WP1203ServiceRoleIdentityFalsifier(unittest.TestCase):
    """REVIEW_ONLY discriminator for issue #426.

    Distinct role state must not disappear merely because caller-controlled
    ServiceState.name values collide. This test is intentionally expected to
    fail against WP1203 G1 until a successor implementation closes the identity
    hole. It grants no runtime, physical-target, or completion credit.
    """

    @staticmethod
    def _snapshot(*, pipewire_generation: int) -> MultimediaTopologySnapshot:
        session = SessionContext(
            generation=1,
            uid=1000,
            session_type=SessionType.WAYLAND,
            xdg_runtime_dir="/run/user/1000",
            session_dbus_available=True,
        )
        # The three structural roles intentionally share one caller-controlled
        # name. In G1 as_dict(), later dictionary entries overwrite earlier
        # ones, so PipeWire state can disappear from the canonical digest.
        pipewire = ServiceState(
            name="dup",
            generation=pipewire_generation,
            active=True,
            usable=True,
            bus_owner="pipewire@1000",
        )
        wireplumber = ServiceState(
            name="dup",
            generation=7,
            active=True,
            usable=True,
            bus_owner="wireplumber@1000",
        )
        portal = ServiceState(
            name="dup",
            generation=9,
            active=True,
            usable=True,
            bus_owner="org.freedesktop.portal.Desktop",
        )
        return MultimediaTopologySnapshot(
            session=session,
            pipewire=pipewire,
            wireplumber=wireplumber,
            portal=portal,
            endpoints=(),
        )

    def test_distinct_pipewire_role_state_cannot_collapse_to_same_digest(self):
        left = self._snapshot(pipewire_generation=1)
        right = replace(left, pipewire=replace(left.pipewire, generation=2))

        self.assertNotEqual(
            left.canonical_json(),
            right.canonical_json(),
            "structurally distinct PipeWire state collapsed during serialization",
        )
        self.assertNotEqual(
            left.sha256(),
            right.sha256(),
            "structurally distinct PipeWire state collapsed to one topology digest",
        )


if __name__ == "__main__":
    unittest.main()
