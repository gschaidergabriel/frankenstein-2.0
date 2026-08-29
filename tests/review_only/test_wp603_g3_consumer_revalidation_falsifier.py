from __future__ import annotations

import runpy
import unittest

from frankenstein2.direct_delegate_router import DELEGATE_BUILD
from frankenstein2.recursion_router import R1, R2, RecursionNeed, RecursionRouterError, route_recursion


_FIXTURES = runpy.run_path("tests/test_recursion_router.py")
make_route = _FIXTURES["make_route"]
make_policy = _FIXTURES["make_policy"]


class WP603G3ConsumerRevalidationFalsifier(unittest.TestCase):
    """REVIEW_ONLY regressions for the active WP603-G3 consumer boundary.

    These tests intentionally mutate frozen dataclasses through object.__setattr__ to model
    post-construction in-process drift. route_recursion() must reconstruct/revalidate the
    exact current RecursionNeed and RecursionPolicy content before consuming any fields.
    """

    def test_need_generation_drift_is_rejected_before_consumption(self) -> None:
        route = make_route(selected=DELEGATE_BUILD, suffix="g3-need-drift")
        need = RecursionNeed.create(
            route_candidate=route,
            requested_mode=R1,
            generation=1,
            provenance_refs=("review:wp603:g3:need-drift",),
        )
        policy = make_policy()

        object.__setattr__(need, "generation", 2)

        with self.assertRaises(RecursionRouterError):
            route_recursion(route_candidate=route, need=need, policy=policy)

    def test_policy_invariant_drift_is_rejected_before_consumption(self) -> None:
        route = make_route(selected=DELEGATE_BUILD, suffix="g3-policy-drift")
        need = RecursionNeed.create(
            route_candidate=route,
            requested_mode=R1,
            generation=1,
            provenance_refs=("review:wp603:g3:policy-drift",),
        )
        policy = make_policy()

        # Invalid by RecursionPolicy.__post_init__: duplicate adaptive preference entries.
        # The R1 path does not otherwise consult this field, so consumer revalidation is
        # required to prevent an invalid current policy object from being accepted.
        object.__setattr__(policy, "r3_preference_order", (R2, R2, R1))

        with self.assertRaises(RecursionRouterError):
            route_recursion(route_candidate=route, need=need, policy=policy)


if __name__ == "__main__":
    unittest.main()
